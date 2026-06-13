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


def test_settings_has_tap_sync_timeout_default_20s():
    from astro_archives_mcp.config import Settings
    s = Settings()
    assert s.tap_sync_timeout_seconds == 20.0


def test_settings_has_job_ttl_default_1h():
    from astro_archives_mcp.config import Settings
    s = Settings()
    assert s.job_ttl_seconds == 3600


def test_settings_env_override_for_sync_timeout(monkeypatch):
    monkeypatch.setenv("STABLE_TAP_SYNC_TIMEOUT_SECONDS", "5")
    from astro_archives_mcp.config import Settings
    s = Settings()
    assert s.tap_sync_timeout_seconds == 5.0


def test_settings_has_schema_kb_staleness_days_default_90():
    from astro_archives_mcp.config import Settings
    s = Settings()
    assert s.schema_kb_staleness_days == 90


def test_settings_env_override_for_schema_kb_staleness_days(monkeypatch):
    monkeypatch.setenv("STABLE_SCHEMA_KB_STALENESS_DAYS", "30")
    from astro_archives_mcp.config import Settings
    s = Settings()
    assert s.schema_kb_staleness_days == 30
