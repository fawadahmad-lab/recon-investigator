"""Reference normalization for deterministic transaction matching."""

from __future__ import annotations

import re
from math import isnan

PREFIX_PATTERN = re.compile(r"^(?:REF|INV|PAYMENT|TRF)[\s\-_]*", re.IGNORECASE)


def _as_text(value: object) -> str:
    """Convert an optional scalar input to a stripped string."""
    if value is None or (isinstance(value, float) and isnan(value)):
        return ""
    return str(value).strip()


def normalize_reference(value: object) -> str:
    """Normalize a reference while retaining an empty result for absent values."""
    reference = _as_text(value).upper()
    while PREFIX_PATTERN.match(reference):
        reference = PREFIX_PATTERN.sub("", reference, count=1)
    return re.sub(r"[\s\-_]", "", reference)
