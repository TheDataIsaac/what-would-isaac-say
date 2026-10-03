"""The search index, stored in Chroma. Chunks are embedded once, and each question is embedded
when it is asked, then matched by similarity (1.0 is identical, 0.0 is unrelated).
"""

import asyncio
from collections.abc import Sequence
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from isaac_says.domain.models import Chunk, RetrievedChunk, SourceType

COLLECTION_NAME = "isaac_says"
BATCH_SIZE = 100  # chunks per embedding request


class VectorIndex:
    def __init__(self, persist_dir: Path, embeddings: Embeddings) -> None:
        self._store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=str(persist_dir),
            # Use cosine distance, so scores read as similarity.
            collection_metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, chunks: Sequence[Chunk]) -> None:
        """Add the chunks, replacing any with the same chunk_id."""
        for start in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[start : start + BATCH_SIZE]
            self._store.add_documents(
                documents=[
                    Document(
                        page_content=c.embedding_text, metadata=c.to_metadata() | {"text": c.text}
                    )
                    for c in batch
                ],
                ids=[c.chunk_id for c in batch],
            )

    def delete(self, chunk_ids: Sequence[str]) -> None:
        if chunk_ids:
            self._store.delete(ids=list(chunk_ids))

    def ids_for(self, source_type: SourceType) -> set[str]:
        """All chunk ids of one source type. Used to remove chunks that no longer exist."""
        found = self._store.get(where={"source_type": source_type}, include=[])
        return set(found["ids"])

    def count(self) -> int:
        return self._store._collection.count()

    def search(self, query: str, k: int) -> list[RetrievedChunk]:
        """The k most similar chunks, best first."""
        results = self._store.similarity_search_with_score(query, k=k)
        return [
            RetrievedChunk(
                chunk=Chunk.from_metadata(
                    chunk_id=doc.id or "",
                    text=doc.metadata["text"],
                    meta=doc.metadata,
                ),
                score=round(1.0 - distance, 4),  # turn distance into similarity
            )
            for doc, distance in results
        ]

    async def asearch(self, query: str, k: int) -> list[RetrievedChunk]:
        """Same as search, but runs in a separate thread so the server is not blocked."""
        return await asyncio.to_thread(self.search, query, k)
