"""Tests for input-file loading and column mapping."""

from pathlib import Path

import pandas as pd
import pytest

from recon.errors import IngestError, MappingError
from recon.ingest.loaders import load_file
from recon.ingest.validate import MAX_FILE_SIZE_BYTES


def _write_csv(path: Path, text: str, encoding: str = "utf-8") -> Path:
    """Write a CSV fixture with explicit encoding."""
    path.write_text(text, encoding=encoding)
    return path


def test_loads_synonym_headers_with_utf8_bom(tmp_path: Path) -> None:
    """A BOM-prefixed CSV uses source headers while exposing canonical mapping."""
    path = _write_csv(
        tmp_path / "bank.csv",
        "Transaction Date,Net Amount,Ref,Details,Curr,Merchant\n"
        "2026-01-01,12.50,A1,Coffee,USD,Shop\n",
        encoding="utf-8-sig",
    )

    ingested = load_file(path)

    assert ingested.frame.iloc[0]["Net Amount"] == "12.50"
    assert ingested.column_map.as_dict() == {
        "date": "Transaction Date",
        "amount": "Net Amount",
        "debit": None,
        "credit": None,
        "reference": "Ref",
        "description": "Details",
        "currency": "Curr",
        "counterparty": "Merchant",
    }


def test_loads_semicolon_csv_with_debit_credit_columns(tmp_path: Path) -> None:
    """Delimiter sniffing supports separate debit and credit input columns."""
    path = _write_csv(
        tmp_path / "ledger.csv",
        "Posting Date;Debit;Credit;Narrative\n2026-01-01;12.50;;Office supplies\n",
    )

    ingested = load_file(path)

    assert ingested.column_map.date == "Posting Date"
    assert ingested.column_map.debit == "Debit"
    assert ingested.column_map.credit == "Credit"
    assert ingested.column_map.amount is None


def test_manual_column_map_overrides_auto_detection(tmp_path: Path) -> None:
    """A manual map can supply nonstandard required source headers."""
    path = _write_csv(tmp_path / "custom.csv", "When,ValueX\n2026-01-01,14.00\n")

    ingested = load_file(path, {"date": "When", "amount": "ValueX"})

    assert ingested.column_map.date == "When"
    assert ingested.column_map.amount == "ValueX"


def test_loads_single_sheet_xlsx(tmp_path: Path) -> None:
    """A single-sheet workbook is read with the same mapping behavior as CSV."""
    path = tmp_path / "statement.xlsx"
    pd.DataFrame({"Date": ["2026-01-01"], "Amount": ["9.99"]}).to_excel(path, index=False)

    ingested = load_file(path)

    assert len(ingested.frame.index) == 1
    assert ingested.column_map.amount == "Amount"


def test_empty_file_has_clear_error(tmp_path: Path) -> None:
    """Zero-byte files are rejected before parsing."""
    path = tmp_path / "empty.csv"
    path.touch()

    with pytest.raises(IngestError, match="empty"):
        load_file(path)


def test_missing_required_columns_lists_headers(tmp_path: Path) -> None:
    """Mapping errors include the available source headers for remediation."""
    path = _write_csv(tmp_path / "missing.csv", "Description,Currency\nCoffee,USD\n")

    with pytest.raises(MappingError, match="Headers found: Description, Currency"):
        load_file(path)


def test_oversize_file_is_rejected(tmp_path: Path) -> None:
    """The configured 10 MB file limit is enforced before parsing."""
    path = tmp_path / "too-large.csv"
    path.write_bytes(b"x" * (MAX_FILE_SIZE_BYTES + 1))

    with pytest.raises(IngestError, match="exceeds"):
        load_file(path)
