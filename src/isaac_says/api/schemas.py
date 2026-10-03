"""The shapes of what the API receives and sends. FastAPI uses them to check requests."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from isaac_says.domain.replies import Reply

MAX_MESSAGE_CHARS = 4000  # enough for a detailed description of a dashboard
THREAD_ID_PATTERN = r"^[A-Za-z0-9_-]{8,64}$"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    # Leave it out on the first message. Send back the one you get to continue the conversation.
    thread_id: str | None = Field(default=None, pattern=THREAD_ID_PATTERN)


class ChatResponse(BaseModel):
    request_id: str  # used to send feedback about this reply
    thread_id: str
    reply: Reply
    latency_ms: int


class FeedbackRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=32)
    rating: Literal[-1, 1]
    comment: str | None = Field(default=None, max_length=1000)


class PostSummary(BaseModel):
    slug: str
    title: str
    subtitle: str | None
    published: date
    url: str
    tags: list[str]
    wordcount: int | None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    indexed_chunks: int
    model: str
    version: str


class OpenQuestionOut(BaseModel):
    id: int
    question: str
    times_asked: int
    status: str
    answer: str | None
    first_asked_at: datetime
    last_asked_at: datetime

    model_config = {"from_attributes": True}  # can be built straight from a database row


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=20, max_length=4000)


class StatsOut(BaseModel):
    total_queries: int
    by_outcome: dict[str, int]
    avg_latency_ms: float
    p95_latency_ms: int
    total_cost_usd: float
    open_questions: int
    answered_questions: int
    thumbs_up: int
    thumbs_down: int
