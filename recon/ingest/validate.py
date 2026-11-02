"""File-level validation for supported reconciliation inputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from recon.errors import IngestError

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50_000
SUPPORTED_SUFFIXES = {".csv", ".xlsx"}


def validate_file(path: Path) -> Path:
    """Validate that an input path is a non-empty supported file within limits."""
    if not path.exists() or not path.is_file():
        raise IngestError(f"input file does not exist: {path}")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise IngestError("input file must be a CSV or single-sheet XLSX file")
    size = path.stat().st_size
    if size == 0:
        raise IngestError("input file is empty")
    if size > MAX_FILE_SIZE_BYTES:
        raise IngestError(f"input file exceeds the {MAX_FILE_SIZE_BYTES} byte limit")
    return path


def validate_row_count(frame: pd.DataFrame) -> None:
    """Enforce the maximum supported input row count."""
    if frame.empty:
        raise IngestError("input file contains no data rows")
    if len(frame.index) > MAX_ROWS:
        raise IngestError(f"input file exceeds the {MAX_ROWS} row limit")
