"""Aggregate saved evaluation JSON files into the project's final evaluation report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from recon.evaluation.metrics import derived_metrics

FINAL_EVAL_NAME = "final_eval.md"
REFERENCE_PROVIDERS = ("mock", "faulty_mock", "disabled")
PROVIDER_NOTES = {
    "mock": "Offline template provider (the shipped default).",
    "faulty_mock": "Offline provider that injects a fault into every packet to measure "
    "the verifier.",
    "disabled": "Deterministic pipeline run with no explanation stage.",
}
SCORE_FIELDS = ("tp", "fp", "fn")
SCORE_HEADER = ("Type", "TP", "FP", "FN", "Precision", "Recall", "F1")
VERIFIER_HEADER = (
    "Packets",
    "Pass first try",
    "Pass after retry",
    "Fallback",
    "Provider errors",
    "Rejected first answers",
    "Rejected answers",
    "Catch rate",
)
VERIFIER_FIELDS = (
    "packets",
    "pass_first_try",
    "pass_after_retry",
    "fallback",
    "provider_errors",
    "rejected_first_try",
    "rejected_answers",
)
LIMITATIONS = (
    "Every metric comes from synthetic data: no real bank or ledger file has been "
    "evaluated, and one currency per run is assumed.",
    "A predicted finding is correct only when its type and its full set of record IDs "
    "equal a labelled entry, so a re-grouped but equivalent pair counts as both a false "
    "positive and a false negative. The `realistic` and `hard` profiles inject "
    "legitimate repeated payments as decoys, and each decoy group is two byte-identical "
    "rows, so part of the `match_exact` error is unavoidable ID ambiguity rather than a "
    "matching mistake (documented under Open questions in `docs/Memory.md`).",
    "Single-character reference noise normalizes to a similarity of 0.875, below the "
    "`REF_STRONG` threshold of 0.90, so those labelled mismatches stay unmatched and "
    "appear as `missing_in_*` false positives. Lowering the threshold was measured and "
    "rejected on precision grounds; see the Bug log in `docs/Memory.md` (T11).",
    "`mock` is a deterministic template provider: it proves the packet, verifier and "
    "report plumbing end to end, and its cause accuracy measures that pipeline rather "
    "than a language model. A real provider is reported in its own section and only "
    "when an API key is configured. Cause labels are single-valued in the ground truth "
    "(each injected discrepancy carries exactly one cause), so a real model that names "
    "a different but plausible cause is counted wrong, and its cause accuracy is a "
    "lower bound rather than an error rate.",
    "The catch rate is the share of first answers the verifier rejected. With "
    "`faulty_mock` every packet carries an injected fault, so 1.000 there means every "
    "injected fault was caught; a clean provider returns 0.000 by construction. Cause "
    "accuracy is measured on the accepted answer only, so an explanation corrected on "
    "retry scores the same as one accepted immediately.",
    "The split search is bounded by the pool and node-budget thresholds in "
    "`recon/config.py`: an ambiguous or truncated anchor is reported as such instead of "
    "guessed, so those cases stay recall gaps by design.",
)


def _load(path: Path) -> dict[str, Any]:
    """Read one saved evaluation report."""
    return json.loads(path.read_text(encoding="utf-8"))


def _reports(runs: Sequence[tuple[Path, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Return the loaded payloads of grouped runs."""
    return [report for _, report in runs]


def _block(report: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    """Return one report's score block, or an empty mapping when it has none."""
    value = report.get(key)
    return value if isinstance(value, dict) else {}


def _total(blocks: Sequence[dict[str, Any]], field: str) -> int:
    """Total one integer field over score blocks, treating a missing key as zero."""
    return sum(int(block.get(field, 0)) for block in blocks)


def _ratio(count: int, total: int) -> str:
    """Render a share with the three decimals used in the saved JSON files."""
    return f"{count / total:.3f}" if total else "0.000"


def _score_row(label: str, blocks: Sequence[dict[str, Any]]) -> list[str]:
    """Micro-average score blocks over runs into one table row."""
    metrics = derived_metrics(*[_total(blocks, field) for field in SCORE_FIELDS])
    return [
        label,
        str(metrics["tp"]),
        str(metrics["fp"]),
        str(metrics["fn"]),
        f"{metrics['precision']:.3f}",
        f"{metrics['recall']:.3f}",
        f"{metrics['f1']:.3f}",
    ]


def _score_rows(
    runs: Sequence[tuple[Path, dict[str, Any]]], key: str, total: str
) -> list[list[str]]:
    """Render the per-type table for one score block across the grouped runs."""
    reports = _reports(runs)
    names = sorted({name for report in reports for name in _block(report, key)} - {"overall"})
    rows = [
        _score_row(
            name,
            [_block(report, key)[name] for report in reports if name in _block(report, key)],
        )
        for name in names
    ]
    overall = [
        block["overall"]
        for block in (_block(report, key) for report in reports)
        if "overall" in block
    ]
    return rows + [_score_row(total, overall)] if overall else rows


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    """Render a markdown table with right-aligned numeric columns."""
    lines = ["| " + " | ".join(header) + " |", "|---" + "|---:" * (len(header) - 1) + "|"]
    return lines + ["| " + " | ".join(row) + " |" for row in rows]


def _runs_line(reports: Sequence[dict[str, Any]]) -> str:
    """Describe the grid cells and row volume a section aggregates."""
    cells = ", ".join(f"{report['profile']} seed {report['seed']}" for report in reports)
    ledger = _total([report.get("rows", {}) for report in reports], "ledger")
    bank = _total([report.get("rows", {}) for report in reports], "bank")
    rows = f", {ledger:,} ledger and {bank:,} bank rows" if ledger or bank else ""
    return f"Runs: {len(reports)} ({cells}{rows}). Tier: R1-R7."


def _cause_rows(runs: Sequence[tuple[Path, dict[str, Any]]]) -> list[list[str]]:
    """Render cause accuracy per type plus the combined total."""
    blocks = [_block(report, "cause_accuracy") for report in _reports(runs)]
    names = sorted({name for block in blocks for name in block.get("by_type", {})})
    rows = []
    for name in names:
        cells = [block["by_type"][name] for block in blocks if name in block.get("by_type", {})]
        scored, correct = _total(cells, "scored"), _total(cells, "correct")
        rows.append([name, str(scored), str(correct), _ratio(correct, scored)])
    scored, correct = _total(blocks, "scored"), _total(blocks, "correct")
    rows.append(["all types", str(scored), str(correct), _ratio(correct, scored)])
    return rows


def _verifier_rows(runs: Sequence[tuple[Path, dict[str, Any]]]) -> list[list[str]]:
    """Render the verifier totals and the derived catch rate."""
    blocks = [_block(report, "verifier") for report in _reports(runs)]
    totals = {field: _total(blocks, field) for field in VERIFIER_FIELDS}
    answered = totals["pass_first_try"] + totals["rejected_first_try"]
    catch = _ratio(totals["rejected_first_try"], answered)
    return [[str(totals[field]) for field in VERIFIER_FIELDS] + [catch]]


def _profile_tables(runs: Sequence[tuple[Path, dict[str, Any]]]) -> list[str]:
    """Repeat the per-type table for each profile, so single-profile figures exist."""
    lines = ["", "### Per-type metrics by profile", ""]
    names = sorted({report["profile"] for report in _reports(runs)})
    for index, profile in enumerate(names):
        subset = [item for item in runs if item[1]["profile"] == profile]
        seeds = ", ".join(str(report["seed"]) for report in _reports(subset))
        if index:
            lines.append("")
        lines += [f"`{profile}` (seeds {seeds}):", ""]
        lines += _table(SCORE_HEADER, _score_rows(subset, "per_type", "overall"))
    return lines


def _provider_section(runs: Sequence[tuple[Path, dict[str, Any]]]) -> list[str]:
    """Render every table for one provider."""
    reports = _reports(runs)
    provider = str(reports[0]["llm"])
    note = PROVIDER_NOTES.get(provider, "Real OpenAI-compatible endpoint configured by `.env`.")
    lines = [f"## Provider `{provider}`", "", f"{note} {_runs_line(reports)}", ""]
    lines += _table(SCORE_HEADER, _score_rows(runs, "per_type", "overall"))
    lines += ["", "### Match-pair accuracy", ""]
    matches = [
        report["match_pair"] for report in reports if isinstance(report.get("match_pair"), dict)
    ]
    lines += _table(SCORE_HEADER, [_score_row("all matches", matches)])
    lines += _profile_tables(runs)
    if any(_block(report, "cause_accuracy") for report in reports):
        lines += ["", "### Cause accuracy", ""]
        lines += _table(("Finding type", "Scored", "Correct", "Accuracy"), _cause_rows(runs))
    if any(_block(report, "verifier") for report in reports):
        lines += ["", "### Verifier statistics", ""]
        lines += _table(VERIFIER_HEADER, _verifier_rows(runs))
    return lines


def _cell_runs(reports_dir: Path, profile: str, seed: int) -> list[tuple[Path, dict[str, Any]]]:
    """Load every saved report for one grid cell, canonical file first."""
    paths = [reports_dir / f"eval_{profile}_{seed}.json"]
    paths += sorted(reports_dir.glob(f"eval_{profile}_{seed}_*.json"))
    return [(path, _load(path)) for path in paths if path.exists()]


def provider_sections(
    reports_dir: Path, grid_paths: Sequence[Path]
) -> list[list[tuple[Path, dict[str, Any]]]]:
    """Group the saved runs of a grid by provider, offline providers listed first."""
    grid = [_load(path) for path in grid_paths]
    cells = sorted({(report["profile"], report["seed"]) for report in grid})
    grouped: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for cell in cells:
        for path, report in _cell_runs(reports_dir, *cell):
            grouped.setdefault(str(report["llm"]), []).append((path, report))

    def rank(name: str) -> tuple[int, str]:
        """Order offline reference providers first, then any real provider by name."""
        index = REFERENCE_PROVIDERS.index(name) if name in REFERENCE_PROVIDERS else 99
        return (index, name)

    return [grouped[name] for name in sorted(grouped, key=rank)]


def final_eval_markdown(
    sections: Sequence[Sequence[tuple[Path, dict[str, Any]]]], sources: Sequence[Path]
) -> str:
    """Render the aggregate document from grouped runs and the files they came from."""
    lines = [
        "# Final evaluation",
        "",
        "Every number below is read from the JSON files listed here; none of it is typed",
        "by hand. Regenerate the tables with:",
        "",
        "```",
        "$ python -m recon eval --profiles easy realistic hard --seeds 1 2 3 --llm mock",
        "```",
        "",
        "Input files: "
        + ", ".join(f"`{name}`" for name in sorted({path.name for path in sources}))
        + ".",
        "",
        "Matching is decided by deterministic code alone, so the per-type and match-pair",
        "tables are identical for every provider listed here; only the cause accuracy and",
        "verifier statistics differ between providers. Ratios are micro-averaged: the TP,",
        "FP and FN counts are summed over the runs of a section before precision, recall",
        "and F1 are computed.",
        "",
    ]
    for section in sections:
        lines += _provider_section(section) + [""]
    lines += ["## Limitations", ""]
    lines += [f"{index}. {text}" for index, text in enumerate(LIMITATIONS, start=1)]
    return "\n".join(lines) + "\n"


def write_final_eval(
    reports_dir: Path, grid_paths: Sequence[Path], out_path: Path | None = None
) -> Path:
    """Write the aggregate report from the evaluation JSON files saved for a grid."""
    destination = out_path or reports_dir / FINAL_EVAL_NAME
    sections = provider_sections(reports_dir, grid_paths)
    sources = [path for section in sections for path, _ in section]
    destination.write_text(final_eval_markdown(sections, sources), encoding="utf-8")
    return destination
