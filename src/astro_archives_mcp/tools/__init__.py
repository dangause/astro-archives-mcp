"""IVOA tools (sync, inline tier).

One tool per IVOA standard, split by protocol:
* TAP: tools.tap (vo_tap_query)
* Cone Search: tools.cone (vo_cone_search)
* Simple Image Access: tools.sia (vo_sia_search)
* Registry: tools.registry (vo_registry_search, vo_registry_describe)
* Archive directory: tools.archives (vo_archive_list)
"""

# Re-exports so `from astro_archives_mcp.tools import vo_tap_query` still works.
from astro_archives_mcp.tools.archives import vo_archive_list
from astro_archives_mcp.tools.cone import vo_cone_search
from astro_archives_mcp.tools.knowledge import vo_schema_describe
from astro_archives_mcp.tools.registry import vo_registry_describe, vo_registry_search
from astro_archives_mcp.tools.sia import vo_sia_fetch, vo_sia_search
from astro_archives_mcp.tools.tap import vo_tap_abort, vo_tap_query, vo_tap_results, vo_tap_status

__all__ = [
    "vo_archive_list",
    "vo_cone_search",
    "vo_registry_describe",
    "vo_registry_search",
    "vo_schema_describe",
    "vo_sia_fetch",
    "vo_sia_search",
    "vo_tap_abort",
    "vo_tap_query",
    "vo_tap_results",
    "vo_tap_status",
]
