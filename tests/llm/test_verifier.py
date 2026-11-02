"""Tests for the six verifier checks, the single retry and the deterministic fallback."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from recon.errors import LLMError
from recon.evidence.packet import EvidencePacket
from recon.llm.mock import FAULT_TYPES, FaultyMockProvider, MockProvider
from recon.llm.verifier import (
    BAD_ENUM,
    CONFIDENCE_INCONSISTENT,
    DECISION_OVERRIDE,
    FAILURE_CODES,
    SCHEMA_INVALID,
    UNSUPPORTED_CITED_FACT,
    UNSUPPORTED_FIGURE,
    VERDICT_ERROR,
    Attempt,
    attempt_records,
    explain_verified,
    fallback_explanation,
    verify,
    write_verifier_log,
)
from recon.models import ExplanationSource

FAULT_TO_CODE = {
    "malformed_json": SCHEMA_INVALID,
    "invalid_enum": BAD_ENUM,
    "invented_amount": UNSUPPORTED_FIGURE,
    "decision_override": DECISION_OVERRIDE,
}

OVERRIDE_TEXTS = (
    "These records do match and should be treated as matched.",
    "The ledger and the bank did not match on the reference.",
    "This is not a duplicate of the earlier payment.",
    "The finding should be reclassified as a match.",
    "There is no discrepancy between the two sides.",
)


class _RecordingProvider:
    """A stub provider that remembers the codes it was asked to fix."""

    name = "stub"
    model_name = "stub-model"

    def __init__(self, raws: list[str]) -> None:
        """Serve one canned answer per call and record every request."""
        self.raws = raws
        self.requests: list[tuple[str, ...]] = []

    def complete(self, packet: EvidencePacket, error_codes: tuple[str, ...] = ()) -> str:
        """Return the next canned answer."""
        self.requests.append(tuple(error_codes))
        return self.raws[len(self.requests) - 1]


def _payload(packet: EvidencePacket) -> dict[str, Any]:
    """The valid mock answer for one packet as a mutable payload."""
    result: dict[str, Any] = json.loads(MockProvider().complete(packet))
    return result


def _dump(payload: dict[str, Any]) -> str:
    """Serialize a payload the way a provider would."""
    return json.dumps(payload, sort_keys=True)


def test_valid_mock_output_passes_every_check_for_every_type(
    all_packets: list[EvidencePacket],
) -> None:
    """The offline provider is verifier-clean by construction, on all eight types."""
    for packet in all_packets:
        investigation, codes = verify(packet, MockProvider().complete(packet))

        assert codes == ()
        assert investigation is not None


def test_a_truncated_answer_is_schema_invalid(all_packets: list[EvidencePacket]) -> None:
    """Unparseable JSON fails check 1 alone and yields no answer object."""
    packet = all_packets[0]
    investigation, codes = verify(packet, _dump(_payload(packet))[:40])

    assert investigation is None
    assert codes == (SCHEMA_INVALID,)


def test_an_answer_that_is_not_an_object_is_schema_invalid(
    packets: dict[str, EvidencePacket],
) -> None:
    """A JSON array is well-formed but is not the documented answer shape."""
    _, codes = verify(packets["fee_difference"], "[]")

    assert codes == (SCHEMA_INVALID,)


def test_an_unknown_cause_is_a_bad_enum(packets: dict[str, EvidencePacket]) -> None:
    """`likely_cause` must be one of this packet's allowed causes."""
    packet = packets["amount_mismatch"]
    payload = _payload(packet)
    payload["likely_cause"] = "reclassification_needed"

    _, codes = verify(packet, _dump(payload))

    assert codes == (BAD_ENUM,)


def test_an_unknown_action_string_is_caught_by_the_parser(
    packets: dict[str, EvidencePacket],
) -> None:
    """The action enum lives in the schema, so a bad action never reaches check 2."""
    packet = packets["fee_difference"]
    payload = _payload(packet)
    payload["recommended_action"] = "reclassify_the_finding"

    investigation, codes = verify(packet, _dump(payload))

    assert investigation is None
    assert codes == (SCHEMA_INVALID,)


def test_a_cited_fact_the_packet_does_not_carry_is_rejected(
    packets: dict[str, EvidencePacket],
) -> None:
    """Check 3 compares cited values against `allowed_values`."""
    packet = packets["date_mismatch"]
    payload = _payload(packet)
    payload["cited_facts"] = [{"field": "L-000001.amount", "value": "424242.42"}]

    _, codes = verify(packet, _dump(payload))

    assert codes == (UNSUPPORTED_CITED_FACT,)


def test_a_cited_fact_in_another_numeric_form_is_still_allowed(
    packets: dict[str, EvidencePacket],
) -> None:
    """More decimals are the same money when compared as `Decimal`, so check 3 accepts it."""
    packet = packets["date_mismatch"]
    amount = Decimal(packet.allowed_values["amounts"][0])
    payload = _payload(packet)
    payload["cited_facts"] = [{"field": "amount", "value": f"{amount:.3f}"}]

    _, codes = verify(packet, _dump(payload))

    assert codes == ()


def test_an_amount_in_the_prose_is_an_unsupported_figure(
    packets: dict[str, EvidencePacket],
) -> None:
    """Check 4 regex-scans the prose, not only the cited facts."""
    packet = packets["fee_difference"]
    payload = _payload(packet)
    payload["explanation"] = f"{payload['explanation']} It also cleared 999999.99."

    _, codes = verify(packet, _dump(payload))

    assert codes == (UNSUPPORTED_FIGURE,)


def test_a_grouped_amount_in_the_prose_is_an_unsupported_figure(
    packets: dict[str, EvidencePacket],
) -> None:
    """Packet money is ungrouped, so a thousands separator is not a packet value."""
    packet = packets["amount_mismatch"]
    grouped = f"{Decimal(packet.allowed_values['amounts'][0]) + Decimal(1000):,.2f}"
    assert "," in grouped
    payload = _payload(packet)
    payload["explanation"] = f"{payload['explanation']} The gap is {grouped}."

    _, codes = verify(packet, _dump(payload))

    assert codes == (UNSUPPORTED_FIGURE,)


@pytest.mark.parametrize("text", OVERRIDE_TEXTS)
def test_decision_arguing_language_is_rejected(
    text: str, packets: dict[str, EvidencePacket]
) -> None:
    """Check 5 rejects sentences about the match decision in any prose field."""
    packet = packets["duplicate_in_ledger"]
    payload = _payload(packet)
    payload["explanation"] = text

    _, codes = verify(packet, _dump(payload))

    assert codes == (DECISION_OVERRIDE,)


def test_the_neutral_evidence_wording_is_not_an_override(
    packets: dict[str, EvidencePacket],
) -> None:
    """The guard must not fire on the wording the mock and the fallback produce."""
    packet = packets["duplicate_in_ledger"]
    fallback = fallback_explanation(packet).model_dump(mode="json", exclude={"explanation_source"})

    assert verify(packet, MockProvider().complete(packet))[1] == ()
    assert DECISION_OVERRIDE not in verify(packet, _dump(fallback))[1]


def test_unknown_cause_requires_low_confidence(packets: dict[str, EvidencePacket]) -> None:
    """Check 6: a cause of `unknown` may not carry medium or high confidence."""
    packet = packets["missing_in_bank"]
    payload = _payload(packet)
    payload["likely_cause"] = "unknown"
    payload["confidence"] = "high"

    _, codes = verify(packet, _dump(payload))

    assert codes == (CONFIDENCE_INCONSISTENT,)


def test_multiple_failures_are_reported_in_documented_order(
    packets: dict[str, EvidencePacket],
) -> None:
    """Codes come out in check order so the retry prompt and the log are stable."""
    packet = packets["missing_in_ledger"]
    payload = _payload(packet)
    payload["likely_cause"] = "not_a_cause"
    payload["explanation"] = "It cleared 999999.99 and these records do match."

    _, codes = verify(packet, _dump(payload))

    assert codes == (BAD_ENUM, UNSUPPORTED_FIGURE, DECISION_OVERRIDE)


def test_the_verifier_catches_every_injected_fault_on_every_type(
    all_packets: list[EvidencePacket],
) -> None:
    """100% catch rate: each fault type on each finding type is rejected."""
    caught = 0
    for fault in FAULT_TYPES:
        provider = FaultyMockProvider(fault=fault)
        for packet in all_packets:
            _, codes = verify(packet, provider.complete(packet))

            assert codes, f"{fault} on {packet.finding_type} passed the verifier"
            assert set(codes) <= set(FAILURE_CODES)
            caught += 1

    assert caught == len(FAULT_TYPES) * len(all_packets)


def test_injected_faults_map_to_their_documented_codes(
    all_packets: list[EvidencePacket],
) -> None:
    """Each injected fault trips exactly the check that describes it."""
    for fault, code in FAULT_TO_CODE.items():
        provider = FaultyMockProvider(fault=fault)
        for packet in all_packets:
            _, codes = verify(packet, provider.complete(packet))

            assert codes == (code,), f"{fault} produced {codes}"


def test_the_hash_selected_faults_are_all_or_nothing(
    all_packets: list[EvidencePacket],
) -> None:
    """At rate 1.0 every packet is rejected; at rate 0.0 the answer is clean."""
    full = FaultyMockProvider(rate=1.0)
    none = FaultyMockProvider(rate=0.0)

    assert all(verify(packet, full.complete(packet))[1] for packet in all_packets)
    assert all(verify(packet, none.complete(packet))[1] == () for packet in all_packets)


def test_a_rejected_answer_is_retried_once_with_its_codes(
    packets: dict[str, EvidencePacket],
) -> None:
    """The retry carries the verifier's codes and an accepted answer wins."""
    packet = packets["amount_mismatch"]
    faulty = FaultyMockProvider(fault="invented_amount").complete(packet)
    provider = _RecordingProvider([faulty, MockProvider().complete(packet)])

    result = explain_verified(packet, provider)

    assert provider.requests == [(), (UNSUPPORTED_FIGURE,)]
    assert result.source is ExplanationSource.AI_VERIFIED
    assert [attempt.verdict for attempt in result.attempts] == ["rejected", "accepted"]
    assert result.explanation.explanation_source is ExplanationSource.AI_VERIFIED


def test_a_second_failure_uses_the_deterministic_fallback(
    packets: dict[str, EvidencePacket],
) -> None:
    """Two rejected answers still produce a marked explanation, never a gap."""
    packet = packets["fee_difference"]
    faulty = FaultyMockProvider(fault="invalid_enum").complete(packet)
    provider = _RecordingProvider([faulty, faulty])

    result = explain_verified(packet, provider)

    assert len(result.attempts) == 2
    assert provider.requests == [(), (BAD_ENUM,)]
    assert result.source is ExplanationSource.DETERMINISTIC_FALLBACK
    assert result.explanation.explanation_source is ExplanationSource.DETERMINISTIC_FALLBACK


def test_a_provider_that_never_answers_still_yields_an_explanation(
    packets: dict[str, EvidencePacket],
) -> None:
    """An empty answer is a rejection, and the run keeps going."""
    packet = packets["ambiguous_split"]
    provider = _RecordingProvider(["", ""])

    result = explain_verified(packet, provider)

    assert [attempt.failure_codes for attempt in result.attempts] == [
        (SCHEMA_INVALID,),
        (SCHEMA_INVALID,),
    ]
    assert result.source is ExplanationSource.DETERMINISTIC_FALLBACK


def test_a_provider_exception_stops_the_retry_and_flags_the_attempt(
    packets: dict[str, EvidencePacket],
) -> None:
    """A transport failure is logged as its own verdict, not retried or left raw."""
    packet = packets["fee_difference"]

    class _Boom(_RecordingProvider):
        def complete(self, packet: EvidencePacket, error_codes: tuple[str, ...] = ()) -> str:
            """Raise the documented provider error."""
            raise LLMError("provider request failed: ConnectTimeout")

    result = explain_verified(packet, _Boom([]))

    assert [attempt.verdict for attempt in result.attempts] == [VERDICT_ERROR]
    assert result.attempts[0].raw == "provider request failed: ConnectTimeout"
    assert result.attempts[0].failure_codes == ()
    assert result.source is ExplanationSource.DETERMINISTIC_FALLBACK


def test_the_fallback_passes_the_verifier_itself(
    all_packets: list[EvidencePacket],
) -> None:
    """A fallback is reportable output, so it must satisfy all six checks."""
    for packet in all_packets:
        explanation = fallback_explanation(packet)
        payload = explanation.model_dump(mode="json", exclude={"explanation_source"})

        assert verify(packet, _dump(payload))[1] == ()


def test_the_fallback_is_identical_across_calls(
    all_packets: list[EvidencePacket],
) -> None:
    """No clock, no randomness: the same packet always falls back the same way."""
    for packet in all_packets:
        assert fallback_explanation(packet).model_dump_json() == (
            fallback_explanation(packet).model_dump_json()
        )


def test_the_fallback_names_the_records_it_holds(
    packets: dict[str, EvidencePacket],
) -> None:
    """The fallback describes the evidence instead of leaving the finding blank."""
    packet = packets["duplicate_in_bank"]
    explanation = fallback_explanation(packet)
    sides = [
        str(record["id"])
        for role in ("ledger", "bank")
        for record in packet.records
        if record["role"] == role
    ]

    assert explanation.likely_cause == "unknown"
    assert str(explanation.confidence) == "low"
    assert explanation.cited_facts
    assert explanation.explanation
    for identifier in sides[:2]:
        assert identifier in explanation.explanation


def test_the_log_records_every_attempt_with_its_raw_answer(
    packets: dict[str, EvidencePacket], tmp_path: Path
) -> None:
    """`verifier_log.jsonl` holds one line per attempt with codes and raw output."""
    packet = packets["missing_in_bank"]
    faulty = FaultyMockProvider(fault="malformed_json").complete(packet)
    provider = _RecordingProvider([faulty, MockProvider().complete(packet)])
    result = explain_verified(packet, provider)

    records = attempt_records(packet, provider, result.attempts)
    write_verifier_log(tmp_path / "run" / "verifier_log.jsonl", records)
    lines = (tmp_path / "run" / "verifier_log.jsonl").read_text(encoding="utf-8").splitlines()

    assert [json.loads(line)["verdict"] for line in lines] == ["rejected", "accepted"]
    assert [json.loads(line)["attempt"] for line in lines] == [0, 1]
    assert json.loads(lines[1])["request_codes"] == [SCHEMA_INVALID]
    assert json.loads(lines[0])["raw"] == faulty
    assert all(json.loads(line)["provider"] == "stub" for line in lines)
    assert all(json.loads(line)["finding_id"] == packet.finding_id for line in lines)


def test_the_log_is_canonical_and_appends(
    tmp_path: Path, packets: dict[str, EvidencePacket]
) -> None:
    """Equal attempts serialize byte-identically and a second run appends."""
    packet = packets["missing_in_ledger"]
    provider = _RecordingProvider([MockProvider().complete(packet)])
    records = attempt_records(packet, provider, explain_verified(packet, provider).attempts)
    path = tmp_path / "verifier_log.jsonl"
    write_verifier_log(path, records)
    first = path.read_text(encoding="utf-8")
    write_verifier_log(path, records)

    assert json.dumps(records[0], sort_keys=True) + "\n" == first
    assert path.read_text(encoding="utf-8") == first + first


def test_an_attempt_exposes_its_verdict_for_counting() -> None:
    """The run summary counts rejections through this property."""
    rejected = Attempt(0, "{}", (BAD_ENUM,), (), "rejected")
    accepted = Attempt(0, "{}", (), (), "accepted")

    assert rejected.failed is True
    assert accepted.failed is False
