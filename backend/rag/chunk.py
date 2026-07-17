"""Heading-aware chunking: split .md on headings (keep sections whole),
window anything longer than CHUNK_TOKENS with CHUNK_OVERLAP. .txt has no
headings -> windowed directly.
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
    heading: str  # nearest markdown heading, "" for .txt / preamble
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
    """Split markdown into (heading, body) pairs; body keeps its heading line
    so embeddings see it. Preamble before the first heading has heading ''."""
    # Matches a whole heading line: 1-6 '#' then whitespace then the title.
    # Because the pattern is in (parens), re.split KEEPS the heading lines,
    # so parts alternates: [preamble, heading1, body1, heading2, body2, ...]
    parts = re.split(r"(?m)^(#{1,6}\s+.*)$", text)

    sections = []
    preamble = parts[0]
    if preamble.strip():
        sections.append(("", preamble))

    heading_lines = parts[1::2]  # every 2nd item starting at 1: the headings
    bodies = parts[2::2]         # every 2nd item starting at 2: their bodies
    for heading_line, body in zip(heading_lines, bodies):
        heading = heading_line.lstrip("#").strip()
        sections.append((heading, heading_line + body))
    return sections


def chunk_file(path):
    """One source file -> list of Chunks with gapless per-file idx."""
    text = path.read_text(encoding="utf-8")

    pieces = []  # (heading, text) pairs, before numbering
    if path.suffix.lower() == ".md":
        for heading, body in _sections(text):
            for window in _window(body):
                pieces.append((heading, window))
    else:
        for window in _window(text):
            pieces.append(("", window))

    chunks = []
    for heading, piece_text in pieces:
        if not piece_text.strip():
            continue  # skip empties before numbering so idx stays gapless
        chunks.append(Chunk(source=path.name, heading=heading, text=piece_text, idx=len(chunks)))
    return chunks
