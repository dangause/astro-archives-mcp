"""Tool for surfacing the curated KNOWN_ARCHIVES registry to the LLM.

`vo_archive_list` is the agent-facing entry point into the project's
knowledge base of well-known IVOA archives. Each returned entry carries
the canonical endpoint URLs, capabilities, notable tables, and — most
importantly — `usage_notes` that capture archive-specific gotchas
(non-standard table locations, sync-vs-async routing, target-name
conventions, etc.).

This is the early scaffolding for what will become a richer knowledge
layer. Today it surfaces `known_archives.KNOWN_ARCHIVES` directly;
later it will be backed by something pluggable (RAG, structured KB,
etc.) but the tool contract stays the same.
"""
from dataclasses import asdict
from typing import Any

from astro_archives_mcp.errors import wrap_tool_errors
from astro_archives_mcp.known_archives import KNOWN_ARCHIVES
from astro_archives_mcp.tools._constants import _ERROR_DOCSTRING


def _archive_to_dict(a) -> dict[str, Any]:
    """Convert an Archive dataclass to a JSON-friendly dict.

    Tuples (host_substrings, notable_tables, usage_notes) become lists
    so they serialize cleanly through MCP.
    """
    d = asdict(a)
    for k in ("host_substrings", "notable_tables", "usage_notes"):
        if k in d and isinstance(d[k], tuple):
            d[k] = list(d[k])
    return d


@wrap_tool_errors
def vo_archive_list() -> dict:
    """List the IVOA archives this server has first-class knowledge of.

    Each entry includes the archive's endpoint URLs (TAP / SIA / SCS),
    waveband, description, notable tables, and **usage_notes** — short
    agent-facing strings capturing archive-specific gotchas like
    non-standard table locations, sync-vs-async routing recommendations,
    target-name conventions, and ADQL quirks.

    Call this FIRST when planning a query against an archive whose
    behavior you don't already know — it'll save you the trial-and-error
    of discovering quirks through failed queries. The notes are curated
    based on real friction encountered while building the server.

    Archives not listed here still work via `vo_registry_search` followed
    by `vo_registry_describe` / `vo_tap_query` — this tool only covers the
    well-known set.

    Returns:
        {
          "archives": [
            {
              "short_name": "...",
              "display_name": "...",
              "host_substrings": ["..."],
              "tap_url": "...",
              "sia_url": "..." | null,
              "scs_url": "..." | null,
              "waveband": "...",
              "description": "...",
              "notable_tables": ["..."],
              "usage_notes": [
                "Short agent-facing strings — read these BEFORE composing "
                "a query. They capture real gotchas like non-standard "
                "table names, required mode='async' routing, target-name "
                "aliasing, etc."
              ]
            },
            ...
          ],
          "count": N
        }
    """
    archives = [_archive_to_dict(a) for a in KNOWN_ARCHIVES]
    return {"archives": archives, "count": len(archives)}


vo_archive_list.__doc__ = (vo_archive_list.__doc__ or "") + _ERROR_DOCSTRING
