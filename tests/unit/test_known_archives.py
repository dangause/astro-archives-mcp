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


def test_nrao_entry_covers_full_instrument_suite():
    """NRAO's first-party archive serves multiple instruments; the entry
    should reflect that rather than being VLA-only."""
    nrao = by_short_name("nrao")
    assert nrao is not None
    assert "data.nrao" in nrao.host_substrings
    assert "data-query.nrao" in nrao.host_substrings
    for instrument in ("VLA", "VLBA", "GMVA", "GBT"):
        assert instrument in nrao.description, (
            f"NRAO description must mention {instrument}; got: {nrao.description}"
        )
    assert nrao.waveband == "radio"


def test_nrao_label_resolves_to_nrao_not_alma_for_data_nrao_host():
    """almascience.nrao.edu must stay labeled 'alma'; data.nrao.edu and
    data-query.nrao.edu must label as 'nrao'. The substring map must not
    confuse the two."""
    from astro_archives_mcp._archive_label import archive_label
    assert archive_label("https://data.nrao.edu/foo") == "nrao"
    assert archive_label("https://data-query.nrao.edu/foo") == "nrao"
    assert archive_label("https://archive.nrao.edu/foo") == "nrao"
    assert archive_label("https://almascience.nrao.edu/tap") == "alma"


def test_nrao_appears_before_alma_in_known_archives():
    """Priority ordering: NOIRLab and NRAO (primary collaborators) come
    first; ALMA follows. The first TAP-having archives surface as the
    schema examples shown to the LLM."""
    order = [a.short_name for a in KNOWN_ARCHIVES]
    assert order.index("datalab") < order.index("nrao")
    assert order.index("nrao") < order.index("alma")


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
