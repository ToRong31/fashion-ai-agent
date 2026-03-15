FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY shared /app/shared
COPY services /app/services
RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -q --spider http://localhost:8002/.well-known/agent-card.json || exit 1

EXPOSE 8002

CMD ["python", "-m", "services.stylist.main"]
