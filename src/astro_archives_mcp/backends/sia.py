import logging

import pyvo
from astropy.table import Table
from pyvo.dal.exceptions import DALAccessError, DALQueryError

from astro_archives_mcp.errors import ArchiveError, DalQueryError

log = logging.getLogger(__name__)


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
            kwargs: dict = {"pos": (ra, dec, size_deg)}
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
        if len(table) > maxrec:
            table = table[:maxrec]
        return table
