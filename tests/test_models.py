"""Tests for the Pydantic reply models that the API and saved conversations rely on."""

import pytest
from pydantic import ValidationError

from isaac_says.domain.replies import AnswerReply, NotCoveredReply, ReplyAdapter


def test_saved_reply_comes_back_as_the_right_type():
    """The "kind" field decides which reply class a saved dict becomes."""
    assert isinstance(
        ReplyAdapter.validate_python({"kind": "not_covered", "text": "No."}), NotCoveredReply
    )
    answer = ReplyAdapter.validate_python({"kind": "answer", "text": "Yes.", "citations": []})
    assert isinstance(answer, AnswerReply)


def test_unknown_or_incomplete_reply_is_rejected():
    """A reply with an unknown kind, or a missing field, fails loudly."""
    with pytest.raises(ValidationError):
        ReplyAdapter.validate_python({"kind": "poem", "text": "Roses are red."})
    with pytest.raises(ValidationError):
        ReplyAdapter.validate_python({"kind": "answer", "text": "No citations field."})
