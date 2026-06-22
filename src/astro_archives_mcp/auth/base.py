from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class CallerContext:
    """Per-request identity + creds passed to every tool. Read-only."""

    caller_id: str
    auth_mode: str  # "none" | "bearer" | "oidc"
    request_id: str
    # Providers should construct with `MappingProxyType(...)` to keep the view read-only.
    archive_creds: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    scopes: frozenset[str] = field(default_factory=frozenset)


@runtime_checkable
class AuthProvider(Protocol):
    """Resolves an inbound request into a CallerContext."""

    async def authenticate(self, *, headers: dict[str, str], request_id: str) -> CallerContext: ...
