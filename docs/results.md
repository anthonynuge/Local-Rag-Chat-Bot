# Results — accuracy pass, 2026-07-18

One day of measured changes took the system from 69% to 94% citation
accuracy and from 72% to 83% judged answer correctness, with every change
validated by the eval harness before being kept. Full per-experiment
details: [evals/EXPERIMENTS.md](../evals/EXPERIMENTS.md). Method: build the
measuring instrument first (LLM-as-judge), then change one thing at a time.

## Metric trajectory

Model is llama3.2:3b until the swap; qwen2.5:7b after. "Answer-correct" is
graded by a local judge model (gemma4) against hand-written reference
answers — `correct` requires every fact including caveats.

| Change (in order)              | Citation | Answer-correct | Wrong answers |
|--------------------------------|----------|----------------|---------------|
| Starting point (3B)            | 24/35 (69%) | 32/47 (68%) | 11 |
| Corpus ground-truth fix        | 24/35       | 34/47 (72%) | 9  |
| Model swap → qwen2.5:7b        | 27/35 (77%) | 38/47 (81%) | 1  |
| Paragraph-aware .txt chunking  | 32/35 (91%) | 37/47 (79%) | 1  |
| Either-or citation scoring     | (fair ruler — rescored, no model change) | | |
| Hybrid retrieval (BM25 + RRF)  | 33/35 (94%) | 34/47 (72%)* | 2  |
| Prompt v2 (decision ladder)    | 33/35 (94%) | **39/47 (83%)** | 5** |

\* churn: ±2 questions flip on any retrieval change at this eval size; the
hybrid's systematic ledger was +2 fixes / −1 break.
\** the five are trick-question soft-pedals, not fabrications; the partial
count fell 11 → 3 in the same run.

Failing checks (eval's bottom line): **14 → 6**.

## What each change was

- **LLM-as-judge** (`scripts/judge.py`): a bigger local model (gemma4)
  grades every answer against its reference — the metric citation checks
  can't see. Built first so everything after was measured, not guessed.
- **Corpus fix**: the $175 feeding fine was referenced by two files but
  stated in neither's expected place — the model's "not in context" answers
  were faithful to a broken corpus. Lesson: audit the eval before
  optimizing against it.
- **Model swap**: 3B → 7B eliminated confident misinformation (reversed
  helicopter rules, self-contradictions): 9 wrong answers → 1. CPU floor
  measured: 24 tok/s generation, ~11 s first-token vs 5 s for the 3B.
- **Paragraph chunking**: `.txt` files now split at blank-line paragraph
  breaks, so FAQ question/answer pairs stay in one chunk. The single
  biggest citation lever (77% → 91%).
- **Either-or scoring**: facts the corpus states in two files accept either
  citation — removed false penalties the single-source ground truth caused.
- **Hybrid retrieval**: BM25 fused with cosine by reciprocal rank. Fixed
  the rare-exact-token misses ("fall rut", "Shoulder Camp") that embeddings
  blur; first run with all 4 multi-turn sequences passing.
- **Prompt v2**: one ordered decision ladder — correct a contradicted
  premise (cited) → answer (cited) → exact refusal, cite nothing. v1 as two
  separate rules failed because the rule nearest the question always won.

## Hybrid retrieval: processing cost

Measured on the 121-chunk sample-v3 index:

| Stage                         | Cosine only | Hybrid (BM25 + RRF) | Added |
|-------------------------------|-------------|---------------------|-------|
| Index load at boot (one-time) | ~3 ms       | 8.7 ms              | +5.6 ms (BM25 stats build) |
| Retrieval per query           | 6 µs        | 226 µs              | +220 µs |
| Share of a ~3 s chat response | —           | —                   | ~0.01% |

Nothing is persisted for BM25 — statistics rebuild deterministically from
chunk text at load. Ingest, the stored index format, and the 6K budget
math are untouched.

## Prompt change: example responses (same questions, before → after)

**Refusals stopped citing** (the spec requires refusal = zero citations;
the 7B model previously stapled markers onto every refusal):

> Q: How much does a Thornmere park ranger earn?
> before: `I don't have that information [1][2][3][4][5].`
> after:  `I don't have that information.`

> Q: Who won the 2018 FIFA World Cup?
> before: `I don't have that information [1][2][3][4][5].`
> after:  `I don't have that information.`

**Premise-corrections kept their citation and got more complete:**

> Q: Which backcountry campsite on the Sable Ridge Trail has a toilet?
> before: `Neither Sable Camp nor Shoulder Camp has a toilet of their own [2].`
> after:  `Neither Sable Camp nor Shoulder Camp has its own toilet [2]. Both
> camps require using pack-it-out or cathole standards for sanitation...`

**Honest regression, kept on the books** — one trick question got worse
(v0 answered it correctly; the ladder made the model over-cautious):

> Q: What's the senior discount on the annual pass?
> before: `There is no separate discounted tier for seniors at Thornmere [1].`
> after:  `I don't have that information. [1] mentions discounts for seniors...`

Net effect of the prompt change: answer-correct 34 → 39 of 47, refusal
format 0/8 → 6/8, partial answers 11 → 3, at the cost of trick-question
assertiveness (cited 6/6, but only 1/6 states the premise correction
head-on).

## Open items

- Trick questions: the model cites the correcting source but soft-pedals
  the correction — the main remaining quality gap (1/6 judged correct).
- Two refusal stragglers and two attribution errors (right answer, wrong
  file cited) — an attribution verifier is scoped if the class persists.
- One retrieval miss: long cross-source queries dilute BM25's vote
  (rare-token gating queued).
- **Eval-set growth is the gate for all further tuning** — at 47 questions,
  any retrieval change flips ±2 borderline questions, which is the same
  size as the effects being measured.
- Model default decision: qwen2.5:7b measured better on every quality axis;
  adopting it means updating spec G3's hardware claim alongside
  `config.MODEL`. The 3B stays one env var away for CPU-first setups.

## Reproduce

```bash
cd backend
uv run python ../scripts/eval.py ./data/thornmere   # rates + run JSON
uv run python ../scripts/judge.py                    # grade newest run
```
