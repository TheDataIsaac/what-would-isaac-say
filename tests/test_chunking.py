"""Tests for turning a post's HTML into chunks, split by heading."""

from datetime import datetime
from pathlib import Path

from isaac_says.domain.models import RawPost
from isaac_says.ingestion.chunking import MAX_CHARS, chunk_post
from isaac_says.ingestion.snapshot import load_snapshot

SNAPSHOT = Path(__file__).parents[1] / "data" / "raw" / "posts.jsonl"


def make_post(html: str) -> RawPost:
    return RawPost(
        id=1,
        slug="sample-post",
        title="Sample Post",
        post_date=datetime(2025, 1, 1),
        canonical_url="https://example.com/p/sample-post",
        audience="everyone",
        type="newsletter",
        body_html=html,
    )


def paragraph(word: str, count: int) -> str:
    return f"<p>{' '.join([word] * count)}.</p>"


def test_each_heading_starts_a_new_chunk():
    """Two sections of normal length become two chunks, named after their headings."""
    html = f"<h2>First</h2>{paragraph('alpha', 80)}<h2>Second</h2>{paragraph('beta', 80)}"
    chunks = chunk_post(make_post(html))
    assert [c.heading for c in chunks] == ["First", "Second"]
    assert [c.chunk_id for c in chunks] == ["sample-post#0", "sample-post#1"]


def test_short_section_is_joined_to_its_neighbour():
    """A section too short to stand alone is merged, and its heading stays in the text."""
    html = f"<h2>Tiny</h2><p>Just one line.</p><h2>Main</h2>{paragraph('gamma', 80)}"
    chunks = chunk_post(make_post(html))
    assert len(chunks) == 1
    assert "Just one line." in chunks[0].text
    assert "Main." in chunks[0].text


def test_long_section_is_split_into_numbered_parts():
    """A section far over the size limit is split between paragraphs into numbered parts."""
    html = "<h2>Long</h2>" + paragraph("delta", 100) * 6
    chunks = chunk_post(make_post(html))
    assert len(chunks) > 1
    assert chunks[0].heading == "Long (part 1)"
    assert all(len(c.text) <= MAX_CHARS for c in chunks)


def test_subscribe_boxes_and_boilerplate_are_dropped():
    """Page extras that Substack adds are not part of any chunk."""
    html = (
        f"<h2>Topic</h2>{paragraph('epsilon', 80)}"
        '<div class="subscription-widget"><p>Join 2,000 readers</p></div>'
        "<p>Thanks for reading Explain the Data!</p>"
    )
    text = chunk_post(make_post(html))[0].text
    assert "Join 2,000 readers" not in text
    assert "Thanks for reading" not in text


def test_every_real_post_gives_chunks_of_a_sensible_size():
    """Every committed post chunks without errors, and no chunk is tiny or huge."""
    posts = load_snapshot(SNAPSHOT)
    assert posts
    for post in posts:
        for chunk in chunk_post(post):
            assert 100 < len(chunk.text) < MAX_CHARS * 1.5
