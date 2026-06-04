import logging

import pyvo
from astropy.table import Table
from pyvo.dal.exceptions import DALQueryError, DALServiceError

from astro_archives_mcp.errors import ArchiveError, DalQueryError

log = logging.getLogger(__name__)


class TapClient:
    """Sync TAP wrapper. Async / auto-promote arrives in a later slice."""

    def query(
        self,
        *,
        endpoint: str,
        adql: str,
        maxrec: int = 10_000,
    ) -> Table:
        try:
            service = pyvo.dal.TAPService(endpoint)
            result = service.search(adql, maxrec=maxrec)
        except DALQueryError as e:
            raise DalQueryError(message=str(e)) from e
        except DALServiceError as e:
            raise ArchiveError(message=str(e)) from e
        return result.to_table()
