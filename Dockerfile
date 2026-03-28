FROM python:3.13-slim AS base

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
RUN uv pip install --no-cache --system .

COPY . .

ENV PYTHONPATH=/app

CMD ["python", "-m", "agents.orchestrator.main"]
