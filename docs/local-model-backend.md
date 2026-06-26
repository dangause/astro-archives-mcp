# Local-model backend for the Jupyter AI persona (dlai01)

Status: **research draft — validate on the box before relying on it.** This explores
backing the Jupyter AI "Claude" persona with a self-hosted model on the GPU box
`dlai01` (4× NVIDIA RTX PRO 6000 Blackwell, ~96 GB each ≈ 384 GB, sm_120, CUDA 13.x)
instead of hosted Claude. It's the §4 "local model" option in `deploy/gp12-runbook.md`.
Goal framing: **PoC feasibility, optimized for agentic MCP tool-calling reliability**
(not throughput).

> **Confidence note.** Backed by a deep-research pass (25 sources). Across two
> verification runs, **13 claims cleared full multi-vote adversarial verification**; the
> rest abstained when the runs hit session limits (they are *unverified*, not refuted).
> Items are tagged **[verified]** (multi-vote 3-0) or **[lead]** (single-source,
> plausible, unverified). Re-verify [lead] items — especially exact version pins and 2026
> model names — on dlai01. Verification flagged two corrections vs. an earlier draft:
> llama.cpp is **not** a clean fallback here (§2), and the recommended Qwen3 parser combo
> has a **verified tool-loss footgun** (§4).

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
  (musistudio, local gateway at `http://127.0.0.1:3456`) or a **LiteLLM** proxy. LiteLLM
  is verified to bridge Claude Code → arbitrary backends: set `ANTHROPIC_BASE_URL` to the
  proxy and `ANTHROPIC_AUTH_TOKEN` to the LiteLLM master key, with models declared in a
  `config.yaml` `model_list`.

## 2. Serving on Blackwell (sm_120, CUDA 13) — the riskiest part

- **[verified] All three engines (vLLM, TensorRT-LLM, llama.cpp) have been empirically
  validated on the RTX PRO 6000 96 GB (sm_120) Blackwell GPU** (blackwell-llm-toolkit,
  as of 2026-05-11). So serving on this hardware is a solved problem *with the right
  recipe* — but the recipe is exact and version-sensitive.
- **[verified] llama.cpp is NOT a drop-in fallback here.** Its CUDA build **fails** on
  sm_120 with CUDA Toolkit 13.1.115 — MXFP4 PTX instructions (`mma with block scale`,
  `.kind::mxf4`, `.block_scale`) are unsupported on `.target sm_120`, and the issue was
  **open/unresolved as of Feb 2026** (llama.cpp #19662). A working build exists (per the
  toolkit above) but you must use a validated recipe / avoid the MXFP4 path — do not
  assume `make`-and-go.
- **[lead] vLLM install is finicky but documented.** Reported working stacks pair a
  recent/nightly vLLM with `torch …+cu130` and matched FlashInfer/Triton (e.g. PyTorch
  `2.10.0+cu130`, vLLM ~`0.17.x`, FlashInfer `0.6.4`, Triton `3.6.0`), and need the
  **full system CUDA 13 toolkit** (not just PyPI wheel fragments) for FlashInfer JIT.
- **Action:** start from the blackwell-llm-toolkit recipe rather than a fresh install;
  budget real time here; pin and record the exact working versions.

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
- **[verified] Reasoning-parser eats the tool call (the Qwen3 footgun).** For Qwen3-MoE
  models, vLLM's reasoning parser pulls everything before `</think>` into the *reasoning*
  field, and the tool-call parser only inspects *content* — so a `<tool_call>` block
  emitted inside `<think>` **never reaches the tool parser and the call is silently lost**
  (vLLM #39056). This happens **specifically with the `qwen3_reasoning_parser` +
  `qwen3_coder` combo** — i.e. exactly the flags in the recommended stack below.
  Mitigate: **disable thinking for the PoC** (sidesteps it entirely), or track vLLM #39056
  for the fix; verify tool calls actually land before trusting the setup.
- **[lead] Thinking-token budget exhaustion.** Reasoning models can also spend the whole
  `max_tokens` inside `<think>` → `content:null` / `finish_reason:length`, a silent
  HTTP-200 that stalls the agent loop. Mitigate: generous `max_tokens`, or thinking off.
- **[lead] Streaming tool-call bugs** in some vLLM versions (raw XML in `content` instead
  of structured `tool_calls`, `finish_reason: stop`). Test your version; non-streaming is
  safer to start.
- **[lead] `tool_choice:auto` may not guarantee schema-valid JSON** (a verifier pushed
  back on the strict-mode specifics, so treat as unconfirmed). Regardless, expect
  occasional malformed args; the agent loop should tolerate/retry.

## Recommended PoC stack

| Layer | Choice | Key flags / env |
|---|---|---|
| Serving | **vLLM** from a validated Blackwell recipe (blackwell-llm-toolkit), tensor-parallel. llama.cpp only via a validated build (CUDA build breaks by default — §2) | `--tensor-parallel-size 4 --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3 --served-model-name local-claude` **+ disable thinking** (avoids the #39056 tool-loss footgun, §4) |
| Bridge | **vLLM native Anthropic endpoint** (no proxy); CCR/LiteLLM verified fallbacks | — |
| Model | **Qwen3-235B-A22B** (primary) / ~30B Qwen3 (fallback) / GLM-4.6 (if tool-use weak). `gpt-oss-120b` + `--tool-call-parser openai` is vLLM's own documented known-good combo | — |
| Harness | JupyterLab launch env (inherited by the persona) | `ANTHROPIC_BASE_URL=http://dlai01:8000` `ANTHROPIC_AUTH_TOKEN=dummy` `ANTHROPIC_DEFAULT_OPUS_MODEL=local-claude` (+ SONNET/HAIKU) |

**Top risks to watch:** (1) Blackwell+CUDA-13 install friction (start from a validated
recipe; llama.cpp's default CUDA build is broken on sm_120); (2) the `qwen3_coder` +
`qwen3` reasoning-parser tool-loss bug (disable thinking, verify calls land); (3)
thinking-token budget exhaustion stalling the agent loop; (4) version-specific streaming
tool-call bugs.

## Sources
vLLM Claude Code integration & tool-calling docs (primary); BFCL V4 leaderboard
(gorilla.cs.berkeley.edu); claude-code-router (github.com/musistudio); lastloop-ai
vllm-blackwell-guide; vLLM issues #37714 / #31871 / #32713; stevescargall.com thinking-mode
analysis; dev.to dcruver Claude-Code-via-vLLM-and-LiteLLM. Full list in the research run
output (`tasks/wqv4strey.output`).
