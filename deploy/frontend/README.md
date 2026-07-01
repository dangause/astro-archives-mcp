# Frontend stack (dockerized) — MCP + Jupyter AI persona

The **frontend** half of the system: the astro-archives **MCP tool server** plus a
**Jupyter AI persona** (Claude Code), containerized and runnable in two modes. The
**model** lives elsewhere (dlai01 vLLM, reached over the network) — see
`../dlai01-vllm-runbook.md`. Architecture recap:

```
[ this stack: MCP + persona + Jupyter ]  ──(model, ANTHROPIC_BASE_URL)──►  dlai01 vLLM
        run locally now, lifts to gp13                                     (443, once open)
```

## Modes

| Mode | What runs | URL | Use when |
|------|-----------|-----|----------|
| **chat** | `mcp` + one JupyterLab (Jupyter AI chat panel) | http://localhost:8888 | You just want to chat with model+persona+tools. No Hub. |
| **hub**  | `mcp` + JupyterHub (DockerSpawner → one frontend container per user) | http://localhost:8081 | Multi-user; the gp13 mirror. |

The `mcp` service runs in both modes; pick exactly one of `chat`/`hub`.

## Quick start

```bash
cp .env.example .env          # set the model endpoint + token (or leave blank for hosted Claude)

# chat mode
docker compose --profile chat up --build
# → open http://localhost:8888, open the Jupyter AI chat, @-mention the persona

# hub mode
docker compose build lab      # build the single-user image DockerSpawner launches
docker compose --profile hub up --build
# → open http://localhost:8081, log in (dummy auth, JUPYTERHUB_DUMMY_PASSWORD)
```

## Configuration (`.env`)

- **Model backend:** set `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` to the dlai01
  endpoint once 443 is open (the token = vLLM's `--api-key`). Leave blank to use
  **hosted Claude** — useful for exercising the frontend *before* 443 is ready.
- `ANTHROPIC_DEFAULT_*_MODEL` must match vLLM's served model name.
- `CLAUDE_CODE_MAX_OUTPUT_TOKENS` caps output to fit the served window (runbook Gotcha 4).
- Hub mode: `JUPYTERHUB_DUMMY_PASSWORD`, and `DOCKER_NETWORK` must equal the compose
  network (`<project>_default`; default `frontend_default` — update if you run with a
  different `-p` project name).

## How it maps to the tools

- **MCP** is a shared service at `http://mcp:8000/mcp/` (see `mcp_settings.json`, baked
  into the frontend image at `~/.jupyter/`). Simple for local dev (Topology B).
  gp13 may instead **colocate** MCP inside each user image (Topology A,
  `../../docs/examples/gp13/`) — the persona config is otherwise identical.
- **Persona** = `claude-agent-acp` wrapping the `claude` CLI; reads the model endpoint
  from the injected `ANTHROPIC_*` env.

## Lifting to gp13

Same images. On gp13, ADL ops point their JupyterHub's single-user image at this
frontend image (or the colocated `docs/examples/gp13/` variant) and inject the same
`ANTHROPIC_*` env for the model + the MCP `mcp_settings.json`. The `chat` mode is a
faithful stand-in for a single spawned user session.

## Status / caveats

- **`chat` mode VALIDATED end-to-end** (2026-07-01, macOS arm64, hosted Claude): both
  images build; `mcp` service healthy; the lab container has node + `claude` +
  `claude-agent-acp` + jupyter-ai 3.0.1 + seeded `mcp_settings.json`; reaches
  `http://mcp:8000` cross-container; JupyterLab serves; and an **in-container persona call
  resolved M51 via the MCP tool** (persona → hosted Claude → `mcp:8000` →
  `vo_target_resolve`). First-run fixes: host port is now `JUPYTER_PORT` (8888 was taken),
  and — see below — the `*_MODEL` overrides must be cleared for hosted Claude.
- **Gotcha — `ANTHROPIC_DEFAULT_*_MODEL` is backend-coupled.** Set to vLLM's served name
  for the local backend; **comment out for hosted Claude** or Claude Code requests a
  "Qwen/…" model Anthropic doesn't have ("model may not exist"). See `.env.example`.
- **Not yet exercised:** the **local dlai01 backend** over 443 (needs 443 open +
  authenticated, pending IT — flip to Option B in `.env`), and **`hub` mode** (not yet
  built/run — watch the jupyterhub↔singleuser version match and the `DOCKER_NETWORK` name).
- **Auth is dummy** in hub mode — local dev only. Replace the authenticator for anything
  exposed.
