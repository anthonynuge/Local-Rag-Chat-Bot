"""Persist/load the index and cosine top_k.

storage/index.npz holds the L2-normalized vector matrix; storage/chunks.jsonl
holds chunk dicts, row-aligned to the matrix. Brute-force cosine over a
handful of files is instant; no vector DB until the corpus is 100x bigger.
"""
import json
from pathlib import Path

import numpy as np

from rag import config


class Store:
    """The loaded index: vector matrix + chunk metadata, row-aligned.

    Retrieval (cosine top_k) lands here in Phase 5.
    """

    def __init__(self, vectors, chunks):
        assert len(vectors) == len(chunks), "matrix and metadata out of alignment"
        self.vectors = vectors  # (n, dim) float32, L2-normalized
        self.chunks = chunks    # list[dict], row-aligned


def save(vectors, chunks, storage_dir=None):
    """Write index.npz + chunks.jsonl to storage_dir (default STORAGE_DIR)."""
    storage = Path(storage_dir or config.STORAGE_DIR)
    storage.mkdir(parents=True, exist_ok=True)
    np.savez(storage / "index.npz", vectors=vectors)
    with open(storage / "chunks.jsonl", "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def load(storage_dir=None):
    """Read a saved index back into a Store; raises FileNotFoundError if not ingested yet."""
    storage = Path(storage_dir or config.STORAGE_DIR)
    vectors = np.load(storage / "index.npz")["vectors"]
    with open(storage / "chunks.jsonl", encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f]
    return Store(vectors, chunks)
