from datetime import UTC, datetime

from astro_archives_mcp.shaper import shape_promotion


def test_shape_promotion_basic_envelope():
    submitted = datetime(2026, 6, 8, 14, 30, 0, tzinfo=UTC)
    env = shape_promotion(
        job_id="0abc123def45",
        archive="alma",
        phase="EXECUTING",
        submitted_at=submitted,
    )
    assert env["mode"] == "async"
    assert env["job_id"] == "0abc123def45"
    assert env["phase"] == "EXECUTING"
    assert env["archive"] == "alma"
    assert env["submitted_at"] == "2026-06-08T14:30:00+00:00"


def test_shape_promotion_next_steps_reference_lifecycle_tools():
    env = shape_promotion(
        job_id="0abc",
        archive="datalab",
        phase="QUEUED",
        submitted_at=datetime.now(UTC),
    )
    joined = " ".join(env["next_steps"])
    assert "vo_tap_status" in joined
    assert "vo_tap_results" in joined


def test_shape_promotion_omits_tabular_keys():
    # Disjoint shape: no rows, columns, preview, resource_uri.
    env = shape_promotion(
        job_id="0abc",
        archive="alma",
        phase="EXECUTING",
        submitted_at=datetime.now(UTC),
    )
    for key in ("rows", "columns", "preview", "resource_uri", "row_count"):
        assert key not in env, f"{key} must not appear in promotion envelope"
