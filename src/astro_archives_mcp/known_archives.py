"""Canonical registry of IVOA archives the server has first-class knowledge of.

This is the single source of truth for:

- Endpoint URLs surfaced in tool schemas (`Field(examples=...)`)
- Host substrings used by `_archive_label._STATIC_MAP` (archive labels +
  SSRF allow-list for `vo_sia_fetch`)
- Test fixtures (instead of duplicating URL strings)

Archives not listed here still work zero-touch via `vo_registry_search` —
this module is just for the well-known ones we want the LLM to see in
the tool schemas and operators to see labeled in responses.

To add a new archive: add one `Archive(...)` entry to `KNOWN_ARCHIVES`.
No other file needs to be touched. Derived structures (the substring
map, schema examples, allow-list) update automatically.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Archive:
    """Static facts about an IVOA archive.

    Fields are best-effort — most archives don't expose every protocol.
    `tap_url` / `sia_url` / `scs_url` are None when the archive doesn't
    have one we want to surface.

    `usage_notes` is a tuple of short, agent-facing strings capturing
    archive-specific gotchas — non-standard table locations, sync-vs-async
    routing recommendations, ADQL quirks, target-name conventions. These
    are surfaced to the LLM via the `vo_archive_list` tool and are the
    early scaffolding for what will eventually become a richer knowledge
    layer.
    """

    short_name: str
    display_name: str
    host_substrings: tuple[str, ...]
    tap_url: str | None = None
    sia_url: str | None = None
    scs_url: str | None = None
    waveband: str | None = None
    description: str = ""
    notable_tables: tuple[str, ...] = field(default_factory=tuple)
    usage_notes: tuple[str, ...] = field(default_factory=tuple)


KNOWN_ARCHIVES: tuple[Archive, ...] = (
    # Primary collaborator archives (NOIRLab + NRAO) come first so they
    # take the top two slots in tool schema examples.
    Archive(
        short_name="datalab",
        display_name="NOIRLab Astro Data Lab",
        host_substrings=("datalab.noirlab",),
        tap_url="https://datalab.noirlab.edu/tap",
        waveband="optical",
        description=(
            "Optical surveys: NSC, SMASH, DECaPS, DES. Large object catalogs."
        ),
        notable_tables=(
            "nsc_dr2.object",
            "smash_dr2.object",
            "des_dr2.main",
            "decaps_dr2.object",
        ),
        usage_notes=(
            "Each survey has its own schema namespace (smash_dr2, nsc_dr2, "
            "des_dr2, decaps_dr2). Use vo_registry_describe on the TAP URL "
            "to enumerate tables, or query `tap_schema.tables` directly.",
            "Cone-search via SCS only works for some surveys — the SMASH "
            "SCS endpoint returns 404 in particular. Prefer vo_tap_query "
            "against the survey's object table.",
            "ADQL geometric functions (DISTANCE, POINT, CIRCLE, CONTAINS, "
            "INTERSECTS) are NOT translated by the Data Lab backend, "
            "despite being mandatory per TAP 1.1. Use bounding-box "
            "predicates instead: `ra BETWEEN <lo> AND <hi> AND dec BETWEEN "
            "<lo> AND <hi>`. Trim to a true circle / compute separations "
            "client-side after fetching.",
            "Bright/extended sources in NSC DR2 (e.g. BCGs, large "
            "galaxies) commonly carry blend flags (flags=3). Filtering "
            "with flags=0 silently excludes them. When searching for "
            "bright objects in dense regions (cluster cores, etc.), drop "
            "the flag filter or post-filter client-side.",
        ),
    ),
    Archive(
        short_name="nrao",
        display_name="NRAO Science Data Archive",
        # Multiple historical hostnames for the NRAO archive web/query
        # interfaces. `almascience.nrao.edu` is intentionally NOT listed
        # here — that traffic is labeled "alma" via the entry below.
        host_substrings=("data.nrao", "data-query.nrao", "archive.nrao"),
        # TAP service per NRAO scripted-access docs:
        # https://science.nrao.edu/facilities/vla/archive/scripted-access-to-the-nrao-archive
        # Note: obscore table lives under `tap_schema.obscore`, not the
        # standard `ivoa.obscore` location used by ALMA/ESO.
        tap_url="https://data-query.nrao.edu/tap",
        waveband="radio",
        description=(
            "NRAO's unified data archive — serves VLA (historical + Karl G. "
            "Jansky VLA), VLBA, GMVA, and GBT (2014–2020) observations, "
            "plus mirrors ALMA archival products. Radio interferometric "
            "and single-dish data. ObsCore-style metadata table at "
            "tap_schema.obscore (NRAO uses a non-standard location for it)."
        ),
        notable_tables=("tap_schema.obscore",),
        usage_notes=(
            "USE mode='async' FOR ALL DATA QUERIES. The /sync TAP endpoint "
            "returns 5xx errors on reads against tap_schema.obscore — even "
            "for trivial `SELECT TOP 1 *`. Metadata queries against "
            "tap_schema.tables, tap_schema.columns work fine in sync.",
            "ObsCore is at `tap_schema.obscore`, NOT the standard "
            "`ivoa.obscore`. Queries against `ivoa.obscore` will fail.",
            "Rows are scan-level, not execution-block-level. For "
            "per-observation summaries, GROUP BY obs_collection (project "
            "code, e.g. '13B-088', 'VLASS3.2') or obs_publisher_did.",
            "Common radio sources are stored under their radio designations, "
            "not optical/popular names: Hydra-A → '3C218'; M87 → '3C274'; "
            "Cygnus A → '3C405'; Centaurus A → 'NGC5128'. If a target_name "
            "search returns nothing, try the radio designation or cone-search "
            "by position.",
            "ADQL aggregate support is partial. COUNT(DISTINCT ...) with "
            "CASE WHEN sometimes fails server-side. Prefer simpler aggregates "
            "(plain COUNT, MIN/MAX, GROUP BY) and assemble multi-aggregate "
            "results client-side.",
            "VLA-specific extension columns are available on tap_schema.obscore "
            "beyond the standard ObsCore set — array configuration, project "
            "code, antenna count, spectral window setup. Inspect columns via "
            "vo_registry_describe.",
        ),
    ),
    Archive(
        short_name="alma",
        display_name="ALMA Science Archive",
        host_substrings=("almascience",),
        tap_url="https://almascience.nrao.edu/tap",
        waveband="millimeter",
        description=(
            "Millimeter/submillimeter interferometric data from ALMA. "
            "Mirrored at NRAO (almascience.nrao.edu) and ESO. Schema "
            "follows ivoa.obscore."
        ),
        notable_tables=("ivoa.obscore",),
        usage_notes=(
            "Rows in ivoa.obscore are at the spectral-window / tuning "
            "granularity, NOT execution-block. A single observing execution "
            "produces multiple rows (one per spectral window). For "
            "'N most recent epochs' style queries, GROUP BY t_min (or "
            "obs_publisher_did) to collapse to distinct executions.",
            "Geometry queries using CONTAINS(POINT('ICRS', s_ra, s_dec), "
            "CIRCLE(...)) have been observed to fail or hit timeouts on "
            "ALMA's obscore. Consider mode='async' or fall back to a "
            "target_name LIKE filter when positional joins misbehave.",
            "Mirrored at almascience.nrao.edu (NA), almascience.eso.org "
            "(EU), and almascience.nao.ac.jp (EA). All three TAP endpoints "
            "serve identical data.",
        ),
    ),
    Archive(
        short_name="eso",
        display_name="ESO Science Archive",
        host_substrings=("archive.eso",),
        tap_url="https://archive.eso.org/tap_obs",
        waveband="optical",
        description="European Southern Observatory archive (VLT, La Silla).",
        notable_tables=("ivoa.ObsCore",),
    ),
    Archive(
        short_name="cadc",
        display_name="Canadian Astronomy Data Centre",
        host_substrings=("cadc-ccda.hia-iha", "ws.cadc-ccda"),
        tap_url="https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/tap",
        sia_url="https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/sia",
        waveband="multi",
        description=(
            "Multi-mission archive — TESS, JWST, CFHT, HST imaging "
            "available via SIA2."
        ),
        usage_notes=(
            "SIA2 results' `access_url` column points at a DataLink VOTable, "
            "NOT directly at the FITS file. The DataLink response describes "
            "where the actual image lives (often at MAST). Check the "
            "`access_format` field — `application/x-votable+xml;content=datalink` "
            "means you'll need to parse the VOTable to find the real URL.",
            "Use `obs_collection` to filter by mission: 'TESS', 'JWST', "
            "'CFHT', 'HST', etc.",
        ),
    ),
    Archive(
        short_name="gaia",
        display_name="ESA Gaia Archive",
        host_substrings=("gea.esac.esa",),
        tap_url="https://gea.esac.esa.int/tap-server/tap",
        waveband="optical",
        description="Authoritative Gaia mission archive at ESAC.",
        notable_tables=("gaiadr3.gaia_source", "gaiadr2.gaia_source"),
        usage_notes=(
            "Each Gaia data release is a separate schema (gaiadr2.*, "
            "gaiadr3.*, gaiaedr3.*, etc.). Newer releases supersede older "
            "ones for most use cases — default to gaiadr3.gaia_source.",
            "`source_id` is the canonical join key. Astrometric solutions, "
            "photometry, and radial velocities are split across multiple "
            "tables — JOIN to gaia_source on source_id.",
        ),
    ),
    Archive(
        short_name="gaia_ari",
        display_name="Gaia ARI Heidelberg",
        host_substrings=("gaia.ari.uni-heidelberg.de",),
        scs_url="https://gaia.ari.uni-heidelberg.de/cone/gaiadr2?",
        waveband="optical",
        description=(
            "Heidelberg's Gaia mirror — exposes a Simple Cone Search "
            "endpoint for legacy clients."
        ),
    ),
    Archive(
        short_name="sdss",
        display_name="Sloan Digital Sky Survey",
        host_substrings=("sdss.org",),
        waveband="optical",
        description="SDSS imaging and spectroscopic archive.",
    ),
)


# ---------- derived lookups ----------

def by_short_name(name: str) -> Archive | None:
    """Return the archive with the given short_name, or None."""
    for a in KNOWN_ARCHIVES:
        if a.short_name == name:
            return a
    return None


def host_substring_to_short_name() -> dict[str, str]:
    """Flatten host_substrings tuple into a substring → short_name map.

    Used by `_archive_label._STATIC_MAP`. Archives with multiple
    host substrings (e.g. CADC's two) contribute multiple entries
    mapping to the same short_name.
    """
    return {
        sub: archive.short_name
        for archive in KNOWN_ARCHIVES
        for sub in archive.host_substrings
    }


def tap_endpoint_urls() -> list[str]:
    """All TAP URLs we know about, in declaration order."""
    return [a.tap_url for a in KNOWN_ARCHIVES if a.tap_url]


def sia_endpoint_urls() -> list[str]:
    """All SIA URLs we know about, in declaration order."""
    return [a.sia_url for a in KNOWN_ARCHIVES if a.sia_url]


def scs_endpoint_urls() -> list[str]:
    """All SCS URLs we know about, in declaration order."""
    return [a.scs_url for a in KNOWN_ARCHIVES if a.scs_url]


# ---------- description helpers (used by tool Field descriptions) ----------

def _format_examples(archives: list[Archive], protocol: str) -> str:
    """Render a few example URLs inline for a tool's Field description.

    Used to keep the LLM-facing schema in sync with the canonical list
    without having to duplicate "'<url>' (<display_name>)" pairs by hand.
    """
    parts = []
    for a in archives:
        url = getattr(a, f"{protocol}_url")
        if url:
            parts.append(f"'{url}' ({a.display_name})")
    return " or ".join(parts)


def tap_endpoint_description() -> str:
    """The full description string for a TAP endpoint parameter."""
    primary = [a for a in KNOWN_ARCHIVES if a.tap_url][:2]
    return (
        f"Full TAP service URL. Example: {_format_examples(primary, 'tap')}. "
        "Discover other services via vo_registry_search."
    )


def sia_endpoint_description() -> str:
    """The full description string for a SIA endpoint parameter."""
    primary = [a for a in KNOWN_ARCHIVES if a.sia_url][:2]
    examples_text = _format_examples(primary, "sia")
    return (
        f"SIA 2.0 endpoint URL. Example: {examples_text}. "
        "Note: NOIRLab Data Lab is SIA v1; use SIA2-capable archives. "
        "Discover with vo_registry_search(servicetype='sia')."
    )


def scs_endpoint_description() -> str:
    """The full description string for a SCS endpoint parameter."""
    primary = [a for a in KNOWN_ARCHIVES if a.scs_url][:2]
    return (
        f"Simple Cone Search endpoint URL. Example: {_format_examples(primary, 'scs')}. "
        "Prefer vo_tap_query for archives that expose a TAP endpoint — "
        "vo_cone_search is here for SCS-only legacy services."
    )
