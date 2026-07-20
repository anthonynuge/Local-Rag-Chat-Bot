# CLAUDE.md

Local RAG chat: local LLM (Ollama, **6K context**) over `.md`/`.txt`, grounded
cited answers. **Core problem: 6K token-budget management.**

Design lives in `docs/` — read the relevant file when a task touches it:
`spec.md` (requirements), `architecture.md` (design + the 6K budget),
`api-contract.md` (frontend↔backend), `tasks.md` (build order),
`corpus-generation-prompt.md` (sample-data generation prompt).

## Layout
`backend/` is a uv project: `main.py` (FastAPI entry), all logic in the `rag/`
package. Source docs in `backend/data/<dataset>/`, generated index in
`backend/storage/`. Full tree + module roles: [architecture.md](docs/architecture.md).

## Guardrails
- Only `backend/rag/llm.py` imports the Ollama client.
- Prompts are assembled only by `budget.pack()`; never exceed `input_budget`.
- `prompt_eval_count + answer_reserve ≤ 6144` — verify empirically.
- Grounded only: out-of-corpus → refusal, no citations.
- Config in `backend/rag/config.py` (env-overridable); no magic numbers elsewhere.

## Commands (run from `backend/`)
```bash
uv sync                                # install deps
uv run python -m rag.ingest ./data/sample   # build index
uv run uvicorn main:app --reload            # backend :8000
uv run pytest tests                         # deterministic tests (no Ollama)
uv run python ../scripts/smoke.py           # live end-to-end check
uv run python ../scripts/eval.py [data_dir] # quality rates vs baseline.json
uv run python ../scripts/chat.py [data_dir] # interactive debug REPL (shows chunks/prompt)
```

`scripts/dev.ps1` / `scripts/dev.sh` (from repo root) start backend + frontend together.
`scripts/demo.ps1` does the same with the backend in a visible pane/window (pipeline trace on screen for demos).

Trunk-based: short branches off `main`, local squash-merge; `pytest tests` green before every merge.
