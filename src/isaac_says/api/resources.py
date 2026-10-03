"""Sets up the API's database, saved conversations and agent when it starts, and closes them."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from isaac_says.agent.factory import build_chat_service
from isaac_says.api.deps import Resources
from isaac_says.api.limiter import SlidingWindowLimiter
from isaac_says.api.schemas import PostSummary
from isaac_says.config import Settings
from isaac_says.db.repository import Repository
from isaac_says.db.session import init_db, make_engine, make_session_factory
from isaac_says.ingestion.snapshot import load_snapshot

log = logging.getLogger(__name__)


def load_post_summaries(settings: Settings) -> list[PostSummary]:
    """Read the post list from the saved file (no database or network)."""
    try:
        posts = load_snapshot(settings.snapshot_path)
    except FileNotFoundError:
        log.warning(
            "No post snapshot found. /posts will be empty. Run `isaac-says ingest --refresh`."
        )
        return []
    return [
        PostSummary(
            slug=p.slug,
            title=p.title,
            subtitle=p.subtitle,
            published=p.post_date.date(),
            url=p.canonical_url,
            tags=p.tags,
            wordcount=p.wordcount,
        )
        for p in posts
    ]


@asynccontextmanager
async def build_resources(settings: Settings) -> AsyncIterator[Resources]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    engine = make_engine(settings.app_db_url)
    await init_db(engine)
    repo = Repository(make_session_factory(engine))

    # Save conversations, so they survive a restart.
    async with AsyncSqliteSaver.from_conn_string(str(settings.checkpoint_path)) as checkpointer:
        chat, index = build_chat_service(
            settings, checkpointer=checkpointer, gap_recorder=repo.record_open_question
        )
        if index.count() == 0:
            log.warning(
                "The search index is empty. Run `isaac-says ingest` before asking questions."
            )
        yield Resources(
            settings=settings,
            chat=chat,
            index=index,
            repo=repo,
            limiter=SlidingWindowLimiter(settings.rate_limit_per_minute),
            posts=load_post_summaries(settings),
        )

    await engine.dispose()
