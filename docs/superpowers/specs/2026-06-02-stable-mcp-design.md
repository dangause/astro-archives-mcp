# STABLE: An MCP Server for Astronomical Archives — Design Spec

**Date:** 2026-06-02
**Project:** astro-archives-mcp (STABLE — Summer Team for Astronomical Benchmarking & LLM Engineering)
**Status:** Approved design; implementation plan to follow
**Primary stakeholders:** Adele Plunkett, Brian Mason (NRAO); Robert Nikutta, Stephanie Juneau (NOIRLab); Dan Gause (intern lead, MCP)
**Funding context:** CosmicAI initiative (NSF + Simons Foundation)

---

## 1. Project overview

A Python MCP (Model Context Protocol) server that exposes astronomical archives to LLM clients (Claude, Jupyter-AI, ADL-integrated chat). The server is built on IVOA standard protocols (TAP, SIA, ConeSearch, VORegistry) with thin extensions for archive-specific features (NOIRLab Astro Data Lab MyDB, SPARCL spectra, ALMA DataLink). It targets hosted deployment inside the NOIRLab Astro Data Lab platform and TACC, and is meant to be the data-access spine for natural-language astronomy workflows.

This is the first of a series of design docs for the project. It covers the **summer v1** target: a working hosted MCP server with the IVOA tool spine, the Data Lab MyDB extension, and a knowledge layer the LLM can consult before querying. Stretch goals (SPARCL, ALMA DataLink, full Hydra II workflow demo) are scoped to the same v1 but with explicit "stretch" markers. Items marked **out of scope** are deliberately deferred to follow-on specs.

### 1.1 Primary goals (in priority order)

1. **A deployed, usable MCP server** — connectable from an LLM integrated into Astro Data Lab, and from a separate deployment at TACC. Production-leaning, not a prototype.
2. **Demonstrable scientific workflows** — concretely, a complete Hydra II RR Lyrae candidate-selection workflow run end-to-end via the server, suitable for a research note.
3. **An evidence base for the documentation-recommendations research deliverable** — the eval harness produces structured data on which docs the LLM reads, which it skips, which lead to successful tool calls. This dataset is itself a deliverable.

### 1.2 Non-goals (for this spec)

- A general "do astronomy" agent. The server provides data access; reasoning, plotting, and statistical analysis remain on the LLM/client side.
- Replacing pyvo, datalab, or alminer. The server wraps them; the underlying libraries continue to do the actual archive talking.
- Multi-user collaboration features (shared MyDB, notebook sharing). The MCP is per-session.
- Jupyter-AI integration. That's a separate deliverable from the project brief; this spec leaves a clean interface for it.
- VLA archive (no scripted-download support as of 2026-06; discovery-only TAP doesn't earn a module yet).

---

## 2. Architectural approach

### 2.1 Approach chosen: layered IVOA spine + thin archive extensions

The server exposes two layers of tools:

- **IVOA generic layer** — one tool per protocol × operation. Archive endpoints are *parameters*, not tool boundaries. `vo_tap_query` is used identically for Data Lab, ALMA, NRAO/VLA, SDSS, CADC, etc.
- **Archive extensions** — added only where IVOA cannot do the job. Examples: Data Lab `MyDB` (writes user state, requires per-user creds), SPARCL (not an IVOA protocol), ALMA DataLink product staging.

Plus a third, parallel layer:

- **Knowledge layer** — a curated + ingested corpus of astronomy documentation, exposed as MCP Resources and searchable via a `kb_search` tool. This is the layer that lets an LLM make scientifically informed choices (catalog selection, column semantics, caveats, workflow patterns).

This approach was selected after considering two alternatives:

- **IVOA-only purist** — rejected because it kills the Data Lab MyDB workflow (which is the killer feature for the Hydra II demo).
- **Archive-first namespaces** (`dl_*`, `alma_*`, `nrao_*`) — rejected because tool count explodes past best-practice LLM tool-selection limits, and because it duplicates near-identical TAP wrappers per archive, contradicting the "extends to any IVOA archive" thesis from the project abstract.

The chosen approach delivers (a) full Hydra II workflow, (b) the "works for any IVOA archive" property, and (c) total tool count of ~13 in v1 hard and ~16 with stretch — within the LLM tool-selection sweet spot.

### 2.2 Server topology

```
                ┌──────────────────────────────────────────────┐
                │       LLM client (Claude / Jupyter-AI /      │
                │     ADL-integrated chat / Inspector / etc.)  │
                └──────────────────────┬───────────────────────┘
                                       │ Streamable HTTP + MCP
                                       │ (+ bearer token, when used)
                                       ▼
┌───────────────────────────────────────────────────────────────────┐
│  astro-archives-mcp  (FastMCP 3.x server)                         │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  AUTH LAYER  (pluggable provider)                           │  │
│  │  • NoAuth | BearerToken | OIDC/OAuth — chosen per env       │  │
│  │  • Resolves request → CallerContext{user, tokens, scopes}   │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─────────────── TOOL MODULES (composed) ─────────────────────┐  │
│  │   ivoa/      archives/datalab/   archives/alma/  knowledge/ │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌────────── SHARED BACKEND CLIENTS ────────────────────────────┐ │
│  │ TapClient, SiaClient, RegistryClient, DataLabClient,         │ │
│  │ SparclClient, AlmaClient — narrow typed wrappers over        │ │
│  │ pyvo / datalab / alminer. Tools never touch raw pyvo.        │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌────────── CROSS-CUTTING ───────────────────────────────────┐   │
│  │ Result shaper (inline / Resource / MyDB-staged)            │   │
│  │ Error mapper → MCP Tool Execution Errors                   │   │
│  │ Hint engine (rule-driven, Pattern C from §6)               │   │
│  │ Reference resources (endpoints, schemas, ADQL primer)      │   │
│  │ OTel spans per tool call                                   │   │
│  └────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

### 2.3 Module boundaries (four packages, each one clear purpose)

- **`mcp_app/`** — FastMCP server wiring, composition, lifespan, transport, health/ready routes. Knows nothing about astronomy.
- **`auth/`** — `AuthProvider` interface + concrete providers. Produces a `CallerContext` for each request.
- **`backends/`** — narrow typed clients. Wrap pyvo / datalab / alminer. Hide async-job mechanics, VOTable parsing, credential injection. Each independently testable.
- **`tools/`** — the actual MCP tools. Tools are thin: receive `CallerContext`, call one backend method, hand the result to the shaper, return. **No astronomy logic in this layer** — it lives in `backends/`.

### 2.4 Stack

- Python 3.12
- **FastMCP 3.x** (Prefect/jlowin) — the canonical Python MCP framework as of 2026-06. Not the bare `mcp` SDK. Provides decorators, OAuth providers, server composition, built-in OTel.
- **Streamable HTTP transport** (MCP spec 2025-11-25). No stdio, no legacy SSE.
- **Stateless HTTP mode** so the server scales horizontally without sticky sessions.
- **pyvo** for IVOA protocols. **datalab** (`astro-datalab` v2.24+) for NOIRLab. **alminer** as a convenience layer for ALMA where useful (not depended on for basic TAP).
- **sqlite-vec** (or lancedb) for the knowledge-base vector store. Embedded, no external service.
- **uv** for dependency management. **OpenTelemetry** for observability with MCP semantic conventions.

---

## 3. Tool catalog

Targeting ≤12 tools in v1 hard, ≤16 with stretch (within current LLM tool-selection best-practice limits). Slice tags: **[A1]** = first end-to-end spike, **[v1]** = summer v1 target, **[B]** = stretch / Hydra II demo.

### 3.1 IVOA generic tools (8)

| Tool | Signature (sketch) | Purpose | Slice |
|---|---|---|---|
| `vo_tap_query` | `(endpoint, adql, maxrec=10000, format='structured')` → result envelope | Sync ADQL against any IVOA TAP service. Auto-promotes to async if MAXREC hit or estimated cost high — returns a job handle instead of rows. | **A1** |
| `vo_tap_status` | `(job_url)` → `{phase, started_at, error?}` | Poll an async TAP job. | **v1** |
| `vo_tap_results` | `(job_url, format='structured')` → result envelope | Fetch completed async results. | **v1** |
| `vo_tap_abort` | `(job_url)` → `{aborted: bool}` | Cancel an async job. | **v1** |
| `vo_sia_search` | `(endpoint, ra, dec, size_deg, band?, format?)` → `{images:[{access_url, ra, dec, instrument, ...}]}` | Discover images / cutouts at a sky position. | **v1** |
| `vo_cone_search` | `(endpoint, ra, dec, radius_deg)` → result envelope | Simple Cone Search (SCS). Kept because many older services support only SCS. | **v1** |
| `vo_registry_search` | `(keywords?, servicetype?, waveband?)` → `{services:[{ivoid, title, tap_url?, description}]}` | Discover IVOA services via RegTAP. | **v1** |
| `vo_registry_describe` | `(ivoid_or_tap_url)` → `{capabilities, tables, columns}` | Introspect a chosen service's schema. | **v1** |

### 3.2 Data Lab extensions (3)

| Tool | Signature | Purpose | Slice |
|---|---|---|---|
| `dl_mydb_query` | `(adql, out_table?, async_=auto)` → `{rows?, mydb_table?, truncated, job_url?}` | If `out_table` set, writes result *server-side* to `mydb://{user}/{out_table}` and returns a reference — no client round-trip. Killer feature for large catalogs. | **v1** |
| `dl_mydb_list` | `()` → `{tables:[{name, nrows, created}]}` | List user's MyDB tables. | **v1** |
| `dl_mydb_drop` | `(table)` → `{dropped: bool}` | Delete a MyDB table. | **v1** |

Deliberately *not* exposed in v1: VOSpace file operations, the local-RAM `xmatch` helper (better done client-side), auth tools (handled by the auth layer not by tools).

### 3.3 Knowledge layer tools (2)

| Tool | Signature | Purpose | Slice |
|---|---|---|---|
| `kb_search` | `(query, kind?='any', limit=5)` → `{chunks:[{source, text, score, tier}]}` | Semantic search over the curated + ingested astronomy documentation corpus. Boosts curated chunks; reports tier. | **v1** |
| `object_resolve` | `(name)` → `{name, ra, dec, type, aliases}` | SIMBAD/SESAME name resolution. Prevents coordinate hallucination. | **v1** |

### 3.4 Stretch tools (3)

| Tool | Signature | Purpose | Slice |
|---|---|---|---|
| `sparcl_find` | `(constraints)` → `{spectra_ids, summary}` | SPARCL spectra discovery. Not IVOA. | **B** |
| `sparcl_retrieve` | `(ids, include=['flux','wavelength','ivar'])` → `{spectra:[...]}` | Fetch spectra by ID. | **B** |
| `alma_datalink_stage` | `(obs_ids)` → `{products:[{type, url, size_mb}]}` | Expand ALMA observation IDs into downloadable product URLs via DataLink. | **B** |

ALMA TAP queries go through `vo_tap_query` with the ALMA endpoint. No `alma_tap_query`.

### 3.5 MCP Resources (static)

Resources don't burn tool-selection budget; LLM lists and reads them on demand:

- `resource://archives/known` — well-known endpoints (Data Lab catalogs, ALMA TAP/SIA, NRAO/VLA TAP, CADC, ESO, GAIA, SDSS, …).
- `resource://archives/{archive}/overview` — when to use the archive, what it covers, gotchas.
- `resource://catalogs/{schema}.{table}/notes` — per-catalog: depth, footprint, photometric system, mag limits, useful flags, known issues, canonical ADQL examples.
- `resource://workflows/{slug}` — annotated end-to-end recipes (Hydra II RR Lyrae, dwarf galaxy candidate search, ALMA molecular line survey, cross-match recipe, …).
- `resource://adql/primer` — geometry / q3c / common idioms.
- `resource://glossary` — astronomy terms.
- `resource://decision_guides/{topic}` — "choosing a cone radius", "when to go async", etc.

### 3.6 Tool-count totals

| Configuration | Count |
|---|---|
| v1 hard set (IVOA + Data Lab MyDB + knowledge) | 13 |
| v1 + stretch (sparcl + ALMA datalink) | 16 |

Both fit within the LLM tool-selection sweet spot (5–8 ideal, ≤12 fine, problems past ~30).

### 3.7 Design rules applied

- **`vo_tap_query` is the workhorse.** Used across all IVOA-compliant archives.
- **Auto-promote sync → async.** The LLM can call naively; if the result would be huge, server returns a job handle. LLM is never silently lied to about completeness.
- **MyDB has its own tool**, not a flag on `vo_tap_query`. Different semantics (writes state, requires auth) earn distinct tool descriptions for the LLM.
- **No "smart" mega-tools.** No `find_galaxy_data(name)` that hides which archive/protocol is used. Visible seams help the LLM reason.
- **Static knowledge in Resources**, dynamic retrieval via `kb_search`.

---

## 4. Knowledge layer

This is the design's answer to "how does the LLM make scientifically rigorous decisions." It's also the engine behind the documentation-recommendations research deliverable.

### 4.1 Two-tier corpus

- **Tier 1 — Ingested external docs.** Mechanically scraped, refreshed on a schedule. Scope:
  - Data Lab: user manual, API reference, all training notebooks (`astro-datalab/notebooks-latest`).
  - ALMA: ALminer docs, ALMA Science Archive Manual, ALMA Help KB articles.
  - NRAO/VLA: scripted-access docs.
  - pyvo, astropy.timeseries (ADQL / TAP best practices).
  - IVOA specs: TAP, ADQL, SIA, VOResource, RegTAP.
  - Catalog references: SMASH, NSC, Legacy Surveys, DES, GAIA EDR3 (descriptions and column listings, not full astronomical-impact discussion).
  - Astropy and datalab cookbook recipes.
- **Tier 2 — Curated KB written by the team.** Narrow, high-quality, opinionated:
  - ~20 catalog notes with caveats and pitfalls.
  - 5–10 workflow recipes.
  - ADQL primer, glossary, 3–4 decision guides.

Both tiers go into the same vector store. Every chunk is tagged with `{tier, source_url, last_reviewed, archive, catalog?, tags}`. `kb_search` boosts curated chunks by default and reports tier so the LLM (and us, in evaluation) can distinguish authoritative-curated from scraped-external.

**Explicit out-of-scope for v1 corpus:** astronomical-impact discussion in discovery papers, textbooks, review articles on statistical rigor. Tempting but quickly drifts away from data-access and tanks `kb_search` precision. If a workflow needs such guidance, it gets a hand-written *decision guide* in Tier 2.

### 4.2 Access patterns

Three options were considered; two are adopted, one rejected.

| Pattern | Who | When | In v1? |
|---|---|---|---|
| **A. Explicit, LLM-driven** | LLM calls `kb_search` / reads a Resource | When uncertain | **Yes** — primary path |
| **B. Implicit server-side context injection** | Server appends chunks to every tool response or system context | Always | **No** — bloats responses, hides reasoning, fights LLM tool-calling, debugging nightmare |
| **C. Server-side hints on specific tool responses** | Server detects known caveats via rules and attaches `hints:[{kind, text, source}]` to the tool result | Triggered by specific rules | **Yes** — bounded safety net |

The server does **not** consult the KB to make decisions on its own. Pattern C attaches a *pointer* to a relevant resource on specific tool responses — a hint, not hidden retrieval.

### 4.3 Corpus location

Same repo as the server (`kb/` next to `src/`) for v1. Keeps the feedback loop tight; PRs can include both code and doc changes. Splitting to a separate repo is a "we're getting external contributors" decision deferred to a later spec.

### 4.4 Initial corpus seed (intern work, first ~4 weeks)

- ~20 catalog notes for the catalogs the demo workflows use.
- 5 workflow recipes (Hydra II RR Lyrae, cone-search → MyDB, cross-match recipe, ALMA line search, SIA cutout retrieval).
- ADQL primer, glossary, 3–4 decision guides.
- Initial ingest of Data Lab training notebooks (already structured well — good first ingest target).

---

## 5. Request lifecycle

### 5.1 The `CallerContext`

Constructed by the auth layer at the start of each request, passed implicitly to every tool, read-only:

```
CallerContext
├── caller_id          # opaque user id, or "anonymous"
├── auth_mode          # "none" | "bearer" | "oidc"
├── archive_creds      # mapping archive_name → credential (lazy, never logged)
├── scopes             # set of granted scopes
├── request_id
└── otel_ctx
```

Tools never look at HTTP headers, env vars, or the auth provider. They consult `ctx.archive_creds["datalab"]` and the layer below handles "is there a token, when does it expire."

### 5.2 Three representative flows

**Flow A — Sync TAP query (happy path).** LLM → FastMCP transport → auth provider → CallerContext → `vo_tap_query` dispatch → `TapClient.query()` → pyvo TAP `.search()` → VOTable → result shaper (inline, small) → hint engine (none) → error mapper (none) → OTel span closes → structured response to LLM.

**Flow B — Auto-promoted async TAP.** Same path up to `TapClient.query()`. Client estimates cost is above MAXREC → submits to `/async` (UWS) → returns immediately with `{status: "async_submitted", job_url, estimated_rows, phase: "EXECUTING", next_steps, tip_resource}`. The LLM uses `vo_tap_status` / `vo_tap_results` / `vo_tap_abort` (same `AsyncTAPJob` semantics as pyvo, exposed as three small tools instead of one mega-tool).

**Flow C — Authenticated MyDB write.** Auth provider produces `CallerContext` with `archive_creds["datalab"]` set. `dl_mydb_query` dispatch guards: if no creds → returns `auth_required` Tool Execution Error. Otherwise calls `DataLabClient.query(adql, out_table="mydb://hydra2_stars", token=…)`. Data Lab writes server-side; client returns reference. Tool returns `{status: "stored", mydb_table, row_count, next_steps}`. Token never appears in tool code, logs, or OTel attributes.

### 5.3 Cross-cutting invariants

- Auth solved once, at the edge. Tools assume they have what they need.
- Backends never return raw pyvo / datalab objects — always normalized dicts.
- Shaper decides inline / Resource / MyDB-staged. Tools don't decide.
- Hint engine runs after every result, bounded and rule-driven.
- OTel spans capture: tool name, caller_id, archive, latency, result size, error class, which resources / kb_search queries occurred in the same session. This feeds the documentation-recommendations dataset.

---

## 6. Result handling

### 6.1 Three-tier sizing

| Tier | Trigger | Returned shape |
|---|---|---|
| **Inline** | ≤ 1,000 rows AND payload ≤ ~512 KB | Full `rows` + `columns` in response |
| **Resource** | ≤ 100,000 rows AND payload ≤ ~10 MB | Inline `preview` (first 50 rows) + `columns` + `resource_uri: "resource://results/{uuid}.parquet"` (TTL 30 min) |
| **MyDB-staged** | Larger than Resource tier, or caller explicitly passes `out_table` | `preview` + `mydb_table: "mydb://..."` + `row_count`. Requires Data Lab creds. |

**`truncated` is always a top-level boolean** — never silently true. Inline results capped mid-fetch get `truncated: true` plus `truncation_reason`. This is the single biggest reliability difference from the ALMA_MCP prototype (which silently `df.head(20)`s everything).

### 6.2 Pagination & async (two separate mechanisms)

- **Pagination** for explicit follow-up: `vo_tap_query` accepts `cursor`, returns `next_cursor` when more rows are available. Backend injects `OFFSET` + stable `ORDER BY` if caller's ADQL lacks one.
- **Async** for big jobs: `vo_tap_query` auto-promotes to async and returns a job handle, then `vo_tap_status` / `vo_tap_results` / `vo_tap_abort` drive the job. Async results that complete go through the same shaper — a giant async result still gets staged to a Resource or MyDB.

### 6.3 Response envelope

Every tabular tool returns:

```json
{
  "row_count": 0,
  "columns": [
    {"name": "...", "type": "...", "unit": "...", "ucd": "...", "description": "..."}
  ],
  "rows": null,
  "preview": null,
  "resource_uri": null,
  "mydb_table": null,
  "truncated": false,
  "truncation_reason": null,
  "archive": "...",
  "next_steps": null,
  "hints": []
}
```

Numeric values are JSON numbers, not strings. NaN / masked → explicit `null` (no `"nan"` strings, no silent zero-fill). UCD included where pyvo provides it — the LLM's column-meaning hint.

### 6.4 Resource lifecycle

- Resource-tier results: 30-minute TTL from creation. URI includes expiry. LLM can re-request or escalate to MyDB-staged if it needs persistence.
- MyDB-staged: live in user's MyDB until user drops them. Server never drops user data implicitly. Tool response includes how to drop (`dl_mydb_drop`).
- No server-side disk caching across requests in v1.

---

## 7. Error taxonomy

Per MCP spec 2025-11-25, anything the model can recover from is a **Tool Execution Error** (`isError: true`), not a JSON-RPC protocol error.

### 7.1 Classes

| Class | When | LLM-actionable response |
|---|---|---|
| `validation_error` | Bad ADQL syntax, bad coords, missing required field | Exact field + one-line hint + resource pointer (e.g. `resource://adql/primer`) |
| `auth_required` | Tool needs creds, ctx has none | What auth mode is expected + how the host platform should provide it |
| `auth_forbidden` | Token present but lacks scope | What scope is missing |
| `archive_error` | Upstream archive returned 4xx/5xx | Sanitized upstream message + retry guidance |
| `archive_unavailable` | Connection refused, DNS, TLS error | Plain English + suggestion to use Registry for alternates |
| `tap_query_error` | TAP returned a structured error | Parsed reason + suggested ADQL fix when pattern-matchable (q3c index missing, column not found, geometry malformed) |
| `oversize` | Result exceeds all tiers | Suggest async submission or narrowing |
| `timeout` | Operation exceeded budget | Suggest async path |
| `internal_error` | Server bug | Generic message + `request_id`; full traceback only in server logs |

### 7.2 Error payload shape

```json
{
  "error_class": "tap_query_error",
  "message": "Column 'g_mag' not found in smash_dr2.object",
  "hint": "Did you mean 'gmag'? See resource://catalogs/smash_dr2.object.notes for the full schema.",
  "retry_strategy": "fix_and_retry",
  "retry_after_seconds": null,
  "request_id": "..."
}
```

- **`retry_strategy` is enumerated**: `fix_and_retry`, `wait_and_retry`, `submit_async`, `abandon`. The LLM doesn't have to parse English to decide whether immediate retry makes sense.
- **`hint` always points at the most specific resource available.** If we don't have one, the field is omitted (not "see the docs lol").

### 7.3 What the LLM sees vs what the server logs

| Audience | Sees |
|---|---|
| LLM | Redacted, structured, actionable error payload |
| Server logs (OTel + structured) | Full traceback, full ADQL, full upstream response, full timing |

Tokens, raw HTML error pages, and stack frames **never** reach the LLM.

---

## 8. Authentication

### 8.1 Pluggable provider interface

The auth provider is selected at startup by env var. Same server image runs in any deployment.

```
AuthProvider
├── async authenticate(request) → CallerContext
│
├── concrete: NoAuthProvider          → CallerContext{auth_mode: "none"}
├── concrete: BearerTokenProvider     → CallerContext{auth_mode: "bearer", archive_creds}
└── concrete: OidcProvider            → CallerContext{auth_mode: "oidc", scopes, archive_creds}
                                        (full impl deferred until ADL clarifies)
```

The `archive_creds` mapping is the key abstraction: tools never know whether the Data Lab token came from an env var, a forwarded bearer header, or an OIDC token exchange. They just ask `ctx.archive_creds["datalab"]`.

### 8.2 Deployment-specific auth choices

| Deployment | v1 auth provider | Rationale |
|---|---|---|
| Local dev | `NoAuth` | Cheap iteration; only public IVOA queries work, MyDB tools return `auth_required` |
| ADL | TBD — likely `BearerTokenProvider` consuming ADL-issued tokens or `OidcProvider` against ADL SSO | Decision pending Adele/Stephanie/Robert conversation in early June |
| TACC | TBD — likely `OidcProvider` against TACC TAS/Tapis | Decision pending TACC ops conversation |

OIDC implementation is stubbed in v1 and completed once the ADL/TACC auth conversations land. Pluggable interface ensures no refactor needed.

### 8.3 Open question

**The auth model is the single biggest open architectural variable in v1.** It's been deliberately isolated so the design can proceed without it being resolved. When ADL clarifies their LLM-integration auth plan, the appropriate provider concrete class is implemented and the `archive_creds` mapping is wired. No other architectural element changes.

---

## 9. Testing strategy

### 9.1 Engineering tests

- **Unit tests** — pure functions: result shaper, error mapper, hint engine, ADQL pagination injection. Fast, no network.
- **Backend client tests with recorded fixtures** — `vcrpy` / `pytest-recording` captures real pyvo/datalab HTTP traffic once, replays forever. Refreshed weekly in CI against a small "smoke catalog" to catch upstream drift.
- **Tool integration tests via in-memory MCP client** — FastMCP's `Client(server)` pattern, no transport. One test per tool: happy path + the 2–3 most likely error classes. Snapshot-test response shapes with `inline-snapshot`.
- **Contract tests** — every tool's output validates against its declared Pydantic schema.
- **Smoke tests against live deployment** — `npx @modelcontextprotocol/inspector --cli` runs `tools/list` + a handful of safe public queries in CI against staging.

Coverage rule: every tool has at least happy-path + auth-required + validation-error tests. No code-coverage percentage target (incentivizes the wrong thing).

### 9.2 TDD discipline

For each new tool: write the contract test + happy-path integration test *before* the implementation. Locks tool semantics in a test up front, which matters because tool return shape drifts fast under "let me just tweak this" pressure.

---

## 10. Evaluation harness

A separate `evals/` directory, runnable independently of server tests. This produces the research dataset for the documentation-recommendations deliverable.

### 10.1 Three eval kinds

| Eval | Tests | Example |
|---|---|---|
| **Workflow** | End-to-end multi-tool success on a scored task | "Find RR Lyrae candidates near Hydra II and return their IDs" — scored by overlap with a known reference set |
| **Tool-selection** | Did the LLM pick the right tool for an unambiguous prompt | "Find images at this position" → must pick `vo_sia_search`, not `vo_tap_query` |
| **Documentation** | Did the LLM read the right Resource / `kb_search` the right thing before the tool call | "Query SMASH for u-band" → expect a read of `resource://catalogs/smash_dr2.object.notes` before the query |

### 10.2 Mechanics

A driver script connects an LLM (Claude via the Anthropic SDK) to the MCP server, gives it a prompt, lets it run to completion, records the full trace (tools called, resources read, kb_search queries, final answer). Scoring scripts compute pass/fail and a structured per-step log.

Each eval task is a YAML file: `{prompt, expected_tools, expected_resources, scoring_rule, reference_data}`. Easy for interns to add new tasks.

### 10.3 Two baked-in tasks

- **Hydra II RR Lyrae workflow** — the flagship example from the abstract. Full multi-tool chain.
- **"Cross-archive" probe** — same prompt run against Data Lab and ALMA, scored by whether the LLM correctly uses generic `vo_tap_query` both times. Verifies the "extends to any IVOA archive" claim isn't aspirational.

### 10.4 Documentation-recommendations dataset

The eval traces, plus session-level OTel data from real usage, form the structured evidence for the brief's third deliverable. Concretely:

- Which Resources are load-bearing (frequently read, followed by successful tool calls)?
- Which are dead weight (never read)?
- Which `kb_search` queries returned nothing useful (corpus gaps)?
- Where did the LLM try a tool with wrong args because it skipped the right resource?

That's evidence-based documentation guidance.

---

## 11. Project structure

```
astro-archives-mcp/
├── pyproject.toml              # uv-managed, Python 3.12+
├── Dockerfile                  # slim, non-root, EXPOSE 8000
├── docker-compose.yml          # local dev (server + jaeger for OTel)
├── README.md
├── src/astro_archives_mcp/
│   ├── __main__.py
│   ├── app.py                  # FastMCP composition, lifespan, /health, /ready
│   ├── config.py               # env-driven Pydantic Settings
│   ├── auth/
│   │   ├── base.py             # AuthProvider interface, CallerContext
│   │   ├── none.py
│   │   ├── bearer.py
│   │   └── oidc.py             # stub in v1
│   ├── backends/
│   │   ├── tap.py              # TapClient (pyvo)
│   │   ├── sia.py
│   │   ├── registry.py
│   │   ├── datalab.py          # wraps dl.queryClient
│   │   ├── sparcl.py
│   │   └── alma.py             # alma datalink helpers
│   ├── tools/
│   │   ├── ivoa.py             # vo_tap_*, vo_sia_*, vo_cone_*, vo_registry_*
│   │   ├── datalab.py          # dl_mydb_*
│   │   ├── alma.py             # alma_datalink_stage (stretch — created when slice B is reached)
│   │   ├── sparcl.py           # sparcl_* (stretch — created when slice B is reached)
│   │   └── knowledge.py        # kb_search, object_resolve
│   ├── shaper.py               # result tier selection
│   ├── errors.py               # ToolExecutionError taxonomy
│   ├── hints.py                # rule-driven hint engine
│   ├── resources/
│   │   ├── server.py           # MCP Resource serving
│   │   └── results_store.py    # 30-min Parquet eviction
│   └── observability.py        # OTel setup, structured logging
├── kb/                         # versioned knowledge corpus
│   ├── catalogs/
│   ├── archives/
│   ├── workflows/
│   ├── adql/
│   ├── glossary/
│   ├── decision_guides/
│   └── ingest/                 # scripts to pull external docs
├── kb_index/                   # built artifacts (sqlite-vec); .gitignored, rebuilt in CI
├── tests/
│   ├── unit/
│   ├── backends/               # vcr fixtures
│   ├── tools/                  # in-memory client integration tests
│   └── contracts/
├── evals/
│   ├── tasks/                  # YAML task specs
│   ├── runner.py
│   ├── scoring.py
│   └── reports/                # generated; .gitignored
├── deploy/
│   ├── adl/                    # ADL-specific manifests
│   └── tacc/                   # TACC-specific manifests
└── docs/
    └── superpowers/specs/      # design docs + future plans
```

---

## 12. Deployment

- **Container**: Python 3.12 slim, uv-installed deps, non-root user, single entry point. Multi-stage build.
- **Config**: env vars only — no secrets baked into image. Pydantic `Settings` for typed parsing.
- **Health endpoints**: `/health` (liveness, no deps) + `/ready` (checks one TAP backend reachable). Kubernetes-friendly.
- **OTel exporter**: OTLP/gRPC by default, configurable target. Spans per tool call with attributes from §5.3. MCP semantic conventions (stable as of 2026).
- **Stateless HTTP mode** so deployments can scale horizontally without sticky sessions.
- **Two deployment profiles** selected by env var `DEPLOYMENT=adl|tacc`. Differ only in auth provider config and allowed archive list. Same image.

### 12.1 Reverse-proxy gotchas to test for

- Idle timeouts (60–75s default) silently kill the GET stream → require `proxy_read_timeout 3600s` and `proxy_buffering off`.
- MCP spec 2025-11-25 requires HTTP 403 on invalid `Origin` — proxy must not strip the header.
- No gzip compression on the SSE stream.
- Forward `MCP-Protocol-Version` header end-to-end.

---

## 13. Sequencing

| Weeks | Milestone |
|---|---|
| 1–2 | **Slice A**: server skeleton + `vo_tap_query` only + `NoAuth` + deployed to staging + Inspector hello-world. Kills risk on transport / deployment / tool shape. |
| 3–5 | Full IVOA tool set (8 tools) + result shaper + error taxonomy + Resource tier + eval harness scaffold |
| 6–8 | **Slice C**: Data Lab MyDB tools + knowledge layer + ingest pipeline + first 5 curated workflow recipes |
| 9–10 | Auth (whatever concrete provider ADL/TACC need) + deploy to both targets + smoke eval suite |
| 11–12 | **Slice B (stretch)**: sparcl + ALMA datalink + Hydra II full-workflow eval + research dataset for documentation paper |

---

## 14. Scope decomposition

### 14.1 In this spec (v1)

1. MCP server core + Streamable HTTP transport
2. Auth pluggability (`NoAuth` + `BearerToken` concrete; OIDC stub)
3. IVOA tool module (8 tools)
4. Data Lab module — MyDB subset (3 tools)
5. Knowledge layer — corpus structure, `kb_search`, `object_resolve` (2 tools)
6. Result shaper / error taxonomy / hint engine
7. Testing harness + eval framework
8. Deployment containers for ADL + TACC

### 14.2 Future specs (not in this one)

- **ALMA module + sparcl tools** — stretch within this summer if time permits, otherwise its own spec.
- **OIDC auth implementation** — once ADL clarifies their auth model.
- **Documentation-recommendations research paper** — its own writeup, driven by eval data.
- **Jupyter-AI integration** — separate deliverable from the project brief's "bonus."
- **Result caching layer.**
- **VLA module** — when scripted download lands.

---

## 15. Open questions

1. **Auth model** (largest variable). ADL meeting in early June will inform. Server design proceeds with `NoAuth` and `BearerToken` providers; OIDC stub becomes concrete once specifics land.
2. **Promotion threshold for sync→async TAP.** Design proposes heuristic auto-promotion with explicit `status: "async_submitted"` field. Heuristic specifics (MAXREC ratio, ADQL pattern matching, optional `EXPLAIN`-equivalent calls) tuned during implementation.
3. **`kb_search` ranking.** Curated Tier 2 chunks boosted; concrete boost factor TBD during corpus build-out. Eval data will inform tuning.
4. **TACC deployment specifics.** Container orchestration (k8s? Singularity?) confirmed after TACC ops conversation.
5. **Result Resource TTL of 30 min.** Reasonable default; revisit if usage shows longer-lived sessions.

---

## 16. References

- MCP Spec 2025-11-25 — Transports, Authorization, Tasks primitive.
- FastMCP 3.x (Prefect/jlowin) — Python MCP framework.
- pyvo — IVOA reference Python implementation.
- `astro-datalab` v2.24+ — Data Lab client library.
- alminer — ALMA convenience wrapper.
- ALMA_MCP prototype (`adamzacharia/ALMA_MCP`) — referenced for docstring-style ergonomics and `summary` field pattern only; not adopted as architectural base.
- Project brief: STABLE (Summer Team for Astronomical Benchmarking & LLM Engineering), CosmicAI initiative.
