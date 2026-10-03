"""Creates the database connection."""

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from isaac_says.db.models import Base


def make_engine(url: str) -> AsyncEngine:
    if url.startswith("sqlite"):
        # The folder has to exist before SQLite can create the file in it.
        Path(url.split("///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(url)

    if url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            # WAL mode lets reads happen while something is being written.
            cursor.execute("PRAGMA journal_mode=WAL")
            # SQLite only checks foreign keys if this is switched on.
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # Keeps objects readable after a save, which async sessions need.
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    """Create any missing tables. Existing tables and data are left alone."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
