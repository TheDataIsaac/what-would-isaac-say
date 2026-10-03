"""Data models shared by ingestion, search, the agent and the API."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Where a chunk came from: a newsletter post, or an answer Isaac wrote in the admin queue.
SourceType = Literal["post", "isaac_answer"]


class RawPost(BaseModel):
    """A newsletter post from the Substack API, with only the fields we use."""

    model_config = ConfigDict(extra="ignore")  # the API returns many fields we do not use

    id: int
    slug: str
    title: str
    subtitle: str | None = None
    post_date: datetime
    canonical_url: str
    audience: str  # "everyone" means free and public
    type: str  # "newsletter", "podcast", "thread", ...
    wordcount: int | None = None
    tags: list[str] = Field(default_factory=list)
    body_html: str

    @model_validator(mode="before")
    @classmethod
    def _flatten_tags(cls, data: Any) -> Any:
        """Turn the API's postTags (a list of objects) into a plain list of tag names."""
        if isinstance(data, dict) and "tags" not in data:
            data = {**data, "tags": [t["name"] for t in data.get("postTags") or []]}
        return data


class Chunk(BaseModel):
    """A piece of text we can search, plus what is needed to cite it."""

    chunk_id: str  # e.g. "the-problem-with-treemaps#2" or "qa-14"
    source_type: SourceType = "post"
    post_slug: str | None = None
    title: str
    heading: str
    url: str | None = None
    published: date | None = None
    tags: list[str] = Field(default_factory=list)
    text: str

    @classmethod
    def from_isaac_answer(cls, question_id: int, question: str, answer: str) -> "Chunk":
        """Make a chunk from an answer Isaac wrote, so it can be found and cited like a post."""
        return cls(
            chunk_id=f"qa-{question_id}",
            source_type="isaac_answer",
            post_slug=None,
            title=question,
            heading="Isaac's answer",
            url=None,
            published=date.today(),
            tags=[],
            text=answer.strip(),
        )

    @property
    def embedding_text(self) -> str:
        """The text that is embedded: the title and heading come first, to give context."""
        return f"{self.title} > {self.heading}\n{self.text}"

    def to_metadata(self) -> dict[str, str | int | float | bool]:
        """Turn the chunk into plain values that the search index can store."""
        return {
            "source_type": self.source_type,
            "post_slug": self.post_slug or "",
            "title": self.title,
            "heading": self.heading,
            "url": self.url or "",
            "published": self.published.isoformat() if self.published else "",
            "tags": "|".join(self.tags),  # the index cannot store a list
        }

    @classmethod
    def from_metadata(cls, chunk_id: str, text: str, meta: dict[str, Any]) -> "Chunk":
        """Rebuild a chunk from what to_metadata stored."""
        return cls(
            chunk_id=chunk_id,
            source_type=meta.get("source_type", "post"),
            post_slug=meta.get("post_slug") or None,
            title=meta.get("title", ""),
            heading=meta.get("heading", ""),
            url=meta.get("url") or None,
            published=date.fromisoformat(meta["published"]) if meta.get("published") else None,
            tags=[t for t in (meta.get("tags") or "").split("|") if t],
            text=text,
        )


class RetrievedChunk(BaseModel):
    """A chunk found by a search, with its similarity score (1.0 means identical)."""

    chunk: Chunk
    score: float
