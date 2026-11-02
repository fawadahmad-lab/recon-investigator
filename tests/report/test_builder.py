"""The self-contained printable HTML report and its run artifacts."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from recon.matching.engine import RunResult
from recon.models import FindingStatus, format_amount
from recon.report.builder import (
    METHOD_STATEMENT,
    REPORT_NAME,
    render_report,
    report_context,
    write_run_artifacts,
)

RESOURCE_ATTRIBUTE = re.compile(r"(?:href|src|action)\s*=\s*[\"']?\s*https?://", re.IGNORECASE)
EXTERNAL_ELEMENT = re.compile(r"<\s*(?:script|link|img|iframe|video|audio|object|embed|form)\b")
SECTION_HEADINGS = ("Method", "Summary", "Inputs", "Findings", "Matched items", "Appendix")


@pytest.fixture(scope="module")
def html(explained_run: RunResult) -> str:
    """One report rendered from a mock-explained run."""
    return render_report(explained_run)


def _section(html: str, start: str, end: str) -> str:
    """Cut one report section out of the document between an anchor id and a marker."""
    return html[html.index(f'id="{start}"') : html.index(end)]


def test_the_documented_artifacts_are_written(explained_run: RunResult, tmp_path: Path) -> None:
    """A run with explanations writes all five artifacts, including the report."""
    written = write_run_artifacts(tmp_path, explained_run)

    assert {path.name for path in written} == {
        "findings.json",
        "run_meta.json",
        "audit_trail.jsonl",
        "verifier_log.jsonl",
        REPORT_NAME,
    }
    assert all(path.exists() and path.stat().st_size > 0 for path in written)


def test_a_deterministic_run_still_writes_a_report(mini_run: RunResult, tmp_path: Path) -> None:
    """Without a provider there is no verifier log, but the report is complete."""
    written = write_run_artifacts(tmp_path, mini_run)

    assert "verifier_log.jsonl" not in {path.name for path in written}
    assert (tmp_path / REPORT_NAME).exists()


def test_the_report_makes_no_external_request(html: str) -> None:
    """Acceptance: no resource reference leaves the file, and no script or stylesheet tag."""
    assert RESOURCE_ATTRIBUTE.findall(html) == []
    assert EXTERNAL_ELEMENT.findall(html) == []
    assert "@import" not in html
    assert "url(" not in html
    assert html.startswith("<!DOCTYPE html>")


def test_the_design_tokens_are_inlined(html: str) -> None:
    """The shared token file is embedded, so the report renders without the UI."""
    assert "--color-ai: #5B3FB5" in html
    assert "font-variant-numeric: tabular-nums" in html


def test_every_documented_section_is_present(html: str) -> None:
    """Title block, method statement, summary, inputs, findings, matches and appendix."""
    for heading in SECTION_HEADINGS:
        assert heading in html
    assert METHOD_STATEMENT in html
    assert "Recon Investigator audit report" in html


def test_the_run_identity_and_both_input_hashes_are_shown(explained_run: RunResult) -> None:
    """A reader can tie the report to one run, its files and its configuration."""
    html = render_report(explained_run)

    assert explained_run.run_id in html
    assert explained_run.meta["created_at"][:10] in html
    assert "UTC" in html
    assert explained_run.meta["tool_version"] in html
    assert explained_run.meta["config_hash"] in html
    for name, meta in explained_run.meta["inputs"].items():
        assert meta["file"] in html
        assert meta["sha256"] in html
        assert str(meta["invalid_rows"]) in html


def test_money_is_grouped_and_minor_units_are_hidden(mini_run: RunResult) -> None:
    """Amounts print as grouped decimals; internal minor units never reach the page."""
    html = render_report(mini_run)
    large = next(
        record
        for record in mini_run.records_by_id.values()
        if abs(record.amount_minor) >= 1_000_000
    )

    assert format_amount(large.amount_minor) in html
    assert str(large.amount_minor) not in html


def test_the_ai_box_is_visually_marked_verified(explained_run: RunResult) -> None:
    """Design section 5: the purple box carries the label, the badge and the confidence."""
    html = render_report(explained_run)
    card = _section(html, "findings", "matches")

    assert "AI explanation" in card
    assert "badge-ai" in card
    assert "Verified" in card
    assert re.search(r"confidence (Low|Medium|High)", card)


def test_a_fallback_is_marked_and_its_raw_answer_is_absent(fallback_run: RunResult) -> None:
    """Rule 2.11: a rejected answer leaves only the marked deterministic fallback."""
    html = render_report(fallback_run)
    card = _section(html, "findings", "matches")

    assert "RAWONLYMARKER" not in html
    assert "Deterministic fallback" in card
    assert "Deterministic rationale" in card
    assert "ai-box deterministic" in card


def test_no_explanation_is_reported_as_none(mini_run: RunResult) -> None:
    """A run without a provider says so instead of inventing a box."""
    html = render_report(mini_run)

    assert "No explanation" in html
    assert "AI explanation" not in html


def test_markup_in_the_input_data_is_escaped(mini_run: RunResult) -> None:
    """A description containing script markup can never execute in the report."""
    html = render_report(mini_run)

    assert "Evil &lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)" not in html
    assert "&amp;amp;" not in html


def test_findings_are_grouped_by_severity_then_type(full_run: RunResult) -> None:
    """Section 5 of the design: severity order first, then sorted types inside it."""
    html = render_report(full_run)
    headings = re.findall(r"<h3>([^<]+)</h3>", _section(html, "findings", "matches"))
    severities = [name.removesuffix(" severity") for name in headings if name.endswith(" severity")]
    body = _section(html, "findings", "matches")

    assert severities == [name for name in ("High", "Medium", "Low") if name in severities]
    for group in re.split(r"<h3>[A-Z][a-z]+ severity</h3>", body)[1:]:
        types = [name.split(" (")[0] for name in re.findall(r"<h3>([^<]+)</h3>", group)]
        assert types == sorted(types)


def test_every_finding_id_appears_once_in_its_place(full_run: RunResult) -> None:
    """Cards show discrepancies; matched items appear only in the compact table."""
    html = render_report(full_run)
    cards = _section(html, "findings", "matches")
    matches = _section(html, "matches", "appendix")
    discrepancy_ids = [
        finding.id for finding in full_run.findings if finding.status is not FindingStatus.MATCHED
    ]
    matched_ids = [
        finding.id for finding in full_run.findings if finding.status is FindingStatus.MATCHED
    ]

    assert all(finding_id in cards for finding_id in discrepancy_ids)
    assert all(finding_id in matches for finding_id in matched_ids)
    assert not any(finding_id in cards for finding_id in matched_ids)


def test_the_matched_table_has_one_row_per_match(full_run: RunResult) -> None:
    """The compact table is complete and carries both side totals."""
    html = render_report(full_run)
    body = _section(html, "matches", "appendix")
    rows = re.findall(r"<tr>\s*<td", body)
    matched = [f for f in full_run.findings if f.status is FindingStatus.MATCHED]

    assert len(rows) == len(matched)
    assert "Ledger total" in body and "Bank total" in body


def test_the_appendix_lists_rules_config_and_verifier_stats(full_run: RunResult) -> None:
    """Design section 7 item 7: configuration, config hash, rule versions, verifier stats."""
    html = render_report(full_run)
    appendix = _section(html, "appendix", "</main>")

    assert "Configuration" in appendix
    assert "Rule versions" in appendix
    assert "R6-SPLIT" in appendix
    assert full_run.meta["config_hash"] in appendix
    assert "ref_strong" in appendix
    assert "ai_verified" in appendix
    assert "llm_api_key" not in appendix


def test_print_and_responsive_rules_exist(html: str) -> None:
    """Acceptance: the stylesheet has print rules and the 720px reflow."""
    assert "@media print" in html
    assert "break-inside: avoid" in html
    assert "margin: 16mm" in html
    assert "@media (max-width: 720px)" in html


def test_rendering_one_run_twice_is_byte_identical(explained_run: RunResult) -> None:
    """The report is a pure function of the run, so a re-render cannot drift."""
    assert render_report(explained_run) == render_report(explained_run)


def test_the_context_carries_no_values_outside_the_run(explained_run: RunResult) -> None:
    """Every reported count can be traced back to the findings list."""
    context = report_context(explained_run)
    kpis = {str(row["label"]): row["value"] for row in context["kpis"]}
    matched = sum(
        1 for finding in explained_run.findings if finding.status is FindingStatus.MATCHED
    )

    assert kpis["Matched"] == matched
    assert kpis["Discrepancies"] == len(explained_run.findings) - matched
    assert sum(row["count"] for row in context["type_counts"]) == len(explained_run.findings)
