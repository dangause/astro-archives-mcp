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
        archive="alma",
        table="ivoa.obscore",
        # Extended ObsCore 1.1 view — all mandatory ObsCore columns present.
        value_enums={
            # Controlled vocabulary (full-table DISTINCT). Empty string also
            # occurs for rows with no assigned category.
            "scientific_category": (
                "Active galaxies",
                "Cosmology",
                "Disks and planet formation",
                "Galaxy evolution",
                "ISM and star formation",
                "Local Universe",
                "Solar system",
                "Stars and stellar evolution",
                "Sun",
            ),
            "dataproduct_type": ("cube", "image"),
            "data_rights": ("Public", "Proprietary"),
            # 'T'/'F' char flags, not SQL booleans.
            "science_observation": ("T", "F"),
            "qa2_passed": ("T", "F"),
        },
        notes=(
            "member_ous_uid identifies a downloadable dataset (Member OUS). "
            "Rows are finer than that — one per spectral window per execution "
            "— so SELECT DISTINCT member_ous_uid is the way to count/collapse "
            "to datasets.",
            "Two spatial columns: s_ra/s_dec is the pointing centre (a point); "
            "s_region is the WKT footprint of the observed field. Use "
            "INTERSECTS(CIRCLE(...), s_region) to catch mosaics and fields "
            "whose centre lies outside a small search radius.",
            "band_list is a space-separated list of ALMA receiver bands "
            "present, e.g. '6' or '3 6 7'. Bands run 1, 3-10 (no band 2). "
            "Beware LIKE '%1%' — it also matches band 10; match an exact token "
            "(band_list = '6') or pad with delimiters.",
            "calib_level: 2 = Member-OUS (per-execution) products, 3 = "
            "Group-OUS (combined) products.",
            "frequency is the tuned sky reference frequency (GHz); "
            "frequency_support holds the full per-spectral-window frequency "
            "ranges. em_min/em_max are the standard ObsCore wavelengths (m).",
        ),
        cross_refs=(("nrao", "tap_schema.obscore"),),
    ),
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
