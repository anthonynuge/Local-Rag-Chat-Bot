"""The service boots and health reports honestly.

Deterministic: the llm seam and the index are faked — no live Ollama, no storage/.
(The chat endpoint's own tests live in test_chat.py.)
"""

import numpy as np
from fastapi.testclient import TestClient

import main
from rag import config, llm, store

client = TestClient(main.app)


def _fake_index():
    vecs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    chunks = [
        {"source": "a.md", "heading": "H", "text": "alpha", "idx": 0},
        {"source": "b.md", "heading": "", "text": "beta", "idx": 0},
    ]
    return store.Store(vecs, chunks)


def _wire_healthy(monkeypatch):
    monkeypatch.setattr(llm, "available_models", lambda: [config.MODEL, config.EMBED_MODEL])
    monkeypatch.setattr(main, "get_index", _fake_index)


def test_health_ok(monkeypatch):
    _wire_healthy(monkeypatch)
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["ollama"]["reachable"] is True
    assert body["models"]["present"] is True
    assert body["index"] == {"loaded": True, "chunks": 2, "sources": 2}
    assert body["budget"]["num_ctx"] == 6144
    assert body["budget"]["input_budget"] == 4608


def test_health_503_when_ollama_unreachable(monkeypatch):
    def boom():
        raise ConnectionError("connection refused")

    monkeypatch.setattr(llm, "available_models", boom)
    monkeypatch.setattr(main, "get_index", _fake_index)
    r = client.get("/api/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unhealthy"
    assert body["ollama"]["reachable"] is False
    assert "unreachable" in body["reason"]


def test_health_503_when_model_missing(monkeypatch):
    monkeypatch.setattr(llm, "available_models", lambda: ["some-other-model:7b"])
    monkeypatch.setattr(main, "get_index", _fake_index)
    r = client.get("/api/health")
    assert r.status_code == 503
    body = r.json()
    assert body["ollama"]["reachable"] is True
    assert body["models"]["present"] is False
    assert "not pulled" in body["reason"]


def test_health_503_when_index_missing(monkeypatch):
    def no_index():
        raise FileNotFoundError("storage/index.npz")

    monkeypatch.setattr(llm, "available_models", lambda: [config.MODEL, config.EMBED_MODEL])
    monkeypatch.setattr(main, "get_index", no_index)
    r = client.get("/api/health")
    assert r.status_code == 503
    body = r.json()
    assert body["index"]["loaded"] is False
    assert "index not loaded" in body["reason"]
