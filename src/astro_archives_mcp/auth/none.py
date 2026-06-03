from astro_archives_mcp.auth.base import CallerContext


class NoAuthProvider:
    """All requests resolve to anonymous; no creds injected."""

    async def authenticate(
        self, *, headers: dict[str, str], request_id: str
    ) -> CallerContext:
        return CallerContext(
            caller_id="anonymous",
            auth_mode="none",
            request_id=request_id,
        )
