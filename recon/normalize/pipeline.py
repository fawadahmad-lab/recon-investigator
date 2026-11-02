"""Deterministic conversion of raw statement rows into valid transactions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from recon.config import Settings
from recon.ingest.column_map import ColumnMap
from recon.models import Source, Transaction, ValidationIssue
from recon.normalize.amounts import parse_amount, parse_debit_credit
from recon.normalize.dates import parse_date
from recon.normalize.references import normalize_reference
from recon.normalize.text import normalize_text
from recon.normalize.validate import normalize_currency, raw_text, validation_issue

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class NormalizationResult:
    """Valid transactions and excluded row-level validation issues."""

    transactions: list[Transaction]
    issues: list[ValidationIssue]


def _raw_row(row: pd.Series) -> dict[str, Any]:
    """Preserve source values under string header names for audit output."""
    return {str(header): value for header, value in row.items()}


def _amount_for_row(row: pd.Series, column_map: ColumnMap) -> int:
    """Select signed or debit-credit amount parsing for one raw row."""
    if column_map.amount is not None:
        return parse_amount(row[column_map.amount])
    return parse_debit_credit(
        row[column_map.debit] if column_map.debit is not None else None,
        row[column_map.credit] if column_map.credit is not None else None,
    )


def _prefix(source: Source) -> str:
    """Return the canonical transaction ID prefix for a source."""
    return "B" if source is Source.BANK else "L"


def normalize_frame(
    frame: pd.DataFrame, source: Source, column_map: ColumnMap, settings: Settings
) -> NormalizationResult:
    """Normalize valid rows and record invalid rows without raising data errors."""
    transactions: list[Transaction] = []
    issues: list[ValidationIssue] = []
    seen_ids: set[str] = set()
    expected_currency: str | None = None
    for row_number, (_, row) in enumerate(frame.iterrows(), start=1):
        raw = _raw_row(row)
        transaction_id = f"{_prefix(source)}-{row_number:06d}"
        try:
            transaction_date = parse_date(row[column_map.date], settings.date_dayfirst)
        except ValueError as error:
            issues.append(
                validation_issue(source, row_number, "missing_or_invalid_date", str(error), raw)
            )
            continue
        try:
            amount_minor = _amount_for_row(row, column_map)
        except ValueError as error:
            issues.append(
                validation_issue(source, row_number, "unparsable_amount", str(error), raw)
            )
            continue
        if amount_minor == 0:
            issues.append(
                validation_issue(source, row_number, "zero_amount", "amount must not be zero", raw)
            )
            continue
        currency_value = row[column_map.currency] if column_map.currency is not None else None
        currency = normalize_currency(currency_value, settings.default_currency)
        if expected_currency is None:
            expected_currency = currency
        if currency != expected_currency:
            issues.append(
                validation_issue(
                    source, row_number, "mixed_currency", "currency differs within input", raw
                )
            )
            continue
        if transaction_id in seen_ids:
            issues.append(
                validation_issue(source, row_number, "duplicate_row_id", "duplicate row ID", raw)
            )
            continue
        seen_ids.add(transaction_id)
        if source is Source.LEDGER and settings.ledger_sign_inverted:
            amount_minor = -amount_minor
        transactions.append(
            Transaction(
                id=transaction_id,
                source=source,
                row_number=row_number,
                date=transaction_date,
                amount_minor=amount_minor,
                currency=currency,
                reference_raw=raw_text(row[column_map.reference]) if column_map.reference else "",
                reference_norm=normalize_reference(row[column_map.reference])
                if column_map.reference
                else "",
                description_raw=raw_text(row[column_map.description])
                if column_map.description
                else "",
                description_norm=normalize_text(row[column_map.description])
                if column_map.description
                else "",
                counterparty=raw_text(row[column_map.counterparty]) or None
                if column_map.counterparty
                else None,
                raw=raw,
            )
        )
    LOGGER.info(
        "normalization_complete source=%s valid=%d issues=%d",
        source,
        len(transactions),
        len(issues),
    )
    return NormalizationResult(transactions=transactions, issues=issues)
