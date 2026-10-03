"""Runs one conversation turn through the graph. The API and the command line both use this."""

import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from isaac_says.config import Settings
from isaac_says.domain.replies import NeedsInputReply, Reply, ReplyAdapter


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class TurnResult:
    thread_id: str
    reply: Reply
    latency_ms: int
    usage: Usage = field(default_factory=Usage)
    intent: str = ""


class ChatService:
    def __init__(self, graph: CompiledStateGraph, settings: Settings) -> None:
        self._graph = graph
        self._settings = settings

    # Helpers
    @staticmethod
    def _config(thread_id: str) -> dict:
        # The thread id picks which saved conversation to use.
        return {"configurable": {"thread_id": thread_id}}

    async def _payload(self, thread_id: str, message: str):
        """Continue if the graph is waiting for an answer, otherwise start a new turn."""
        state = await self._graph.aget_state(self._config(thread_id))
        paused = any(task.interrupts for task in state.tasks)
        if paused:
            return Command(resume=message)
        return {"messages": [HumanMessage(content=message)]}

    async def _read_result(self, thread_id: str, started: float, usage: Usage) -> TurnResult:
        state = await self._graph.aget_state(self._config(thread_id))
        interrupts = [i for task in state.tasks for i in task.interrupts]
        if interrupts:  # waiting for the user's answer
            reply: Reply = NeedsInputReply(question=interrupts[0].value["question"])
        else:
            reply = ReplyAdapter.validate_python(state.values["reply"])
        return TurnResult(
            thread_id=thread_id,
            reply=reply,
            latency_ms=int((time.perf_counter() - started) * 1000),
            usage=usage,
            intent=state.values.get("intent", ""),
        )

    def _usage_from(self, metadata: dict) -> Usage:
        """Add up the tokens used in this turn and estimate the cost."""
        inp = sum(m.get("input_tokens", 0) for m in metadata.values())
        out = sum(m.get("output_tokens", 0) for m in metadata.values())
        cost = (
            inp * self._settings.llm_input_price_per_m + out * self._settings.llm_output_price_per_m
        ) / 1_000_000
        return Usage(input_tokens=inp, output_tokens=out, cost_usd=round(cost, 6))

    # Used by the API and the command line
    async def delete_thread(self, thread_id: str) -> None:
        """Delete a saved conversation and all its messages."""
        checkpointer = self._graph.checkpointer
        if checkpointer:  # there is none when the graph has no saved state
            await checkpointer.adelete_thread(thread_id)

    async def run_turn(self, thread_id: str | None, message: str) -> TurnResult:
        thread_id = thread_id or uuid.uuid4().hex
        started = time.perf_counter()
        payload = await self._payload(thread_id, message)
        with get_usage_metadata_callback() as usage_callback:
            await self._graph.ainvoke(payload, self._config(thread_id))
        usage = self._usage_from(usage_callback.usage_metadata)
        return await self._read_result(thread_id, started, usage)

    async def stream_turn(self, thread_id: str | None, message: str) -> AsyncIterator[dict]:
        """Yield a "step" event as each step finishes, then one "reply" event with the answer."""
        thread_id = thread_id or uuid.uuid4().hex
        started = time.perf_counter()
        payload = await self._payload(thread_id, message)
        with get_usage_metadata_callback() as usage_callback:
            # "updates" mode gives one item per finished step.
            async for update in self._graph.astream(
                payload, self._config(thread_id), stream_mode="updates"
            ):
                for node in update:
                    if not node.startswith("__"):  # skip the internal "__interrupt__" item
                        yield {"type": "step", "node": node}
        usage = self._usage_from(usage_callback.usage_metadata)
        result = await self._read_result(thread_id, started, usage)
        yield {
            "type": "reply",
            "thread_id": result.thread_id,
            "reply": result.reply.model_dump(mode="json"),
            "latency_ms": result.latency_ms,
            "intent": result.intent,
            "usage": {
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "cost_usd": result.usage.cost_usd,
            },
        }
