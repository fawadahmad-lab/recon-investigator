"""Tests for domain models and Decimal money helpers."""

from datetime import date
from decimal import Decimal

import pytest

from recon.models import (
    Confidence,
    EvidencePacket,
    Explanation,
    ExplanationSource,
    Finding,
    FindingStatus,
    FindingType,
    RecommendedAction,
    Rule,
    Severity,
    Source,
    Transaction,
    format_amount,
    from_minor,
    to_minor,
)


def test_transaction_validates_and_serializes_to_json() -> None:
    """Transactions serialize dates and enum values as JSON-compatible values."""
    transaction = Transaction(
        id="L-000001",
        source=Source.LEDGER,
        row_number=1,
        date=date(2026, 3, 4),
        amount_minor=12345,
        currency="USD",
        reference_raw="INV-42",
        reference_norm="42",
        description_raw="Acme Supplies",
        description_norm="acme supplies",
    )

    payload = transaction.model_dump(mode="json")

    assert payload["date"] == "2026-03-04"
    assert payload["source"] == "ledger"
    assert Transaction.model_validate_json(transaction.model_dump_json()) == transaction


def test_finding_packet_and_explanation_validate_and_serialize() -> None:
    """Finding-related models retain the deterministic trust boundary fields."""
    explanation = Explanation(
        summary="A bank fee may explain the difference.",
        likely_cause="bank_fee_deducted",
        explanation="The packet records a 25.00 difference.",
        recommended_action=RecommendedAction.REQUEST_BANK_CONFIRMATION,
        action_detail="Request confirmation of the fee.",
        confidence=Confidence.MEDIUM,
        explanation_source=ExplanationSource.AI_VERIFIED,
    )
    finding = Finding(
        id="F-0001",
        type=FindingType.FEE_DIFFERENCE,
        status=FindingStatus.DISCREPANCY,
        ledger_ids=["L-000001"],
        bank_ids=["B-000001"],
        rule_id="R4-AMT",
        rule_version="1",
        severity=Severity.LOW,
        explanation=explanation,
    )
    packet = EvidencePacket(
        finding_id=finding.id,
        finding_type=finding.type,
        rule=Rule(id=finding.rule_id, version="1", description="Amount comparison."),
        allowed_causes=["bank_fee_deducted", "unknown"],
        allowed_values={"amounts": ["25.00"], "dates": [], "ids": [finding.id]},
    )

    assert finding.model_dump(mode="json")["explanation"]["explanation_source"] == "ai_verified"
    assert EvidencePacket.model_validate_json(packet.model_dump_json()) == packet


@pytest.mark.parametrize(
    ("value", "decimal_places", "expected_minor"),
    [
        ("123.45", 2, 12345),
        ("-123.45", 2, -12345),
        (Decimal("1.2345"), 3, 1235),
        (Decimal("-1.2345"), 3, -1235),
    ],
)
def test_money_round_trips_with_decimal_rounding(
    value: Decimal | str,
    decimal_places: int,
    expected_minor: int,
) -> None:
    """Money conversion uses Decimal rounding for positive and negative values."""
    amount_minor = to_minor(value, decimal_places)

    assert amount_minor == expected_minor
    assert to_minor(from_minor(amount_minor, decimal_places), decimal_places) == amount_minor


def test_money_helpers_reject_floats_and_format_minor_units() -> None:
    """Float inputs cannot enter a money conversion path."""
    with pytest.raises(TypeError, match="floats"):
        to_minor(12.34)  # type: ignore[arg-type]

    assert format_amount(-123456) == "-1,234.56"
