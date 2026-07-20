"""Persist/load the index and hybrid top_k (cosine + BM25, rank-fused).

storage/index.npz holds the L2-normalized vector matrix; storage/chunks.jsonl
holds chunk dicts, row-aligned to the matrix. BM25 statistics are rebuilt
from the chunk texts at load time — deterministic, so nothing extra is
persisted. Brute-force over a handful of files is instant; no vector DB
until the corpus is 100x bigger.
"""
import json
import math
import re
from pathlib import Path

import numpy as np

from rag import config


def _tokenize(text):
    # \w+ = runs of letters/digits; lowercased so query and chunk tokens match
    return re.findall(r"\w+", text.lower())


class Store:
    """The loaded index: vector matrix + chunk metadata, row-aligned."""

    def __init__(self, vectors, chunks):
        assert len(vectors) == len(chunks), "matrix and metadata out of alignment"
        self.vectors = vectors  # (n, dim) float32, L2-normalized
        self.chunks = chunks    # list[dict], row-aligned

        # BM25 statistics, built once from the chunk texts.
        self._term_counts = []  # per chunk: {token: occurrences}
        for chunk in chunks:
            counts = {}
            for token in _tokenize(chunk["text"]):
                counts[token] = counts.get(token, 0) + 1
            self._term_counts.append(counts)
        self._chunk_lens = [sum(counts.values()) for counts in self._term_counts]
        if chunks:
            self._avg_len = sum(self._chunk_lens) / len(chunks)
        else:
            self._avg_len = 0.0
        chunks_with_term = {}  # token -> number of chunks containing it
        for counts in self._term_counts:
            for token in counts:
                chunks_with_term[token] = chunks_with_term.get(token, 0) + 1
        self._idf = {}
        for token, chunk_count in chunks_with_term.items():
            self._idf[token] = math.log(
                (len(chunks) - chunk_count + 0.5) / (chunk_count + 0.5) + 1.0
            )

    def _bm25_scores(self, query_text):
        """One BM25 score per chunk row for the query's tokens."""
        scores = np.zeros(len(self.chunks), dtype=np.float32)
        for token in _tokenize(query_text):
            idf = self._idf.get(token)
            if idf is None:
                continue  # token appears in no chunk
            for row, counts in enumerate(self._term_counts):
                occurrences = counts.get(token, 0)
                if occurrences == 0:
                    continue
                length_norm = 1 - config.BM25_B + config.BM25_B * (
                    self._chunk_lens[row] / self._avg_len
                )
                scores[row] += idf * (occurrences * (config.BM25_K1 + 1)) / (
                    occurrences + config.BM25_K1 * length_norm
                )
        return scores

    def top_k(self, query_vec, query_text=None, k=None):
        """Best-matching chunks, best first.

        query_vec is normalized (llm.embed) -> dot product IS cosine
        similarity. With query_text, the cosine ranking is fused with a BM25
        ranking by reciprocal rank (score = sum of 1/(RRF_K + rank)); BM25
        only votes for chunks it actually matched, so a query with no rare
        tokens degrades gracefully to the cosine order. Without query_text,
        pure cosine (kept for callers that have no text, and for tests).
        The reported "score" stays the cosine similarity either way — it is
        the observable the logs and REPL have always shown.
        """
        if k is None:
            k = config.TOP_K
        sims = self.vectors @ query_vec      # one cosine score per chunk row
        best_first = np.argsort(sims)[::-1]  # argsort is ascending; reverse it

        if query_text is not None:
            fused = np.zeros(len(self.chunks), dtype=np.float32)
            cosine_position = {}
            for position, row in enumerate(best_first):
                fused[row] += 1.0 / (config.RRF_K + position + 1)
                cosine_position[row] = position
            bm25 = self._bm25_scores(query_text)
            bm25_order = np.argsort(bm25)[::-1]
            for position, row in enumerate(bm25_order):
                if bm25[row] <= 0.0:
                    break  # rows below matched nothing; they get no BM25 vote
                fused[row] += 1.0 / (config.RRF_K + position + 1)
            # equal fusion scores fall back to the cosine order, so a query
            # BM25 has no opinion about cannot reshuffle the semantic ranking
            best_first = sorted(
                range(len(self.chunks)),
                key=lambda row: (-fused[row], cosine_position[row]),
            )

        results = []
        slots_used = {}  # source file -> chunks already selected
        for row in best_first:
            if len(results) == k:
                break
            source = self.chunks[row]["source"]
            if config.TOP_K_PER_FILE and slots_used.get(source, 0) >= config.TOP_K_PER_FILE:
                continue  # this file has enough slots; let the next-ranked file in
            slots_used[source] = slots_used.get(source, 0) + 1
            hit = dict(self.chunks[row])  # copy so the stored chunk stays unmodified
            hit["score"] = float(sims[row])
            results.append(hit)
        return results


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
