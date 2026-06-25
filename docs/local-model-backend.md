# Local-model backend for the Jupyter AI persona (dlai01)

Status: **research draft — validate on the box before relying on it.** This explores
backing the Jupyter AI "Claude" persona with a self-hosted model on the GPU box
`dlai01` (4× NVIDIA RTX PRO 6000 Blackwell, ~96 GB each ≈ 384 GB, sm_120, CUDA 13.x)
instead of hosted Claude. It's the §4 "local model" option in `deploy/gp12-runbook.md`.
Goal framing: **PoC feasibility, optimized for agentic MCP tool-calling reliability**
(not throughput).

> **Confidence note.** A deep-research pass (24 sources) backs this, but only ~8 claims
> cleared full adversarial verification (the run hit a session limit). Items below are
> tagged **[verified]** (multi-vote) or **[lead]** (single-source, plausible, unverified).
> Re-verify [lead] items — especially exact versions and 2026 model names — on dlai01.

## Why this is even tractable: the persona inherits env

The persona launches `claude-agent-acp`, which wraps Claude Code, which reads
`ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` from its environment. Same inheritance
trick we used for `CLAUDE_CONFIG_DIR` (work account): set these in the JupyterLab
launch env and the persona talks to the local model. The MCP path is unchanged — the
`vo_*` tools work identically regardless of which model backs the persona.

## 1. Bridge: prefer vLLM's native Anthropic endpoint

- **[verified] vLLM natively implements the Anthropic Messages API** (`/v1/messages`),
  the same API Claude Code speaks — so Claude Code points *straight at vLLM*, with **no
  separate translation proxy**. This is the cleanest path and removes the
  Anthropic↔OpenAI translation layer that is the main source of tool-call breakage.
  Source: vLLM docs, Claude Code integration.
- **[verified] Env to point Claude Code at vLLM:** `ANTHROPIC_BASE_URL=http://dlai01:8000`,
  `ANTHROPIC_AUTH_TOKEN=dummy` (any value), and map tiers with
  `ANTHROPIC_DEFAULT_OPUS_MODEL` / `_SONNET_MODEL` / `_HAIKU_MODEL` = your served model
  name.
- **[verified] Fallback bridges** if the native path misbehaves: `claude-code-router`
  (musistudio) or a **LiteLLM** proxy — both translate Anthropic Messages ⇄
  OpenAI-style backends. [lead] LiteLLM has been reported working end-to-end for Claude
  Code → vLLM tool-calling.

## 2. Serving on Blackwell (sm_120, CUDA 13) — the riskiest part

- **[lead] vLLM runs on RTX PRO 6000 Blackwell + CUDA 13, but the install is finicky.**
  Reported working stacks pair a recent/nightly vLLM with `torch …+cu130` and matched
  FlashInfer/Triton. One practitioner combo: PyTorch `2.10.0+cu130`, vLLM ~`0.17.x`,
  FlashInfer `0.6.4`, Triton `3.6.0`.
- **[lead] Install the full system CUDA 13 toolkit** (e.g. `cuda-nvcc-13`, `cuda-cccl-13`,
  `cuda-cudart-dev-13`), not just PyPI CUDA wheel fragments — FlashInfer JIT on sm_120
  needs the real toolkit.
- **[lead] llama.cpp is the lower-friction fallback** on this hardware if the vLLM dance
  stalls. Slower/less featureful for serving but easier to stand up.
- **Action:** budget real time for this step; it's the most likely thing to bite. Pin and
  record the exact working versions once found.

## 3. Model choice (tool-use reliability)

- **[verified] Judge models by BFCL V4** (holistic agentic tool-use), and/or Tau2-bench.
- **[lead] Open-weight tool-use leaders:** the **GLM family** tops agentic tool-use
  (GLM-4.5 ≈ 70.9% BFCL V4 open-weight lead; GLM-4.7/5.x very high on Tau2-Telecom).
  **Qwen3** was the family specifically validated on *this exact hardware* with a known
  vLLM parser (`qwen3_coder`).
- **[lead] VRAM fit:** Qwen3-235B-A22B (235B total / **22B active** MoE) fits the 384 GB
  box comfortably; a ~30B Qwen3 fits in 1 GPU for a simpler first bring-up.

**PoC recommendation (pragmatism over leaderboard points):**
- **Primary:** Qwen3-235B-A22B on vLLM — best balance of strong tool-use and a
  *known-good Blackwell + parser* path.
- **Simpler fallback:** a ~30B Qwen3 (single-GPU) to get the end-to-end loop working first.
- **If Qwen tool-use disappoints:** try a **GLM-4.6**-class model (benchmark leader for
  agentic tool-calling).

## 4. Integration failure modes & mitigations

- **[verified] Parser/template mismatch** → tool calls silently dropped. Use the parser
  matched to the family: Qwen → `hermes`/`qwen3_coder`, DeepSeek-V3 → `deepseek_v3`,
  Llama 3.x → `llama3_json`, Mistral → `mistral`. Always pair with the matching chat
  template.
- **[lead] Thinking-token budget exhaustion (the big one).** Reasoning models can spend
  the whole `max_tokens` inside hidden `<think>` blocks → `content:null` /
  `finish_reason:length`, a silent HTTP-200 that stalls the agent loop. And tool-call XML
  emitted *inside* `<think>` is captured by the reasoning parser, not the tool-call parser
  → calls lost. Mitigate: matched `--reasoning-parser`, generous `max_tokens`, consider
  disabling thinking for the PoC.
- **[lead] Streaming tool-call bugs** in some vLLM versions (raw XML in `content` instead
  of structured `tool_calls`, `finish_reason: stop`). Test your version; non-streaming is
  safer to start.
- **[verified] `tool_choice:auto` doesn't guarantee schema-valid JSON** (only
  `required`/named use constrained decoding). Expect occasional malformed args; the agent
  loop should tolerate/retry.

## Recommended PoC stack

| Layer | Choice | Key flags / env |
|---|---|---|
| Serving | **vLLM** (recent/nightly, CUDA 13 build), tensor-parallel across GPUs; llama.cpp fallback | `--tensor-parallel-size 4 --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3 --served-model-name local-claude` |
| Bridge | **vLLM native Anthropic endpoint** (no proxy); CCR/LiteLLM fallback | — |
| Model | **Qwen3-235B-A22B** (primary) / ~30B Qwen3 (fallback) / GLM-4.6 (if tool-use weak) | — |
| Harness | JupyterLab launch env (inherited by the persona) | `ANTHROPIC_BASE_URL=http://dlai01:8000` `ANTHROPIC_AUTH_TOKEN=dummy` `ANTHROPIC_DEFAULT_OPUS_MODEL=local-claude` (+ SONNET/HAIKU) |

**Top risks to watch:** (1) Blackwell+CUDA-13 vLLM install friction; (2) thinking-token
budget exhaustion breaking the agent loop; (3) tool-parser/template mismatch dropping
calls; (4) version-specific streaming tool-call bugs.

## Sources
vLLM Claude Code integration & tool-calling docs (primary); BFCL V4 leaderboard
(gorilla.cs.berkeley.edu); claude-code-router (github.com/musistudio); lastloop-ai
vllm-blackwell-guide; vLLM issues #37714 / #31871 / #32713; stevescargall.com thinking-mode
analysis; dev.to dcruver Claude-Code-via-vLLM-and-LiteLLM. Full list in the research run
output (`tasks/wqv4strey.output`).
