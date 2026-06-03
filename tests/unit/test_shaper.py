import math

import astropy.units as u
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


def test_string_column_normalizes_to_python_str():
    t = Table()
    t["name"] = ["alpha", "beta"]
    out = shape_inline_table(t, archive="datalab", maxrec=10)
    assert out["rows"][0] == ["alpha"]
    assert out["rows"][1] == ["beta"]
    assert all(isinstance(v, str) for v in (out["rows"][0][0], out["rows"][1][0]))


def test_int_column_stays_int():
    t = Table()
    t["count"] = np.array([1, 2, 3], dtype=np.int32)
    out = shape_inline_table(t, archive="datalab", maxrec=10)
    assert out["rows"][0] == [1]
    assert isinstance(out["rows"][0][0], int)


def test_ucd_picked_up_from_attribute():
    t = Table()
    t["ra"] = [185.43]
    # Mimic pyvo's behavior: UCD as first-class attribute on the Column.
    t["ra"].ucd = "pos.eq.ra;meta.main"
    out = shape_inline_table(t, archive="datalab", maxrec=10)
    cols_by_name = {c["name"]: c for c in out["columns"]}
    assert cols_by_name["ra"]["ucd"] == "pos.eq.ra;meta.main"


def test_ucd_picked_up_from_meta_lowercase():
    t = Table()
    t["dec"] = [-31.99]
    t["dec"].meta["ucd"] = "pos.eq.dec;meta.main"
    out = shape_inline_table(t, archive="datalab", maxrec=10)
    cols_by_name = {c["name"]: c for c in out["columns"]}
    assert cols_by_name["dec"]["ucd"] == "pos.eq.dec;meta.main"


def test_ucd_picked_up_from_meta_uppercase():
    t = Table()
    t["gmag"] = [18.4]
    t["gmag"].meta["UCD"] = "phot.mag;em.opt.g"
    out = shape_inline_table(t, archive="datalab", maxrec=10)
    cols_by_name = {c["name"]: c for c in out["columns"]}
    assert cols_by_name["gmag"]["ucd"] == "phot.mag;em.opt.g"


def test_dimensionless_unit_serializes_to_none():
    t = Table()
    t["count"] = [1, 2, 3]
    t["count"].unit = u.dimensionless_unscaled
    out = shape_inline_table(t, archive="datalab", maxrec=10)
    cols_by_name = {c["name"]: c for c in out["columns"]}
    assert cols_by_name["count"]["unit"] is None


def test_no_unit_no_description_no_ucd_all_none():
    t = Table()
    t["bare"] = [1.0]
    out = shape_inline_table(t, archive="datalab", maxrec=10)
    cols_by_name = {c["name"]: c for c in out["columns"]}
    assert cols_by_name["bare"]["unit"] is None
    assert cols_by_name["bare"]["description"] is None
    assert cols_by_name["bare"]["ucd"] is None
