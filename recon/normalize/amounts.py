"""Decimal-based normalization of signed and debit-credit statement amounts."""

from __future__ import annotations

import re
from decimal import InvalidOperation
from math import isnan

from recon.models import to_minor


def _is_blank(value: object) -> bool:
    """Return whether a scalar money cell is absent."""
    return (
        value is None
        or (isinstance(value, str) and not value.strip())
        or (isinstance(value, float) and isnan(value))
    )


def _clean_amount(value: object) -> str:
    """Produce a Decimal-compatible amount string from a statement cell."""
    if _is_blank(value):
        raise ValueError("amount is missing")
    text = str(value).strip()
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = re.sub(r"[^0-9,\.\-+]", "", text).replace(",", "")
    if not text or text in {"+", "-", "."}:
        raise ValueError("amount is missing or invalid")
    return f"-{text}" if negative and not text.startswith("-") else text


def parse_amount(value: object) -> int:
    """Parse a signed statement amount into integer minor units using Decimal."""
    try:
        return to_minor(_clean_amount(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"unparsable amount: {value}") from error


def parse_debit_credit(debit: object, credit: object) -> int:
    """Combine debit and credit cells into one signed integer minor amount."""
    debit_minor = 0 if _is_blank(debit) else abs(parse_amount(debit))
    credit_minor = 0 if _is_blank(credit) else abs(parse_amount(credit))
    if debit_minor == 0 and credit_minor == 0:
        raise ValueError("amount is missing")
    return credit_minor - debit_minor
