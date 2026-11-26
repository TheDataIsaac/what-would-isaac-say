"""Asks the assistant every question in questions.jsonl several times and checks every reply.

Each reply gets two checks:
1. Its kind: did the assistant answer, refuse or review when it should have?
2. For newsletter answers, the judge (judge.py): does the answer address the question, using only
   what the newsletter says?

Asking more than once shows which questions get a different result each time.

Run it from the project folder with `uv run python evals/run_eval.py --runs 5`. It uses the real
model and search index, so it needs OPENAI_API_KEY in .env and a built index
(`uv run isaac-says ingest`). It writes the report to evals/results.md and every reply to
evals/output/replies.jsonl, which check_judge.py reads.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from isaac_says.agent.factory import build_chat_service
from isaac_says.agent.llm import OpenAIClient
from isaac_says.agent.nodes import format_excerpts
from isaac_says.agent.service import ChatService, TurnResult
from isaac_says.config import get_settings
from judge import JUDGE_MODEL, judge_answer, make_judge
from report import build_report

EVALS_DIR = Path(__file__).parent
OUTPUT_DIR = EVALS_DIR / "output"

# For each category, the reply kind that counts as correct.
EXPECTED = {
    "in_scope": "answer",
    "out_of_scope": "not_covered",
    "adjacent": "not_covered",
    "review": "review",
}

# A review request can get a follow-up question. This is the reply of a reader with nothing to add.
NO_MORE_DETAIL = "That is all the detail I have. Please go ahead and review it based on that."
MAX_FOLLOW_UPS = 2  # the agent asks at most two follow-up questions before it reviews anyway

# How many questions are asked at the same time. One at a time takes about 15 minutes per run.
# Much higher risks the API's rate limit.
AT_ONCE = 8


async def ask(service: ChatService, question: str, costs: list[float]) -> TurnResult:
    """Ask one question in a new conversation and return the last turn.
    Each turn's cost is added to `costs` straight away, so it still counts if a later turn fails."""
    result = await service.run_turn(None, question)
    costs.append(result.usage.cost_usd)
    for _ in range(MAX_FOLLOW_UPS):
        if result.reply.kind != "needs_input":
            break
        result = await service.run_turn(result.thread_id, NO_MORE_DETAIL)
        costs.append(result.usage.cost_usd)
    return result


async def check_question(service: ChatService, judge: OpenAIClient, item: dict, run: int) -> dict:
    """Ask one question, check the reply, and return a record of what happened."""
    record = {
        "run": run,
        "id": item["id"],
        "category": item["category"],
        "question": item["question"],
        "kind": "",
        "correct": False,
        "cost": 0.0,
        "seconds": None,  # how long the reply took, including any follow-up turns
        # Only filled in for newsletter answers:
        "answer": None,
        "excerpts": None,
        "verdict": None,  # the judge's checks and reason, or None if it wasn't judged
        "judge_cost": 0.0,
    }
    costs: list[float] = []
    started = time.perf_counter()
    try:
        result = await ask(service, item["question"], costs)
    except Exception as error:  # one failed API call should not stop a long run
        record["kind"] = f"error: {type(error).__name__}"
        record["cost"] = sum(costs)  # turns that finished before the error still count
        return record

    record["seconds"] = round(time.perf_counter() - started, 1)
    record["kind"] = result.reply.kind
    record["correct"] = result.reply.kind == EXPECTED[item["category"]]
    record["cost"] = sum(costs)

    if result.reply.kind == "answer":
        record["answer"] = result.reply.text
        record["excerpts"] = format_excerpts(result.excerpts)
        try:
            verdict, judge_cost = await judge_answer(
                judge, item["question"], result.reply.text, result.excerpts
            )
            record["verdict"] = verdict.model_dump() | {"passed": verdict.passed}
            record["judge_cost"] = judge_cost
        except Exception as error:  # the reply still counts; it just has no verdict
            print(f"  judge failed on {item['id']}: {type(error).__name__}")
    return record


async def main(runs: int) -> None:
    # Hundreds of test turns would fill the Langfuse free plan, so tracing is off here.
    settings = get_settings().model_copy(update={"langfuse_public_key": None})
    # Set up like the `ask` command: memory only, and unanswered questions are not saved.
    service, _ = build_chat_service(settings, checkpointer=InMemorySaver())
    judge = make_judge(settings)
    lines = (EVALS_DIR / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    questions = [json.loads(line) for line in lines if line.strip()]

    total = runs * len(questions)
    finished = 0
    slots = asyncio.Semaphore(AT_ONCE)  # lets AT_ONCE questions in at a time; the rest wait

    async def check_when_free(item: dict, run: int) -> dict:
        nonlocal finished
        async with slots:
            record = await check_question(service, judge, item, run)
        finished += 1
        print(f"{finished}/{total} run {run} {item['id']}: {record['kind']}")
        return record

    jobs = [check_when_free(item, run) for run in range(1, runs + 1) for item in questions]
    records = await asyncio.gather(*jobs)  # results come back in the same order as jobs

    OUTPUT_DIR.mkdir(exist_ok=True)
    replies = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    (OUTPUT_DIR / "replies.jsonl").write_text(replies, encoding="utf-8")

    reasoning = f"{settings.reasoning_effort}, evidence check {settings.grade_reasoning_effort}"
    report = build_report(records, runs, settings.llm_model, reasoning, JUDGE_MODEL)
    (EVALS_DIR / "results.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate the assistant on questions.jsonl.")
    parser.add_argument("--runs", type=int, default=5, help="times to ask each question")
    args = parser.parse_args()
    asyncio.run(main(args.runs))
