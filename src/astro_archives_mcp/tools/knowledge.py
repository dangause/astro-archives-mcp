"""Tool for querying the curated per-table schema knowledge layer.

`vo_schema_describe(archive, table)` augments live introspection — the
agent's natural flow is to call this BEFORE composing an ADQL query, so
it learns about NRAO's missing `dataproduct_subtype` column, ALMA's
spectral-window row granularity, etc., without paying the trial-and-
error cost of discovering them through failed queries.

Soft-fails on miss (returns `known: false`) so the LLM cleanly falls
back to `vo_registry_describe` for archives/tables we haven't yet
curated.
"""
from datetime import date
from typing import Annotated

from pydantic import Field

from astro_archives_mcp.config import Settings
from astro_archives_mcp.errors import ValidationError, wrap_tool_errors
from astro_archives_mcp.knowledge import lookup_schema, schema_to_dict
from astro_archives_mcp.tools._constants import _ERROR_DOCSTRING


def _staleness_days_threshold() -> int:
    """Thin indirection so tests can monkey-patch the threshold without
    rebuilding the whole Settings."""
    return Settings().schema_kb_staleness_days


@wrap_tool_errors
def vo_schema_describe(
    archive: Annotated[
        str,
        Field(
            description=(
                "Archive short_name (e.g. 'nrao', 'datalab', 'alma'). "
                "Use vo_archive_list to discover available names."
            ),
            examples=["nrao", "datalab", "alma"],
        ),
    ],
    table: Annotated[
        str,
        Field(
            description=(
                "Fully qualified table name as it appears in the "
                "archive's TAP schema (e.g. 'tap_schema.obscore', "
                "'ivoa.obscore', 'nsc_dr2.object')."
            ),
            examples=["tap_schema.obscore", "ivoa.obscore", "nsc_dr2.object"],
        ),
    ],
) -> dict:
    """Curated quirks for one archive table. Augments live introspection.

    Returns the curated entry — missing standard columns, value enums,
    notes, cross_refs — along with a `last_verified` date, `stale`
    flag, and `stale_days` so the agent can hedge old claims.

    On miss returns `{"known": false, "archive": ..., "table": ...}`
    with no other keys. The agent should fall back to
    `vo_registry_describe` for the full schema.

    `stale` is true when `stale_days >= STABLE_SCHEMA_KB_STALENESS_DAYS`
    (default 90). Stale entries should be treated as priors to check,
    not facts to act on.
    """
    archive_clean = archive.strip()
    table_clean = table.strip()
    if not archive_clean or not table_clean:
        raise ValidationError(
            message=(
                "Both 'archive' and 'table' must be non-empty. Use "
                "vo_archive_list to discover archive short_names."
            ),
        )

    s = lookup_schema(archive=archive_clean, table=table_clean)
    if s is None:
        return {
            "known": False,
            "archive": archive_clean,
            "table": table_clean,
        }

    serialized = schema_to_dict(s)
    # Clamp at 0: a future "last_verified" (clock skew, pre-dated seed)
    # is not negatively stale.
    stale_days = max(0, (date.today() - s.last_verified).days)
    # `>=` so threshold=0 trips every entry (used by tests to pin the
    # comparison direction without re-seeding the KB).
    stale = stale_days >= _staleness_days_threshold()
    return {
        "known": True,
        **serialized,
        "stale": stale,
        "stale_days": stale_days,
    }


vo_schema_describe.__doc__ = (vo_schema_describe.__doc__ or "") + _ERROR_DOCSTRING
