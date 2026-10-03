"""Builds the search index from the newsletter posts.

    Substack  ->  saved file  ->  clean and split  ->  embed  ->  Chroma
    (only with --refresh)

It is safe to run again: chunks are replaced by id, and chunks that no longer exist are removed.
Answers Isaac wrote in the admin queue are left alone.
"""

import logging
from dataclasses import dataclass

from langchain_core.embeddings import Embeddings

from isaac_says.config import Settings
from isaac_says.domain.models import Chunk, RawPost
from isaac_says.ingestion.chunking import chunk_post
from isaac_says.ingestion.snapshot import load_snapshot, save_snapshot
from isaac_says.ingestion.substack import SubstackClient
from isaac_says.retrieval.index import VectorIndex

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestReport:
    posts: int
    chunks: int
    removed_stale: int
    downloaded: bool


def build_chunks(posts: list[RawPost]) -> list[Chunk]:
    return [chunk for post in posts for chunk in chunk_post(post)]


def run_ingest(settings: Settings, embeddings: Embeddings, *, refresh: bool) -> IngestReport:
    """Build or update the index. With refresh, download the posts from Substack first."""
    if refresh:
        posts = SubstackClient(settings.substack_publication).fetch_all()
        save_snapshot(posts, settings.snapshot_path)
        log.info("Saved %d posts to %s", len(posts), settings.snapshot_path)
    else:
        posts = load_snapshot(settings.snapshot_path)

    chunks = build_chunks(posts)
    index = VectorIndex(settings.chroma_dir, embeddings)

    # Remove chunks that the current posts no longer produce.
    stale = index.ids_for("post") - {c.chunk_id for c in chunks}
    index.delete(sorted(stale))
    index.upsert(chunks)
    log.info(
        "Indexed %d chunks from %d posts (%d stale removed)", len(chunks), len(posts), len(stale)
    )

    return IngestReport(
        posts=len(posts), chunks=len(chunks), removed_stale=len(stale), downloaded=refresh
    )
