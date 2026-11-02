"""Tests for deterministic Tier 1 exact matching."""

from __future__ import annotations

from datetime import date, timedelta
from time import perf_counter

from recon.matching.exact import match_exact
from recon.models import Source, Transaction


def _transaction(
    source: Source, number: int, reference: str, transaction_date: date, amount_minor: int = 1000
) -> Transaction:
    """Create a concise canonical transaction fixture."""
    prefix = "L" if source is Source.LEDGER else "B"
    return Transaction(
        id=f"{prefix}-{number:06d}",
        source=source,
        row_number=number,
        date=transaction_date,
        amount_minor=amount_minor,
        currency="USD",
        reference_norm=reference,
    )


def test_exact_matches_are_one_to_one() -> None:
    """No record can appear in more than one accepted exact match."""
    day = date(2026, 1, 5)
    ledger = [_transaction(Source.LEDGER, 1, "A", day), _transaction(Source.LEDGER, 2, "B", day)]
    bank = [_transaction(Source.BANK, 1, "A", day), _transaction(Source.BANK, 2, "B", day)]

    result = match_exact(ledger, bank, date_window_days=3)

    assert len(result.matches) == 2
    assert len({match.ledger.id for match in result.matches}) == 2
    assert len({match.bank.id for match in result.matches}) == 2
    assert result.unmatched_ledger == []
    assert result.unmatched_bank == []


def test_legitimate_repeated_payments_match_pairwise() -> None:
    """Repeated equal payments on both sides are matched, not collapsed or flagged."""
    day = date(2026, 1, 5)
    ledger = [_transaction(Source.LEDGER, number, "REPEAT", day) for number in (1, 2)]
    bank = [_transaction(Source.BANK, number, "REPEAT", day) for number in (1, 2)]

    result = match_exact(ledger, bank, date_window_days=3)

    assert [(match.ledger.id, match.bank.id) for match in result.matches] == [
        ("L-000001", "B-000001"),
        ("L-000002", "B-000002"),
    ]


def test_ties_use_date_then_ledger_then_bank_ids() -> None:
    """Equal-score candidates follow the documented stable deterministic sort order."""
    day = date(2026, 1, 5)
    ledger = [
        _transaction(Source.LEDGER, 1, "TIE", day),
        _transaction(Source.LEDGER, 2, "TIE", day),
    ]
    bank = [
        _transaction(Source.BANK, 2, "TIE", day - timedelta(days=1)),
        _transaction(Source.BANK, 1, "TIE", day + timedelta(days=1)),
    ]

    result = match_exact(ledger, bank, date_window_days=3)

    assert [(match.ledger.id, match.bank.id) for match in result.matches] == [
        ("L-000001", "B-000001"),
        ("L-000002", "B-000002"),
    ]


def test_blank_references_and_nonmatching_blocks_remain_unmatched() -> None:
    """Tier 1 requires nonempty equal reference, currency, and amount blocks."""
    day = date(2026, 1, 5)
    ledger = [_transaction(Source.LEDGER, 1, "", day), _transaction(Source.LEDGER, 2, "A", day)]
    bank = [_transaction(Source.BANK, 1, "", day), _transaction(Source.BANK, 2, "A", day, 1001)]

    result = match_exact(ledger, bank, date_window_days=3)

    assert result.matches == []
    assert len(result.unmatched_ledger) == 2
    assert len(result.unmatched_bank) == 2


def test_5000_row_blocked_matching_completes_within_target() -> None:
    """Amount-reference blocking keeps the documented 5,000-row case fast."""
    day = date(2026, 1, 5)
    ledger = [_transaction(Source.LEDGER, index, f"REF{index}", day) for index in range(1, 5001)]
    bank = [_transaction(Source.BANK, index, f"REF{index}", day) for index in range(1, 5001)]

    started = perf_counter()
    result = match_exact(ledger, bank, date_window_days=3)

    assert len(result.matches) == 5000
    assert perf_counter() - started < 30
