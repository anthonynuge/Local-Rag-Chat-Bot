"""Store: save/load round-trip and top_k ordering with synthetic vectors."""
import numpy as np

from rag import store


def _unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_save_load_roundtrip(tmp_path):
    vecs = np.stack([_unit([1, 0.0]), _unit([1, 1]), _unit([0.0, 1])])
    chunks = [{"source": f"f{i}.md", "heading": "", "text": f"t{i}", "idx": 0} for i in range(3)]
    store.save(vecs, chunks, tmp_path)

    loaded = store.load(tmp_path)
    assert np.allclose(loaded.vectors, vecs)
    assert loaded.chunks == chunks


def test_top_k_returns_best_first(tmp_path):
    # three unit vectors at increasing angle from the [1, 0] query direction
    vecs = np.stack([_unit([1, 0.0]), _unit([1, 1]), _unit([0.0, 1])])
    chunks = [{"source": f"f{i}.md", "heading": "", "text": f"t{i}", "idx": 0} for i in range(3)]
    s = store.Store(vecs, chunks)

    hits = s.top_k(_unit([1, 0.0]), k=2)
    assert [h["source"] for h in hits] == ["f0.md", "f1.md"]
    assert hits[0]["score"] > hits[1]["score"]
    # a query pointing the other way ranks the last chunk first
    assert s.top_k(_unit([0.0, 1]), k=1)[0]["source"] == "f2.md"
    # the stored chunks were not mutated by scoring
    assert "score" not in s.chunks[0]


def test_per_file_cap_lets_other_files_in():
    # four chunks of big.md outscore everything; the cap (2 per file) must
    # pass slots 3 and 4 on to the next-ranked files instead
    vecs = np.stack([
        _unit([1, 0.0]),      # big.md
        _unit([1, 0.1]),      # big.md
        _unit([1, 0.2]),      # big.md
        _unit([1, 0.3]),      # big.md
        _unit([0.5, 1]),      # other.md
        _unit([0.0, 1]),      # third.md
    ])
    chunks = [
        {"source": "big.md", "heading": "", "text": f"big {i}", "idx": i} for i in range(4)
    ] + [
        {"source": "other.md", "heading": "", "text": "other", "idx": 0},
        {"source": "third.md", "heading": "", "text": "third", "idx": 0},
    ]
    s = store.Store(vecs, chunks)
    hits = s.top_k(_unit([1, 0.0]), k=4)
    assert [h["source"] for h in hits] == ["big.md", "big.md", "other.md", "third.md"]


def test_hybrid_rare_token_beats_cosine():
    # cosine alone ranks the wrong chunk first (vectors say so), but the
    # query's rare token "rut" appears only in the second chunk — the BM25
    # vote must pull it to the top of the fused ranking
    vecs = np.stack([_unit([1, 0.0]), _unit([0.6, 0.8])])
    chunks = [
        {"source": "generic.md", "heading": "", "text": "general park visiting advice", "idx": 0},
        {"source": "moose.txt", "heading": "", "text": "keep far away during the fall rut", "idx": 0},
    ]
    s = store.Store(vecs, chunks)
    query = _unit([1, 0.0])  # cosine favors generic.md

    assert s.top_k(query, k=1)[0]["source"] == "generic.md"  # cosine-only order
    hybrid = s.top_k(query, "what about during the fall rut?", k=2)
    assert hybrid[0]["source"] == "moose.txt"


def test_hybrid_without_rare_tokens_keeps_cosine_order():
    # a query whose tokens appear in every chunk (or none) gives BM25 nothing
    # decisive — the cosine order must survive fusion
    vecs = np.stack([_unit([1, 0.0]), _unit([0.0, 1])])
    chunks = [
        {"source": "a.md", "heading": "", "text": "park trails and park views", "idx": 0},
        {"source": "b.md", "heading": "", "text": "park fees and park passes", "idx": 0},
    ]
    s = store.Store(vecs, chunks)
    hybrid = s.top_k(_unit([1, 0.0]), "tell me about the park", k=2)
    assert hybrid[0]["source"] == "a.md"
