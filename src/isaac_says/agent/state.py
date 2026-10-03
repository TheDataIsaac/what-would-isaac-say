"""The data that moves through the graph. It is saved after every step, so it holds plain dicts."""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    # Kept across turns (the conversation so far).
    messages: Annotated[list[AnyMessage], add_messages]

    # Reset at the start of every turn.
    intent: str  # "question" | "review" | "chitchat"
    clarifications: int  # follow-up questions asked this turn
    pending_question: str  # the follow-up question waiting for an answer, if any
    queries: list[str]  # search queries (one for a question, several for a review)
    candidates: list[dict]  # chunks that passed the similarity cutoff
    relevant: list[dict]  # the chunks the grader approved
    draft: dict  # the model's answer or review, before its quotes are checked
    reply: dict  # the final reply
