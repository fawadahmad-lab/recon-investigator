"""Tests for multiplicity-aware duplicate detection."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from recon.evaluation.runner import run_evaluation
from recon.matching.duplicates import detect_duplicates
from recon.models import Source, Transaction


def _transaction(
    source: Source, number: int, reference: str, transaction_date: date
) -> Transaction:
    """Create a concise same-amount transaction fixture."""
    prefix = "L" if source is Source.LEDGER else "B"
    return Transaction(
        id=f"{prefix}-{number:06d}",
        source=source,
        row_number=number,
        date=transaction_date,
        amount_minor=10000,
        currency="USD",
        reference_norm=reference,
    )


def test_legitimate_repeats_matched_on_both_sides_are_not_duplicates() -> None:
    """Repeated payments that have both-side matches never enter duplicate findings."""
    day = date(2026, 1, 5)
    ledger = [_transaction(Source.LEDGER, number, "REPEAT", day) for number in (1, 2)]
    bank = [_transaction(Source.BANK, number, "REPEAT", day) for number in (1, 2)]

    result = detect_duplicates([], [], ledger, bank, window_days=3)

    assert result.findings == []


def test_doubled_ledger_entry_links_to_matched_ledger_primary() -> None:
    """An unmatched ledger copy is classified and linked to its matched ledger primary."""
    day = date(2026, 1, 5)
    primary = _transaction(Source.LEDGER, 1, "DUP", day)
    duplicate = _transaction(Source.LEDGER, 2, "DUP", day + timedelta(days=1))

    result = detect_duplicates([duplicate], [], [primary], [], window_days=3)

    assert [(item.type, item.duplicate.id, item.primary.id) for item in result.findings] == [
        ("duplicate_in_ledger", "L-000002", "L-000001")
    ]
    assert result.unmatched_ledger == []


def test_doubled_bank_entry_links_to_matched_bank_primary() -> None:
    """An unmatched bank copy is classified and linked to its matched bank primary."""
    day = date(2026, 1, 5)
    primary = _transaction(Source.BANK, 1, "DUP", day)
    duplicate = _transaction(Source.BANK, 2, "DUP", day + timedelta(days=1))

    result = detect_duplicates([], [duplicate], [], [primary], window_days=3)

    assert [(item.type, item.duplicate.id, item.primary.id) for item in result.findings] == [
        ("duplicate_in_bank", "B-000002", "B-000001")
    ]
    assert result.unmatched_bank == []


def test_multiple_unmatched_copies_are_all_linked_to_the_primary() -> None:
    """Multiplicity-aware detection does not discard additional duplicated copies."""
    day = date(2026, 1, 5)
    primary = _transaction(Source.LEDGER, 1, "DUP", day)
    copies = [_transaction(Source.LEDGER, number, "DUP", day) for number in (2, 3)]

    result = detect_duplicates(copies, [], [primary], [], window_days=3)

    assert [item.duplicate.id for item in result.findings] == ["L-000002", "L-000003"]


def test_decoy_like_unmatched_record_without_matched_primary_is_not_flagged() -> None:
    """No duplicate is inferred unless an identical same-source matched primary exists."""
    day = date(2026, 1, 5)
    unmatched = _transaction(Source.BANK, 1, "DEC", day)

    result = detect_duplicates([], [unmatched], [], [], window_days=3)

    assert result.findings == []
    assert result.unmatched_bank == [unmatched]


def test_hard_profile_decoys_do_not_produce_duplicate_false_positives(tmp_path: Path) -> None:
    """Matched repeated-payment decoys remain absent from hard-profile duplicate false positives."""
    report_path = run_evaluation("hard", 42, tmp_path / "reports", tmp_path / "data")
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["per_type"]["duplicate_in_ledger"]["fp"] == 0
    assert report["per_type"]["duplicate_in_bank"]["fp"] == 0
