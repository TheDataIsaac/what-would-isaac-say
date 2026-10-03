"""The chat model client.

There are two clients with different timeouts. Some requests stall for 40 to 60 seconds but work
when retried, so short calls get a short timeout and long answers get a longer one.
"""

from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from isaac_says.config import Settings

T = TypeVar("T", bound=BaseModel)


class OpenAIClient:
    def __init__(self, settings: Settings) -> None:
        common = {
            "model": settings.llm_model,
            "api_key": settings.require_openai_key(),
            "use_responses_api": True,  # this model needs the Responses API
            "reasoning": {"effort": settings.reasoning_effort},
            "max_retries": 2,
        }
        self._short = ChatOpenAI(timeout=settings.llm_timeout_seconds, **common)
        self._long = ChatOpenAI(timeout=settings.llm_long_timeout_seconds, **common)

    async def structured(
        self, schema: type[T], system: str, user: str, *, long_output: bool = False
    ) -> T:
        """Ask the model to answer in the shape of schema. Use long_output for long answers."""
        model = self._long if long_output else self._short
        runnable = model.with_structured_output(schema)
        return await runnable.ainvoke([SystemMessage(system), HumanMessage(user)])

    async def text(self, system: str, user: str) -> str:
        """Ask the model for plain text."""
        response = await self._short.ainvoke([SystemMessage(system), HumanMessage(user)])
        return response.text
