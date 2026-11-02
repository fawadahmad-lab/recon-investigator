"""Bounded, deterministic split-payment search used by rule `R6-SPLIT`.

An anchor record on one side may be settled by 2 to `SPLIT_MAX_PARTS` records on
the other side whose amounts sum to the anchor within tolerance. The candidate
pool, the number of part records, the solution listing and the explored node
count are all bounded, so an ambiguous or too-large search never guesses.
"""

from __future__ import annotations

from dataclasses import dataclass

from recon.config import Settings
from recon.matching.fuzzy import fuzzy_score
from recon.matching.keys import date_difference_days
from recon.models import Source, Transaction

MAX_AMBIGUOUS_CANDIDATE_SETS = 3


@dataclass(frozen=True)
class SplitMatch:
    """A uniquely solved split: one anchor and the opposite-side parts."""

    anchor: Transaction
    parts: tuple[Transaction, ...]
    difference_minor: int
    average_similarity: float


@dataclass(frozen=True)
class AmbiguousSplit:
    """An anchor with more than one bounded solution; no record is matched."""

    anchor: Transaction
    candidate_sets: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class SplitResult:
    """Split outcomes plus the records still available to later rules."""

    matches: list[SplitMatch]
    ambiguous: list[AmbiguousSplit]
    truncated: list[Transaction]
    unmatched_ledger: list[Transaction]
    unmatched_bank: list[Transaction]


@dataclass(frozen=True)
class _PoolPart:
    """One pool record with its similarity to the anchor."""

    transaction: Transaction
    similarity: float


def _same_sign(first: int, second: int) -> bool:
    """Return whether two nonzero signed minor-unit amounts have the same sign."""
    return first != 0 and second != 0 and (first > 0) == (second > 0)


def _candidate_pool(
    anchor: Transaction, records: list[Transaction], settings: Settings
) -> list[_PoolPart]:
    """Select the most similar eligible opposite-side records for one anchor."""
    scored: list[_PoolPart] = []
    for record in records:
        if record.currency != anchor.currency:
            continue
        if not _same_sign(anchor.amount_minor, record.amount_minor):
            continue
        if date_difference_days(anchor.date, record.date) > settings.split_date_window_days:
            continue
        score = fuzzy_score(anchor, record, settings.split_date_window_days)[0]
        if score < settings.split_min_sim:
            continue
        scored.append(_PoolPart(record, score))
    ranked = sorted(scored, key=lambda part: (-part.similarity, part.transaction.id))
    return sorted(ranked[: settings.split_max_pool], key=lambda part: part.transaction.id)


def _largest_prefix_sums(magnitudes: list[int], limit: int) -> list[int]:
    """Bound the reachable sum from any state by the sum of the k largest amounts."""
    ordered = sorted(magnitudes, reverse=True)
    prefix = [0]
    for value in ordered[:limit]:
        prefix.append(prefix[-1] + value)
    while len(prefix) <= limit:
        prefix.append(prefix[-1])
    return prefix


class _SplitSearch:
    """Depth-first combination search over one anchor's ID-ordered candidate pool."""

    def __init__(self, anchor: Transaction, pool: list[_PoolPart], settings: Settings) -> None:
        """Derive the bounded search targets from the anchor and its pool."""
        self.pool = pool
        self.magnitudes = [abs(part.transaction.amount_minor) for part in pool]
        self.max_parts = settings.split_max_parts
        self.low = max(0, abs(anchor.amount_minor) - settings.split_tolerance_minor)
        self.high = abs(anchor.amount_minor) + settings.split_tolerance_minor
        self.node_budget = settings.split_max_nodes
        self.largest = _largest_prefix_sums(self.magnitudes, self.max_parts)
        self.solutions: list[tuple[_PoolPart, ...]] = []
        self.nodes = 0
        self.truncated = False

    def run(self) -> None:
        """Explore combinations until a result, the listing cap, or the budget stops it."""
        self._visit(0, (), 0)

    def _stopped(self) -> bool:
        """Return whether further exploration can change the reported outcome."""
        return self.truncated or len(self.solutions) >= MAX_AMBIGUOUS_CANDIDATE_SETS

    def _visit(self, start: int, chosen: tuple[_PoolPart, ...], total: int) -> None:
        """Record an in-range combination and extend it within the part limit."""
        if self._stopped():
            return
        if len(chosen) >= 2 and self.low <= total <= self.high:
            self.solutions.append(chosen)
        if len(chosen) >= self.max_parts:
            return
        for index in range(start, len(self.pool)):
            if self._stopped():
                return
            self.nodes += 1
            if self.nodes > self.node_budget:
                self.truncated = True
                return
            new_total = total + self.magnitudes[index]
            slots_left = self.max_parts - len(chosen) - 1
            if new_total > self.high or new_total + self.largest[slots_left] < self.low:
                continue
            self._visit(index + 1, (*chosen, self.pool[index]), new_total)


def _to_match(anchor: Transaction, solution: tuple[_PoolPart, ...]) -> SplitMatch:
    """Build a split match from a unique solution."""
    parts = tuple(part.transaction for part in solution)
    similarity = sum(part.similarity for part in solution) / len(solution)
    return SplitMatch(
        anchor=anchor,
        parts=parts,
        difference_minor=sum(part.amount_minor for part in parts) - anchor.amount_minor,
        average_similarity=round(similarity, 4),
    )


def _anchor_sequence(
    ledger_transactions: list[Transaction], bank_transactions: list[Transaction]
) -> list[tuple[Source, Transaction]]:
    """Order anchors deterministically: the ledger side first, then the bank side."""
    return [(Source.LEDGER, row) for row in sorted(ledger_transactions, key=lambda row: row.id)] + [
        (Source.BANK, row) for row in sorted(bank_transactions, key=lambda row: row.id)
    ]


def _record_outcome(
    anchor: Transaction,
    side: Source,
    available: dict[Source, dict[str, Transaction]],
    solutions: list[tuple[_PoolPart, ...]],
    truncated: bool,
    matches: list[SplitMatch],
    ambiguous: list[AmbiguousSplit],
    missed: list[Transaction],
) -> None:
    """Report one anchor outcome and consume records only for a unique solution."""
    if truncated and len(solutions) < 2:
        missed.append(anchor)
        return
    if len(solutions) >= 2:
        ambiguous.append(
            AmbiguousSplit(
                anchor,
                tuple(tuple(part.transaction.id for part in item) for item in solutions),
            )
        )
        return
    if not solutions:
        return
    match = _to_match(anchor, solutions[0])
    matches.append(match)
    del available[side][anchor.id]
    for part in match.parts:
        del available[part.source][part.id]


def match_splits(
    ledger_transactions: list[Transaction],
    bank_transactions: list[Transaction],
    settings: Settings,
) -> SplitResult:
    """Match anchors with one unique split solution and report every other case."""
    if settings.split_date_window_days <= 0:
        raise ValueError("split_date_window_days must be positive")
    available = {
        Source.LEDGER: {row.id: row for row in sorted(ledger_transactions, key=lambda row: row.id)},
        Source.BANK: {row.id: row for row in sorted(bank_transactions, key=lambda row: row.id)},
    }
    matches: list[SplitMatch] = []
    ambiguous: list[AmbiguousSplit] = []
    truncated_anchors: list[Transaction] = []
    if settings.split_max_parts >= 2:
        for side, anchor in _anchor_sequence(ledger_transactions, bank_transactions):
            if anchor.id not in available[side]:
                continue
            other = Source.BANK if side is Source.LEDGER else Source.LEDGER
            pool = _candidate_pool(anchor, list(available[other].values()), settings)
            search = _SplitSearch(anchor, pool, settings)
            search.run()
            _record_outcome(
                anchor,
                side,
                available,
                search.solutions,
                search.truncated,
                matches,
                ambiguous,
                truncated_anchors,
            )
    return SplitResult(
        matches=matches,
        ambiguous=ambiguous,
        truncated=truncated_anchors,
        unmatched_ledger=[row for row in ledger_transactions if row.id in available[Source.LEDGER]],
        unmatched_bank=[row for row in bank_transactions if row.id in available[Source.BANK]],
    )
