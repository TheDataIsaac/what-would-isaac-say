# Evaluation results

Run on 2026-11-10 with `gpt-5.6-luna` (reasoning: none). Estimated model cost: $0.07.
Questions that failed with an API error (counted as misses): 0.

| What it should do | Result |
|---|---|
| Newsletter questions answered | 58/60 |
| Unrelated questions refused | 12/12 |
| Near-topic questions refused | 9/10 |
| Review requests reviewed | 6/6 |

## Misses

- `in_scope-022` got `not_covered`: How should I present mixed results so people understand the problem and know what to do?
- `in_scope-033` got `not_covered`: How can I tell whether my data shows a real problem or just random noise?
- `adjacent-081` got `answer`: How should I prepare for a data analyst job interview?
