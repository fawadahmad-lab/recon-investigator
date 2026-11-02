"""Multiplicity-aware detection of unmatched duplicates of matched primaries."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from recon.matching.keys import ExactBlockKey, date_difference_days, exact_block_key
from recon.models import Source, Transaction


@dataclass(frozen=True)
class DuplicateFinding:
    """A deterministic duplicate linked to the same-source matched primary."""

    type: str
    duplicate: Transaction
    primary: Transaction


@dataclass(frozen=True)
class DuplicateResult:
    """Detected duplicates and records left available for later matching rules."""

    findings: list[DuplicateFinding]
    unmatched_ledger: list[Transaction]
    unmatched_bank: list[Transaction]


def _blocks(transactions: list[Transaction]) -> dict[ExactBlockKey, list[Transaction]]:
    """Index matched source records by the duplicate identity key."""
    blocks: dict[ExactBlockKey, list[Transaction]] = defaultdict(list)
    for transaction in transactions:
        key = exact_block_key(transaction)
        if key is not None:
            blocks[key].append(transaction)
    return blocks


def _find_duplicates(
    unmatched: list[Transaction], matched: list[Transaction], source: Source, window_days: int
) -> tuple[list[DuplicateFinding], set[str]]:
    """Link unmatched records to nearest matched same-source primaries within the window."""
    blocks = _blocks(matched)
    findings: list[DuplicateFinding] = []
    duplicate_ids: set[str] = set()
    finding_type = "duplicate_in_ledger" if source is Source.LEDGER else "duplicate_in_bank"
    for transaction in sorted(unmatched, key=lambda row: row.id):
        key = exact_block_key(transaction)
        if key is None:
            continue
        primaries = [
            primary
            for primary in blocks.get(key, [])
            if date_difference_days(transaction.date, primary.date) <= window_days
        ]
        if not primaries:
            continue
        primary = min(
            primaries, key=lambda row: (date_difference_days(transaction.date, row.date), row.id)
        )
        findings.append(DuplicateFinding(finding_type, transaction, primary))
        duplicate_ids.add(transaction.id)
    return findings, duplicate_ids


def detect_duplicates(
    unmatched_ledger: list[Transaction],
    unmatched_bank: list[Transaction],
    matched_ledger: list[Transaction],
    matched_bank: list[Transaction],
    window_days: int,
) -> DuplicateResult:
    """Detect unmatched same-source copies of records already matched by prior tiers."""
    if window_days < 0:
        raise ValueError("window_days must not be negative")
    ledger_findings, ledger_duplicate_ids = _find_duplicates(
        unmatched_ledger, matched_ledger, Source.LEDGER, window_days
    )
    bank_findings, bank_duplicate_ids = _find_duplicates(
        unmatched_bank, matched_bank, Source.BANK, window_days
    )
    return DuplicateResult(
        findings=[*ledger_findings, *bank_findings],
        unmatched_ledger=[row for row in unmatched_ledger if row.id not in ledger_duplicate_ids],
        unmatched_bank=[row for row in unmatched_bank if row.id not in bank_duplicate_ids],
    )
