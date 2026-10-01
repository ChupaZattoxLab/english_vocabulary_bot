# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock README.md ./
COPY tgbot tgbot
COPY scripts scripts
COPY migrations migrations
COPY alembic.ini ./

RUN uv sync --frozen --no-dev

# Runtime uses migrate-then-bot via compose command; default is the bot process.
CMD ["python", "-m", "tgbot"]
