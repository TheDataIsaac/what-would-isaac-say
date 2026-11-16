# Evaluation results

Run on 2026-11-16. Runs: 5 (each run asks every question once, in a new conversation). Assistant: `gpt-5.6-luna` (reasoning: none, evidence check low). Judge: `gpt-6.1-terra`.

Estimated cost: $0.37 for the assistant and $0.45 for the judge. Replies that failed with an API error (counted as wrong): 0. Answers the judge couldn't grade: 0.

## Did it answer or refuse correctly?

| What it should do | Correct | Rate | Likely range (95%) |
|---|---|---|---|
| Answer newsletter questions | 297/300 | 99% | 97% to 100% |
| Refuse unrelated questions | 60/60 | 100% | 94% to 100% |
| Refuse near-topic questions | 50/50 | 100% | 93% to 100% |
| Review a piece of work | 30/30 | 100% | 89% to 100% |

## Were the answers good?

The judge read every answer the assistant gave, with the excerpts it was written from.

| Judge's check | Passed | Rate | Likely range (95%) |
|---|---|---|---|
| Answers the question | 297/297 | 100% | 99% to 100% |
| Uses only what the excerpts say | 290/297 | 98% | 95% to 99% |
| Both | 290/297 | 98% | 95% to 99% |

## Questions that only failed sometimes

These got a different result from one run to the next.

| Id | Question | Correct | What it got |
|---|---|---|---|
| `in_scope-022` | How should I present mixed results so people understand the problem and know what to do? | 2/5 | not_covered 3, answer 2 |

## Questions that failed every time

None.

## Answers the judge failed

- `in_scope-013`, 1 of 5 answers: How should I arrange the information in my chart so people understand it quickly?
  - Judge: The answer applies “top left” placement to a chart as well as a dashboard; the excerpt only recommends it for dashboards.
- `in_scope-029`, 2 of 5 answers: Where can I find practical advice for getting better at working with data?
  - Judge: The answer recommends relevant posts and summarizes their advice, but the excerpts do not identify the newsletter as “Explain the Data.”
- `in_scope-030`, 1 of 5 answers: When should I avoid putting two different metrics on the same chart?
  - Judge: The answer addresses when to avoid a dual-axis chart, but the advice to use one only when “the metrics are meaningfully related” is not stated or clearly implied by the excerpts.
- `in_scope-042`, 1 of 5 answers: How can I explain my data project so recruiters understand why it matters?
  - Judge: The advice answers the question, but “customer retention” is not a business goal stated in the excerpts; keeping customers happy is not the same claim.
- `in_scope-043`, 1 of 5 answers: How do I choose the right dashboard for the people who will use it?
  - Judge: The answer addresses choosing and tailoring a dashboard, but the advice to remove unused “features” goes beyond the excerpt’s specific recommendation to delete an unused filter.
- `in_scope-047`, 1 of 5 answers: How can I tell whether my data shows a real cause or just two things happening together?
  - Judge: The answer addresses how to distinguish a pattern from a cause. However, “delivery problems” is not stated in the excerpts, which mention switching delivery trucks instead.
