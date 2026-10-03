"""Turns a post's HTML into clean text, grouped by heading.

The HTML mixes the writing with page extras (subscribe boxes, images, buttons). We keep the writing
and drop the rest.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from isaac_says.domain.models import RawPost

HEADING_TAGS = {"h1", "h2", "h3", "h4"}
TEXT_BLOCKS = {"p", "blockquote", "pre"}
LIST_TAGS = {"ul", "ol"}

# Divs with these classes are page extras, so we skip what is inside them.
SKIP_CLASS_MARKERS = (
    "subscription-widget",
    "captioned-image",
    "button-wrapper",
    "image-link",
    "footnote",
    "poll",
    "embedded-post",
)

# Lines Substack adds to every post.
BOILERPLATE = re.compile(
    r"^(thanks for reading|subscribe for free|share this post|leave a comment|"
    r"this post is public so feel free to share)",
    re.IGNORECASE,
)


@dataclass
class Section:
    heading: str
    paragraphs: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(self.paragraphs)


def normalize(text: str) -> str:
    """Make unusual characters standard and squash extra spaces. The words stay the same."""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def _should_skip(tag: Tag) -> bool:
    classes = " ".join(tag.get("class") or [])
    return any(marker in classes for marker in SKIP_CLASS_MARKERS)


def _walk(node: Tag, sections: list[Section]) -> None:
    """Go through the tags in order and add the text to the current (last) section."""
    for child in node.children:
        if not isinstance(child, Tag):
            continue  # text between tags is only spaces
        name = child.name
        if name in HEADING_TAGS:
            heading = normalize(child.get_text(" "))
            if heading:
                sections.append(Section(heading=heading))
        elif name in TEXT_BLOCKS:
            _add_paragraph(sections, normalize(child.get_text(" ")))
        elif name in LIST_TAGS:
            for item in child.find_all("li"):
                _add_paragraph(sections, "- " + normalize(item.get_text(" ")))
        elif name == "div":
            if not _should_skip(child):
                _walk(child, sections)  # an ordinary wrapper, so look inside


def _add_paragraph(sections: list[Section], text: str) -> None:
    if text and not BOILERPLATE.match(text):
        sections[-1].paragraphs.append(text)


def html_to_sections(post: RawPost) -> list[Section]:
    """The post's sections in reading order, without the empty ones."""
    soup = BeautifulSoup(post.body_html, "html.parser")
    # Text before the first heading is the introduction, labelled with the post title.
    sections = [Section(heading=post.title)]
    _walk(soup, sections)
    return [s for s in sections if s.paragraphs]
