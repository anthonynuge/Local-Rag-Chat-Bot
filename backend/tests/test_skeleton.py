"""The service boots, health reports honestly, the chat stub emits contract-shaped events.

Deterministic: the llm seam is monkeypatched — no live Ollama.
"""

from fastapi.testclient import TestClient

from main import app
from rag import config, llm

client = TestClient(app)


def test_health_ok(monkeypatch):
    monkeypatch.setattr(llm, "available_models", lambda: [config.MODEL, config.EMBED_MODEL])
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["ollama"]["reachable"] is True
    assert body["models"]["present"] is True
    assert body["budget"]["num_ctx"] == 6144
    assert body["budget"]["input_budget"] == 4608


def test_health_503_when_ollama_unreachable(monkeypatch):
    def boom():
        raise ConnectionError("connection refused")

    monkeypatch.setattr(llm, "available_models", boom)
    r = client.get("/api/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unhealthy"
    assert body["ollama"]["reachable"] is False
    assert "unreachable" in body["reason"]


def test_health_503_when_model_missing(monkeypatch):
    monkeypatch.setattr(llm, "available_models", lambda: ["some-other-model:7b"])
    r = client.get("/api/health")
    assert r.status_code == 503
    body = r.json()
    assert body["ollama"]["reachable"] is True
    assert body["models"]["present"] is False
    assert "not pulled" in body["reason"]


def test_chat_stub_emits_contract_events():
    r = client.post("/api/chat", json={"message": "What is the PTO policy?"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    body = r.text
    # events arrive in contract order: token(s) → citations → done
    assert "event: token" in body
    assert body.index("event: token") < body.index("event: citations") < body.index("event: done")
    assert '"source": "pto-policy.md"' in body
