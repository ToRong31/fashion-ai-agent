FROM python:3.13-slim

WORKDIR /app

COPY ../pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY . .

ENV PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -q --spider http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["python", "-m", "src.main"]
