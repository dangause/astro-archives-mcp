# dlai01 Model-Hosting — Validation Record & Runbook

**What this documents:** hosting an open-weight LLM (Qwen3.5) on the dlai01 GPU box
via vLLM, and consuming it from a Claude Code persona that calls the astro-archives
**MCP** tool server — the full local-model chain, proven end to end. Exact working
commands, verified results, and every gotcha we hit.

Paired with `docs/local-model-backend.md` (the *why* behind model choice) and
`docs/jupyter-ai-integration.md` (the persona/MCP architecture). Status: **local chain
VALIDATED**; not yet exposed off-box (see *Current status* at the end).

---

## Architecture

Two hosts, split backend/frontend:

- **dlai01** — the **backend / model host**: 4× RTX PRO 6000 Blackwell, runs vLLM
  serving the LLM. Where the GPUs and docker access live.
- **gp13** — the production **frontend**: a shared JupyterHub running Jupyter AI + the
  Claude Code persona per user. (Not yet accessible; the MCP server + a JupyterHub are
  being stood up locally first as a gp13 stand-in.)

The chain, and the two independent connections the persona makes:

```
JupyterLab (Jupyter AI v3)
      │
      ▼
 ACP persona = Claude Code ──(model)──► vLLM  [ANTHROPIC_BASE_URL]      ← dlai01
      │
      └─────────────────────(tools)──► astro-archives MCP  [/mcp/]      ← colocated
```

- **Model** and **tools** are orthogonal: the `vo_*` tools work identically no matter
  which model backs the persona (hosted Claude or local vLLM).
- The persona talks to the model over the **Anthropic Messages API** — vLLM implements
  it natively, so **no translation proxy** is needed.

## The box (dlai01)

- Rocky Linux 10, **4× RTX PRO 6000 Blackwell** ~96 GB ea (~384 GB total), **sm_120**,
  driver 610.43.02 / CUDA UMD 13.3.
- User `dgause`: in the `docker` group, **no sudo / no host software installs** →
  everything runs in containers.
- GPU-in-container verified (`docker run --gpus all … nvidia-smi -L` lists all 4).

## What's validated

| Date | Milestone |
|------|-----------|
| 2026-06-29 | MCP server rootless on dlai01; persona chain proven with **hosted Claude** (headless `claude -p`, M51 resolved via `vo_target_resolve`). |
| 2026-06-30 | **Local-model plumbing** proven — Qwen2.5-7B on vLLM (sm_120 works out of the box; native `/v1/messages`; tool call fired). |
| 2026-07-01 | **Production model** proven — **Qwen3.5-122B-A10B-FP8**, TP=4, resolved M51 (RA 202.469575 / Dec +47.19525833 ICRS) via a real tool call. |

## Prerequisites (resolved by IT, 2026-06-29)

All in-container; no host installs needed from us.

1. **Docker image storage on real space.** The vLLM image is ~20 GB extracted; the
   default docker fs was 16 GB → `no space left on device`. **Subtlety that cost a
   round-trip:** this box uses Docker's **containerd image store**
   (`Storage Driver: overlayfs`), so image layers land in **`/var/lib/containerd`**,
   *not* the `/var/lib/docker` reported as "Docker Root Dir". Growing `/var/lib/docker`
   did nothing; the fix was giving `/var/lib/containerd` its own 250 GB volume. **If you
   ever hit this again, check `df -h /var/lib/containerd`.**
2. **Writable weights dir** — `/mlhome/dgause` (7 TB NVMe), owned by `dgause`, for the
   HF cache (`-v /mlhome/dgause/hf:/root/.cache/huggingface`).
3. **nvidia-container-toolkit** installed → GPU passthrough into containers.

---

## Part 1 — the MCP tool server

Runs rootless via `uv` on loopback (read-only VO tools; no auth needed on loopback).

```bash
cd ~/sbx/astro-archives-mcp
export PATH="$HOME/.local/bin:$PATH" XDG_CACHE_HOME="$HOME/.cache"   # writable astropy/tmp cache
nohup env STABLE_PORT=8000 uv run python -m astro_archives_mcp > ~/sbx/mcp.log 2>&1 &
curl -fsS http://127.0.0.1:8000/health        # {"status":"ok","version":"0.3.0",...}
```

Register it with Claude Code — **user scope is required** (see Gotcha 3):

```bash
CLAUDE_CONFIG_DIR=$HOME/.claude-work \
  claude mcp add --scope user --transport http astro-archives http://127.0.0.1:8000/mcp/
CLAUDE_CONFIG_DIR=$HOME/.claude-work claude mcp list       # astro-archives: ✓ Connected
```

## Part 2 — hosting the model on vLLM

**Model: `Qwen/Qwen3.5-122B-A10B-FP8`** (122B total / ~10B active MoE). Chosen via a
fact-checked model survey (`docs/local-model-backend.md`): near-top open-weight BFCL V4
(~0.722), fits FP8 (~122 GB) with large KV-cache headroom, MoE decode is fast and
concurrency-friendly. Tool-call parser: `qwen3_coder`. Runner-up to A/B later:
**GLM-4.7** (τ²-Bench 87.4, but 358 GB FP8 leaves little KV room → poor concurrency).

> The lighter **Qwen2.5-7B-Instruct** (parser `hermes`, `--max-model-len 32768`) is the
> de-risking PoC — same command, smaller model — used 2026-06-30 to prove vLLM runs on
> sm_120 and the Anthropic path carries tool calls before committing to the big download.

Launch (weights cache to `/mlhome`; ~122 GB pull first time, then loads from cache):

```bash
docker rm -f vllm 2>/dev/null
docker run -d --name vllm --gpus all --ipc=host \
  -v /mlhome/dgause/hf:/root/.cache/huggingface \
  -p 127.0.0.1:8001:8000 \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen3.5-122B-A10B-FP8 \
  --tensor-parallel-size 4 \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder \
  --max-model-len 65536
docker logs -f vllm            # wait for "Application startup complete" (~130 s)
```

Notes / verified behavior:
- **sm_120 works out of the box** on `vllm/vllm-openai:latest` (vLLM **v0.23.0**) —
  FlashAttention 2, FlashInfer, torch.compile, CUDA graphs all initialize; no special
  tag/recipe. Arch resolves as `Qwen3_5MoeForConditionalGeneration`.
- **Native Anthropic endpoint present:** `Route: /v1/messages` is in the served route
  list and returns a proper `{"type":"message",...,"stop_reason":"end_turn"}` — **no
  proxy**. Quick check:
  ```bash
  curl -s http://127.0.0.1:8001/v1/messages -H 'content-type: application/json' \
    -d '{"model":"Qwen/Qwen3.5-122B-A10B-FP8","max_tokens":64,"messages":[{"role":"user","content":"hi"}]}'
  ```
- **Benign multi-GPU warnings on sm_120** (not errors): `SymmMemCommunicator: Device
  capability 12.0 not supported` and `Custom allreduce is disabled … PCIe-only GPUs` →
  both fall back to NCCL.
- **`--reasoning-parser` is deliberately omitted** — see Gotcha 5.

## Part 3 — consuming it (the Claude Code persona)

The persona reads its endpoint from env; point it at vLLM and run the validation. Use a
**scoped tool allowlist**, not `--dangerously-skip-permissions` (Gotcha 2):

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8001
export ANTHROPIC_AUTH_TOKEN=dummy                 # any value while on loopback; a real secret once exposed
export ANTHROPIC_DEFAULT_OPUS_MODEL=Qwen/Qwen3.5-122B-A10B-FP8
export ANTHROPIC_DEFAULT_SONNET_MODEL=Qwen/Qwen3.5-122B-A10B-FP8
export ANTHROPIC_DEFAULT_HAIKU_MODEL=Qwen/Qwen3.5-122B-A10B-FP8
export CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192          # REQUIRED — Gotcha 4

: > ~/sbx/mcp.log                                  # clear so the tool-fire check is unambiguous
CLAUDE_CONFIG_DIR=$HOME/.claude-work \
  claude -p "Use the astro-archives MCP tools to resolve M51. Call the tool; do not guess." \
  --allowedTools "mcp__astro-archives__vo_target_resolve"
grep -c "CallToolRequest" ~/sbx/mcp.log            # ≥1 = tool actually fired
```

> **VALIDATED 2026-07-01.** Returned M51 = **RA 202.469575° / Dec +47.19525833° (ICRS)**
> — driven by the local Qwen3.5-122B-A10B on vLLM, via the no-proxy Anthropic endpoint,
> via the persona, calling `vo_target_resolve`. The `⚠ claude.ai connectors are
> disabled…` line is benign (it just means the env auth/base-URL is in use → routing to
> vLLM). Note: `<think>` currently leaks into the reply text — cosmetic, see Gotcha 5.

---

## Gotchas & lessons learned

1. **containerd image store, not `/var/lib/docker`.** `Storage Driver: overlayfs` →
   image layers live in `/var/lib/containerd`. Sizing/pull failures: check
   `df -h /var/lib/containerd`.
2. **Use a scoped tool allowlist, never `--dangerously-skip-permissions`.**
   `--allowedTools "mcp__<server>__<tool>"` grants exactly that tool and denies
   everything else (no filesystem/bash), with no interactive prompts in `-p` mode.
3. **`claude mcp add --scope user`.** The default `local`/project scope only loads when
   `claude` runs from that project dir; `-p` from `~` saw *no* servers and the model
   reported "no astro-archives tools". User scope loads everywhere.
4. **Token budget — two failure modes.** (a) Claude Code requests up to `32000` output
   tokens by default; if that exceeds `--max-model-len`, vLLM returns **HTTP 500**. (b)
   Claude Code's input floor is **~24.5K tokens** (its system prompt + the 12 `vo_*`
   tool schemas). Fix: run vLLM at a generous `--max-model-len` (≥65536) **and** cap
   `CLAUDE_CODE_MAX_OUTPUT_TOKENS` (8192). Long agent loops accumulate tool results, so
   headroom matters.
5. **The Qwen3 `<think>` tool-loss footgun (vLLM #39056) — and the mitigation we use.**
   With `--reasoning-parser qwen3` + `--tool-call-parser qwen3_coder`, a `<tool_call>`
   emitted inside `<think>` is pulled into the *reasoning* field and never reaches the
   tool parser → **silently dropped**. This is the real basis of the "Qwen3.5 is bad at
   tools" rumor (the model is actually top of open-weight BFCL). **Mitigation: omit
   `--reasoning-parser`** — the call stays in `content` where `qwen3_coder` finds it.
   Verified working (thinking stays on, tool still fires). **Side effect:** raw
   `<think>…</think>` text leaks into the reply. Cosmetic; deferred to gp13-deployment
   cleanup. The clean fix is a request-level `chat_template_kwargs:{enable_thinking:
   false}`, which Claude Code doesn't expose — so it'll need a thin proxy that injects
   it, a custom chat template baked into the served model, or a non-thinking checkpoint.
   (`vllm serve --help` crashes in this build, so there's no easy serve-flag route.)
6. **FP8 KV cache left OFF for now.** `--kv-cache-dtype fp8` roughly halves KV memory
   (a big concurrency lever) but is unvalidated on sm_120 here, and reportedly produced
   garbled output for another model on this GPU — validate before enabling.

## Current status & next steps

**Done:** local model (Qwen3.5-122B-A10B) hosted on dlai01 and consumed by the persona
+ MCP, end to end. All on loopback / inside dlai01.

**Next (not yet started):**
- **Expose dlai01's vLLM off-box via authenticated TLS on 443.** External traffic to
  dlai01 is being opened by IT on **443 only** (no port 80). Requires a TLS-terminating
  reverse proxy (Caddy/nginx) in front of vLLM **and a bearer token** (`vllm --api-key`,
  client sends it as `ANTHROPIC_AUTH_TOKEN`) — an open internet LLM endpoint must not be
  unauthenticated. Cert for `dlai01.csdc.noirlab.edu` (Let's Encrypt once 443 is
  reachable, or IT-provided).
- **Dockerized frontend as a gp13 stand-in** (run locally first): MCP server + Jupyter AI
  + persona, persona pointed at `https://dlai01.csdc.noirlab.edu` + token. Dockerized so
  it lifts to gp13 unchanged.
- **Thinking-off** cleanup (Gotcha 5) for clean chat UX.
- **Concurrency load test** at agentic context lengths (KV cache is the limiter;
  prefix-caching the ~24.5K static tool-schema prefix is the big lever) to size gp13.

## Quick reproduce (all-in-one)

```bash
# 1. MCP server (rootless, loopback)
cd ~/sbx/astro-archives-mcp && export PATH="$HOME/.local/bin:$PATH" XDG_CACHE_HOME="$HOME/.cache"
nohup env STABLE_PORT=8000 uv run python -m astro_archives_mcp > ~/sbx/mcp.log 2>&1 &
CLAUDE_CONFIG_DIR=$HOME/.claude-work claude mcp add --scope user --transport http astro-archives http://127.0.0.1:8000/mcp/

# 2. Model on vLLM (TP=4)
docker rm -f vllm 2>/dev/null
docker run -d --name vllm --gpus all --ipc=host \
  -v /mlhome/dgause/hf:/root/.cache/huggingface -p 127.0.0.1:8001:8000 \
  vllm/vllm-openai:latest --model Qwen/Qwen3.5-122B-A10B-FP8 \
  --tensor-parallel-size 4 --enable-auto-tool-choice --tool-call-parser qwen3_coder --max-model-len 65536

# 3. Persona → local model, validate
export ANTHROPIC_BASE_URL=http://127.0.0.1:8001 ANTHROPIC_AUTH_TOKEN=dummy CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192
export ANTHROPIC_DEFAULT_OPUS_MODEL=Qwen/Qwen3.5-122B-A10B-FP8 \
       ANTHROPIC_DEFAULT_SONNET_MODEL=Qwen/Qwen3.5-122B-A10B-FP8 \
       ANTHROPIC_DEFAULT_HAIKU_MODEL=Qwen/Qwen3.5-122B-A10B-FP8
CLAUDE_CONFIG_DIR=$HOME/.claude-work claude -p \
  "Use the astro-archives MCP tools to resolve M51. Call the tool; do not guess." \
  --allowedTools "mcp__astro-archives__vo_target_resolve"
```
