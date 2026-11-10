"""Asks the assistant every question in questions.jsonl and counts how many it handled correctly.

Run it from the project folder with `uv run python evals/run_eval.py`. It uses the real model and
search index, so it needs OPENAI_API_KEY in .env and a built index (`uv run isaac-says ingest`).
The table is printed and saved to evals/results.md.
"""

import asyncio
import json
from datetime import date
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from isaac_says.agent.factory import build_chat_service
from isaac_says.agent.service import ChatService
from isaac_says.config import get_settings

EVALS_DIR = Path(__file__).parent

# For each category: the reply kind that counts as correct, and the row label in the table.
EXPECTED = {
    "in_scope": ("answer", "Newsletter questions answered"),
    "out_of_scope": ("not_covered", "Unrelated questions refused"),
    "adjacent": ("not_covered", "Near-topic questions refused"),
    "review": ("review", "Review requests reviewed"),
}

# A review request can get a follow-up question. This is the reply of a reader with nothing to add.
NO_MORE_DETAIL = "That is all the detail I have. Please go ahead and review it based on that."
MAX_FOLLOW_UPS = 2  # the agent asks at most two follow-up questions before it reviews anyway


async def ask(service: ChatService, question: str, costs: list[float]) -> str:
    """Ask one question in a new conversation and return the reply kind.
    Each turn's cost is added to `costs` straight away, so it still counts if a later turn fails."""
    result = await service.run_turn(None, question)
    costs.append(result.usage.cost_usd)
    for _ in range(MAX_FOLLOW_UPS):
        if result.reply.kind != "needs_input":
            break
        result = await service.run_turn(result.thread_id, NO_MORE_DETAIL)
        costs.append(result.usage.cost_usd)
    return result.reply.kind


async def main() -> None:
    settings = get_settings()
    # Set up like the `ask` command: memory only, and unanswered questions are not saved.
    service, _ = build_chat_service(settings, checkpointer=InMemorySaver())
    lines = (EVALS_DIR / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    questions = [json.loads(line) for line in lines if line.strip()]

    correct = dict.fromkeys(EXPECTED, 0)
    totals = dict.fromkeys(EXPECTED, 0)
    misses = []
    errors = 0
    costs = []
    for number, item in enumerate(questions, 1):
        category = item["category"]
        try:
            kind = await ask(service, item["question"], costs)
        except Exception as error:  # one failed API call should not stop a long run
            # The failed call's cost is unknown, but turns that already finished stay counted.
            kind = f"error: {type(error).__name__}"
            errors += 1
        totals[category] += 1
        if kind == EXPECTED[category][0]:
            correct[category] += 1
        else:
            misses.append(f"- `{item['id']}` got `{kind}`: {item['question']}")
        print(f"{number}/{len(questions)} {item['id']}: {kind}")

    report = [
        "# Evaluation results",
        "",
        f"Run on {date.today().isoformat()} with `{settings.llm_model}` "
        f"(reasoning: {settings.reasoning_effort}). Estimated model cost: ${sum(costs):.2f}.",
        f"Questions that failed with an API error (counted as misses): {errors}.",
        "",
        "| What it should do | Result |",
        "|---|---|",
        *[f"| {label} | {correct[c]}/{totals[c]} |" for c, (_, label) in EXPECTED.items()],
        "",
        "## Misses",
        "",
        *(misses or ["None."]),
        "",
    ]
    text = "\n".join(report)
    (EVALS_DIR / "results.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
