"""Phase 1: the service boots, health is 200, the chat stub emits contract-shaped events."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["budget"]["num_ctx"] == 6144
    assert body["budget"]["input_budget"] == 4608


def test_chat_stub_emits_contract_events():
    r = client.post("/api/chat", json={"message": "What is the PTO policy?"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    body = r.text
    # events arrive in contract order: token(s) → citations → done
    assert "event: token" in body
    assert body.index("event: token") < body.index("event: citations") < body.index("event: done")
    assert '"source": "pto-policy.md"' in body
