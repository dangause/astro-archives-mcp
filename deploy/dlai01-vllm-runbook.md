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

The 16 GB `/var/lib/docker` cannot hold the vLLM image (~20 GB extracted — a pull
fails with `no space left on device`), and the 7 TB NVMe (`/scratch`, `/mlhome`) is
root-owned. Need:

1. **Docker storage on the NVMe** — relocate docker `data-root` to `/scratch/docker`
   (or grow the `noirlab-docker` LV to ~250 GB). Unblocks pulling the vLLM image.
2. **A writable weights dir** — e.g. `/scratch/dgause` owned by `dgause`, a few
   hundred GB, for the HF model cache.

Until (1) lands, even the 7B PoC can't pull the image. (The 7B *weights* fit in
`/home`, but the *image* does not fit the docker fs.)

## Step 1 — bring vLLM up on a small model (prove the plumbing)

The two real risks are independent of model size: **does vLLM run on sm_120 at
all**, and **does the Anthropic-API path carry tool calls**. Shake those out on a
7B that downloads in minutes, *then* scale.

```bash
MODELS=/scratch/dgause/hf            # the writable NVMe dir; falls back to $HOME/hf-cache
mkdir -p "$MODELS"
docker run -d --name vllm --gpus all --ipc=host \
  -v "$MODELS":/root/.cache/huggingface \
  -p 127.0.0.1:8001:8000 \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen2.5-7B-Instruct \
  --enable-auto-tool-choice --tool-call-parser hermes \
  --max-model-len 16384
docker logs -f vllm        # Ctrl-C after "Application startup complete"
```

Single 7B on one GPU — no tensor-parallel needed yet. `hermes` is the correct
tool-call parser for the Qwen2.5 family. No reasoning/thinking flags here, so the
Qwen3 `<think>` tool-loss footgun (research §4) doesn't apply.

> **If the load fails with `sm_120` / `no kernel image`:** the prebuilt image's CUDA
> doesn't cover this Blackwell. Switch to a Blackwell-validated vLLM (research §2:
> recent/nightly vLLM + `torch …+cu130` + matched FlashInfer/Triton, per
> blackwell-llm-toolkit). Capture the exact working version pins here when found.

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

# MCP server still on 127.0.0.1:8000 from Phase 1; resolver tool call must fire:
claude -p "Use the astro-archives MCP tools to resolve M51. Call the tool; do not guess." \
  --dangerously-skip-permissions
```

**Success =** real M51 coords (RA ≈ 202.47 / Dec ≈ +47.20) **and** a `CallToolRequest`
in the MCP log — now driven by the local model. That proves the full local-model
chain end to end. A 7B may call tools unreliably; that's expected — the goal of this
step is the *plumbing*, not answer quality. Tool-use quality is the model question,
handled in Step 4.

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
