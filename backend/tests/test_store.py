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
