"""Every database read and write happens here."""

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from isaac_says.db.models import Feedback, OpenQuestion, QueryLog, utcnow


def question_key(question: str) -> str:
    """Put a question in a standard form, so small differences count as the same question."""
    lowered = re.sub(r"[^\w\s]", "", question.lower())
    return re.sub(r"\s+", " ", lowered).strip()[:300]


@dataclass(frozen=True)
class Stats:
    total_queries: int
    by_outcome: dict[str, int]
    avg_latency_ms: float
    p95_latency_ms: int
    total_cost_usd: float
    open_questions: int
    answered_questions: int
    thumbs_up: int
    thumbs_down: int


class Repository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # The question queue
    async def record_open_question(self, question: str) -> int:
        """Save a question we could not answer, or add one to its count if it is already saved.

        The count goes up with a single UPDATE in the database. Reading the number and writing it
        back from Python would lose counts when two visitors ask at the same moment.
        """
        key = question_key(question)
        async with self._session_factory() as session:
            if not await self._bump(session, key):
                session.add(OpenQuestion(question=question.strip(), question_key=key))
                try:
                    await session.commit()
                except IntegrityError:
                    # Someone else saved the same question a moment ago. Count this one on theirs.
                    await session.rollback()
                    await self._bump(session, key)
            return await session.scalar(
                select(OpenQuestion.id).where(OpenQuestion.question_key == key)
            )  # type: ignore[return-value]

    @staticmethod
    async def _bump(session: AsyncSession, key: str) -> bool:
        """Add one to a saved question's count. Returns False if the question is not saved."""
        result = await session.execute(
            update(OpenQuestion)
            .where(OpenQuestion.question_key == key)
            .values(times_asked=OpenQuestion.times_asked + 1, last_asked_at=utcnow())
        )
        await session.commit()
        return result.rowcount > 0

    async def list_questions(self, status: str = "open", limit: int = 50) -> list[OpenQuestion]:
        """The questions with this status, most asked first."""
        async with self._session_factory() as session:
            result = await session.scalars(
                select(OpenQuestion)
                .where(OpenQuestion.status == status)
                .order_by(OpenQuestion.times_asked.desc(), OpenQuestion.last_asked_at.desc())
                .limit(limit)
            )
            return list(result)

    async def get_question(self, question_id: int) -> OpenQuestion | None:
        async with self._session_factory() as session:
            return await session.get(OpenQuestion, question_id)

    async def mark_answered(
        self, question_id: int, answer: str, chunk_id: str
    ) -> OpenQuestion | None:
        async with self._session_factory() as session:
            row = await session.get(OpenQuestion, question_id)
            if row is None:
                return None
            row.status, row.answer, row.chunk_id, row.answered_at = (
                "answered",
                answer,
                chunk_id,
                utcnow(),
            )
            await session.commit()
            return row

    # Logs and feedback
    async def log_query(
        self,
        *,
        request_id: str,
        thread_id: str,
        intent: str,
        outcome: str,
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> None:
        async with self._session_factory() as session:
            session.add(
                QueryLog(
                    request_id=request_id,
                    thread_id=thread_id,
                    intent=intent,
                    outcome=outcome,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                )
            )
            await session.commit()

    async def count_queries_since(self, since: datetime) -> int:
        """How many chat turns were logged since the given time (UTC)."""
        async with self._session_factory() as session:
            count = await session.scalar(
                select(func.count()).select_from(QueryLog).where(QueryLog.created_at >= since)
            )
            return count or 0

    async def stale_thread_ids(self, last_active_before: datetime) -> list[str]:
        """Conversations whose last turn is older than the given time (UTC)."""
        async with self._session_factory() as session:
            rows = await session.execute(
                select(QueryLog.thread_id)
                .group_by(QueryLog.thread_id)
                .having(func.max(QueryLog.created_at) < last_active_before)
            )
            return [thread_id for (thread_id,) in rows]

    async def add_feedback(self, request_id: str, rating: int, comment: str | None) -> bool:
        """Save feedback. Returns False if the request_id is not known."""
        async with self._session_factory() as session:
            known = await session.scalar(
                select(QueryLog.id).where(QueryLog.request_id == request_id)
            )
            if known is None:
                return False
            session.add(Feedback(request_id=request_id, rating=rating, comment=comment))
            await session.commit()
            return True

    # Numbers for the admin page
    async def stats(self, since: datetime | None = None) -> Stats:
        """Totals for usage, cost, response time, the question queue and feedback."""
        async with self._session_factory() as session:
            log_filter = [QueryLog.created_at >= since] if since else []

            outcomes = await session.execute(
                select(QueryLog.outcome, func.count()).where(*log_filter).group_by(QueryLog.outcome)
            )
            by_outcome = {outcome: count for outcome, count in outcomes}

            totals = (
                await session.execute(
                    select(
                        func.count(),
                        func.coalesce(func.avg(QueryLog.latency_ms), 0.0),
                        func.coalesce(func.sum(QueryLog.cost_usd), 0.0),
                    ).where(*log_filter)
                )
            ).one()

            # SQLite cannot work out a percentile, so do it here.
            latencies = sorted(
                await session.scalars(select(QueryLog.latency_ms).where(*log_filter))
            )
            p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else 0

            questions = await session.execute(
                select(
                    func.coalesce(func.sum(case((OpenQuestion.status == "open", 1), else_=0)), 0),
                    func.coalesce(
                        func.sum(case((OpenQuestion.status == "answered", 1), else_=0)), 0
                    ),
                )
            )
            open_q, answered_q = questions.one()

            ratings = await session.execute(
                select(
                    func.coalesce(func.sum(case((Feedback.rating > 0, 1), else_=0)), 0),
                    func.coalesce(func.sum(case((Feedback.rating < 0, 1), else_=0)), 0),
                )
            )
            up, down = ratings.one()

        return Stats(
            total_queries=totals[0],
            by_outcome=by_outcome,
            avg_latency_ms=round(float(totals[1]), 1),
            p95_latency_ms=p95,
            total_cost_usd=round(float(totals[2]), 6),
            open_questions=int(open_q),
            answered_questions=int(answered_q),
            thumbs_up=int(up),
            thumbs_down=int(down),
        )
