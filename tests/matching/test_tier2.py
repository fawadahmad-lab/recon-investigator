"""Tests for deterministic fuzzy matching and discrepancy classification."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from recon.config import get_settings
from recon.matching.classify import classify_amount_differences, classify_date_mismatches
from recon.matching.fuzzy import match_fuzzy
from recon.models import Source, Transaction


def _transaction(
    source: Source,
    number: int,
    reference: str,
    amount_minor: int,
    transaction_date: date,
    description: str = "acme supplies",
) -> Transaction:
    """Create a deterministic Tier 2 candidate fixture."""
    prefix = "L" if source is Source.LEDGER else "B"
    return Transaction(
        id=f"{prefix}-{number:06d}",
        source=source,
        row_number=number,
        date=transaction_date,
        amount_minor=amount_minor,
        currency="USD",
        reference_norm=reference,
        description_norm=description,
    )


def test_fuzzy_match_accepts_noisy_reference_with_exact_amount() -> None:
    """Tier 2 matches a high-score reference typo within the fuzzy date window."""
    day = date(2026, 1, 5)
    ledger = _transaction(Source.LEDGER, 1, "INVOICE1234", 10000, day)
    bank = _transaction(Source.BANK, 1, "INVOICE123X", 10000, day + timedelta(days=2))

    result = match_fuzzy([ledger], [bank], window_days=10, accept_score=0.75)

    assert len(result.matches) == 1
    assert result.matches[0].score >= 0.75
    assert result.unmatched_ledger == []


def test_fee_and_amount_classification_use_integer_minor_units() -> None:
    """A smaller bank amount within the fee limit is distinct from an amount mismatch."""
    day = date(2026, 1, 5)
    ledger = [
        _transaction(Source.LEDGER, 1, "FEE1", 10000, day),
        _transaction(Source.LEDGER, 2, "AMT1", 10000, day),
    ]
    bank = [
        _transaction(Source.BANK, 1, "FEE1", 9875, day),
        _transaction(Source.BANK, 2, "AMT1", 7000, day),
    ]

    result = classify_amount_differences(ledger, bank, get_settings())

    assert [(pair.type, pair.amount_difference_minor) for pair in result.pairs] == [
        ("fee_difference", 125),
        ("amount_mismatch", 3000),
    ]


def test_amount_classification_requires_a_unique_best_candidate() -> None:
    """Near-tied strong-reference candidates remain unclassified rather than guessed."""
    day = date(2026, 1, 5)
    ledger = [_transaction(Source.LEDGER, 1, "INVOICE0001", 10000, day)]
    bank = [
        _transaction(Source.BANK, 1, "INVOICE0001", 9900, day),
        _transaction(Source.BANK, 2, "INVOICE0002", 9900, day),
    ]

    result = classify_amount_differences(ledger, bank, replace(get_settings(), pair_margin=0.05))

    assert result.pairs == []
    assert result.unmatched_ledger == ledger


def test_date_mismatch_uses_configured_window_boundaries() -> None:
    """Equal reference and amount outside fuzzy range produce a date mismatch."""
    day = date(2026, 1, 5)
    ledger = _transaction(Source.LEDGER, 1, "DATE1", 10000, day)
    bank = _transaction(Source.BANK, 1, "DATE1", 10000, day + timedelta(days=15))

    result = classify_date_mismatches([ledger], [bank], get_settings())

    assert [(pair.type, pair.date_difference_days) for pair in result.pairs] == [
        ("date_mismatch", 15)
    ]
