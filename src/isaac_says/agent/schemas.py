"""The shapes the model must answer in. The field descriptions are instructions to the model.

The Draft models are unchecked: verify.py checks their quotes before a reply is built.
"""

from typing import Literal

from pydantic import BaseModel, Field


class Route(BaseModel):
    intent: Literal["question", "review", "chitchat"] = Field(
        description="question: asks something a newsletter about data work might answer. "
        "review: shares their own work and wants feedback. "
        "chitchat: a greeting, thanks, or a question about the assistant itself."
    )


class SearchQuery(BaseModel):
    query: str = Field(description="A short standalone search query, at most 20 words.")


class SearchQueries(BaseModel):
    queries: list[str] = Field(
        description="2 to 4 short search queries. Each covers a DIFFERENT aspect of the user's work."
    )


class InfoCheck(BaseModel):
    enough_information: bool = Field(
        description="True if the message describes the work concretely enough to review."
    )
    clarifying_question: str = Field(
        description="One specific question to ask the user. Empty string if enough_information."
    )


class EvidenceGrade(BaseModel):
    relevant_chunk_ids: list[str] = Field(
        description="Ids of the excerpts that help with the request. Copy them exactly."
    )
    sufficient: bool = Field(
        description="True only if the relevant excerpts contain enough to respond well, "
        "using nothing but their content."
    )


class CitationDraft(BaseModel):
    chunk_id: str = Field(description="Id of the excerpt the quote comes from.")
    quote: str = Field(
        description="A short passage (at most 25 words) copied word for word from that excerpt."
    )


class AnswerDraft(BaseModel):
    answer: str = Field(description="The answer, in plain language, using only the excerpts.")
    citations: list[CitationDraft] = Field(
        description="1 to 4 quotes that support the answer. Empty only if the excerpts do not answer."
    )


class ReviewIssueDraft(BaseModel):
    title: str = Field(description="Short name for the issue, at most 8 words.")
    problem: str = Field(
        description="What is wrong or risky in the user's work, in one or two sentences."
    )
    advice: str = Field(description="What to change, in one or two sentences.")
    chunk_id: str = Field(
        description="Id of the excerpt that states the principle behind this issue."
    )
    quote: str = Field(
        description="A short passage (at most 25 words) copied word for word from that excerpt."
    )


class ReviewDraft(BaseModel):
    summary: str = Field(description="One or two sentences on what the work is trying to do.")
    strengths: list[str] = Field(
        description="Up to 3 things the work already does well. May be empty."
    )
    issues: list[ReviewIssueDraft] = Field(
        description="Between 1 and 4 issues, most important first."
    )
    next_step: str = Field(description="The single most useful thing to do next.")
