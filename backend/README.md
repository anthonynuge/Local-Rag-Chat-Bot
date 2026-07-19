# backend

FastAPI service + `rag/` package (chunking, retrieval, budget packing, Ollama seam).

Setup, commands, and docs live in the [root README](../README.md);
design details in [docs/architecture.md](../docs/architecture.md).

```bash
uv sync                                   # install
uv run python -m rag.ingest ./data/sample # build the index
uv run uvicorn main:app --reload          # serve on :8000
uv run pytest tests                       # tests (no Ollama needed)
```
