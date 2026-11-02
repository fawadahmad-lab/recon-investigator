"""Stable blocking keys and date comparisons for deterministic matching."""

from __future__ import annotations

from datetime import date

from recon.models import Transaction

ExactBlockKey = tuple[str, int, str]


def exact_block_key(transaction: Transaction) -> ExactBlockKey | None:
    """Return the Tier 1 block key or None when a reference is unavailable."""
    reference = transaction.reference_norm.strip()
    if not reference:
        return None
    return (transaction.currency.upper(), transaction.amount_minor, reference)


def date_difference_days(first: date, second: date) -> int:
    """Return the absolute whole-day distance between two transaction dates."""
    return abs((first - second).days)
