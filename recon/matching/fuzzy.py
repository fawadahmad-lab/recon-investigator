"""Tier 2 deterministic fuzzy matching over exact-amount candidate pairs."""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz.fuzz import token_set_ratio

from recon.matching.keys import date_difference_days
from recon.models import Transaction


@dataclass(frozen=True)
class FuzzyMatch:
    """An accepted fuzzy match with transparent scoring components."""

    ledger: Transaction
    bank: Transaction
    score: float
    reference_similarity: float
    description_similarity: float
    date_similarity: float


@dataclass(frozen=True)
class FuzzyMatchResult:
    """Accepted fuzzy matches and records available for subsequent rules."""

    matches: list[FuzzyMatch]
    unmatched_ledger: list[Transaction]
    unmatched_bank: list[Transaction]


def text_similarity(left: str, right: str) -> float:
    """Return token-set similarity in the inclusive range zero through one."""
    if not left or not right:
        return 0.0
    return token_set_ratio(left, right) / 100


def fuzzy_components(
    ledger: Transaction, bank: Transaction, window_days: int
) -> tuple[float, float, float]:
    """Calculate reference, description, and date components for a candidate pair."""
    days = date_difference_days(ledger.date, bank.date)
    return (
        text_similarity(ledger.reference_norm, bank.reference_norm),
        text_similarity(ledger.description_norm, bank.description_norm),
        1 - days / window_days,
    )


def fuzzy_score(
    ledger: Transaction, bank: Transaction, window_days: int
) -> tuple[float, float, float, float]:
    """Calculate the configured Tier 2 weighted score and its components."""
    reference, description, date = fuzzy_components(ledger, bank, window_days)
    return (0.5 * reference + 0.35 * description + 0.15 * date, reference, description, date)


def match_fuzzy(
    ledger_transactions: list[Transaction],
    bank_transactions: list[Transaction],
    window_days: int,
    accept_score: float,
) -> FuzzyMatchResult:
    """Greedily accept exact-amount fuzzy candidates in stable deterministic order."""
    if window_days <= 0:
        raise ValueError("window_days must be positive")
    candidates: list[
        tuple[float, int, str, str, Transaction, Transaction, tuple[float, float, float]]
    ] = []
    for ledger in ledger_transactions:
        for bank in bank_transactions:
            if ledger.currency != bank.currency or ledger.amount_minor != bank.amount_minor:
                continue
            days = date_difference_days(ledger.date, bank.date)
            if days > window_days:
                continue
            score, reference, description, date = fuzzy_score(ledger, bank, window_days)
            if score >= accept_score:
                candidates.append(
                    (-score, days, ledger.id, bank.id, ledger, bank, (reference, description, date))
                )
    matched_ledger: set[str] = set()
    matched_bank: set[str] = set()
    matches: list[FuzzyMatch] = []
    for negative_score, _, _, _, ledger, bank, components in sorted(candidates):
        if ledger.id in matched_ledger or bank.id in matched_bank:
            continue
        matched_ledger.add(ledger.id)
        matched_bank.add(bank.id)
        matches.append(FuzzyMatch(ledger, bank, -negative_score, *components))
    return FuzzyMatchResult(
        matches=matches,
        unmatched_ledger=[row for row in ledger_transactions if row.id not in matched_ledger],
        unmatched_bank=[row for row in bank_transactions if row.id not in matched_bank],
    )
