"""Heading-aware chunking: split .md on headings (keep sections whole),
window anything longer than CHUNK_TOKENS with CHUNK_OVERLAP. .txt has no
headings, but blank-line paragraphs are still real structure -> split there,
so a window never cuts mid-thought (an FAQ's Q/A pair, being one paragraph,
stays whole for free).
"""
import re
from dataclasses import dataclass

import tiktoken

from rag import config

_enc = tiktoken.get_encoding("cl100k_base")


def n_tokens(text):
    """Token estimate used everywhere (chunking, budgeting). cl100k, not the
    llama tokenizer — SAFETY_FRAC in config covers the drift."""
    return len(_enc.encode(text))


@dataclass
class Chunk:
    """One retrievable piece of a source file — the unit the index stores and ranks."""
    source: str   # filename
    heading: str  # full heading breadcrumb ("Title > Section > Sub"), "" for .txt / preamble
    text: str
    idx: int      # position within the source file


# Noise stripped before chunking: URLs and image syntax burn tokens and embed
# poorly, but their human-readable text (alt text, link labels) is worth keeping.
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")  # ![alt](src) -> alt
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")    # [label](url) -> label
_URL = re.compile(r"<https?://[^>\s]+>|https?://\S+")  # autolink or bare URL -> gone


def _clean(text):
    """Drop URL/image noise, keep the readable text. Markdown structure
    (headings, bold, lists) stays: headings drive the splitter and the
    rest is cheap tokens the model reads fine."""
    text = _IMAGE.sub(r"\1", text)  # before _LINK: an image is a link with a ! prefix
    text = _LINK.sub(r"\1", text)
    text = _URL.sub("", text)
    return text


def _window(text):
    """Slide a CHUNK_TOKENS window with CHUNK_OVERLAP over the token stream."""
    tokens = _enc.encode(text)
    if len(tokens) <= config.CHUNK_TOKENS:
        return [text]

    step = config.CHUNK_TOKENS - config.CHUNK_OVERLAP
    windows = []
    start = 0
    while True:
        end = start + config.CHUNK_TOKENS
        windows.append(_enc.decode(tokens[start:end]))
        if end >= len(tokens):
            return windows
        start += step


def _sections(text):
    """Split markdown into (heading_path, body) pairs. heading_path is the
    full breadcrumb of open headings ("Title > Section > Sub"), maintained
    as a stack: a new level-N heading pops everything at level N or deeper.
    Every window of a section inherits the same path, so a chunk from deep
    inside a long section still knows where it lives. Body keeps its heading
    line. Preamble before the first heading has path ''."""
    sections = []
    open_headings = []   # (level, title) of every heading enclosing the current line
    current_lines = []   # lines of the section being accumulated

    def flush():
        body = "\n".join(current_lines)
        if body.strip():
            path = " > ".join(title for _level, title in open_headings)
            sections.append((path, body))
        current_lines.clear()

    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if match:
            flush()  # previous section ends where a new heading starts
            level = len(match.group(1))
            while open_headings and open_headings[-1][0] >= level:
                open_headings.pop()
            open_headings.append((level, match.group(2).strip()))
        current_lines.append(line)
    flush()
    return sections


def _paragraphs(text):
    """Split .txt at blank-line paragraph breaks — the only structure plain
    text reliably has. No format sniffing (FAQ markers, list styles): any
    paragraph-shaped unit stays whole unless it alone exceeds the window."""
    # Blank line(s) = paragraph break; tolerate trailing spaces on the
    # "blank" line, which editors leave behind in hand-written .txt files.
    parts = re.split(r"\n[ \t]*\n", text)
    return [part for part in parts if part.strip()]


def _shared_heading(headings):
    """Longest common breadcrumb prefix: ("A > B", "A > C") -> "A"."""
    paths = [heading.split(" > ") if heading else [] for heading in headings]
    prefix = paths[0]
    for path in paths[1:]:
        keep = 0
        while keep < len(prefix) and keep < len(path) and prefix[keep] == path[keep]:
            keep += 1
        prefix = prefix[:keep]
    return " > ".join(prefix)


def _merge(pieces):
    """Pack neighboring (heading, text) pieces into chunks of up to
    CHUNK_MERGE_TOKENS. Pieces stay whole — this only decides how many
    share a chunk; a piece already over the target stands alone. The
    merged heading is the pieces' shared breadcrumb prefix."""
    merged = []
    group = []  # pieces going into the chunk being built
    group_tokens = 0
    for heading, text in pieces:
        piece_tokens = n_tokens(text)
        if group and group_tokens + piece_tokens > config.CHUNK_MERGE_TOKENS:
            merged.append(group)
            group, group_tokens = [], 0
        group.append((heading, text))
        group_tokens += piece_tokens
    if group:
        merged.append(group)

    combined = []
    for group in merged:
        heading = _shared_heading([heading for heading, _text in group])
        text = "\n\n".join(text for _heading, text in group)
        combined.append((heading, text))
    return combined


def chunk_file(path, source=None):
    """One source file -> list of Chunks with gapless per-file idx.

    source: name stored on each chunk (citations, BM25, embed prefix).
    Defaults to the bare filename; ingest passes the corpus-relative path
    so nested files with the same name stay distinguishable.
    """
    text = _clean(path.read_text(encoding="utf-8"))
    source = source or path.name

    pieces = []  # (heading, text) pairs, before numbering
    if path.suffix.lower() == ".md":
        for heading, body in _sections(text):
            for window in _window(body):
                pieces.append((heading, window))
    else:
        for paragraph in _paragraphs(text):
            for window in _window(paragraph):
                pieces.append(("", window))

    if config.CHUNK_MERGE_TOKENS > 0:
        pieces = _merge(pieces)

    chunks = []
    for heading, piece_text in pieces:
        if not piece_text.strip():
            continue  # skip empties before numbering so idx stays gapless
        chunks.append(Chunk(source=source, heading=heading, text=piece_text, idx=len(chunks)))
    return chunks
