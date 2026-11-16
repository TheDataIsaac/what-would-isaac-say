"""Turns the records from run_eval.py into the Markdown report in results.md."""

from collections import Counter, defaultdict
from datetime import date

from stats import wilson_range

# The table label for each category, in the order the rows appear.
LABELS = {
    "in_scope": "Answer newsletter questions",
    "out_of_scope": "Refuse unrelated questions",
    "adjacent": "Refuse near-topic questions",
    "review": "Review a piece of work",
}


def rate_row(label: str, passes: int, total: int) -> str:
    """One table row: the label, the count, the rate and its likely range."""
    if total == 0:
        return f"| {label} | 0/0 | - | - |"
    low, high = wilson_range(passes, total)
    return f"| {label} | {passes}/{total} | {passes / total:.0%} | {low:.0%} to {high:.0%} |"


def kind_section(records: list[dict]) -> list[str]:
    lines = [
        "## Did it answer or refuse correctly?",
        "",
        "| What it should do | Correct | Rate | Likely range (95%) |",
        "|---|---|---|---|",
    ]
    for category, label in LABELS.items():
        in_category = [r for r in records if r["category"] == category]
        passes = sum(r["correct"] for r in in_category)
        lines.append(rate_row(label, passes, len(in_category)))
    return lines + [""]


def judge_section(records: list[dict]) -> list[str]:
    verdicts = [r["verdict"] for r in records if r["verdict"] is not None]
    total = len(verdicts)
    return [
        "## Were the answers good?",
        "",
        "The judge read every answer the assistant gave, with the excerpts it was written from.",
        "",
        "| Judge's check | Passed | Rate | Likely range (95%) |",
        "|---|---|---|---|",
        rate_row("Answers the question", sum(v["answers_question"] for v in verdicts), total),
        rate_row("Uses only what the excerpts say", sum(v["grounded"] for v in verdicts), total),
        rate_row("Both", sum(v["passed"] for v in verdicts), total),
        "",
    ]


def question_sections(records: list[dict]) -> list[str]:
    """The questions that failed every time, and the ones that only failed sometimes."""
    by_question = defaultdict(list)
    for record in records:
        by_question[record["id"]].append(record)

    always_failed = []
    sometimes_failed = []
    for question_id, tries in by_question.items():
        passes = sum(r["correct"] for r in tries)
        kinds = Counter(r["kind"] for r in tries)
        got = ", ".join(f"{kind} {count}" for kind, count in kinds.most_common())
        line = f"| `{question_id}` | {tries[0]['question']} | {passes}/{len(tries)} | {got} |"
        if passes == 0:
            always_failed.append(line)
        elif passes < len(tries):
            sometimes_failed.append(line)

    header = ["| Id | Question | Correct | What it got |", "|---|---|---|---|"]
    lines = [
        "## Questions that only failed sometimes",
        "",
        "These got a different result from one run to the next.",
        "",
    ]
    lines += header + sometimes_failed if sometimes_failed else ["None."]
    lines += ["", "## Questions that failed every time", ""]
    lines += header + always_failed if always_failed else ["None."]
    return lines + [""]


def judge_failures_section(records: list[dict]) -> list[str]:
    """Each question with an answer the judge failed, with the judge's reason for one of them."""
    judged = defaultdict(list)
    for record in records:
        if record["verdict"] is not None:
            judged[record["id"]].append(record)

    lines = ["## Answers the judge failed", ""]
    for question_id, tries in judged.items():
        failed = [r for r in tries if not r["verdict"]["passed"]]
        if failed:
            lines.append(
                f"- `{question_id}`, {len(failed)} of {len(tries)} answers: {tries[0]['question']}"
            )
            lines.append(f"  - Judge: {failed[0]['verdict']['reason']}")
    if len(lines) == 2:
        lines.append("None.")
    return lines + [""]


def build_report(
    records: list[dict], runs: int, model: str, reasoning: str, judge_model: str
) -> str:
    errors = sum(r["kind"].startswith("error") for r in records)
    unjudged = sum(r["answer"] is not None and r["verdict"] is None for r in records)
    model_cost = sum(r["cost"] for r in records)
    judge_cost = sum(r["judge_cost"] for r in records)
    lines = [
        "# Evaluation results",
        "",
        f"Run on {date.today().isoformat()}. Runs: {runs} (each run asks every question once, "
        f"in a new conversation). Assistant: `{model}` (reasoning: {reasoning}). "
        f"Judge: `{judge_model}`.",
        "",
        f"Estimated cost: ${model_cost:.2f} for the assistant and ${judge_cost:.2f} for the judge. "
        f"Replies that failed with an API error (counted as wrong): {errors}. "
        f"Answers the judge couldn't grade: {unjudged}.",
        "",
        *kind_section(records),
        *judge_section(records),
        *question_sections(records),
        *judge_failures_section(records),
    ]
    return "\n".join(lines)
