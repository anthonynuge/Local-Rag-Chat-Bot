"""Live eval harness: run a dataset's question set and report quality rates.

Run from backend/:   uv run python ../scripts/eval.py [data_dir] [--metrics]
Defaults to config.DATA_DIR (data/sample). Expects <data_dir>/eval.json with
three lists: "corpus" (must cite the expected file), "refusal" (must cite
nothing), "multi_turn" (sequences where every turn must keep citing).

Rates reported: retrieval hit-rate, citation-rate, refusal-rate, multi-turn
sequences passed. TTFT and tok/s are informational (hardware-dependent).
Exit 0 when every check passes, 1 otherwise.

Every run is also written to evals/results/<dataset>-<timestamp>.json
(gitignored — machine- and moment-specific) with a full config snapshot, so
any two runs stay comparable after the knobs change. If <data_dir>/
baseline.json exists (committed; updated by hand when a change is accepted),
the summary prints the difference against it.

--metrics adds a per-question block: stage timings, token counts, and
best-effort CPU/RAM/GPU readings. Stages that don't exist yet (BM25,
reranking, graph expansion) have no rows; each gets a row when it lands.

Needs Ollama running with both models pulled. Sequential on purpose — a
single local GPU serializes requests anyway.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# eval.py lives in scripts/; the app package lives in backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient  # noqa: E402  (path setup must come first)

import main as app_main                     # noqa: E402
from rag import config, ingest, llm, store  # noqa: E402
from rag.chunk import n_tokens              # noqa: E402
from smoke import parse_sse, data_for       # noqa: E402  (same scripts/ dir)

RESULTS_DIR = Path(__file__).resolve().parents[1] / "evals" / "results"

# The knobs a prompt or retrieval experiment might change. A run record
# without these is unreadable once the next experiment starts.
CONFIG_KEYS = [
    "MODEL", "EMBED_MODEL", "TEMPERATURE", "NUM_CTX", "ANSWER_RESERVE",
    "SAFETY_FRAC", "INPUT_BUDGET", "CONTEXT_BUDGET", "TOP_K",
    "CHUNK_TOKENS", "CHUNK_OVERLAP", "SYSTEM_PROMPT", "CITE_REMINDER",
]

# ANSI colors. Windows Terminal understands them natively; the empty
# os.system("") call flips classic conhost into VT mode too. Piped or
# redirected output (not a tty) stays plain so saved logs are clean.
GREEN, RED, YELLOW, BOLD, DIM = "32", "31", "33", "1", "2"
COLOR_ENABLED = sys.stdout.isatty()
if COLOR_ENABLED and os.name == "nt":
    os.system("")


def paint(text, color):
    if not COLOR_ENABLED:
        return text
    return f"\033[{color}m{text}\033[0m"


def paint_rate(passed, total):
    """passed/total colored: full green, partial yellow, zero red."""
    if passed == total:
        color = GREEN
    elif passed == 0:
        color = RED
    else:
        color = YELLOW
    return paint(f"{passed}/{total}", color)


def ask(client, message, history):
    """POST /api/chat; returns (answer, cited_sources, stats dict).

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
    stats = {
        "ttft_s": max(wall_seconds - generation_seconds, 0.0),
        "tok_s": tok_s,
        "total_s": wall_seconds,
        "prompt_tokens": done["prompt_eval_count"],
        "context_tokens": done["budget"]["context"],
    }
    return answer, cited_sources, stats


def retrieval_hit(index, question, expected_source):
    """(hit, embed_seconds, search_seconds): is the expected file in top-k?

    Same embed -> top_k path the endpoint uses; computed here because the
    citations SSE event only carries chunks the answer actually cited. The
    timings are this process's own calls, but they mirror the endpoint's
    retrieval stage exactly."""
    started = time.perf_counter()
    query_vec = llm.embed([question])[0]
    embed_seconds = time.perf_counter() - started

    started = time.perf_counter()
    chunks = index.top_k(query_vec)
    search_seconds = time.perf_counter() - started

    sources = set()
    for chunk in chunks:
        sources.add(chunk["source"])
    return expected_source in sources, embed_seconds, search_seconds


def sample_resources():
    """Best-effort [(label, value)] resource rows; a missing tool drops its row.

    cpu_percent() averages since the previous call, so one call per question
    covers roughly that question's lifetime (run() makes a priming call
    first — the very first reading is always 0 otherwise). nvidia-smi's
    utilization covers its last sample period, close enough to "during
    generation" when read right after the response."""
    rows = []
    try:
        import psutil
        cpu_percent = psutil.cpu_percent()
        ram_gb = psutil.virtual_memory().used / 1e9
        rows.append(("CPU", f"{cpu_percent:.0f}%"))
        rows.append(("RAM used", f"{ram_gb:.1f} GB"))
    except ImportError:
        pass
    try:
        query = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        # one "util%, MiB" line per GPU; single-GPU box, take the first
        util_percent, vram_mib = query.stdout.strip().splitlines()[0].split(", ")
        rows.append(("GPU", f"{util_percent}%"))
        rows.append(("GPU VRAM", f"{int(vram_mib) / 1024:.1f} GB"))
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        pass
    return rows


def print_query_metrics(question, embed_seconds, search_seconds, stats):
    rows = [("question length", f"{n_tokens(question)} tokens")]
    # refusal questions pass 0.0/0.0 — no retrieval was timed for them
    if embed_seconds or search_seconds:
        rows.append(("embedding time", f"{embed_seconds * 1000:.0f} ms"))
        # cosine over a few dozen chunks is one numpy matmul: microseconds.
        # "us" not the µ glyph — Windows console codepages mangle it
        rows.append(("vector search", f"{search_seconds * 1_000_000:.0f} us"))
    rows.extend([
        ("context tokens", f"{stats['context_tokens']:,}"),
        ("prompt tokens", f"{stats['prompt_tokens']:,}"),
        ("TTFT", f"{stats['ttft_s'] * 1000:.0f} ms"),
        ("generation speed", f"{stats['tok_s']:.1f} tok/s"),
        ("total response", f"{stats['total_s']:.2f} s"),
    ])
    rows.extend(sample_resources())
    for label, value in rows:
        print(paint(f"           {label + ':':<18}{value:>12}", DIM))
    print()


def make_record(phase, question, stats, **extra):
    """One per-question entry for the run's results JSON."""
    record = {
        "phase": phase,
        "question": question,
        "ttft_s": round(stats["ttft_s"], 3),
        "tok_s": round(stats["tok_s"], 1),
        "total_s": round(stats["total_s"], 3),
        "prompt_tokens": stats["prompt_tokens"],
        "context_tokens": stats["context_tokens"],
    }
    record.update(extra)
    return record


def run():
    arguments = sys.argv[1:]
    metrics_enabled = "--metrics" in arguments
    positional = [argument for argument in arguments if not argument.startswith("--")]
    data_dir = Path(positional[0]) if positional else config.DATA_DIR
    question_set = json.loads((data_dir / "eval.json").read_text(encoding="utf-8"))
    corpus_questions = question_set["corpus"]
    refusal_questions = question_set["refusal"]
    sequences = question_set["multi_turn"]

    if metrics_enabled:
        try:
            import psutil
            psutil.cpu_percent()  # priming call — see sample_resources()
        except ImportError:
            pass

    print(paint(f"[1/5] ingest: rebuilding index from {data_dir} ...", BOLD))
    ingest.main(data_dir)

    client = TestClient(app_main.app)

    print(paint("[2/5] health ...", BOLD))
    health = client.get("/api/health")
    assert health.status_code == 200, f"unhealthy: {health.json()}"

    index = store.load()

    retrieval_checks = 0
    retrieval_hits = 0
    ttfts = []
    speeds = []
    records = []

    print(paint(f"\n[3/5] in-corpus: {len(corpus_questions)} questions ...", BOLD))
    cited_correctly = 0
    for entry in corpus_questions:
        question = entry["question"]
        expected = entry["expected_source"]
        retrieval_checks += 1
        retrieved, embed_seconds, search_seconds = retrieval_hit(index, question, expected)
        if retrieved:
            retrieval_hits += 1
        answer, cited_sources, stats = ask(client, question, [])
        ttfts.append(stats["ttft_s"])
        speeds.append(stats["tok_s"])
        cited = expected in cited_sources
        if cited:
            cited_correctly += 1
        # pad BEFORE painting — the invisible color codes would break
        # f-string column alignment otherwise
        status = paint("ok  ", GREEN) if cited else paint("MISS", RED)
        detail = "" if cited else f"  (cited {sorted(cited_sources)}, answer: {answer[:90]!r})"
        ret_flag = paint("ok  ", GREEN) if retrieved else paint("MISS", RED)
        print(f"      {status} cite {expected:<20} ret={ret_flag} "
              f"ttft={stats['ttft_s']:.2f}s {stats['tok_s']:5.1f} tok/s  {question!r}{detail}")
        if metrics_enabled:
            print_query_metrics(question, embed_seconds, search_seconds, stats)
        records.append(make_record(
            "corpus", question, stats,
            expected_source=expected, retrieved=retrieved, cited=cited,
            cited_sources=sorted(cited_sources),
            embed_ms=round(embed_seconds * 1000, 1),
            search_ms=round(search_seconds * 1000, 2),
        ))

    print(paint(f"\n[4/5] must-refuse: {len(refusal_questions)} questions ...", BOLD))
    refused = 0
    for entry in refusal_questions:
        question = entry["question"]
        answer, cited_sources, stats = ask(client, question, [])
        ttfts.append(stats["ttft_s"])
        speeds.append(stats["tok_s"])
        if cited_sources == set():
            refused += 1
        status = paint("ok  ", GREEN) if cited_sources == set() else paint("MISS", RED)
        print(f"      {status} refuse ({sorted(cited_sources)} cited)  {question!r}")
        if metrics_enabled:
            print_query_metrics(question, 0.0, 0.0, stats)
        records.append(make_record(
            "refusal", question, stats,
            refused=cited_sources == set(), cited_sources=sorted(cited_sources),
        ))

    print(paint(f"\n[5/5] multi-turn: {len(sequences)} sequences ...", BOLD))
    passed_sequences = 0
    for sequence in sequences:
        history = []
        every_turn_cited = True
        print(f"      -- {sequence['name']}")
        for turn in sequence["turns"]:
            question = turn["question"]
            expected = turn["expected_source"]
            retrieval_checks += 1
            retrieved, embed_seconds, search_seconds = retrieval_hit(index, question, expected)
            if retrieved:
                retrieval_hits += 1
            answer, cited_sources, stats = ask(client, question, history)
            ttfts.append(stats["ttft_s"])
            speeds.append(stats["tok_s"])
            cited = expected in cited_sources
            if not cited:
                every_turn_cited = False
            status = paint("ok  ", GREEN) if cited else paint("MISS", RED)
            detail = "" if cited else f"  (cited {sorted(cited_sources)}, answer: {answer[:90]!r})"
            ret_flag = paint("ok  ", GREEN) if retrieved else paint("MISS", RED)
            print(f"      {status} cite {expected:<20} ret={ret_flag} "
                  f"history={len(history)//2} turns  {question!r}{detail}")
            if metrics_enabled:
                print_query_metrics(question, embed_seconds, search_seconds, stats)
            records.append(make_record(
                "multi_turn", question, stats,
                sequence=sequence["name"], history_turns=len(history) // 2,
                expected_source=expected, retrieved=retrieved, cited=cited,
                cited_sources=sorted(cited_sources),
                embed_ms=round(embed_seconds * 1000, 1),
                search_ms=round(search_seconds * 1000, 2),
            ))
            # Carry the model's ACTUAL answer forward — an uncited answer in
            # history is the suspected drift mechanism, so never substitute
            # a canned one.
            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": answer})
        if every_turn_cited:
            passed_sequences += 1

    rates = {
        "retrieval": [retrieval_hits, retrieval_checks],
        "citation": [cited_correctly, len(corpus_questions)],
        "refusal": [refused, len(refusal_questions)],
        "multi_turn": [passed_sequences, len(sequences)],
    }
    failing = (
        (retrieval_checks - retrieval_hits)
        + (len(corpus_questions) - cited_correctly)
        + (len(refusal_questions) - refused)
        + (len(sequences) - passed_sequences)
    )
    total_requests = len(ttfts)

    print(paint(f"\n=== EVAL REPORT ({data_dir.name}, {total_requests} requests) ===", BOLD))
    print(f"retrieval hit-rate: {paint_rate(retrieval_hits, retrieval_checks)} "
          f"({100 * retrieval_hits / retrieval_checks:.0f}%)")
    print(f"citation-rate:      {paint_rate(cited_correctly, len(corpus_questions))} "
          f"({100 * cited_correctly / len(corpus_questions):.0f}%)")
    print(f"refusal-rate:       {paint_rate(refused, len(refusal_questions))} "
          f"({100 * refused / len(refusal_questions):.0f}%)")
    print(f"multi-turn:         {paint_rate(passed_sequences, len(sequences))} sequences")
    print(f"TTFT avg:           {sum(ttfts) / total_requests:.2f}s   "
          f"tok/s avg: {sum(speeds) / total_requests:.1f}")

    # baseline.json = the accepted rates, committed next to eval.json and
    # updated by hand when a change is accepted. Informational only: the
    # exit code stays tied to the absolute checks above.
    baseline_path = data_dir / "baseline.json"
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        differences = []
        for name, [passed, total] in rates.items():
            if baseline.get(name) != [passed, total]:
                base_passed, base_total = baseline.get(name, [0, 0])
                color = GREEN if passed > base_passed else RED
                differences.append(paint(
                    f"{name} {base_passed}/{base_total} -> {passed}/{total}", color
                ))
        if differences:
            print("vs baseline:        " + ",  ".join(differences))
        else:
            print("vs baseline:        no change")

    config_snapshot = {}
    for key in CONFIG_KEYS:
        config_snapshot[key] = getattr(config, key)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / f"{data_dir.name}-{datetime.now():%Y%m%d-%H%M%S}.json"
    result_path.write_text(json.dumps({
        "dataset": data_dir.name,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "config": config_snapshot,
        "rates": rates,
        "ttft_avg_s": round(sum(ttfts) / total_requests, 3),
        "tok_s_avg": round(sum(speeds) / total_requests, 1),
        "failing_checks": failing,
        "questions": records,
    }, indent=2), encoding="utf-8")
    print(f"run saved:          {result_path}")

    if failing == 0:
        print(paint("EVAL GREEN", GREEN))
    else:
        print(paint(f"EVAL RED ({failing} failing checks)", RED))
    sys.exit(0 if failing == 0 else 1)


if __name__ == "__main__":
    run()
