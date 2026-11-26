"""Runs the evaluation on several models, to compare how often each is right, what it costs and
how fast it replies.

A cheaper or faster model is only worth switching to if it's just as accurate. So every model
answers the same questions, and the same judge grades every answer.

Run it from the project folder with `uv run python evals/compare_models.py --runs 2`. It writes
the table to evals/model_comparison.md and every reply to evals/output/comparison.jsonl.
Two runs of the three models cost about $1.
"""

import argparse
import asyncio
import json
import statistics
from datetime import date

from langgraph.checkpoint.memory import InMemorySaver

from isaac_says.agent.factory import build_chat_service
from isaac_says.config import get_settings
from judge import JUDGE_MODEL, make_judge
from run_eval import AT_ONCE, EVALS_DIR, OUTPUT_DIR, check_question
from stats import wilson_range

# USD per million tokens (input, output), from OpenAI's pricing page on 25 November 2026.
# The judge is gpt-6.1-terra, so it isn't in this list: a model grading its own answers tends to
# agree with itself.
MODELS = {
    "gpt-5.6-luna": (0.20, 1.20),  # what the app uses now
    "gpt-6-luna": (0.10, 0.50),  # newer and cheaper
    "gpt-5.4-mini": (0.75, 4.50),  # older and dearer
}


async def evaluate(model: str, questions: list[dict], runs: int) -> list[dict]:
    """Ask every question `runs` times with this model, and return one record per reply."""
    input_price, output_price = MODELS[model]
    settings = get_settings().model_copy(
        update={
            "llm_model": model,
            "llm_input_price_per_m": input_price,
            "llm_output_price_per_m": output_price,
            # Hundreds of test turns would fill the Langfuse free plan, so tracing is off here.
            "langfuse_public_key": None,
        }
    )
    service, _ = build_chat_service(settings, checkpointer=InMemorySaver())
    judge = make_judge(settings)
    slots = asyncio.Semaphore(AT_ONCE)  # lets AT_ONCE questions in at a time; the rest wait

    async def check_when_free(item: dict, run: int) -> dict:
        async with slots:
            return await check_question(service, judge, item, run)

    jobs = [check_when_free(item, run) for run in range(1, runs + 1) for item in questions]
    return await asyncio.gather(*jobs)


def rate(passes: int, total: int) -> str:
    """A pass rate with its likely range, like "97% (93-99%)"."""
    if total == 0:
        return "-"
    low, high = wilson_range(passes, total)
    return f"{passes / total:.0%} ({low:.0%}-{high:.0%})"


def table_row(model: str, records: list[dict]) -> str:
    """One row of the comparison table."""
    input_price, output_price = MODELS[model]
    right = sum(r["correct"] for r in records)
    verdicts = [r["verdict"] for r in records if r["verdict"] is not None]
    good = sum(v["passed"] for v in verdicts)
    cost_per_100 = sum(r["cost"] for r in records) / len(records) * 100
    seconds = [r["seconds"] for r in records if r["seconds"] is not None]
    median = statistics.median(seconds)
    slowest = statistics.quantiles(seconds, n=10)[-1]  # 9 in 10 replies were faster than this
    errors = sum(r["kind"].startswith("error") for r in records)
    return (
        f"| `{model}` | ${input_price:.2f} / ${output_price:.2f} | {rate(right, len(records))} "
        f"| {rate(good, len(verdicts))} | ${cost_per_100:.3f} | {median:.1f}s | {slowest:.1f}s "
        f"| {errors} |"
    )


async def main(runs: int) -> None:
    lines = (EVALS_DIR / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    questions = [json.loads(line) for line in lines if line.strip()]

    rows = []
    all_records = []
    for model in MODELS:
        print(f"Asking {len(questions)} questions {runs} times with {model}...")
        records = await evaluate(model, questions, runs)
        rows.append(table_row(model, records))
        all_records += [record | {"model": model} for record in records]

    OUTPUT_DIR.mkdir(exist_ok=True)
    replies = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in all_records)
    (OUTPUT_DIR / "comparison.jsonl").write_text(replies, encoding="utf-8")

    settings = get_settings()
    report = "\n".join(
        [
            "# Model comparison",
            "",
            f"Run on {date.today().isoformat()}. Each model answered all {len(questions)} "
            f"questions {runs} times, with reasoning {settings.reasoning_effort} "
            f"(evidence check {settings.grade_reasoning_effort}). Judge: `{JUDGE_MODEL}`.",
            "",
            "- **Right kind of reply**: answered, refused or reviewed when it should have.",
            "- **Judge passed**: of the answers, how many address the question using only "
            "the excerpts.",
            "- **Cost per 100 questions** is the assistant's cost only, not the judge's.",
            "- **Median** is the typical reply time. **9 in 10 under** is the time that 90% of "
            "replies beat, so it shows how slow the slow ones get.",
            "- The ranges in brackets are where the true rate most likely sits (95%). If two "
            "models' ranges overlap a lot, the test can't tell them apart.",
            "",
            "| Model | Price per 1M tokens (in / out) | Right kind of reply | Judge passed "
            "| Cost per 100 questions | Median | 9 in 10 under | API errors |",
            "|---|---|---|---|---|---|---|---|",
            *rows,
            "",
        ]
    )
    (EVALS_DIR / "model_comparison.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare models on questions.jsonl.")
    parser.add_argument("--runs", type=int, default=2, help="times to ask each question")
    args = parser.parse_args()
    asyncio.run(main(args.runs))
