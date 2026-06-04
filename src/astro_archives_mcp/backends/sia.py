import logging

import httpx
import pyvo
from astropy.table import Table
from pyvo.dal.exceptions import DALAccessError, DALQueryError

from astro_archives_mcp.errors import ArchiveError, DalQueryError

log = logging.getLogger(__name__)

_FETCH_BYTE_CAP = 10 * 1024 * 1024  # 10 MB — matches RESOURCE_BYTE_LIMIT in shaper
_FETCH_TIMEOUT_SECONDS = 60.0


class SiaClient:
    """Sync wrapper over pyvo.dal.SIA2Service.search()."""

    def search(
        self,
        *,
        endpoint: str,
        ra: float,
        dec: float,
        size_deg: float,
        band: str | None = None,
        fmt: str | None = None,
        maxrec: int = 1_000,
    ) -> Table:
        try:
            svc = pyvo.dal.SIA2Service(endpoint)
            # pyvo SIA2 expects pos as (ra, dec, radius) for a CIRCLE region
            kwargs: dict = {"pos": (ra, dec, size_deg), "maxrec": maxrec}
            if band:
                kwargs["band"] = band
            if fmt:
                kwargs["format"] = fmt
            result = svc.search(**kwargs)
        except DALQueryError as e:
            raise DalQueryError(message=str(e)) from e
        except DALAccessError as e:
            raise ArchiveError(message=str(e)) from e

        table = result.to_table()
        # Defensive cap — pyvo respects maxrec server-side, but verify locally.
        if len(table) > maxrec:
            table = table[:maxrec]
        return table

    def fetch(self, access_url: str) -> tuple[bytes, str]:
        """Download bytes from access_url, stream-capped at 10 MB.

        Returns (bytes, content_type). Raises ArchiveError on any HTTP
        failure, on exceeding the 10 MB cap, or on timeout.
        """
        try:
            with httpx.stream(
                "GET",
                access_url,
                follow_redirects=True,
                timeout=_FETCH_TIMEOUT_SECONDS,
            ) as response:
                response.raise_for_status()
                content_type = response.headers.get(
                    "content-type", "application/octet-stream"
                ).split(";")[0].strip()
                buf = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    buf.extend(chunk)
                    if len(buf) > _FETCH_BYTE_CAP:
                        # Abort mid-stream; do NOT drain the rest.
                        raise ArchiveError(
                            message=(
                                "Image exceeds 10 MB cap; reduce size_deg "
                                "in vo_sia_search"
                            ),
                            retry_strategy="abandon",
                        )
                return bytes(buf), content_type
        except httpx.HTTPStatusError as e:
            raise ArchiveError(
                message=f"upstream HTTP {e.response.status_code}",
            ) from e
        except httpx.HTTPError as e:
            raise ArchiveError(message=f"upstream error: {e}") from e
