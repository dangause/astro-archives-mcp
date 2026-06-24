import pytest

from astro_archives_mcp.backends.sia import SiaClient

SIA_ENDPOINT = "https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/sia"


@pytest.mark.vcr
def test_sia_returns_metadata_table_with_access_url():
    client = SiaClient()
    table = client.search(
        endpoint=SIA_ENDPOINT,
        ra=185.43,
        dec=-31.99,
        size_deg=0.05,
        band=None,
        fmt=None,
        maxrec=5,
    )
    cols = {c.lower() for c in table.colnames}
    # SIA2 results always include some form of access URL column
    assert any("access_url" in c or "access" in c for c in cols)
    assert len(table) <= 5


@pytest.mark.vcr
def test_sia_respects_maxrec_truncation():
    client = SiaClient()
    table = client.search(
        endpoint=SIA_ENDPOINT,
        ra=185.43,
        dec=-31.99,
        size_deg=0.2,
        band=None,
        fmt=None,
        maxrec=3,
    )
    assert len(table) <= 3
