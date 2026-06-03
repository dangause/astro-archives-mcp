"""IVOA generic tools. Slice A ships only vo_tap_query (sync, inline tier)."""
from typing import Annotated

from pydantic import Field

from astro_archives_mcp.backends.tap import TapClient
from astro_archives_mcp.errors import ToolExecutionError, error_to_payload
from astro_archives_mcp.shaper import shape_inline_table

_tap = TapClient()


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

    Returns the inline result envelope: {row_count, columns, rows, archive,
    truncated, ...}. Slice A only supports the inline tier (<= 1000 rows or
    ~512 KB); larger results will be truncated with `truncated: true` and
    `truncation_reason: "maxrec_exceeded"`. Async, auto-promote, and Resource-
    tier responses ship in later slices.

    On error, returns a Tool Execution Error payload with `error_class`,
    `message`, `retry_strategy`, and (when available) `hint`.
    """
    try:
        table = _tap.query(endpoint=endpoint, adql=adql, maxrec=maxrec)
    except ToolExecutionError as e:
        return {"isError": True, **error_to_payload(e)}
    except Exception as e:  # noqa: BLE001
        return {"isError": True, **error_to_payload(e)}
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
