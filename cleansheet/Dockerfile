# CleanSheet web MVP — single-container beta deployment.
# No database, no volumes, no secrets required. Run with ONE worker:
# in-memory rate limits and download tokens are per-process.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY pyproject.toml README.md ./
COPY cleaning_engine ./cleaning_engine
COPY backend ./backend

RUN pip install --no-cache-dir ".[api]"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT', '8000') + '/api/health')"

CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
