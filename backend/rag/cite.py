"""Fix citation markers that point at the wrong packed chunk.

The model sometimes states a fact correctly but tags it with a neighbor's
number ("...Ruben Ortega [5]" when Ortega is only in chunk 1). Retrieval and
the answer are both right; only the attribution is wrong.

Checked here instead of in the prompt: the answer text is already streamed
to the client when this runs, so the marker the user sees stays as-is and
only the source that marker resolves to is corrected.
"""
import re

# Distinctive = the tokens that make a claim checkable: numbers (with their
# units/symbols) and capitalized names. Common words are useless here — they
# appear in every chunk.
_NUMBER = re.compile(r"\$?\d[\d,.]*\s?(?:%|km|m|kg|hours?|days?|weeks?|months?|years?|minutes?)?")
_NAME = re.compile(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*")
_SENTENCE = re.compile(r"[^.!?]+[.!?]?")

# A capitalized word that starts a sentence is usually just grammar, not a
# name — and these appear in every chunk, so they prove nothing.
_NOT_NAMES = {
    "the", "this", "that", "these", "those", "there", "their", "they",
    "you", "your", "employees", "all", "any", "each", "every", "only",
    "before", "after", "when", "where", "what", "who", "how", "for",
    "from", "with", "and", "but", "not", "yes",
}


def _distinctive(text):
    """The number and name tokens a sentence stakes its claim on."""
    found = set()
    for match in _NUMBER.findall(text):
        cleaned = match.strip()
        if cleaned:
            found.add(cleaned.lower())
    for match in _NAME.findall(text):
        name = match.lower()
        if name in _NOT_NAMES:
            continue
        found.add(name)
    return found


def _supports(chunk_text, tokens):
    """How many of the sentence's distinctive tokens this chunk contains."""
    haystack = chunk_text.lower()
    return sum(1 for token in tokens if token in haystack)


def fix(answer, citations):
    """Return citations with mis-attributed ids repointed at the chunk that
    actually contains the claim.

    A marker is only repointed when its own chunk supports none of the
    sentence's distinctive tokens AND exactly one other packed chunk
    supports the most of them. Anything less clear-cut is left alone —
    a wrong citation is bad, a wrongly "corrected" one is worse.
    """
    by_id = {citation["id"]: citation for citation in citations}
    corrected = {}

    for sentence in _SENTENCE.findall(answer):
        marker_ids = [int(number) for number in re.findall(r"\[(\d+)\]", sentence)]
        if not marker_ids:
            continue
        tokens = _distinctive(re.sub(r"\[\d+\]", "", sentence))
        if not tokens:
            continue  # nothing checkable in this sentence

        for marker_id in marker_ids:
            cited = by_id.get(marker_id)
            if cited is None or _supports(cited["text"], tokens) > 0:
                continue  # unknown id, or the cited chunk does support the claim

            scores = []
            for citation in citations:
                if citation["id"] == marker_id:
                    continue
                scores.append((_supports(citation["text"], tokens), citation))
            if not scores:
                continue
            scores.sort(key=lambda pair: pair[0], reverse=True)
            best_score, best = scores[0]
            tied = sum(1 for score, _citation in scores if score == best_score)
            if best_score > 0 and tied == 1:
                corrected[marker_id] = best

    if not corrected:
        return citations, []

    fixed = []
    for citation in citations:
        replacement = corrected.get(citation["id"])
        if replacement is None:
            fixed.append(citation)
        else:
            # keep the marker number the reader saw, point it at the real source
            fixed.append({**replacement, "id": citation["id"]})
    changes = [(marker_id, by_id[marker_id]["source"], new["source"]) for marker_id, new in corrected.items()]
    return fixed, changes
