"""Sends a trace of each chat turn to Langfuse, when Langfuse keys are set.

A trace is the record of one turn: which graph steps ran and in what order, the prompt and reply
of every model call, the tokens and cost of each call, and how long each step took. Turns from the
same conversation share a session id, so Langfuse can show a whole conversation together.

LangGraph reports every step it runs to "callbacks". Langfuse's CallbackHandler is one of those
callbacks: it turns the steps into a trace and sends it from a background thread, so a visitor
never waits for it.
"""

from contextlib import AbstractContextManager, nullcontext

from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler

from isaac_says.config import Settings


class Tracer:
    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.langfuse_public_key and settings.langfuse_secret_key)
        self._public_key = settings.langfuse_public_key
        if self.enabled:
            # Creating the client once is enough. Each CallbackHandler finds it by its public key.
            # Traces waiting to be sent are sent when the program exits.
            Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key.get_secret_value(),
                base_url=settings.langfuse_base_url,
            )

    def callbacks(self) -> list[CallbackHandler]:
        """The callbacks for one turn. A new handler each time, so turns running at the same time
        don't mix their steps up."""
        if not self.enabled:
            return []
        return [CallbackHandler(public_key=self._public_key)]

    def turn(self, thread_id: str) -> AbstractContextManager:
        """Name the trace and attach it to its conversation."""
        if not self.enabled:
            return nullcontext()
        return propagate_attributes(trace_name="chat turn", session_id=thread_id)
