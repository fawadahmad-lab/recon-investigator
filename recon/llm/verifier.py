"""The six mandatory verifier checks, the single retry, and the deterministic fallback."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from recon.errors import LLMError
from recon.evidence.packet import EvidencePacket, packet_hash
from recon.llm.base import LLMProvider
from recon.llm.mock import build_output
from recon.llm.schema import Investigation, parse_investigation, to_explanation
from recon.models import Confidence, Explanation, ExplanationSource, RecommendedAction

LOGGER = logging.getLogger(__name__)

SCHEMA_INVALID = "schema_invalid"
BAD_ENUM = "bad_enum"
UNSUPPORTED_CITED_FACT = "unsupported_cited_fact"
UNSUPPORTED_FIGURE = "unsupported_figure"
DECISION_OVERRIDE = "decision_override"
CONFIDENCE_INCONSISTENT = "confidence_inconsistent"

FAILURE_CODES: tuple[str, ...] = (
    SCHEMA_INVALID,
    BAD_ENUM,
    UNSUPPORTED_CITED_FACT,
    UNSUPPORTED_FIGURE,
    DECISION_OVERRIDE,
    CONFIDENCE_INCONSISTENT,
)

RETRY_LIMIT = 1
FALLBACK_CAUSE = "unknown"
VERDICT_ACCEPTED = "accepted"
VERDICT_REJECTED = "rejected"
VERDICT_ERROR = "provider_error"

_MONEY_PATTERN = r"-?\d+\.\d{2}"
_NUMERIC_RE = re.compile(r"-?\d+(?:\.\d+)?")
# The grouped alternative comes first so "1,234.56" is one token, not "234.56".
_FIGURE_RE = re.compile(
    rf"-?\d{{1,3}}(?:,\d{{3}})+\.\d{{2}}|{_MONEY_PATTERN}|\d{{4}}-\d{{2}}-\d{{2}}|[LB]-\d{{6}}|F-\d{{4}}"
)
_PROSE_FIELDS = ("summary", "explanation", "action_detail")

# Every pattern argues about the match decision instead of explaining it.
OVERRIDE_PATTERNS: tuple[str, ...] = (
    r"\bdo(?: ?n[o']?t)? match\b",
    r"\bdid(?: ?n[o']?t)? match\b",
    r"\bwill match\b",
    r"\bdoes not match\b",
    r"\b(?:is|was|were|are)(?: not)? a duplicate\b",
    r"\b(?:is|was|were|are)(?: not)? matched\b",
    r"\bshould be treated\b",
    r"\b(?:should|must) be (?:reclassif\w*|relabel\w*|removed|deleted|ignored|reversed)\b",
    r"\breclassif\w*",
    r"\brelabel\w*",
    r"\bnot a discrepancy\b",
    r"\bno discrepancy\b",
    r"\bcorrect decision\b",
)

_OVERRIDE_RES = tuple(re.compile(pattern, re.IGNORECASE) for pattern in OVERRIDE_PATTERNS)


@dataclass(frozen=True)
class Attempt:
    """One provider call and the verifier's verdict on its answer."""

    index: int
    raw: str
    failure_codes: tuple[str, ...]
    request_codes: tuple[str, ...]
    verdict: str

    @property
    def failed(self) -> bool:
        """True when the verifier rejected this answer."""
        return bool(self.failure_codes)


@dataclass(frozen=True)
class VerifiedExplanation:
    """The explanation the report may use, plus the auditable attempt history."""

    explanation: Explanation
    source: ExplanationSource
    attempts: tuple[Attempt, ...]


def _decimal(value: str) -> Decimal | None:
    """Parse a numeric string, returning `None` instead of raising."""
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _numeric_allowed(value: str, allowed: dict[str, list[str]]) -> bool:
    """Compare one numeric token against the packet amounts and numbers as `Decimal`."""
    number = _decimal(value)
    if number is None:
        return False
    pool = list(allowed.get("amounts", [])) + list(allowed.get("numbers", []))
    return any(number == other for other in map(_decimal, pool) if other is not None)


def _cited_value_allowed(packet: EvidencePacket, value: str) -> bool:
    """Test one cited fact: money as `Decimal`, dates and IDs exactly, nothing else."""
    allowed = packet.allowed_values
    if _NUMERIC_RE.fullmatch(value):
        return _numeric_allowed(value, allowed)
    return any(value in items for items in allowed.values())


def _bad_cited_facts(packet: EvidencePacket, investigation: Investigation) -> list[str]:
    """Return the cited values the packet does not actually carry."""
    return [
        fact.value
        for fact in investigation.cited_facts
        if not _cited_value_allowed(packet, fact.value)
    ]


def _prose(investigation: Investigation) -> str:
    """Join every free-text field the verifier must scan."""
    parts = [str(getattr(investigation, name)) for name in _PROSE_FIELDS]
    parts.extend(investigation.uncertainties)
    return " ".join(parts)


def _unsupported_figures(packet: EvidencePacket, text: str) -> list[str]:
    """Find money, date and ID-like tokens in prose that the packet never showed."""
    allowed = packet.allowed_values
    offenders: list[str] = []
    for token in _FIGURE_RE.findall(text):
        if _NUMERIC_RE.fullmatch(token):
            ok = _numeric_allowed(token, allowed)
        else:
            ok = any(token in items for items in allowed.values())
        if not ok:
            offenders.append(token)
    return offenders


def _override_hits(text: str) -> list[str]:
    """Report the decision-argument phrases found in prose."""
    return [pattern.pattern for pattern in _OVERRIDE_RES if pattern.search(text)]


def _action_allowed(investigation: Investigation) -> bool:
    """Check the action against the enum at verification time, not only at parse time."""
    return str(investigation.recommended_action) in {str(item) for item in RecommendedAction}


def _confidence_consistent(investigation: Investigation) -> bool:
    """`unknown` must always be paired with `low` confidence."""
    if investigation.likely_cause != FALLBACK_CAUSE:
        return True
    return investigation.confidence is Confidence.LOW


def verify(packet: EvidencePacket, raw: str) -> tuple[Investigation | None, tuple[str, ...]]:
    """Run the six documented checks; return the answer (if parseable) and its failure codes."""
    try:
        investigation = parse_investigation(raw)
    except LLMError:
        return None, (SCHEMA_INVALID,)
    codes: list[str] = []
    cause_allowed = investigation.likely_cause in packet.allowed_causes
    if not cause_allowed or not _action_allowed(investigation):
        codes.append(BAD_ENUM)
    if _bad_cited_facts(packet, investigation):
        codes.append(UNSUPPORTED_CITED_FACT)
    text = _prose(investigation)
    if _unsupported_figures(packet, text):
        codes.append(UNSUPPORTED_FIGURE)
    if _override_hits(text):
        codes.append(DECISION_OVERRIDE)
    if not _confidence_consistent(investigation):
        codes.append(CONFIDENCE_INCONSISTENT)
    return investigation, tuple(codes)


def fallback_explanation(packet: EvidencePacket) -> Explanation:
    """Build the marked deterministic explanation from packet values only."""
    cause = FALLBACK_CAUSE if FALLBACK_CAUSE in packet.allowed_causes else packet.allowed_causes[-1]
    return to_explanation(build_output(packet, cause), ExplanationSource.DETERMINISTIC_FALLBACK)


def explain_verified(packet: EvidencePacket, provider: LLMProvider) -> VerifiedExplanation:
    """Ask once, retry once with the failure codes, then fall back deterministically."""
    attempts: list[Attempt] = []
    codes: tuple[str, ...] = ()
    for index in range(RETRY_LIMIT + 1):
        try:
            raw = provider.complete(packet, codes)
        except LLMError as error:
            LOGGER.warning(
                "llm_error finding=%s provider=%s error=%s", packet.finding_id, provider.name, error
            )
            attempts.append(
                Attempt(
                    index=index,
                    raw=str(error),
                    failure_codes=(),
                    request_codes=codes,
                    verdict=VERDICT_ERROR,
                )
            )
            break
        investigation, failure = verify(packet, raw)
        attempts.append(
            Attempt(
                index=index,
                raw=raw,
                failure_codes=failure,
                request_codes=codes,
                verdict=VERDICT_ACCEPTED if not failure else VERDICT_REJECTED,
            )
        )
        if investigation is not None and not failure:
            return VerifiedExplanation(
                explanation=to_explanation(investigation, ExplanationSource.AI_VERIFIED),
                source=ExplanationSource.AI_VERIFIED,
                attempts=tuple(attempts),
            )
        codes = failure
    return VerifiedExplanation(
        explanation=fallback_explanation(packet),
        source=ExplanationSource.DETERMINISTIC_FALLBACK,
        attempts=tuple(attempts),
    )


def attempt_records(
    packet: EvidencePacket, provider: LLMProvider, attempts: Sequence[Attempt]
) -> list[dict[str, Any]]:
    """Render one auditable record per provider attempt for `verifier_log.jsonl`."""
    digest = packet_hash(packet)
    return [
        {
            "packet_hash": digest,
            "finding_id": packet.finding_id,
            "finding_type": str(packet.finding_type),
            "provider": provider.name,
            "model": provider.model_name,
            "attempt": attempt.index,
            "request_codes": list(attempt.request_codes),
            "failure_codes": list(attempt.failure_codes),
            "verdict": attempt.verdict,
            "raw": attempt.raw,
        }
        for attempt in attempts
    ]


def write_verifier_log(
    path: Path, records: Sequence[dict[str, Any]], truncate: bool = False
) -> None:
    """Write the verifier records; `truncate` starts a fresh file for a new run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w" if truncate else "a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")
