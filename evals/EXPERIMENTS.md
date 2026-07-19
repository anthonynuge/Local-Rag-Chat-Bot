# Experiment log

One entry per experiment, newest first. Numbers come from `scripts/eval.py`
(citation/retrieval/refusal rates) and `scripts/judge.py` (answer-correctness,
graded by a local judge model against the reference answers in `eval.json`).
Raw run JSONs live in `evals/results/` (gitignored); the committed accepted
rates live in `<data_dir>/baseline.json`.

---

## 2026-07-19 — Full eval + judge after the refusal hardening + condenser. RED

The delayed verification run for the two changes shipped without a full
eval (famous-fact refusal hardening in CITE_REMINDER, and the follow-up
condenser). Tests 25/25. Eval vs the last full run:

| | before | after |
|---|---|---|
| retrieval | 46/47 | 46/47 |
| citation | 33/35 | 30/35 |
| refusal | 6/8 | 10/12 (set grew to 12) |
| multi-turn sequences | 3/4 | 1/4 |
| answer-correct (judge) | 39/47 (83%) | 33/47 (70%) |

**What the hardening bought:** famous facts (World Cup, capital of China)
and task requests now refuse cleanly, plus one trap question fixed.

**What it cost:** five questions that used to be answered now refuse with
the right chunk in the prompt — "Is there public WiFi anywhere in the
park?" (a stated "no" in the corpus), the Shoulder Camp two-parter, the
WiFi-password trick, and two multi-turn third turns (food storage,
helicopter weather). Retrieval still hits on all five; the model refuses
at generation. The new "even when you are certain from your own knowledge,
do not answer" clause is over-applying: it also swallows answers the
context does state, especially negative ones ("no WiFi") and applied ones.
One refusal regressed in format (lost-and-found phone: explanation +
citation after the exact phrase).

**Condenser verdict:** clean as far as the eval can see. The one condensed
turn that failed still retrieved the right chunk; its refusal happened at
generation, same as the un-condensed failures. Not the condenser's doing.

**Next:** soften the certainty clause so it only blocks answers that are
NOT in the context — e.g. add "if the context does state the answer,
including when the answer is 'no' or 'none', answer and cite it" — and
re-run these five plus the 12 refusal probes before accepting. Baseline
NOT updated (run is red).

## 2026-07-19 — Reasoning prompts for date questions. NOT ADOPTED

**Question:** the model recites rules fine ("what are the hours") but fails
to apply them to a specific date ("open on a Tuesday in January?") even with
the right chunk in the prompt. Can a prompt that forces step-by-step
reasoning fix that? Tested with env overrides only, no code. Four probes
(one easy control + the three known failures), chat.py, qwen2.5:7b,
ANSWER_RESERVE=1536.

**Results:**

| prompt | score | what happened |
|---|---|---|
| current prompt (baseline) | 2/4 | Thanksgiving refused; kiosk refused with a citation marker it shouldn't have |
| think step-by-step in `<think>` tags | 1/4 | reasoned correctly, refused anyway — wrote "6 a.m. is before staffed hours" then answered "I don't have that information." |
| same, plus "a conclusion you derived counts as answered" | 1.5/4 | gave the right answer, then added the refusal sentence right after it |
| quote the evidence first, then a one-line conclusion (no think tags) | 2/4 | Jan Tuesday fixed, but kiosk became confidently wrong: said 6 a.m. is inside 07:00–19:00 |

**Why it failed:** the model isn't missing reasoning — it reasons correctly
and then won't commit to the conclusion. Each prompt change just moved the
problem: the think versions refuse after working out the answer, and the
version that forces an answer commits to a wrong time comparison. A wrong
answer is worse than a refusal here. Thanksgiving failed in every version.

**Takeaway:** prompts won't fix this, as tasks.md predicted. But the correct
answer does show up inside the reasoning text — so a second pass that checks
the draft (or a bigger model) should be able to recover it. Refusal probes
were not re-run and no parsing code was built, since nothing won.

## 2026-07-19 — Generalization check (sample-1) + heading-path chunking. KEPT

**Generalization first:** the full current stack (hybrid retrieval, prompt
v2, paragraph chunking) run on the sample-1 corpus (company docs — PTO,
runbook, security policy; unseen since the old stack): retrieval 20/21 ->
21/21, citation 11/12 -> 12/12, multi-turn 3/3. The stack is not overfit
to sample-v3 — it *improved* a corpus it was never tuned on. One refusal
regressed (3B half-answers a competitors question); the prompt ladder was
only ever tuned on qwen.

**Heading-path chunking:** .md `heading` is now the full breadcrumb
("Title > Section > Sub") via a heading stack — every window of a long
section inherits its path, and pack()/citations show it with zero code
changes. Ingest embeds each chunk with a `file-stem — path` prefix
(embed-side only; stored text stays clean for BM25 + prompt), which also
gives heading-less .txt paragraphs their file as context.

**Measured:** sample-1 identical (already at ceiling, change harmless);
sample-v3 misses 4 -> 3 — the "60 meters" wrong-file citation fixed, one
churn-band wobble traded in, the two known stubborn failures unchanged
(Sable overnight BM25 flooding; multi-turn fine attribution). Kept:
structural fix for windowed-section anonymity, load-bearing for any
deep-hierarchy corpus (handbooks), cost zero.

## 2026-07-19 — difflib query typo-repair: built, measured, REVERTED

**Idea:** replace query words absent from the corpus vocabulary with their
closest corpus word (difflib, deterministic, retrieval-side only) to fix
the "typos embed poorly" issue from the Phase 10.5 list.

**Why it died — two measurements:**
1. "Not in vocabulary" cannot distinguish a typo from a legitimately absent
   word at this corpus size. The repair corrupted 8/55 clean eval questions
   ("earn"→"ear", "died"→"did", "tall"→"stall", "tour"→"detour") — and the
   worst victims were refusal traps, whose words are SUPPOSED to be absent.
2. The planned rescue (only repair when retrieval confidence is low) is
   impossible: typo'd queries score 0.54–0.70, inside the answerable range
   (min 0.532), and refusal questions reach 0.778 — the distributions
   overlap; no floor separates them. Bonus finding: nomic-embed is already
   substantially typo-tolerant, so the 3B-era issue was probably mostly the
   old model's refusal-happiness, not retrieval.

**Lesson:** verify a "safe deterministic" fix against the eval set before
wiring it — this one failed its no-op check in five minutes and never cost
an eval run. Revisit only with typo probes in a grown eval set, and then as
a low-score-triggered small-LLM rephrase, not vocab repair.

**End-to-end follow-up (same day):** 6 typo'd questions ("mosoe",
"vehical", "dailyy", "trial" for trail...) through the live pipeline:
6/6 correct facts + correct citations on llama3.2:3b AND qwen2.5:7b.
The Phase 10.5 "malformed questions" issue is resolved by the current
stack with no typo-specific code: typo-tolerant embeddings + BM25's
graceful no-vote degradation + prompt v2's refusal ladder. The issue was
the OLD stack (3B-era eager refusals), not typos per se.

## 2026-07-18 — Prompt v2: refusal exact-reply + premise-correction ladder. KEPT

**Change (config.py defaults):** SYSTEM_PROMPT gains a premise-correction
line; CITE_REMINDER became an ordered decision ladder — (1) premise
contradicted -> correct it and cite, (2) answer present -> answer and cite,
(3) neither -> reply with exactly "I don't have that information.", no
markers, nothing else. v1 (two independent lines) failed: the strict
refusal rule sat nearest the question and beat the distant premise rule —
trick questions refused instead of correcting (6/6 -> 2/6 cited). Ordering
the rules in ONE place fixed the collision.

**Measured (qwen2.5:7b, hybrid retrieval):** answer-correct 34/47 -> 39/47
(83%, day best); partials 11 -> 3; cross-source judged 5/5; refusal format
0/8 -> 6/8; failing checks 11 -> 6. Also surfaced one more either-or
ground-truth fix (Sable Spring is in the FAQ too).

**Still open:** trick questions cite the correcting file (6/6) but
soft-pedal the correction (judged 1/6) — the model points at the truth
without committing to it. Two refusal stragglers (one explains after the
exact phrase, one trap answered). One genuine mis-attribution (60 m cited
to permits; the fact lives only in wildlife-safety).

## 2026-07-18 — Hybrid retrieval: BM25 + cosine, reciprocal-rank fusion. KEPT

**Change:** `store.top_k(query_vec, query_text)` fuses the cosine ranking
with a BM25 ranking via RRF (RRF_K=60); BM25 votes only for chunks it
matched, ties fall back to cosine order. Stats built from chunk text at
load — ingest untouched, fully deterministic, microseconds per query.
Motivation: the remaining retrieval misses were rare-exact-token queries
("fall rut" rank 5, "Shoulder Camp" rank 7) — embeddings blur short queries
whose one distinctive token appears in exactly one file.

**Offline sweep (deterministic, no LLM):** hit@1 38->39, hit@4 45->46;
fall rut rank 5->1, Shoulder Camp 7->3. One casualty: the long Sable
overnight cross-source query fell 3->12 — BM25's many medium-rare tokens
("Sable", "Ridge", "trail") flood the ranking with trail-guide chunks,
pushing out the wildlife-safety chunk the pair needs.

**End-to-end (qwen2.5:7b):** citation 32/35 -> 33/35 (94%, day high),
multi-turn 1/4 -> 4/4 (first full pass), factual 24/24, trick 6/6.
Answer-correct 37/47 -> 34/47: -1 systematic (Sable overnight, the
predicted casualty), -2 the usual chunk-mix churn. Systematic ledger
+2/-1 -> kept per the pre-registered decision rule.

**Follow-up queued (behind eval-set growth):** rare-token gating so long
queries don't dilute BM25's vote; would recover the Sable overnight break.

## 2026-07-18 — Control run: 3B on paragraph chunking + fair scoring

Re-ran the default llama3.2:3b on the fixed chunks and either-or scoring.
(Timings in this run are CPU-contaminated — the model was resident with
num_gpu=0 from the floor check; rates are placement-independent and stand.)

| same chunks, fair scoring | 3B | 7B |
|---|---|---|
| citation-rate | 30/35 (86%) | 32/35 (91%) |
| answer-correct | 36/47 (77%) | 37/47 (79%) |
| flat-wrong answers | 6 (+1 self-contradiction) | 1 |
| trick handled | 1/6 | 3/6 |
| refusal format | 7/8 | 0/8 (cites while refusing) |
| multi-turn sequences | 3/4 | 1/4 |

**Chunking was the dominant lever:** it moved 3B from 24->30 citations and
72->77% correct; the headline model gap shrank from 9 points to 1. The real
model difference is failure TYPE: 3B produces confident misinformation
(helicopter rules reversed, a self-contradictory shuttle answer); 7B
produces omissions. Recommendation unchanged — 7B default, 3B documented as
the CPU-first option — but the margin is honest now, not lopsided.

## 2026-07-18 — CPU-only floor check: 3B vs 7B (NUM_GPU=0, ~1.8K-token prompt)

| | llama3.2:3b | qwen2.5:7b |
|---|---|---|
| TTFT warm | ~5.4s | ~11.4s |
| TTFT cold (incl. load) | 13.6s | 25.4s |
| generation | 47 tok/s | 24 tok/s |
| RAM | ~2.5 GB | ~5.5 GB |

Quality is placement-independent; only speed changes. 7B on CPU = usable but
patient: streaming runs at 4-5x reading speed once it starts, the cost is
~11s of silence per question (prompt processing, scales with prompt size).
Feeds the adoption decision: 7B default for quality, 3B stays documented as
the CPU-first option via MODEL env — the llm-seam swap the spec designed for.

## 2026-07-18 — TOP_K=4 tested, kept 6; eval gains either-or source groups

**Rank sweep first (no LLM):** for all 47 questions, the rank at which every
expected file appears in the cosine ranking. hit@2 = 42/47, hit@4 = 44/47,
hit@6 = 45/47 — slots 5-6 buy exactly one question; the two k=6 misses sit
at ranks 7 and 9 (elliptical follow-ups), unreachable at any sane k.

**Ground-truth fix found during scoring:** the corpus states several facts
in two files (summit height, filming fee, feeding fine, High Country
elevation...), but eval.json accepted exactly one source — runs citing the
valid alternate were penalized. eval.json entries now use either-or groups
(`[["a.md", "faq.txt"]]` = either counts); eval.py `covers()` scores them.
Both runs rescored offline from saved `cited_sources` — no re-runs needed.

**TOP_K=4 vs 6 (both qwen2.5:7b, fair scoring):** citations 33/35 vs 32/35,
multi-turn turns 10/12 vs 9/12, but answer-correct 35/47 (74%) vs 37/47
(79%). k=4 fixed the Summit Route distractor flip exactly as predicted, then
created two new flips (dog off-leash regressed to wrong, fall rut lost its
rank-5 chunk and refused).

**Kept TOP_K=6.** Every retrieval knob flips 3-5 borderline questions; at 47
questions that churn (±2) exceeds the effect being chased. Lesson: grow the
eval set before tuning retrieval knobs further. TOP_K=5 (same coverage as 6,
one less distractor) left untested for the same reason.

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
