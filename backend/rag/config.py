"""All tunable knobs, each overridable by an env var of the same name."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent  # backend/


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


MODEL = os.getenv("MODEL", "qwen2.5:7b")  # chat model; MODEL=llama3.2:3b for the CPU-first fallback
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")  # local embedding model
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
TEMPERATURE = float(os.getenv("TEMPERATURE", 0.0))  # 0 = deterministic — grounded answers, repeatable smoke test
NUM_GPU = os.getenv("NUM_GPU")  # unset = Ollama auto-detects; "0" = force CPU (calibration pass)
# Dev-tooling only (scripts/judge.py): a bigger local model that grades eval
# answers. Never on the serving path, so the 6K ceiling doesn't apply to it.
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemma4:latest")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # "WARNING" silences the per-request trace

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "Answer ONLY using the numbered context below. Cite sources inline as [1], [2]. "
    "If the answer is not in the context, say you don't have that information — "
    "do not use outside knowledge. If the question assumes something the context "
    "contradicts, say so and correct it with a citation instead of answering as asked.",
)
# Rides with the current question (budget.pack). The system prompt sits at the
# top of an ever-growing prompt; a 3B model drops the cite format without a
# reminder near the generation point.
CITE_REMINDER = os.getenv(
    "CITE_REMINDER",
    "Every statement taken from the context MUST end with its inline citation "
    "marker, for example: \"The limit is three days [2].\" If the question "
    "assumes something the context contradicts, correct the assumption and "
    "cite the correcting source — that counts as an answer, not a refusal. "
    "Only when the context offers neither the answer nor a correction, reply "
    "with exactly: \"I don't have that information.\" — no citation markers, "
    "nothing else. This applies even when you are certain of the answer from "
    "your own knowledge (famous facts, general knowledge): if it is not in "
    "the numbered context, do not answer it and never attach a citation to it. "
    "Requests to perform a task — write a poem, solve math, produce code — are "
    "not questions about the context; give the same exact refusal.",
)

# Follow-up condensation (llm.condense_query): content-thin follow-ups like
# "are you sure" embed to junk, so retrieval never re-fetches the chunk the
# answer needs. When a query this short arrives mid-conversation, the chat
# model rewrites it into a standalone question first — retrieval-side only,
# the packed prompt still carries the user's literal words.
CONDENSER_MODEL = os.getenv("CONDENSER_MODEL", MODEL)  # same model by default: already resident, no VRAM swap
CONDENSE_MAX_WORDS = _int("CONDENSE_MAX_WORDS", 6)  # ponytail: word count as the content-thin test; a vocab check if it misfires
CONDENSE_PROMPT = os.getenv(
    "CONDENSE_PROMPT",
    "Rewrite the user's last message as one standalone question, using the "
    "conversation for context. Keep every specific detail. Reply with ONLY "
    "the rewritten question.",
)

NUM_CTX = _int("NUM_CTX", 6144)  # hard ceiling: "6K" = 6 × 1024, passed to Ollama's num_ctx
ANSWER_RESERVE = _int("ANSWER_RESERVE", 1024)  # held back for the reply (num_predict)
SAFETY_FRAC = float(os.getenv("SAFETY_FRAC", 0.10))  # input held back for tokenizer drift + template
CONTEXT_BUDGET = _int("CONTEXT_BUDGET", 3000)  # max tokens of retrieved chunks in the prompt
TOP_K = _int("TOP_K", 6)  # chunks retrieved per query (6 × 400 fits CONTEXT_BUDGET)

# Hybrid retrieval (store.top_k): cosine and BM25 rankings merged by
# reciprocal-rank fusion. Cosine carries meaning; BM25 carries rare exact
# tokens ("rut", "Sable 14") that short queries lean on and embeddings blur.
RRF_K = _int("RRF_K", 60)  # fusion constant; 60 is the standard from the RRF paper
BM25_K1 = float(os.getenv("BM25_K1", 1.5))  # term-frequency saturation
BM25_B = float(os.getenv("BM25_B", 0.75))  # document-length normalization

CHUNK_TOKENS = _int("CHUNK_TOKENS", 400)  # target chunk size at ingest
CHUNK_OVERLAP = _int("CHUNK_OVERLAP", 50)  # overlap between adjacent chunks

DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data" / "sample"))  # ingest source (CLI arg overrides)
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", BASE_DIR / "storage"))  # index.npz + chunks.jsonl

# Derived — the input side of the window:
INPUT_BUDGET = int((NUM_CTX - ANSWER_RESERVE) * (1 - SAFETY_FRAC))  # ≈ 4608
