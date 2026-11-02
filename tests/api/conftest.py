"""Fixtures for the API and UI tests."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from recon.api.app import create_app
from recon.config import Settings, get_settings


@pytest.fixture()
def settings() -> Settings:
    """Force the offline `mock` provider regardless of the local `.env`."""
    return replace(get_settings(), llm_provider="mock", llm_api_key=None)


@pytest.fixture()
def reports_dir(tmp_path: Path) -> Path:
    """Return the scratch folder the run artifacts are written under."""
    return tmp_path / "reports"


@pytest.fixture()
def client(settings: Settings, reports_dir: Path) -> Iterator[TestClient]:
    """Serve the API and the UI from a scratch reports folder."""
    with TestClient(create_app(settings, reports_dir)) as test_client:
        yield test_client
