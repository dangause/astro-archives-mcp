import io
import json
import math
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from astropy.table import Table

from astro_archives_mcp import result_store

INLINE_ROW_LIMIT = 1_000
INLINE_BYTE_LIMIT = 512 * 1024
RESOURCE_ROW_LIMIT = 100_000
TRUNCATION_REASON_MAXREC = "maxrec_exceeded"
TRUNCATION_REASON_OVERSIZE = "oversize_for_resource_tier"


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


def shape_table(table: Table, *, archive: str, maxrec: int) -> dict[str, Any]:
    """Pick inline or Resource tier based on size; build the envelope.

    Public entry point for tabular tools. Delegates to:
    - shape_inline_table for small results (unchanged behavior)
    - _shape_resource for results above the inline threshold
    """
    n_rows = len(table)
    if n_rows <= INLINE_ROW_LIMIT:
        envelope = shape_inline_table(table, archive=archive, maxrec=maxrec)
        if _estimate_payload_bytes(envelope) <= INLINE_BYTE_LIMIT:
            return envelope
    return _shape_resource(table, archive=archive, maxrec=maxrec)


def _estimate_payload_bytes(envelope: dict) -> int:
    """Cheap upper bound on JSON-serialized size of the envelope."""
    return len(json.dumps(envelope, default=str))


def _shape_resource(table: Table, *, archive: str, maxrec: int) -> dict[str, Any]:
    """Build the Resource-tier envelope: preview + Parquet via MCP Resource URI."""
    true_count = len(table)
    visible = table[:RESOURCE_ROW_LIMIT]
    truncated = true_count > RESOURCE_ROW_LIMIT

    # astropy.Table -> pyarrow.Table -> Parquet bytes (no pandas dep)
    pa_table = pa.table({name: visible[name].data for name in visible.colnames})
    buf = io.BytesIO()
    pq.write_table(pa_table, buf)
    uuid_hex, expires_at = result_store.put(buf.getvalue(), "application/vnd.apache.parquet")

    # Reuse inline envelope shape for preview rows
    preview_envelope = shape_inline_table(
        visible[:50], archive=archive, maxrec=maxrec,
    )

    hints: list[dict[str, Any]] = []
    if truncated:
        hints.append({
            "kind": "tip",
            "text": (
                f"{RESOURCE_ROW_LIMIT} of {true_count} rows available at the "
                "resource URI. For full results, narrow the query or use "
                "MyDB-staged storage (Slice C)."
            ),
            "source": None,
        })

    return {
        "row_count": true_count,
        "columns": preview_envelope["columns"],
        "rows": None,
        "preview": preview_envelope["rows"],
        "resource_uri": f"resource://results/{uuid_hex}.parquet",
        "resource_expires_at": expires_at.isoformat(),
        "mydb_table": None,
        "truncated": truncated,
        "truncation_reason": TRUNCATION_REASON_OVERSIZE if truncated else None,
        "archive": archive,
        "next_steps": None,
        "hints": hints,
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


def shape_registry_search_result(services: list[dict], *, maxrec: int) -> dict:
    """Envelope for vo_registry_search results."""
    truncated = len(services) > maxrec
    visible = services[:maxrec] if truncated else services
    return {
        "services": visible,
        "row_count": len(visible),
        "truncated": truncated,
        "truncation_reason": "maxrec_exceeded" if truncated else None,
    }


def shape_registry_describe_result(described: dict) -> dict:
    """Pass-through envelope for vo_registry_describe."""
    return dict(described)
