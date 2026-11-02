"""Tests for the test-only `faulty_mock` provider used to measure the verifier."""

from __future__ import annotations

import json

import pytest

from recon.errors import LLMError, ValidationError
from recon.evidence.packet import ALLOWED_CAUSES, packet_hash
from recon.llm.mock import (
    INVALID_CAUSE,
    INVENTED_AMOUNT,
    NO_FAULT,
    OVERRIDE_SENTENCE,
    FaultyMockProvider,
    answer,
    build_output,
    inject_fault,
)
from recon.llm.schema import parse_investigation
from recon.models import EvidencePacket

ALL_FAULTS = ("invented_amount", "invalid_enum", "decision_override", "malformed_json")


@pytest.mark.parametrize("fault", ALL_FAULTS)
def test_each_documented_fault_is_produced_deterministically(
    fault: str, all_packets: list[EvidencePacket]
) -> None:
    """Every fault type appears in the provider text and repeats exactly."""
    provider = FaultyMockProvider(fault=fault)

    for packet in all_packets:
        raw = provider.complete(packet)

        assert raw == provider.complete(packet)
        assert raw == FaultyMockProvider(fault=fault).complete(packet)
        payload = {} if fault == "malformed_json" else json.loads(raw)
        if fault == "invented_amount":
            assert INVENTED_AMOUNT in payload["explanation"]
            assert INVENTED_AMOUNT not in packet.allowed_values["amounts"]
        if fault == "invalid_enum":
            assert payload["likely_cause"] == INVALID_CAUSE
            assert INVALID_CAUSE not in packet.allowed_causes
        if fault == "decision_override":
            assert OVERRIDE_SENTENCE in payload["explanation"]
        if fault == "malformed_json":
            assert raw and not raw.endswith("}")
            with pytest.raises(LLMError, match="not valid JSON"):
                parse_investigation(raw)


@pytest.mark.parametrize("finding_type", ALLOWED_CAUSES)
def test_valid_answers_still_parse_for_every_type(
    finding_type: str, packets: dict[str, EvidencePacket]
) -> None:
    """The `valid` fault setting is the unmodified provider answer."""
    packet = packets[finding_type]

    investigation = parse_investigation(inject_fault(build_output(packet, "unknown"), NO_FAULT))

    assert investigation.likely_cause == "unknown"
    assert investigation.confidence.value == "low"


def test_rate_zero_faults_nothing_and_rate_one_faults_every_packet(
    all_packets: list[EvidencePacket],
) -> None:
    """The rate selects which packets are answered badly, and the choice is by hash."""
    clean = FaultyMockProvider(rate=0.0)
    dirty = FaultyMockProvider(rate=1.0)
    kinds: set[str | None] = set()

    for packet in all_packets:
        first_cause = packet.allowed_causes[0]
        assert parse_investigation(clean.complete(packet)).likely_cause == first_cause

        raw = dirty.complete(packet)
        assert raw != answer(packet, first_cause)
        assert raw == FaultyMockProvider(rate=1.0).complete(packet)
        kinds.add(_kind(raw))

    assert len(kinds) >= 2
    assert kinds <= set(ALL_FAULTS)


def test_a_partial_rate_is_reproducible(all_packets: list[EvidencePacket]) -> None:
    """A mid-range rate faults the same packets in every provider instance."""
    half = FaultyMockProvider(rate=0.5)

    faulty = {
        packet.finding_id
        for packet in all_packets
        if half.complete(packet) != answer(packet, packet.allowed_causes[0])
    }

    assert faulty == {
        packet.finding_id for packet in all_packets if int(packet_hash(packet), 16) % 1000 < 500
    }


def test_a_retry_after_verifier_codes_answers_correctly(all_packets: list[EvidencePacket]) -> None:
    """The retry path is what lets the evaluation measure pass-after-retry."""
    provider = FaultyMockProvider(fault="invented_amount")

    for packet in all_packets:
        raw = provider.complete(packet, ("unsupported_figure",))

        assert raw == answer(packet, packet.allowed_causes[0])
        assert parse_investigation(raw).likely_cause in packet.allowed_causes


def test_unknown_fault_type_and_rate_are_rejected(packets: dict[str, EvidencePacket]) -> None:
    """Misconfiguration fails loudly instead of silently answering clean."""
    with pytest.raises(ValidationError, match="unknown fault type"):
        FaultyMockProvider(fault="made_up")
    with pytest.raises(ValidationError, match="between 0 and 1"):
        FaultyMockProvider(rate=1.5)


def _kind(raw: str) -> str | None:
    """Identify which fault a provider answer carries, the way the verifier will."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return "malformed_json"
    text = str(payload.get("explanation", ""))
    if INVENTED_AMOUNT in text:
        return "invented_amount"
    if OVERRIDE_SENTENCE in text:
        return "decision_override"
    if payload.get("likely_cause") == INVALID_CAUSE:
        return "invalid_enum"
    return None
