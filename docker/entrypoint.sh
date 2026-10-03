#!/bin/sh
# Container entrypoint: prepare the data volume, then exec the given command.
set -eu

DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "$DATA_DIR/raw"

# Seed the newsletter snapshot on first start without overwriting an existing one.
if [ ! -f "$DATA_DIR/raw/posts.jsonl" ]; then
    cp /app/seed/posts.jsonl "$DATA_DIR/raw/posts.jsonl"
fi

# Build the search index on first start. Only the API container needs it (and an OpenAI key).
if [ "${1:-}" = "isaac-says" ] && [ "${2:-}" = "serve" ] && [ ! -d "$DATA_DIR/chroma" ]; then
    echo "First start: building the search index from the snapshot..."
    isaac-says ingest
fi

exec "$@"
