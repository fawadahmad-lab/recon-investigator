"""Tests for the investigator output schema and its parser."""

from __future__ import annotations

import json

import pytest

from recon.errors import LLMError
from recon.llm.schema import Investigation, output_schema, parse_investigation, to_explanation
from recon.models import Confidence, ExplanationSource, RecommendedAction

VALID = {
    "summary": "L-000042 and B-000310 differ by 25.00",
    "likely_cause": "typo_or_transposition",
    "explanation": "Ledger record L-000042 dated 2026-03-04 for 1250.00 USD.",
    "cited_facts": [{"field": "L-000042.amount", "value": "1250.00"}],
    "recommended_action": "post_adjusting_entry",
    "action_detail": "Prepare an adjusting entry for the period-end review.",
    "confidence": "medium",
    "uncertainties": ["The packet holds no confirmation."],
}


def test_a_valid_answer_parses_into_the_documented_shape() -> None:
    """The eight fields of Architecture section 10 parse with their enums."""
    investigation = parse_investigation(json.dumps(VALID))

    assert investigation.recommended_action is RecommendedAction.POST_ADJUSTING_ENTRY
    assert investigation.confidence is Confidence.MEDIUM
    assert investigation.cited_facts[0].value == "1250.00"
    assert set(VALID) == set(output_schema()["properties"])


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("{not json", "not valid JSON"),
        ("[]", "not a JSON object"),
        ('{"summary": 1}', "does not match the schema"),
        ("null", "not a JSON object"),
    ],
)
def test_a_malformed_answer_is_a_provider_error(raw: str, reason: str) -> None:
    """Nothing downstream ever sees a partially parsed response."""
    with pytest.raises(LLMError, match=reason):
        parse_investigation(raw)


@pytest.mark.parametrize(
    "field",
    [
        "matched",
        "type",
        "status",
        "finding_id",
        "severity",
        "ledger_ids",
        "bank_ids",
        "decision",
    ],
)
def test_a_field_that_could_change_the_decision_is_rejected(field: str) -> None:
    """Extra keys are refused, so a model cannot smuggle a match decision out."""
    payload = dict(VALID)
    payload[field] = True

    with pytest.raises(LLMError, match="does not match the schema"):
        parse_investigation(json.dumps(payload))


@pytest.mark.parametrize(
    ("field", "length"),
    [("summary", 201), ("explanation", 801), ("action_detail", 301)],
)
def test_the_length_limits_are_part_of_the_schema(field: str, length: int) -> None:
    """An over-long answer fails the schema check instead of being truncated."""
    payload = dict(VALID)
    payload[field] = "x" * length

    with pytest.raises(LLMError, match="does not match the schema"):
        parse_investigation(json.dumps(payload))


def test_enum_fields_only_accept_documented_values() -> None:
    """A made-up action or confidence level is a schema error, not a bad enum code."""
    for field, value in (("recommended_action", "refund_money"), ("confidence", "certain")):
        payload = dict(VALID)
        payload[field] = value
        with pytest.raises(LLMError, match="does not match the schema"):
            parse_investigation(json.dumps(payload))


def test_a_cited_fact_needs_both_a_field_and_a_value() -> None:
    """Half a citation cannot pass the verifier's value lookup."""
    payload = dict(VALID)
    payload["cited_facts"] = [{"field": "amount"}]

    with pytest.raises(LLMError, match="does not match the schema"):
        parse_investigation(json.dumps(payload))


def test_to_explanation_only_attaches_the_verification_outcome() -> None:
    """The stored explanation is the answer plus its source, with nothing else changed."""
    investigation = parse_investigation(json.dumps(VALID))

    explanation = to_explanation(investigation, ExplanationSource.AI_VERIFIED)

    assert explanation.model_dump(exclude={"explanation_source"}) == investigation.model_dump()
    assert explanation.explanation_source is ExplanationSource.AI_VERIFIED
    assert isinstance(investigation, Investigation)


def test_optional_collections_may_be_empty() -> None:
    """A terse but valid answer still parses, so the verifier judges substance separately."""
    payload = dict(VALID)
    payload["cited_facts"] = []
    payload["uncertainties"] = []

    assert parse_investigation(json.dumps(payload)).cited_facts == []
