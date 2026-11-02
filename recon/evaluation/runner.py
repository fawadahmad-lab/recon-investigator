"""Deterministic evaluation of the shipped pipeline against synthetic ground truth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from recon.config import Settings, get_settings
from recon.evaluation.metrics import (
    FindingRecord,
    cause_accuracy,
    match_pair_metrics,
    per_type_metrics,
    verifier_stats,
)
from recon.llm.base import LLMProvider, build_provider
from recon.matching.engine import run_pipeline
from recon.models import Finding
from recon.synth.generator import generate_dataset

DETERMINISTIC_LLM = "disabled"
CANONICAL_PROVIDERS = ("none", "mock")


def _record(kind: str, ledger_ids: list[str], bank_ids: list[str], cause: str) -> FindingRecord:
    """Create a predicted finding record for metric and cause comparison."""
    record: FindingRecord = {"type": kind, "ledger_ids": ledger_ids, "bank_ids": bank_ids}
    if cause:
        record["likely_cause"] = cause
    return record


def _load_truth(path: Path) -> dict[str, Any]:
    """Read generated ground truth JSON using explicit UTF-8."""
    return json.loads(path.read_text(encoding="utf-8"))


def _predictions(findings: Sequence[Finding]) -> list[FindingRecord]:
    """Convert run findings into the metric record shape in run order."""
    return [
        _record(
            str(finding.type),
            sorted(finding.ledger_ids),
            sorted(finding.bank_ids),
            finding.explanation.likely_cause if finding.explanation is not None else "",
        )
        for finding in findings
    ]


def _resolve_provider(llm: str, settings: Settings) -> tuple[LLMProvider | None, str]:
    """Build the named provider; `none` runs the deterministic pipeline only."""
    if llm == "none":
        return None, DETERMINISTIC_LLM
    return build_provider(settings, llm), llm


def _output_name(profile: str, seed: int, llm: str) -> str:
    """Name the metrics file, keeping the documented name for the canonical providers."""
    suffix = "" if llm in CANONICAL_PROVIDERS else f"_{llm}"
    return f"eval_{profile}_{seed}{suffix}.json"


def run_evaluation(
    profile: str,
    seed: int,
    reports_dir: Path,
    data_dir: Path,
    llm: str = "mock",
    settings: Settings | None = None,
) -> Path:
    """Generate a dataset, run the pipeline, and write metrics JSON.

    With a provider the run also scores explanation causes and reports the verifier
    outcome per packet; the matching metrics are identical either way because the
    LLM never changes a finding.
    """
    config = settings or get_settings()
    provider, provider_label = _resolve_provider(llm, config)
    dataset_dir = generate_dataset(profile, seed, data_dir / f"{profile}_{seed}")
    truth = _load_truth(dataset_dir / "ground_truth.json")
    result = run_pipeline(
        dataset_dir / "bank.csv", dataset_dir / "ledger.csv", config, provider=provider
    )
    expected_findings = [*truth["matches"], *truth["expected"]]
    predictions = _predictions(result.findings)
    report: dict[str, Any] = {
        "llm": provider_label,
        "match_pair": match_pair_metrics(
            [item for item in predictions if item["type"].startswith("match_")], truth["matches"]
        ),
        "per_type": per_type_metrics(predictions, expected_findings),
        "profile": profile,
        "rows": {"bank": len(result.bank), "ledger": len(result.ledger)},
        "seed": seed,
        "tier": "R1-R7",
        "validation_issues": len(result.issues),
    }
    if provider is not None:
        report["cause_accuracy"] = cause_accuracy(predictions, truth["expected"])
        report["verifier"] = verifier_stats(
            result.verifier_records, provider.name, provider.model_name
        )
    reports_dir.mkdir(parents=True, exist_ok=True)
    output_path = reports_dir / _output_name(profile, seed, llm)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def run_evaluations(
    profiles: list[str],
    seeds: list[int],
    reports_dir: Path,
    data_dir: Path,
    llm: str = "mock",
    settings: Settings | None = None,
) -> list[Path]:
    """Run a stable profile-major sequence of evaluation jobs for one provider."""
    return [
        run_evaluation(profile, seed, reports_dir, data_dir, llm=llm, settings=settings)
        for profile in profiles
        for seed in seeds
    ]
