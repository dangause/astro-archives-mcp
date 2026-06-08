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


KNOWN_ARCHIVES: tuple[Archive, ...] = (
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
    ),
    Archive(
        short_name="alma",
        display_name="ALMA Science Archive",
        host_substrings=("almascience",),
        tap_url="https://almascience.nrao.edu/tap",
        waveband="millimeter",
        description=(
            "Millimeter/submillimeter interferometric data from ALMA. "
            "Schema follows ivoa.obscore."
        ),
        notable_tables=("ivoa.obscore",),
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
    ),
    Archive(
        short_name="gaia",
        display_name="ESA Gaia Archive",
        host_substrings=("gea.esac.esa",),
        tap_url="https://gea.esac.esa.int/tap-server/tap",
        waveband="optical",
        description="Authoritative Gaia mission archive at ESAC.",
        notable_tables=("gaiadr3.gaia_source", "gaiadr2.gaia_source"),
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
        short_name="nrao_vla",
        display_name="NRAO Data Archive",
        host_substrings=("data-query.nrao",),
        waveband="radio",
        description="VLA and other NRAO radio telescope archives.",
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
