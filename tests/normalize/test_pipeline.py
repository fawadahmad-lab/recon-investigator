"""Tests for transaction normalization and row-level validation."""

from dataclasses import replace

import pandas as pd

from recon.config import get_settings
from recon.ingest.column_map import ColumnMap
from recon.models import Source
from recon.normalize.dates import parse_date
from recon.normalize.pipeline import normalize_frame


def _settings(**changes: object):
    """Return settings adjusted for a focused normalization test."""
    return replace(get_settings(), **changes)


def test_parse_dates_in_common_formats_and_excel_serial() -> None:
    """Date parsing supports ISO, configured ambiguity, month names, and Excel values."""
    assert str(parse_date("2026-03-04")) == "2026-03-04"
    assert str(parse_date("04/03/2026", dayfirst=True)) == "2026-03-04"
    assert str(parse_date("03/04/2026", dayfirst=False)) == "2026-03-04"
    assert str(parse_date("04-Mar-2026")) == "2026-03-04"
    assert str(parse_date(1)) == "1900-01-01"


def test_normalizes_amount_reference_description_and_ids() -> None:
    """Valid rows become canonical transactions with deterministic source IDs."""
    frame = pd.DataFrame(
        {
            "Date": ["2026-03-04"],
            "Amount": ["(1,234.50)"],
            "Reference": ["payment-INV_2031"],
            "Description": ["ACME!!! card **** 1234"],
            "Currency": ["usd"],
        }
    )
    column_map = ColumnMap(
        date="Date",
        amount="Amount",
        reference="Reference",
        description="Description",
        currency="Currency",
    )

    result = normalize_frame(frame, Source.LEDGER, column_map, _settings())

    assert result.issues == []
    assert result.transactions[0].id == "L-000001"
    assert result.transactions[0].amount_minor == -123450
    assert result.transactions[0].reference_norm == "2031"
    assert result.transactions[0].description_norm == "acme card"


def test_debit_credit_and_ledger_sign_inversion() -> None:
    """Debit-credit inputs are signed and can be inverted for ledger exports."""
    frame = pd.DataFrame({"Date": ["2026-03-04"], "Debit": ["12.50"], "Credit": [""]})
    column_map = ColumnMap(date="Date", debit="Debit", credit="Credit")

    result = normalize_frame(frame, Source.LEDGER, column_map, _settings(ledger_sign_inverted=True))

    assert result.transactions[0].amount_minor == 1250


def test_invalid_rows_are_excluded_with_row_level_issues() -> None:
    """Missing dates, invalid amounts, zeroes, and mixed currency are reported."""
    frame = pd.DataFrame(
        {
            "Date": ["", "2026-03-04", "2026-03-04", "2026-03-05", "2026-03-06"],
            "Amount": ["1.00", "nope", "0", "2.00", "3.00"],
            "Currency": ["USD", "USD", "USD", "USD", "EUR"],
        }
    )
    column_map = ColumnMap(date="Date", amount="Amount", currency="Currency")

    result = normalize_frame(frame, Source.BANK, column_map, _settings())

    assert result.transactions[0].id == "B-000004"
    assert [issue.code for issue in result.issues] == [
        "missing_or_invalid_date",
        "unparsable_amount",
        "zero_amount",
        "mixed_currency",
    ]


def test_missing_currency_uses_configured_default() -> None:
    """Rows without a currency column receive the configured run currency."""
    frame = pd.DataFrame({"Date": ["2026-03-04"], "Amount": ["1.00"]})
    column_map = ColumnMap(date="Date", amount="Amount")

    result = normalize_frame(frame, Source.BANK, column_map, _settings(default_currency="CAD"))

    assert result.transactions[0].currency == "CAD"
