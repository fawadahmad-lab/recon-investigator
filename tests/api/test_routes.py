"""API endpoint tests: the run contract, the limits and the JSON error shape."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from recon import __version__
from recon.api.app import create_app
from recon.api.routes import DEMO_BANK, DEMO_LEDGER, WEB_RUNS_FOLDER
from recon.config import Settings
from recon.ingest.validate import MAX_FILE_SIZE_BYTES, MAX_ROWS
from recon.report.builder import METHOD_STATEMENT, REPORT_NAME

BANK_CSV = (
    "Date,Amount,Reference,Description,Currency\n"
    "2026-01-05,-100.00,INV-1000,Acme Supplies,USD\n"
    "2026-01-06,-250.00,INV-1001,Northwind Services,USD\n"
    "2026-01-07,-500.00,BANK-7788,Card processing fee,USD\n"
)
LEDGER_CSV = (
    "Date,Amount,Reference,Description,Currency\n"
    "2026-01-05,-100.00,INV-1000,Acme Supplies,USD\n"
    "2026-01-06,-260.00,INV-1001,Northwind Services inv,USD\n"
    "2026-01-20,-777.00,INV-7777,Ghost Payment,USD\n"
    "not-a-date,-1.00,INV-9999,Broken row,USD\n"
)
UNMAPPED_CSV = (
    "Txn Date,Money,Ref,Memo\n"
    "2026-02-01,-40.00,INV-2001,Cedar Office\n"
    "2026-02-01,-40.00,INV-2001,Cedar Office\n"
)
COLUMN_MAP = '{"amount": "Money", "reference": "Ref", "description": "Memo"}'
GROUPED_AMOUNT = re.compile(r"^-?\d{1,3}(,\d{3})*\.\d\d$")
ARTIFACT_NAMES = [
    "audit_trail.jsonl",
    "findings.json",
    REPORT_NAME,
    "run_meta.json",
    "verifier_log.jsonl",
]


def csv_part(name: str, content: str) -> tuple[str, str, str]:
    """Build one multipart CSV part for a TestClient request."""
    return (name, content, "text/csv")


def run_form(**overrides: Any) -> dict[str, Any]:
    """Return the default bank and ledger parts with any part replaced."""
    parts = {
        "bank": csv_part("bank.csv", BANK_CSV),
        "ledger": csv_part("ledger.csv", LEDGER_CSV),
    }
    parts.update(overrides)
    return parts


def oversized_bank() -> tuple[str, bytes, str]:
    """Build a bank part larger than the documented 10 MB upload limit."""
    header = b"Date,Amount,Reference,Description,Currency\n"
    row = b"2026-01-05,-100.00,INV-1000,Acme Supplies,USD\n"
    payload = header + row * (MAX_FILE_SIZE_BYTES // len(row) + 1)
    return ("bank.csv", payload, "text/csv")


def many_rows(count: int) -> str:
    """Build a valid CSV holding exactly `count` data rows."""
    header = "Date,Amount,Reference,Description,Currency\n"
    template = "2026-01-05,-{index}.00,INV-{code},Vendor {index},USD\n"
    rows = [template.format(index=index, code=f"{index:04d}") for index in range(1, count + 1)]
    return header + "".join(rows)


def error_of(response: Any) -> dict[str, Any]:
    """Return the documented error object and assert its shape."""
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    return body["error"]


def decisions(rows: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    """Project the decision fields of a findings list for comparison."""
    return [
        (row["id"], row["type"], row["status"], row["ledger_ids"], row["bank_ids"]) for row in rows
    ]


def post_run(client: TestClient, **overrides: Any) -> Any:
    """POST /api/run with the default fixture pair and any part overrides."""
    return client.post("/api/run", files=run_form(**overrides))


def test_health_reports_the_configured_provider(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "tool_version": __version__,
        "llm_provider": "mock",
    }


def test_run_returns_the_summary_and_writes_the_artifacts(
    client: TestClient, reports_dir: Path
) -> None:
    response = post_run(client)
    assert response.status_code == 200
    data = response.json()
    totals = data["totals"]
    assert totals["matched"] + totals["discrepancies"] == len(data["findings"])
    assert totals["matched"] >= 1
    assert totals["discrepancies"] >= 2
    assert totals["ai_verified"] >= 1
    assert data["validation_issues"] >= 1
    assert data["llm"]["provider"] == "mock"
    assert data["inputs"]["bank"]["file"] == "bank.csv"
    assert data["inputs"]["ledger"]["file"] == "ledger.csv"
    assert len(data["inputs"]["bank"]["sha256"]) == 64
    assert data["report_url"] == f"/api/runs/{data['run_id']}/report"

    run_dir = reports_dir / WEB_RUNS_FOLDER / data["run_id"]
    assert sorted(path.name for path in run_dir.iterdir()) == ARTIFACT_NAMES


def test_finding_rows_carry_the_decision_and_the_explanation(client: TestClient) -> None:
    data = post_run(client).json()
    assert data["findings"]
    for row in data["findings"]:
        assert row["id"].startswith("F-")
        assert row["status"] in {"matched", "discrepancy", "needs_review"}
        assert row["severity"] in {"high", "medium", "low"}
        assert row["ledger_ids"] or row["bank_ids"]
        assert row["rule"].startswith("R")
        assert row["explanation"] is not None
        assert row["explanation"]["badge"] in {"Verified", "Deterministic fallback"}
        assert row["explanation"]["source"] in {"ai_verified", "deterministic_fallback"}
        for total in (row["ledger_total"], row["bank_total"]):
            assert total is None or GROUPED_AMOUNT.match(total)


def test_filter_values_cover_every_reported_finding(client: TestClient) -> None:
    data = post_run(client).json()
    assert sorted(data["filters"]["types"]) == sorted({row["type"] for row in data["findings"]})
    assert data["filters"]["severities"] == [
        severity
        for severity in ("high", "medium", "low")
        if any(row["severity"] == severity for row in data["findings"])
    ]


def test_run_is_deterministic_for_the_same_uploads(client: TestClient) -> None:
    first = post_run(client).json()["findings"]
    second = post_run(client).json()["findings"]
    assert decisions(first) == decisions(second)


def test_report_endpoint_serves_the_self_contained_html(client: TestClient) -> None:
    run_id = post_run(client).json()["run_id"]
    response = client.get(f"/api/runs/{run_id}/report")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert METHOD_STATEMENT in response.text
    assert run_id in response.text


def test_run_detail_returns_the_stored_summary(client: TestClient) -> None:
    data = post_run(client).json()
    response = client.get(f"/api/runs/{data['run_id']}")
    assert response.status_code == 200
    assert response.json() == data


def test_unknown_run_id_returns_the_error_shape(client: TestClient) -> None:
    for path in ("/api/runs/20260101-000000-deadbeef", "/api/runs/nope/report"):
        response = client.get(path)
        assert response.status_code == 404
        error = error_of(response)
        assert error["code"] == "run_not_found"
        assert error["details"]["stage"] == "report"


def test_bad_file_returns_the_json_error_shape(client: TestClient) -> None:
    response = post_run(client, bank=csv_part("bank.csv", "Txn Date,Money\n2026-01-05,1.00\n"))
    assert response.status_code == 400
    error = error_of(response)
    assert error["code"] == "mapping_error"
    assert "Money" in error["message"]
    assert error["details"]["stage"] == "parse"


def test_empty_upload_is_rejected(client: TestClient) -> None:
    response = post_run(client, bank=csv_part("bank.csv", ""))
    assert response.status_code == 400
    assert error_of(response)["code"] == "ingest_error"


def test_upload_over_the_size_limit_is_rejected(client: TestClient) -> None:
    response = post_run(client, bank=oversized_bank())
    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "file_too_large"
    assert error["details"]["limit_bytes"] == MAX_FILE_SIZE_BYTES


def test_row_limit_is_enforced(client: TestClient) -> None:
    response = post_run(client, ledger=csv_part("ledger.csv", many_rows(MAX_ROWS + 1)))
    assert response.status_code == 400
    error = error_of(response)
    assert error["code"] == "ingest_error"
    assert str(MAX_ROWS) in error["message"]


def test_only_supported_file_types_are_accepted(client: TestClient) -> None:
    response = post_run(client, bank=("bank.txt", BANK_CSV, "text/plain"))
    assert response.status_code == 400
    assert error_of(response)["code"] == "unsupported_file_type"


def test_missing_upload_part_uses_the_error_shape(client: TestClient) -> None:
    response = client.post("/api/run", files={"bank": csv_part("bank.csv", BANK_CSV)})
    assert response.status_code == 422
    error = error_of(response)
    assert error["code"] == "request_invalid"
    assert error["details"]["problems"][0]["field"].endswith("ledger")


def test_column_map_must_be_a_json_object_of_headers(client: TestClient) -> None:
    response = client.post("/api/run", files=run_form(), data={"column_map": "[1, 2]"})
    assert response.status_code == 422
    assert error_of(response)["code"] == "validation_error"

    response = client.post("/api/run", files=run_form(), data={"column_map": "not json"})
    assert response.status_code == 422
    assert "column_map" in error_of(response)["message"]


def test_column_map_override_maps_a_non_standard_export(client: TestClient) -> None:
    parts = {
        "bank": csv_part("bank.csv", UNMAPPED_CSV),
        "ledger": csv_part("ledger.csv", UNMAPPED_CSV),
    }
    response = client.post("/api/run", files=parts)
    assert response.status_code == 400
    assert error_of(response)["code"] == "mapping_error"

    response = client.post("/api/run", files=parts, data={"column_map": COLUMN_MAP})
    assert response.status_code == 200
    data = response.json()
    mapping = data["inputs"]["bank"]["column_map"]
    assert mapping["amount"] == "Money"
    assert mapping["description"] == "Memo"
    assert mapping["date"] == "Txn Date"
    assert data["totals"]["matched"] == 2


def test_demo_endpoint_runs_the_seeded_pair_end_to_end(
    client: TestClient, reports_dir: Path
) -> None:
    response = client.post("/api/demo")
    assert response.status_code == 200
    data = response.json()
    assert data["inputs"]["bank"]["file"] == DEMO_BANK
    assert data["inputs"]["ledger"]["file"] == DEMO_LEDGER
    assert data["totals"]["matched"] >= 1
    assert data["totals"]["discrepancies"] >= 1
    assert decisions(data["findings"])[0][0] == "F-0001"
    run_dir = reports_dir / WEB_RUNS_FOLDER / data["run_id"]
    assert sorted(path.name for path in run_dir.iterdir()) == ARTIFACT_NAMES


def test_unexpected_failure_returns_a_generic_500(settings: Settings, tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a folder", encoding="utf-8")
    client = TestClient(create_app(settings, blocker), raise_server_exceptions=False)
    response = client.post("/api/run", files=run_form())
    assert response.status_code == 500
    error = error_of(response)
    assert error["code"] == "internal_error"
    assert "blocker" not in response.text
