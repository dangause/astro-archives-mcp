"""IVOA generic tools (sync, inline tier).

One tool per IVOA standard:
* TAP: vo_tap_query
* Registry: vo_registry_search, vo_registry_describe (Slice 2)
* Simple Cone Search: vo_cone_search (Slice 2)
* Simple Image Access: vo_sia_search (Slice 2)

Async TAP, Resource tier, and SIA image fetching are deferred to Slice 3.
"""
from typing import Annotated

from pydantic import Field

from astro_archives_mcp._archive_label import archive_label
from astro_archives_mcp.backends.registry import RegistryClient
from astro_archives_mcp.backends.tap import TapClient
from astro_archives_mcp.errors import wrap_tool_errors
from astro_archives_mcp.shaper import (
    shape_inline_table,
    shape_registry_describe_result,
    shape_registry_search_result,
)

_ERROR_DOCSTRING = (
    "\n\n"
    "On error, returns a Tool Execution Error payload with `error_class`, "
    "`message`, `retry_strategy`, and (when available) `hint`. The presence "
    "of `error_class` is the discriminator the LLM should branch on — do "
    "NOT rely on a separate `isError` field."
)

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
    return shape_inline_table(table, archive=archive_label(endpoint), maxrec=maxrec)


_registry: RegistryClient | None = None


def _get_registry() -> RegistryClient:
    """Lazy accessor so tests can patch RegistryClient without import-time side effects."""
    global _registry
    if _registry is None:
        _registry = RegistryClient()
    return _registry


@wrap_tool_errors
def vo_registry_search(
    keywords: Annotated[
        list[str] | None,
        Field(
            description=(
                "Free-text keywords to match against service titles/descriptions. "
                "Example: ['Magellanic', 'photometry']."
            ),
            examples=[["magellanic"], ["RR Lyrae", "variable"]],
        ),
    ] = None,
    servicetype: Annotated[
        str | None,
        Field(
            description="Filter by service type: 'tap', 'sia', 'scs', 'ssa'.",
            examples=["tap", "sia"],
        ),
    ] = None,
    waveband: Annotated[
        str | None,
        Field(
            description=(
                "Filter by waveband: 'radio', 'infrared', 'optical', 'uv', "
                "'euv', 'x-ray', 'gamma-ray'."
            ),
            examples=["optical", "infrared"],
        ),
    ] = None,
    maxrec: Annotated[
        int,
        Field(ge=1, le=500, description="Hard cap on services returned. Default 50."),
    ] = 50,
) -> dict:
    """Discover IVOA-registered services matching the given constraints.

    Returns a {services: [...], row_count, truncated, truncation_reason}
    envelope. Each service entry has: ivoid, title, description, publisher,
    waveband, and one URL per capability (tap_url, sia_url, scs_url,
    ssa_url; null when the service doesn't expose that capability).

    Use for discovery before calling vo_tap_query / vo_sia_search /
    vo_cone_search on a specific endpoint. Smaller default maxrec (50)
    than catalog tools — discovery is about choice, not bulk data.
    """
    services = _get_registry().search(
        keywords=keywords, servicetype=servicetype, waveband=waveband, maxrec=maxrec
    )
    return shape_registry_search_result(services, maxrec=maxrec)


@wrap_tool_errors
def vo_registry_describe(
    ivoid_or_url: Annotated[
        str,
        Field(
            description=(
                "Either an IVOID (starts with 'ivo://') or a TAP service "
                "URL. The tool resolves both forms via RegTAP."
            ),
            examples=["ivo://datalab/smash_dr2", "https://datalab.noirlab.edu/tap"],
        ),
    ],
) -> dict:
    """Introspect a specific IVOA service: its capabilities, and for TAP
    services its tables and columns.

    Returns {ivoid, title, description, capabilities, tables}. Use after
    vo_registry_search to learn what's queryable on a specific service
    before composing ADQL via vo_tap_query.
    """
    described = _get_registry().describe(ivoid_or_url=ivoid_or_url)
    return shape_registry_describe_result(described)


vo_tap_query.__doc__ = (vo_tap_query.__doc__ or "") + _ERROR_DOCSTRING
vo_registry_search.__doc__ = (vo_registry_search.__doc__ or "") + _ERROR_DOCSTRING
vo_registry_describe.__doc__ = (vo_registry_describe.__doc__ or "") + _ERROR_DOCSTRING
