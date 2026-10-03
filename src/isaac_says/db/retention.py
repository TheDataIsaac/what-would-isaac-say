"""Deletes old conversations.

Conversations are saved so they can continue after a restart. A visitor can delete their own
(DELETE /chat/{thread_id}), and conversations that sit idle are removed after thread_retention_days.
"""

import logging
from datetime import timedelta

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from isaac_says.config import Settings
from isaac_says.db.models import utcnow
from isaac_says.db.repository import Repository
from isaac_says.db.session import init_db, make_engine, make_session_factory

log = logging.getLogger(__name__)


async def purge_stale_threads(settings: Settings, days: int | None = None) -> int:
    """Delete conversations with no activity for the given number of days.

    Returns how many were deleted. The question queue, feedback and logs are kept.
    """
    days = days if days is not None else settings.thread_retention_days
    cutoff = utcnow() - timedelta(days=days)

    engine = make_engine(settings.app_db_url)
    try:
        await init_db(engine)
        stale = await Repository(make_session_factory(engine)).stale_thread_ids(cutoff)
        if stale:
            async with AsyncSqliteSaver.from_conn_string(str(settings.checkpoint_path)) as saver:
                for thread_id in stale:
                    await saver.adelete_thread(thread_id)
    finally:
        await engine.dispose()
    log.info("Purged %d conversation(s) idle for more than %d days", len(stale), days)
    return len(stale)
