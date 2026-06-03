"""IVOA generic tools. Slice A ships only vo_tap_query (sync, inline tier)."""
import logging
from typing import Annotated

from pydantic import Field

from astro_archives_mcp.backends.tap import TapClient
from astro_archives_mcp.errors import ToolExecutionError, error_to_payload
from astro_archives_mcp.observability import current_request_id
from astro_archives_mcp.shaper import shape_inline_table

log = logging.getLogger(__name__)

_tap: TapClient | None = None


def _get_tap() -> TapClient:
    """Lazy accessor so tests can patch TapClient without import-time side effects."""
    global _tap
    if _tap is None:
        _tap = TapClient()
    return _tap


def vo_tap_query(
    endpoint: Annotated[
        str,
        Field(
            description=(
                "Full TAP service URL. Example: "
                "'https://datalab.noirlab.edu/tap' (NOIRLab Astro Data Lab) "
                "or 'https://almascience.nrao.edu/tap' (ALMA Science Archive). "
                "Discover services via vo_registry_search (later slice)."
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

    On error, returns a Tool Execution Error payload with `error_class`,
    `message`, `retry_strategy`, and (when available) `hint`.
    """
    try:
        table = _get_tap().query(endpoint=endpoint, adql=adql, maxrec=maxrec)
    except ToolExecutionError as e:
        rid = current_request_id.get()
        log.warning("vo_tap_query: %s (request_id=%s)", e.error_class, rid)
        return {"isError": True, **error_to_payload(e, request_id=rid)}
    except Exception as e:  # noqa: BLE001
        rid = current_request_id.get()
        log.exception("vo_tap_query: unexpected error (request_id=%s)", rid)
        return {"isError": True, **error_to_payload(e, request_id=rid)}
    return shape_inline_table(table, archive=_archive_label(endpoint), maxrec=maxrec)


def _archive_label(endpoint: str) -> str:
    """Coarse label for the `archive` field. Static map for Slice A; later
    slices replace with a registry-aware lookup."""
    e = endpoint.lower()
    if "datalab.noirlab" in e:
        return "datalab"
    if "almascience" in e:
        return "alma"
    if "data-query.nrao" in e:
        return "nrao_vla"
    return "other"
