"""FastAPI entry — walking skeleton. Routes are the HTTP seam; RAG logic lives in rag/.

/api/health probes Ollama through the llm seam (503 + reason when it can't serve).
/api/chat streams a canned SSE sequence shaped like the real contract so the
frontend can integrate before the pipeline exists; its insides get swapped for
the live pipeline in Phase 6 — the SSE shape doesn't change.
"""

import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from rag import config, llm

app = FastAPI(title="Local RAG Chat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sse(event: str, data: dict) -> str:
    """One SSE frame: named event + JSON data, terminated by a blank line."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


def _has_model(want: str, models: list[str]) -> bool:
    """True if `want` is in `models`. A fully tagged want ("llama3.2:3b") needs an
    exact match; a bare want ("nomic-embed-text") matches any tag of that model."""
    for model in models:
        if model == want:
            return True
        base_name = model.split(":", 1)[0]  # "nomic-embed-text:latest" -> "nomic-embed-text"
        if ":" not in want and base_name == want:
            return True
    return False


@app.get("/api/health")
def health():
    body = {
        "status": "ok",
        "ollama": {"reachable": False, "host": config.OLLAMA_HOST},
        "models": {"chat": config.MODEL, "embed": config.EMBED_MODEL, "present": False},
        "index": {"loaded": False},  # wired in Phase 4
        "budget": {
            "num_ctx": config.NUM_CTX,
            "answer_reserve": config.ANSWER_RESERVE,
            "safety_frac": config.SAFETY_FRAC,
            "input_budget": config.INPUT_BUDGET,
            "context_budget": config.CONTEXT_BUDGET,
        },
    }
    reason = None
    try:
        models = llm.available_models()
        body["ollama"]["reachable"] = True
        body["models"]["present"] = all(
            _has_model(want, models) for want in (config.MODEL, config.EMBED_MODEL)
        )
        if not body["models"]["present"]:
            reason = f"model(s) not pulled: have {models}"
    except Exception as e:
        reason = f"ollama unreachable: {e}"

    if reason:
        body["status"] = "unhealthy"
        body["reason"] = reason
        return JSONResponse(body, status_code=503)
    return body


def _stub_stream():
    """Canned token → citations → done sequence, per api-contract.md."""
    for delta in ["Full-time ", "employees ", "accrue ", "1.5 days ", "per month."]:
        yield _sse("token", {"delta": delta})
    yield _sse("citations", {"citations": [{"id": 1, "source": "pto-policy.md", "heading": "Accrual"}]})
    yield _sse("done", {
        "prompt_eval_count": 0,
        "eval_count": 0,
        "budget": {"system": 0, "context": 0, "history": 0, "question": 0},
    })


@app.post("/api/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    # canned stream; retrieve → pack → llm.chat() replaces this in Phase 6.
    return StreamingResponse(_stub_stream(), media_type="text/event-stream")
