"""Fixed, reproducible synthetic-data profile definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class SynthProfile:
    """The row volume, noise level, and labeled injection counts for a profile."""

    name: str
    ledger_rows: int
    noise_level: int
    injections: Mapping[str, int]


EASY = SynthProfile(
    name="easy",
    ledger_rows=200,
    noise_level=0,
    injections={
        "missing_in_bank": 5,
        "missing_in_ledger": 5,
        "duplicate_in_bank": 5,
        "duplicate_in_ledger": 5,
        "amount_mismatch": 5,
        "fee_difference": 5,
        "date_mismatch": 5,
        "split": 4,
        "ambiguous_split": 5,
        "decoy": 5,
    },
)

REALISTIC = SynthProfile(
    name="realistic",
    ledger_rows=500,
    noise_level=1,
    injections={
        "missing_in_bank": 10,
        "missing_in_ledger": 10,
        "duplicate_in_bank": 6,
        "duplicate_in_ledger": 6,
        "amount_mismatch": 8,
        "fee_difference": 8,
        "date_mismatch": 8,
        "split": 8,
        "ambiguous_split": 2,
        "decoy": 10,
    },
)

HARD = SynthProfile(
    name="hard",
    ledger_rows=1000,
    noise_level=2,
    injections={
        "missing_in_bank": 20,
        "missing_in_ledger": 20,
        "duplicate_in_bank": 12,
        "duplicate_in_ledger": 12,
        "amount_mismatch": 16,
        "fee_difference": 16,
        "date_mismatch": 16,
        "split": 16,
        "ambiguous_split": 6,
        "decoy": 20,
    },
)

PROFILES = {profile.name: profile for profile in (EASY, REALISTIC, HARD)}


def get_profile(name: str) -> SynthProfile:
    """Return a named profile or raise ValueError with valid choices."""
    try:
        return PROFILES[name]
    except KeyError as error:
        raise ValueError(f"unknown profile {name!r}; choose from {', '.join(PROFILES)}") from error


def profile_names() -> tuple[str, ...]:
    """Return profile names in stable CLI-display order."""
    return tuple(PROFILES)
