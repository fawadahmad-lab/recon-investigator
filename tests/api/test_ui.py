"""Web UI tests: the single page, its assets and its API wiring."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from recon.api.app import STATIC_DIR, TOKENS_PATH, create_app
from recon.config import Settings, get_settings
from recon.ingest.column_map import COLUMN_FIELDS
from recon.models import Severity

EXTERNAL = re.compile(r"https?://", re.IGNORECASE)


def asset(client: TestClient, name: str) -> tuple[str, str]:
    """GET one UI asset and return its body and content type."""
    response = client.get(f"/static/{name}")
    assert response.status_code == 200
    return response.text, response.headers["content-type"]


def test_index_serves_the_single_page_ui(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert "Recon Investigator" in html
    assert "Deterministic matching. Verified AI explanations." in html
    for label in ("Bank statement", "Ledger", "Column mapping"):
        assert label in html
    for button in ("Run reconciliation", "Load demo data", "Open audit report"):
        assert button in html
    for step in ("Parse", "Normalize", "Match", "Investigate", "Report"):
        assert f'data-stage="{step.lower()}"' in html
    assert 'id="type-filter"' in html and 'id="severity-filter"' in html
    assert 'id="show-matched"' in html
    assert 'id="bank-file"' in html and 'id="ledger-file"' in html


def test_ui_assets_are_served_with_their_media_types(client: TestClient) -> None:
    assert asset(client, "app.css")[1].startswith("text/css")
    assert asset(client, "app.js")[1].startswith("text/javascript")
    tokens, media_type = asset(client, "tokens.css")
    assert media_type.startswith("text/css")
    assert "--color-ai: #5B3FB5" in tokens
    assert tokens == TOKENS_PATH.read_text(encoding="utf-8")


def test_unknown_asset_returns_the_error_shape(client: TestClient) -> None:
    body = client.get("/static/nope.css").json()
    assert body["error"]["code"] == "asset_not_found"


def test_ui_never_references_an_external_resource(client: TestClient) -> None:
    for name in ("index.html", "app.css", "app.js"):
        assert not EXTERNAL.search(asset(client, name)[0]), name
    assert (STATIC_DIR / "index.html").exists()


def test_ui_column_mapping_fields_match_the_ingest_fields(client: TestClient) -> None:
    script = asset(client, "app.js")[0]
    declared = re.search(r"const COLUMN_FIELDS = \[(.*?)\];", script, re.DOTALL)
    assert declared is not None
    assert tuple(re.findall(r'"([a-z_]+)"', declared.group(1))) == tuple(COLUMN_FIELDS)


def test_ui_severity_badges_cover_every_severity(client: TestClient) -> None:
    script = asset(client, "app.js")[0]
    css = asset(client, "app.css")[0]
    assert "badge-${row.severity}" in script
    for severity in Severity:
        assert f".badge-{severity}" in css


def test_ui_calls_the_documented_endpoints(client: TestClient) -> None:
    script = asset(client, "app.js")[0]
    assert '"/api/run"' in script
    assert '"/api/demo"' in script
    assert "summary.report_url" in script


def test_health_of_a_default_app_needs_no_api_key() -> None:
    client = TestClient(create_app(get_settings()))
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_app_holds_its_settings_and_an_empty_index(settings: Settings) -> None:
    app = create_app(settings)
    assert app.state.settings is settings
    assert app.state.store.get("20260101-000000-deadbeef") is None
    assert app.state.store.reports_dir.name == "reports"
