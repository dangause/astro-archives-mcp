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


_VERIFIED = date(2026, 6, 13)

SCHEMA_KB: tuple[Schema, ...] = (
    Schema(
        archive="nrao",
        table="tap_schema.obscore",
        last_verified=_VERIFIED,
        missing_standard_columns=("dataproduct_subtype",),
        value_enums={
            "instrument_name": ("EVLA", "VLA", "VLBA", "GBT"),
            "facility_name": ("NRAO",),
        },
        notes=(
            "Rows are scan-level, not execution-block-level. GROUP BY "
            "project_code (e.g. '13B-088', 'VLASS3.2') or "
            "obs_publisher_did for per-observation summaries.",
            "Both freq_min/freq_max (Hz) and em_min/em_max (m, standard "
            "ObsCore) are populated but disagree by ~1% on the same row. "
            "Don't trust either to better than that without checking the "
            "spectral_resolutions column.",
            "USE mode='async' for queries selecting from this table. The "
            "/sync TAP endpoint returns 5xx errors on data reads here.",
            "ADQL LOWER() and UPPER() FAIL server-side (spec violation). "
            "Use exact-case equality on enum values; LIKE patterns work.",
            "On phase=ERROR, the UWS error_summary is always empty. "
            "Isolate failures by simplifying the query, not by parsing "
            "the missing diagnostic.",
        ),
        cross_refs=(
            ("alma", "ivoa.obscore"),
        ),
    ),
    Schema(
        archive="alma",
        table="ivoa.obscore",
        last_verified=_VERIFIED,
        notes=(
            "Rows are at the spectral-window / tuning granularity, NOT "
            "execution-block. A single observing execution produces "
            "multiple rows (one per spectral window). For 'N most recent "
            "epochs' style queries, GROUP BY t_min (or obs_publisher_did) "
            "to collapse to distinct executions.",
            "Positional CONTAINS(POINT(...), CIRCLE(...)) queries have "
            "been observed to fail or hit timeouts on this obscore. "
            "Consider mode='async' or fall back to target_name LIKE "
            "filtering when geometry misbehaves.",
            "Mirrored at almascience.nrao.edu (NA), almascience.eso.org "
            "(EU), and almascience.nao.ac.jp (EA). All three TAP endpoints "
            "serve identical data; we model only the NA endpoint as the "
            "canonical 'alma' archive.",
        ),
    ),
    Schema(
        archive="cadc",
        table="ivoa.obscore",
        last_verified=_VERIFIED,
        notes=(
            "SIA2 results carry access_format = "
            "'application/x-votable+xml;content=datalink'. The access_url "
            "is a DataLink VOTable, NOT the FITS file. Follow the "
            "semantics='#this' link in the VOTable to find the real "
            "image URL (which may live at mast.stsci.edu or S3 — follow "
            "redirects).",
            "Use obs_collection to filter by mission ('TESS', 'JWST', "
            "'CFHT', 'HST', etc.).",
        ),
    ),
    Schema(
        archive="datalab",
        table="nsc_dr2.object",
        last_verified=_VERIFIED,
        notes=(
            "Bright/extended sources (BCGs, large galaxies) commonly "
            "carry blend flags (flags=3). Filtering with flags=0 "
            "silently excludes them. When searching dense regions, drop "
            "the flag filter or post-filter client-side.",
            "ADQL geometric functions (DISTANCE, POINT, CIRCLE, CONTAINS, "
            "INTERSECTS) are NOT translated by the Data Lab backend "
            "(spec violation). Use bounding-box predicates: `ra BETWEEN "
            "<lo> AND <hi> AND dec BETWEEN <lo> AND <hi>`.",
            "Per Data Lab's documented caveats, NUMERIC columns may be "
            "exposed via TAP as VARCHAR to preserve precision for large "
            "identifier values. Treat large IDs as strings; cast only "
            "when arithmetic is needed.",
            "The table carries convenience columns for indexed spatial "
            "filtering: htm9 (~10 arcmin), healpix_ring256 (~14 arcmin), "
            "healpix_nest4096 (~52 arcsec). These work in bounding-box "
            "queries even when the ADQL geometry functions don't.",
        ),
    ),
    Schema(
        archive="datalab",
        table="smash_dr2.object",
        last_verified=_VERIFIED,
        notes=(
            "Same ADQL-geometry gap as nsc_dr2.object — use bounding-box "
            "predicates, not CIRCLE/CONTAINS.",
            "SCS URL for this survey is "
            "https://datalab.noirlab.edu/scs/smash_dr2/object, NOT "
            "/scs/smash_dr2. The dataset-only path returns 404.",
        ),
        cross_refs=(
            ("datalab", "nsc_dr2.object"),
        ),
    ),
    Schema(
        archive="datalab",
        table="tap_schema.tables",
        last_verified=_VERIFIED,
        notes=(
            "Per-survey schema-namespacing pattern: each survey lives in "
            "its own schema (smash_dr2.*, nsc_dr2.*, des_dr2.*, "
            "decaps_dr2.*, etc.). Inside each schema the main table is "
            "usually <schema>.object.",
            "Data Lab Python SDK call `dl.queryClient.services()` is the "
            "authoritative catalog of all ~180 services (SCS / SIA / TAP / "
            "VOS) across surveys. Equivalent IVOA registry coverage exists "
            "under ivo://noirlab.edu/...",
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
