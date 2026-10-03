"""Everything the assistant can reply with. Each reply has a "kind" so clients know which it is."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from isaac_says.domain.models import SourceType


class SourceCitation(BaseModel):
    """A quote from the newsletter that supports a statement."""

    chunk_id: str
    title: str
    heading: str
    url: str | None = None
    quote: str  # copied word for word, and checked against the source before it is shown
    source_type: SourceType = "post"


class AnswerReply(BaseModel):
    kind: Literal["answer"] = "answer"
    text: str
    citations: list[SourceCitation]


class ReviewIssue(BaseModel):
    title: str
    problem: str
    advice: str
    citation: SourceCitation


class ReviewReply(BaseModel):
    kind: Literal["review"] = "review"
    summary: str
    strengths: list[str]
    issues: list[ReviewIssue]
    next_step: str


class NotCoveredReply(BaseModel):
    """The newsletter does not cover the question, so the assistant says so instead of guessing."""

    kind: Literal["not_covered"] = "not_covered"
    text: str
    # The id of the saved question in the admin queue, if it was saved.
    question_id: int | None = None


class NeedsInputReply(BaseModel):
    """The assistant needs one more detail. The next message in the thread answers it."""

    kind: Literal["needs_input"] = "needs_input"
    question: str


class ChitchatReply(BaseModel):
    kind: Literal["chitchat"] = "chitchat"
    text: str


Reply = Annotated[
    AnswerReply | ReviewReply | NotCoveredReply | NeedsInputReply | ChitchatReply,
    Field(discriminator="kind"),
]

# Turns a saved dict back into the right reply.
ReplyAdapter: TypeAdapter[Reply] = TypeAdapter(Reply)
