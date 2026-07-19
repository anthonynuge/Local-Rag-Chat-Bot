"""Interactive debug chat: ask one question, see the whole pipeline.

Run from backend/:   uv run python ../scripts/chat.py [data_dir]

Every turn shows the retrieved chunks (score, packed or dropped, full text),
the answer streaming live, which sources the [n] markers resolved to, and
the same metrics block as eval --metrics. Multi-turn by default: each answer
joins the history, exactly like the frontend would send it.

Commands:   /prompt   print the exact messages sent to the model last turn
            /new      clear the conversation history
            /quit     exit (Ctrl+C works too)

Passing a data_dir re-ingests it first; with no argument the existing index
in backend/storage/ is used as-is (whatever was ingested last).

Needs Ollama running with both models pulled.
"""
import logging
import re
import sys
import textwrap
import time
from pathlib import Path

# chat.py lives in scripts/; the app package lives in backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from rag import budget, config, ingest, llm, store  # noqa: E402
from rag.chunk import n_tokens                      # noqa: E402
# display helpers shared with the eval harness (same scripts/ dir)
from eval import BOLD, DIM, GREEN, RED, paint, print_query_metrics  # noqa: E402

# the Ollama client logs one httpx INFO line per request — noise in a REPL
logging.getLogger("httpx").setLevel(logging.WARNING)


def show_chunks(ranked, packed_count):
    """The retrieval check: every candidate, its score, and its full text.

    pack() keeps a strict rank-order prefix, so the first packed_count
    chunks made it into the prompt and the rest were dropped by budget."""
    print(paint(f"\nretrieved chunks ({len(ranked)} candidates, {packed_count} packed):", BOLD))
    for rank, chunk in enumerate(ranked, start=1):
        if rank <= packed_count:
            fate = paint("packed ", GREEN)
        else:
            fate = paint("dropped", RED)
        heading = chunk["heading"] or "(no heading)"
        print(f"  [{rank}] {fate} score={chunk['score']:.3f} "
              f"{chunk['source']} — {heading}  ({n_tokens(chunk['text'])} tokens)")
        for line in textwrap.wrap(chunk["text"], width=96):
            print(paint(f"        {line}", DIM))


def show_prompt(messages):
    """Dump the exact messages handed to llm.chat(), role by role."""
    total = 0
    for message in messages:
        total += n_tokens(message["content"])
    print(paint(f"\nprompt sent to the model ({len(messages)} messages, ~{total:,} tokens):", BOLD))
    for message in messages:
        print(paint(f"--- {message['role']} ---", BOLD))
        print(message["content"])


def turn(index, question, history):
    """One full pipeline pass, everything printed. Returns (answer, messages)."""
    started = time.perf_counter()
    query_vec = llm.embed([question])[0]
    embed_seconds = time.perf_counter() - started

    started = time.perf_counter()
    ranked = index.top_k(query_vec, question)
    search_seconds = time.perf_counter() - started

    messages, citations, report = budget.pack(
        config.SYSTEM_PROMPT, question, ranked, history
    )
    show_chunks(ranked, len(citations))
    print(paint(
        f"\nprompt: system {report['system']:,} + context {report['context']:,} "
        f"+ history {report['history']:,} + question {report['question']:,} tokens "
        f"(budget {report['input_budget']:,}) — /prompt shows the full text", DIM,
    ))

    print(paint("\nanswer:", BOLD))
    request_started = time.perf_counter()
    first_token_at = None
    deltas = []
    final = None
    for chunk in llm.chat(messages):
        delta = chunk["message"]["content"]
        if delta:
            if first_token_at is None:
                first_token_at = time.perf_counter()
            deltas.append(delta)
            print(delta, end="", flush=True)
        final = chunk
    print()
    answer = "".join(deltas)
    total_seconds = time.perf_counter() - request_started

    # Which sources the [n] markers resolved to — same regex as the API
    cited_ids = {int(number) for number in re.findall(r"\[(\d+)\]", answer)}
    resolved = [c for c in citations if c["id"] in cited_ids]
    if resolved:
        print(paint("\ncited:", BOLD))
        for citation in resolved:
            heading = citation["heading"] or "(no heading)"
            print(f"  [{citation['id']}] {citation['source']} — {heading}")
    else:
        print(paint("\ncited: nothing", BOLD))
    ghosts = cited_ids - {c["id"] for c in citations}
    if ghosts:  # a marker pointing at a block that was never packed
        print(paint(f"  markers with no matching block: {sorted(ghosts)}", RED))

    generation_seconds = final.get("eval_duration", 0) / 1e9
    if generation_seconds > 0:
        tok_s = final["eval_count"] / generation_seconds
    else:
        tok_s = 0.0
    stats = {
        # real streaming here (no TestClient buffering), so TTFT is the
        # honest wall-clock wait for the first token
        "ttft_s": (first_token_at - request_started) if first_token_at else 0.0,
        "tok_s": tok_s,
        "total_s": total_seconds,
        "prompt_tokens": final["prompt_eval_count"],
        "context_tokens": report["context"],
    }
    print()
    print_query_metrics(question, embed_seconds, search_seconds, stats)
    return answer, messages


def run():
    if len(sys.argv) > 1:
        data_dir = Path(sys.argv[1])
        print(paint(f"ingest: rebuilding index from {data_dir} ...", BOLD))
        ingest.main(data_dir)

    index = store.load()
    sources = set()
    for chunk in index.chunks:
        sources.add(chunk["source"])
    print(paint(
        f"index: {len(index.chunks)} chunks from {len(sources)} sources — "
        f"{', '.join(sorted(sources))}", BOLD,
    ))
    print("ask a question; /prompt /new /quit\n")

    history = []
    last_messages = None
    while True:
        try:
            line = input(paint(f"[{len(history) // 2} turns] > ", BOLD)).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return
        if not line:
            continue
        if line == "/quit":
            return
        if line == "/new":
            history = []
            print("history cleared\n")
            continue
        if line == "/prompt":
            if last_messages is None:
                print("nothing sent yet\n")
            else:
                show_prompt(last_messages)
                print()
            continue
        answer, last_messages = turn(index, line, history)
        history.append({"role": "user", "content": line})
        history.append({"role": "assistant", "content": answer})
        print()


if __name__ == "__main__":
    run()
