"""The steps of the agent. Each step reads the state and returns the parts it changes.

graph.py decides the order the steps run in.
"""

import asyncio
from collections.abc import Awaitable, Callable

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.types import interrupt

from isaac_says.agent import prompts
from isaac_says.agent.llm import OpenAIClient
from isaac_says.agent.schemas import (
    AnswerDraft,
    EvidenceGrade,
    InfoCheck,
    ReviewDraft,
    Route,
    SearchQueries,
    SearchQuery,
)
from isaac_says.agent.state import AgentState
from isaac_says.agent.style import clean_prose
from isaac_says.agent.verify import locate_quote
from isaac_says.config import Settings
from isaac_says.domain.models import RetrievedChunk
from isaac_says.domain.replies import (
    AnswerReply,
    ChitchatReply,
    NotCoveredReply,
    ReviewIssue,
    ReviewReply,
    SourceCitation,
)
from isaac_says.retrieval.index import VectorIndex

# Saves a question the newsletter cannot answer, and returns its id (or None).
GapRecorder = Callable[[str], Awaitable[int | None]]

MAX_REVIEW_CANDIDATES = 12  # most chunks kept when searching for a review
MAX_CLARIFICATIONS = 2  # most follow-up questions asked for one review
HISTORY_MESSAGES = 6  # how many recent messages the query rewriter sees


# Small helpers
def _last_user_text(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if message.type == "human":
            return str(message.content)
    return ""


def _transcript(messages: list[AnyMessage], limit: int = HISTORY_MESSAGES) -> str:
    lines = []
    for m in messages[-limit:]:
        role = "User" if m.type == "human" else "Assistant"
        lines.append(f"{role}: {str(m.content)[:600]}")
    return "\n".join(lines)


def _standalone_question(state: AgentState) -> str:
    """The question on its own, with words like "it" spelled out. Falls back to the raw message."""
    queries = state.get("queries") or []
    return queries[0] if queries else _last_user_text(state)


def _request_context(state: AgentState) -> str:
    """Describe what the user is asking, with enough of the conversation to judge it."""
    if state["intent"] == "review":
        return f"The user's messages about their work:\n{_transcript(state['messages'], limit=10)}"
    latest = _last_user_text(state)
    standalone = _standalone_question(state)
    if standalone == latest:
        return f"Question: {latest}"
    return f"Question: {latest}\nStandalone version: {standalone}"


def format_excerpts(chunks: list[RetrievedChunk]) -> str:
    """Write the chunks as numbered excerpts, so the model can say which one a quote is from."""
    blocks = [
        f"[chunk_id: {r.chunk.chunk_id}] {r.chunk.title} > {r.chunk.heading}\n{r.chunk.text}"
        for r in chunks
    ]
    return "\n\n---\n\n".join(blocks)


def _to_citation(quote: str, chunk: RetrievedChunk) -> SourceCitation:
    c = chunk.chunk
    return SourceCitation(
        chunk_id=c.chunk_id,
        title=c.title,
        heading=c.heading,
        url=c.url,
        quote=quote.strip(),
        source_type=c.source_type,
    )


def _finish(reply: ReviewReply | AnswerReply | NotCoveredReply | ChitchatReply, text: str, **extra):
    """Save the reply and add it to the chat history. Every final step ends this way."""
    return {"reply": reply.model_dump(), "messages": [AIMessage(content=text)], **extra}


class AgentNodes:
    def __init__(
        self,
        llm: OpenAIClient,
        retriever: VectorIndex,
        settings: Settings,
        gap_recorder: GapRecorder | None = None,
    ) -> None:
        self.llm = llm
        self.retriever = retriever
        self.settings = settings
        self.gap_recorder = gap_recorder

    # 1. Understand the message
    async def route(self, state: AgentState):
        """Decide what kind of message it is, and clear the values left from the last turn."""
        text = _last_user_text(state)
        decision = await self.llm.structured(Route, prompts.ROUTER, text)
        return {
            "intent": decision.intent,
            "clarifications": 0,
            "queries": [],
            "candidates": [],
            "relevant": [],
            "draft": {},
            "reply": {},
        }

    async def chitchat(self, state: AgentState):
        text = clean_prose(await self.llm.text(prompts.CHITCHAT, _last_user_text(state)))
        return _finish(ChitchatReply(text=text), text)

    # 2. For reviews, check there is enough detail
    async def info_check(self, state: AgentState):
        if state["clarifications"] >= MAX_CLARIFICATIONS:
            return {"pending_question": ""}  # asked enough already, so go ahead
        check = await self.llm.structured(
            InfoCheck, prompts.INFO_CHECK, _transcript(state["messages"], limit=10)
        )
        if check.enough_information or not check.clarifying_question.strip():
            return {"pending_question": ""}
        return {"pending_question": clean_prose(check.clarifying_question)}

    async def ask_user(self, state: AgentState):
        """Pause and wait for the user to answer the follow-up question.

        interrupt() saves the state and stops. When the user replies, this step runs again from the
        top and interrupt() returns their answer.
        """
        question = state["pending_question"]
        answer = interrupt({"question": question})
        return {
            "messages": [AIMessage(content=question), HumanMessage(content=str(answer))],
            "clarifications": state["clarifications"] + 1,
            "pending_question": "",
        }

    # 3. Find the evidence
    async def rewrite_query(self, state: AgentState):
        text = _last_user_text(state)
        is_review = state["intent"] == "review"
        has_history = len(state["messages"]) > 1
        if is_review:
            # One search per part of the work. A single search only finds the most obvious point.
            planned = await self.llm.structured(
                SearchQueries, prompts.REWRITE_REVIEW, _transcript(state["messages"], limit=10)
            )
            queries = [q.strip() for q in planned.queries if q.strip()][:4]
            return {"queries": queries or [text[:300]]}
        if not has_history:
            return {"queries": [text]}  # the first message needs no rewrite, which saves a call
        rewritten = await self.llm.structured(
            SearchQuery, prompts.REWRITE_QUESTION, _transcript(state["messages"])
        )
        return {"queries": [rewritten.query.strip() or text]}

    async def retrieve(self, state: AgentState):
        is_review = state["intent"] == "review"
        k = self.settings.review_top_k if is_review else self.settings.retrieval_top_k
        batches = await asyncio.gather(*(self.retriever.asearch(q, k) for q in state["queries"]))
        # Combine the results, keeping each chunk once with its best score.
        best: dict[str, RetrievedChunk] = {}
        for result in (r for batch in batches for r in batch):
            known = best.get(result.chunk.chunk_id)
            if known is None or result.score > known.score:
                best[result.chunk.chunk_id] = result
        ranked = sorted(best.values(), key=lambda r: r.score, reverse=True)
        limit = MAX_REVIEW_CANDIDATES if is_review else k
        # Drop weak matches before the model sees them.
        kept = [r for r in ranked[:limit] if r.score >= self.settings.min_relevance_score]
        return {"candidates": [r.model_dump() for r in kept]}

    async def grade(self, state: AgentState):
        """Ask the model if the excerpts are enough to answer. If not, keep none of them."""
        candidates = [RetrievedChunk.model_validate(c) for c in state["candidates"]]
        user = f"Request:\n{_request_context(state)}\n\nExcerpts:\n{format_excerpts(candidates)}"
        grade = await self.llm.structured(EvidenceGrade, prompts.GRADE, user)
        wanted = set(grade.relevant_chunk_ids)
        relevant = [c for c in candidates if c.chunk.chunk_id in wanted]
        if not grade.sufficient:
            relevant = []
        return {"relevant": [r.model_dump() for r in relevant]}

    # 4. Write the reply
    async def write_answer(self, state: AgentState):
        relevant = [RetrievedChunk.model_validate(c) for c in state["relevant"]]
        user = f"{_request_context(state)}\n\nExcerpts:\n{format_excerpts(relevant)}"
        draft = await self.llm.structured(AnswerDraft, prompts.ANSWER, user, long_output=True)
        return {"draft": draft.model_dump()}

    async def write_review(self, state: AgentState):
        relevant = [RetrievedChunk.model_validate(c) for c in state["relevant"]]
        user = (
            f"The user's messages about their work:\n{_transcript(state['messages'], limit=10)}\n\n"
            f"Excerpts:\n{format_excerpts(relevant)}"
        )
        draft = await self.llm.structured(ReviewDraft, prompts.REVIEW, user, long_output=True)
        return {"draft": draft.model_dump()}

    # 5. Check the quotes, then reply
    async def verify(self, state: AgentState):
        """Keep only the quotes that really appear in the source. With none left, refuse."""
        relevant = [RetrievedChunk.model_validate(c) for c in state["relevant"]]
        if state["intent"] == "review":
            return await self._verify_review(state, relevant)
        return await self._verify_answer(state, relevant)

    async def _verify_answer(self, state: AgentState, relevant: list[RetrievedChunk]):
        draft = AnswerDraft.model_validate(state["draft"])
        citations: list[SourceCitation] = []
        for c in draft.citations:
            found = locate_quote(c.quote, c.chunk_id, relevant)
            if found is None:
                continue  # the quote is not in any source
            if any(x.chunk_id == found.chunk.chunk_id for x in citations):
                continue  # that chunk is already cited
            citations.append(_to_citation(c.quote, found))
        if not citations:
            return await self._refuse(state)
        answer = clean_prose(draft.answer)
        return _finish(AnswerReply(text=answer, citations=citations), answer)

    async def _verify_review(self, state: AgentState, relevant: list[RetrievedChunk]):
        draft = ReviewDraft.model_validate(state["draft"])
        issues: list[ReviewIssue] = []
        for issue in draft.issues:
            found = locate_quote(issue.quote, issue.chunk_id, relevant)
            if found:  # an issue with no real quote behind it is dropped
                issues.append(
                    ReviewIssue(
                        title=clean_prose(issue.title),
                        problem=clean_prose(issue.problem),
                        advice=clean_prose(issue.advice),
                        citation=_to_citation(issue.quote, found),
                    )
                )
        if not issues:
            return await self._refuse(state)
        summary, next_step = clean_prose(draft.summary), clean_prose(draft.next_step)
        reply = ReviewReply(
            summary=summary,
            strengths=[clean_prose(s) for s in draft.strengths],
            issues=issues,
            next_step=next_step,
        )
        return _finish(reply, f"{summary} Next step: {next_step}")

    async def not_covered(self, state: AgentState):
        return await self._refuse(state)

    async def _refuse(self, state: AgentState):
        """Say the newsletter does not cover this, and save the question for Isaac."""
        question_id = None
        # Reviews hold the user's own work, so they are never saved. A follow-up question is
        # saved in full, as the question it refers to.
        if state["intent"] == "question" and self.gap_recorder is not None:
            question_id = await self.gap_recorder(_standalone_question(state))
        saved = prompts.NOT_COVERED_SAVED if question_id else prompts.NOT_COVERED_NOT_SAVED
        text = prompts.NOT_COVERED.format(saved=saved)
        return _finish(NotCoveredReply(text=text, question_id=question_id), text)
