# syntax=docker/dockerfile:1

# ---- Build stage: resolve and install dependencies into a virtual environment ----------------
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv

# Precompile bytecode at build time so the first request after startup does not pay for it.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies are installed in their own layer so it is only rebuilt when pyproject.toml or
# uv.lock change. UV_EXTRAS is empty for the API image and "--extra ui" for the UI image.
ARG UV_EXTRAS=""
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project ${UV_EXTRAS}

# --no-editable installs the package into the virtual environment. An editable install only
# references /app/src, which the runtime stage does not contain.
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable ${UV_EXTRAS}

# ---- Runtime stage ----------------------------------------------------------------------------
FROM python:3.12-slim

RUN useradd --create-home --uid 1000 app && mkdir /data && chown app:app /data

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
# The newsletter snapshot ships in the image; the entrypoint copies it to the data volume and
# builds the search index on first start.
COPY data/raw/posts.jsonl /app/seed/posts.jsonl
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH" \
    DATA_DIR=/data \
    PYTHONUNBUFFERED=1

USER app
VOLUME /data
EXPOSE 8000 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["isaac-says", "serve", "--host", "0.0.0.0", "--port", "8000"]
