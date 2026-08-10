"""Stable query fingerprints for the client-side result cache.

The fingerprint names the CSV a client saves a result to
(``manna_cache/<fingerprint>.csv`` — see shaper.build_save_recipe). It must
be stable across sessions and across incidental whitespace differences in
the same query, and distinct for different queries/endpoints/tools.

Normalization is deliberately minimal: strip + collapse whitespace runs.
No case-folding — ADQL string literals ('M87') are case-significant, and
folding would merge distinct queries. The algorithm is private to the
server (clients match on catalog query text, not by recomputing hashes),
so it can evolve without orphaning existing cache files.
"""

import hashlib
import re

_WHITESPACE = re.compile(r"\s+")


def query_fingerprint(tool: str, endpoint: str, identity: str) -> str:
    """First 12 hex chars of sha256 over 'tool|endpoint|normalized identity'.

    tool is one of "tap" | "cone" | "sia"; identity is the ADQL text (TAP)
    or the canonical parameter summary (cone/SIA — built by the tool).
    """
    normalized = _WHITESPACE.sub(" ", identity.strip())
    canonical = f"{tool}|{endpoint}|{normalized}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
