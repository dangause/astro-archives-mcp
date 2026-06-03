# astro-archives-mcp — Claude Code context

MCP server exposing IVOA-compliant astronomical archives (NOIRLab Astro Data Lab, NRAO/ALMA, …) to LLM clients. STABLE summer project (CosmicAI), Slice A shipped.

Design: `docs/superpowers/specs/2026-06-02-stable-mcp-design.md`. Read this for any non-trivial change — it explains why the layers are shaped the way they are.

## Commands

```bash
uv sync                                  # install deps + dev deps
uv run pytest --record-mode=none         # 36 tests, offline replay
uv run pytest --record-mode=once -k <t>  # re-record one cassette (needs net)
uv run ruff check .                      # lint
uv run python -m astro_archives_mcp      # boot server on :8000 (STABLE_PORT to override)
docker build -t astro-archives-mcp:dev . # ~325 MB image
npx -y @modelcontextprotocol/inspector --cli http://localhost:8000/mcp --method tools/list
```

Settings env vars are `STABLE_*` (Pydantic Settings, `extra="ignore"`). See `.env.example`.

## Architecture (Slice A)

```
src/astro_archives_mcp/
├── auth/         # CallerContext, AuthProvider Protocol (runtime_checkable), NoAuthProvider
├── backends/     # TapClient (typed pyvo wrapper). Tools never import pyvo directly.
├── tools/        # vo_tap_query — thin: backend → shaper → response
├── shaper.py     # astropy.Table → inline response envelope (spec §6)
├── errors.py     # ToolExecutionError taxonomy + error_to_payload (spec §7)
├── observability.py  # JSON logging + current_request_id ContextVar
├── app.py        # build_mcp() + build_app() factories; RequestIdMiddleware (pure ASGI)
└── __main__.py   # uvicorn entry; called by `python -m astro_archives_mcp`
```

Tests mirror this: `tests/unit/` (pure), `tests/backends/` (vcrpy cassettes), `tests/tools/` (in-memory MCP Client), `tests/app/` (Starlette via httpx ASGITransport with manually-driven lifespan).

## Gotchas (real things that bit Slice A — don't repeat)

- **vcrpy `decode_content` shim lives at `tests/conftest.py`.** Do NOT move it to a subdirectory — pytest doesn't propagate conftests across siblings, and `tests/tools/` + `tests/backends/` both need it (astropy's votable parser passes `decode_content=True` which vcrpy's stub forwards to BytesIO, which rejects it).
- **FastMCP lifespan MUST be propagated to Starlette.** `Starlette(..., lifespan=mcp_app.lifespan)`. Without it, every `POST /mcp` raises `RuntimeError(StreamableHTTPSessionManager task group was not initialized)`. The in-memory `Client(mcp_server)` bypasses Starlette, so this only shows up over HTTP. Regression guarded by `tests/app/test_build_app.py`.
- **Dockerfile uses `uv sync --frozen --no-dev --no-editable`.** The `--no-editable` is load-bearing — the default editable install bakes `/build/src` paths into the venv, which break in the `/app/` runtime stage.
- **`README.md` is NOT in `.dockerignore`.** uv reads `pyproject.toml`'s `readme=` during install. Resist the shrink-the-build-context instinct.
- **`POST /mcp` 307-redirects to `/mcp/`** because of Starlette `Mount`. Inspector follows redirects; bare `curl /mcp` does not. Use `curl -L` or `/mcp/`.
- **Default for replay is `--record-mode=none`.** New cassettes need explicit `--record-mode=once -k <test>` + network access.

## Reliability contracts (spec invariants — don't break)

- **Tools never touch raw pyvo.** Only `backends/` imports pyvo. Spec §2.3 layering. Verifiable with `grep -r pyvo src/astro_archives_mcp/tools/`.
- **`truncated` is always a top-level boolean.** Never silently true. The ALMA_MCP prototype's `df.head(20)` is the explicit anti-pattern. Enforced in `shape_inline_table`.
- **Error payloads carry `error_class` + `retry_strategy`.** `error_class` is the discriminator the LLM branches on. No `isError` key (intentional — see `tools/ivoa.py` docstring).
- **Tokens / raw tracebacks never reach the LLM.** `InternalError.redact_message = True` (ClassVar) drives `error_to_payload` to swap in `_INTERNAL_GENERIC_MESSAGE`. Server logs retain the cause via `__cause__`.

## Workflow

1. Branch from `main`, e.g. `slice-2-implementation`.
2. Design changes go through the superpowers skills: brainstorming → writing-plans → executing.
3. Open a PR. CI (`.github/workflows/ci.yml`) runs ruff + pytest + container build + Inspector smoke.
4. Merge when green.

Slice-C carryover items (deferred from Slice A's whole-branch review) are tracked in `docs/superpowers/notes/2026-06-03-slice-a-final-review.md`.
