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
from astro_archives_mcp.backends.cone import ConeSearchClient
from astro_archives_mcp.backends.registry import RegistryClient
from astro_archives_mcp.backends.sia import SiaClient
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


_cone: ConeSearchClient | None = None


def _get_cone() -> ConeSearchClient:
    """Lazy accessor so tests can patch ConeSearchClient without import-time side effects."""
    global _cone
    if _cone is None:
        _cone = ConeSearchClient()
    return _cone


_sia: SiaClient | None = None


def _get_sia() -> SiaClient:
    """Lazy accessor so tests can patch SiaClient without import-time side effects."""
    global _sia
    if _sia is None:
        _sia = SiaClient()
    return _sia


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


@wrap_tool_errors
def vo_cone_search(
    endpoint: Annotated[
        str,
        Field(
            description=(
                "Simple Cone Search endpoint URL. Example: "
                "'https://gaia.ari.uni-heidelberg.de/cone/gaiadr2?'. Prefer "
                "vo_tap_query for archives that expose a TAP endpoint — "
                "vo_cone_search is here for SCS-only legacy services."
            ),
            examples=["https://gaia.ari.uni-heidelberg.de/cone/gaiadr2?"],
        ),
    ],
    ra: Annotated[float, Field(description="Right ascension (ICRS), degrees.")],
    dec: Annotated[float, Field(description="Declination (ICRS), degrees.")],
    radius_deg: Annotated[
        float,
        Field(ge=0.0001, le=10.0, description="Cone radius in degrees."),
    ],
    maxrec: Annotated[int, Field(ge=1, le=100_000, description="Hard cap on rows returned. Default 10_000.")] = 10_000,
) -> dict:
    """Run a Simple Cone Search (SCS) against a catalog endpoint.

    Returns the inline tabular envelope, same shape as vo_tap_query.
    For most uses, prefer vo_tap_query — SCS is here for catalogs that
    only expose the legacy protocol.
    """
    table = _get_cone().search(
        endpoint=endpoint, ra=ra, dec=dec, radius_deg=radius_deg, maxrec=maxrec,
    )
    return shape_inline_table(table, archive=archive_label(endpoint), maxrec=maxrec)


@wrap_tool_errors
def vo_sia_search(
    endpoint: Annotated[
        str,
        Field(
            description=(
                "SIA 2.0 endpoint URL. Example: "
                "'https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/sia' (CADC). "
                "Note: Data Lab is SIA v1; use SIA2-capable archives like "
                "CADC or ESO. Discover with vo_registry_search(servicetype='sia')."
            ),
            examples=["https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/sia"],
        ),
    ],
    ra: Annotated[float, Field(description="Right ascension (ICRS), degrees.")],
    dec: Annotated[float, Field(description="Declination (ICRS), degrees.")],
    size_deg: Annotated[
        float,
        Field(ge=0.0001, le=5.0, description="Field-of-view size in degrees."),
    ],
    band: Annotated[
        str | None,
        Field(
            description="Optional waveband filter (e.g. 'optical', 'infrared').",
            examples=["optical"],
        ),
    ] = None,
    fmt: Annotated[
        str | None,
        Field(
            description="Optional image format (e.g. 'image/fits').",
            examples=["image/fits"],
        ),
    ] = None,
    maxrec: Annotated[int, Field(ge=1, le=10_000, description="Hard cap on rows returned. Default 1_000.")] = 1_000,
) -> dict:
    """Discover images at a sky position via Simple Image Access (SIA 2.0).

    Returns the inline tabular envelope. Each row is image metadata; the
    `access_url` column points at a FITS file you can fetch directly.
    Slice 2: no server-side image fetching — that arrives with the
    Resource tier in Slice 3.

    For all-sky discovery first, see vo_registry_search with
    servicetype='sia'.
    """
    table = _get_sia().search(
        endpoint=endpoint, ra=ra, dec=dec, size_deg=size_deg,
        band=band, fmt=fmt, maxrec=maxrec,
    )
    return shape_inline_table(table, archive=archive_label(endpoint), maxrec=maxrec)


vo_tap_query.__doc__ = (vo_tap_query.__doc__ or "") + _ERROR_DOCSTRING
vo_registry_search.__doc__ = (vo_registry_search.__doc__ or "") + _ERROR_DOCSTRING
vo_registry_describe.__doc__ = (vo_registry_describe.__doc__ or "") + _ERROR_DOCSTRING
vo_cone_search.__doc__ = (vo_cone_search.__doc__ or "") + _ERROR_DOCSTRING
vo_sia_search.__doc__ = (vo_sia_search.__doc__ or "") + _ERROR_DOCSTRING
