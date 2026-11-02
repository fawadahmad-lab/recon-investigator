"""Tests for deterministic finding and match-pair metrics."""

import pytest

from recon.evaluation.metrics import match_pair_metrics, per_type_metrics


def _finding(kind: str, ledger_id: str, bank_id: str) -> dict[str, object]:
    """Create a concise labeled finding fixture."""
    return {"type": kind, "ledger_ids": [ledger_id], "bank_ids": [bank_id]}


def test_per_type_metrics_on_hand_built_cases() -> None:
    """Metrics calculate true positives, false positives, and false negatives exactly."""
    expected = [
        _finding("match_exact", "L-1", "B-1"),
        _finding("amount_mismatch", "L-2", "B-2"),
    ]
    predicted = [
        _finding("match_exact", "L-1", "B-1"),
        _finding("match_exact", "L-3", "B-3"),
    ]

    metrics = per_type_metrics(predicted, expected)

    assert metrics["match_exact"] == {
        "tp": 1,
        "fp": 1,
        "fn": 0,
        "precision": 0.5,
        "recall": 1.0,
        "f1": pytest.approx(2 / 3),
    }
    assert metrics["amount_mismatch"]["fn"] == 1
    assert metrics["overall"]["tp"] == 1
    assert metrics["overall"]["fp"] == 1
    assert metrics["overall"]["fn"] == 1


def test_match_pair_metrics_ignore_match_label() -> None:
    """Pair accuracy recognizes the same source IDs despite different match tiers."""
    expected = [_finding("match_fuzzy", "L-1", "B-1")]
    predicted = [_finding("match_exact", "L-1", "B-1")]

    metrics = match_pair_metrics(predicted, expected)

    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
