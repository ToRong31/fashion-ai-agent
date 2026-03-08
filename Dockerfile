FROM python:3.13-slim AS base

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

ENV PYTHONPATH=/app

CMD ["python", "-m", "agents.orchestrator.main"]
