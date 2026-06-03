from astro_archives_mcp.config import Settings


def test_settings_defaults():
    s = Settings(_env_file=None)
    assert s.host == "0.0.0.0"
    assert s.port == 8000
    assert s.deployment == "local"
    assert s.log_level == "INFO"


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("STABLE_PORT", "9001")
    monkeypatch.setenv("STABLE_DEPLOYMENT", "adl")
    s = Settings(_env_file=None)
    assert s.port == 9001
    assert s.deployment == "adl"
