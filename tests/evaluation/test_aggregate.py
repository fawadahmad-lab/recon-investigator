"""Tests for the final evaluation aggregate built from saved JSON files."""

import json
from pathlib import Path
from typing import Any

from recon.evaluation.aggregate import write_final_eval


def _score(tp: int, fp: int, fn: int) -> dict[str, Any]:
    """Build one confusion block the way the evaluation runner saves it."""
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def _report(
    llm: str, profile: str = "easy", seed: int = 1, tp: int = 10, fp: int = 1, fn: int = 4
) -> dict[str, Any]:
    """Build a minimal saved evaluation report."""
    scored = tp + fp
    return {
        "cause_accuracy": {
            "accuracy": 1.0,
            "by_type": {"missing_in_bank": {"correct": scored, "scored": scored}},
            "correct": scored,
            "scored": scored,
        },
        "llm": llm,
        "match_pair": _score(tp, fp, fn),
        "per_type": {
            "missing_in_bank": _score(tp, fp, fn),
            "overall": _score(tp * 2, fp, fn),
        },
        "profile": profile,
        "rows": {"bank": 234, "ledger": 228},
        "seed": seed,
        "tier": "R1-R7",
        "validation_issues": 0,
        "verifier": {
            "catch_rate": 0.0,
            "fallback": 0,
            "model": llm,
            "packets": scored,
            "pass_after_retry": 0,
            "pass_first_try": scored,
            "provider": llm,
            "provider_errors": 0,
            "rejected_answers": 0,
            "rejected_first_try": 0,
        },
    }


def _write(reports_dir: Path, name: str, report: dict[str, Any]) -> Path:
    """Save one evaluation report under its documented name."""
    path = reports_dir / name
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def test_aggregate_lists_every_grid_file_and_groups_by_provider(tmp_path: Path) -> None:
    """Offline reference providers are listed before any real provider."""
    grid = [
        _write(tmp_path, "eval_easy_1.json", _report("mock")),
        _write(tmp_path, "eval_easy_1_faulty_mock.json", _report("faulty_mock")),
        _write(tmp_path, "eval_easy_1_groq.json", _report("groq")),
    ]
    text = write_final_eval(tmp_path, grid).read_text(encoding="utf-8")

    assert "`eval_easy_1.json`, `eval_easy_1_faulty_mock.json`, `eval_easy_1_groq.json`" in text
    assert text.index("## Provider `mock`") < text.index("## Provider `faulty_mock`")
    assert text.index("## Provider `faulty_mock`") < text.index("## Provider `groq`")
    assert text.count("## Provider") == 3


def test_ratios_are_micro_averaged_over_the_runs_of_a_section(tmp_path: Path) -> None:
    """Confusion counts are summed before precision, recall and F1 are taken."""
    first = _write(tmp_path, "eval_easy_1.json", _report("mock", tp=10, fp=1, fn=4))
    _write(tmp_path, "eval_easy_2.json", _report("mock", seed=2, tp=5, fp=2, fn=1))
    text = write_final_eval(tmp_path, [first, tmp_path / "eval_easy_2.json"]).read_text(
        encoding="utf-8"
    )

    assert "| overall | 30 | 3 | 5 | 0.909 | 0.857 | 0.882 |" in text
    assert "| missing_in_bank | 15 | 3 | 5 | 0.833 | 0.750 | 0.789 |" in text


def test_cause_and_verifier_numbers_come_from_the_saved_files(tmp_path: Path) -> None:
    """The provider tables repeat the JSON numbers instead of recomputing them."""
    grid = [_write(tmp_path, "eval_easy_1.json", _report("mock", tp=7, fp=0, fn=0))]
    faulty = _report("faulty_mock", tp=7, fp=0, fn=0)
    _write(
        tmp_path,
        "eval_easy_1_faulty_mock.json",
        {
            **faulty,
            "verifier": {
                **faulty["verifier"],
                "catch_rate": 1.0,
                "pass_after_retry": 7,
                "pass_first_try": 0,
                "rejected_answers": 7,
                "rejected_first_try": 7,
            },
        },
    )
    text = write_final_eval(tmp_path, grid).read_text(encoding="utf-8")

    assert "| missing_in_bank | 7 | 7 | 1.000 |" in text
    assert "| 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0.000 |" in text
    assert "| 7 | 0 | 7 | 0 | 0 | 7 | 7 | 1.000 |" in text


def test_only_the_requested_grid_cells_are_aggregated(tmp_path: Path) -> None:
    """A saved run outside the grid cannot add its numbers to the tables."""
    outside = _write(tmp_path, "eval_realistic_42.json", _report("mock", "realistic", 42, tp=999))
    grid = [_write(tmp_path, "eval_easy_1.json", _report("mock"))]
    text = write_final_eval(tmp_path, grid).read_text(encoding="utf-8")

    assert "eval_realistic_42" not in text
    assert "| overall | 20 | 1 | 4 |" in text
    assert outside.exists()


def test_aggregate_is_reproducible_and_free_of_placeholders(tmp_path: Path) -> None:
    """Two builds of the same inputs are byte-identical and carry no template text."""
    grid = [_write(tmp_path, "eval_easy_1.json", _report("mock"))]
    first = write_final_eval(tmp_path, grid).read_text(encoding="utf-8")
    second = write_final_eval(tmp_path, grid).read_text(encoding="utf-8")

    assert first == second
    assert "## Limitations" in first
    for marker in ("TODO", "TBD", "{{", "AGENT:", "placeholder"):
        assert marker not in first


def test_profile_tables_are_rendered_inside_a_provider_section(tmp_path: Path) -> None:
    """Single-profile figures exist, so the write-up can cite them."""
    grid = [
        _write(tmp_path, "eval_easy_1.json", _report("mock", tp=10, fp=1, fn=4)),
        _write(
            tmp_path,
            "eval_realistic_1.json",
            _report("mock", "realistic", 1, tp=40, fp=2, fn=8),
        ),
    ]
    text = write_final_eval(tmp_path, grid).read_text(encoding="utf-8")

    assert "### Per-type metrics by profile" in text
    assert "`easy` (seeds 1):" in text and "`realistic` (seeds 1):" in text
    assert "| overall | 100 | 3 | 12 |" in text
    assert "| missing_in_bank | 10 | 1 | 4 |" in text
    assert "| missing_in_bank | 40 | 2 | 8 |" in text


def test_deterministic_section_has_no_explanation_tables(tmp_path: Path) -> None:
    """A run without a provider contributes no cause or verifier columns."""
    report = {
        key: value
        for key, value in _report("disabled").items()
        if key not in ("cause_accuracy", "verifier")
    }
    grid = [_write(tmp_path, "eval_easy_1.json", report)]
    text = write_final_eval(tmp_path, grid).read_text(encoding="utf-8")

    assert "### Cause accuracy" not in text
    assert "### Verifier statistics" not in text
    assert "Deterministic pipeline run" in text
