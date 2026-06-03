# Slice A — Server Skeleton + `vo_tap_query` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the first end-to-end vertical slice of the STABLE MCP server: a containerized FastMCP server exposing one IVOA tool (`vo_tap_query` against any public TAP endpoint), reachable via Streamable HTTP, with TDD discipline and CI in place. This kills risk on the architecture before we add real complexity.

**Architecture:** Single FastMCP 3.x server mounted under `/mcp` in a Starlette app alongside `/health` and `/ready`. One tool, one backend client (pyvo TAP, sync only), one auth provider (`NoAuthProvider`), one result tier (inline), four error classes. Async TAP, MyDB, knowledge layer, Resource tier, and OIDC are deferred to follow-on slices per the spec at `docs/superpowers/specs/2026-06-02-stable-mcp-design.md`.

**Tech Stack:** Python 3.12 · uv · FastMCP 3.x · Starlette · uvicorn · pyvo · pytest · pytest-asyncio · pytest-recording (vcrpy) · inline-snapshot · ruff · GitHub Actions · Docker · MCP Inspector CLI

**Spec:** `docs/superpowers/specs/2026-06-02-stable-mcp-design.md`

---

## What's in Slice A vs explicitly deferred

| In Slice A | Deferred (later slices) |
|---|---|
| FastMCP server + Streamable HTTP | stdio transport |
| `/health`, `/ready` | full OTel exporter wiring |
| `NoAuthProvider` only | `BearerTokenProvider`, OIDC |
| `vo_tap_query` (sync, no auto-promote) | `vo_tap_status/results/abort`, auto-promote, other 7 IVOA tools |
| `TapClient` (sync only) | all other backends |
| Inline result tier only | Resource tier, MyDB-staged tier, pagination, cursor |
| 4 error classes: `validation_error`, `archive_error`, `tap_query_error`, `internal_error` | `auth_required`, `auth_forbidden`, `archive_unavailable`, `oversize`, `timeout` |
| Container + manual deploy runbook | k8s manifests, OIDC config |
| GitHub Actions CI (lint + tests + container build + Inspector smoke) | Multi-arch builds, signed images |
| `kb_search`, `object_resolve`, all knowledge | Whole knowledge layer (its own plan) |

---

## File Structure

Files this plan creates or modifies, with one-line responsibility:

```
astro-archives-mcp/
├── .python-version                            # 3.12
├── .gitignore                                 # Python, uv, IDE, build, env
├── .dockerignore                              # exclude .venv, tests, docs, .git
├── pyproject.toml                             # uv-managed project metadata + deps
├── README.md                                  # quickstart for engineers
├── Dockerfile                                 # multi-stage slim, non-root
├── docker-compose.yml                         # local dev: server only
├── .env.example                               # documented env vars
├── src/astro_archives_mcp/
│   ├── __init__.py                            # __version__
│   ├── __main__.py                            # entry: python -m astro_archives_mcp
│   ├── app.py                                 # FastMCP + Starlette composition; /health, /ready
│   ├── config.py                              # Pydantic Settings (env-driven)
│   ├── observability.py                       # structured stdlib logging (OTel deferred)
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── base.py                            # CallerContext, AuthProvider Protocol
│   │   └── none.py                            # NoAuthProvider
│   ├── backends/
│   │   ├── __init__.py
│   │   └── tap.py                             # TapClient — sync pyvo wrapper
│   ├── tools/
│   │   ├── __init__.py
│   │   └── ivoa.py                            # vo_tap_query only
│   ├── shaper.py                              # inline-tier result envelope
│   └── errors.py                              # ToolExecutionError + 4-class taxonomy
├── tests/
│   ├── __init__.py
│   ├── conftest.py                            # in-memory MCP client fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_shaper.py
│   │   ├── test_errors.py
│   │   ├── test_caller_context.py
│   │   └── test_config.py
│   ├── backends/
│   │   ├── __init__.py
│   │   ├── test_tap_client.py
│   │   └── cassettes/                         # vcrpy cassettes (committed)
│   └── tools/
│       ├── __init__.py
│       └── test_vo_tap_query.py               # in-memory client integration
├── .github/workflows/
│   └── ci.yml                                 # lint + tests + container build + Inspector smoke
└── deploy/
    └── staging-runbook.md                     # how to deploy this image manually
```

---

## Sub-skills available

These are referenced inline below where useful:
- `@superpowers:test-driven-development` — for every new tool / backend method, write test first
- `@superpowers:verification-before-completion` — before any "done" claim, run the verification command
- `@superpowers:systematic-debugging` — when a test fails unexpectedly, don't guess; isolate

---

## Pre-flight: verify API surface before coding

Two libraries change fast enough that a 2-week-old assumption can bite. Before starting Task 1, verify:

- **FastMCP 3.x current `mcp.http_app()` + Starlette mount pattern.** Authoritative docs: <https://gofastmcp.com>. Look for "ASGI integration" / "mounting in Starlette." The pattern this plan uses is `Mount("/mcp", app=mcp.http_app())`. If the docs show a different mount call, use the docs version.
- **pyvo current `TAPService.search()` signature and `result.to_table()` behavior.** Authoritative docs: <https://pyvo.readthedocs.io>. The shapes used in this plan match pyvo 1.8.

If either differs, adjust the code in the relevant task — do **not** "fix" by adding shims around old APIs.

---

## Task 1: Project scaffold (uv + pyproject + git-ignore)

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.gitignore`, `.dockerignore`, `src/astro_archives_mcp/__init__.py`, `tests/__init__.py`
- Modify: `README.md` (replace empty file)

- [ ] **Step 1.1: Confirm uv is installed**

Run: `uv --version`
Expected: `uv 0.x.y` (any version ≥ 0.4 is fine). If not installed: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

- [ ] **Step 1.2: Create `.python-version`**

Write `.python-version` containing:
```
3.12
```

- [ ] **Step 1.3: Create `pyproject.toml`**

Write `pyproject.toml`:
```toml
[project]
name = "astro-archives-mcp"
version = "0.1.0"
description = "MCP server for IVOA-compliant astronomical archives"
requires-python = ">=3.12"
readme = "README.md"
license = { text = "MIT" }
authors = [{ name = "STABLE / CosmicAI", email = "noreply@example.invalid" }]
dependencies = [
    "fastmcp>=3.0,<4.0",
    "pyvo>=1.8,<2.0",
    "astropy>=6.0",
    "pydantic>=2.7",
    "pydantic-settings>=2.5",
    "starlette>=0.40",
    "uvicorn[standard]>=0.32",
    "httpx>=0.27",
]

[project.scripts]
astro-archives-mcp = "astro_archives_mcp.__main__:main"

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-recording>=0.13",
    "vcrpy>=6.0",
    "inline-snapshot>=0.13",
    "ruff>=0.7",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/astro_archives_mcp"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra --strict-markers"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "W"]
ignore = ["E501"]
```

- [ ] **Step 1.4: Create `.gitignore`**

Write `.gitignore`:
```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/

# uv
.venv/

# IDE
.vscode/
.idea/
*.swp

# Env
.env
.env.local

# Build
dist/
build/

# OS
.DS_Store
```

- [ ] **Step 1.5: Create `.dockerignore`**

Write `.dockerignore`:
```
.venv/
.git/
.github/
.pytest_cache/
.ruff_cache/
__pycache__/
*.pyc
.env
.env.local
docs/
tests/
README.md
deploy/
```

- [ ] **Step 1.6: Create package files**

Write `src/astro_archives_mcp/__init__.py`:
```python
__version__ = "0.1.0"
```

Write `tests/__init__.py`:
```python
```
(empty file — just marks the directory as a package)

- [ ] **Step 1.7: Replace README.md**

Write `README.md`:
```markdown
# astro-archives-mcp

MCP server exposing IVOA-compliant astronomical archives (NOIRLab Astro Data Lab, NRAO/ALMA, etc.) to LLM clients.

Design: `docs/superpowers/specs/2026-06-02-stable-mcp-design.md`
Slice A plan: `docs/superpowers/plans/2026-06-02-slice-a-server-skeleton.md`

## Quickstart (Slice A)

```bash
uv sync
uv run pytest
uv run python -m astro_archives_mcp
# server on http://localhost:8000, MCP endpoint at /mcp
```

Smoke test with MCP Inspector:
```bash
npx -y @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/list
```
```

- [ ] **Step 1.8: Install deps and confirm the scaffold imports**

Run: `uv sync`
Expected: lockfile generated, deps installed without conflict.

Run: `uv run python -c "import astro_archives_mcp; print(astro_archives_mcp.__version__)"`
Expected: `0.1.0`

- [ ] **Step 1.9: Confirm pytest discovers and the lint is clean**

Run: `uv run pytest`
Expected: `no tests ran` (exit 5 is fine — there are literally no tests yet)

Run: `uv run ruff check .`
Expected: `All checks passed!`

- [ ] **Step 1.10: Commit**

```bash
git add .python-version .gitignore .dockerignore pyproject.toml uv.lock README.md src/ tests/
git commit -m "chore: project scaffold (uv, pyproject, package skeleton)"
```

---

## Task 2: Config layer (Pydantic Settings)

Env-driven config so we never bake env-specific values into code or images.

**Files:**
- Create: `src/astro_archives_mcp/config.py`, `tests/unit/__init__.py`, `tests/unit/test_config.py`, `.env.example`

- [ ] **Step 2.1: Write the failing test**

Write `tests/unit/__init__.py`: empty.

Write `tests/unit/test_config.py`:
```python
import os
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
```

- [ ] **Step 2.2: Run the failing test**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: `ModuleNotFoundError: No module named 'astro_archives_mcp.config'`

- [ ] **Step 2.3: Write `config.py`**

Write `src/astro_archives_mcp/config.py`:
```python
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STABLE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    deployment: Literal["local", "adl", "tacc"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Slice-A: NoAuth only. BearerTokenProvider / OIDC arrive in later slices.
    auth_mode: Literal["none"] = "none"
```

- [ ] **Step 2.4: Run the test, confirm pass**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: both tests pass.

- [ ] **Step 2.5: Write `.env.example`**

Write `.env.example`:
```dotenv
# Slice A — all values are optional; defaults are fine for local dev.
# Prefix all env vars with STABLE_

STABLE_HOST=0.0.0.0
STABLE_PORT=8000
STABLE_DEPLOYMENT=local
STABLE_LOG_LEVEL=INFO
```

- [ ] **Step 2.6: Commit**

```bash
git add src/astro_archives_mcp/config.py tests/unit/ .env.example
git commit -m "feat(config): env-driven Pydantic settings"
```

---

## Task 3: `CallerContext` + `NoAuthProvider`

The auth abstraction the rest of the server reads from. Slice A only ships `NoAuth` — but the interface is the one all later providers conform to.

**Files:**
- Create: `src/astro_archives_mcp/auth/__init__.py`, `src/astro_archives_mcp/auth/base.py`, `src/astro_archives_mcp/auth/none.py`, `tests/unit/test_caller_context.py`

- [ ] **Step 3.1: Write the failing test**

Write `tests/unit/test_caller_context.py`:
```python
import pytest
from astro_archives_mcp.auth.base import CallerContext
from astro_archives_mcp.auth.none import NoAuthProvider


def test_caller_context_archive_creds_default_empty():
    ctx = CallerContext(caller_id="anonymous", auth_mode="none", request_id="r-1")
    assert ctx.archive_creds == {}
    assert ctx.scopes == set()


def test_caller_context_is_frozen():
    ctx = CallerContext(caller_id="anonymous", auth_mode="none", request_id="r-1")
    with pytest.raises(Exception):  # FrozenInstanceError or ValidationError
        ctx.caller_id = "someone-else"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_no_auth_provider_yields_anonymous_context():
    provider = NoAuthProvider()
    ctx = await provider.authenticate(headers={}, request_id="r-2")
    assert ctx.caller_id == "anonymous"
    assert ctx.auth_mode == "none"
    assert ctx.archive_creds == {}
    assert ctx.request_id == "r-2"
```

- [ ] **Step 3.2: Run the failing test**

Run: `uv run pytest tests/unit/test_caller_context.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3.3: Implement `auth/base.py`**

Write `src/astro_archives_mcp/auth/__init__.py`: empty.

Write `src/astro_archives_mcp/auth/base.py`:
```python
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
```

- [ ] **Step 3.4: Implement `auth/none.py`**

Write `src/astro_archives_mcp/auth/none.py`:
```python
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
```

- [ ] **Step 3.5: Fix the freeze-test if needed**

`dataclass(frozen=True)` raises `dataclasses.FrozenInstanceError` on attribute set. The test catches the broad `Exception`. If you'd rather assert specifically, change the test to `import dataclasses` and `pytest.raises(dataclasses.FrozenInstanceError)`.

- [ ] **Step 3.6: Run tests**

Run: `uv run pytest tests/unit/test_caller_context.py -v`
Expected: all three tests pass.

- [ ] **Step 3.7: Commit**

```bash
git add src/astro_archives_mcp/auth/ tests/unit/test_caller_context.py
git commit -m "feat(auth): CallerContext + NoAuthProvider"
```

---

## Task 4: Error taxonomy (4 classes)

The Tool Execution Error envelope every tool returns on failure.

**Files:**
- Create: `src/astro_archives_mcp/errors.py`, `tests/unit/test_errors.py`

- [ ] **Step 4.1: Write the failing test**

Write `tests/unit/test_errors.py`:
```python
import pytest
from astro_archives_mcp.errors import (
    ArchiveError,
    InternalError,
    TapQueryError,
    ToolExecutionError,
    ValidationError,
    error_to_payload,
)


def test_validation_error_payload_shape():
    err = ValidationError(
        message="Bad ADQL: column 'g_mag' not found",
        hint="Did you mean 'gmag'? See resource://catalogs/smash_dr2.object.notes",
        request_id="r-1",
    )
    payload = error_to_payload(err)
    assert payload["error_class"] == "validation_error"
    assert payload["retry_strategy"] == "fix_and_retry"
    assert payload["request_id"] == "r-1"
    assert payload["hint"].startswith("Did you mean")


def test_archive_error_carries_retry_after():
    err = ArchiveError(
        message="upstream 503",
        retry_after_seconds=30,
        request_id="r-2",
    )
    payload = error_to_payload(err)
    assert payload["retry_strategy"] == "wait_and_retry"
    assert payload["retry_after_seconds"] == 30


def test_tap_query_error_default_strategy():
    err = TapQueryError(message="syntax error", request_id="r-3")
    payload = error_to_payload(err)
    assert payload["error_class"] == "tap_query_error"
    assert payload["retry_strategy"] == "fix_and_retry"


def test_internal_error_does_not_leak_message():
    err = InternalError(message="raw traceback redacted", request_id="r-4")
    payload = error_to_payload(err)
    assert payload["error_class"] == "internal_error"
    assert payload["message"] == "Internal server error. Contact ops with request_id."
    assert payload["request_id"] == "r-4"


def test_hint_omitted_when_none():
    err = ValidationError(message="bad", request_id="r-5")
    payload = error_to_payload(err)
    assert "hint" not in payload


def test_unknown_error_is_internal():
    payload = error_to_payload(RuntimeError("oh no"), request_id="r-6")
    assert payload["error_class"] == "internal_error"
    assert payload["request_id"] == "r-6"
```

- [ ] **Step 4.2: Run the failing test**

Run: `uv run pytest tests/unit/test_errors.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 4.3: Implement `errors.py`**

Write `src/astro_archives_mcp/errors.py`:
```python
from dataclasses import dataclass
from typing import Literal, Optional

RetryStrategy = Literal["fix_and_retry", "wait_and_retry", "submit_async", "abandon"]


@dataclass
class ToolExecutionError(Exception):
    """Base class — every concrete subclass sets error_class + retry_strategy."""
    error_class: str = "internal_error"
    retry_strategy: RetryStrategy = "abandon"
    message: str = ""
    hint: Optional[str] = None
    retry_after_seconds: Optional[int] = None
    request_id: Optional[str] = None

    def __post_init__(self) -> None:
        super().__init__(self.message)


@dataclass
class ValidationError(ToolExecutionError):
    error_class: str = "validation_error"
    retry_strategy: RetryStrategy = "fix_and_retry"


@dataclass
class ArchiveError(ToolExecutionError):
    error_class: str = "archive_error"
    retry_strategy: RetryStrategy = "wait_and_retry"


@dataclass
class TapQueryError(ToolExecutionError):
    error_class: str = "tap_query_error"
    retry_strategy: RetryStrategy = "fix_and_retry"


@dataclass
class InternalError(ToolExecutionError):
    error_class: str = "internal_error"
    retry_strategy: RetryStrategy = "abandon"


_INTERNAL_GENERIC_MESSAGE = "Internal server error. Contact ops with request_id."


def error_to_payload(
    err: Exception, *, request_id: Optional[str] = None
) -> dict:
    """Convert any error into the LLM-facing payload shape.

    Unknown exceptions become InternalError; their raw message is redacted to
    avoid leaking tracebacks or creds.
    """
    if not isinstance(err, ToolExecutionError):
        err = InternalError(message="", request_id=request_id)

    payload: dict = {
        "error_class": err.error_class,
        "message": (
            _INTERNAL_GENERIC_MESSAGE if err.error_class == "internal_error" else err.message
        ),
        "retry_strategy": err.retry_strategy,
        "request_id": err.request_id or request_id,
    }
    if err.hint:
        payload["hint"] = err.hint
    if err.retry_after_seconds is not None:
        payload["retry_after_seconds"] = err.retry_after_seconds
    return payload
```

- [ ] **Step 4.4: Run tests**

Run: `uv run pytest tests/unit/test_errors.py -v`
Expected: all 6 tests pass.

- [ ] **Step 4.5: Commit**

```bash
git add src/astro_archives_mcp/errors.py tests/unit/test_errors.py
git commit -m "feat(errors): Tool Execution Error taxonomy (4 classes)"
```

---

## Task 5: Result shaper (inline tier only)

Normalizes archive responses into the response envelope from spec §6.3. Slice A only implements the inline tier — Resource and MyDB tiers come later.

**Files:**
- Create: `src/astro_archives_mcp/shaper.py`, `tests/unit/test_shaper.py`

- [ ] **Step 5.1: Write the failing test**

Write `tests/unit/test_shaper.py`:
```python
import math
import numpy as np
from astropy.table import Table
from astro_archives_mcp.shaper import shape_inline_table


def _astropy_table_basic() -> Table:
    t = Table()
    t["ra"] = [185.43, 186.0]
    t["ra"].unit = "deg"
    t["ra"].description = "Right ascension"
    t["dec"] = [-31.99, -31.5]
    t["dec"].unit = "deg"
    t["gmag"] = [18.4, 19.1]
    return t


def test_inline_envelope_basic_shape():
    table = _astropy_table_basic()
    out = shape_inline_table(table, archive="datalab", maxrec=10)
    assert out["row_count"] == 2
    assert out["truncated"] is False
    assert out["truncation_reason"] is None
    assert out["resource_uri"] is None
    assert out["mydb_table"] is None
    assert out["archive"] == "datalab"
    assert len(out["rows"]) == 2
    assert out["preview"] is None
    assert out["next_steps"] is None
    assert out["hints"] == []

    cols_by_name = {c["name"]: c for c in out["columns"]}
    assert cols_by_name["ra"]["unit"] == "deg"
    assert cols_by_name["ra"]["description"] == "Right ascension"


def test_truncation_marked_when_rows_exceed_maxrec():
    table = _astropy_table_basic()
    out = shape_inline_table(table, archive="datalab", maxrec=1)
    assert out["row_count"] == 1
    assert out["truncated"] is True
    assert out["truncation_reason"] == "maxrec_exceeded"
    assert len(out["rows"]) == 1


def test_masked_values_become_json_null():
    t = Table()
    t["x"] = np.ma.MaskedArray([1.0, 2.0], mask=[False, True])
    out = shape_inline_table(t, archive="datalab", maxrec=10)
    assert out["rows"][0][0] == 1.0
    assert out["rows"][1][0] is None


def test_nan_becomes_json_null():
    t = Table()
    t["x"] = [1.0, math.nan]
    out = shape_inline_table(t, archive="datalab", maxrec=10)
    assert out["rows"][1][0] is None
```

- [ ] **Step 5.2: Run the failing test**

Run: `uv run pytest tests/unit/test_shaper.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 5.3: Implement `shaper.py`**

Write `src/astro_archives_mcp/shaper.py`:
```python
import math
from typing import Any
import numpy as np
from astropy.table import Table


def shape_inline_table(
    table: Table,
    *,
    archive: str,
    maxrec: int,
) -> dict[str, Any]:
    """Convert an astropy.Table into the inline-tier response envelope.

    Inline tier only. Resource / MyDB tiers handled by other functions
    once result sizes warrant them.
    """
    n_in = len(table)
    truncated = n_in > maxrec
    if truncated:
        table = table[:maxrec]

    columns: list[dict[str, Any]] = []
    for name in table.colnames:
        col = table[name]
        columns.append({
            "name": name,
            "type": str(col.dtype),
            "unit": str(col.unit) if col.unit else None,
            "ucd": getattr(col, "meta", {}).get("ucd"),
            "description": col.description or None,
        })

    rows: list[list[Any]] = []
    for row in table:
        rows.append([_normalize(row[name]) for name in table.colnames])

    return {
        "row_count": len(rows),
        "columns": columns,
        "rows": rows,
        "preview": None,
        "resource_uri": None,
        "mydb_table": None,
        "truncated": truncated,
        "truncation_reason": "maxrec_exceeded" if truncated else None,
        "archive": archive,
        "next_steps": None,
        "hints": [],
    }


def _normalize(value: Any) -> Any:
    """Convert astropy / numpy scalars into JSON-friendly values; NaN/masked -> None."""
    if value is np.ma.masked:
        return None
    if hasattr(value, "mask") and bool(getattr(value, "mask", False)):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
```

- [ ] **Step 5.4: Run the tests**

Run: `uv run pytest tests/unit/test_shaper.py -v`
Expected: all 4 tests pass.

- [ ] **Step 5.5: Commit**

```bash
git add src/astro_archives_mcp/shaper.py tests/unit/test_shaper.py
git commit -m "feat(shaper): inline-tier response envelope"
```

---

## Task 6: `TapClient` (sync, pyvo-backed)

The single typed wrapper around pyvo's TAP service. Tools never touch raw pyvo objects.

**Files:**
- Create: `src/astro_archives_mcp/backends/__init__.py`, `src/astro_archives_mcp/backends/tap.py`, `tests/backends/__init__.py`, `tests/backends/test_tap_client.py`

Uses `pytest-recording` (vcrpy) to capture real TAP traffic once and replay forever. Cassettes are committed to the repo. If the upstream service breaks compatibly, deleting the cassette and re-running with `--record-mode=once` refreshes the fixture.

- [ ] **Step 6.1: Pick a known-stable public TAP endpoint + ADQL for fixture**

Use NOIRLab Astro Data Lab TAP (`https://datalab.noirlab.edu/tap`) with a tiny deterministic query:
```
SELECT TOP 3 ra, dec FROM smash_dr2.object WHERE ra BETWEEN 185 AND 185.01 ORDER BY ra
```

This returns ≤3 rows quickly and the underlying catalog table is stable. (If `smash_dr2.object` is unavailable when the cassette is first recorded, fall back to NSC, e.g. `nsc_dr2.object` — the choice doesn't matter for the test, only that the cassette captures a deterministic shape.)

- [ ] **Step 6.2: Write the failing tests**

Write `tests/backends/__init__.py`: empty.

Write `tests/backends/test_tap_client.py`:
```python
import pytest
from astro_archives_mcp.backends.tap import TapClient
from astro_archives_mcp.errors import TapQueryError


SMASH_TAP = "https://datalab.noirlab.edu/tap"
SAFE_ADQL = (
    "SELECT TOP 3 ra, dec FROM smash_dr2.object "
    "WHERE ra BETWEEN 185 AND 185.01 ORDER BY ra"
)


@pytest.mark.vcr
def test_tap_client_returns_astropy_table():
    client = TapClient()
    table = client.query(endpoint=SMASH_TAP, adql=SAFE_ADQL, maxrec=10)
    assert "ra" in table.colnames
    assert "dec" in table.colnames
    assert len(table) <= 3


@pytest.mark.vcr
def test_tap_client_bad_adql_raises_tap_query_error():
    client = TapClient()
    with pytest.raises(TapQueryError) as exc:
        client.query(
            endpoint=SMASH_TAP,
            adql="SELECT garbage FROM nowhere",
            maxrec=10,
        )
    assert "tap_query_error" in str(exc.value.error_class)
```

- [ ] **Step 6.3: Run failing tests**

Run: `uv run pytest tests/backends/test_tap_client.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 6.4: Implement `TapClient`**

Write `src/astro_archives_mcp/backends/__init__.py`: empty.

Write `src/astro_archives_mcp/backends/tap.py`:
```python
import logging
from astropy.table import Table
import pyvo
from pyvo.dal.exceptions import DALQueryError, DALServiceError

from astro_archives_mcp.errors import ArchiveError, TapQueryError

log = logging.getLogger(__name__)


class TapClient:
    """Sync TAP wrapper. Async / auto-promote arrives in a later slice."""

    def query(
        self,
        *,
        endpoint: str,
        adql: str,
        maxrec: int = 10_000,
    ) -> Table:
        try:
            service = pyvo.dal.TAPService(endpoint)
            result = service.search(adql, maxrec=maxrec)
        except DALQueryError as e:
            raise TapQueryError(message=str(e)) from e
        except DALServiceError as e:
            raise ArchiveError(message=str(e)) from e
        return result.to_table()
```

- [ ] **Step 6.5: Record the cassette (one-time)**

This requires network access. Run with explicit recording mode:

Run:
```
uv run pytest tests/backends/test_tap_client.py -v \
  --record-mode=once
```
Expected: tests pass AND new files appear at `tests/backends/cassettes/test_tap_client/`.

- [ ] **Step 6.6: Confirm cassettes replay offline**

Disconnect from the network (or set the relevant env var to block egress in your shell).

Run: `uv run pytest tests/backends/test_tap_client.py -v --record-mode=none`
Expected: tests pass without network access.

Reconnect to the network when done.

- [ ] **Step 6.7: Commit (cassettes included)**

```bash
git add src/astro_archives_mcp/backends/ tests/backends/
git commit -m "feat(backends): sync TapClient + recorded cassettes"
```

---

## Task 7: `vo_tap_query` tool

Wires backend + shaper + error mapper into a single MCP tool. Slice A scope only — no async, no auto-promote, no Resource tier, no hints.

**Files:**
- Create: `src/astro_archives_mcp/tools/__init__.py`, `src/astro_archives_mcp/tools/ivoa.py`

- [ ] **Step 7.1: Implement `tools/ivoa.py`**

Write `src/astro_archives_mcp/tools/__init__.py`: empty.

Write `src/astro_archives_mcp/tools/ivoa.py`:
```python
"""IVOA generic tools. Slice A ships only vo_tap_query (sync, inline tier)."""
from typing import Annotated
from pydantic import Field

from astro_archives_mcp.backends.tap import TapClient
from astro_archives_mcp.errors import ToolExecutionError, error_to_payload
from astro_archives_mcp.shaper import shape_inline_table


_tap = TapClient()


def vo_tap_query(
    endpoint: Annotated[
        str,
        Field(
            description=(
                "Full TAP service URL. Example: "
                "'https://datalab.noirlab.edu/tap' (NOIRLab Astro Data Lab) "
                "or 'https://almascience.nrao.edu/tap' (ALMA Science Archive). "
                "Discover services via vo_registry_search (later slice)."
            ),
            examples=[
                "https://datalab.noirlab.edu/tap",
                "https://almascience.nrao.edu/tap",
            ],
        ),
    ],
    adql: Annotated[
        str,
        Field(
            description=(
                "ADQL query. Use CIRCLE/POINT/CONTAINS for sky-region "
                "cuts. Use SELECT TOP N to cap row counts. Use ORDER BY for "
                "deterministic results."
            ),
            examples=[
                "SELECT TOP 100 ra, dec, gmag FROM smash_dr2.object "
                "WHERE 1=CONTAINS(POINT('ICRS', ra, dec), "
                "CIRCLE('ICRS', 185.43, -31.99, 0.2))",
            ],
        ),
    ],
    maxrec: Annotated[
        int,
        Field(
            ge=1, le=100_000,
            description="Hard cap on rows returned. Default 10_000.",
        ),
    ] = 10_000,
) -> dict:
    """Run a synchronous ADQL query against any IVOA-compliant TAP service.

    Returns the inline result envelope: {row_count, columns, rows, archive,
    truncated, ...}. Slice A only supports the inline tier (≤ 1000 rows or
    ~512 KB); larger results will be truncated with `truncated: true` and
    `truncation_reason: "maxrec_exceeded"`. Async, auto-promote, and Resource-
    tier responses ship in later slices.

    On error, returns a Tool Execution Error payload with `error_class`,
    `message`, `retry_strategy`, and (when available) `hint`.
    """
    try:
        table = _tap.query(endpoint=endpoint, adql=adql, maxrec=maxrec)
    except ToolExecutionError as e:
        return {"isError": True, **error_to_payload(e)}
    except Exception as e:  # noqa: BLE001
        return {"isError": True, **error_to_payload(e)}
    return shape_inline_table(table, archive=_archive_label(endpoint), maxrec=maxrec)


def _archive_label(endpoint: str) -> str:
    """Coarse label for the `archive` field. Static map for Slice A; later
    slices replace with a registry-aware lookup."""
    e = endpoint.lower()
    if "datalab.noirlab" in e:
        return "datalab"
    if "almascience" in e:
        return "alma"
    if "data-query.nrao" in e:
        return "nrao_vla"
    return "other"
```

- [ ] **Step 7.2: Commit (tool tests come with the MCP integration in Task 8)**

```bash
git add src/astro_archives_mcp/tools/
git commit -m "feat(tools): vo_tap_query (sync, inline tier)"
```

---

## Task 8: FastMCP server + Starlette mount + in-memory client test

Wire FastMCP, mount under Starlette with `/health` and `/ready`, register `vo_tap_query`, and integration-test it via an in-memory MCP client.

**Files:**
- Create: `src/astro_archives_mcp/app.py`, `src/astro_archives_mcp/observability.py`, `tests/conftest.py`, `tests/tools/__init__.py`, `tests/tools/test_vo_tap_query.py`

- [ ] **Step 8.1: Implement observability (structured stdlib logging)**

Write `src/astro_archives_mcp/observability.py`:
```python
import json
import logging
import sys


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers[:] = [handler]
```

- [ ] **Step 8.2: Implement `app.py`**

> **NOTE — verify against FastMCP 3.x docs before pasting verbatim.** The mount pattern is `Mount("/mcp", app=mcp.http_app())` per FastMCP ASGI integration docs. If the current FastMCP version has shifted (e.g. method renamed to `mcp.asgi_app()`), use the documented form.

Write `src/astro_archives_mcp/app.py`:
```python
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from astro_archives_mcp import __version__
from astro_archives_mcp.observability import configure_logging
from astro_archives_mcp.tools.ivoa import vo_tap_query


def build_mcp() -> FastMCP:
    """Construct the FastMCP server with all Slice-A tools registered."""
    mcp = FastMCP(name="astro-archives-mcp")
    mcp.tool(vo_tap_query)
    return mcp


def build_app() -> Starlette:
    configure_logging()
    mcp = build_mcp()

    async def health(_request):
        return JSONResponse({"status": "ok", "version": __version__})

    async def ready(_request):
        # Slice A: no backend pre-warm. Later slices ping a known TAP endpoint.
        return JSONResponse({"status": "ok"})

    return Starlette(routes=[
        Route("/health", health),
        Route("/ready", ready),
        Mount("/mcp", app=mcp.http_app()),
    ])
```

- [ ] **Step 8.3: Write the in-memory client test**

Write `tests/tools/__init__.py`: empty.

Write `tests/conftest.py`:
```python
import pytest
from astro_archives_mcp.app import build_mcp


@pytest.fixture
def mcp_server():
    return build_mcp()
```

Write `tests/tools/test_vo_tap_query.py`:
```python
import pytest
from fastmcp import Client


@pytest.mark.vcr
async def test_vo_tap_query_via_in_memory_client(mcp_server):
    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "vo_tap_query",
            {
                "endpoint": "https://datalab.noirlab.edu/tap",
                "adql": (
                    "SELECT TOP 3 ra, dec FROM smash_dr2.object "
                    "WHERE ra BETWEEN 185 AND 185.01 ORDER BY ra"
                ),
                "maxrec": 10,
            },
        )
        payload = result.structured_content
        assert payload["row_count"] <= 3
        assert payload["truncated"] is False
        assert payload["archive"] == "datalab"
        names = {c["name"] for c in payload["columns"]}
        assert {"ra", "dec"}.issubset(names)


async def test_vo_tap_query_validation_error_surface(mcp_server):
    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "vo_tap_query",
            {
                "endpoint": "https://datalab.noirlab.edu/tap",
                "adql": "SELECT TOP 3 ra FROM x",
                "maxrec": -1,  # violates Field(ge=1)
            },
        )
        # FastMCP surfaces Pydantic validation as a tool error; behaviour depends
        # on framework version. Assert one of the two acceptable shapes:
        if result.is_error:
            assert "maxrec" in result.error_message or "maxrec" in str(result.content)
        else:
            payload = result.structured_content
            assert payload.get("isError") is True
```

- [ ] **Step 8.4: Run the in-memory test under `--record-mode=once` to record the cassette**

Run:
```
uv run pytest tests/tools/test_vo_tap_query.py -v --record-mode=once
```
Expected: tests pass and cassette appears at `tests/tools/cassettes/`.

- [ ] **Step 8.5: Confirm replay-only run passes**

Run: `uv run pytest tests/tools/test_vo_tap_query.py -v --record-mode=none`
Expected: passes offline.

- [ ] **Step 8.6: Commit**

```bash
git add src/astro_archives_mcp/app.py src/astro_archives_mcp/observability.py tests/conftest.py tests/tools/
git commit -m "feat(app): FastMCP + Starlette mount with /health and /ready"
```

---

## Task 9: Entry point + local server smoke

Make `python -m astro_archives_mcp` start a server. Verify the server actually serves over HTTP.

**Files:**
- Create: `src/astro_archives_mcp/__main__.py`

- [ ] **Step 9.1: Implement entry point**

Write `src/astro_archives_mcp/__main__.py`:
```python
import uvicorn
from astro_archives_mcp.app import build_app
from astro_archives_mcp.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        build_app(),
        host=settings.host,
        port=settings.port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 9.2: Start the server, verify health**

Run in one terminal: `uv run python -m astro_archives_mcp`
Expected: uvicorn boots, logs `INFO Uvicorn running on http://0.0.0.0:8000`.

Run in another terminal: `curl -fsS http://localhost:8000/health`
Expected: `{"status":"ok","version":"0.1.0"}`

Run: `curl -fsS http://localhost:8000/ready`
Expected: `{"status":"ok"}`

Stop the server (Ctrl-C).

- [ ] **Step 9.3: Smoke test with MCP Inspector CLI**

Restart the server: `uv run python -m astro_archives_mcp`

In another terminal:
```
npx -y @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/list
```
Expected: JSON output listing one tool, `vo_tap_query`, with its description and JSON schema.

Stop the server.

- [ ] **Step 9.4: Commit**

```bash
git add src/astro_archives_mcp/__main__.py
git commit -m "feat(app): uvicorn entry point and verified local smoke"
```

---

## Task 10: Containerize

Multi-stage slim image, non-root user, `EXPOSE 8000`, health check.

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`

- [ ] **Step 10.1: Write `Dockerfile`**

Write `Dockerfile`:
```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /build

# Install uv (frozen version pinned for reproducibility — bump deliberately)
RUN pip install --no-cache-dir "uv==0.4.30"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
COPY README.md ./
RUN uv sync --frozen --no-dev


FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 mcp
WORKDIR /app
COPY --from=builder /build/.venv ./.venv
COPY --from=builder /build/src ./src

USER mcp
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health',timeout=3).status==200 else 1)"

CMD ["python", "-m", "astro_archives_mcp"]
```

- [ ] **Step 10.2: Write `docker-compose.yml`**

Write `docker-compose.yml`:
```yaml
services:
  mcp:
    build: .
    ports:
      - "8000:8000"
    environment:
      STABLE_LOG_LEVEL: INFO
```

- [ ] **Step 10.3: Build the image**

Run: `docker build -t astro-archives-mcp:slice-a .`
Expected: build succeeds. Final image size should be reasonable (~150–250 MB).

- [ ] **Step 10.4: Start the container, verify health**

Run: `docker run -d --rm -p 8000:8000 --name aamcp astro-archives-mcp:slice-a`

Wait ~3 seconds, then:
```
curl -fsS http://localhost:8000/health
```
Expected: `{"status":"ok","version":"0.1.0"}`

Run: `docker inspect --format='{{.State.Health.Status}}' aamcp`
Expected: `healthy` (may take up to 30s for the first probe).

- [ ] **Step 10.5: Smoke-test the containerized server with Inspector**

Run:
```
npx -y @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/list
```
Expected: same output as Step 9.3.

Run: `docker stop aamcp`

- [ ] **Step 10.6: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat(deploy): multi-stage Dockerfile + docker-compose"
```

---

## Task 11: CI pipeline (lint + tests + container + Inspector smoke)

GitHub Actions runs on every push and PR: ruff, pytest (replay-only), `docker build`, run container, Inspector smoke.

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 11.1: Write the workflow**

Write `.github/workflows/ci.yml`:
```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          version: "0.4.30"
          enable-cache: true
      - name: Install Python 3.12
        run: uv python install 3.12
      - name: Sync deps
        run: uv sync
      - name: Lint
        run: uv run ruff check .
      - name: Tests (replay-only)
        run: uv run pytest --record-mode=none

  container:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - name: Build image
        run: docker build -t astro-archives-mcp:ci .
      - name: Run container
        run: |
          docker run -d --rm -p 8000:8000 --name aamcp astro-archives-mcp:ci
          for i in $(seq 1 30); do
            if curl -fsS http://localhost:8000/health > /dev/null; then break; fi
            sleep 1
          done
          curl -fsS http://localhost:8000/health
      - name: Inspector smoke
        run: |
          npx -y @modelcontextprotocol/inspector \
            --cli http://localhost:8000/mcp --method tools/list \
            | tee inspector.json
          grep -q '"name": "vo_tap_query"' inspector.json
      - name: Stop container
        if: always()
        run: docker stop aamcp || true
```

- [ ] **Step 11.2: Push and confirm CI passes**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: lint, tests, container build, Inspector smoke"
git push origin main   # or open a PR if you prefer; ask before pushing
```

> **Confirm with the user before pushing to a remote.** This is the first push to `main` from this branch.

Verify the GitHub Actions run on the repo's Actions tab. Expected: both `test` and `container` jobs green.

If the run fails: do not @superpowers:systematic-debugging — read the failed log first; the most common cause will be a missing dependency or a path mismatch. Fix forward; commit; re-push.

---

## Task 12: Staging deployment runbook

Manual deploy instructions for the first hosted Slice-A staging environment. Automation comes when ADL/TACC ops conversations have happened.

**Files:**
- Create: `deploy/staging-runbook.md`

- [ ] **Step 12.1: Write the runbook**

Write `deploy/staging-runbook.md`:
```markdown
# Slice A — Staging Deployment Runbook

This is a manual deploy procedure for the first hosted Slice-A server.
Automation (k8s manifests, OIDC, OTel exporters) lands in later slices once
ADL/TACC ops have weighed in.

## Prereqs

- Access to whichever container host we land on for early staging
  (a small VM or a container PaaS will do for Slice A)
- Container registry credentials
- A public hostname terminating TLS in front of the container

## Build & push

```bash
docker build -t <registry>/astro-archives-mcp:0.1.0 .
docker push <registry>/astro-archives-mcp:0.1.0
```

## Run

```bash
docker run -d --restart=unless-stopped \
  -p 8000:8000 \
  -e STABLE_DEPLOYMENT=local \
  -e STABLE_LOG_LEVEL=INFO \
  --name astro-archives-mcp \
  <registry>/astro-archives-mcp:0.1.0
```

## Reverse-proxy notes (nginx example)

The MCP Streamable HTTP transport keeps a long-lived GET stream open. The
default 60–75s idle timeouts of nginx/ALB/CDN will silently kill the stream.

```nginx
location /mcp {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header MCP-Protocol-Version $http_mcp_protocol_version;
    proxy_read_timeout 3600s;
    proxy_buffering off;
    chunked_transfer_encoding on;
}
```

Per MCP spec 2025-11-25, return HTTP 403 on invalid `Origin`. Most reverse
proxies pass `Origin` through; do not strip it. Do not gzip the MCP stream.

## Verify

From a machine that can reach the public hostname:

```bash
curl -fsS https://<host>/health
curl -fsS https://<host>/ready
npx -y @modelcontextprotocol/inspector --cli https://<host>/mcp --method tools/list
```

Expected: `vo_tap_query` listed.

## Rollback

`docker stop astro-archives-mcp && docker run … <registry>/astro-archives-mcp:<previous-tag>`
```

- [ ] **Step 12.2: Commit**

```bash
git add deploy/staging-runbook.md
git commit -m "docs(deploy): Slice A staging runbook"
```

---

## Done criteria for Slice A

All of these are independently verifiable:

- `uv run pytest --record-mode=none` is green and includes ≥1 unit test per source file plus integration tests for `vo_tap_query`.
- `uv run ruff check .` is clean.
- `uv run python -m astro_archives_mcp` boots; `/health` and `/ready` return 200; Inspector lists `vo_tap_query`.
- `docker build` succeeds; the container is healthy; Inspector against the containerized server lists `vo_tap_query`.
- CI is green on a fresh `git push`.
- Spec architectural boundaries hold: tools never touch raw pyvo objects, `vo_tap_query` never logs or returns raw tracebacks, errors carry `error_class` + `retry_strategy` from the taxonomy.

When all checks above pass, Slice A is complete. The next plan (Slice C — Data Lab MyDB + Knowledge layer) gets written separately.

---

## Notes on what *not* to do during Slice A

These show up as tempting expansions; reject them and write a follow-on plan instead.

- Adding any other IVOA tool (`vo_sia_search`, `vo_registry_search`, etc.) — wait for Slice 3-5.
- Adding async TAP / auto-promote — Slice C.
- Wiring full OTel — needs deployment-side clarity from ops; basic structured logs are enough for Slice A.
- Adding a Resource tier — needs result-store eviction logic; postpone.
- Adding `BearerTokenProvider` or OIDC — auth model still pending ADL clarification.
- Building the knowledge corpus — its own substantial plan; do not start it inside Slice A.
- Pre-warming archive connections in `/ready` — fragile, ties Slice A to a specific upstream; revisit in Slice C.
