import math

import numpy as np
from astropy.table import Table

from astro_archives_mcp.shaper import shape_inline_table


def _astropy_table_basic() -> Table:
    t = Table()
    t["ra"] = [185.43, 186.0]
    t["ra"].unit = "deg"
    t["ra"].description = "Right ascension"
    t["dec"] = [-31.99, -31.5]
    t["dec"].unit = "deg"
    t["gmag"] = [18.4, 19.1]
    return t


def test_inline_envelope_basic_shape():
    table = _astropy_table_basic()
    out = shape_inline_table(table, archive="datalab", maxrec=10)
    assert out["row_count"] == 2
    assert out["truncated"] is False
    assert out["truncation_reason"] is None
    assert out["resource_uri"] is None
    assert out["mydb_table"] is None
    assert out["archive"] == "datalab"
    assert len(out["rows"]) == 2
    assert out["preview"] is None
    assert out["next_steps"] is None
    assert out["hints"] == []

    cols_by_name = {c["name"]: c for c in out["columns"]}
    assert cols_by_name["ra"]["unit"] == "deg"
    assert cols_by_name["ra"]["description"] == "Right ascension"


def test_truncation_marked_when_rows_exceed_maxrec():
    table = _astropy_table_basic()
    out = shape_inline_table(table, archive="datalab", maxrec=1)
    assert out["row_count"] == 1
    assert out["truncated"] is True
    assert out["truncation_reason"] == "maxrec_exceeded"
    assert len(out["rows"]) == 1


def test_masked_values_become_json_null():
    t = Table()
    t["x"] = np.ma.MaskedArray([1.0, 2.0], mask=[False, True])
    out = shape_inline_table(t, archive="datalab", maxrec=10)
    assert out["rows"][0][0] == 1.0
    assert out["rows"][1][0] is None


def test_nan_becomes_json_null():
    t = Table()
    t["x"] = [1.0, math.nan]
    out = shape_inline_table(t, archive="datalab", maxrec=10)
    assert out["rows"][1][0] is None
