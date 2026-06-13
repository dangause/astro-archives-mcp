"""Curated per-table schema knowledge (Tier 2).

SCHEMA_KB is the single source of truth. Each entry captures SURPRISES
only — missing standard columns, value enums for filterable fields,
semantics quirks. Live introspection via vo_registry_describe is the
authoritative source for the full column list; this KB only adds
human-curated context that wouldn't be derivable.

To add a new entry: append a Schema(...) to SCHEMA_KB. Pin a
`last_verified` date — the tool surfaces staleness so old facts get
visibly flagged rather than silently misleading the agent.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType


@dataclass(frozen=True)
class Schema:
    """Curated knowledge about ONE table at one archive."""

    archive: str
    table: str
    # Required — see spec §3.1: no default means every seed entry must
    # carry an honest date. The on-the-wire envelope serializes this
    # as an ISO 8601 string.
    last_verified: date

    missing_standard_columns: tuple[str, ...] = ()

    # Stored as MappingProxyType (read-only view). Seed entries pass
    # plain dict literals; __post_init__ wraps them. See spec §3.1
    # for why both the dataclass-being-frozen AND a proxy are needed.
    value_enums: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )

    notes: tuple[str, ...] = ()

    # 2-tuple form, not "archive:table" strings: see spec §3.1 +
    # Appendix C for the parsing-fragility argument.
    cross_refs: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.value_enums, MappingProxyType):
            object.__setattr__(
                self, "value_enums", MappingProxyType(dict(self.value_enums))
            )


SCHEMA_KB: tuple[Schema, ...] = (
    # Smoke entry; Task 4 adds the rest.
    Schema(
        archive="nrao",
        table="tap_schema.obscore",
        last_verified=date(2026, 6, 13),
    ),
)


def lookup_schema(*, archive: str, table: str) -> Schema | None:
    """Linear scan of SCHEMA_KB. None if no curated entry.

    Matching is exact (case-sensitive) on both archive short_name and
    table name. Same shape as known_archives.by_short_name.
    """
    for s in SCHEMA_KB:
        if s.archive == archive and s.table == table:
            return s
    return None
