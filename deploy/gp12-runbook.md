# gp12 Deployment Runbook — astro-archives-mcp via Jupyter AI

Status: **design draft** for review by ADL ops. Goal: surface the VO tools to
notebook users on Astro Data Lab's **gp12**, a shared JupyterHub that spawns a
per-user single-user server (VM/container) per session, through **Jupyter AI v3**
chat. See `docs/jupyter-ai-integration.md` for the architecture and the
locally-validated test (2026-06-25).

> **Assumptions flagged for ADL ops** (confirm before building — they change the
> mechanics below):
> 1. The single-user image derives from **jupyter/docker-stacks** (so
>    `before-notebook.d/` start hooks exist). If it's a bespoke image or VM, the
>    hook becomes a systemd unit / entrypoint line instead.
> 2. Each user's **`$HOME` is a writable, non-tiny persistent volume**. astropy &
>    pyvo write caches under `~/.astropy` and `$TMPDIR`; a read-only or full
>    volume makes every `vo_target_resolve` / `vo_registry_search` fail with
>    `archive_error` (we hit exactly this with a disk-full container in testing).
> 3. The chosen **persona LLM backend** (hosted Claude vs. local model on dlai01)
>    and how its credentials are provisioned — see §4.

## Topology: colocated vs. shared

| | **A. Colocated (recommended to prove first)** | **B. Shared service** |
|---|---|---|
| Where | MCP server runs *inside* each single-user server on `127.0.0.1` | One MCP deployment all user pods reach over the cluster network |
| Config URL | `http://127.0.0.1:8000/mcp/` | `http://astro-mcp.<ns>:8000/mcp/` |
| Auth | none (loopback, anonymous read-only tools) | none needed (anonymous), but exposed off-loopback → see `deploy/staging-runbook.md` proxy/timeout notes |
| Pros | identical to the local recipe, zero network/auth surface, per-user isolation | one upgrade path, no per-user process/cache duplication |
| Cons | N server processes + N astropy caches | requires user-pod → service reachability; one shared blast radius |

Because the tools are anonymous and read-only, **A** is the path of least resistance
to a first rollout and is what the rest of this runbook details. **B** becomes
attractive once it's proven and you want a single thing to operate/upgrade — at
that point deploy the existing container (see `deploy/staging-runbook.md`) as a
cluster service and only change the config URL.

## What the single-user image needs (Topology A)

> **Locally validated (2026-06-26).** A `docs/examples/gp12/Dockerfile` builds these
> additions onto `jupyter/minimal-notebook`; in the running container the hook launched
> the MCP server on loopback, the seeded config was in place, and `vo_target_resolve`
> returned real coordinates (astropy cache writable). Untested: node + the ACP adapter /
> persona LLM call, and gp12's actual base image.
>
> **Build the single-user image with the example dir as context, not the repo root:**
> ```bash
> docker build -t astro-archives-singleuser docs/examples/gp12/
> ```
> The repo-root `.dockerignore` excludes `docs/`, `deploy/`, `tests/`, so a repo-root
> context can't `COPY` the hook or config. Building from the subdir sidesteps that.

1. **Python deps** — Jupyter AI v3 and this server, into the image's env:
   ```dockerfile
   RUN pip install --no-cache-dir "jupyter-ai>=3" jupyterlab \
       "astro-archives-mcp @ git+https://github.com/dangause/astro-archives-mcp.git@v0.3.0"
   ```
   Pin to a tag/commit for reproducibility; bump deliberately.

2. **Node.js + the Claude ACP adapter** (the persona's agent binary):
   ```dockerfile
   RUN npm install -g @zed-industries/claude-agent-acp   # provides `claude-agent-acp`
   ```
   (npm warns this was renamed to `@agentclientprotocol/claude-agent-acp`; either works.)
   Skip this if you back the persona with a local model instead (§4).

3. **Pre-warm the pyvo/astropy caches at build time** so the first user query
   doesn't pay a network+disk hit (and so a momentarily-tight `$TMPDIR` can't
   break vocabulary downloads):
   ```dockerfile
   RUN python -c "from pyvo.utils import vocabularies as v; v.get_vocabulary('messenger')"
   ```

4. **Start the MCP server on loopback** when the single-user server boots — copy
   `docs/examples/gp12/before-notebook.d/10-astro-archives-mcp.sh` to
   `/usr/local/bin/before-notebook.d/` in the image. It launches the server in the
   background on `127.0.0.1:8000` with writable cache env, and is idempotent.
   > More robust alternative (ties lifecycle to the server, restarts on crash): a
   > small Jupyter Server extension that manages the subprocess. The hook is fine
   > to start; revisit if crash-recovery matters.

5. **Seed the MCP config** so the persona discovers the server. Jupyter AI reads
   `.jupyter/mcp_settings.json` walking up from the chat dir to the JupyterLab
   root, so the catch-all location is the user's home:
   `~/.jupyter/mcp_settings.json` = `docs/examples/gp12/mcp_settings.json`.
   - If `$HOME` is freshly materialized from the image each spawn, bake it into the
     image's home (or `/etc/skel`).
   - If `$HOME` is a pre-existing persistent volume, seed it via a JupyterHub
     pre-spawn hook or a one-time migration — baking into the image won't reach
     already-provisioned homes.

## 4. Persona credentials at scale (the main ADL decision)

The persona is Claude Code (`claude-agent-acp`), which authenticates exactly like
the `claude` CLI — it reads credentials from `$CLAUDE_CONFIG_DIR` (default
`~/.claude`). Options, independent of this MCP server:

- **Per-user login** — each user runs `claude /login` once; creds persist in their
  home volume. No shared secret; users need their own Anthropic access.
- **Shared org credentials** — provision an NRAO/CosmicAI key into the image env
  (`ANTHROPIC_API_KEY`) or a baked `~/.claude`. Simplest UX; shared billing &
  governance. Pin the account with `CLAUDE_CONFIG_DIR` (the same mechanism used to
  select the work account in local testing).
- **Local model on dlai01** — point Claude Code at an on-prem model via
  `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN`. No per-call cost, data stays on-prem;
  tool-use quality depends on the model. Orthogonal to everything above — the MCP path
  is unchanged. See **`docs/local-model-backend.md`** for the researched PoC stack
  (vLLM native Anthropic endpoint + Qwen3 + tool-call/reasoning parser flags) and the
  Blackwell/sm_120 serving gotchas.

## Verify (inside a spawned single-user server)

```bash
curl -fsS http://127.0.0.1:8000/health                       # astro-archives 0.3.0
cat ~/.jupyter/mcp_settings.json                             # points at 127.0.0.1:8000/mcp/
ps eww $(pgrep -f 'jupyter-lab') | tr ' ' '\n' | grep CLAUDE_CONFIG_DIR  # if pinning an account
```
Then in JupyterLab chat: `@Claude use the astro-archives tools to resolve M51.`
Success = the server log shows a `CallToolRequest` and the reply carries real
coordinates (RA 202.47, Dec +47.20), not a model guess.

## Open questions for ADL ops

- Spawner & base image (docker-stacks? KubeSpawner/DockerSpawner? bespoke VM)?
- Is `$HOME` per-spawn-fresh or a persistent volume? (decides config seeding)
- Persona backend + credential model (§4)?
- Topology A vs. B for the operated rollout?
