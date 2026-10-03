"""The database tables. The posts are not here, they are in the saved file and the search index.

* OpenQuestion   questions the assistant could not answer
* QueryLog       one row per chat turn (time taken, tokens, cost, outcome)
* Feedback       thumbs up or down on a reply
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """The base class for all tables."""


class OpenQuestion(Base):
    __tablename__ = "open_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    # The question in a standard form. It is unique, so a repeat adds to times_asked instead.
    question_key: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    times_asked: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open | answered
    answer: Mapped[str | None] = mapped_column(Text, default=None)
    chunk_id: Mapped[str | None] = mapped_column(
        String(64), default=None
    )  # where the answer is indexed
    first_asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class QueryLog(Base):
    __tablename__ = "query_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Feedback uses request_id to say which reply it is about.
    request_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    intent: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(16), index=True)  # the reply kind
    latency_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("query_logs.request_id"), index=True)
    rating: Mapped[int] = mapped_column(Integer)  # +1 or -1
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
