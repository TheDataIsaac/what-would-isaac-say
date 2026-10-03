-- Analytics queries for the assistant's operational database (data/app.db).
--
-- Run with any SQLite client, for example:
--   sqlite3 data/app.db < scripts/analytics.sql
-- The admin dashboard figures are computed by equivalent queries.

-- 1. What happens to questions? (outcome mix and share)
SELECT outcome,
       COUNT(*)                                            AS replies,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)  AS percent
FROM query_logs
GROUP BY outcome
ORDER BY replies DESC;

-- 2. Refusal rate by kind of request. A high rate for "question" means readers are asking about
--    topics the newsletter does not cover, which is a list of post ideas.
SELECT intent,
       COUNT(*)                                                         AS turns,
       SUM(outcome = 'not_covered')                                     AS refused,
       ROUND(100.0 * SUM(outcome = 'not_covered') / COUNT(*), 1)        AS refusal_percent
FROM query_logs
GROUP BY intent;

-- 3. Daily volume, cost and average latency.
SELECT DATE(created_at)                 AS day,
       COUNT(*)                         AS chats,
       ROUND(SUM(cost_usd), 4)          AS cost_usd,
       ROUND(AVG(latency_ms) / 1000.0, 1) AS avg_seconds
FROM query_logs
GROUP BY day
ORDER BY day DESC;

-- 4. The slowest 10 requests (find out whether slowness is one outcome or everything).
SELECT created_at, outcome, latency_ms, input_tokens + output_tokens AS tokens
FROM query_logs
ORDER BY latency_ms DESC
LIMIT 10;

-- 5. Do readers like the replies? Thumbs up and down per outcome.
SELECT q.outcome,
       SUM(f.rating > 0) AS thumbs_up,
       SUM(f.rating < 0) AS thumbs_down
FROM feedback AS f
JOIN query_logs AS q ON q.request_id = f.request_id
GROUP BY q.outcome;

-- 6. The content backlog: questions readers asked that the newsletter does not answer yet,
--    most requested first.
SELECT question, times_asked, status, first_asked_at
FROM open_questions
ORDER BY status, times_asked DESC, last_asked_at DESC;

-- 7. Turnaround: how long do questions wait before Isaac answers them?
SELECT ROUND(AVG(julianday(answered_at) - julianday(first_asked_at)), 2) AS avg_days_to_answer,
       COUNT(*)                                                          AS answered
FROM open_questions
WHERE status = 'answered';
