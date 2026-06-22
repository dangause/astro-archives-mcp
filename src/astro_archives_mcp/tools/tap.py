"""Tools for IVOA TAP."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import Field

from astro_archives_mcp import job_store
from astro_archives_mcp._archive_label import archive_label
from astro_archives_mcp.backends.tap import TapClient
from astro_archives_mcp.config import get_settings
from astro_archives_mcp.errors import (
    ArchiveError,
    DalQueryError,
    JobNotReadyError,
    TimeoutArchiveError,
    ValidationError,
    wrap_tool_errors,
)
from astro_archives_mcp.known_archives import (
    tap_endpoint_description,
    tap_endpoint_urls,
)
from astro_archives_mcp.shaper import shape_promotion, shape_table
from astro_archives_mcp.tools._constants import _ERROR_DOCSTRING

_tap: TapClient | None = None


def _get_tap() -> TapClient:
    """Lazy accessor so tests can patch TapClient without import-time side effects."""
    global _tap
    if _tap is None:
        _tap = TapClient(
            sync_timeout_seconds=get_settings().tap_sync_timeout_seconds,
        )
    return _tap


def _promote_async(*, endpoint: str, adql: str, maxrec: int) -> dict:
    """Submit async and return a promotion envelope.

    Wraps submit + JobStore put + envelope shaping. Raises ArchiveError
    if the async submission itself fails (so the caller still gets a
    structured payload via wrap_tool_errors).
    """
    job_url = _get_tap().submit_async(endpoint=endpoint, adql=adql, maxrec=maxrec)
    job_id, _ = job_store.put(
        job_url=job_url,
        endpoint=endpoint,
        adql=adql,
        ttl_seconds=get_settings().job_ttl_seconds,
    )
    return shape_promotion(
        job_id=job_id,
        archive=archive_label(endpoint),
        phase="EXECUTING",
        submitted_at=datetime.now(UTC),
    )


@wrap_tool_errors
def vo_tap_query(
    endpoint: Annotated[
        str,
        Field(
            description=tap_endpoint_description(),
            examples=tap_endpoint_urls()[:2],
        ),
    ],
    adql: Annotated[
        str,
        Field(
            description=(
                "ADQL query. Use CIRCLE/POINT/CONTAINS for sky-region "
                "cuts. Use SELECT TOP N to cap row counts. Use ORDER BY for "
                "deterministic results."
            ),
            examples=[
                "SELECT TOP 100 ra, dec, gmag FROM smash_dr2.object "
                "WHERE 1=CONTAINS(POINT('ICRS', ra, dec), "
                "CIRCLE('ICRS', 185.43, -31.99, 0.2))",
            ],
        ),
    ],
    maxrec: Annotated[
        int,
        Field(
            ge=1,
            le=100_000,
            description="Hard cap on rows returned. Default 10_000.",
        ),
    ] = 10_000,
    mode: Annotated[
        Literal["sync", "async", "auto"],
        Field(
            description=(
                "Execution mode. 'sync' = TAP /sync only (default Slice-A "
                "behavior; times out as archive_error). 'async' = skip "
                "sync, submit /async, return a promotion envelope with "
                "job_id. 'auto' (default) = try sync first; on timeout, "
                "transparently promote to async."
            ),
        ),
    ] = "auto",
) -> dict:
    """Run an ADQL query against any IVOA-compliant TAP service.

    BEFORE composing a query against an archive you don't already know
    cold, call `vo_archive_list` first. It returns curated usage notes
    for the well-known archives — non-standard table locations, required
    mode='async' routing, ADQL quirks, target-name conventions — that
    will save you trial-and-error here.

    Returns one of two envelope shapes depending on what happened:

    1. Sync result envelope (rows or resource_uri).
       Returned when mode='sync', or when mode='auto' and the query
       finished within the sync timeout. No `mode` key on the response.

    2. Promotion envelope (mode='async', job_id, phase, next_steps).
       Returned when mode='async', or when mode='auto' and the sync
       attempt timed out and was promoted. Disambiguate by checking
       payload.get('mode') == 'async'.

    For async results, poll vo_tap_status(job_id) until phase is
    COMPLETED, then call vo_tap_results(job_id).
    """
    if mode == "async":
        return _promote_async(endpoint=endpoint, adql=adql, maxrec=maxrec)

    if mode == "sync":
        table = _get_tap().query(endpoint=endpoint, adql=adql, maxrec=maxrec)
        return shape_table(table, archive=archive_label(endpoint), maxrec=maxrec)

    # mode == "auto": try sync, promote to async only on a sync timeout.
    # The discriminator is the exception TYPE (TimeoutArchiveError), not a
    # substring of the message — other archive errors (unreachable host,
    # 5xx, etc.) are plain ArchiveError and propagate unpromoted.
    try:
        table = _get_tap().query(endpoint=endpoint, adql=adql, maxrec=maxrec)
    except TimeoutArchiveError:
        try:
            return _promote_async(endpoint=endpoint, adql=adql, maxrec=maxrec)
        except ArchiveError as submit_err:
            raise ArchiveError(
                message=f"auto-promote submission failed: {submit_err.message}",
                retry_strategy="wait_and_retry",
            ) from submit_err
    return shape_table(table, archive=archive_label(endpoint), maxrec=maxrec)


vo_tap_query.__doc__ = (vo_tap_query.__doc__ or "") + _ERROR_DOCSTRING


def _status_payload(*, job_id: str, job, endpoint: str) -> dict:
    """Build the status response from a live AsyncTAPJob."""
    error_message = None
    if job.phase == "ERROR":
        es = getattr(job, "error_summary", None)
        if es is not None:
            error_message = getattr(es, "message", None) or str(es)

    started = getattr(job, "starttime", None)
    ended = getattr(job, "endtime", None)
    return {
        "job_id": job_id,
        "phase": job.phase,
        "started_at": started.isoformat() if started else None,
        "ended_at": ended.isoformat() if ended else None,
        "error_message": error_message,
        "archive": archive_label(endpoint),
    }


@wrap_tool_errors
def vo_tap_status(
    job_id: Annotated[
        str,
        Field(
            description=(
                "Opaque 12-character job_id returned by vo_tap_query "
                "when it goes async (mode='async' or auto-promote)."
            ),
            min_length=12,
            max_length=12,
        ),
    ],
) -> dict:
    """Fetch the live UWS phase for an async TAP job.

    Returns {job_id, phase, started_at, ended_at, error_message, archive}.
    Phase is read live from the upstream service; no local caching.

    Phases per UWS spec: PENDING, QUEUED, EXECUTING, COMPLETED, ERROR,
    ABORTED, ARCHIVED, HELD, SUSPENDED, UNKNOWN. The LLM branches on
    the string.
    """
    entry = job_store.get(job_id)
    if entry is None:
        raise ValidationError(
            message=(f"Unknown or expired job_id '{job_id}'. Re-submit with vo_tap_query."),
            retry_strategy="abandon",
        )
    job = _get_tap().load_job(entry.job_url)
    return _status_payload(job_id=job_id, job=job, endpoint=entry.endpoint)


vo_tap_status.__doc__ = (vo_tap_status.__doc__ or "") + _ERROR_DOCSTRING


@wrap_tool_errors
def vo_tap_results(
    job_id: Annotated[
        str,
        Field(
            description="Opaque 12-character job_id from vo_tap_query (async).",
            min_length=12,
            max_length=12,
        ),
    ],
) -> dict:
    """Fetch the result table for a COMPLETED async TAP job.

    Returns the same envelope shape as a sync vo_tap_query: inline rows
    for small results, Resource-tier (resource_uri) for large results.

    If the job is not yet COMPLETED, raises job_not_ready (retry_strategy=poll).
    If the job ended in ERROR, raises tap_query_error with the upstream
    message.
    """
    entry = job_store.get(job_id)
    if entry is None:
        raise ValidationError(
            message=(f"Unknown or expired job_id '{job_id}'. Re-submit with vo_tap_query."),
            retry_strategy="abandon",
        )

    job = _get_tap().load_job(entry.job_url)
    phase = job.phase

    if phase == "ERROR":
        es = getattr(job, "error_summary", None)
        msg = getattr(es, "message", None) if es is not None else None
        raise DalQueryError(message=msg or "Async TAP job ended in ERROR.")
    if phase == "ABORTED":
        raise ValidationError(
            message=f"Job {job_id} was aborted; re-submit if you still want results.",
            retry_strategy="abandon",
        )
    if phase != "COMPLETED":
        raise JobNotReadyError(
            message=f"Job is still {phase}.",
            hint="Call vo_tap_status until phase is COMPLETED, then retry.",
        )

    table = job.fetch_result().to_table()
    return shape_table(
        table,
        archive=archive_label(entry.endpoint),
        maxrec=len(table),
    )


vo_tap_results.__doc__ = (vo_tap_results.__doc__ or "") + _ERROR_DOCSTRING


@wrap_tool_errors
def vo_tap_abort(
    job_id: Annotated[
        str,
        Field(
            description="Opaque 12-character job_id from vo_tap_query (async).",
            min_length=12,
            max_length=12,
        ),
    ],
) -> dict:
    """Cancel a running async TAP job.

    Sends UWS DELETE upstream and evicts the local JobStore entry.
    Idempotent: aborting an already-deleted or expired job returns the
    same {job_id, phase=ABORTED} shape rather than raising.
    """
    entry = job_store.get(job_id)
    if entry is None:
        return {
            "job_id": job_id,
            "phase": "ABORTED",
            "archive": None,
        }
    _get_tap().abort_job(entry.job_url)
    job_store.evict(job_id)
    return {
        "job_id": job_id,
        "phase": "ABORTED",
        "archive": archive_label(entry.endpoint),
    }


vo_tap_abort.__doc__ = (vo_tap_abort.__doc__ or "") + _ERROR_DOCSTRING
