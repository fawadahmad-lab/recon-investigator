"""Evidence packets: the code-built, verifier-bounded input for LLM explanations."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from recon.config import Settings
from recon.matching.fuzzy import fuzzy_components
from recon.models import EvidencePacket, Finding, Rule, Source, Transaction, from_minor

MAX_CANDIDATES = 3
AMBIGUOUS_SPLIT_REASON = "several combinations of these records sum to the anchor amount"

ALLOWED_CAUSES: dict[str, tuple[str, ...]] = {
    "missing_in_bank": (
        "timing_delay_not_cleared",
        "payment_not_sent",
        "recorded_in_wrong_period",
        "recorded_in_error",
        "bank_statement_incomplete",
        "unknown",
    ),
    "missing_in_ledger": (
        "unrecorded_bank_item",
        "bank_fee_or_interest",
        "unexpected_or_unauthorized",
        "recorded_in_other_account",
        "unknown",
    ),
    "duplicate_in_ledger": ("double_entry_in_ledger", "bank_missing_second_payment", "unknown"),
    "duplicate_in_bank": ("duplicate_bank_charge", "ledger_missing_second_entry", "unknown"),
    "amount_mismatch": (
        "typo_or_transposition",
        "partial_payment",
        "discount_or_adjustment",
        "fx_or_rounding",
        "unknown",
    ),
    "fee_difference": ("bank_fee_deducted", "rounding", "unknown"),
    "date_mismatch": ("late_posting", "wrong_period_entry", "unknown"),
    "ambiguous_split": ("multiple_possible_combinations", "unknown"),
}
LLM_FINDING_TYPES = tuple(ALLOWED_CAUSES)

RULE_DESCRIPTIONS: dict[str, str] = {
    "R0-INVALID": "Row rejected during validation and excluded from matching.",
    "R1-EXACT": (
        "Equal currency, equal amount, identical non-empty reference and a date difference "
        "within the exact window."
    ),
    "R2-FUZZY": (
        "Equal currency and amount inside the fuzzy date window, accepted by a weighted "
        "reference, description and date score."
    ),
    "R3-DUP": (
        "Unmatched record identical in currency, amount and reference to a matched record "
        "from the same source inside the duplicate window."
    ),
    "R4-AMT": (
        "Strong-reference pair inside the fuzzy window with different amounts and a unique "
        "best candidate; a small bank shortfall is a fee."
    ),
    "R5-DATE": (
        "Equal currency, amount and reference with a date difference beyond the fuzzy window "
        "and inside the mismatch window."
    ),
    "R6-SPLIT": (
        "Anchor amount equal to the sum of records on the other side inside the split window; "
        "more than one combination is reported as ambiguous."
    ),
    "R7-MISSING": "Record left unmatched by every rule ahead of it.",
}

_AMOUNT_RE = re.compile(r"-?\d+\.\d{2}")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ID_RE = re.compile(r"(?:[LB]-\d{6}|F-\d{4})")
_SOURCE_ORDER = {Source.LEDGER: 0, Source.BANK: 1}


def packet_amount(amount_minor: int) -> str:
    """Render minor units as the packet's fixed two-decimal amount string."""
    return f"{from_minor(amount_minor):.2f}"


def packet_json(packet: EvidencePacket) -> str:
    """Serialize a packet with sorted keys so equal packets are byte-equal."""
    return json.dumps(packet.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def packet_hash(packet: EvidencePacket) -> str:
    """Return the SHA-256 of the packet, used as the explanation cache key."""
    return hashlib.sha256(packet_json(packet).encode("utf-8")).hexdigest()


def _iter_values(value: Any) -> Iterator[Any]:
    """Yield every scalar value inside a JSON-like structure."""
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _iter_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_values(item)
    else:
        yield value


def _sort_key(text: str) -> tuple[int, Decimal, str]:
    """Order numeric strings by value, falling back to text."""
    try:
        return (0, Decimal(text), "")
    except InvalidOperation:
        return (1, Decimal(0), text)


def _collect_allowed_values(payload: Any) -> dict[str, list[str]]:
    """Read every amount, date, identifier and number out of the packet itself."""
    buckets: dict[str, set[str]] = {
        "amounts": set(),
        "dates": set(),
        "ids": set(),
        "numbers": set(),
    }
    for value in _iter_values(payload):
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            buckets["numbers"].add(str(value))
        elif not isinstance(value, str):
            continue
        elif _AMOUNT_RE.fullmatch(value):
            buckets["amounts"].add(value)
        elif _DATE_RE.fullmatch(value):
            buckets["dates"].add(value)
        elif _ID_RE.fullmatch(value):
            buckets["ids"].add(value)
    return {name: sorted(values, key=_sort_key) for name, values in buckets.items()}


def _packet_record(record: Transaction) -> dict[str, Any]:
    """Project one transaction onto the packet's record shape."""
    return {
        "role": str(record.source),
        "id": record.id,
        "row_number": record.row_number,
        "date": record.date.isoformat(),
        "amount": packet_amount(record.amount_minor),
        "currency": record.currency,
        "reference_raw": record.reference_raw,
        "reference_norm": record.reference_norm,
        "description_raw": record.description_raw,
    }


def _packet_facts(facts: Mapping[str, Any]) -> dict[str, Any]:
    """Convert minor-unit amounts to decimal strings without changing any value."""
    converted: dict[str, Any] = {}
    for name in sorted(facts):
        value = facts[name]
        if name.endswith("_minor"):
            converted[name[: -len("_minor")]] = packet_amount(value)
        elif isinstance(value, Mapping):
            converted[name] = _packet_facts(value)
        else:
            converted[name] = value
    return converted


def _evidence_ids(finding: Finding, records_by_id: Mapping[str, Transaction]) -> list[str]:
    """List every record the packet needs, including records named only inside the facts."""
    identifiers = set(finding.ledger_ids) | set(finding.bank_ids)
    for value in _iter_values(finding.facts):
        if isinstance(value, str) and _ID_RE.fullmatch(value):
            identifiers.add(value)
    missing = sorted(identifiers - set(records_by_id))
    if missing:
        raise ValueError(f"Finding {finding.id} references unknown records: {missing}")
    return sorted(
        identifiers,
        key=lambda identifier: (_SOURCE_ORDER[records_by_id[identifier].source], identifier),
    )


def _split_candidates(
    finding: Finding, records_by_id: Mapping[str, Transaction], settings: Settings
) -> list[dict[str, Any]]:
    """Score each candidate of an ambiguous split against the anchor it failed to match."""
    anchor = records_by_id[str(finding.facts["anchor_id"])]
    identifiers = {
        identifier
        for group in finding.facts["candidate_sets"]
        for identifier in group
        if identifier != anchor.id
    }
    scored: list[dict[str, Any]] = []
    for identifier in sorted(identifiers):
        candidate = records_by_id[identifier]
        if candidate.source is anchor.source:
            continue
        ledger, bank = (
            (anchor, candidate) if anchor.source is Source.LEDGER else (candidate, anchor)
        )
        reference, description, day = fuzzy_components(
            ledger, bank, settings.split_date_window_days
        )
        score = 0.5 * reference + 0.35 * description + 0.15 * day
        scored.append(
            {
                "id": identifier,
                "score": round(score, 4),
                "components": {
                    "ref_sim": round(reference, 4),
                    "desc_sim": round(description, 4),
                    "date_sim": round(day, 4),
                },
                "rejected_reason": AMBIGUOUS_SPLIT_REASON,
            }
        )
    scored.sort(key=lambda item: (-item["score"], item["id"]))
    return scored[:MAX_CANDIDATES]


def build_packet(
    finding: Finding, records_by_id: Mapping[str, Transaction], settings: Settings
) -> EvidencePacket:
    """Build the full evidence packet for one discrepancy the LLM is allowed to explain."""
    finding_type = str(finding.type)
    if finding_type not in ALLOWED_CAUSES:
        raise ValueError(f"{finding_type} findings are not explained by the LLM")
    identifiers = _evidence_ids(finding, records_by_id)
    records = [_packet_record(records_by_id[identifier]) for identifier in identifiers]
    candidates = (
        _split_candidates(finding, records_by_id, settings)
        if finding_type == "ambiguous_split"
        else []
    )
    packet = EvidencePacket(
        packet_version="1",
        finding_id=finding.id,
        finding_type=finding.type,
        rule=Rule(
            id=finding.rule_id,
            version=finding.rule_version,
            description=RULE_DESCRIPTIONS[finding.rule_id],
        ),
        records=records,
        candidates_considered=candidates,
        facts=_packet_facts(finding.facts),
        allowed_causes=list(ALLOWED_CAUSES[finding_type]),
        allowed_values={},
    )
    packet.allowed_values = _collect_allowed_values(packet.model_dump(mode="json"))
    return packet
