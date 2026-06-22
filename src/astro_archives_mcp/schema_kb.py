"""Curated per-table schema knowledge base (Tier 2).

SCHEMA_KB stores table-specific SURPRISES only — missing standard columns,
value enums for filterable fields, spatial index columns, naming conventions.
Archive-level quirks (ADQL bugs, endpoint routing, mode requirements) belong
in known_archives.Archive.usage_notes instead, NOT here.

Live introspection via vo_registry_describe is the authoritative source for
the full column list; this KB only adds human-curated context not derivable
from the schema alone.

Forking note: deployments that only target a subset of archives should prune
SCHEMA_KB to just the relevant entries (same as pruning KNOWN_ARCHIVES).
No other file needs to be touched.

To add a new entry: append a Schema(...) to SCHEMA_KB.
"""

from dataclasses import dataclass, field

from astro_archives_mcp._serialization import dataclass_to_jsonable_dict


@dataclass(frozen=True)
class Schema:
    """Curated knowledge about ONE table at one archive."""

    archive: str
    table: str

    missing_standard_columns: tuple[str, ...] = ()
    value_enums: dict[str, tuple[str, ...]] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    # 2-tuple form, not "archive:table" strings, to avoid parsing fragility.
    cross_refs: tuple[tuple[str, str], ...] = ()


SCHEMA_KB: tuple[Schema, ...] = (
    Schema(
        archive="nrao",
        table="tap_schema.obscore",
        missing_standard_columns=("dataproduct_subtype",),
        value_enums={
            "instrument_name": ("EVLA", "VLA", "VLBA", "GBT"),
            "facility_name": ("NRAO",),
        },
    ),
    Schema(
        archive="datalab",
        table="nsc_dr2.object",
        notes=(
            "Convenience columns for indexed spatial filtering: htm9 "
            "(~10 arcmin), healpix_ring256 (~14 arcmin), "
            "healpix_nest4096 (~52 arcsec). These work in bounding-box "
            "queries even when ADQL geometry functions don't.",
        ),
    ),
    Schema(
        archive="datalab",
        table="smash_dr2.object",
        notes=(
            "SCS URL is https://datalab.noirlab.edu/scs/smash_dr2/object, "
            "NOT /scs/smash_dr2. The dataset-only path returns 404.",
        ),
        cross_refs=(("datalab", "nsc_dr2.object"),),
    ),
    Schema(
        archive="datalab",
        table="tap_schema.tables",
        notes=(
            "Crossmatch tables (nearest-neighbor 1.5 arcsec against "
            "AllWISE / Gaia DR3 / NSC DR2 / SDSS DR17 / unWISE DR1) carry "
            "an x1p5 suffix, e.g. "
            "phat_v3.x1p5__phot_mod__gaia_dr3__gaia_source.",
        ),
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


def schema_to_dict(s: Schema) -> dict:
    """Serialize a Schema for inclusion in a tool's JSON envelope."""
    return dataclass_to_jsonable_dict(s)
