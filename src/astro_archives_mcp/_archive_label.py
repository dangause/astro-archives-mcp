"""Hybrid archive-label lookup.

Three-step resolution:
  1. Static substring map (no I/O, fast path)
  2. In-memory cache (process lifetime, no TTL)
  3. RegistryClient.find_label fallback (one RegTAP call, result cached)

Cache is keyed by the full endpoint URL (not just hostname) so distinct
services on the same host get distinct labels. Restart wipes it; archive
identities don't churn.
"""

# (substring → label). Substring matched lowercase against the full URL.
_STATIC_MAP: dict[str, str] = {
    "datalab.noirlab": "datalab",
    "almascience": "alma",
    "data-query.nrao": "nrao_vla",
    "archive.eso": "eso",
    "gea.esac.esa": "gaia",
    "cadc-ccda.hia-iha": "cadc",
    "ws.cadc-ccda": "cadc",
    "sdss.org": "sdss",
}

_CACHE: dict[str, str] = {}


def archive_label(endpoint: str) -> str:
    """Resolve an endpoint URL to a short archive label."""
    low = endpoint.lower()
    for needle, label in _STATIC_MAP.items():
        if needle in low:
            return label

    if endpoint in _CACHE:
        return _CACHE[endpoint]

    discovered = _registry_find_label(endpoint)
    label = discovered or "other"
    _CACHE[endpoint] = label
    return label


def _registry_find_label(endpoint: str) -> str | None:
    """Thin indirection so tests can patch it without instantiating RegistryClient."""
    # Lazy import to avoid pulling pyvo into modules that don't need it
    # (and to keep _archive_label cheap to import at module load).
    from astro_archives_mcp.backends.registry import RegistryClient
    return RegistryClient().find_label(endpoint)
