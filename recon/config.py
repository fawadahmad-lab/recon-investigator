"""Environment-backed application settings."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv

from dotenv import load_dotenv


def _bool_setting(name: str, default: bool) -> bool:
    """Read a boolean environment setting."""
    value = getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_setting(name: str, default: int) -> int:
    """Read an integer environment setting."""
    value = getenv(name)
    return default if value is None else int(value)


def _float_setting(name: str, default: float) -> float:
    """Read a floating-point threshold environment setting."""
    value = getenv(name)
    return default if value is None else float(value)


@dataclass(frozen=True)
class Settings:
    """All runtime configuration loaded from environment variables."""

    date_window_exact_days: int
    date_window_fuzzy_days: int
    date_mismatch_max_days: int
    fuzzy_accept: float
    ref_strong: float
    pair_margin: float
    dup_date_window_days: int
    fee_max_minor: int
    split_max_parts: int
    split_date_window_days: int
    split_tolerance_minor: int
    split_max_pool: int
    split_min_sim: float
    split_max_nodes: int
    severity_high_minor: int
    severity_medium_minor: int
    default_currency: str
    date_dayfirst: bool
    ledger_sign_inverted: bool
    llm_provider: str
    llm_base_url: str
    llm_api_key: str | None
    llm_model: str
    llm_timeout_s: int
    llm_max_concurrency: int
    llm_cache_dir: str


def get_settings() -> Settings:
    """Load settings from `.env` and the process environment."""
    load_dotenv()
    return Settings(
        date_window_exact_days=_int_setting("DATE_WINDOW_EXACT_DAYS", 3),
        date_window_fuzzy_days=_int_setting("DATE_WINDOW_FUZZY_DAYS", 10),
        date_mismatch_max_days=_int_setting("DATE_MISMATCH_MAX_DAYS", 30),
        fuzzy_accept=_float_setting("FUZZY_ACCEPT", 0.75),
        ref_strong=_float_setting("REF_STRONG", 0.90),
        pair_margin=_float_setting("PAIR_MARGIN", 0.05),
        dup_date_window_days=_int_setting("DUP_DATE_WINDOW_DAYS", 3),
        fee_max_minor=_int_setting("FEE_MAX_MINOR", 2500),
        split_max_parts=_int_setting("SPLIT_MAX_PARTS", 4),
        split_date_window_days=_int_setting("SPLIT_DATE_WINDOW_DAYS", 7),
        split_tolerance_minor=_int_setting("SPLIT_TOLERANCE_MINOR", 0),
        split_max_pool=_int_setting("SPLIT_MAX_POOL", 30),
        split_min_sim=_float_setting("SPLIT_MIN_SIM", 0.4),
        split_max_nodes=_int_setting("SPLIT_MAX_NODES", 200000),
        severity_high_minor=_int_setting("SEVERITY_HIGH_MINOR", 1000000),
        severity_medium_minor=_int_setting("SEVERITY_MEDIUM_MINOR", 100000),
        default_currency=getenv("DEFAULT_CURRENCY", "USD"),
        date_dayfirst=_bool_setting("DATE_DAYFIRST", False),
        ledger_sign_inverted=_bool_setting("LEDGER_SIGN_INVERTED", False),
        llm_provider=getenv("LLM_PROVIDER", "mock"),
        llm_base_url=getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
        llm_api_key=getenv("LLM_API_KEY") or None,
        llm_model=getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
        llm_timeout_s=_int_setting("LLM_TIMEOUT_S", 30),
        llm_max_concurrency=_int_setting("LLM_MAX_CONCURRENCY", 2),
        llm_cache_dir=getenv("LLM_CACHE_DIR", ".cache/llm"),
    )
