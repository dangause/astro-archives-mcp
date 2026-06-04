"""In-memory keyed bytes store with TTL.

Used by the Resource tier (shape_table) to stash large Parquet payloads
that are served via MCP Resource URIs. Process lifetime; lost on
restart. Single-instance (no cross-worker sharing — fine for Slice 3's
single-process deployment).

Eviction is check-on-read: when `get` finds an expired entry, it deletes
it before returning None. No background sweeper. A write-once-never-read
entry will sit in memory until restart, which is acceptable for the
expected traffic patterns.
"""

import threading
import uuid as _uuid
from datetime import UTC, datetime, timedelta

_STORE: dict[str, tuple[bytes, datetime]] = {}
_LOCK = threading.RLock()

_DEFAULT_TTL_SECONDS = 1800  # 30 minutes


def put(payload: bytes, ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> tuple[str, datetime]:
    """Store payload, return (uuid_hex, expires_at).

    The uuid_hex is a 12-character hex prefix from uuid4 — short enough
    to log readably, long enough that collisions are vanishingly rare
    within a process lifetime.
    """
    uuid_hex = _uuid.uuid4().hex[:12]
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    with _LOCK:
        _STORE[uuid_hex] = (payload, expires_at)
    return uuid_hex, expires_at


def get(uuid_hex: str) -> bytes | None:
    """Return payload if present and not expired. Evicts expired entries."""
    with _LOCK:
        entry = _STORE.get(uuid_hex)
        if entry is None:
            return None
        payload, expires_at = entry
        if datetime.now(UTC) >= expires_at:
            del _STORE[uuid_hex]
            return None
        return payload


def size_estimate() -> dict[str, int]:
    """Surfaced on /health for ops visibility."""
    with _LOCK:
        entries = len(_STORE)
        bytes_held = sum(len(payload) for payload, _ in _STORE.values())
    return {"entries": entries, "bytes": bytes_held}
