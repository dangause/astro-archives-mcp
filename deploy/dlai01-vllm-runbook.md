# dlai01 Local-Model Runbook — vLLM backend for the Jupyter AI persona

Status: **operational runbook**, paired with the research doc
`docs/local-model-backend.md` (the *why* — model choice, Blackwell serving notes,
tool-call gotchas, concurrency). This is the *how*: the exact bring-up sequence on
dlai01, smallest-risk-first. The persona→MCP path itself is already proven (hosted
Claude, 2026-06-29); this swaps the model backend underneath it.

## The box (established)

- Rocky Linux 10, **4× RTX PRO 6000 Blackwell** 96 GB ea (~384 GB), **sm_120**,
  driver 610.43.02 / CUDA UMD 13.3.
- **GPU-in-container verified** (`docker run --gpus all … nvidia-smi -L` lists all 4).
- User `dgause`: docker group, **no sudo / no host installs** → everything runs in
  containers.

## Prerequisites (IT — both pending as of 2026-06-29)

Both resolved by IT 2026-06-29 (no host access needed from us — everything else runs
in containers):

1. **Docker image storage on real space.** The vLLM image is ~20 GB extracted; the
   default docker fs was 16 GB → `no space left on device`. **Subtlety that cost a
   round-trip:** this box uses Docker's **containerd image store**
   (`Storage Driver: overlayfs`), so image layers land in **`/var/lib/containerd`**,
   *not* the `/var/lib/docker` reported as "Docker Root Dir". Growing `/var/lib/docker`
   did nothing; the fix was giving `/var/lib/containerd` its own 250 GB volume
   (`noirlab-containerd`). If you ever hit this again, check `df -h /var/lib/containerd`,
   not `/var/lib/docker`.
2. **Writable weights dir** — `/mlhome/dgause` (the 7 TB NVMe), owned by `dgause`, for
   the HF model cache (`-v /mlhome/dgause/hf:/root/.cache/huggingface`).

## Step 1 — bring vLLM up on a small model (prove the plumbing)

The two real risks are independent of model size: **does vLLM run on sm_120 at
all**, and **does the Anthropic-API path carry tool calls**. Shake those out on a
7B that downloads in minutes, *then* scale.

```bash
MODELS=/mlhome/dgause/hf             # writable NVMe dir (IT-provisioned 2026-06-29)
mkdir -p "$MODELS"
docker run -d --name vllm --gpus all --ipc=host \
  -v "$MODELS":/root/.cache/huggingface \
  -p 127.0.0.1:8001:8000 \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen2.5-7B-Instruct \
  --enable-auto-tool-choice --tool-call-parser hermes \
  --max-model-len 32768
docker logs -f vllm        # Ctrl-C after "Application startup complete"
```

Single 7B on one GPU — no tensor-parallel needed yet. `hermes` is the correct
tool-call parser for the Qwen2.5 family. No reasoning/thinking flags here, so the
Qwen3 `<think>` tool-loss footgun (research §4) doesn't apply. Use the model's full
`--max-model-len 32768`, not a smaller value — Claude Code's input alone is ~24.5K
tokens (see Gotchas).

> **sm_120 works out of the box — CONFIRMED 2026-06-29.** `vllm/vllm-openai:latest`
> (vLLM **v0.23.0**) ran cleanly on the RTX PRO 6000 Blackwell with FlashAttention 2,
> FlashInfer, torch.compile and CUDA graphs — *no* special tag or recipe needed.
> Startup ~95 s first boot (compile + CUDA-graph capture), faster after via the
> compile cache. If a *future* image ever regresses with `sm_120` / `no kernel image`,
> fall back to a Blackwell-validated vLLM (research §2: recent vLLM + `torch …+cu130`
> + matched FlashInfer/Triton, per blackwell-llm-toolkit) and pin the versions here.

## Step 2 — verify serving + the native Anthropic endpoint

```bash
curl -s http://127.0.0.1:8001/v1/models                       # served model name
curl -s http://127.0.0.1:8001/v1/messages \
  -H 'content-type: application/json' \
  -d '{"model":"Qwen/Qwen2.5-7B-Instruct","max_tokens":64,
       "messages":[{"role":"user","content":"say hi in 3 words"}]}'
```

- `/v1/messages` returns JSON → vLLM's **native Anthropic Messages API** is live;
  Claude Code points straight at it, **no proxy** (research §1).
- `/v1/messages` → 404 → this image lacks the endpoint; drop in the **LiteLLM** or
  **claude-code-router** shim (research §1) and point `ANTHROPIC_BASE_URL` at the
  shim instead.

> **CONFIRMED 2026-06-29 (v0.23.0):** `/v1/messages` is present (it's in the served
> route list) and returns a proper Anthropic-shaped reply
> (`{"type":"message","role":"assistant","content":[{"type":"text",...}],
> "stop_reason":"end_turn"}`). **No proxy needed.**

## Step 3 — point the persona at the local model, re-run the M51 tool call

Claude Code reads its endpoint from env; the persona inherits it (same trick as
`CLAUDE_CONFIG_DIR`). Re-run the exact validation that passed against hosted Claude
on 2026-06-29 — only the backend changes:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8001
export ANTHROPIC_AUTH_TOKEN=dummy                  # any value; vLLM ignores it
export ANTHROPIC_DEFAULT_OPUS_MODEL=Qwen/Qwen2.5-7B-Instruct
export ANTHROPIC_DEFAULT_SONNET_MODEL=Qwen/Qwen2.5-7B-Instruct
export ANTHROPIC_DEFAULT_HAIKU_MODEL=Qwen/Qwen2.5-7B-Instruct
export CLAUDE_CODE_MAX_OUTPUT_TOKENS=4096          # REQUIRED — see Gotchas

# MCP server still on 127.0.0.1:8000 from Phase 1; resolver tool call must fire:
CLAUDE_CONFIG_DIR=$HOME/.claude-work \
  claude -p "Use the astro-archives MCP tools to resolve M51. Call the tool; do not guess." \
  --dangerously-skip-permissions
```

> **VALIDATED 2026-06-29.** This exact path returned M51 = **RA 202.469575 /
> Dec 47.1952583 (ICRS)** — driven by the local Qwen2.5-7B on vLLM, via the no-proxy
> Anthropic endpoint, via the Claude Code persona, calling `vo_target_resolve`. The
> 6-decimal precision confirms a real tool call (no 7B knows that from memory). The
> `⚠ claude.ai connectors are disabled …` line is benign — it just means Claude Code
> is using the env auth/base-URL (i.e. routing to vLLM), which is the goal.

**Success =** real M51 coords (RA ≈ 202.47 / Dec ≈ +47.20) **and** a `CallToolRequest`
in the MCP log — now driven by the local model. A 7B may call tools unreliably; that's
expected — this step proves the *plumbing*, not answer quality. Tool-use quality is the
model question, handled in Step 4.

### Gotchas (both hit and resolved 2026-06-29)

1. **`max_completion_tokens` > `max_model_len` → HTTP 500.** Claude Code requests up to
   `32000` output tokens by default; vLLM rejects an output budget larger than its whole
   window. Fix from both ends: run vLLM at the model's full `--max-model-len` (32768 for
   the 7B) **and** cap Claude Code with `CLAUDE_CODE_MAX_OUTPUT_TOKENS`.
2. **Claude Code's input floor is ~24.5K tokens** (its system prompt + the 12 `vo_*`
   tool schemas). On the 7B's 32K window that leaves little room: `24577 + 8192 > 32768`
   failed; `CLAUDE_CODE_MAX_OUTPUT_TOKENS=4096` (→ 28,673 total) works. **Implication for
   Step 4:** give the production model a much larger window (Qwen3 / 72B-class do 128K+)
   so the agent loop has real headroom as tool results accumulate over turns.

## Step 4 — scale to a production-grade model

Same launch, bigger model, tensor-parallel across all 4 GPUs. Per research §3, the
lowest-yak-shaving proven-on-Blackwell pick is **Qwen3-235B-A22B**; a **~70B-class**
model (e.g. Qwen2.5-72B-Instruct) is the better multi-user bet because it leaves far
more KV-cache headroom (research §5). Mind the Qwen3 thinking/tool-loss footgun (§4).

```bash
# Qwen3-235B-A22B (MoE), tensor-parallel 4, thinking DISABLED to avoid the
# qwen3_coder + reasoning-parser tool-loss bug (research §4, vLLM #39056):
docker run -d --name vllm --gpus all --ipc=host \
  -v "$MODELS":/root/.cache/huggingface \
  -p 127.0.0.1:8001:8000 \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen3-235B-A22B \
  --tensor-parallel-size 4 \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder \
  --served-model-name local-claude \
  --kv-cache-dtype fp8 --enable-prefix-caching \
  --gpu-memory-utilization 0.9 --max-model-len 32768
```

Then re-point Step 3's env at `--served-model-name local-claude` and re-validate.
**Before trusting it, confirm tool calls actually land** (the silent-drop failure
mode, §4) — a passing M51 resolve is the check. For gp13's dozens of users, do a
real concurrency load test (§5): KV cache, not compute, is the limiter, and prefix
caching of the shared `vo_*` tool-schema prefix is the big lever.

## Wiring into gp13 later

This local backend is **orthogonal to the MCP integration** — the `vo_*` tools work
regardless of model. To use it from gp13's persona instead of hosted Claude, set the
same `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_DEFAULT_*` env in the
single-user spawn environment (the gp13 runbook's §4 "local model" credential
option), pointed at wherever vLLM is reachable from the user pods.

## Open items to record once run

- [ ] Exact working vLLM/torch/FlashInfer versions on sm_120 (if `:latest` fails).
- [ ] Whether `/v1/messages` is native or needs a shim.
- [ ] Tool-call reliability per model (7B vs 235B vs 70B).
- [ ] Concurrency numbers from a real load test at agentic context lengths.
