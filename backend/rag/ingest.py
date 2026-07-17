"""Build the local index: uv run python -m rag.ingest [corpus_dir]

Defaults to config.DATA_DIR (data/sample). Chunks every .md/.txt file,
embeds through the llm seam, saves the index to config.STORAGE_DIR.
"""
import sys
from dataclasses import asdict
from pathlib import Path

from rag import config, llm, store
from rag.chunk import chunk_file, n_tokens


def main(corpus_dir=None):
    corpus = Path(corpus_dir or config.DATA_DIR)
    files = sorted(p for p in corpus.iterdir() if p.suffix.lower() in (".md", ".txt"))
    if not files:
        sys.exit(f"no .md/.txt files in {corpus}")

    chunks = []
    for file in files:
        chunks.extend(chunk_file(file))

    # One embed call for the whole corpus — at this size it's one small batch;
    # split into batches when a corpus actually needs it.
    vectors = llm.embed([chunk.text for chunk in chunks])
    store.save(vectors, [asdict(chunk) for chunk in chunks])

    total_tokens = sum(n_tokens(chunk.text) for chunk in chunks)
    print(f"{len(files)} files -> {len(chunks)} chunks ({total_tokens} tokens) -> {config.STORAGE_DIR}")


if __name__ == "__main__":
    main(*sys.argv[1:])
