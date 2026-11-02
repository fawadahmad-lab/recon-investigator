"""End-to-end coverage: generate, run, report, evaluate and aggregate."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

from recon import cli
from recon.config import get_settings
from recon.evaluation.runner import run_evaluation
from recon.llm.base import build_provider
from recon.matching.engine import run_pipeline
from recon.report.builder import write_run_artifacts
from recon.synth.generator import generate_dataset

ARTIFACT_NAMES = (
    "audit_trail.jsonl",
    "findings.json",
    "report.html",
    "run_meta.json",
    "verifier_log.jsonl",
)


def _read(path: Path) -> Any:
    """Read a saved JSON document."""
    return json.loads(path.read_text(encoding="utf-8"))


def _findings(path: Path) -> list[dict[str, Any]]:
    """Read the findings document as a list."""
    payload = _read(path)
    return payload["findings"] if isinstance(payload, dict) else payload


def test_generate_run_report_and_evaluate_agree(tmp_path: Path) -> None:
    """One dataset drives the pipeline, the report and the scorer to the same count."""
    settings = replace(get_settings(), llm_provider="mock", llm_api_key=None)
    dataset = generate_dataset("easy", 1, tmp_path / "data")
    result = run_pipeline(
        dataset / "bank.csv",
        dataset / "ledger.csv",
        settings,
        provider=build_provider(settings, "mock"),
    )
    artifacts = write_run_artifacts(tmp_path / "run", result)
    report = _read(
        run_evaluation("easy", 1, tmp_path / "eval", tmp_path / "data", settings=settings)
    )
    findings = _findings(tmp_path / "run" / "findings.json")

    assert {path.name for path in artifacts} == set(ARTIFACT_NAMES)
    assert (tmp_path / "run" / "report.html").read_text(encoding="utf-8").count("<article") == len(
        [item for item in findings if item["status"] != "matched"]
    )
    predicted = sum(
        block["tp"] + block["fp"] for name, block in report["per_type"].items() if name != "overall"
    )
    assert predicted == len(findings) == len(result.findings)
    discrepancies = [
        item
        for item in findings
        if item["status"] != "matched" and item["type"] != "invalid_record"
    ]
    assert report["verifier"]["packets"] == len(discrepancies)
    assert 0 < report["cause_accuracy"]["scored"] <= len(discrepancies)
    assert {item["explanation"]["explanation_source"] for item in findings} == {
        "ai_verified",
        "deterministic_fallback",
    }


def test_demo_command_finishes_under_a_minute_offline(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`demo` generates, runs, explains and writes the report without the network."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["recon", "demo", "--profile", "easy", "--seed", "1"])
    started = time.monotonic()
    cli.main()
    elapsed = time.monotonic() - started
    printed = capsys.readouterr().out

    assert elapsed < 60
    assert {path.name for path in (tmp_path / "reports" / "demo").iterdir()} == set(ARTIFACT_NAMES)
    assert "report: reports/demo/report.html" in printed
    assert "llm=mock" in printed
    assert "data/synthetic" not in printed


def test_eval_command_writes_the_grid_and_the_aggregate(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`eval` saves one JSON per cell and aggregates them into `final_eval.md`."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["recon", "eval", "--profiles", "easy", "--seeds", "1", "2", "--llm", "mock"],
    )
    cli.main()
    printed = capsys.readouterr().out
    markdown = (tmp_path / "reports" / "final_eval.md").read_text(encoding="utf-8")
    blocks = [
        _read(tmp_path / "reports" / f"eval_easy_{seed}.json")["per_type"]["overall"]
        for seed in (1, 2)
    ]
    totals = " | ".join(str(sum(block[field] for block in blocks)) for field in ("tp", "fp", "fn"))

    assert Path("reports/eval_easy_1.json").exists() and Path("reports/eval_easy_2.json").exists()
    assert printed.strip().endswith("reports/final_eval.md")
    assert f"| overall | {totals} |" in markdown
    assert "## Provider `mock`" in markdown
