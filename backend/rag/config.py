"""All tunable knobs, each overridable by an env var of the same name."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent  # backend/


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


MODEL = os.getenv("MODEL", "llama3.2:3b")  # chat model — 3B quantized, usable on CPU
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")  # local embedding model
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

NUM_CTX = _int("NUM_CTX", 6144)  # hard ceiling: "6K" = 6 × 1024, passed to Ollama's num_ctx
ANSWER_RESERVE = _int("ANSWER_RESERVE", 1024)  # held back for the reply (num_predict)
SAFETY_FRAC = float(os.getenv("SAFETY_FRAC", 0.10))  # input held back for tokenizer drift + template
CONTEXT_BUDGET = _int("CONTEXT_BUDGET", 3000)  # max tokens of retrieved chunks in the prompt
TOP_K = _int("TOP_K", 6)  # chunks retrieved per query (6 × 400 fits CONTEXT_BUDGET)

CHUNK_TOKENS = _int("CHUNK_TOKENS", 400)  # target chunk size at ingest
CHUNK_OVERLAP = _int("CHUNK_OVERLAP", 50)  # overlap between adjacent chunks

DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data" / "sample"))  # ingest source (CLI arg overrides)
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", BASE_DIR / "storage"))  # index.npz + chunks.jsonl

# Derived — the input side of the window:
INPUT_BUDGET = int((NUM_CTX - ANSWER_RESERVE) * (1 - SAFETY_FRAC))  # ≈ 4608
