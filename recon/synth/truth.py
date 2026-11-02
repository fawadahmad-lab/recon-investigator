"""Stable serialization for synthetic generation ground truth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_ground_truth(path: Path, ground_truth: dict[str, Any]) -> None:
    """Write sorted, UTF-8 ground truth JSON with a deterministic newline."""
    path.write_text(
        json.dumps(ground_truth, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
