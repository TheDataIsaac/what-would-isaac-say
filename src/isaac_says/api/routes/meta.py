"""Read-only endpoints about the service and the newsletter it knows."""

from fastapi import APIRouter, Depends, Query

import isaac_says
from isaac_says.api.deps import Resources, get_resources
from isaac_says.api.schemas import HealthResponse, PostSummary

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthResponse, summary="Is the service up and loaded?")
async def health(resources: Resources = Depends(get_resources)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        indexed_chunks=resources.index.count(),
        model=resources.settings.llm_model,
        version=isaac_says.__version__,
    )


@router.get(
    "/posts", response_model=list[PostSummary], summary="The newsletter posts the assistant knows"
)
async def posts(
    tag: str | None = Query(default=None, description="Only posts with this tag"),
    resources: Resources = Depends(get_resources),
) -> list[PostSummary]:
    found = resources.posts
    if tag:
        found = [p for p in found if tag.lower() in (t.lower() for t in p.tags)]
    return sorted(found, key=lambda p: p.published, reverse=True)
