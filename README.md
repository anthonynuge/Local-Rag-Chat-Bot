<div align="center">

# Local RAG Chat

### Grounded, cited answers from your own documents — fully local, inside a 6K-token context window

<a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" alt="License"></a>
<img src="https://img.shields.io/badge/Python-3.14-3776ab?style=flat-square" alt="Python">
<img src="https://img.shields.io/badge/Ollama-local-black?style=flat-square" alt="Ollama">

<a href="docs/spec.md"><b>Spec</b></a> •
<a href="docs/architecture.md"><b>Architecture</b></a> •
<a href="docs/results.md"><b>Results</b></a> •
<a href="evals/EXPERIMENTS.md"><b>Experiment Log</b></a>

</div>

<!-- TODO: add docs/images/demo.gif (screen capture of a chat with citations, ~1200px wide) then uncomment
<p align="center">
  <img src="docs/images/demo.gif" width="650" alt="Local RAG Chat demo" />
</p>
-->

---

<details>
<summary>Table of Contents</summary>

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Evaluation](#evaluation)
- [Roadmap](#roadmap)
- [License](#license)

</details>

## Overview

A RAG chat application where everything runs on your machine: a local LLM
(via Ollama) answers questions about a folder of `.md`/`.txt` documents,
cites the source file for every claim, and refuses when the answer isn't in
the corpus. The defining constraint is a **hard 6,144-token context
window** — system prompt, retrieved chunks, conversation history, and room
for the answer all have to coexist in it, so deterministic token budgeting
is the core of the design, not an afterthought.

## Features

- **6K token budget packer** - every prompt is assembled by a greedy packer that reserves answer space, drops oldest history first, and reports per-slice token counts; the model-measured prompt size stays within 3.1% of the estimate
- **Hybrid retrieval** - cosine similarity over local embeddings fused with BM25 via reciprocal-rank fusion, so rare exact tokens ("Shoulder Camp") rank as well as semantic matches
- **Heading-aware chunking** - Markdown chunks carry their full heading breadcrumb ("Title > Section > Sub"); `.txt` files split on paragraph boundaries so FAQ entries stay whole
- **Grounded answers with citations** - inline `[n]` markers resolve to source files in the UI; out-of-corpus questions (including famous facts the model knows) get an explicit refusal with no citation
- **Follow-up condensing** - short mid-conversation follow-ups ("are you sure?") are rewritten into standalone questions before retrieval, so they fetch the right chunks
- **Streaming chat UI** - React frontend with server-sent events: live token stream, typing indicator, citation list, backend health dot
- **Measured, not guessed** - a committed eval set (59 requests across factual, cross-source, trick, refusal, and multi-turn buckets), an LLM-as-judge grader, and an experiment log where every change ships with before/after numbers

## Tech Stack

- **Backend:** Python 3.14, FastAPI, uv; numpy (vector search), tiktoken (token counting)
- **Inference:** Ollama — `qwen2.5:7b` chat (default), `nomic-embed-text` embeddings, `llama3.2:3b` CPU-first fallback
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS v4
- **Storage:** flat files — `index.npz` + `chunks.jsonl` (no vector DB; a handful of documents doesn't need one)

## Quick Start

**Prerequisites:** [Ollama](https://ollama.com) running, [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
# 1. Models (one-time download; runtime is fully local)
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

# 2. Install
cd backend && uv sync && cd ..
cd frontend && npm install && cd ..

# 3. Build the index from the sample corpus — from backend/
cd backend && uv run python -m rag.ingest ./data/sample

# 4. Run both servers (API :8000, UI :5173) — from the repo root
./scripts/dev.sh        # macOS / Linux / Git Bash
.\scripts\dev.ps1       # Windows PowerShell
```

Then open http://localhost:5173 and ask a question about the sample docs.

<details>
<summary>Run the servers manually instead</summary>

```bash
# Terminal 1 — from backend/
uv run uvicorn main:app --reload   # API on :8000

# Terminal 2 — from frontend/
npm run dev                        # UI on :5173
```

</details>

> [!NOTE]
> Ollama unloads idle models after ~5 minutes, so the first question after a
> break pays a few seconds of model-reload time. That's normal.

> [!TIP]
> No GPU? Everything still works — Ollama falls back to CPU automatically.
> For faster CPU answers, use the smaller model: `MODEL=llama3.2:3b`.

## Usage

All scripts run from `backend/`:

```bash
# Swap in your own documents (any folder of .md/.txt files)
uv run python -m rag.ingest ./data/your-folder

# Deterministic tests — no Ollama needed
uv run pytest tests

# Live end-to-end check: ingest → ask → assert citation + budget
uv run python ../scripts/smoke.py

# Quality rates vs the committed baseline (citation / refusal / multi-turn)
uv run python ../scripts/eval.py ./data/sample-v3

# Grade the latest eval run's answers with a local judge model
uv run python ../scripts/judge.py

# Interactive debug REPL — shows retrieved chunks, the packed prompt, metrics
uv run python ../scripts/chat.py
```

## Configuration

Every knob lives in [`backend/rag/config.py`](backend/rag/config.py) and is
overridable by environment variable. The ones you're most likely to touch:

| Variable | Default | Description |
|---|---|---|
| `MODEL` | `qwen2.5:7b` | Chat model; `llama3.2:3b` is the tested CPU-first fallback |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model for ingest and queries |
| `NUM_CTX` | `6144` | The hard context ceiling passed to Ollama |
| `CONTEXT_BUDGET` | `3000` | Max tokens of retrieved chunks per prompt |
| `TOP_K` | `6` | Chunks retrieved per query |
| `DATA_DIR` | `backend/data/sample` | Default ingest source |
| `NUM_GPU` | unset | Set `0` to force generation onto CPU (calibration) |

Full list and the budget math: [architecture.md — config](docs/architecture.md#config).

## Architecture

Two processes: a FastAPI backend (chunking, retrieval, budget packing, SSE
streaming) and Ollama (the only thing that touches a model). Per request:
embed the question → hybrid top-k over the local index → pack system prompt,
chunks, and history into the 6K budget → stream the answer with citations.
The Ollama client is isolated behind one module (`rag/llm.py`) so the
inference runtime is swappable without touching retrieval or budgeting.

Details: [architecture.md](docs/architecture.md) ·
[api-contract.md](docs/api-contract.md) · [spec.md](docs/spec.md)

```
backend/
├── main.py          # FastAPI app: /api/chat (SSE), /api/health
├── rag/             # config, chunk, store, budget, llm, ingest
├── data/<dataset>/  # source documents + eval.json question sets
└── storage/         # generated index (npz + jsonl)
frontend/            # Vite + React chat UI
scripts/             # smoke, eval, judge, chat REPL
evals/               # EXPERIMENTS.md log + raw run JSONs
```

## Evaluation

The eval harness runs every question through the live pipeline and scores
retrieval, citations, refusals, and multi-turn sequences against a committed
baseline. A separate judge model (`JUDGE_MODEL`, default `gemma4:latest`)
grades answer text against reference answers — the judge is a development
and testing tool only: it is never part of the serving pipeline, isn't
needed to run the app, and its grades are LLM output, so they're indicative
rather than deterministic (the deterministic checks live in `pytest`). One measured day took citation accuracy 69% → 94% and judged
correctness 72% → 83% — the trajectory, and what each change bought, is in
[docs/results.md](docs/results.md). Every experiment since (including the
ones that lost and got reverted) is written up in
[evals/EXPERIMENTS.md](evals/EXPERIMENTS.md); currently-open issues are
tracked at the bottom of [docs/tasks.md](docs/tasks.md).

## Roadmap

- [ ] Soften the refusal rule so stated negatives ("there is no WiFi") aren't over-refused — regression documented in the experiment log
- [ ] Draft→verify second pass for questions that apply a rule to a specific date ("open on a January Tuesday?")
- [ ] Grow the eval set before further retrieval tuning — knob changes currently churn more questions than they fix

## License

MIT — see [LICENSE](LICENSE).
