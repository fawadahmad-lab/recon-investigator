"""Description normalization for deterministic fuzzy comparison inputs."""

from __future__ import annotations

import re
from math import isnan


def normalize_text(value: object) -> str:
    """Lowercase text, remove punctuation and long numeric noise, and collapse spaces."""
    if value is None or (isinstance(value, float) and isnan(value)):
        return ""
    text = str(value).lower()
    text = re.sub(r"\b\d{4,}\b", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())
