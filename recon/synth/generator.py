"""Seeded synthetic bank and ledger files with labeled reconciliation cases."""

from __future__ import annotations

import csv
import logging
import random
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from recon.models import format_amount
from recon.synth.profiles import SynthProfile, get_profile
from recon.synth.truth import write_ground_truth

LOGGER = logging.getLogger(__name__)
VENDORS = ("Acme Supplies", "Northwind Services", "Bluebird Coffee", "Cedar Office")
BANK_CHARGES = (
    "Bank service charge",
    "Card processing fee",
    "Account analysis fee",
    "Wire return fee",
)


@dataclass(frozen=True)
class SyntheticRow:
    """Internal synthetic row retaining a stable key until final ID assignment."""

    key: str
    transaction_date: date
    amount_minor: int
    reference: str
    description: str
    currency: str = "USD"

    def csv_row(self) -> dict[str, str]:
        """Return the stable CSV representation of this synthetic row."""
        return {
            "Date": self.transaction_date.isoformat(),
            "Amount": format_amount(self.amount_minor),
            "Reference": self.reference,
            "Description": self.description,
            "Currency": self.currency,
        }


def _base_rows(profile: SynthProfile, rng: random.Random) -> list[SyntheticRow]:
    """Build the profile's ledger seed rows with realistic but synthetic values."""
    start = date(2026, 1, 1)
    rows: list[SyntheticRow] = []
    for index in range(1, profile.ledger_rows + 1):
        vendor = VENDORS[index % len(VENDORS)]
        rows.append(
            SyntheticRow(
                key=f"base-{index:04d}",
                transaction_date=start + timedelta(days=rng.randrange(365)),
                amount_minor=rng.randrange(1000, 250000),
                reference=f"INV-2026-{index:04d}",
                description=f"{vendor} invoice {index:04d}",
            )
        )
    return rows


def _bank_copy(row: SyntheticRow, profile: SynthProfile, rng: random.Random) -> SyntheticRow:
    """Derive an initially matching bank row with profile-controlled reference noise."""
    reference = row.reference
    if profile.noise_level and rng.randrange(4 if profile.noise_level == 1 else 2) == 0:
        reference = f"{reference[:-1]}X"
    return replace(
        row,
        transaction_date=row.transaction_date
        + timedelta(days=rng.randrange(profile.noise_level + 1)),
        reference=reference,
    )


def _take_targets(rows: list[SyntheticRow], count: int, offset: int) -> list[SyntheticRow]:
    """Choose a deterministic non-overlapping block of base rows for an injection."""
    return rows[offset : offset + count]


def _remove_key(rows: list[SyntheticRow], key: str) -> SyntheticRow:
    """Remove and return the unique row with an internal key."""
    for index, row in enumerate(rows):
        if row.key == key:
            return rows.pop(index)
    raise ValueError(f"synthetic row key not found: {key}")


def _event(kind: str, ledger_keys: list[str], bank_keys: list[str], **extra: Any) -> dict[str, Any]:
    """Create an internal labeled event before source IDs are assigned."""
    return {"type": kind, "ledger_keys": ledger_keys, "bank_keys": bank_keys, **extra}


def _inject_missing(
    ledger: list[SyntheticRow],
    bank: list[SyntheticRow],
    targets: list[SyntheticRow],
    events: list[dict[str, Any]],
) -> None:
    """Drop bank twins of ledger rows and add bank charges absent from the ledger."""
    for row in targets:
        _remove_key(bank, row.key)
        events.append(_event("missing_in_bank", [row.key], [], cause="timing_delay_not_cleared"))
    for index, row in enumerate(targets):
        key = f"missing-bank-{index:04d}"
        bank.append(
            SyntheticRow(
                key=key,
                transaction_date=row.transaction_date,
                amount_minor=-(500 + 25 * index),
                reference=f"CHG-{index:04d}",
                description=BANK_CHARGES[index % len(BANK_CHARGES)],
            )
        )
        events.append(_event("missing_in_ledger", [], [key], cause="unrecorded_bank_item"))


def _inject_duplicates(
    ledger: list[SyntheticRow],
    bank: list[SyntheticRow],
    ledger_targets: list[SyntheticRow],
    bank_targets: list[SyntheticRow],
    events: list[dict[str, Any]],
) -> None:
    """Copy a matched record on one side only, leaving the extra copy unmatched.

    Ledger copies stay byte-identical to their primary: ledger IDs follow input
    order, so Tier 1 always keeps the primary and reports the copy. Bank rows are
    shuffled, so a bank copy is posted one day after its twin and is therefore
    always the farther candidate for Tier 1 regardless of its final ID.
    """
    for index, row in enumerate(ledger_targets):
        key = f"dup-ledger-{index:04d}"
        ledger.append(replace(row, key=key))
        events.append(_event("duplicate_in_ledger", [key], [], cause="double_entry_in_ledger"))
    for index, row in enumerate(bank_targets):
        twin = next(item for item in bank if item.key == row.key)
        key = f"dup-bank-{index:04d}"
        bank.append(
            replace(twin, key=key, transaction_date=twin.transaction_date + timedelta(days=1))
        )
        events.append(_event("duplicate_in_bank", [], [key], cause="duplicate_bank_charge"))


def _inject_difference(
    bank: list[SyntheticRow], targets: list[SyntheticRow], events: list[dict[str, Any]], kind: str
) -> None:
    """Inject one labeled amount, fee, or date discrepancy for each target."""
    causes = {
        "amount_mismatch": "typo_or_transposition",
        "fee_difference": "bank_fee_deducted",
        "date_mismatch": "late_posting",
    }
    for row in targets:
        changed = _remove_key(bank, row.key)
        if kind == "amount_mismatch":
            changed = replace(changed, amount_minor=changed.amount_minor + 321)
        elif kind == "fee_difference":
            changed = replace(changed, amount_minor=changed.amount_minor - 125)
        else:
            changed = replace(
                changed, transaction_date=changed.transaction_date + timedelta(days=15)
            )
        bank.append(changed)
        events.append(_event(kind, [row.key], [row.key], cause=causes[kind]))


def _inject_splits(
    bank: list[SyntheticRow],
    targets: list[SyntheticRow],
    events: list[dict[str, Any]],
    ambiguous: bool,
    label: str,
) -> None:
    """Replace a bank record with one unique or two ambiguous two-part combinations."""
    for index, row in enumerate(targets):
        original = _remove_key(bank, row.key)
        first_amount = original.amount_minor // 2
        second_amount = original.amount_minor - first_amount
        keys = [f"{label}-{index:04d}-a", f"{label}-{index:04d}-b"]
        bank.extend(
            [
                replace(original, key=keys[0], amount_minor=first_amount),
                replace(original, key=keys[1], amount_minor=second_amount),
            ]
        )
        if ambiguous:
            alternate = [f"{label}-{index:04d}-c", f"{label}-{index:04d}-d"]
            bank.extend(
                [
                    replace(original, key=alternate[0], amount_minor=first_amount - 100),
                    replace(original, key=alternate[1], amount_minor=second_amount + 100),
                ]
            )
            events.append(
                _event(
                    "ambiguous_split",
                    [row.key],
                    [*keys, *alternate],
                    cause="multiple_possible_combinations",
                )
            )
        else:
            events.append(_event("match_split", [row.key], keys))


def _inject_decoys(
    ledger: list[SyntheticRow], bank: list[SyntheticRow], count: int, events: list[dict[str, Any]]
) -> None:
    """Add legitimate repeated payments as matched decoys, never discrepancies."""
    for index in range(count):
        row = SyntheticRow(
            key=f"decoy-{index:04d}-a",
            transaction_date=date(2026, 12, 1) + timedelta(days=index),
            amount_minor=5000 + index,
            reference=f"DEC-{index:04d}",
            description="Legitimate repeated payment",
        )
        twin = replace(row, key=f"decoy-{index:04d}-b")
        ledger.extend([row, twin])
        bank.extend([row, twin])
        events.extend(
            [
                _event("match_exact", [row.key], [row.key], decoy=True),
                _event("match_exact", [twin.key], [twin.key], decoy=True),
            ]
        )


def _assign_ids(rows: list[SyntheticRow], prefix: str) -> dict[str, str]:
    """Assign source IDs from final output order after all mutations and shuffling."""
    return {row.key: f"{prefix}-{index:06d}" for index, row in enumerate(rows, start=1)}


def _ground_truth(
    profile: SynthProfile,
    seed: int,
    events: list[dict[str, Any]],
    ledger_ids: dict[str, str],
    bank_ids: dict[str, str],
) -> dict[str, Any]:
    """Convert internal event keys into stable exported ground-truth IDs."""
    matches: list[dict[str, Any]] = []
    expected: list[dict[str, Any]] = []
    for event in events:
        item = {
            "type": event["type"],
            "ledger_ids": [ledger_ids[key] for key in event["ledger_keys"]],
            "bank_ids": [bank_ids[key] for key in event["bank_keys"]],
        }
        if "cause" in event:
            item["cause"] = event["cause"]
        if event.get("decoy"):
            item["decoy"] = True
        (matches if event["type"].startswith("match_") else expected).append(item)
    return {
        "expected": expected,
        "injection_counts": dict(profile.injections),
        "matches": matches,
        "profile": profile.name,
        "seed": seed,
    }


def _write_csv(path: Path, rows: list[SyntheticRow]) -> None:
    """Write generated rows with stable headers, line endings, and UTF-8 encoding."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["Date", "Amount", "Reference", "Description", "Currency"]
        )
        writer.writeheader()
        writer.writerows(row.csv_row() for row in rows)


def generate_dataset(profile_name: str, seed: int, output_dir: Path) -> Path:
    """Generate seeded bank, ledger, and ground-truth files into an output directory."""
    profile = get_profile(profile_name)
    rng = random.Random(seed)
    ledger = _base_rows(profile, rng)
    bank = [_bank_copy(row, profile, rng) for row in ledger]
    events: list[dict[str, Any]] = []
    cursor = 0
    for kind in (
        "missing_in_bank",
        "amount_mismatch",
        "fee_difference",
        "date_mismatch",
        "split",
        "ambiguous_split",
    ):
        count = profile.injections[kind]
        targets = _take_targets(ledger, count, cursor)
        cursor += count
        if kind == "missing_in_bank":
            _inject_missing(ledger, bank, targets, events)
        elif kind == "split":
            _inject_splits(bank, targets, events, ambiguous=False, label="split")
        elif kind == "ambiguous_split":
            _inject_splits(bank, targets, events, ambiguous=True, label="ambiguous")
        else:
            _inject_difference(bank, targets, events, kind)
    duplicate_count = (
        profile.injections["duplicate_in_ledger"] + profile.injections["duplicate_in_bank"]
    )
    duplicate_targets = _take_targets(ledger, duplicate_count, cursor)
    cursor += duplicate_count
    ledger_end = profile.injections["duplicate_in_ledger"]
    _inject_duplicates(
        ledger, bank, duplicate_targets[:ledger_end], duplicate_targets[ledger_end:], events
    )
    _inject_decoys(ledger, bank, profile.injections["decoy"], events)
    injected_ledger_keys = {key for event in events for key in event["ledger_keys"]}
    for row in ledger:
        if row.key in injected_ledger_keys or row.key not in {item.key for item in bank}:
            continue
        bank_row = next(item for item in bank if item.key == row.key)
        match_type = "match_exact" if bank_row.reference == row.reference else "match_fuzzy"
        events.append(_event(match_type, [row.key], [row.key]))
    rng.shuffle(bank)
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger_ids = _assign_ids(ledger, "L")
    bank_ids = _assign_ids(bank, "B")
    _write_csv(output_dir / "ledger.csv", ledger)
    _write_csv(output_dir / "bank.csv", bank)
    write_ground_truth(
        output_dir / "ground_truth.json", _ground_truth(profile, seed, events, ledger_ids, bank_ids)
    )
    LOGGER.info(
        "synthetic_data_generated profile=%s seed=%d output=%s", profile.name, seed, output_dir
    )
    return output_dir
