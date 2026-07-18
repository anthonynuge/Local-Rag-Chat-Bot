"""FastAPI entry — routes are the HTTP seam; RAG logic lives in rag/.

/api/health probes Ollama and the index (503 + reason when it can't serve).
/api/chat runs the live pipeline: retrieve → pack → llm.chat(), streamed as
SSE (token → citations → done, or error), per api-contract.md.
"""

import json
import logging
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from rag import budget, config, llm, store

logging.basicConfig(level=config.LOG_LEVEL, format="%(levelname)s %(name)s | %(message)s")
logger = logging.getLogger("rag.api")

app = FastAPI(title="Local RAG Chat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

_index = None


def get_index():
    """Load the saved index once, on first use; raises if ingest never ran."""
    global _index
    if _index is None:
        _index = store.load()
    return _index


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
        "index": {"loaded": False, "chunks": 0, "sources": 0},
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

    try:
        index = get_index()
        sources = {chunk["source"] for chunk in index.chunks}
        body["index"] = {"loaded": True, "chunks": len(index.chunks), "sources": len(sources)}
    except Exception as e:
        reason = reason or f"index not loaded: {e}"

    if reason:
        body["status"] = "unhealthy"
        body["reason"] = reason
        return JSONResponse(body, status_code=503)
    return body


def _stream(messages, citations, report):
    """Yield SSE frames from the live model: token* → citations → done.

    Any failure mid-stream yields an error event instead of done and ends
    the stream (api-contract.md)."""
    try:
        deltas = []
        final = None
        for chunk in llm.chat(messages):
            delta = chunk["message"]["content"]
            if delta:
                deltas.append(delta)
                yield _sse("token", {"delta": delta})
            final = chunk

        # Only sources the answer actually cites — a refusal cites nothing (spec A3).
        answer = "".join(deltas)
        # r"\[(\d+)\]" finds every [1], [2], ... marker and captures the number.
        cited_ids = {int(number) for number in re.findall(r"\[(\d+)\]", answer)}
        cited = [citation for citation in citations if citation["id"] in cited_ids]
        yield _sse("citations", {"citations": cited})

        logger.info("answer: %d chars, cited %s", len(answer), sorted(cited_ids) or "nothing")

        # 6K guardrail (architecture.md#budget), checked empirically: Ollama's own
        # prompt token count plus the answer reserve must fit the context window.
        prompt_tokens = final["prompt_eval_count"]
        if prompt_tokens + config.ANSWER_RESERVE > config.NUM_CTX:
            raise RuntimeError(f"budget breach: prompt_eval_count={prompt_tokens}")

        estimate = report["system"] + report["context"] + report["history"] + report["question"]
        logger.info("budget: prompt_eval_count=%d, estimate=%d", prompt_tokens, estimate)

        yield _sse("done", {
            "prompt_eval_count": prompt_tokens,
            "eval_count": final["eval_count"],
            # generation time in ns (api-contract.md); .get keeps faked
            # streams in tests working without the field
            "eval_duration": final.get("eval_duration", 0),
            "budget": report,
        })
    except Exception as e:
        logger.exception("chat stream failed")  # full traceback server-side; client gets the message
        yield _sse("error", {"message": str(e)})


@app.post("/api/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    question = req.message.strip()
    if not question:
        raise HTTPException(400, "empty message")

    try:
        # Pre-flight with no context/history: rejects an oversized question
        # with a 400 before the query ever reaches the embedder.
        budget.pack(config.SYSTEM_PROMPT, question, [], [])
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    query_vec = llm.embed([question])[0]  # embed() is batch-shaped; one question -> row 0
    ranked = get_index().top_k(query_vec)
    messages, citations, report = budget.pack(config.SYSTEM_PROMPT, question, ranked, req.history)

    # Retrieval trace: what came back, how confident, and whether pack() kept it.
    # pack() keeps a strict rank-order prefix, so the first len(citations) are in.
    logger.info("chat: %r (history=%d turns)", question[:80], len(req.history))
    for rank, chunk in enumerate(ranked, start=1):
        kept = "packed" if rank <= len(citations) else "dropped by budget"
        logger.info(
            "  #%d score=%.3f %s — %r (%s)",
            rank, chunk["score"], chunk["source"], chunk["heading"], kept,
        )

    return StreamingResponse(_stream(messages, citations, report), media_type="text/event-stream")
