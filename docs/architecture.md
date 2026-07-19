# Architecture — Backend / System Design

How the system is built. Requirements in [spec.md](spec.md); the interface in
[api-contract.md](api-contract.md). Section anchors here are referenced by
[tasks.md](tasks.md).

## Overview

```
 ingest (offline)                 chat (runtime)
 ───────────────                  ─────────────
 data/<dataset>/*.md,txt          React SPA (Vite)  ── chat input, SSE reader,
   │  rag/chunk.py                    │  POST /api/chat      renders [n] citations
   │  (heading-aware, ~400 tok        │  SSE (token deltas → citations → done)
   │   windows, ~50 overlap)          ▼
   │  llm.embed (nomic-embed-text) FastAPI  /api/chat, /api/health
   ▼                                  │  rag/budget.py  ← THE CORE
 storage/index.npz  (vectors)        │    pack(system, context, history, reserve)
 storage/chunks.jsonl (text+meta)    │  rag/store.py  → top_k(query_vec)
        └──────── loaded at startup ─┤  llm.chat(stream, num_ctx=6144)
                                      ▼
                                   Ollama (llama3.2:3b, local)
```

## Repo layout (planned)

```
Local-Rag-Chat-Bot/
├── docs/                  # spec, architecture, api-contract, tasks (+ design.md in Phase 8)
├── backend/
│   ├── main.py            # FastAPI: POST /api/chat (SSE), GET /api/health
│   ├── pyproject.toml     # uv-managed: deps (pinned) + pytest/lint config
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── config.py      # all knobs, env-overridable
│   │   ├── llm.py         # the only module that talks to Ollama (chat + embed)
│   │   ├── chunk.py       # heading-aware splitting + overlap
│   │   ├── store.py       # save/load index, cosine top_k
│   │   ├── budget.py      # pack() — the 6K budget core
│   │   └── ingest.py      # CLI: data/<dataset> → storage/ index
│   ├── data/              # source .md/.txt, one subfolder per dataset (sample/, demo/)
│   ├── storage/           # index.npz + chunks.jsonl (generated, gitignored)
│   └── tests/             # deterministic unit tests (no Ollama)
├── frontend/              # Vite + React + TS chat UI
│   └── src/               # api.ts (SSE client), components, index.css
├── scripts/
│   ├── dev.ps1            # start backend + frontend (two terminals)
│   └── smoke.py           # live end-to-end check against a running stack
└── README.md
```

Retrieval (embed query → `store.top_k`) is a few lines and lives in `store.py`
rather than its own module — a file per function call is structure without
content.

## <a id="llm-seam"></a>LLM seam (`rag/llm.py`)

**The only module that imports the Ollama client.** Wraps two operations:

- `chat(messages, stream=True, options={num_ctx, num_predict, temperature})` →
  yields token deltas + a final response carrying `prompt_eval_count`.
- `embed(texts) -> np.ndarray` via `nomic-embed-text`.

Retrieval and budgeting never touch Ollama directly. Swapping in an NPU runtime
or another local server means rewriting this one file (Goal G3). The guarantee
is the "only importer" rule, not the folder — enforced by a test/grep that no
other module imports the client.

## <a id="ingestion"></a>Ingestion (`rag/ingest.py`, `rag/chunk.py`, `rag/store.py`)

- **Chunk** (`chunk.py`): split each file on markdown headings first (keep
  sections whole), then window long sections into ~`CHUNK_TOKENS` (400) pieces
  with ~`CHUNK_OVERLAP` (50) overlap. `.txt` with no headings → windowed
  directly. Each `Chunk` carries `{source, heading, text, idx}`.
- **Embed**: `llm.embed()` in batches → L2-normalized float32 vectors.
- **Persist** (`store.py`): `storage/index.npz` (vector matrix) +
  `storage/chunks.jsonl` (metadata + text, row-aligned to the matrix). Loaded
  once at server startup.
- **CLI**: `python -m rag.ingest ./data/sample` prints file/chunk/token counts.

## Retrieval (`rag/store.py`)

Embed the query, cosine similarity (normalized dot product) against the matrix,
take `TOP_K` (6). Ranked chunks go to the budgeter, which packs as many as fit
the context slice. Deliberately skipped: vector DB and reranker — brute-force
cosine over a handful of files is instant. Revisit if the corpus grows ~100x.

## <a id="budget"></a>The core: 6K budget management (`rag/budget.py`)

Total window `NUM_CTX = 6144`. Fixed allocation, then greedy packing.

| Slice             | Budget (tok)                 | Rule                                                                                                                                                     |
| ----------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Answer reserve    | ~1024                        | passed to Ollama as `num_predict`; never used by input                                                                                                   |
| Safety margin     | `SAFETY_FRAC` (10%) of input | covers chat-template overhead + tokenizer drift; proportional because drift grows with prompt length                                                     |
| System prompt     | ~250                         | always kept (grounding + citation format)                                                                                                                |
| Retrieved context | up to ~3000                  | top-ranked chunks packed until slice full                                                                                                                |
| Chat history      | remainder (~1300)            | most-recent turns kept, oldest dropped                                                                                                                   |

`input_budget = (NUM_CTX - answer_reserve) × (1 - SAFETY_FRAC)` (~4608 tok).

**Packing priority** (never overflow `input_budget`):

1. System prompt — always included.
2. Current user question — always included. If system + question alone exceed
   `input_budget`, reject with **400** before streaming (see
   [api-contract.md](api-contract.md)) — never silently truncate the question.
3. Retrieved context — add chunks in rank order until the context slice cap is
   hit; drop lowest-ranked overflow.
4. Chat history — fill the remainder with most-recent turn pairs; drop oldest
   first (sliding window).

`pack()` returns `(messages, citations, budget_report)`. The `budget_report`
(per-slice token counts) is surfaced in the `done` SSE event and `/api/health`,
so the budget is observable, not a black box.

### <a id="calibration"></a>Token counting & calibration

Ollama exposes no pre-send tokenizer, so we **estimate** with `tiktoken`
(cl100k) and hold back the proportional safety margin (cl100k and the llama
tokenizer disagree by a length-proportional amount), then **calibrate against
reality**: every
response returns `prompt_eval_count` (the tokens the model actually saw). We log
estimate-vs-actual drift and assert `prompt_eval_count + answer_reserve ≤
num_ctx`. Also pass `options.num_ctx = 6144` as a hard backstop against silent
truncation. An approximate tokenizer plus a margin is enough here; if measured
drift ever exceeds the margin, the fix is swapping tiktoken for the model's
real tokenizer.

## <a id="hardware"></a>Hardware (CPU / GPU)

The CPU/GPU question is answered by **model choice, not code**: `llama3.2:3b`
quantized is small enough that CPU-only inference runs at usable tok/s in a few
GB of RAM — the floor is any reviewer laptop. Ollama auto-detects a GPU and
offloads layers when present, so GPU is transparent acceleration, not a
requirement; nothing in this app has a hardware mode. Two consequences:

- Outputs can differ slightly between backends (float non-associativity flips
  near-tied tokens), so no test asserts on answer wording — only structure.
- Generation is several times slower on CPU, so clients rely on streaming
  (tokens keep the connection alive) rather than tight timeouts. Phase 7 runs the
  smoke script once CPU-only (`OLLAMA_NO_GPU=1`) to verify this holds, and
  reports measured tok/s from `eval_count / eval_duration`.

## Grounding & citations (`main.py`)

System prompt: _"Answer ONLY using the numbered context below. Cite sources
inline as [1], [2]. If the answer is not in the context, say you don't have that
information — do not use outside knowledge."_ Context is rendered as:

```
[1] (onboarding.md — "PTO Policy") <chunk text>
[2] (deploy-runbook.md — "Rollback") <chunk text>
```

`[n]` maps to the `citations` SSE event.

## Conversation state

Stateless server: the client sends history each turn (see
[api-contract.md](api-contract.md)); the budgeter applies the sliding window.
Cross-restart persistence is out of scope for the demo.

## Config (`rag/config.py`, env-overridable)

Every knob lives here, each overridable by an env var of the same name:

```python
MODEL = "llama3.2:3b"             # chat model — 3B quantized runs at usable speed on CPU
EMBED_MODEL = "nomic-embed-text"  # local embedding model
OLLAMA_HOST = "http://localhost:11434"

NUM_CTX = 6144         # the hard ceiling: model context window
ANSWER_RESERVE = 1024  # held back for the model's reply (passed as num_predict)
SAFETY_FRAC = 0.10     # input fraction held back for tokenizer drift + template overhead
CONTEXT_BUDGET = 3000  # max tokens of retrieved chunks in the prompt
TOP_K = 6              # chunks retrieved per query (6 × 400 fits CONTEXT_BUDGET)

CHUNK_TOKENS = 400     # target chunk size at ingest
CHUNK_OVERLAP = 50     # overlap between adjacent chunks

DATA_DIR = "./data/sample"  # ingest source (CLI arg overrides — e.g. the demo-day dataset)
STORAGE_DIR = "./storage"   # index.npz + chunks.jsonl

# Derived — the input side of the window:
INPUT_BUDGET = int((NUM_CTX - ANSWER_RESERVE) * (1 - SAFETY_FRAC))  # ≈ 4608
```

**Dataset selection** is already free: `ingest` takes the source folder as a CLI
arg that overrides `DATA_DIR` (`python -m rag.ingest ./data/demo`), and
both dirs are env-overridable. No dataset registry needed. Note: a second
dataset overwrites the first's index — if side-by-side datasets are ever
needed, derive `STORAGE_DIR` from the dataset name. Not needed for the demo.

## Testing (see [tasks.md](tasks.md) P4/P5/P6)

- **Deterministic unit tests (CI, no Ollama):** budget invariants, chunking,
  cosine `top_k` ordering, pack-time estimate `≤ input_budget`.
- **Live smoke script (`scripts/smoke.py`, on demand):** grounded Q cites the
  expected file; out-of-corpus Q refuses with no citations; empirical
  `prompt_eval_count` under budget and within margin.

## Failure modes

| Failure                       | Handling                                                       |
| ----------------------------- | -------------------------------------------------------------- |
| Ollama down / model missing   | `/api/health` fails fast with a reason                         |
| Question too large for budget | `POST /api/chat` → **400** before any streaming                |
| Generation error/timeout      | `/api/chat` emits `event: error`; UI renders it                |
| Empty output                  | smoke test asserts non-empty stream ending in `done`           |
| Ungrounded answer             | grounding via system prompt; tested by citation/refusal checks |

## Future directions (out of scope, with triggers)

Ideas worth exploring, each with the condition that would justify it — none pay
off at demo scale:

- **Reranker (cross-encoder).** Add when retrieval quality is the bottleneck:
  top-k returns topically-close-but-wrong chunks. At a handful of files, cosine
  rank is already near-perfect. _(trigger now met — see tasks.md Phase 10.5;
  deferred pending model-swap + chunking results)_
- **Hybrid retrieval (BM25 + vectors).** _Implemented 2026-07-18_ — the
  trigger fired (rare-exact-token queries like "fall rut" were the remaining
  retrieval misses). RRF fusion in `store.top_k`; BM25 stats rebuilt from
  chunk text at load, ingest untouched. See `evals/EXPERIMENTS.md`.
- **Vector DB (e.g. sqlite-vec, LanceDB).** At ~100x corpus size, when
  brute-force cosine or index load time becomes measurable.
- **Real model tokenizer.** Swap tiktoken for the llama tokenizer if measured
  drift exceeds `SAFETY_FRAC` — the calibration in Phase 7 decides this.
- **GraphRAG / multi-hop.** Only if questions require joining facts across
  documents ("who approves X's budget?" spanning org-chart + policy docs).
  Heavy ingest cost; lookup-style Q&A never needs it.
- **Conversation persistence.** Add a store when sessions must survive
  restarts; the stateless API already leaves room (client sends history).
