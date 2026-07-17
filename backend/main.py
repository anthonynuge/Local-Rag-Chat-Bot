"""FastAPI entry — walking skeleton. Routes are the HTTP seam; RAG logic lives in rag/.

Phase 1: /api/health returns 200; /api/chat streams a canned SSE sequence shaped
like the real contract so the frontend can integrate before the pipeline exists.
The stub's insides get swapped for the live pipeline in Phase 6 — the SSE shape
doesn't change.
"""

import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from rag import config

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


@app.get("/api/health")
def health() -> dict:
    # Budget block is real (from config); ollama/index checks land in Phase 3/4.
    return {
        "status": "ok",
        "ollama": {"reachable": False, "host": config.OLLAMA_HOST},
        "models": {"chat": config.MODEL, "embed": config.EMBED_MODEL, "present": False},
        "index": {"loaded": False},
        "budget": {
            "num_ctx": config.NUM_CTX,
            "answer_reserve": config.ANSWER_RESERVE,
            "safety_frac": config.SAFETY_FRAC,
            "input_budget": config.INPUT_BUDGET,
            "context_budget": config.CONTEXT_BUDGET,
        },
    }


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
    # ponytail: canned stream; retrieve → pack → llm.chat() replaces this in Phase 6.
    return StreamingResponse(_stub_stream(), media_type="text/event-stream")
