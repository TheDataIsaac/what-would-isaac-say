# What Would Isaac Say?

**A grounded AI assistant for the [Explain the Data](https://explainthedata.substack.com) newsletter.**
It answers questions using only what the newsletter says, backs every answer with quotes that code
has checked against the original text, reviews a reader's dashboard or report against the
newsletter's principles, and admits when it does not know.

**Live demo:** <https://ask.isaacjoresanya.com> (a small server with a daily question cap, so it may
decline questions late in the day; conversations are stored, so please keep them non-confidential).

![A question answered with verified sources](docs/images/chat-answer.jpg)

## Why this project exists

A chatbot on top of a blog has an obvious problem: language models invent things that sound right.
For a newsletter about *explaining data honestly*, an assistant that makes up quotes would be
embarrassing. So this project is built around one rule:

> The assistant may only say what it can back up with quotes from Isaac's own text.

Everything else follows from that rule. Three independent checks make it refuse instead of guess,
and every citation is verified by plain code rather than trusted.

## What it does

| You do this | It does this |
|---|---|
| Ask a question the newsletter covers | Answers in a few sentences, with quotes and links to the posts |
| Ask something the newsletter does not cover | Says so, and saves the question for Isaac |
| Describe your dashboard, chart or report | Asks one question if it needs more detail, then reviews it, every point tied to a post |
| (Isaac) Answers a saved question in the admin view | The answer is added to the knowledge base and cited from then on |
| Connect Claude Desktop (or any MCP client) | Lists, reads and searches the posts as tools |

![A review of a dashboard description](docs/images/chat-review.jpg)

## Quick start

You need Python 3.12 or newer, [uv](https://docs.astral.sh/uv/), and an OpenAI API key.

```bash
# 1. Install
uv sync --extra ui

# 2. Configure (copy the template, then add your keys)
cp .env.example .env

# 3. Build the search index from the committed newsletter snapshot (about 20 seconds, under a cent)
uv run isaac-says ingest

# 4. Try it in the terminal
uv run isaac-says ask "When should I use a dual axis chart?"
uv run isaac-says chat

# 5. Run the API and the web interface (two terminals)
uv run isaac-says serve                                    # http://127.0.0.1:8000/docs
uv run streamlit run src/isaac_says/ui/streamlit_app.py    # http://localhost:8501
```

Or with Docker (needs `.env` with your keys): `docker compose up --build`.

To pull new posts from Substack first: `uv run isaac-says ingest --refresh`.

## How it works

```mermaid
flowchart LR
    Q[Message] --> R{route}
    R -->|question| S[search]
    R -->|review| I[enough detail?]
    I -->|no| A[ask the user, then resume]
    I -->|yes| S
    S --> G{evidence good enough?}
    G -->|no| N[say so and save the question for Isaac]
    G -->|yes| W[write answer or review]
    W --> V{every quote really in the source?}
    V -->|no| N
    V -->|yes| OUT[reply with verified citations]
```

1. **Ingest.** Download the posts from Substack's public API, split them by heading, embed them, store them in Chroma.
2. **Search.** Turn a question into an embedding and find the nearest chunks. Weak matches are dropped before any model sees them.
3. **Judge.** A model call decides whether the remaining text really answers the question. If not, the assistant refuses.
4. **Write.** A model call writes the answer and proposes quotes in a strict Pydantic shape.
5. **Verify.** Plain code checks each quote appears word for word in the chunk it cites. Invented quotes are removed. If none survive, the reply becomes a refusal.

Details, including the full graph and the life of one request, are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tech stack

| Concern | Choice | Where |
|---|---|---|
| Language and packaging | Python 3.12, `uv`, `pyproject.toml`, lockfile | root |
| Agent orchestration | LangGraph (explicit graph, checkpointed memory, `interrupt` for clarifications) | `agent/` |
| Language model | OpenAI `gpt-5.6-luna`, reasoning off (low for the evidence check), Responses API, structured outputs | `agent/llm.py` |
| Data validation | Pydantic v2 (models, settings, LLM outputs, API bodies, discriminated unions) | everywhere |
| Search | Chroma + `text-embedding-3-small`, cosine similarity | `retrieval/` |
| HTTP API | FastAPI: dependencies, middleware, SSE streaming, API-key auth, rate limiting | `api/` |
| Database | SQLite (WAL) through async SQLAlchemy 2.0, repository pattern | `db/` |
| Tool interface | MCP server (`MCPServer`, stdio) | `mcp_server.py` |
| Web interface | Streamlit, talking to the API over HTTP only | `ui/` |
| Tracing | Langfuse, through its LangChain callback (optional, on when keys are set) | `agent/tracing.py` |
| Code quality | ruff (lint and format), pytest, GitHub Actions CI | `tests/`, `.github/` |
| Deployment | Multi-stage Dockerfile, compose files, Caddy for HTTPS, non-root user, healthchecks, spend caps | root, `deploy/` |

## Project layout

```
src/isaac_says/
  config.py            all settings, in one validated class
  logging_setup.py     logging configuration
  domain/              plain data shapes: posts, chunks, replies
  ingestion/           Substack client, cleaning, chunking, snapshot, pipeline
  retrieval/           vector index and embeddings
  agent/               the LangGraph agent: state, nodes, graph, prompts, verification, service, tracing
  db/                  tables, sessions, repository, conversation retention
  api/                 FastAPI app, routes, security, resources
  ui/                  Streamlit page and the API client it uses
  mcp_server.py        the MCP server
  cli.py               the `isaac-says` command
tests/                 pytest tests (no API key needed)
evals/                 the 88 evaluation questions, the evaluation script, its judge and the judge check
docs/                  architecture, decisions, deployment
deploy/proxy/          shared Caddy reverse proxy for the production server
scripts/analytics.sql  SQL over the operational database
data/raw/posts.jsonl   the committed snapshot of the 60 posts
```

## Everyday commands

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest

sqlite3 data/app.db < scripts/analytics.sql            # usage analytics
uv run isaac-says purge-threads                        # delete conversations idle past the retention period
```

## Tests and evaluation

```bash
uv run pytest                                 # tests, no API key or network needed
uv run python evals/run_eval.py --runs 5      # evaluation, uses the real models (about 8 minutes, under $1)
```

The tests cover quote verification, splitting posts by heading, the steps that decide when to
refuse, and the reply models.

The evaluation has 88 questions: 60 the newsletter answers, 12 unrelated ones (such as the capital
of France), 10 near-topic ones it never covers (such as a Power BI DAX measure), and 6 requests to
review a piece of work. It asks every question several times, each time in a new conversation,
and checks every reply in two ways:

* **The kind of reply.** Did it answer, refuse or review when it should have? Plain code checks this.
* **The quality of each answer.** A second, stronger model (the judge, `gpt-6.1-terra`) reads the
  question, the excerpts the answer was written from and the answer, and checks that the answer
  responds to the question and says nothing the excerpts don't support.

Asking several times matters because the model doesn't give the same reply every time. The report
shows each pass rate with a 95% range, lists the questions that only fail sometimes, and gives the
judge's reason for every answer it failed. It's written to [evals/results.md](evals/results.md).

`evals/check_judge.py` checks the judge itself: it picks 30 judged answers for a person to grade
before looking at the judge's verdict, then reports how often the two agree.

On 16 November the 30 answers (in [evals/judge_check.csv](evals/judge_check.csv)) were graded by a
second model, Claude Opus, which saw only the question, the answer and the excerpts. It agreed with
the judge on 24 of 30 (80%, likely range 63% to 90%). Of the six disagreements, the judge was right
on one, too strict on three and too lenient on two:

* Too strict: it failed an example that is in the excerpts word for word, a paraphrase of what an
  excerpt says, and the newsletter's name, which the assistant gets from its own instructions and
  the judge never sees.
* Too lenient: it passed advice the excerpts give for one situation applied to another, and a fixed
  order where the excerpt says to use "whatever order makes sense for your goal".

So the judge's errors go both ways and roughly cancel out in its pass rate, but a single verdict
can be wrong. A second model is not a person, and 30 answers is a small sample, so a person grading
them is still the better check.

Runs on 16 November 2026, 5 runs each, `gpt-5.6-luna`, before and after one fix: giving the
evidence check (the step that decides whether the excerpts are enough to answer) low reasoning.
Every other step still runs with reasoning off.

| What it should do | Before | After | Likely range after (95%) |
|---|---|---|---|
| Answer newsletter questions | 296/300 | 297/300 | 97% to 100% |
| Refuse unrelated questions | 60/60 | 60/60 | 94% to 100% |
| Refuse near-topic questions | 45/50 | 50/50 | 93% to 100% |
| Review a piece of work | 30/30 | 30/30 | 89% to 100% |

The judge passed 292 of 301 answers before and 290 of 297 after (97% and 98%). The clear gain is
"How should I prepare for a data analyst job interview?", which was answered 5 times out of 5
before and refused 5 times out of 5 after. The one-question gain on newsletter questions is within
the noise.

The single run on 10 November missed two newsletter questions. Over five runs, one of them
(`in_scope-022`) failed 4 times out of 5 and the other (`in_scope-033`) never failed, so a single
run can't tell an unlucky question from a broken one. The cause is described below.

## Limitations and what comes next

* **One author, 60 posts.** The assistant is only as broad as the newsletter. That is the design, but it means many questions get an honest "not covered".
* **Quotes are verified, the sentences around them are not.** Code guarantees the quotes are real. It cannot check that the sentences around them are faithful to the post. The evaluation's judge measures this instead: 2 to 3% of answers add something the excerpts don't say, usually a small example or an advice point stretched to a new situation.
* **The evidence check can still flip.** For the same question and the same six excerpts, the step that decides whether the excerpts are enough says yes on one try and no on the next. "How should I present mixed results…" was refused 4 times out of 5 with reasoning off and 3 times out of 5 with low reasoning, though one of Isaac's posts covers exactly that. Medium reasoning made it refuse more often, and rewording the prompt made reviews start failing, so neither is in.
* **Response time is slow for a chat.** A reply usually takes around 8 to 13 seconds, because it makes four to five model calls one after another, and the provider sometimes stalls. Searching while routing, and skipping the grader when the top score is very high, are the obvious next optimisations.
* **Substack's API is undocumented.** It could change. The snapshot keeps the project running if it does.
* **Conversations are stored.** Every message in a thread, including work submitted for review, is
  kept in a local SQLite file so follow-ups work. Clients can delete a thread
  (`DELETE /chat/{thread_id}`), and `isaac-says purge-threads` removes threads idle for more than
  `THREAD_RETENTION_DAYS` (default 30). Review text is never added to the question queue or logs.
* **Single server.** The rate limiter and SQLite are process-local. Scaling out means Postgres and Redis (see `docs/ARCHITECTURE.md`).

Next steps: hybrid keyword plus vector search, a reranker, and per-user authentication for the
admin view.

## Documentation

| Document | Read it to |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the components fit together and how a message flows through them |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Why each significant design choice was made, and its trade-offs |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Running it on a small public server with HTTPS and spend limits |

## About this project

Built by Isaac Oresanya as a portfolio project for applied AI engineering. This is an AI assistant and is not Isaac himself.

The code is under the [MIT licence](LICENSE). The newsletter text in `data/raw/` belongs to its author and is not covered by the licence.
