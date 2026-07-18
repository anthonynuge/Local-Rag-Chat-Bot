"""Ollama wrapper: chat (streaming, num_ctx=NUM_CTX) and embeddings.

Guardrail: this is the only file that imports the Ollama client.
"""

import numpy as np
import ollama

from rag import config

_client = ollama.Client(host=config.OLLAMA_HOST)


def chat(messages):
    """Stream chat chunks; the last one (done=True) carries
    prompt_eval_count / eval_count — the numbers the budget guardrail
    asserts against."""
    options = {
        "num_ctx": config.NUM_CTX,
        "num_predict": config.ANSWER_RESERVE,
        "temperature": config.TEMPERATURE,
    }
    if config.NUM_GPU is not None:
        options["num_gpu"] = int(config.NUM_GPU)  # 0 = CPU-only calibration pass
    return _client.chat(model=config.MODEL, messages=messages, stream=True, options=options)


def available_models():
    """Names of locally pulled models; raises when Ollama is unreachable."""
    return [m["model"] for m in _client.list()["models"]]


def embed(texts):
    """Embed texts -> L2-normalized float32 matrix, one row per text.
    Normalized here, once, so cosine similarity downstream is a plain dot."""
    resp = _client.embed(model=config.EMBED_MODEL, input=list(texts))
    vecs = np.asarray(resp["embeddings"], dtype=np.float32)
    return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)


if __name__ == "__main__":  # round-trip check: uv run python -m rag.llm
    v = embed(["hello world", "goodbye"])
    assert v.shape[0] == 2 and v.dtype == np.float32
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-5)

    chunks = list(chat([{"role": "user", "content": "Reply with exactly: OK"}]))
    text = "".join(c["message"]["content"] for c in chunks)
    final = chunks[-1]
    assert text.strip(), "empty completion"
    assert final["done"] and final["prompt_eval_count"] > 0
    print(f"ok — reply={text.strip()!r} prompt_eval_count={final['prompt_eval_count']} "
          f"eval_count={final['eval_count']} dim={v.shape[1]}")
