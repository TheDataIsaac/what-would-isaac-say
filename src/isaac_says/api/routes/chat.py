"""The chat endpoints: ask, stream, feedback and delete a conversation."""

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from fastapi.responses import StreamingResponse

from isaac_says.agent.service import TurnResult
from isaac_says.api.deps import Resources, get_resources
from isaac_says.api.schemas import (
    THREAD_ID_PATTERN,
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
)
from isaac_says.api.security import daily_limit, rate_limit

log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"], dependencies=[Depends(rate_limit)])


async def _log_turn(resources: Resources, request_id: str, result: TurnResult) -> None:
    """Save a record of the turn. If saving fails, the chat still works."""
    try:
        await resources.repo.log_query(
            request_id=request_id,
            thread_id=result.thread_id,
            intent=result.intent,
            outcome=result.reply.kind,
            latency_ms=result.latency_ms,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            cost_usd=result.usage.cost_usd,
        )
    except Exception:
        log.exception("Could not write the query log")


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask a question or share work for review",
    dependencies=[Depends(daily_limit)],
)
async def chat(
    body: ChatRequest, request: Request, resources: Resources = Depends(get_resources)
) -> ChatResponse:
    """Send one message. The reply "kind" says what came back:

    * answer: an answer with checked quotes from the newsletter
    * review: feedback on the user's work, each point tied to a post
    * not_covered: the newsletter does not cover it (the question is saved)
    * needs_input: one more detail is needed. Send it as the next message with the same thread_id
    * chitchat: a greeting, or a question about the assistant
    """
    request_id = request.state.request_id
    result = await resources.chat.run_turn(body.thread_id, body.message)
    await _log_turn(resources, request_id, result)
    return ChatResponse(
        request_id=request_id,
        thread_id=result.thread_id,
        reply=result.reply,
        latency_ms=result.latency_ms,
    )


def _sse(event: str, data: dict) -> str:
    """Write one server-sent event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post(
    "/chat/stream",
    summary="Same as /chat, but streams progress as Server-Sent Events",
    dependencies=[Depends(daily_limit)],
)
async def chat_stream(
    body: ChatRequest, request: Request, resources: Resources = Depends(get_resources)
) -> StreamingResponse:
    """Send a "step" event as each step finishes, then one "reply" event.

    The reply is sent whole because its quotes are checked first. The step events show progress.
    """
    request_id = request.state.request_id

    async def events() -> AsyncIterator[str]:
        try:
            async for event in resources.chat.stream_turn(body.thread_id, body.message):
                if event["type"] == "step":
                    yield _sse("step", {"node": event["node"]})
                else:
                    usage = event.pop("usage")
                    intent = event.pop("intent")
                    payload = {**event, "request_id": request_id}
                    yield _sse("reply", payload)
                    await _log_stream_turn(resources, request_id, event, intent, usage)
        except Exception:
            log.exception("Streaming chat failed")
            yield _sse("error", {"detail": "Something went wrong. Please try again."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},  # no proxy buffering
    )


async def _log_stream_turn(
    resources: Resources, request_id: str, event: dict, intent: str, usage: dict
) -> None:
    try:
        await resources.repo.log_query(
            request_id=request_id,
            thread_id=event["thread_id"],
            intent=intent,
            outcome=event["reply"]["kind"],
            latency_ms=event["latency_ms"],
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cost_usd=usage["cost_usd"],
        )
    except Exception:
        log.exception("Could not write the query log")


@router.post("/feedback", status_code=status.HTTP_201_CREATED, summary="Rate a reply")
async def feedback(body: FeedbackRequest, resources: Resources = Depends(get_resources)) -> dict:
    saved = await resources.repo.add_feedback(body.request_id, body.rating, body.comment)
    if not saved:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown request_id.")
    return {"status": "saved"}


@router.delete(
    "/chat/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation and all of its stored messages",
)
async def delete_thread(
    thread_id: str = Path(pattern=THREAD_ID_PATTERN),
    resources: Resources = Depends(get_resources),
) -> Response:
    """Delete a saved conversation. A conversation that does not exist also returns 204."""
    await resources.chat.delete_thread(thread_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
