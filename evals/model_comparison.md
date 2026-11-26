# Model comparison

Run on 2026-11-25. Each model answered all 88 questions 2 times, with reasoning none (evidence check low). Judge: `gpt-6.1-terra`.

- **Right kind of reply**: answered, refused or reviewed when it should have.
- **Judge passed**: of the answers, how many address the question using only the excerpts.
- **Cost per 100 questions** is the assistant's cost only, not the judge's.
- **Median** is the typical reply time. **9 in 10 under** is the time that 90% of replies beat, so it shows how slow the slow ones get.
- The ranges in brackets are where the true rate most likely sits (95%). If two models' ranges overlap a lot, the test can't tell them apart.

| Model | Price per 1M tokens (in / out) | Right kind of reply | Judge passed | Cost per 100 questions | Median | 9 in 10 under | API errors |
|---|---|---|---|---|---|---|---|
| `gpt-5.6-luna` | $0.20 / $1.20 | 99% (97%-100%) | 97% (92%-99%) | $0.084 | 6.9s | 8.4s | 0 |
| `gpt-6-luna` | $0.10 / $0.50 | 98% (95%-99%) | 100% (97%-100%) | $0.036 | 6.1s | 7.5s | 0 |
| `gpt-5.4-mini` | $0.75 / $4.50 | 99% (96%-100%) | 98% (94%-100%) | $0.325 | 6.8s | 7.8s | 0 |
