"""Tools for IVOA TAP."""
from typing import Annotated

from pydantic import Field

from astro_archives_mcp import job_store
from astro_archives_mcp._archive_label import archive_label
from astro_archives_mcp.backends.tap import TapClient
from astro_archives_mcp.errors import (
    DalQueryError,
    JobNotReadyError,
    ValidationError,
    wrap_tool_errors,
)
from astro_archives_mcp.shaper import shape_table
from astro_archives_mcp.tools._constants import _ERROR_DOCSTRING

_tap: TapClient | None = None


def _get_tap() -> TapClient:
    """Lazy accessor so tests can patch TapClient without import-time side effects."""
    global _tap
    if _tap is None:
        _tap = TapClient()
    return _tap


@wrap_tool_errors
def vo_tap_query(
    endpoint: Annotated[
        str,
        Field(
            description=(
                "Full TAP service URL. Example: "
                "'https://datalab.noirlab.edu/tap' (NOIRLab Astro Data Lab) "
                "or 'https://almascience.nrao.edu/tap' (ALMA Science Archive). "
                "Discover services via vo_registry_search."
            ),
            examples=[
                "https://datalab.noirlab.edu/tap",
                "https://almascience.nrao.edu/tap",
            ],
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
            ge=1, le=100_000,
            description="Hard cap on rows returned. Default 10_000.",
        ),
    ] = 10_000,
) -> dict:
    """Run a synchronous ADQL query against any IVOA-compliant TAP service.

    Returns the inline result envelope:
    {row_count, columns, rows, archive, truncated, ...}.

    Results are returned inline up to `maxrec` rows (default 10000, hard cap
    100000). If more rows match the query, the response is truncated to
    `maxrec` and the envelope reports `truncated=true` with
    `truncation_reason="maxrec_exceeded"`. Always inspect `truncated` before
    treating the result as complete.

    Later slices add: async / auto-promote for very large jobs, a Resource
    tier for medium-large results, and registry-aware archive labels.
    """
    table = _get_tap().query(endpoint=endpoint, adql=adql, maxrec=maxrec)
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
            min_length=12, max_length=12,
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
            message=(
                f"Unknown or expired job_id '{job_id}'. Re-submit with "
                "vo_tap_query."
            ),
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
            min_length=12, max_length=12,
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
            message=(
                f"Unknown or expired job_id '{job_id}'. Re-submit with "
                "vo_tap_query."
            ),
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
        table, archive=archive_label(entry.endpoint), maxrec=len(table),
    )


vo_tap_results.__doc__ = (vo_tap_results.__doc__ or "") + _ERROR_DOCSTRING


@wrap_tool_errors
def vo_tap_abort(
    job_id: Annotated[
        str,
        Field(
            description="Opaque 12-character job_id from vo_tap_query (async).",
            min_length=12, max_length=12,
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
