"""Admin endpoints for the question queue and usage numbers. They need the X-API-Key header.

An answer sent here is added to the search index, so later readers get it with a citation.
"""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from isaac_says.api.deps import Resources, get_resources
from isaac_says.api.schemas import AnswerRequest, OpenQuestionOut, StatsOut
from isaac_says.api.security import require_admin
from isaac_says.domain.models import Chunk

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/questions", response_model=list[OpenQuestionOut], summary="Questions readers asked")
async def list_questions(
    status_filter: Literal["open", "answered"] = Query(default="open", alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    resources: Resources = Depends(get_resources),
) -> list[OpenQuestionOut]:
    rows = await resources.repo.list_questions(status_filter, limit)
    return [OpenQuestionOut.model_validate(r) for r in rows]


@router.post(
    "/questions/{question_id}/answer",
    response_model=OpenQuestionOut,
    summary="Answer a question and add the answer to the knowledge base",
)
async def answer_question(
    question_id: int, body: AnswerRequest, resources: Resources = Depends(get_resources)
) -> OpenQuestionOut:
    question = await resources.repo.get_question(question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown question id.")

    chunk = Chunk.from_isaac_answer(question.id, question.question, body.answer)
    # Indexing calls the embedding API, so it runs in a separate thread. It happens before the
    # question is marked answered, so if it fails the question stays open.
    await asyncio.to_thread(resources.index.upsert, [chunk])
    updated = await resources.repo.mark_answered(question.id, body.answer, chunk.chunk_id)
    return OpenQuestionOut.model_validate(updated)


@router.get("/stats", response_model=StatsOut, summary="Usage, cost, latency and feedback")
async def stats(resources: Resources = Depends(get_resources)) -> StatsOut:
    return StatsOut(**vars(await resources.repo.stats()))
