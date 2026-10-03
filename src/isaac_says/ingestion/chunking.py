"""Splits posts into chunks that can be searched and cited.

The rules, in order:
1. Follow the headings: a section is usually one chunk.
2. Keep chunks a sensible size: very short ones lack context, very long ones are too vague.
3. Avoid splitting a paragraph.
"""

import re

from isaac_says.domain.models import Chunk, RawPost
from isaac_says.ingestion.cleaning import Section, html_to_sections

MAX_CHARS = 1400  # about 230 words
MIN_CHARS = 350  # shorter sections are joined to a neighbour

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    """For one very long paragraph: split at the ends of sentences."""
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(paragraph):
        if current and len(current) + len(sentence) + 1 > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def _split_section(section: Section, max_chars: int, min_chars: int) -> list[Section]:
    """Split a section that is too long into parts, between paragraphs."""
    if len(section.text) <= max_chars:
        return [section]
    parts: list[list[str]] = []
    current: list[str] = []
    size = 0
    for paragraph in section.paragraphs:
        pieces = (
            _split_long_paragraph(paragraph, max_chars)
            if len(paragraph) > max_chars
            else [paragraph]
        )
        for piece in pieces:
            if current and size + len(piece) > max_chars:
                parts.append(current)
                current, size = [], 0
            current.append(piece)
            size += len(piece) + 2  # plus the blank line between paragraphs
    if current:
        parts.append(current)

    # Join a very short last part to the one before it, instead of making a tiny chunk.
    if len(parts) > 1:
        tail_size = sum(len(p) for p in parts[-1])
        previous_size = sum(len(p) for p in parts[-2])
        if tail_size < min_chars and previous_size + tail_size <= max_chars * 1.5:
            parts[-2].extend(parts.pop())

    if len(parts) == 1:
        return [Section(section.heading, parts[0])]
    # Number the parts, so citations can be told apart.
    return [Section(f"{section.heading} (part {i})", p) for i, p in enumerate(parts, 1)]


def _merge_small_sections(sections: list[Section], min_chars: int) -> list[Section]:
    """Join short sections to the one after them (or before, if it is the last one).

    The joined heading stays in the text as a plain line, so nothing is lost.
    """
    merged: list[Section] = []
    carry: Section | None = None
    for section in sections:
        if carry is not None:
            section = Section(
                carry.heading,
                [*carry.paragraphs, section.heading + ".", *section.paragraphs],
            )
            carry = None
        if len(section.text) < min_chars:
            carry = section
        else:
            merged.append(section)
    if carry is not None:
        if merged:  # a short last section joins the one before it
            last = merged[-1]
            merged[-1] = Section(
                last.heading, [*last.paragraphs, carry.heading + ".", *carry.paragraphs]
            )
        else:  # the whole post is short, so keep it as one chunk
            merged.append(carry)
    return merged


def chunk_post(
    post: RawPost, *, max_chars: int = MAX_CHARS, min_chars: int = MIN_CHARS
) -> list[Chunk]:
    """Turn one post into chunks with ids like "<slug>#0", "<slug>#1"."""
    sections = html_to_sections(post)
    sections = _merge_small_sections(sections, min_chars)
    sections = [part for s in sections for part in _split_section(s, max_chars, min_chars)]
    return [
        Chunk(
            chunk_id=f"{post.slug}#{i}",
            source_type="post",
            post_slug=post.slug,
            title=post.title,
            heading=section.heading,
            url=post.canonical_url,
            published=post.post_date.date(),
            tags=post.tags,
            text=section.text,
        )
        for i, section in enumerate(sections)
    ]
