"""Chunking: split/overlap/metadata/no runaway sizes — against the real corpus."""
from rag import config
from rag.chunk import Chunk, chunk_file, n_tokens

CORPUS_DIR = config.DATA_DIR  # backend/data/sample — the generated wiki


def all_chunks():
    chunks = []
    for file in sorted(CORPUS_DIR.iterdir()):
        chunks.extend(chunk_file(file))
    return chunks


def test_corpus_chunks_metadata_and_size():
    chunks = all_chunks()
    assert chunks, "corpus produced no chunks"
    assert {c.source for c in chunks} == {p.name for p in CORPUS_DIR.iterdir()}
    for c in chunks:
        assert isinstance(c, Chunk) and c.text.strip()
        assert n_tokens(c.text) <= config.CHUNK_TOKENS + 5  # decode/re-encode slack
    # .md sections carry their heading; idx restarts per file
    assert any(c.heading for c in chunks if c.source.endswith(".md"))
    for src in {c.source for c in chunks}:
        idxs = [c.idx for c in chunks if c.source == src]
        assert idxs == list(range(len(idxs)))


def test_long_text_windows_with_overlap(tmp_path):
    words = " ".join(f"word{i}" for i in range(2000))  # >> CHUNK_TOKENS
    f = tmp_path / "long.txt"
    f.write_text(words, encoding="utf-8")
    chunks = chunk_file(f)
    assert len(chunks) > 1
    for a, b in zip(chunks, chunks[1:]):
        assert a.text[-20:] in b.text  # tail of one window appears in the next


def test_txt_splits_on_paragraphs_keeping_them_whole(tmp_path):
    # multi-line paragraphs (like an FAQ's Q/A pair) must not be separated;
    # the paragraph break is the only boundary a window may cut at
    f = tmp_path / "notes.txt"
    f.write_text(
        "Q: How often does the shuttle run?\n"
        "A: Every 20 minutes in season.\n"
        "\n"
        "second paragraph about moose\n",
        encoding="utf-8",
    )
    chunks = chunk_file(f)
    assert len(chunks) == 2
    assert [c.heading for c in chunks] == ["", ""]  # .txt never invents headings
    assert "shuttle" in chunks[0].text and "Every 20 minutes" in chunks[0].text
    assert "moose" in chunks[1].text


def test_md_sections_kept_whole(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("# Title\nintro\n## Section A\nbody a\n## Section B\nbody b\n", encoding="utf-8")
    chunks = chunk_file(f)
    assert [c.heading for c in chunks] == ["Title", "Section A", "Section B"]
    assert "body a" in chunks[1].text and "## Section A" in chunks[1].text
