"""Row-level validation helpers for normalized transactions."""

from __future__ import annotations

from math import isnan
from typing import Any

from recon.models import Source, ValidationIssue


def raw_text(value: object) -> str:
    """Convert an optional scalar to a stripped display string."""
    if value is None or (isinstance(value, float) and isnan(value)):
        return ""
    return str(value).strip()


def normalize_currency(value: object, default_currency: str) -> str:
    """Return an uppercase currency code, defaulting absent values."""
    return raw_text(value).upper() or default_currency.upper()


def validation_issue(
    source: Source, row_number: int, code: str, message: str, raw: dict[str, Any]
) -> ValidationIssue:
    """Create a consistently shaped row-level validation issue."""
    return ValidationIssue(
        source=source,
        row_number=row_number,
        code=code,
        message=message,
        raw=raw,
    )
