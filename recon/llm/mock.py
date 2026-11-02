"""Deterministic offline providers: `mock` and the test-only `faulty_mock`."""

from __future__ import annotations

import json
from typing import Any

from recon.errors import ValidationError
from recon.evidence.packet import EvidencePacket, packet_hash
from recon.llm.schema import Investigation
from recon.models import CitedFact, Confidence, RecommendedAction

CAUSE_PHRASES: dict[str, str] = {
    "timing_delay_not_cleared": (
        "The payment was probably issued but had not reached the bank by the statement cut-off."
    ),
    "payment_not_sent": (
        "The ledger entry may record a payment that was never released to the bank."
    ),
    "recorded_in_wrong_period": (
        "The item may belong to a different accounting period than the one it was booked in."
    ),
    "recorded_in_error": (
        "The ledger entry may have been created by mistake or for the wrong party."
    ),
    "bank_statement_incomplete": (
        "The statement may not cover the whole period, so the bank side can be incomplete."
    ),
    "unrecorded_bank_item": "The bank movement exists but was never entered in the ledger.",
    "bank_fee_or_interest": (
        "The amount has the size and shape of a bank charge or interest posting."
    ),
    "unexpected_or_unauthorized": (
        "The posting was not expected from the ledger and needs an authorization check."
    ),
    "recorded_in_other_account": "The item may have been booked in a different ledger account.",
    "double_entry_in_ledger": "The same payment appears to have been booked twice in the ledger.",
    "bank_missing_second_payment": (
        "The second ledger copy may be a real payment the bank has not shown yet."
    ),
    "duplicate_bank_charge": "The bank appears to have charged the same item twice.",
    "ledger_missing_second_entry": (
        "The bank shows two movements while the ledger records only one of them."
    ),
    "typo_or_transposition": (
        "The two amounts differ in a way typical of a keying error or transposed digits."
    ),
    "partial_payment": "The smaller amount may be one instalment of the larger one.",
    "discount_or_adjustment": "The difference may be a discount, credit or negotiated adjustment.",
    "fx_or_rounding": "The difference is small enough to come from a currency step or rounding.",
    "bank_fee_deducted": "The bank appears to have deducted a charge from the amount it settled.",
    "rounding": "The difference looks like a rounding artefact rather than a real payment gap.",
    "late_posting": "The bank posted the item later than the ledger recorded it.",
    "wrong_period_entry": (
        "One side appears to be booked in a period that does not match the other."
    ),
    "multiple_possible_combinations": (
        "More than one combination of bank items adds up to the ledger amount."
    ),
    "unknown": "The packet does not contain enough evidence to identify a cause.",
}

CAUSE_ACTIONS: dict[str, RecommendedAction] = {
    "timing_delay_not_cleared": RecommendedAction.WAIT_AND_RECHECK,
    "payment_not_sent": RecommendedAction.INVESTIGATE,
    "recorded_in_wrong_period": RecommendedAction.POST_ADJUSTING_ENTRY,
    "recorded_in_error": RecommendedAction.POST_ADJUSTING_ENTRY,
    "bank_statement_incomplete": RecommendedAction.REQUEST_BANK_CONFIRMATION,
    "unrecorded_bank_item": RecommendedAction.POST_ADJUSTING_ENTRY,
    "bank_fee_or_interest": RecommendedAction.POST_ADJUSTING_ENTRY,
    "unexpected_or_unauthorized": RecommendedAction.INVESTIGATE,
    "recorded_in_other_account": RecommendedAction.POST_ADJUSTING_ENTRY,
    "double_entry_in_ledger": RecommendedAction.REVERSE_DUPLICATE,
    "bank_missing_second_payment": RecommendedAction.REQUEST_BANK_CONFIRMATION,
    "duplicate_bank_charge": RecommendedAction.REQUEST_BANK_CONFIRMATION,
    "ledger_missing_second_entry": RecommendedAction.POST_ADJUSTING_ENTRY,
    "typo_or_transposition": RecommendedAction.POST_ADJUSTING_ENTRY,
    "partial_payment": RecommendedAction.CONTACT_COUNTERPARTY,
    "discount_or_adjustment": RecommendedAction.CONTACT_COUNTERPARTY,
    "fx_or_rounding": RecommendedAction.NO_ACTION,
    "bank_fee_deducted": RecommendedAction.POST_ADJUSTING_ENTRY,
    "rounding": RecommendedAction.NO_ACTION,
    "late_posting": RecommendedAction.NO_ACTION,
    "wrong_period_entry": RecommendedAction.POST_ADJUSTING_ENTRY,
    "multiple_possible_combinations": RecommendedAction.INVESTIGATE,
    "unknown": RecommendedAction.INVESTIGATE,
}

ACTION_DETAILS: dict[str, str] = {
    RecommendedAction.INVESTIGATE: (
        "Ask the preparer for the source document before changing any record."
    ),
    RecommendedAction.REQUEST_BANK_CONFIRMATION: (
        "Request the missing statement page or a written confirmation from the bank."
    ),
    RecommendedAction.POST_ADJUSTING_ENTRY: "Prepare an adjusting entry for the period-end review.",
    RecommendedAction.REVERSE_DUPLICATE: (
        "Reverse the later of the two ledger entries after confirmation."
    ),
    RecommendedAction.CONTACT_COUNTERPARTY: (
        "Confirm the agreed amount and payment schedule with the counterparty."
    ),
    RecommendedAction.WAIT_AND_RECHECK: "Recheck the next statement before booking anything.",
    RecommendedAction.NO_ACTION: "Leave the records unchanged and note the finding as explained.",
}

UNCERTAINTY_TEXTS: dict[str, list[str]] = {
    "known": ["The packet holds no bank correspondence or ledger note that confirms this cause."],
    "unknown": ["No amount, date or reference in the packet separates one cause from another."],
}

FAULT_TYPES = ("invented_amount", "invalid_enum", "decision_override", "malformed_json")
NO_FAULT = "valid"
INVENTED_AMOUNT = "999999.99"
OVERRIDE_SENTENCE = "These records do match and should be treated as matched."
INVALID_CAUSE = "reclassification_needed"
DEFAULT_CAUSE_INDEX = 0
MAX_SENTENCES_RECORDS = 2


def _record(packet: EvidencePacket, role: str) -> dict[str, Any] | None:
    """Return the packet's first record on one side."""
    return next((item for item in packet.records if item["role"] == role), None)


def _side_sentence(record: dict[str, Any]) -> tuple[str, list[CitedFact]]:
    """Describe one record using only its own packet values."""
    label = "Ledger" if record["role"] == "ledger" else "Bank"
    identifier = str(record["id"])
    cited = [
        CitedFact(field=f"{identifier}.amount", value=str(record["amount"])),
        CitedFact(field=f"{identifier}.date", value=str(record["date"])),
        CitedFact(field=f"{identifier}.id", value=identifier),
    ]
    return (
        f"{label} record {identifier} dated {record['date']} for {record['amount']} "
        f"{record['currency']}.",
        cited,
    )


def _difference_sentence(packet: EvidencePacket) -> tuple[str, list[CitedFact]]:
    """Quote the deterministic differences the engine measured."""
    parts: list[str] = []
    cited: list[CitedFact] = []
    amount = packet.facts.get("amount_difference")
    if isinstance(amount, str):
        parts.append(f"They differ by {amount}.")
        cited.append(CitedFact(field="amount_difference", value=amount))
    days = packet.facts.get("date_difference_days")
    if isinstance(days, int):
        parts.append(f"The dates are {days} day{'s' if days != 1 else ''} apart.")
        cited.append(CitedFact(field="date_difference_days", value=str(days)))
    return (" ".join(parts), cited)


def _combination_sentence(packet: EvidencePacket) -> tuple[str, list[CitedFact]]:
    """List the candidate sets an ambiguity refused to guess between."""
    sets = packet.facts.get("candidate_sets")
    if not isinstance(sets, list) or not sets:
        return ("", [])
    groups = [" or ".join(str(identifier) for identifier in group) for group in sets]
    cited = [
        CitedFact(field="candidate_sets", value=str(identifier))
        for group in sets
        for identifier in group
    ]
    return (f"Possible combinations: {', '.join(groups)}.", cited)


def build_output(packet: EvidencePacket, cause: str) -> Investigation:
    """Compose one answer for a cause using only values the packet already holds."""
    if cause not in packet.allowed_causes:
        raise ValidationError(f"{cause} is not an allowed cause for {packet.finding_type}")
    ledger = _record(packet, "ledger")
    bank = _record(packet, "bank")
    single = ledger or bank
    if single is None:
        raise ValidationError(f"Packet {packet.finding_id} has no records to explain")

    shown = [item for item in (ledger, bank) if item is not None]
    if len(shown) < 2:
        shown = list(packet.records[:MAX_SENTENCES_RECORDS])
    sentences: list[str] = []
    cited: list[CitedFact] = []
    for record in shown:
        sentence, facts = _side_sentence(record)
        sentences.append(sentence)
        cited.extend(facts)
    if ledger is not None and bank is not None:
        difference, facts = _difference_sentence(packet)
        if difference:
            sentences.append(difference)
            cited.extend(facts)
    if str(packet.finding_type) == "ambiguous_split":
        sentence, facts = _combination_sentence(packet)
        if sentence:
            sentences.append(sentence)
            cited.extend(facts)

    explanation = f"{CAUSE_PHRASES[cause]} {' '.join(sentences)}".strip()
    confidence = Confidence.LOW if cause == "unknown" else Confidence.MEDIUM
    return Investigation(
        summary=f"{single['id']}: {cause.replace('_', ' ')}"[:200],
        likely_cause=cause,
        explanation=explanation[:800],
        cited_facts=cited,
        recommended_action=CAUSE_ACTIONS[cause],
        action_detail=ACTION_DETAILS[CAUSE_ACTIONS[cause]],
        confidence=confidence,
        uncertainties=list(UNCERTAINTY_TEXTS["unknown" if cause == "unknown" else "known"]),
    )


def inject_fault(investigation: Investigation, fault: str) -> str:
    """Render one provider answer with the requested deterministic fault applied."""
    payload: dict[str, Any] = investigation.model_dump(mode="json")
    if fault == NO_FAULT:
        return _dump(payload)
    if fault == "invented_amount":
        payload["explanation"] = f"{payload['explanation']} It also cleared {INVENTED_AMOUNT}."
        return _dump(payload)
    if fault == "invalid_enum":
        payload["likely_cause"] = INVALID_CAUSE
        return _dump(payload)
    if fault == "decision_override":
        payload["explanation"] = OVERRIDE_SENTENCE
        return _dump(payload)
    if fault == "malformed_json":
        text = _dump(payload)
        return text[: len(text) // 2]
    raise ValidationError(f"unknown fault type: {fault}")


def answer(packet: EvidencePacket, cause: str) -> str:
    """Render a complete answer for one packet and cause."""
    return _dump(build_output(packet, cause).model_dump(mode="json"))


def _dump(payload: dict[str, Any]) -> str:
    """Serialize a provider payload canonically."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class MockProvider:
    """Rule-based offline investigator used as the default provider."""

    name = "mock"
    model_name = "mock"

    def complete(self, packet: EvidencePacket, error_codes: tuple[str, ...] = ()) -> str:
        """Answer with the first allowed cause for the finding type."""
        return answer(packet, packet.allowed_causes[DEFAULT_CAUSE_INDEX])


class FaultyMockProvider:
    """Injects every documented fault type so the verifier's catch rate is measurable."""

    name = "faulty_mock"
    model_name = "faulty_mock"

    def __init__(self, fault: str | None = None, rate: float = 1.0) -> None:
        """Force one fault type, or fault a `rate` share of packets chosen by packet hash."""
        if not 0.0 <= rate <= 1.0:
            raise ValidationError("fault rate must be between 0 and 1")
        if fault is not None and fault not in FAULT_TYPES:
            raise ValidationError(f"unknown fault type: {fault}")
        self.fault = fault
        self.rate = rate

    def complete(self, packet: EvidencePacket, error_codes: tuple[str, ...] = ()) -> str:
        """Fault the first answer; a retry always answers correctly."""
        cause = packet.allowed_causes[DEFAULT_CAUSE_INDEX]
        if error_codes:
            return answer(packet, cause)
        fault = self.fault if self.fault is not None else self._select(packet)
        return inject_fault(build_output(packet, cause), fault)

    def _select(self, packet: EvidencePacket) -> str:
        """Pick a fault from the packet hash so the choice is call-order independent."""
        digest = int(packet_hash(packet), 16)
        if digest % 1000 >= round(self.rate * 1000):
            return NO_FAULT
        return FAULT_TYPES[digest % len(FAULT_TYPES)]
