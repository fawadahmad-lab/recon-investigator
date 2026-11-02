"""Canonical models and money conversion helpers for reconciliation runs."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Source(StrEnum):
    """The source file that supplied a transaction."""

    BANK = "bank"
    LEDGER = "ledger"


class FindingType(StrEnum):
    """Deterministic match and discrepancy classifications."""

    MATCH_EXACT = "match_exact"
    MATCH_FUZZY = "match_fuzzy"
    MATCH_SPLIT = "match_split"
    MISSING_IN_BANK = "missing_in_bank"
    MISSING_IN_LEDGER = "missing_in_ledger"
    DUPLICATE_IN_BANK = "duplicate_in_bank"
    DUPLICATE_IN_LEDGER = "duplicate_in_ledger"
    AMOUNT_MISMATCH = "amount_mismatch"
    FEE_DIFFERENCE = "fee_difference"
    DATE_MISMATCH = "date_mismatch"
    AMBIGUOUS_SPLIT = "ambiguous_split"
    INVALID_RECORD = "invalid_record"


class FindingStatus(StrEnum):
    """Resolution status assigned by deterministic matching."""

    MATCHED = "matched"
    DISCREPANCY = "discrepancy"
    NEEDS_REVIEW = "needs_review"


class Severity(StrEnum):
    """Severity derived from deterministic amount thresholds."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ExplanationSource(StrEnum):
    """Origin of an explanation attached to a finding."""

    AI_VERIFIED = "ai_verified"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


class Confidence(StrEnum):
    """Confidence level allowed in verified LLM output."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendedAction(StrEnum):
    """Permitted follow-up actions in an explanation."""

    INVESTIGATE = "investigate"
    REQUEST_BANK_CONFIRMATION = "request_bank_confirmation"
    POST_ADJUSTING_ENTRY = "post_adjusting_entry"
    REVERSE_DUPLICATE = "reverse_duplicate"
    CONTACT_COUNTERPARTY = "contact_counterparty"
    WAIT_AND_RECHECK = "wait_and_recheck"
    NO_ACTION = "no_action"


class Transaction(BaseModel):
    """A normalized, valid transaction from a bank or ledger input."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source: Source
    row_number: int = Field(ge=1)
    date: date
    amount_minor: int
    currency: str = Field(min_length=1)
    reference_raw: str = ""
    reference_norm: str = ""
    description_raw: str = ""
    description_norm: str = ""
    counterparty: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ValidationIssue(BaseModel):
    """A row-level validation problem retained for audit reporting."""

    model_config = ConfigDict(extra="forbid")

    source: Source
    row_number: int = Field(ge=1)
    code: str
    message: str
    raw: dict[str, Any] = Field(default_factory=dict)


class CitedFact(BaseModel):
    """A packet value cited by an explanation."""

    model_config = ConfigDict(extra="forbid")

    field: str
    value: str


class Explanation(BaseModel):
    """A verified AI or deterministic explanation of a fixed finding."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(max_length=200)
    likely_cause: str
    explanation: str = Field(max_length=800)
    cited_facts: list[CitedFact] = Field(default_factory=list)
    recommended_action: RecommendedAction
    action_detail: str = Field(max_length=300)
    confidence: Confidence
    uncertainties: list[str] = Field(default_factory=list)
    explanation_source: ExplanationSource


class Finding(BaseModel):
    """A deterministic reconciliation result with optional explanation."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: FindingType
    status: FindingStatus
    ledger_ids: list[str] = Field(default_factory=list)
    bank_ids: list[str] = Field(default_factory=list)
    rule_id: str
    rule_version: str
    score: float | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
    severity: Severity
    explanation: Explanation | None = None


class Rule(BaseModel):
    """The deterministic rule metadata included in an evidence packet."""

    model_config = ConfigDict(extra="forbid")

    id: str
    version: str
    description: str


class EvidencePacket(BaseModel):
    """Verifier-bounded evidence supplied to an LLM for explanation only."""

    model_config = ConfigDict(extra="forbid")

    packet_version: str = "1"
    finding_id: str
    finding_type: FindingType
    rule: Rule
    records: list[dict[str, Any]] = Field(default_factory=list)
    candidates_considered: list[dict[str, Any]] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)
    allowed_causes: list[str] = Field(default_factory=list)
    allowed_values: dict[str, list[str]] = Field(default_factory=dict)


def _validate_decimal_places(decimal_places: int) -> None:
    """Validate the number of minor-unit decimal places."""
    if isinstance(decimal_places, bool) or not 0 <= decimal_places <= 8:
        raise ValueError("decimal_places must be an integer from 0 through 8")


def _as_decimal(value: Decimal | str | int) -> Decimal:
    """Convert a supported money edge value to Decimal without float coercion."""
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("money values must not be floats or booleans")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (str, int)):
        return Decimal(value)
    raise TypeError("money values must be Decimal, str, or int")


def to_minor(value: Decimal | str | int, decimal_places: int = 2) -> int:
    """Round a money edge value to integer minor units using Decimal."""
    _validate_decimal_places(decimal_places)
    scale = Decimal(10) ** decimal_places
    quantum = Decimal(1) / scale
    rounded = _as_decimal(value).quantize(quantum, rounding=ROUND_HALF_UP)
    return int(rounded * scale)


def from_minor(amount_minor: int, decimal_places: int = 2) -> Decimal:
    """Convert integer minor units to a fixed-scale Decimal value."""
    _validate_decimal_places(decimal_places)
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int):
        raise TypeError("amount_minor must be an integer")
    scale = Decimal(10) ** decimal_places
    return (Decimal(amount_minor) / scale).quantize(Decimal(1) / scale)


def format_amount(amount_minor: int, decimal_places: int = 2) -> str:
    """Format integer minor units as a grouped fixed-scale decimal string."""
    amount = from_minor(amount_minor, decimal_places)
    return f"{amount:,.{decimal_places}f}"
