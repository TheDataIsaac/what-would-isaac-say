"""Tests for when the agent refuses. None of these call the model."""

import asyncio

from isaac_says.agent.graph import _after_grade, _has_candidates
from isaac_says.agent.nodes import AgentNodes
from isaac_says.domain.models import Chunk, RetrievedChunk

SOURCE = "A dual axis chart lets the reader compare two scales, but it often misleads them."


def answer_state(quotes: list[str]) -> dict:
    """The graph state just before the verify step, with a draft answer citing these quotes."""
    chunk = Chunk(chunk_id="dual-axis#0", title="Dual axis", heading="Intro", text=SOURCE)
    return {
        "intent": "question",
        "relevant": [RetrievedChunk(chunk=chunk, score=0.8).model_dump()],
        "draft": {
            "answer": "Use them with care.",
            "citations": [{"chunk_id": "dual-axis#0", "quote": q} for q in quotes],
        },
    }


def run_verify(state: dict) -> dict:
    # The verify step only checks text, so it needs no model, search index or settings.
    nodes = AgentNodes(llm=None, retriever=None, settings=None)
    return asyncio.run(nodes.verify(state))["reply"]


def test_no_search_results_goes_straight_to_refusal():
    """If nothing passes the similarity cutoff, the agent refuses without calling the model."""
    assert _has_candidates({"candidates": []}) == "not_covered"


def test_grader_saying_no_leads_to_refusal():
    """If the grader keeps no excerpts, the agent refuses instead of writing an answer."""
    assert _after_grade({"intent": "question", "relevant": []}) == "not_covered"


def test_approved_evidence_goes_to_the_right_writer():
    """Questions go to the answer writer and reviews go to the review writer."""
    assert _after_grade({"intent": "question", "relevant": [{}]}) == "write_answer"
    assert _after_grade({"intent": "review", "relevant": [{}]}) == "write_review"


def test_invented_quote_is_removed_and_real_one_kept():
    """The reply keeps only the quote that is really in the source."""
    reply = run_verify(answer_state(["it often misleads them", "dual axis charts are always fine"]))
    assert reply["kind"] == "answer"
    assert [c["quote"] for c in reply["citations"]] == ["it often misleads them"]


def test_answer_with_only_invented_quotes_becomes_a_refusal():
    """With no real quote left, the answer is replaced by "not covered"."""
    reply = run_verify(answer_state(["dual axis charts are always fine"]))
    assert reply["kind"] == "not_covered"
