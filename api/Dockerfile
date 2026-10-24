# Steward API — production image
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --system steward && useradd --system --gid steward --home /app steward
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
# Private storage lives on a volume, outside any web root. Never served statically.
RUN mkdir -p /data/storage /data/mail-outbox && chown -R steward:steward /data
USER steward
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
