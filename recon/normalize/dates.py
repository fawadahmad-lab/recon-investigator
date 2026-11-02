"""Date parsing for common statement formats and Excel serial values."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import isnan

EXCEL_EPOCH = date(1899, 12, 30)
DAYFIRST_FORMATS = ("%d/%m/%Y", "%m/%d/%Y")
MONTHFIRST_FORMATS = ("%m/%d/%Y", "%d/%m/%Y")
UNAMBIGUOUS_FORMATS = ("%Y-%m-%d", "%d-%b-%Y", "%d %b %Y")


def _is_blank(value: object) -> bool:
    """Return whether a scalar value is absent."""
    return (
        value is None
        or (isinstance(value, str) and not value.strip())
        or (isinstance(value, float) and isnan(value))
    )


def _excel_serial(value: int | float | Decimal) -> date:
    """Convert an Excel day serial to a date without float date arithmetic."""
    serial = Decimal(str(value))
    if serial < 1:
        raise ValueError("Excel date serial must be positive")
    days = int(serial)
    epoch = date(1899, 12, 31) if days < 60 else EXCEL_EPOCH
    return epoch + timedelta(days=days)


def parse_date(value: object, dayfirst: bool = False) -> date:
    """Parse a supported date value or raise ValueError with a clear reason."""
    if _is_blank(value):
        raise ValueError("date is missing")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        try:
            return _excel_serial(value)
        except (InvalidOperation, OverflowError) as error:
            raise ValueError("date is not a valid Excel serial") from error
    text = str(value).strip()
    for date_format in (
        *UNAMBIGUOUS_FORMATS,
        *(DAYFIRST_FORMATS if dayfirst else MONTHFIRST_FORMATS),
    ):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date: {text}")
