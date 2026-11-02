"""The single JSON object an investigator may return, and its parser."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from recon.errors import LLMError
from recon.models import CitedFact, Confidence, Explanation, ExplanationSource, RecommendedAction


class Investigation(BaseModel):
    """LLM output shape: it carries no field that can change a finding."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(max_length=200)
    likely_cause: str
    explanation: str = Field(max_length=800)
    cited_facts: list[CitedFact] = Field(default_factory=list)
    recommended_action: RecommendedAction
    action_detail: str = Field(max_length=300)
    confidence: Confidence
    uncertainties: list[str] = Field(default_factory=list)


def output_schema() -> dict[str, Any]:
    """Return the JSON schema handed to the model so parser and prompt cannot drift."""
    return Investigation.model_json_schema()


def parse_investigation(raw: str) -> Investigation:
    """Parse one provider response, raising a provider error for any malformed output."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise LLMError(f"provider output is not valid JSON: {error.msg}") from error
    if not isinstance(payload, dict):
        raise LLMError("provider output is not a JSON object")
    try:
        return Investigation.model_validate(payload)
    except ValidationError as error:
        count = error.error_count()
        raise LLMError(f"provider output does not match the schema: {count} errors") from error


def to_explanation(investigation: Investigation, source: ExplanationSource) -> Explanation:
    """Attach the verification outcome to an otherwise untouched response."""
    return Explanation(**investigation.model_dump(), explanation_source=source)
