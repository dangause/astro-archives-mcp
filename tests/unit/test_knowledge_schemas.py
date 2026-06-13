"""Schema dataclass + SCHEMA_KB contract tests."""
from datetime import date
from types import MappingProxyType

import pytest

from astro_archives_mcp.knowledge.schemas import (
    SCHEMA_KB,
    Schema,
    lookup_schema,
)
from astro_archives_mcp.known_archives import KNOWN_ARCHIVES

# ---------- Schema dataclass ----------

def test_schema_is_frozen():
    s = Schema(
        archive="nrao", table="tap_schema.obscore",
        last_verified=date(2026, 6, 13),
    )
    with pytest.raises(AttributeError):  # FrozenInstanceError is a subclass
        s.archive = "mutated"  # type: ignore[misc]


def test_schema_last_verified_is_required():
    """No default — making it mandatory at the dataclass level forces
    every seed entry to carry an honest date."""
    with pytest.raises(TypeError):
        Schema(archive="nrao", table="tap_schema.obscore")  # type: ignore[call-arg]


def test_schema_value_enums_default_is_read_only():
    s = Schema(
        archive="nrao", table="tap_schema.obscore",
        last_verified=date(2026, 6, 13),
    )
    assert isinstance(s.value_enums, MappingProxyType)
    with pytest.raises(TypeError):
        s.value_enums["x"] = ("y",)  # type: ignore[index]


def test_schema_value_enums_passed_as_dict_is_wrapped_read_only():
    """Seed entries use plain dict literals; __post_init__ wraps them."""
    s = Schema(
        archive="nrao", table="tap_schema.obscore",
        last_verified=date(2026, 6, 13),
        value_enums={"instrument_name": ("EVLA", "VLA", "VLBA", "GBT")},
    )
    assert isinstance(s.value_enums, MappingProxyType)
    assert s.value_enums["instrument_name"] == ("EVLA", "VLA", "VLBA", "GBT")
    with pytest.raises(TypeError):
        s.value_enums["facility_name"] = ("NRAO",)  # type: ignore[index]


def test_schema_cross_refs_is_nested_tuple_shape():
    s = Schema(
        archive="nrao", table="tap_schema.obscore",
        last_verified=date(2026, 6, 13),
        cross_refs=(("alma", "ivoa.obscore"),),
    )
    assert s.cross_refs == (("alma", "ivoa.obscore"),)


# ---------- lookup ----------

def test_lookup_schema_finds_known_entry():
    """The Task-3 smoke entry — Task 4 fleshes the rest out."""
    s = lookup_schema(archive="nrao", table="tap_schema.obscore")
    assert s is not None
    assert s.archive == "nrao"
    assert s.table == "tap_schema.obscore"


def test_lookup_schema_returns_none_for_unknown_pair():
    assert lookup_schema(archive="bogus", table="bogus") is None


def test_lookup_schema_is_case_sensitive():
    """No matching is exact per spec §3.3."""
    assert lookup_schema(archive="NRAO", table="tap_schema.obscore") is None
    assert lookup_schema(archive="nrao", table="TAP_SCHEMA.OBSCORE") is None


# ---------- SCHEMA_KB integrity ----------

def test_every_schema_archive_is_a_known_archive_short_name():
    valid_short_names = {a.short_name for a in KNOWN_ARCHIVES}
    for s in SCHEMA_KB:
        assert s.archive in valid_short_names, (
            f"Schema entry archive={s.archive!r} is not a known archive "
            f"short_name. Available: {sorted(valid_short_names)}"
        )


def test_no_two_schemas_share_an_archive_table_pair():
    seen: set[tuple[str, str]] = set()
    for s in SCHEMA_KB:
        key = (s.archive, s.table)
        assert key not in seen, (
            f"Duplicate Schema entry for {key}; collapse the duplicates"
        )
        seen.add(key)


def test_every_cross_ref_resolves_to_another_schema_entry():
    by_pair = {(s.archive, s.table): s for s in SCHEMA_KB}
    for s in SCHEMA_KB:
        for archive, table in s.cross_refs:
            assert (archive, table) in by_pair, (
                f"Schema({s.archive}, {s.table}).cross_refs references "
                f"{(archive, table)} but no such entry exists in SCHEMA_KB"
            )


def test_every_seed_entry_has_a_real_last_verified_date():
    """Catches a regression where someone makes `last_verified` optional."""
    for s in SCHEMA_KB:
        assert isinstance(s.last_verified, date)
        # Sanity bound: not in the future, not before the project existed.
        assert s.last_verified <= date.today()
        assert s.last_verified >= date(2026, 6, 1)
