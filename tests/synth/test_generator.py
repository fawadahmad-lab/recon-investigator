"""Tests for deterministic synthetic reconciliation data generation."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest

from recon.normalize.references import normalize_reference
from recon.synth.generator import generate_dataset
from recon.synth.profiles import get_profile


def _load_truth(output_dir: Path) -> dict[str, object]:
    """Read a generated ground-truth document."""
    return json.loads((output_dir / "ground_truth.json").read_text(encoding="utf-8"))


def _all_ids(truth: dict[str, object]) -> list[str]:
    """Collect every exported source ID from ground-truth entries."""
    entries = [*truth["matches"], *truth["expected"]]
    return [
        identifier for entry in entries for identifier in [*entry["ledger_ids"], *entry["bank_ids"]]
    ]


def test_same_seed_produces_byte_identical_files(tmp_path: Path) -> None:
    """Every exported synthetic artifact is identical for the same profile and seed."""
    first = generate_dataset("easy", 7, tmp_path / "first")
    second = generate_dataset("easy", 7, tmp_path / "second")

    for name in ("ledger.csv", "bank.csv", "ground_truth.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


@pytest.mark.parametrize("profile_name", ("easy", "realistic", "hard"))
def test_injection_counts_match_profile(profile_name: str, tmp_path: Path) -> None:
    """Each profile emits exactly its documented discrepancy and split counts."""
    truth = _load_truth(generate_dataset(profile_name, 42, tmp_path / profile_name))
    profile = get_profile(profile_name)
    expected_counts = Counter(entry["type"] for entry in truth["expected"])
    match_counts = Counter(entry["type"] for entry in truth["matches"])
    decoys = [entry for entry in truth["matches"] if entry.get("decoy")]

    for kind in (
        "missing_in_bank",
        "missing_in_ledger",
        "duplicate_in_bank",
        "duplicate_in_ledger",
        "amount_mismatch",
        "fee_difference",
        "date_mismatch",
        "ambiguous_split",
    ):
        assert expected_counts[kind] == profile.injections[kind]
    assert match_counts["match_split"] == profile.injections["split"]
    assert len(decoys) == profile.injections["decoy"] * 2


def test_ground_truth_ids_exist_and_decoys_are_matches(tmp_path: Path) -> None:
    """Ground truth references final shuffled bank IDs and never labels decoys as discrepancies."""
    output_dir = generate_dataset("realistic", 42, tmp_path / "realistic")
    truth = _load_truth(output_dir)
    with (output_dir / "ledger.csv").open(encoding="utf-8", newline="") as handle:
        ledger_count = sum(1 for _ in csv.DictReader(handle))
    with (output_dir / "bank.csv").open(encoding="utf-8", newline="") as handle:
        bank_count = sum(1 for _ in csv.DictReader(handle))

    for identifier in _all_ids(truth):
        prefix, number = identifier.split("-")
        assert prefix in {"L", "B"}
        assert 1 <= int(number) <= (ledger_count if prefix == "L" else bank_count)
    assert all("decoy" not in entry for entry in truth["expected"])
    assert any(entry.get("decoy") for entry in truth["matches"])


def test_fuzzy_labels_use_different_normalized_references(tmp_path: Path) -> None:
    """Reference-noise labels remain distinct after the production normalizer runs."""
    output_dir = generate_dataset("realistic", 42, tmp_path / "realistic")
    truth = _load_truth(output_dir)
    fuzzy = next(entry for entry in truth["matches"] if entry["type"] == "match_fuzzy")
    with (output_dir / "ledger.csv").open(encoding="utf-8", newline="") as handle:
        ledger = list(csv.DictReader(handle))
    with (output_dir / "bank.csv").open(encoding="utf-8", newline="") as handle:
        bank = list(csv.DictReader(handle))
    ledger_row = ledger[int(fuzzy["ledger_ids"][0].split("-")[1]) - 1]
    bank_row = bank[int(fuzzy["bank_ids"][0].split("-")[1]) - 1]

    assert normalize_reference(ledger_row["Reference"]) != normalize_reference(
        bank_row["Reference"]
    )


def _rows_by_id(path: Path) -> dict[str, dict[str, str]]:
    """Index exported CSV rows by the ground-truth ID derived from their position."""
    prefix = "L" if path.name == "ledger.csv" else "B"
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            f"{prefix}-{number:06d}": row
            for number, row in enumerate(csv.DictReader(handle), start=1)
        }


def _identity(row: dict[str, str]) -> tuple[str, str]:
    """Return the amount and normalized reference that Tier 1 and Tier 2 compare."""
    return (row["Amount"], normalize_reference(row["Reference"]))


def test_one_sided_injections_cannot_pair_across_sources(tmp_path: Path) -> None:
    """A labeled missing record shares no amount and reference with any other-side record."""
    output_dir = generate_dataset("realistic", 42, tmp_path / "realistic")
    truth = _load_truth(output_dir)
    ledger = _rows_by_id(output_dir / "ledger.csv")
    bank = _rows_by_id(output_dir / "bank.csv")
    ledger_identity = {_identity(row) for row in ledger.values()}
    bank_identity = {_identity(row) for row in bank.values()}

    for entry in truth["expected"]:
        if entry["type"] == "missing_in_ledger":
            row = bank[entry["bank_ids"][0]]
            assert _identity(row) not in ledger_identity
            assert row["Amount"].startswith("-")
        if entry["type"] == "missing_in_bank":
            assert _identity(ledger[entry["ledger_ids"][0]]) not in bank_identity


def test_duplicate_injections_leave_only_one_primary_on_the_other_side(
    tmp_path: Path,
) -> None:
    """A labeled duplicate is a copy on its own side, so the other side cannot absorb it."""
    output_dir = generate_dataset("realistic", 42, tmp_path / "realistic")
    truth = _load_truth(output_dir)
    ledger = _rows_by_id(output_dir / "ledger.csv")
    bank = _rows_by_id(output_dir / "bank.csv")

    for side, rows, other in (
        ("duplicate_in_ledger", ledger, bank),
        ("duplicate_in_bank", bank, ledger),
    ):
        for entry in truth["expected"]:
            if entry["type"] != side:
                continue
            record_id = [*entry["ledger_ids"], *entry["bank_ids"]][0]
            identity = _identity(rows[record_id])
            assert sum(_identity(row) == identity for row in rows.values()) == 2
            assert sum(_identity(row) == identity for row in other.values()) <= 1
