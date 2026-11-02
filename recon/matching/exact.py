"""Tier 1 exact, blocked, deterministic one-to-one transaction matching."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from recon.matching.keys import ExactBlockKey, date_difference_days, exact_block_key
from recon.models import Transaction


@dataclass(frozen=True)
class ExactMatch:
    """One deterministic Tier 1 match and its date-distance evidence."""

    ledger: Transaction
    bank: Transaction
    date_difference_days: int


@dataclass(frozen=True)
class ExactMatchResult:
    """Tier 1 matches plus records that remain available for later rules."""

    matches: list[ExactMatch]
    unmatched_ledger: list[Transaction]
    unmatched_bank: list[Transaction]


def _bank_blocks(
    bank_transactions: Iterable[Transaction],
) -> dict[ExactBlockKey, list[Transaction]]:
    """Index bank records by the fields that must exactly agree in Tier 1."""
    blocks: dict[ExactBlockKey, list[Transaction]] = defaultdict(list)
    for transaction in bank_transactions:
        key = exact_block_key(transaction)
        if key is not None:
            blocks[key].append(transaction)
    return blocks


def _candidates(
    ledger_transactions: Iterable[Transaction],
    blocks: dict[ExactBlockKey, list[Transaction]],
    date_window_days: int,
) -> list[tuple[int, str, str, Transaction, Transaction]]:
    """Build eligible exact candidates, retaining only blocked date-window pairs."""
    candidates: list[tuple[int, str, str, Transaction, Transaction]] = []
    for ledger in ledger_transactions:
        key = exact_block_key(ledger)
        if key is None:
            continue
        for bank in blocks.get(key, []):
            difference = date_difference_days(ledger.date, bank.date)
            if difference <= date_window_days:
                candidates.append((difference, ledger.id, bank.id, ledger, bank))
    return candidates


def match_exact(
    ledger_transactions: list[Transaction],
    bank_transactions: list[Transaction],
    date_window_days: int,
) -> ExactMatchResult:
    """Match exact candidates greedily using the documented deterministic sort key."""
    if date_window_days < 0:
        raise ValueError("date_window_days must not be negative")
    candidates = _candidates(ledger_transactions, _bank_blocks(bank_transactions), date_window_days)
    matched_ledger: set[str] = set()
    matched_bank: set[str] = set()
    matches: list[ExactMatch] = []
    for difference, _, _, ledger, bank in sorted(candidates):
        if ledger.id in matched_ledger or bank.id in matched_bank:
            continue
        matched_ledger.add(ledger.id)
        matched_bank.add(bank.id)
        matches.append(ExactMatch(ledger=ledger, bank=bank, date_difference_days=difference))
    return ExactMatchResult(
        matches=matches,
        unmatched_ledger=[row for row in ledger_transactions if row.id not in matched_ledger],
        unmatched_bank=[row for row in bank_transactions if row.id not in matched_bank],
    )
