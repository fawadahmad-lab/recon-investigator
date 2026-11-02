"""Explanation pipeline: packets in, verified explanations or rationales attached out."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from recon.config import Settings, get_settings
from recon.evidence.packet import ALLOWED_CAUSES, RULE_DESCRIPTIONS, EvidencePacket, build_packet
from recon.llm.base import LLMProvider
from recon.llm.verifier import (
    VERDICT_ERROR,
    VerifiedExplanation,
    attempt_records,
    explain_verified,
)
from recon.models import (
    CitedFact,
    Confidence,
    Explanation,
    ExplanationSource,
    Finding,
    RecommendedAction,
    Transaction,
)

LOGGER = logging.getLogger(__name__)

MATCH_CAUSE = "matched_by_rule"
INVALID_CAUSE = "invalid_row"
INVALID_TYPE = "invalid_record"
MATCH_ACTION_DETAIL = "No follow-up: the deterministic rule chain matched these records."
INVALID_ACTION_DETAIL = "Correct the source row and rerun the file; it took no part in matching."
MAX_SUMMARY = 200
MAX_EXPLANATION = 800


@dataclass(frozen=True)
class ExplanationOutcome:
    """Findings with explanations, plus the verifier audit records and run statistics."""

    findings: list[Finding]
    verifier_records: list[dict[str, Any]]
    stats: dict[str, Any]


def is_explainable(finding: Finding) -> bool:
    """True for the discrepancy types the LLM is allowed to explain."""
    return str(finding.type) in ALLOWED_CAUSES


def _rationale_text(finding: Finding) -> str:
    """Compose the one-line deterministic explanation of a match or an invalid row."""
    if str(finding.type) == INVALID_TYPE:
        message = str(finding.facts.get("message") or finding.facts.get("code") or "invalid row")
        row = finding.facts.get("row_number")
        return f"{finding.rule_id}: {message} Row {row} was excluded before matching."
    description = RULE_DESCRIPTIONS.get(finding.rule_id, finding.rule_id)
    identifiers = ", ".join([*finding.ledger_ids, *finding.bank_ids])
    return f"{finding.rule_id}: {description} Records {identifiers}."


def rationale(finding: Finding) -> Explanation:
    """Explain a match or an invalid row with deterministic code, never with the LLM."""
    invalid = str(finding.type) == INVALID_TYPE
    cited = [CitedFact(field="finding.id", value=finding.id)]
    cited += [
        CitedFact(field=f"record.{position}", value=identifier)
        for position, identifier in enumerate([*finding.ledger_ids, *finding.bank_ids])
    ]
    if invalid:
        cited.append(CitedFact(field="code", value=str(finding.facts.get("code", ""))))
    if finding.score is not None:
        cited.append(CitedFact(field="score", value=str(round(finding.score, 4))))
    action = RecommendedAction.INVESTIGATE if invalid else RecommendedAction.NO_ACTION
    return Explanation(
        summary=f"{finding.id}: {finding.type}".replace("_", " ")[:MAX_SUMMARY],
        likely_cause=INVALID_CAUSE if invalid else MATCH_CAUSE,
        explanation=_rationale_text(finding)[:MAX_EXPLANATION],
        cited_facts=cited,
        recommended_action=action,
        action_detail=INVALID_ACTION_DETAIL if invalid else MATCH_ACTION_DETAIL,
        confidence=Confidence.HIGH,
        uncertainties=[],
        explanation_source=ExplanationSource.DETERMINISTIC_FALLBACK,
    )


def build_packets(
    findings: Sequence[Finding], records_by_id: Mapping[str, Transaction], settings: Settings
) -> list[tuple[int, EvidencePacket]]:
    """Build one packet per explainable finding, keyed by its position in the run."""
    return [
        (index, build_packet(finding, records_by_id, settings))
        for index, finding in enumerate(findings)
        if is_explainable(finding)
    ]


def _answer_all(
    packets: Sequence[tuple[int, EvidencePacket]], provider: LLMProvider, settings: Settings
) -> dict[int, VerifiedExplanation]:
    """Answer every packet with bounded concurrency, keeping the finding order."""
    if not packets:
        return {}
    workers = max(1, min(len(packets), settings.llm_max_concurrency))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            (index, pool.submit(explain_verified, packet, provider)) for index, packet in packets
        ]
    return {index: future.result() for index, future in futures}


def explain_findings(
    findings: Sequence[Finding],
    records_by_id: Mapping[str, Transaction],
    provider: LLMProvider,
    settings: Settings | None = None,
) -> ExplanationOutcome:
    """Attach a verified explanation to each discrepancy and a rationale to each match."""
    config = settings or get_settings()
    packets = build_packets(findings, records_by_id, config)
    answers = _answer_all(packets, provider, config)
    records: list[dict[str, Any]] = []
    for index, packet in packets:
        records.extend(attempt_records(packet, provider, answers[index].attempts))

    updated = [
        finding.model_copy(
            update={
                "explanation": (
                    answers[index].explanation if index in answers else rationale(finding)
                )
            }
        )
        for index, finding in enumerate(findings)
    ]
    return ExplanationOutcome(
        findings=updated,
        verifier_records=records,
        stats=explanation_stats(provider, answers, len(records)),
    )


def explanation_stats(
    provider: LLMProvider, answers: Mapping[int, VerifiedExplanation], records: int
) -> dict[str, Any]:
    """Summarise the explanation stage for `run_meta.json`."""
    outcomes = list(answers.values())
    sources = [str(outcome.source) for outcome in outcomes]
    attempts = [attempt for outcome in outcomes for attempt in outcome.attempts]
    return {
        "provider": provider.name,
        "model": provider.model_name,
        "explained": len(outcomes),
        "ai_verified": sources.count(str(ExplanationSource.AI_VERIFIED)),
        "deterministic_fallback": sources.count(str(ExplanationSource.DETERMINISTIC_FALLBACK)),
        "retried": sum(1 for outcome in outcomes if len(outcome.attempts) > 1),
        "rejected_answers": sum(1 for attempt in attempts if attempt.failed),
        "provider_errors": sum(1 for attempt in attempts if attempt.verdict == VERDICT_ERROR),
        "verifier_records": records,
    }
