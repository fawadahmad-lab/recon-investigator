"""Application exception hierarchy."""


class ReconError(Exception):
    """Base exception for expected reconciliation errors."""


class IngestError(ReconError):
    """Raised when an input file cannot be ingested."""


class MappingError(ReconError):
    """Raised when input columns cannot be mapped."""


class ValidationError(ReconError):
    """Raised for invalid application configuration or requests."""


class MatchingError(ReconError):
    """Raised when deterministic matching cannot complete."""


class LLMError(ReconError):
    """Raised for recoverable LLM provider failures."""


class VerificationError(ReconError):
    """Raised when an LLM response fails verification."""


class ReportError(ReconError):
    """Raised when report generation cannot complete."""
