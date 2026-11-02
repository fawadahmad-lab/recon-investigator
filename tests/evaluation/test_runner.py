"""Tests for evaluation-report generation, including the explanation stage."""

import json
from pathlib import Path

from recon.evaluation.runner import run_evaluation, run_evaluations


def _report(path: Path) -> dict:
    """Read a saved evaluation report."""
    return json.loads(path.read_text(encoding="utf-8"))


def test_full_tier_evaluation_reports_split_recall_and_remaining_gaps(tmp_path: Path) -> None:
    """R1-R7 reports score every implemented rule and retain unmet recall."""
    output = run_evaluation("realistic", 42, tmp_path / "reports", tmp_path / "data", llm="none")
    report = _report(output)

    assert output.name == "eval_realistic_42.json"
    assert report["tier"] == "R1-R7"
    assert report["llm"] == "disabled"
    assert "cause_accuracy" not in report
    assert "verifier" not in report
    assert report["per_type"]["fee_difference"]["recall"] > 0.0
    assert report["per_type"]["match_fuzzy"]["recall"] > 0.0
    assert report["per_type"]["amount_mismatch"]["recall"] > 0.0
    assert report["per_type"]["date_mismatch"]["recall"] > 0.0
    assert report["per_type"]["match_split"]["recall"] > 0.0
    assert report["per_type"]["ambiguous_split"]["precision"] > 0.0
    assert report["per_type"]["overall"]["recall"] < 1.0


def test_mock_evaluation_scores_causes_and_the_verifier(tmp_path: Path) -> None:
    """A provider run adds cause accuracy and one verifier line per packet."""
    output = run_evaluation("easy", 1, tmp_path / "reports", tmp_path / "data")
    report = _report(output)
    cause = report["cause_accuracy"]
    verifier = report["verifier"]

    assert output.name == "eval_easy_1.json"
    assert report["llm"] == "mock"
    assert report["rows"]["bank"] > 100 and report["rows"]["ledger"] > 100
    assert cause["scored"] == cause["correct"] > 0
    assert set(cause["by_type"]) <= set(report["per_type"])
    assert verifier["provider"] == "mock"
    assert verifier["packets"] == cause["scored"]
    assert verifier["pass_first_try"] == verifier["packets"]
    assert verifier["fallback"] == 0
    assert verifier["catch_rate"] == 0.0


def test_matching_metrics_are_identical_with_and_without_a_provider(tmp_path: Path) -> None:
    """The explanation stage cannot move a metric: the core principle, asserted."""
    plain = _report(run_evaluation("easy", 1, tmp_path / "a", tmp_path / "d1", llm="none"))
    explained = _report(run_evaluation("easy", 1, tmp_path / "b", tmp_path / "d2", llm="mock"))

    assert plain["per_type"] == explained["per_type"]
    assert plain["match_pair"] == explained["match_pair"]
    assert plain["validation_issues"] == explained["validation_issues"]
    assert plain["llm"] == "disabled" and explained["llm"] == "mock"


def test_faulty_mock_evaluation_reports_the_catch_rate(tmp_path: Path) -> None:
    """Injected faults are named in the file name and measured in the verifier block."""
    output = run_evaluation("easy", 1, tmp_path / "reports", tmp_path / "data", llm="faulty_mock")
    verifier = _report(output)["verifier"]

    assert output.name == "eval_easy_1_faulty_mock.json"
    assert verifier["provider"] == "faulty_mock"
    assert verifier["pass_first_try"] == 0
    assert verifier["pass_after_retry"] == verifier["packets"]
    assert verifier["catch_rate"] == 1.0


def test_evaluations_run_a_stable_profile_major_grid(tmp_path: Path) -> None:
    """The grid writes one file per profile and seed in the documented order."""
    outputs = run_evaluations(["easy", "realistic"], [1, 2], tmp_path, tmp_path / "data")

    assert [path.name for path in outputs] == [
        "eval_easy_1.json",
        "eval_easy_2.json",
        "eval_realistic_1.json",
        "eval_realistic_2.json",
    ]
