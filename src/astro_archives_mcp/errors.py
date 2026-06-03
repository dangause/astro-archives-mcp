from dataclasses import dataclass
from typing import Literal

RetryStrategy = Literal["fix_and_retry", "wait_and_retry", "submit_async", "abandon"]


@dataclass
class ToolExecutionError(Exception):
    """Base class — every concrete subclass sets error_class + retry_strategy."""

    error_class: str = "internal_error"
    retry_strategy: RetryStrategy = "abandon"
    message: str = ""
    hint: str | None = None
    retry_after_seconds: int | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        super().__init__(self.message)


@dataclass
class ValidationError(ToolExecutionError):
    error_class: str = "validation_error"
    retry_strategy: RetryStrategy = "fix_and_retry"


@dataclass
class ArchiveError(ToolExecutionError):
    error_class: str = "archive_error"
    retry_strategy: RetryStrategy = "wait_and_retry"


@dataclass
class TapQueryError(ToolExecutionError):
    error_class: str = "tap_query_error"
    retry_strategy: RetryStrategy = "fix_and_retry"


@dataclass
class InternalError(ToolExecutionError):
    error_class: str = "internal_error"
    retry_strategy: RetryStrategy = "abandon"


_INTERNAL_GENERIC_MESSAGE = "Internal server error. Contact ops with request_id."


def error_to_payload(
    err: Exception, *, request_id: str | None = None
) -> dict:
    """Convert any error into the LLM-facing payload shape.

    Unknown exceptions become InternalError; their raw message is redacted to
    avoid leaking tracebacks or creds.
    """
    if not isinstance(err, ToolExecutionError):
        err = InternalError(message="", request_id=request_id)

    payload: dict = {
        "error_class": err.error_class,
        "message": (
            _INTERNAL_GENERIC_MESSAGE if err.error_class == "internal_error" else err.message
        ),
        "retry_strategy": err.retry_strategy,
        "request_id": err.request_id or request_id,
    }
    if err.hint:
        payload["hint"] = err.hint
    if err.retry_after_seconds is not None:
        payload["retry_after_seconds"] = err.retry_after_seconds
    return payload
