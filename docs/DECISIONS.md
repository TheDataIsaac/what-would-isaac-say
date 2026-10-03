# Design decisions

A record of the significant design choices, the alternatives considered, and the trade-offs. Each
entry lists **context, decision, alternatives, consequences.**

---

## 1. Use Substack's public JSON API, and commit a snapshot

**Context.** The content lives on Substack. There is no official developer API for reading a
publication.
**Decision.** Read the two public endpoints the website itself uses, and save everything to
`data/raw/posts.jsonl`, which is committed to git. The rest of the project reads the snapshot.
**Alternatives.** RSS (only the latest 20 posts). Scraping HTML (fragile). Substack's manual export
(a human step, but official).
**Consequences.** The endpoints are undocumented and could change, so a change breaks
`ingest --refresh` but nothing else. The snapshot also means the index can be rebuilt without the
network.

## 2. Chunk by heading, not by fixed size

**Context.** Retrieval quality depends on what a chunk contains.
**Decision.** One chunk per heading section, merging tiny ones and splitting huge ones at paragraph
boundaries. Each chunk is embedded with its title and heading as a prefix.
**Alternatives.** Fixed 1000-character windows with overlap (the usual tutorial default).
**Consequences.** Chunks match how the author organised ideas, and citations land on a meaningful
section ("The Order Is Not Easy To See") instead of an arbitrary slice. Quotes never straddle a
cut, which keeps verification reliable. The approach relies on posts having headings.

## 3. Chroma with OpenAI embeddings

**Context.** Need similarity search over about 340 chunks.
**Decision.** Chroma for storage and `text-embedding-3-small` for vectors.
**Alternatives.** FAISS (used in the RAG practice folder; needs its own metadata handling). Local
`sentence-transformers` (free per call, but pulls in PyTorch and makes the Docker image several
gigabytes larger). A plain SQLite table with NumPy (enough at this size, but teaches less).
**Consequences.** A tiny image and simple metadata filtering. Embedding the whole newsletter costs
a fraction of a cent. The price is a network call per search and a dependency on OpenAI.

## 4. An explicit LangGraph graph instead of a single "agent" call

**Context.** LangChain offers prebuilt agents (`create_agent`) that loop over tools.
**Decision.** Build the graph by hand with named nodes and conditional edges.
**Alternatives.** A prebuilt tool-calling agent. A plain function that calls the steps in order.
**Consequences.** Every decision point is visible, testable and streamable as a progress event.
Refusals are an explicit path in the graph rather than behaviour left to the model. The cost is
more code than a prebuilt agent. A plain function would have been simpler for the question flow, but the
review flow (branching, pausing, looping) is exactly what a graph is for.

## 5. Structured output, and verify quotes with code

**Context.** Language models invent plausible quotes.
**Decision.** The model returns Pydantic-shaped drafts, including quotes. Ordinary code then checks
each quote against the source text and drops any that do not appear. A reply with no surviving
citation becomes a refusal.
**Alternatives.** Trust the model. Ask a second model to check the first.
**Consequences.** Every citation shown to a user is guaranteed to be real text from the source.
This does **not** guarantee the prose around the quote is faithful. Matching is forgiving about
case, quote marks and spacing, and strict about words: pieces must match whole words (so
"bar charts" does not match inside "toolbar charts") and, when a quote uses an ellipsis, the pieces
must appear in source order without overlapping.

## 6. Refuse by default, in three layers

**Context.** A wrong confident answer is worse than "I don't know".
**Decision.** Layer 1: a similarity cutoff discards weak matches before any model sees them (and
skips the model calls entirely if nothing is left). Layer 2: a grader model decides whether the
evidence is sufficient. Layer 3: quote verification.
**Alternatives.** A single "answer only from context" instruction in the prompt.
**Consequences.** Three cheap, independent checks, each catching failures the others miss. Extra
latency (one more model call) and a small risk of refusing a borderline question.

## 7. Speak about Isaac in the third person

**Context.** The project is named "What Would Isaac Say?", which invites impersonation.
**Decision.** The assistant says it is an AI, and phrases answers as "Isaac argues that...",
quoting his text. It never writes as if it were him.
**Alternatives.** First-person persona imitating his voice.
**Consequences.** Readers are never misled about who is speaking, and every claim is traceable to
his words. It is less fun than a voice clone, and it is the honest design for a public demo.

## 8. The owner-in-the-loop question queue

**Context.** Questions the newsletter cannot answer are the most valuable signal the system collects.
**Decision.** Save them (deduplicated, counted). Isaac answers them in the admin view. The answer is
indexed as a new source and cited like a post.
**Alternatives.** Let the model answer from general knowledge. Silently log and ignore.
**Consequences.** The knowledge base improves from real demand, and the queue doubles as a content
backlog. It needs a human, which is the point. Safeguards: review descriptions (a reader's own work)
are never added to the queue, queued questions are stored in resolved form, and the reply tells
the reader their question was saved. Conversation state is stored separately for continuity; see
the privacy and retention notes in `ARCHITECTURE.md`.

## 9. Keep the outside services behind two small classes

**Decision.** The agent talks to OpenAI only through `OpenAIClient` and to the search index only
through `VectorIndex`. `agent/factory.py` is the one place that creates them.
**Consequences.** Changing the model provider or the search store means changing one class. The
price is one extra layer of indirection.

## 10. Async everywhere on the request path

**Decision.** `async def` routes, async SQLAlchemy (`aiosqlite`), async checkpointer. Blocking
calls (Chroma, the embedding request) are pushed to a worker thread with `asyncio.to_thread`.
**Consequences.** One slow model call does not freeze other requests. The price is that async has
sharp edges; a lost-update race in the question counter is the example (see the atomic `UPDATE` in
`db/repository.py`).

## 11. SQLite and `create_all`, no migration tool

**Decision.** SQLite in WAL mode, tables created at startup.
**Alternatives.** Postgres and Alembic migrations.
**Consequences.** Zero infrastructure, one file to back up, fast enough for this load. Changing a
table later means a manual migration. The repository pattern keeps SQL in one file, so moving to
Postgres later is a contained change.

## 12. Stream progress, not tokens

**Decision.** `/chat/stream` sends one event per finished graph step, then the full reply.
**Alternatives.** Stream the model's tokens as it writes.
**Consequences.** The answer cannot be shown until its quotes are verified, so token streaming
would show text that might later be thrown away. Step events still remove the blank wait ("Searching
the newsletter", "Verifying every quote").

## 13. Reasoning off, Responses API, short timeouts

**Decision.** `gpt-5.6-luna` with `reasoning_effort="none"` through the Responses API, with a 12
second timeout for small calls and 40 seconds for long ones.
**Why.** Reasoning off is faster and cheaper. The Responses API is the endpoint this model supports for tools plus reasoning settings. The timeouts
follow from measurement: requests stalled for 40 to 60 seconds in roughly 10 to 25 percent of calls
while normal calls take about 1.5 seconds, and the retry after a timeout succeeds immediately.

## 14. MCP is pinned to major version 2

**Context.** MCP 2.0 renamed `FastMCP` to `MCPServer` and changed result fields (`isError` became
`is_error`).
**Decision.** `mcp>=2.0,<3`.
**Consequences.** A breaking release cannot arrive unnoticed.

## 15. Fail closed on anything private

**Decision.** With no `ADMIN_API_KEY` configured, admin endpoints return 503 instead of being open.
Secrets are `SecretStr`. `.env` is ignored by git and Docker. Errors never leak internals.
**Consequences.** A misconfigured deployment is broken but safe, rather than working but exposed.
Docker's `--env-file` keeps quote characters literally, so a quoted `OPENAI_API_KEY="sk-..."`
arrives as an invalid key, and an empty `ADMIN_API_KEY=` would otherwise become an empty-string key
that an empty header could match. `Settings` therefore strips quotes and treats an empty secret as
"not set" (see `_clean_secret` in `config.py`).

## 16. A casual voice, enforced in two places

**Decision.** Replies are written in a relaxed, plain-spoken tone (`VOICE` in `agent/prompts.py`):
short sentences, no filler openers or flattery, no em dashes. Rules a program can check, such as
the dash rule, are also enforced in code (`agent/style.py`), because a model can ignore an
instruction. Quotes from the newsletter are never altered by this step.
**Consequences.** The assistant sounds closer to the newsletter's author, but it still says it is
an AI and still refers to Isaac in the third person (see decision 7).
