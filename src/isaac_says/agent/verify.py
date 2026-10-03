"""Checks that a quote really appears in the source, because the model can invent quotes.

Case, quote marks and spacing are ignored, but the words must match.
"""

import re
import unicodedata

from isaac_says.domain.models import RetrievedChunk

MIN_QUOTE_WORDS = 3  # a shorter quote is not real evidence

_DASHES = str.maketrans({"—": " ", "–": " ", "-": " "})
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
_ELLIPSIS = re.compile(r"\.\.\.|…")


def normalize_for_match(text: str) -> str:
    """Lower-case the text and make quote marks, dashes and spaces uniform."""
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES).translate(_DASHES)
    text = re.sub(r"[\"'`]", "", text)  # drop quote marks so different apostrophes match
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_appears_in(quote: str, text: str) -> bool:
    """True if the quote appears in the text.

    A quote with "..." is split into pieces that must appear in order, without overlapping.
    Pieces must match whole words, so "bar charts" does not match inside "toolbar charts".
    """
    haystack = normalize_for_match(text)
    fragments = [normalize_for_match(f).strip(" .,;:!?") for f in _ELLIPSIS.split(quote)]
    fragments = [f for f in fragments if f]
    if not fragments or sum(len(f.split()) for f in fragments) < MIN_QUOTE_WORDS:
        return False

    position = 0
    for fragment in fragments:
        match = re.compile(rf"(?<!\w){re.escape(fragment)}(?!\w)").search(haystack, position)
        if match is None:
            return False
        position = match.end()  # the next piece must come after this one
    return True


def locate_quote(
    quote: str, claimed_chunk_id: str, candidates: list[RetrievedChunk]
) -> RetrievedChunk | None:
    """Return the chunk that contains the quote, or None.

    The chunk the model named is tried first. If the quote is in a different chunk, the model
    named the wrong one, so that chunk is returned instead.
    """
    named = [c for c in candidates if c.chunk.chunk_id == claimed_chunk_id]
    others = [c for c in candidates if c.chunk.chunk_id != claimed_chunk_id]
    for candidate in [*named, *others]:
        if quote_appears_in(quote, candidate.chunk.text):
            return candidate
    return None
