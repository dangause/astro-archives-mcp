from dataclasses import dataclass
from typing import ClassVar, Literal

RetryStrategy = Literal["fix_and_retry", "wait_and_retry", "submit_async", "abandon"]


@dataclass
class ToolExecutionError(Exception):
    """Base class — every concrete subclass sets error_class + retry_strategy.

    Subclasses that should have their message redacted in the LLM-facing
    payload (e.g. internal server errors) override redact_message to True.
    """

    redact_message: ClassVar[bool] = False
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
    redact_message: ClassVar[bool] = True
    error_class: str = "internal_error"
    retry_strategy: RetryStrategy = "abandon"


_INTERNAL_GENERIC_MESSAGE = "Internal server error. Contact ops with request_id."


def error_to_payload(
    err: Exception, *, request_id: str | None = None
) -> dict:
    """Convert any error into the LLM-facing payload shape.

    Unknown exceptions (anything not a ToolExecutionError) are coerced into
    InternalError; the original exception is attached as __cause__ so the
    caller's logger can still recover it.

    The LLM-facing payload omits hint and retry_after_seconds when not present
    to save tokens; callers should use payload.get(...) on those keys.
    """
    if not isinstance(err, ToolExecutionError):
        original = err
        err = InternalError(message="", request_id=request_id)
        err.__cause__ = original

    payload: dict = {
        "error_class": err.error_class,
        "message": (
            _INTERNAL_GENERIC_MESSAGE if err.redact_message else err.message
        ),
        "retry_strategy": err.retry_strategy,
        "request_id": err.request_id or request_id,
    }
    if err.hint:
        payload["hint"] = err.hint
    if err.retry_after_seconds is not None:
        payload["retry_after_seconds"] = err.retry_after_seconds
    return payload
