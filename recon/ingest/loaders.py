"""CSV and single-sheet XLSX ingestion with deterministic mapping."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import pandas as pd

from recon.errors import IngestError
from recon.ingest.column_map import ColumnMap, detect_column_map
from recon.ingest.validate import validate_file, validate_row_count

LOGGER = logging.getLogger(__name__)
CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252")


@dataclass(frozen=True)
class IngestedFile:
    """Raw file contents and the canonical mapping detected for them."""

    path: Path
    frame: pd.DataFrame
    column_map: ColumnMap


def _read_csv(path: Path) -> pd.DataFrame:
    """Read CSV data with BOM handling, encoding fallback, and delimiter sniffing."""
    encoding_error: UnicodeDecodeError | None = None
    for encoding in CSV_ENCODINGS:
        try:
            return pd.read_csv(path, dtype=object, encoding=encoding, sep=None, engine="python")
        except UnicodeDecodeError as error:
            encoding_error = error
    raise IngestError(f"could not decode CSV file: {path.name}") from encoding_error


def _read_xlsx(path: Path) -> pd.DataFrame:
    """Read a single-sheet XLSX file and reject workbooks with multiple sheets."""
    try:
        workbook = pd.ExcelFile(path)
    except (OSError, ValueError) as error:
        raise IngestError(f"could not read XLSX file: {path.name}") from error
    if len(workbook.sheet_names) != 1:
        raise IngestError("XLSX input must contain exactly one sheet")
    return pd.read_excel(workbook, sheet_name=workbook.sheet_names[0], dtype=object)


def load_file(path: Path, column_map: Mapping[str, str] | None = None) -> IngestedFile:
    """Load a supported input file, enforce limits, and detect its column mapping."""
    input_path = validate_file(path)
    try:
        frame = (
            _read_csv(input_path) if input_path.suffix.lower() == ".csv" else _read_xlsx(input_path)
        )
    except pd.errors.EmptyDataError as error:
        raise IngestError("input file is empty") from error
    except pd.errors.ParserError as error:
        raise IngestError(f"could not parse input file: {input_path.name}") from error
    validate_row_count(frame)
    headers = [str(header) for header in frame.columns]
    mapping = detect_column_map(headers, column_map)
    LOGGER.info("ingest_loaded file=%s rows=%d", input_path.name, len(frame.index))
    return IngestedFile(path=input_path, frame=frame, column_map=mapping)
