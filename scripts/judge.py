"""Grade a saved eval run's answers with a local judge model (LLM-as-judge).

Run from backend/:   uv run python ../scripts/judge.py [run_json]
Defaults to the newest run in evals/results/. Report-only: eval.py's rates
and exit codes are untouched; this adds the dimension they can't see —
whether the ANSWER TEXT is actually correct, not just whether the right
file was cited.

The judge is config.JUDGE_MODEL (default gemma4:latest — the biggest local
model pulled, and a different family from the answering model so it isn't
grading its own sibling). Free and fully local, same as the serving path;
the 6K ceiling doesn't apply because judging is dev tooling, not serving.

Each corpus/multi-turn record is judged against its reference_answer on two
axes (the useful part of Ragas' faithfulness idea, without the framework):
  verdict            correct | partial | incorrect
  self_contradictory does the answer contradict itself? (the "garbled
                     grounding" failure mode — e.g. "off-leash only on a
                     leash-only trail")

One judge call per question — small local models grade one item reliably
but mangle big batch outputs — with the reply constrained to a JSON schema
via Ollama structured outputs, so parsing never depends on model manners.

Output: summary table on stdout + <run-name>-judge.json next to the run.
Needs a run produced after eval.py started saving answer text; older runs
are reported as unjudgeable.
"""
import json
import sys
from pathlib import Path

# judge.py lives in scripts/; the app package lives in backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from rag import config, llm  # noqa: E402  (path setup must come first)

RESULTS_DIR = Path(__file__).resolve().parents[1] / "evals" / "results"

JUDGE_PROMPT = """\
You are grading one answer from a small local RAG model against a reference
answer written by the corpus author.

Judge ONLY factual agreement with the reference answer:
  "correct"   — states the same facts; wording may differ
  "partial"   — some facts right, but incomplete or partly wrong
  "incorrect" — wrong, unsupported, or an unnecessary refusal

Separately, set self_contradictory to true when the answer contradicts
ITSELF (asserts a thing and its opposite), regardless of correctness.
Give a one-sentence reason.

question: {question}
reference answer: {reference_answer}
model answer: {answer}
"""

# Ollama structured-outputs schema: the judge reply is forced into this shape
VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["correct", "partial", "incorrect"]},
        "self_contradictory": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "self_contradictory", "reason"],
}


def newest_run_path():
    candidates = []
    for path in RESULTS_DIR.glob("*.json"):
        # judge output files live next to run files; never judge a judge file
        if not path.name.endswith("-judge.json"):
            candidates.append(path)
    if not candidates:
        sys.exit(f"no run files in {RESULTS_DIR} — run eval.py first")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def judgeable_records(run):
    """(record_index, record) pairs the judge can grade: answered questions
    that have a reference answer. Refusal questions are skipped — eval.py
    already measures those exactly."""
    pairs = []
    for record_index, record in enumerate(run["questions"]):
        if record["phase"] not in ("corpus", "multi_turn"):
            continue
        if record.get("answer") and record.get("reference_answer"):
            pairs.append((record_index, record))
    return pairs


def main():
    if len(sys.argv) > 1:
        run_path = Path(sys.argv[1])
    else:
        run_path = newest_run_path()
    run = json.loads(run_path.read_text(encoding="utf-8"))

    pairs = judgeable_records(run)
    if not pairs:
        sys.exit(
            f"{run_path.name} has no records with saved answer text — "
            "re-run eval.py (older runs didn't save answers)"
        )

    print(f"judging {len(pairs)} answers from {run_path.name} "
          f"with {config.JUDGE_MODEL} ...")

    # tally per verdict and per question label; keep failures for the report
    verdict_counts = {"correct": 0, "partial": 0, "incorrect": 0}
    counts_by_label = {}
    contradictions = 0
    failures = []
    judgements = []
    for item_number, (record_index, record) in enumerate(pairs):
        prompt = JUDGE_PROMPT.format(
            question=record["question"],
            reference_answer=record["reference_answer"],
            answer=record["answer"],
        )
        judgement = json.loads(llm.judge(prompt, VERDICT_SCHEMA))
        judgement["record_index"] = record_index
        judgements.append(judgement)

        verdict = judgement["verdict"]
        verdict_counts[verdict] += 1
        label = record.get("label") or "unlabeled"
        tally = counts_by_label.setdefault(label, {"correct": 0, "total": 0})
        tally["total"] += 1
        if verdict == "correct":
            tally["correct"] += 1
        if judgement["self_contradictory"]:
            contradictions += 1
        if verdict != "correct" or judgement["self_contradictory"]:
            failures.append((record, judgement))
        print(f"  [{item_number + 1}/{len(pairs)}] {verdict:<10} {record['question']!r}")

    total = len(pairs)
    print(f"\n=== JUDGE REPORT ({run_path.name}, judge={config.JUDGE_MODEL}) ===")
    print(f"answer-correct:     {verdict_counts['correct']}/{total} "
          f"({100 * verdict_counts['correct'] / total:.0f}%)   "
          f"partial: {verdict_counts['partial']}   "
          f"incorrect: {verdict_counts['incorrect']}")
    for label in sorted(counts_by_label):
        tally = counts_by_label[label]
        print(f"    - {label + ':':<22}{tally['correct']}/{tally['total']}")
    print(f"self-contradictory: {contradictions}/{total}")
    if failures:
        print("\nnot fully correct:")
        for record, judgement in failures:
            flags = judgement["verdict"]
            if judgement["self_contradictory"]:
                flags += ", self-contradictory"
            print(f"  [{flags}] {record['question']!r}")
            print(f"      {judgement['reason']}")

    judge_path = run_path.with_name(run_path.stem + "-judge.json")
    judge_path.write_text(json.dumps({
        "run": run_path.name,
        "judge_model": config.JUDGE_MODEL,
        "answer_correct": [verdict_counts["correct"], total],
        "verdicts": verdict_counts,
        "self_contradictory": contradictions,
        "by_label": counts_by_label,
        "judgements": judgements,
    }, indent=2), encoding="utf-8")
    print(f"\njudge saved:        {judge_path}")


if __name__ == "__main__":
    main()
