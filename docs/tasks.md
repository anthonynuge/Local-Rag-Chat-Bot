# Tasks

Build order is a **walking skeleton**: stand the service up first (boots, health
check, stubbed endpoint), then build the logic underneath it, test-first — never
write pipeline functions before there's a running app to hang them on. Backend
and frontend stay decoupled by [api-contract.md](api-contract.md). Each phase is
roughly one short-lived branch / PR.

Status: `[ ]` todo · `[x]` done · `[-]` deferred / won't do (add reason + when to revisit)

---

## Phase 0 — Foundation

- [x] Repo layout: `backend/` (uv project), `docs/`; `frontend/`, `scripts/` added when their phase lands
- [x] Root `.gitignore` (`.venv`, `__pycache__`, `backend/storage/`, node)
- [x] `docs/` — spec, architecture, api-contract, tasks, corpus-generation-prompt
- [x] `CLAUDE.md` + `AGENTS.md` — tool alignment, pointer to `docs/`
- [x] `backend/rag/config.py` — all knobs, env-overridable → [architecture.md#config](architecture.md#config)
- [x] `backend/pyproject.toml` deps pinned (`uv add fastapi uvicorn ollama numpy tiktoken`) + pytest config

## Phase 1 — Walking skeleton _(first thing that runs)_

Proves the service boots before any logic exists; every later phase lands on
rails that already serve traffic.

- [x] `main.py`: FastAPI boots under uvicorn; `GET /api/health` returns 200
- [x] Stub `POST /api/chat`: streams a canned SSE sequence per the contract
      (token → citations → done) — frontend can integrate from day one
- [x] CORS for the frontend origin
- [-] `scripts/dev.ps1`: deferred — one `uvicorn` command is enough until the frontend exists; revisit in Phase 8
- [x] Test: health returns 200; stub emits contract-shaped events

## Phase 2 — Sample corpus

Real data before the pipeline, so chunk/retrieve/budget test against it.

- [x] Generate the sample wiki → `backend/data/sample/` (mixed `.md`/`.txt`, varying length) → [corpus-generation-prompt.md](corpus-generation-prompt.md)
- [x] Exclude some topics on purpose → drives the refusal test

## Phase 3 — LLM seam → [architecture.md#llm-seam](architecture.md#llm-seam)

- [x] `rag/llm.py`: `chat()` + `embed()` wrappers, round-trip verified
- [x] Guardrail: only this file imports the Ollama client
- [x] Wire `GET /api/health` to report Ollama reachability

## Phase 4 — Ingestion → [architecture.md#ingestion](architecture.md#ingestion)

- [x] `rag/chunk.py`: heading-aware split + overlap, tests green
- [x] `rag/store.py`: save/load index + chunk metadata; round-trip test
- [x] `rag/ingest.py`: CLI, prints file/chunk/token counts; run live once, sanity-check numbers

## Phase 5 — Retrieval + budget **[CORE]** → [architecture.md#budget](architecture.md#budget)

- [x] `rag/store.py`: cosine `top_k`
- [x] `rag/budget.py`: `pack()` greedy packer + budget report
- [x] Tests: never exceed `input_budget`, keep system+question, drop oldest history, chunk/`top_k` correctness

## Phase 6 — Real chat endpoint → [api-contract.md](api-contract.md)

Swap the Phase 1 stub for the live pipeline; the SSE shape doesn't change.

- [x] `POST /api/chat`: retrieve → pack → `llm.chat()` → stream token/citations/done
- [x] `event: error` on failure; 400 on empty/oversized question
- [x] Tests: event shape/order + 400 path (Ollama stubbed via the seam)

## Phase 7 — Verify → [architecture.md#calibration](architecture.md#calibration)

- [x] `scripts/smoke.py`: ingest → chat → assert correct citation + under budget
- [x] Token calibration: estimate vs `prompt_eval_count` within margin (+3.1% vs 10%); CPU-only pass identical

## Frontend

Can start any time after Phase 1 — the stub endpoint serves the contract.

### Phase 8 — Setup

- [x] `docs/design.md` (color tokens, typography, component inventory)
- [x] Vite + React + TS, Tailwind v4, tokens into `src/index.css` (shadcn
      skipped — native elements cover a 5-component UI; revisit if a dialog/
      dropdown-class widget ever lands)

### Phase 9 — Chat shell → [api-contract.md](api-contract.md)

- [ ] `Composer`, `MessageList`, `MessageBubble`
- [ ] `src/api.ts`: SSE client per the contract, developed against the stub

### Phase 10 — Streaming + states

- [ ] Live token append + typing indicator until `done`
- [ ] `CitationList`, loading/disabled/error states, `HealthDot` from `/api/health`

## Phase 11 — Release

- [ ] `README.md` demo script verified end-to-end
- [ ] Final calibration pass, cleanup / lint

---

**Acceptance traceability** (criteria in [spec.md](spec.md)):
A1 → P2+P4 · A2/A3 → P2+P6 · A4/A6 → P5 · A5 → P7 · A7 → P3

**Why skeleton-first:** the API skeleton is Phase 1, before any RAG logic.
Standing up a boots-and-serves service first proves runnability immediately,
gives the frontend a live (stubbed) endpoint from day one instead of a paper
contract, and makes Phase 6 "swap the stub's insides" rather than "introduce
HTTP." The logic phases (corpus → seam → ingestion → retrieval/budget) run
risk-first — the 6K budget math is the hard part, built test-first.
