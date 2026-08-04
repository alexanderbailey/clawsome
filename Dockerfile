FROM python:3.12-slim-bookworm

WORKDIR /app

# Pinned, not :latest — a floating tag silently changes the build tool between
# builds, which is the same reproducibility `uv sync --frozen` is protecting
# two lines below. Dependabot keeps this current.
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev && \
    uv run playwright install --with-deps chromium

COPY src/ src/
COPY skill/ skill/

ENV HOST=0.0.0.0 \
    PORT=3000

EXPOSE 3000

# Shell form so HOST/PORT are expanded at runtime rather than baked in at build.
CMD uv run uvicorn src.app:app --host "$HOST" --port "$PORT"
