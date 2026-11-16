"""The judge: a second model that grades each newsletter answer.

The assistant already checks that every quote really appears in the newsletter. That doesn't show
the answer as a whole is right. The judge reads the question, the excerpts the answer was written
from and the answer, then makes two yes/no checks.
"""

from langchain_core.callbacks import get_usage_metadata_callback
from pydantic import BaseModel, Field

from isaac_says.agent.llm import OpenAIClient
from isaac_says.agent.nodes import format_excerpts
from isaac_says.config import Settings
from isaac_says.domain.models import RetrievedChunk

# A different and stronger model than the assistant's. A model grading its own answers tends to
# agree with itself.
JUDGE_MODEL = "gpt-6.1-terra"
INPUT_PRICE_PER_M = 1.00  # USD per million tokens, only used to estimate the cost
OUTPUT_PRICE_PER_M = 5.00

INSTRUCTIONS = """You are grading an AI assistant. It answers questions about data work using \
only excerpts from Isaac's newsletter. You get the user's question, the excerpts the assistant was \
given, and its answer.

Make two checks:
1. answers_question: does the answer respond to what the user actually asked? An answer about a \
related topic that never addresses the question fails. An answer that covers only part of the \
question passes if what it says is useful for that question.
2. grounded: is every claim, piece of advice and example in the answer stated in, or clearly \
implied by, the excerpts? Rewording and summarising are fine. Anything added from general \
knowledge fails, even if it is true. Naming Isaac's posts by title is fine.

Judge only these two things, not the writing style.
In reason, quote the unsupported claim or name the part of the question that was missed. If both \
checks pass, say so in a few words."""


class Verdict(BaseModel):
    """The judge's answer. The field descriptions are instructions to the judge."""

    answers_question: bool = Field(description="True if the answer responds to what was asked.")
    grounded: bool = Field(description="True if everything in the answer is in the excerpts.")
    reason: str = Field(description="One or two sentences explaining the checks.")

    @property
    def passed(self) -> bool:
        return self.answers_question and self.grounded


def make_judge(settings: Settings) -> OpenAIClient:
    """The same client the assistant uses, pointed at the judge's model."""
    judge_settings = settings.model_copy(
        update={"llm_model": JUDGE_MODEL, "reasoning_effort": "low"}
    )
    return OpenAIClient(judge_settings)


async def judge_answer(
    judge: OpenAIClient, question: str, answer: str, excerpts: list[RetrievedChunk]
) -> tuple[Verdict, float]:
    """Grade one answer. Returns the verdict and the estimated cost of grading it in USD."""
    user = f"Question:\n{question}\n\nExcerpts:\n{format_excerpts(excerpts)}\n\nAnswer:\n{answer}"
    # Counts the tokens of the calls made inside the with block.
    with get_usage_metadata_callback() as usage:
        verdict = await judge.structured(Verdict, INSTRUCTIONS, user, long_output=True)
    tokens_in = sum(m.get("input_tokens", 0) for m in usage.usage_metadata.values())
    tokens_out = sum(m.get("output_tokens", 0) for m in usage.usage_metadata.values())
    cost = (tokens_in * INPUT_PRICE_PER_M + tokens_out * OUTPUT_PRICE_PER_M) / 1_000_000
    return verdict, cost
