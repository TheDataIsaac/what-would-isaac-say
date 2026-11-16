"""Checks the judge against a person's grades. The judge is a model, so it can be wrong too.

1. `uv run python evals/check_judge.py sample` picks 30 judged answers from the last run
   (evals/output/replies.jsonl) and writes them to evals/judge_check.csv.
2. Grade each answer yourself, before looking at the judge's columns: put pass or fail in
   my_grade, using the same two checks the judge makes (see INSTRUCTIONS in judge.py).
3. `uv run python evals/check_judge.py compare` prints how often you and the judge agreed, and
   every answer where you didn't.

Running sample again replaces judge_check.csv, including any grades in it.
"""

import argparse
import csv
import json
import random
from pathlib import Path

EVALS_DIR = Path(__file__).parent
REPLIES_PATH = EVALS_DIR / "output" / "replies.jsonl"
CHECK_PATH = EVALS_DIR / "judge_check.csv"

SAMPLE_SIZE = 30
# The judge passes most answers, so a random sample would be nearly all passes, and agreeing on
# easy passes says little. Up to this many of the 30 are answers the judge failed.
MOST_JUDGE_FAILS = 10
SEED = 7  # the same replies file always gives the same sample

COLUMNS = [
    "id",
    "question",
    "answer",
    "excerpts",
    "my_grade",
    "my_reason",
    "judge_grade",
    "judge_reason",
]


def sample() -> None:
    records = [json.loads(line) for line in REPLIES_PATH.read_text(encoding="utf-8").splitlines()]
    judged = [r for r in records if r["verdict"] is not None]

    # One answer per question, so no question is graded twice.
    rng = random.Random(SEED)
    rng.shuffle(judged)
    # Failed answers first, so a question with one keeps that one rather than one of its passes.
    judged.sort(key=lambda r: r["verdict"]["passed"])
    one_each = {}
    for record in judged:
        one_each.setdefault(record["id"], record)
    fails = [r for r in one_each.values() if not r["verdict"]["passed"]]
    passes = [r for r in one_each.values() if r["verdict"]["passed"]]
    chosen = fails[:MOST_JUDGE_FAILS]
    chosen += passes[: SAMPLE_SIZE - len(chosen)]
    rng.shuffle(chosen)  # so the judge's fails aren't all at the top

    # utf-8-sig adds a marker at the start of the file so Excel reads curly quotes correctly.
    with open(CHECK_PATH, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        for record in chosen:
            writer.writerow(
                {
                    "id": f"{record['id']} run {record['run']}",
                    "question": record["question"],
                    "answer": record["answer"],
                    "excerpts": record["excerpts"],
                    "my_grade": "",
                    "my_reason": "",
                    "judge_grade": "pass" if record["verdict"]["passed"] else "fail",
                    "judge_reason": record["verdict"]["reason"],
                }
            )
    print(f"Wrote {len(chosen)} answers ({len(fails[:MOST_JUDGE_FAILS])} failed by the judge)")
    print(f"to {CHECK_PATH}. Fill in my_grade with pass or fail.")


def compare() -> None:
    with open(CHECK_PATH, encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    for row in rows:
        row["my_grade"] = row["my_grade"].strip().lower()  # accept "Pass", " fail " and so on
    graded = [r for r in rows if r["my_grade"] in ("pass", "fail")]
    if not graded:
        print("No grades yet. Put pass or fail in the my_grade column first.")
        return

    agreed = [r for r in graded if r["my_grade"] == r["judge_grade"]]
    # The two ways to disagree mean different things, so they are counted separately.
    too_strict = [r for r in graded if r["judge_grade"] == "fail" and r["my_grade"] == "pass"]
    too_lenient = [r for r in graded if r["judge_grade"] == "pass" and r["my_grade"] == "fail"]

    print(f"Agreed on {len(agreed)} of {len(graded)} answers ({len(agreed) / len(graded):.0%}).")
    print(f"Judge failed an answer you passed: {len(too_strict)}")
    print(f"Judge passed an answer you failed: {len(too_lenient)}")
    for row in too_strict + too_lenient:
        print(f"\n{row['id']}: you said {row['my_grade']}, the judge said {row['judge_grade']}")
        print(f"  Question: {row['question']}")
        print(f"  You: {row['my_reason'] or '(no reason given)'}")
        print(f"  Judge: {row['judge_reason']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check the judge against your own grades.")
    parser.add_argument("step", choices=["sample", "compare"])
    args = parser.parse_args()
    if args.step == "sample":
        sample()
    else:
        compare()
