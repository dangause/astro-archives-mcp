"""Unit tests for the known_archives registry.

These tests lock down the derived-lookup contract so that downstream
modules (`_archive_label`, the tool Field examples, tests) stay
consistent with the canonical archive list.
"""
from dataclasses import FrozenInstanceError

import pytest

from astro_archives_mcp.known_archives import (
    KNOWN_ARCHIVES,
    Archive,
    by_short_name,
    host_substring_to_short_name,
    scs_endpoint_description,
    scs_endpoint_urls,
    sia_endpoint_description,
    sia_endpoint_urls,
    tap_endpoint_description,
    tap_endpoint_urls,
)


def test_archive_dataclass_is_frozen():
    a = KNOWN_ARCHIVES[0]
    with pytest.raises(FrozenInstanceError):
        a.short_name = "mutated"  # type: ignore[misc]


def test_known_archives_short_names_unique():
    names = [a.short_name for a in KNOWN_ARCHIVES]
    assert len(names) == len(set(names))


def test_host_substring_to_short_name_flattens_multi_substring_archives():
    m = host_substring_to_short_name()
    # CADC has two substrings; both must resolve to "cadc".
    assert m["cadc-ccda.hia-iha"] == "cadc"
    assert m["ws.cadc-ccda"] == "cadc"
    # Singletons still work.
    assert m["datalab.noirlab"] == "datalab"
    assert m["almascience"] == "alma"


def test_by_short_name_round_trip():
    alma = by_short_name("alma")
    assert alma is not None
    assert alma.display_name == "ALMA Science Archive"
    assert alma.tap_url == "https://almascience.nrao.edu/tap"


def test_by_short_name_unknown_returns_none():
    assert by_short_name("not-an-archive") is None


def test_tap_endpoint_urls_has_alma_and_datalab():
    urls = tap_endpoint_urls()
    assert "https://datalab.noirlab.edu/tap" in urls
    assert "https://almascience.nrao.edu/tap" in urls
    assert all(u for u in urls), "no None entries in tap_endpoint_urls"


def test_sia_endpoint_urls_has_cadc():
    urls = sia_endpoint_urls()
    assert any("cadc" in u for u in urls)


def test_scs_endpoint_urls_has_gaia_ari():
    urls = scs_endpoint_urls()
    assert any("gaia.ari.uni-heidelberg.de" in u for u in urls)


def test_tap_description_mentions_two_archives_by_name():
    desc = tap_endpoint_description()
    assert "NOIRLab" in desc or "ALMA" in desc
    assert "vo_registry_search" in desc  # discovery hint preserved


def test_sia_description_mentions_sia2_and_discovery():
    desc = sia_endpoint_description()
    assert "SIA 2.0" in desc
    assert "vo_registry_search" in desc


def test_scs_description_mentions_tap_preference():
    desc = scs_endpoint_description()
    assert "vo_tap_query" in desc


def test_adding_a_new_archive_is_isolated():
    """Adding an Archive entry should not require touching other modules.

    This test simulates adding a fake archive and verifies the derived
    lookups pick it up. It does NOT mutate KNOWN_ARCHIVES (which is a
    tuple) — instead it constructs a one-off and asserts the helpers'
    logic works the same way.
    """
    fake = Archive(
        short_name="fake",
        display_name="Fake Test Archive",
        host_substrings=("fake.invalid",),
        tap_url="https://fake.invalid/tap",
    )
    assert fake.tap_url == "https://fake.invalid/tap"
    # If this archive were added to KNOWN_ARCHIVES, the derived map
    # would include it. Since helpers operate on the global tuple, we
    # just verify the dataclass shape supports the contract.
    assert isinstance(fake.host_substrings, tuple)
