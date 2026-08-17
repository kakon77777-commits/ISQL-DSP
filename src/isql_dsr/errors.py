class DSRError(Exception):
    """Base error for ISQL Dynamic Spectrum Runtime."""


class DSRValidationError(DSRError, ValueError):
    """Raised when an object violates the DSR schema or invariants."""


class DSRExecutionError(DSRError, RuntimeError):
    """Raised when a deterministic runtime operation cannot be applied."""
