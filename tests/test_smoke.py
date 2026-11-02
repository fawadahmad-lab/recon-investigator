"""Bootstrap smoke tests."""

from pytest import MonkeyPatch

from recon import config


def test_defaults_load_without_environment(monkeypatch: MonkeyPatch) -> None:
    """The application has safe offline defaults without a `.env` file."""
    monkeypatch.setattr(config, "load_dotenv", lambda: False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DATE_WINDOW_EXACT_DAYS", raising=False)
    settings = config.get_settings()
    assert settings.llm_provider == "mock"
    assert settings.date_window_exact_days == 3
