"""POST /api/chat: SSE event shape/order, citation filtering, 400s, error event.

Deterministic: the llm seam and the index are faked — no live Ollama.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

import main
from rag import config, llm, store

client = TestClient(main.app)


def _fake_index():
    vecs = np.array([[1.0, 0.0]], dtype=np.float32)
    chunks = [{
        "source": "pto-policy.md",
        "heading": "Accrual",
        "text": "PTO accrues at 1.5 days per month.",
        "idx": 0,
    }]
    return store.Store(vecs, chunks)


def _fake_chat(deltas, prompt_eval_count=100):
    """A stand-in for llm.chat: yields token chunks, then a final counting chunk."""
    def fake(messages):
        for delta in deltas:
            yield {"message": {"content": delta}, "done": False}
        yield {
            "message": {"content": ""},
            "done": True,
            "prompt_eval_count": prompt_eval_count,
            "eval_count": len(deltas),
        }
    return fake


@pytest.fixture
def wired(monkeypatch):
    """Fake index + embedder; each test picks its own llm.chat behavior."""
    monkeypatch.setattr(main, "get_index", _fake_index)

    def fake_embed(texts):
        # every text embeds to the same unit vector — retrieval always hits the one chunk
        return np.array([[1.0, 0.0]] * len(texts), dtype=np.float32)

    monkeypatch.setattr(llm, "embed", fake_embed)
    return monkeypatch


def test_chat_streams_contract_events_in_order(wired):
    wired.setattr(llm, "chat", _fake_chat(["PTO accrues ", "at 1.5 days [1]."]))
    r = client.post("/api/chat", json={"message": "How much PTO?"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    body = r.text
    assert body.index("event: token") < body.index("event: citations") < body.index("event: done")
    assert '"delta": "PTO accrues "' in body
    assert '"source": "pto-policy.md"' in body        # cited -> included
    assert '"prompt_eval_count": 100' in body
    assert '"input_budget"' in body                    # budget report rides in done


def test_uncited_sources_are_dropped(wired):
    # answer never cites [1] -> citations event is an empty list (refusal path, spec A3)
    wired.setattr(llm, "chat", _fake_chat(["I don't have that information."]))
    r = client.post("/api/chat", json={"message": "What is the meaning of life?"})
    assert '"citations": []' in r.text


def test_error_event_replaces_done(wired):
    def exploding_chat(messages):
        yield {"message": {"content": "part"}, "done": False}
        raise RuntimeError("ollama fell over")

    wired.setattr(llm, "chat", exploding_chat)
    r = client.post("/api/chat", json={"message": "hello?"})
    body = r.text
    assert "event: error" in body
    assert "ollama fell over" in body
    assert "event: done" not in body


def test_budget_breach_yields_error_not_done(wired):
    # Ollama reports more prompt tokens than the 6K window allows -> guardrail trips
    wired.setattr(llm, "chat", _fake_chat(["hi [1]"], prompt_eval_count=99999))
    r = client.post("/api/chat", json={"message": "hi"})
    body = r.text
    assert "budget breach" in body
    assert "event: done" not in body


def test_empty_message_400():
    r = client.post("/api/chat", json={"message": "   "})
    assert r.status_code == 400


def test_oversized_question_400():
    huge = "why " * config.INPUT_BUDGET
    r = client.post("/api/chat", json={"message": huge})
    assert r.status_code == 400
    assert "question too large" in r.json()["detail"]
