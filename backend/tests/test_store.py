"""Store: save/load round-trip with synthetic vectors."""
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
