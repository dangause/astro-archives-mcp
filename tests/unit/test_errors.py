from astro_archives_mcp.errors import (
    ArchiveError,
    InternalError,
    TapQueryError,
    ValidationError,
    error_to_payload,
)


def test_validation_error_payload_shape():
    err = ValidationError(
        message="Bad ADQL: column 'g_mag' not found",
        hint="Did you mean 'gmag'? See resource://catalogs/smash_dr2.object.notes",
        request_id="r-1",
    )
    payload = error_to_payload(err)
    assert payload["error_class"] == "validation_error"
    assert payload["retry_strategy"] == "fix_and_retry"
    assert payload["request_id"] == "r-1"
    assert payload["hint"].startswith("Did you mean")


def test_archive_error_carries_retry_after():
    err = ArchiveError(
        message="upstream 503",
        retry_after_seconds=30,
        request_id="r-2",
    )
    payload = error_to_payload(err)
    assert payload["retry_strategy"] == "wait_and_retry"
    assert payload["retry_after_seconds"] == 30


def test_tap_query_error_default_strategy():
    err = TapQueryError(message="syntax error", request_id="r-3")
    payload = error_to_payload(err)
    assert payload["error_class"] == "tap_query_error"
    assert payload["retry_strategy"] == "fix_and_retry"


def test_internal_error_does_not_leak_message():
    err = InternalError(message="raw traceback redacted", request_id="r-4")
    payload = error_to_payload(err)
    assert payload["error_class"] == "internal_error"
    assert payload["message"] == "Internal server error. Contact ops with request_id."
    assert payload["request_id"] == "r-4"


def test_hint_omitted_when_none():
    err = ValidationError(message="bad", request_id="r-5")
    payload = error_to_payload(err)
    assert "hint" not in payload


def test_unknown_error_is_internal():
    payload = error_to_payload(RuntimeError("oh no"), request_id="r-6")
    assert payload["error_class"] == "internal_error"
    assert payload["request_id"] == "r-6"
