import math
from typing import Any

import numpy as np
from astropy.table import Table


def shape_inline_table(
    table: Table,
    *,
    archive: str,
    maxrec: int,
) -> dict[str, Any]:
    """Convert an astropy.Table into the inline-tier response envelope.

    Inline tier only. Resource / MyDB tiers handled by other functions
    once result sizes warrant them.
    """
    n_in = len(table)
    truncated = n_in > maxrec
    if truncated:
        table = table[:maxrec]

    columns: list[dict[str, Any]] = []
    for name in table.colnames:
        col = table[name]
        columns.append({
            "name": name,
            "type": str(col.dtype),
            "unit": (str(col.unit) if col.unit and str(col.unit) else None),
            "ucd": _column_ucd(col),
            "description": col.description or None,
        })

    rows: list[list[Any]] = []
    for row in table:
        rows.append([_normalize(row[name]) for name in table.colnames])

    return {
        "row_count": len(rows),
        "columns": columns,
        "rows": rows,
        "preview": None,
        "resource_uri": None,
        "mydb_table": None,
        "truncated": truncated,
        "truncation_reason": "maxrec_exceeded" if truncated else None,
        "archive": archive,
        "next_steps": None,
        "hints": [],
    }


def _normalize(value: Any) -> Any:
    """Convert astropy / numpy scalars into JSON-friendly values; NaN/masked -> None."""
    if value is np.ma.masked:
        return None
    if hasattr(value, "mask") and bool(getattr(value, "mask", False)):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _column_ucd(col) -> str | None:
    """Resolve a column's UCD, checking the attribute first then meta variants.

    pyvo TAP results expose UCD via col.ucd. Hand-built astropy.Tables and some
    VOTable-loaded tables put it under col.meta['ucd'] or col.meta['UCD'].
    """
    direct = getattr(col, "ucd", None)
    if direct:
        return str(direct)
    meta = getattr(col, "meta", {}) or {}
    return meta.get("ucd") or meta.get("UCD")
