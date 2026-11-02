"""Tests for the deterministic offline `mock` provider."""

from __future__ import annotations

import json
import re

import pytest

from recon.errors import ValidationError
from recon.evidence.packet import ALLOWED_CAUSES
from recon.llm.mock import (
    ACTION_DETAILS,
    CAUSE_ACTIONS,
    CAUSE_PHRASES,
    MockProvider,
    answer,
    build_output,
)
from recon.llm.schema import output_schema, parse_investigation
from recon.models import Confidence, EvidencePacket, RecommendedAction

MONEY = re.compile(r"\d+\.\d{2}")
DATE_TEXT = re.compile(r"\d{4}-\d{2}-\d{2}")
ID_TEXT = re.compile(r"[LB]-\d{6}|F-\d{4}")


def test_cause_tables_cover_every_documented_cause() -> None:
    """Every allowed cause has a phrase and an action, and actions cover the enum."""
    causes = {cause for values in ALLOWED_CAUSES.values() for cause in values}
    assert causes == set(CAUSE_PHRASES) == set(CAUSE_ACTIONS)
    assert set(ACTION_DETAILS) == set(RecommendedAction)


@pytest.mark.parametrize("finding_type", ALLOWED_CAUSES)
def test_mock_yields_valid_output_for_every_allowed_cause(
    finding_type: str, packets: dict[str, EvidencePacket]
) -> None:
    """Each cause of each type produces a schema-valid answer citing only packet values."""
    packet = packets[finding_type]
    allowed = {value for values in packet.allowed_values.values() for value in values}

    for cause in packet.allowed_causes:
        investigation = parse_investigation(answer(packet, cause))

        assert investigation.likely_cause == cause
        assert cause in ALLOWED_CAUSES[finding_type]
        assert len(investigation.summary) <= 200
        assert len(investigation.explanation) <= 800
        assert len(investigation.action_detail) <= 300
        assert investigation.confidence is (
            Confidence.LOW if cause == "unknown" else Confidence.MEDIUM
        )
        assert investigation.uncertainties
        assert investigation.cited_facts
        for fact in investigation.cited_facts:
            assert fact.value in allowed
        for text in (
            investigation.summary,
            investigation.explanation,
            investigation.action_detail,
        ):
            for token in MONEY.findall(text):
                assert token in packet.allowed_values["amounts"]
            for token in DATE_TEXT.findall(text):
                assert token in packet.allowed_values["dates"]
            for token in ID_TEXT.findall(text):
                assert token in packet.allowed_values["ids"]


def test_mock_answers_are_identical_across_calls_and_instances(
    all_packets: list[EvidencePacket],
) -> None:
    """The mock has no clock, randomness or cache, so identical packets answer identically."""
    first = MockProvider()
    second = MockProvider()
    for packet in all_packets:
        cause = packet.allowed_causes[0]
        assert answer(packet, cause) == answer(packet, cause)
        assert first.complete(packet) == second.complete(packet)


def test_mock_default_cause_is_the_first_allowed_cause(packets: dict[str, EvidencePacket]) -> None:
    """The deterministic guess is the documented first cause of the finding type."""
    payload = json.loads(MockProvider().complete(packets["amount_mismatch"]))

    assert payload["likely_cause"] == ALLOWED_CAUSES["amount_mismatch"][0]
    assert payload["likely_cause"] == "typo_or_transposition"


def test_mock_output_carries_no_field_that_could_change_a_decision(
    packets: dict[str, EvidencePacket],
) -> None:
    """The answer shape is exactly the eight explanation fields and nothing else."""
    payload = json.loads(MockProvider().complete(packets["missing_in_ledger"]))

    assert set(payload) == set(output_schema()["properties"])
    assert {"type", "status", "matched", "severity", "finding_id"}.isdisjoint(payload)


def test_mock_names_the_records_it_explains(packets: dict[str, EvidencePacket]) -> None:
    """Explanations quote real packet identifiers, amounts and dates."""
    investigation = parse_investigation(answer(packets["date_mismatch"], "late_posting"))
    record_ids = {record["id"] for record in packets["date_mismatch"].records}

    assert record_ids <= set(ID_TEXT.findall(investigation.explanation))
    assert "day" in investigation.explanation


def test_build_output_refuses_a_cause_the_packet_does_not_allow(
    packets: dict[str, EvidencePacket],
) -> None:
    """An invented cause is rejected at construction, not only by the verifier."""
    with pytest.raises(ValidationError, match="not an allowed cause"):
        build_output(packets["fee_difference"], "typo_or_transposition")
