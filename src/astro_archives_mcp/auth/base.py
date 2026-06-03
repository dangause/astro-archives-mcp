from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CallerContext:
    """Per-request identity + creds passed to every tool. Read-only."""
    caller_id: str
    auth_mode: str  # "none" | "bearer" | "oidc"
    request_id: str
    archive_creds: dict[str, str] = field(default_factory=dict)
    scopes: frozenset[str] = field(default_factory=frozenset)


class AuthProvider(Protocol):
    """Resolves an inbound request into a CallerContext."""
    async def authenticate(
        self, *, headers: dict[str, str], request_id: str
    ) -> CallerContext: ...
