# Experiment log

One entry per experiment, newest first. Numbers come from `scripts/eval.py`
(citation/retrieval/refusal rates) and `scripts/judge.py` (answer-correctness,
graded by a local judge model against the reference answers in `eval.json`).
Raw run JSONs live in `evals/results/` (gitignored); the committed accepted
rates live in `<data_dir>/baseline.json`.

---

## 2026-07-18 — Paragraph-aware .txt chunking

**Change:** `.txt` files split at blank-line paragraph breaks before
windowing (`chunk.py`), instead of sliding a 400-token window across the
whole file. No format sniffing — an FAQ's Q/A pair stays whole because it's
one paragraph, not because the code knows what an FAQ is. Both runs
qwen2.5:7b.

| | before | after |
|---|---|---|
| citation-rate | 27/35 (77%) | 32/35 (91%) |
| factual citations | 21/24 | 24/24 |
| trick citations | 3/6 | 6/6 |
| cross-source citations | 3/5 | 2/5 |
| retrieval | 46/47 | 45/47 |
| answer-correct (judge) | 38/47 (81%) | 37/47 (79%) |

**Kept.** Single-file citations perfect; the trout-limit retrieval miss
(the only one in the corpus set) is fixed. Cost: ~3x more small .txt chunks
compete for the fixed TOP_K=6 slots, so multi-file questions lost a little
retrieval/citation ground — that's the TOP_K / score-threshold experiment's
territory, queued next. Also logged: qwen padded the fall-rut answer with an
unsupported "50 meters" figure — its failure mode is embellishment, not
reversal.

## 2026-07-18 — Model swap: llama3.2:3b → qwen2.5:7b

**Change:** `MODEL=qwen2.5:7b`, nothing else. Run vs the post-corpus-fix 3B run.

| | llama3.2:3b | qwen2.5:7b |
|---|---|---|
| answer-correct (judge) | 34/47 (72%) | 38/47 (81%) |
| judged incorrect | 9 | 1 |
| citation-rate | 24/35 (69%) | 27/35 (77%) |
| refusal-rate | 7/8 | 0/8 (see below) |
| speed | 246 tok/s | 143 tok/s |

**What improved:** fact reversals eliminated (3B stated the helicopter weather
rules backwards, billed the free shuttle at $9, invented a Coldpine reservation
process — all correct on 7B). Unnecessary refusals 4 → 1.

**The remaining incorrect answer** (trout limit) is a retrieval miss — the
right file never reached top-k — not a generation failure. FAQ-aware `.txt`
chunking is the fix for that one.

**New problems it exposed, in fix-cheapness order:**
1. Refusal formatting: all 8 refusals were correct in content but carried
   citation markers ("We do not have that information [1][2]"), which the
   spec counts as failure. Prompt-wording fix.
2. Marker attribution: right answer, wrong file cited — now the dominant
   citation failure (shuttle frequency, feeding fine, helicopter, Shoulder
   Camp).
3. Trick questions: gives correct facts but doesn't call out the false
   premise (2/6); omits small caveats (8 partials vs 3B's 4).

**Decision:** pending — adopting 7B as default changes the hardware floor
(4.7 GB vs 2 GB) and contradicts spec G3's "3B answers the CPU question"
line, so config default + spec change together or not at all.

## 2026-07-18 — Corpus ground-truth fix: feeding-wildlife fine

**Change:** one sentence added to `wildlife-safety.txt` stating the $175 fine
and park-ban escalation. Found by auditing every eval reference answer against
the corpus: the fine lived only in `visitor-faq.txt`, while both
`ranger-operations.md` and the eval pointed at `wildlife-safety.txt` — the
model's "not in context" answers were faithful to a broken corpus.

| | before | after |
|---|---|---|
| answer-correct (judge) | 32/47 (68%) | 34/47 (72%) |
| judged incorrect | 11 | 9 |

**Lesson:** part of what looked like the 3B model's ceiling was wrong ground
truth. Audit the eval set before optimizing against it.

## 2026-07-18 — Judge baseline (pre-fix), llama3.2:3b

First graded run (`scripts/judge.py`, judge=gemma4:latest). Established that
citation-rate (69%) and answer-correctness (68%) track closely, but the
per-bucket story differs: trick-false-premise questions were far worse than
citation-rate suggested (1/6 truly handled vs 3/6 cited), and the graded
failures split into four buckets — unnecessary refusals (4), fact reversals
(5), omissions (4), false-premise acceptance (5/6). Self-contradiction flag
fired 0/47 — garbled answers read as confidently wrong, not self-contradicting.
