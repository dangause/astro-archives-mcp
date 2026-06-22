"""Hybrid archive-label lookup.

Three-step resolution:
  1. Static substring map derived from `known_archives.KNOWN_ARCHIVES`
     (no I/O, fast path)
  2. In-memory cache (process lifetime, no TTL)
  3. RegistryClient.find_label fallback (one RegTAP call, result cached)

Cache is keyed by the full endpoint URL (not just hostname) so distinct
services on the same host get distinct labels. Restart wipes it; archive
identities don't churn.

To add an archive to the static map, add it to `KNOWN_ARCHIVES` in
`known_archives.py`. Both `archive_label` and `is_known_archive_url`
pick it up automatically.
"""

from urllib.parse import urlparse

from astro_archives_mcp.known_archives import host_substring_to_short_name

# (substring → short_name). Substring matched lowercase against the full URL.
# Derived once at import from KNOWN_ARCHIVES; do not edit directly.
_STATIC_MAP: dict[str, str] = host_substring_to_short_name()

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


def is_known_archive_url(url: str) -> bool:
    """Return True iff the URL host substring-matches an entry in
    `_STATIC_MAP`.

    Used as an SSRF defense in `vo_sia_fetch`: the LLM may not pass
    arbitrary URLs to the server — only ones pointing at known IVOA
    archives. The function deliberately does NOT consult the registry
    fallback cache (`_CACHE`); otherwise an LLM could "warm" the cache
    via `vo_registry_describe(url=...)` and then bypass the check.
    """
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
    except (ValueError, TypeError):
        return False
    if not host:
        return False
    for needle in _STATIC_MAP:
        if needle in host:
            return True
    return False
