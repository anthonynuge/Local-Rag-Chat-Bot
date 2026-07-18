"""Live end-to-end smoke check: ingest -> chat -> assert citation + budget.

Run from backend/:   uv run python ../scripts/smoke.py
CPU-only calibration: $env:NUM_GPU = "0"; uv run python ../scripts/smoke.py

Needs Ollama running with both models pulled. Exercises the real pipeline
in-process (TestClient) — no separate server required.
"""
import json
import sys
from pathlib import Path

# smoke.py lives in scripts/; the app package lives in backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient  # noqa: E402  (path setup must come first)

import main as app_main                    # noqa: E402
from rag import config, ingest             # noqa: E402


def parse_sse(body):
    """SSE text -> list of (event, data) in stream order."""
    events = []
    for frame in body.strip().split("\n\n"):
        event_line, data_line = frame.split("\n", 1)
        event = event_line.removeprefix("event: ")
        data = json.loads(data_line.removeprefix("data: "))
        events.append((event, data))
    return events


def data_for(events, wanted):
    """The data dict of the first `wanted` event; fails loudly if absent."""
    for event, data in events:
        if event == wanted:
            return data
    raise AssertionError(f"no '{wanted}' event in stream: {[e for e, _ in events]}")


def run():
    print("[1/4] ingest: rebuilding index from data/sample ...")
    ingest.main()

    client = TestClient(app_main.app)

    print("[2/4] health ...")
    health = client.get("/api/health")
    assert health.status_code == 200, f"unhealthy: {health.json()}"
    print("      index:", health.json()["index"])

    print("[3/4] in-corpus question -> must answer and cite pto-policy.md ...")
    question = "How much PTO do full-time employees accrue per month?"
    r = client.post("/api/chat", json={"message": question})
    events = parse_sse(r.text)

    tokens = [data["delta"] for event, data in events if event == "token"]
    answer = "".join(tokens)
    citations = data_for(events, "citations")["citations"]
    done = data_for(events, "done")

    cited_sources = {citation["source"] for citation in citations}
    assert "pto-policy.md" in cited_sources, f"expected pto-policy.md cited, got {cited_sources}"

    # The 6K guardrail, on real numbers from Ollama:
    prompt_tokens = done["prompt_eval_count"]
    assert prompt_tokens + config.ANSWER_RESERVE <= config.NUM_CTX, (
        f"budget breach: {prompt_tokens} + {config.ANSWER_RESERVE} > {config.NUM_CTX}"
    )

    # Calibration: tiktoken estimate vs what the model actually saw.
    report = done["budget"]
    estimate = report["system"] + report["context"] + report["history"] + report["question"]
    drift = (prompt_tokens - estimate) / estimate
    assert abs(drift) <= config.SAFETY_FRAC, (
        f"calibration drift {drift:+.1%} exceeds SAFETY_FRAC {config.SAFETY_FRAC:.0%} — "
        "consider swapping tiktoken for the model tokenizer (architecture.md#calibration)"
    )

    print(f"      answer: {answer[:70]!r}")
    print(f"      cited: {sorted(cited_sources)}")
    print(f"      prompt_eval_count={prompt_tokens}, estimate={estimate}, drift={drift:+.1%} "
          f"(margin {config.SAFETY_FRAC:.0%})")

    print("[4/4] out-of-corpus question -> must refuse with zero citations ...")
    r = client.post("/api/chat", json={"message": "Who won the 2018 FIFA World Cup?"})
    events = parse_sse(r.text)
    refusal_citations = data_for(events, "citations")["citations"]
    assert refusal_citations == [], f"refusal should cite nothing, got {refusal_citations}"
    data_for(events, "done")  # refusal still ends with a clean done event

    print("SMOKE PASSED")


if __name__ == "__main__":
    run()
