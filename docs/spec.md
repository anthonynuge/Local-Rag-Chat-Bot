# Spec — Local RAG Chat

What this system does and the constraints it must respect. How it's built
lives in [architecture.md](architecture.md); the frontend↔backend interface is
[api-contract.md](api-contract.md). (A frontend `design.md` is added in Phase
8 — see [tasks.md](tasks.md).)

## Problem

A RAG-enabled AI chat application where the LLM runs **locally** and is limited
to a **6K context window**. The RAG pipeline ingests `.md`/`.txt` files and is
also **fully local**. The assistant answers questions grounded only in the
ingested documents, with citations, and refuses when the answer isn't present.

## Constraints (hard requirements)

| #   | Constraint                                                       | Source            |
| --- | ---------------------------------------------------------------- | ----------------- |
| C1  | LLM runs locally — no cloud LLM APIs at runtime                  | problem statement |
| C2  | Model context window is **6144 tokens**, a hard ceiling          | problem statement |
| C3  | RAG ingestion + storage + retrieval fully local (no cloud)       | clarification     |
| C4  | Ingests `.md` and `.txt` files                                   | problem statement |
| C5  | `ollama pull` at setup is acceptable; runtime execution is local | clarification     |
| C6  | Corpus is a **handful** of files                                 | clarification     |
| C7  | Sample knowledge base built for the demo                         | clarification     |

## Goals

- **G1 — Budget management (the core problem).** System prompt + retrieved
  context + conversation history + room for the answer all coexist within 6144
  tokens. Budgeting is deterministic and observable, never silent truncation.
- **G2 — Grounded answers with citations.** Answers come only from ingested
  docs; each cites its source. Out-of-corpus questions get an explicit "I don't
  have that information," not a hallucination.
- **G3 — Local, swappable inference on commodity hardware.** Ollama today,
  behind a single interface, so the model runtime can be replaced (e.g. an NPU)
  without touching retrieval or budgeting. Default is qwen2.5:7b;
  `MODEL=llama3.2:3b` is the CPU-first fallback. CPU-only is usable, and
  Ollama offloads to a GPU automatically when one is present — see
  [architecture.md#hardware](architecture.md#hardware).
- **G4 — Lightweight streaming UI.** One chat input, streamed response,
  rendered citations. Ingestion is a separate command run before startup, not an
  upload widget.

## Non-goals (explicitly out of scope)

- Vector database or reranker (a handful of files → brute-force cosine).
- Auth, multi-user, Docker, cloud deploy.
- Cross-restart conversation persistence.
- Document upload through the UI.

## Users & flow

1. Author/drop `.md`/`.txt` files into `backend/data/` (a subfolder per dataset,
   e.g. `data/sample/`).
2. Run the ingest command against that folder → builds a local vector index in
   `backend/storage/`.
3. Start backend + frontend → chat with grounded, cited answers.

## Sample knowledge base

**Domain-agnostic.** The demo ships one sample corpus, but nothing in the
pipeline is tied to a subject — the corpus is swappable and could be any domain
on any given day. The requirements, not a fixed domain:

- A **handful** of self-contained documents, mixing `.md` (headed sections) and
  `.txt` (plain text), of **varying length** (short → long).
- Invented / self-contained content so it sits **outside model training data** —
  retrieval, not recall, is what's exercised.
- Coverage chosen so some questions have clear **grounded** answers _and_ some
  fall **outside** the corpus (to demonstrate refusal, A3).

The shipped sample lives in `backend/data/sample/` (built in Phase 2). Swapping
domains means pointing ingest at a different folder (e.g. the dataset handed out
on demo day) and re-running it; the retrieval, budgeting, and API code don't
change.

## Acceptance criteria

- [ ] **A1** Ingesting the sample corpus produces a local index; command prints
      file/chunk/token counts.
- [ ] **A2** A grounded question returns a streamed answer that cites the
      correct source file.
- [ ] **A3** An out-of-corpus question returns a refusal with **no** citations.
- [ ] **A4** The assembled prompt never exceeds the input budget; the `done`
      event reports per-slice token counts (`/api/health` reports the budget
      config). _(deterministic — unit tested)_
- [ ] **A5** Measured `prompt_eval_count` (tokens the model actually saw) stays
      `≤ 6144` and within the safety margin of our estimate. _(empirical — smoke
      script)_
- [ ] **A6** With a long history, oldest turns drop while system prompt, context,
      and current question survive.
- [ ] **A7** No cloud calls at runtime (LLM or embeddings).
