"""Tools for IVOA Simple Image Access."""
from typing import Annotated

from pydantic import Field

from astro_archives_mcp._archive_label import archive_label, is_known_archive_url
from astro_archives_mcp.backends.sia import SiaClient
from astro_archives_mcp.errors import ValidationError, wrap_tool_errors
from astro_archives_mcp.shaper import shape_blob_fetch, shape_table
from astro_archives_mcp.tools._constants import _ERROR_DOCSTRING

_sia: SiaClient | None = None


def _get_sia() -> SiaClient:
    """Lazy accessor so tests can patch SiaClient without import-time side effects."""
    global _sia
    if _sia is None:
        _sia = SiaClient()
    return _sia


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
    return shape_table(table, archive=archive_label(endpoint), maxrec=maxrec)


vo_sia_search.__doc__ = (vo_sia_search.__doc__ or "") + _ERROR_DOCSTRING


@wrap_tool_errors
def vo_sia_fetch(
    access_url: Annotated[
        str,
        Field(
            description=(
                "URL of a single image, from an `access_url` column in a "
                "vo_sia_search result. Must point to a known IVOA archive "
                "(Data Lab, ALMA, ESO, CADC, Gaia, NRAO, SDSS). Other "
                "hosts are rejected with validation_error."
            ),
            examples=[
                "https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/data/pub/...",
            ],
        ),
    ],
) -> dict:
    """Fetch a single image from an IVOA SIA access_url.

    Downloads the bytes (up to 10 MB), stashes them in the Resource
    store, returns an envelope with a `resource_uri` the user/client
    can fetch via MCP `resources/read`. The actual bytes do NOT flow
    inline — the response is small JSON describing the stored image.
    """
    if not is_known_archive_url(access_url):
        raise ValidationError(
            message=(
                "URL host not in known-archive allow-list. "
                "Pass an access_url from a vo_sia_search result."
            ),
            retry_strategy="abandon",
        )
    payload, mime_type = _get_sia().fetch(access_url)
    return shape_blob_fetch(
        payload,
        source_url=access_url,
        mime_type=mime_type,
        archive=archive_label(access_url),
    )


vo_sia_fetch.__doc__ = (vo_sia_fetch.__doc__ or "") + _ERROR_DOCSTRING
