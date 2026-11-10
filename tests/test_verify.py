"""Tests for quote verification, the check that stops the assistant showing invented quotes."""

from isaac_says.agent.verify import locate_quote, quote_appears_in
from isaac_says.domain.models import Chunk, RetrievedChunk

SOURCE = (
    "Treemaps look tidy, but areas are hard to compare. "
    "Treemaps also make ranking harder than it needs to be."
)


def make_retrieved(chunk_id: str, text: str) -> RetrievedChunk:
    chunk = Chunk(chunk_id=chunk_id, title="A post", heading="A heading", text=text)
    return RetrievedChunk(chunk=chunk, score=0.8)


def test_exact_quote_is_accepted():
    """A quote copied word for word passes."""
    assert quote_appears_in("Treemaps also make ranking harder than it needs to be.", SOURCE)


def test_case_spacing_and_curly_quotes_are_ignored():
    """Formatting differences that do not change the words still pass."""
    assert quote_appears_in("TREEMAPS ALSO MAKE   ranking harder", SOURCE)
    assert quote_appears_in("“Treemaps look tidy”", SOURCE)
    assert quote_appears_in("Isaac’s rule is simple", "Isaac's rule is simple.")


def test_invented_or_reworded_quote_is_rejected():
    """A quote whose words are not in the source fails, even if the meaning is close."""
    assert not quote_appears_in("Treemaps are always the best choice", SOURCE)
    assert not quote_appears_in("Ranking is made harder by treemaps", SOURCE)


def test_quote_shorter_than_three_words_is_rejected():
    """Two words could match almost anywhere, so they do not count as evidence."""
    assert not quote_appears_in("Treemaps also", SOURCE)
    assert not quote_appears_in("", SOURCE)


def test_quote_must_match_whole_words():
    """Words must match whole, so "bar charts" does not match inside "toolbar charts"."""
    assert not quote_appears_in("bar charts are useful", "Toolbar charts are useful.")


def test_ellipsis_pieces_must_all_appear_in_order():
    """Each piece of a quote with "..." must be in the source, in the same order."""
    assert quote_appears_in("Treemaps look tidy ... harder than it needs to be", SOURCE)
    assert not quote_appears_in("harder than it needs to be ... Treemaps look tidy", SOURCE)


def test_locate_quote_finds_the_named_chunk():
    """When the model names the right chunk, that chunk is returned."""
    chunks = [make_retrieved("a#0", "Something about SQL joins."), make_retrieved("b#1", SOURCE)]
    found = locate_quote("areas are hard to compare", "b#1", chunks)
    assert found is not None and found.chunk.chunk_id == "b#1"


def test_locate_quote_fixes_a_wrong_chunk_id():
    """When the model names the wrong chunk, the chunk that really holds the quote is returned."""
    chunks = [make_retrieved("a#0", "Something about SQL joins."), make_retrieved("b#1", SOURCE)]
    found = locate_quote("areas are hard to compare", "a#0", chunks)
    assert found is not None and found.chunk.chunk_id == "b#1"


def test_locate_quote_returns_none_for_an_invented_quote():
    """A quote that is in no chunk gives None, so the reply drops it."""
    chunks = [make_retrieved("b#1", SOURCE)]
    assert locate_quote("this sentence was never written", "b#1", chunks) is None
