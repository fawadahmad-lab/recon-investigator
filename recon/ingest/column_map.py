"""Deterministic column detection and manual override validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from recon.errors import MappingError

COLUMN_FIELDS = (
    "date",
    "amount",
    "debit",
    "credit",
    "reference",
    "description",
    "currency",
    "counterparty",
)

SYNONYMS: dict[str, tuple[str, ...]] = {
    "date": ("date", "transaction date", "posting date", "value date", "txn date"),
    "amount": ("amount", "transaction amount", "net amount", "value", "total"),
    "debit": ("debit", "withdrawal", "money out", "outflow", "charge"),
    "credit": ("credit", "deposit", "money in", "inflow"),
    "reference": ("reference", "ref", "transaction id", "invoice", "check number"),
    "description": ("description", "memo", "details", "narrative", "particulars"),
    "currency": ("currency", "curr", "currency code"),
    "counterparty": ("counterparty", "payee", "merchant", "beneficiary", "vendor"),
}


@dataclass(frozen=True)
class ColumnMap:
    """The source header selected for each canonical input field."""

    date: str
    amount: str | None = None
    debit: str | None = None
    credit: str | None = None
    reference: str | None = None
    description: str | None = None
    currency: str | None = None
    counterparty: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        """Return a stable dictionary representation of the mapping."""
        return {field: getattr(self, field) for field in COLUMN_FIELDS}


def _normalise_header(header: str) -> str:
    """Normalize a header for synonym matching without changing the source name."""
    return re.sub(r"[^a-z0-9]+", " ", header.casefold()).strip()


def _mapping_error(message: str, headers: list[str]) -> MappingError:
    """Build a mapping error that includes all source headers."""
    found = ", ".join(headers) if headers else "(none)"
    return MappingError(f"{message}. Headers found: {found}")


def _auto_map(headers: list[str]) -> dict[str, str | None]:
    """Select the first source header matching each canonical synonym list."""
    normalized = {header: _normalise_header(header) for header in headers}
    result: dict[str, str | None] = {}
    for field in COLUMN_FIELDS:
        aliases = set(SYNONYMS[field])
        result[field] = next(
            (header for header in headers if normalized[header] in aliases),
            None,
        )
    return result


def detect_column_map(headers: list[str], column_map: Mapping[str, str] | None = None) -> ColumnMap:
    """Detect canonical columns and apply a validated manual override."""
    if not headers:
        raise _mapping_error("input file has no headers", headers)
    mapping = _auto_map(headers)
    if column_map is not None:
        unknown = sorted(set(column_map).difference(COLUMN_FIELDS))
        if unknown:
            raise _mapping_error(f"unknown column-map fields: {', '.join(unknown)}", headers)
        for field, header in column_map.items():
            if header not in headers:
                raise _mapping_error(f"mapped header does not exist: {header}", headers)
            mapping[field] = header
    if mapping["date"] is None:
        raise _mapping_error("required date column is missing", headers)
    if mapping["amount"] is None and not (mapping["debit"] or mapping["credit"]):
        raise _mapping_error("required amount or debit/credit column is missing", headers)
    return ColumnMap(**mapping)
