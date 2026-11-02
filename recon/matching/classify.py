"""Deterministic amount, fee, and date mismatch classification."""

from __future__ import annotations

from dataclasses import dataclass

from recon.config import Settings
from recon.matching.fuzzy import fuzzy_score
from recon.matching.keys import date_difference_days
from recon.models import Transaction


@dataclass(frozen=True)
class ClassifiedPair:
    """A deterministic discrepancy classification for one ledger-bank pair."""

    type: str
    ledger: Transaction
    bank: Transaction
    score: float | None
    amount_difference_minor: int | None = None
    date_difference_days: int | None = None


@dataclass(frozen=True)
class ClassificationResult:
    """Classified pairs and records not consumed by a classifier."""

    pairs: list[ClassifiedPair]
    unmatched_ledger: list[Transaction]
    unmatched_bank: list[Transaction]


def _same_sign(first: int, second: int) -> bool:
    """Return whether two nonzero signed minor-unit amounts have the same sign."""
    return (first > 0) == (second > 0)


def _clear_best(scores: list[float], margin: float) -> bool:
    """Return whether a ranked candidate list has a unique best score by margin."""
    return len(scores) == 1 or scores[0] - scores[1] >= margin


def classify_amount_differences(
    ledger_transactions: list[Transaction], bank_transactions: list[Transaction], settings: Settings
) -> ClassificationResult:
    """Classify unambiguous strong-reference amount pairs as fees or mismatches."""
    candidates: list[tuple[float, int, str, str, Transaction, Transaction]] = []
    for ledger in ledger_transactions:
        for bank in bank_transactions:
            if ledger.currency != bank.currency or not _same_sign(
                ledger.amount_minor, bank.amount_minor
            ):
                continue
            if ledger.amount_minor == bank.amount_minor:
                continue
            days = date_difference_days(ledger.date, bank.date)
            if days > settings.date_window_fuzzy_days:
                continue
            score, reference, _, _ = fuzzy_score(ledger, bank, settings.date_window_fuzzy_days)
            if reference >= settings.ref_strong:
                candidates.append((score, days, ledger.id, bank.id, ledger, bank))
    ledger_scores = _candidate_scores(candidates, 2)
    bank_scores = _candidate_scores(candidates, 3)
    accepted = [
        candidate
        for candidate in candidates
        if candidate[0] == ledger_scores[candidate[2]][0]
        and candidate[0] == bank_scores[candidate[3]][0]
        and _clear_best(ledger_scores[candidate[2]], settings.pair_margin)
        and _clear_best(bank_scores[candidate[3]], settings.pair_margin)
    ]
    return _classify_amount_candidates(accepted, ledger_transactions, bank_transactions, settings)


def _candidate_scores(
    candidates: list[tuple[float, int, str, str, Transaction, Transaction]], id_index: int
) -> dict[str, list[float]]:
    """Group candidate scores by a source ID in descending deterministic order."""
    grouped: dict[str, list[float]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate[id_index], []).append(candidate[0])
    return {identifier: sorted(scores, reverse=True) for identifier, scores in grouped.items()}


def _classify_amount_candidates(
    candidates: list[tuple[float, int, str, str, Transaction, Transaction]],
    ledger_transactions: list[Transaction],
    bank_transactions: list[Transaction],
    settings: Settings,
) -> ClassificationResult:
    """Greedily classify accepted amount candidates with deterministic tie ordering."""
    used_ledger: set[str] = set()
    used_bank: set[str] = set()
    pairs: list[ClassifiedPair] = []
    for score, _, _, _, ledger, bank in sorted(
        candidates, key=lambda item: (-item[0], item[1], item[2], item[3])
    ):
        if ledger.id in used_ledger or bank.id in used_bank:
            continue
        difference = abs(ledger.amount_minor - bank.amount_minor)
        is_fee = (
            abs(bank.amount_minor) < abs(ledger.amount_minor)
            and difference <= settings.fee_max_minor
        )
        pairs.append(
            ClassifiedPair(
                "fee_difference" if is_fee else "amount_mismatch", ledger, bank, score, difference
            )
        )
        used_ledger.add(ledger.id)
        used_bank.add(bank.id)
    return ClassificationResult(
        pairs=pairs,
        unmatched_ledger=[row for row in ledger_transactions if row.id not in used_ledger],
        unmatched_bank=[row for row in bank_transactions if row.id not in used_bank],
    )


def classify_date_mismatches(
    ledger_transactions: list[Transaction], bank_transactions: list[Transaction], settings: Settings
) -> ClassificationResult:
    """Classify equal-reference amount pairs outside fuzzy but within date mismatch windows."""
    candidates: list[tuple[int, str, str, Transaction, Transaction]] = []
    for ledger in ledger_transactions:
        for bank in bank_transactions:
            if ledger.currency != bank.currency or ledger.amount_minor != bank.amount_minor:
                continue
            if not ledger.reference_norm or ledger.reference_norm != bank.reference_norm:
                continue
            days = date_difference_days(ledger.date, bank.date)
            if settings.date_window_fuzzy_days < days <= settings.date_mismatch_max_days:
                candidates.append((days, ledger.id, bank.id, ledger, bank))
    used_ledger: set[str] = set()
    used_bank: set[str] = set()
    pairs: list[ClassifiedPair] = []
    for days, _, _, ledger, bank in sorted(candidates):
        if ledger.id in used_ledger or bank.id in used_bank:
            continue
        pairs.append(ClassifiedPair("date_mismatch", ledger, bank, None, date_difference_days=days))
        used_ledger.add(ledger.id)
        used_bank.add(bank.id)
    return ClassificationResult(
        pairs=pairs,
        unmatched_ledger=[row for row in ledger_transactions if row.id not in used_ledger],
        unmatched_bank=[row for row in bank_transactions if row.id not in used_bank],
    )
