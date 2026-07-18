"""Live eval harness: run a dataset's question set and report quality rates.

Run from backend/:   uv run python ../scripts/eval.py [data_dir]
Defaults to config.DATA_DIR (data/sample). Expects <data_dir>/eval.json with
three lists: "corpus" (must cite the expected file), "refusal" (must cite
nothing), "multi_turn" (sequences where every turn must keep citing).

Rates reported: retrieval hit-rate, citation-rate, refusal-rate, multi-turn
sequences passed. TTFT and tok/s are informational (hardware-dependent).
Exit 0 when every check passes, 1 otherwise.

Needs Ollama running with both models pulled. Sequential on purpose — a
single local GPU serializes requests anyway.
"""
import json
import sys
import time
from pathlib import Path

# eval.py lives in scripts/; the app package lives in backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient  # noqa: E402  (path setup must come first)

import main as app_main                     # noqa: E402
from rag import config, ingest, llm, store  # noqa: E402
from smoke import parse_sse, data_for       # noqa: E402  (same scripts/ dir)


def ask(client, message, history):
    """POST /api/chat; returns (answer, cited_sources, ttft, tok_s).

    TestClient buffers the SSE stream, so per-frame wall-clock timing is
    meaningless. Instead: Ollama's own eval_duration (forwarded in the done
    event) is the pure generation time, and total wall time minus that is
    everything before the first token — an honest TTFT."""
    started = time.perf_counter()
    response = client.post(
        "/api/chat", json={"message": message, "history": history}
    )
    wall_seconds = time.perf_counter() - started
    assert response.status_code == 200, f"chat returned {response.status_code}"

    events = parse_sse(response.text)

    deltas = []
    for event, data in events:
        if event == "token":
            deltas.append(data["delta"])
    answer = "".join(deltas)

    cited_sources = set()
    for citation in data_for(events, "citations")["citations"]:
        cited_sources.add(citation["source"])

    done = data_for(events, "done")  # fails loudly if the stream errored

    generation_seconds = done["eval_duration"] / 1e9  # Ollama reports nanoseconds
    if generation_seconds > 0:
        tok_s = done["eval_count"] / generation_seconds
    else:
        tok_s = 0.0
    ttft = max(wall_seconds - generation_seconds, 0.0)
    return answer, cited_sources, ttft, tok_s


def retrieval_hit(index, question, expected_source):
    """True if the expected file appears in the top-k retrieved chunks.

    Same embed -> top_k path the endpoint uses; computed here because the
    citations SSE event only carries chunks the answer actually cited."""
    query_vec = llm.embed([question])[0]
    sources = set()
    for chunk in index.top_k(query_vec):
        sources.add(chunk["source"])
    return expected_source in sources


def run():
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else config.DATA_DIR
    question_set = json.loads((data_dir / "eval.json").read_text(encoding="utf-8"))
    corpus_questions = question_set["corpus"]
    refusal_questions = question_set["refusal"]
    sequences = question_set["multi_turn"]

    print(f"[1/5] ingest: rebuilding index from {data_dir} ...")
    ingest.main(data_dir)

    client = TestClient(app_main.app)

    print("[2/5] health ...")
    health = client.get("/api/health")
    assert health.status_code == 200, f"unhealthy: {health.json()}"

    index = store.load()

    retrieval_checks = 0
    retrieval_hits = 0
    ttfts = []
    speeds = []

    print(f"[3/5] in-corpus: {len(corpus_questions)} questions ...")
    cited_correctly = 0
    for entry in corpus_questions:
        question = entry["question"]
        expected = entry["expected_source"]
        retrieval_checks += 1
        retrieved = retrieval_hit(index, question, expected)
        if retrieved:
            retrieval_hits += 1
        answer, cited_sources, ttft, tok_s = ask(client, question, [])
        ttfts.append(ttft)
        speeds.append(tok_s)
        cited = expected in cited_sources
        if cited:
            cited_correctly += 1
            status = "ok  "
        else:
            status = "MISS"
        detail = "" if cited else f"  (cited {sorted(cited_sources)}, answer: {answer[:90]!r})"
        ret_flag = "ok" if retrieved else "MISS"
        print(f"      {status} cite {expected:<20} ret={ret_flag:<4} "
              f"ttft={ttft:.2f}s {tok_s:5.1f} tok/s  {question!r}{detail}")

    print(f"[4/5] must-refuse: {len(refusal_questions)} questions ...")
    refused = 0
    for entry in refusal_questions:
        question = entry["question"]
        answer, cited_sources, ttft, tok_s = ask(client, question, [])
        ttfts.append(ttft)
        speeds.append(tok_s)
        if cited_sources == set():
            refused += 1
            status = "ok  "
        else:
            status = "MISS"
        print(f"      {status} refuse ({sorted(cited_sources)} cited)  {question!r}")

    print(f"[5/5] multi-turn: {len(sequences)} sequences ...")
    passed_sequences = 0
    for sequence in sequences:
        history = []
        every_turn_cited = True
        print(f"      -- {sequence['name']}")
        for turn in sequence["turns"]:
            question = turn["question"]
            expected = turn["expected_source"]
            retrieval_checks += 1
            retrieved = retrieval_hit(index, question, expected)
            if retrieved:
                retrieval_hits += 1
            answer, cited_sources, ttft, tok_s = ask(client, question, history)
            ttfts.append(ttft)
            speeds.append(tok_s)
            cited = expected in cited_sources
            if cited:
                status = "ok  "
            else:
                status = "MISS"
                every_turn_cited = False
            detail = "" if cited else f"  (cited {sorted(cited_sources)}, answer: {answer[:90]!r})"
            ret_flag = "ok" if retrieved else "MISS"
            print(f"      {status} cite {expected:<20} ret={ret_flag:<4} "
                  f"history={len(history)//2} turns  {question!r}{detail}")
            # Carry the model's ACTUAL answer forward — an uncited answer in
            # history is the suspected drift mechanism, so never substitute
            # a canned one.
            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": answer})
        if every_turn_cited:
            passed_sequences += 1

    failing = (
        (retrieval_checks - retrieval_hits)
        + (len(corpus_questions) - cited_correctly)
        + (len(refusal_questions) - refused)
        + (len(sequences) - passed_sequences)
    )
    total_requests = len(ttfts)

    print(f"\n=== EVAL REPORT ({data_dir.name}, {total_requests} requests) ===")
    print(f"retrieval hit-rate: {retrieval_hits}/{retrieval_checks} "
          f"({100 * retrieval_hits / retrieval_checks:.0f}%)")
    print(f"citation-rate:      {cited_correctly}/{len(corpus_questions)} "
          f"({100 * cited_correctly / len(corpus_questions):.0f}%)")
    print(f"refusal-rate:       {refused}/{len(refusal_questions)} "
          f"({100 * refused / len(refusal_questions):.0f}%)")
    print(f"multi-turn:         {passed_sequences}/{len(sequences)} sequences")
    print(f"TTFT avg:           {sum(ttfts) / total_requests:.2f}s   "
          f"tok/s avg: {sum(speeds) / total_requests:.1f}")
    if failing == 0:
        print("EVAL GREEN")
    else:
        print(f"EVAL RED ({failing} failing checks)")
    sys.exit(0 if failing == 0 else 1)


if __name__ == "__main__":
    run()
