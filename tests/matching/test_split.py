"""Tests for the bounded, deterministic split-payment matcher."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from recon.config import get_settings
from recon.matching.split import match_splits
from recon.models import Source, Transaction

DAY = date(2026, 1, 5)


def _transaction(
    source: Source,
    number: int,
    reference: str,
    amount_minor: int,
    transaction_date: date = DAY,
    description: str = "acme supplies",
    currency: str = "USD",
) -> Transaction:
    """Create a deterministic split fixture with an ID-ordered identity."""
    prefix = "L" if source is Source.LEDGER else "B"
    return Transaction(
        id=f"{prefix}-{number:06d}",
        source=source,
        row_number=number,
        date=transaction_date,
        amount_minor=amount_minor,
        currency=currency,
        reference_norm=reference,
        description_norm=description,
    )


def _ledger(number: int, amount_minor: int, reference: str = "SPLIT1") -> Transaction:
    """Create a ledger fixture sharing the default split reference."""
    return _transaction(Source.LEDGER, number, reference, amount_minor)


def _bank(number: int, amount_minor: int, reference: str = "SPLIT1") -> Transaction:
    """Create a bank fixture sharing the default split reference."""
    return _transaction(Source.BANK, number, reference, amount_minor)


def test_two_part_bank_split_matches_the_ledger_anchor() -> None:
    """A unique two-part bank sum resolves one ledger anchor."""
    result = match_splits([_ledger(1, 10000)], [_bank(1, 6000), _bank(2, 4000)], get_settings())

    assert len(result.matches) == 1
    assert result.matches[0].anchor.id == "L-000001"
    assert [part.id for part in result.matches[0].parts] == ["B-000001", "B-000002"]
    assert result.matches[0].difference_minor == 0
    assert result.unmatched_ledger == []
    assert result.unmatched_bank == []


def test_three_part_split_is_found_and_does_not_need_a_fourth_part() -> None:
    """A three-record sum resolves the anchor without requiring the maximum part count."""
    ledger = [_ledger(1, 9000)]
    bank = [_bank(1, 5000), _bank(2, 2500), _bank(3, 1500), _bank(4, 7000)]

    result = match_splits(ledger, bank, get_settings())

    assert [part.id for part in result.matches[0].parts] == ["B-000001", "B-000002", "B-000003"]
    assert result.matches[0].difference_minor == 0
    assert result.ambiguous == []


def test_four_part_split_uses_the_configured_maximum() -> None:
    """Four records are allowed and a three-record partial sum is not reported."""
    ledger = [_ledger(1, 10000)]
    bank = [_bank(1, 4000), _bank(2, 3000), _bank(3, 2000), _bank(4, 1000)]

    result = match_splits(ledger, bank, get_settings())

    assert len(result.matches) == 1
    assert [part.id for part in result.matches[0].parts] == [
        "B-000001",
        "B-000002",
        "B-000003",
        "B-000004",
    ]


def test_a_split_needing_more_parts_than_the_limit_is_not_matched() -> None:
    """The bounded part count leaves a five-record split unmatched instead of guessing."""
    ledger = [_ledger(1, 5000)]
    bank = [_bank(number, 1000) for number in range(1, 6)]

    result = match_splits(ledger, bank, get_settings())

    assert result.matches == []
    assert result.ambiguous == []
    assert result.truncated == []
    assert [item.id for item in result.unmatched_ledger] == ["L-000001"]


def test_split_search_runs_in_both_directions() -> None:
    """Ledger anchors may consume bank parts and bank anchors may consume ledger parts."""
    ledger = [_ledger(1, 10000, "SPLA"), _ledger(2, 5000, "SPLB"), _ledger(3, 3000, "SPLB")]
    bank = [_bank(1, 6000, "SPLA"), _bank(2, 4000, "SPLA"), _bank(3, 8000, "SPLB")]

    result = match_splits(ledger, bank, get_settings())

    assert [(item.anchor.id, [part.id for part in item.parts]) for item in result.matches] == [
        ("L-000001", ["B-000001", "B-000002"]),
        ("B-000003", ["L-000002", "L-000003"]),
    ]
    assert result.unmatched_ledger == []
    assert result.unmatched_bank == []


def test_negative_anchor_splits_over_negative_parts() -> None:
    """Signed money is preserved: an outflow anchor splits into outflow parts."""
    ledger = [_ledger(1, -10000)]
    bank = [_bank(1, -6000), _bank(2, -4000)]

    result = match_splits(ledger, bank, get_settings())

    assert [part.amount_minor for part in result.matches[0].parts] == [-6000, -4000]
    assert result.matches[0].difference_minor == 0


def test_ambiguous_split_lists_candidate_sets_and_matches_nothing() -> None:
    """Two valid combinations produce an ambiguity finding and consume no records."""
    bank = [_bank(1, 6000), _bank(2, 4000), _bank(3, 7000), _bank(4, 3000)]

    result = match_splits([_ledger(1, 10000)], bank, get_settings())

    assert result.matches == []
    assert len(result.ambiguous) == 1
    assert result.ambiguous[0].anchor.id == "L-000001"
    assert result.ambiguous[0].candidate_sets == (
        ("B-000001", "B-000002"),
        ("B-000003", "B-000004"),
    )
    assert [item.id for item in result.unmatched_bank] == [
        "B-000001",
        "B-000002",
        "B-000003",
        "B-000004",
    ]
    assert [item.id for item in result.unmatched_ledger] == ["L-000001"]


def test_ambiguous_listing_is_capped_at_three_candidate_sets() -> None:
    """Only the first three candidate sets are reported for a many-way ambiguity."""
    bank = [
        _bank(1, 6000),
        _bank(2, 4000),
        _bank(3, 7000),
        _bank(4, 3000),
        _bank(5, 5000),
        _bank(6, 5000),
        _bank(7, 8000),
        _bank(8, 2000),
    ]

    result = match_splits([_ledger(1, 10000)], bank, get_settings())

    assert len(result.ambiguous[0].candidate_sets) == 3
    assert result.matches == []


def test_search_budget_truncation_flags_the_anchor_without_matching() -> None:
    """An exhausted node budget leaves the anchor unmatched and records the flag."""
    bank = [_bank(number, 2500) for number in range(1, 11)] + [_bank(11, 1000)]
    ledger = [_ledger(1, 9000)]
    truncated_settings = replace(get_settings(), split_max_nodes=20)

    limited = match_splits(ledger, bank, truncated_settings)
    complete = match_splits(ledger, bank, get_settings())

    assert limited.matches == []
    assert limited.ambiguous == []
    assert [item.id for item in limited.truncated] == ["L-000001"]
    assert [item.id for item in limited.unmatched_ledger] == ["L-000001"]
    assert len(limited.unmatched_bank) == 11
    assert complete.truncated == []
    assert complete.matches == []


def test_results_are_deterministic_across_repeats_and_input_order() -> None:
    """Repeated and reversed-order runs produce identical outcomes and record sets."""
    ledger = [_ledger(1, 10000, "SPLA"), _ledger(2, 8000, "SPLB")]
    bank = [
        _bank(1, 6000, "SPLA"),
        _bank(2, 4000, "SPLA"),
        _bank(3, 7000, "SPLB"),
        _bank(4, 3000, "SPLB"),
        _bank(5, 5000, "SPLB"),
    ]
    first = match_splits(ledger, bank, get_settings())
    again = match_splits(ledger, bank, get_settings())
    reversed_run = match_splits(list(reversed(ledger)), list(reversed(bank)), get_settings())

    assert again == first
    assert [
        (item.anchor.id, [part.id for part in item.parts]) for item in reversed_run.matches
    ] == [(item.anchor.id, [part.id for part in item.parts]) for item in first.matches]
    assert [item.candidate_sets for item in reversed_run.ambiguous] == [
        item.candidate_sets for item in first.ambiguous
    ]


def test_pool_is_limited_by_configured_size() -> None:
    """A pool truncated below the number of needed parts cannot produce a split."""
    ledger = [_ledger(1, 10000)]
    bank = [_bank(1, 6000), _bank(2, 4000)]

    limited = match_splits(ledger, bank, replace(get_settings(), split_max_pool=1))

    assert limited.matches == []
    assert limited.ambiguous == []
    assert limited.truncated == []
    assert [item.id for item in limited.unmatched_bank] == ["B-000001", "B-000002"]


def test_pool_drops_records_below_the_minimum_similarity() -> None:
    """Unrelated records are excluded from the pool unless the similarity floor is removed."""
    ledger = [_ledger(1, 10000)]
    bank = [_bank(1, 6000), _transaction(Source.BANK, 2, "", 4000, description="")]

    filtered = match_splits(ledger, bank, get_settings())
    permissive = match_splits(ledger, bank, replace(get_settings(), split_min_sim=0.0))

    assert filtered.matches == []
    assert [item.id for item in filtered.unmatched_bank] == ["B-000001", "B-000002"]
    assert [part.id for part in permissive.matches[0].parts] == ["B-000001", "B-000002"]


def test_pool_requires_same_currency_sign_and_date_window() -> None:
    """Currency, sign and the split date window gate which records may form a split."""
    anchor = _ledger(1, 10000)
    wrong_currency = [_bank(1, 6000), _transaction(Source.BANK, 2, "SPLIT1", 4000, currency="EUR")]
    wrong_sign = [_bank(1, 6000), _transaction(Source.BANK, 2, "SPLIT1", -4000)]
    outside_window = [
        _bank(1, 6000),
        _transaction(Source.BANK, 2, "SPLIT1", 4000, transaction_date=DAY + timedelta(days=8)),
    ]
    inside_window = [
        _bank(1, 6000),
        _transaction(Source.BANK, 2, "SPLIT1", 4000, transaction_date=DAY + timedelta(days=7)),
    ]

    assert match_splits([anchor], wrong_currency, get_settings()).matches == []
    assert match_splits([anchor], wrong_sign, get_settings()).matches == []
    assert match_splits([anchor], outside_window, get_settings()).matches == []
    assert len(match_splits([anchor], inside_window, get_settings()).matches) == 1


def test_parts_are_never_reused_by_a_second_anchor() -> None:
    """One-to-one assignment keeps consumed parts from a second anchor's pool."""
    ledger = [_ledger(1, 10000), _ledger(2, 10000)]
    bank = [_bank(1, 6000), _bank(2, 4000)]

    result = match_splits(ledger, bank, get_settings())

    assert len(result.matches) == 1
    assert result.matches[0].anchor.id == "L-000001"
    assert [item.id for item in result.unmatched_ledger] == ["L-000002"]


def test_tolerance_is_applied_in_integer_minor_units() -> None:
    """A configured minor-unit tolerance accepts an in-range sum and reports the residual."""
    ledger = [_ledger(1, 10000)]
    bank = [_bank(1, 6000), _bank(2, 4030)]

    result = match_splits(ledger, bank, replace(get_settings(), split_tolerance_minor=50))

    assert result.matches[0].difference_minor == 30
    assert result.ambiguous == []
