import dataclasses

import pytest

from astro_archives_mcp.auth.base import CallerContext
from astro_archives_mcp.auth.none import NoAuthProvider


def test_caller_context_archive_creds_default_empty():
    ctx = CallerContext(caller_id="anonymous", auth_mode="none", request_id="r-1")
    assert ctx.archive_creds == {}
    assert ctx.scopes == set()


def test_caller_context_is_frozen():
    ctx = CallerContext(caller_id="anonymous", auth_mode="none", request_id="r-1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.caller_id = "someone-else"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_no_auth_provider_yields_anonymous_context():
    provider = NoAuthProvider()
    ctx = await provider.authenticate(headers={}, request_id="r-2")
    assert ctx.caller_id == "anonymous"
    assert ctx.auth_mode == "none"
    assert ctx.archive_creds == {}
    assert ctx.request_id == "r-2"
