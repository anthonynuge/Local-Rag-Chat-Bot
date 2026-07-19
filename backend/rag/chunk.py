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


def chunk_file(path):
    """One source file -> list of Chunks with gapless per-file idx."""
    text = path.read_text(encoding="utf-8")

    pieces = []  # (heading, text) pairs, before numbering
    if path.suffix.lower() == ".md":
        for heading, body in _sections(text):
            for window in _window(body):
                pieces.append((heading, window))
    else:
        for paragraph in _paragraphs(text):
            for window in _window(paragraph):
                pieces.append(("", window))

    chunks = []
    for heading, piece_text in pieces:
        if not piece_text.strip():
            continue  # skip empties before numbering so idx stays gapless
        chunks.append(Chunk(source=path.name, heading=heading, text=piece_text, idx=len(chunks)))
    return chunks
