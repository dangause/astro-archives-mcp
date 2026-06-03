# Slice A — Whole-Branch Final Review Notes

**Date:** 2026-06-03
**Branch reviewed:** `slice-a-implementation` (19 commits from `2d3b473` → `80eba81`)
**Verdict:** SHIP

This note captures the whole-branch review findings that were not addressed in
the branch itself, organized by what to track in the Slice C plan vs. what was
intentionally deferred by design.

---

## Addressed before merge

- **`isError` vs protocol-level `is_error` ambiguity** — Resolved by dropping
  the `"isError": True` key from the dict returned by tool error paths in
  `tools/ivoa.py`. The discriminator the LLM should branch on is `error_class`.
  Tool docstring updated to make this contract explicit. A new parameterized
  unit test (`test_vo_tap_query_error_path_returns_structured_payload`) verifies
  the error path actually surfaces `error_class` for `TapQueryError`,
  `ValidationError`, and arbitrary `Exception` (coerced to `internal_error`).

---

## Slice C carryover (track in next plan, do not block this PR)

| ID | Item |
|---|---|
| C-1 | Replace static `_archive_label` map in `tools/ivoa.py` with a registry-aware lookup once `vo_registry_search` exists |
| C-2 | Resource tier + 30-min result-store eviction; tighten shaper with 512 KB byte budget at that time |
| C-3 | Async TAP auto-promote (`vo_tap_status`, `vo_tap_results`, `vo_tap_abort`) |
| C-4 | `BearerTokenProvider` concrete; widen `Settings.auth_mode` Literal to accept `"bearer"`. `CallerContext` and `AuthProvider` Protocol are ready — no refactor expected |
| C-5 | Real `/ready` probe — at minimum verify the tool registry is non-empty (currently returns `ok` unconditionally) |
| C-6 | Tool error-catching decorator/helper applied uniformly across all 8 IVOA tools as they land |
| C-7 | Decide whether tool errors should also surface at the MCP protocol level (`raise`) in addition to the structured payload, then codify the pattern |
| C-8 | Hint engine (Pattern C in the spec) — rule-driven, replaces the `hints: []` placeholder |
| C-9 | OTel spans per tool call (deferred by design in Slice A) |
| C-10 | Document the Origin allowlist explicitly in the staging runbook and/or implement an Origin-validation middleware |
| C-11 | Cassette refresh procedure documented in the README (`pytest --record-mode=once -k <test>`) |
| C-12 | Either start using `inline-snapshot` (perfect candidate: the shaper envelope test) or drop it from dev deps |

---

## Items the reviewer flagged as Minor that were intentionally left in place

- `vo_tap_query` two-arm try/except with `log.warning` vs `log.exception` —
  works for one tool; extract to a decorator in Slice C when 7 more tools
  arrive (folded into C-6).
- `_get_tap()` module-level singleton with a global — the DI seam is small
  but adequate for one tool. Revisit when a tool needs a differently-configured
  client.
- `RequestIdMiddleware.__init__` is missing type hints — one-line cleanup,
  not load-bearing.
- `errors.py` recipe documentation — fold a brief subclassing recipe into the
  module docstring when C-6 or C-7 reopens the file.
- `error_to_payload(err, *, request_id=...)` precedence convention
  (`err.request_id or request_id`) reverses the usual "argument overrides
  default" — works as tested; document precedence in Slice C if a real
  conflict case appears.
- Inline-tier byte budget (~512 KB from spec §6.1) is not enforced — only the
  row-count cap. Folded into C-2.

---

## Why these items were not addressed in Slice A

1. **They are bounded by their own task scope.** Real `/ready` probing,
   `Origin` validation, OTel, and the result-tier byte budget each require
   their own design decisions that the spec already defers.
2. **They become work multipliers in Slice C.** Items like the error-catching
   decorator make sense to extract only after the second or third tool exists.
   Premature abstraction now costs us more than copying the pattern when 7
   more tools land.
3. **They depend on input still pending.** `BearerTokenProvider` needs the
   ADL/TACC auth conversation referenced in Spec §8.3.

---

## Done criteria verification (from plan §"Done criteria for Slice A")

- ✅ `uv run pytest --record-mode=none` green; ≥1 unit test per source file plus integration tests for `vo_tap_query` (36 tests passing)
- ✅ `uv run ruff check .` clean
- ✅ `uv run python -m astro_archives_mcp` boots; `/health`, `/ready` return 200; Inspector lists `vo_tap_query`
- ✅ `docker build` succeeds; container reports healthy via `docker inspect`; Inspector against containerized server lists `vo_tap_query`
- ⏳ CI green on a fresh `git push` — verified after pushing this branch
- ✅ Spec architectural boundaries hold: tools never touch raw pyvo (verified by grep), `vo_tap_query` never logs/returns raw tracebacks, errors carry `error_class` + `retry_strategy` from the taxonomy
