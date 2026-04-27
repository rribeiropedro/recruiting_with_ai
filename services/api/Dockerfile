# ─── base ────────────────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libcairo2 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ─── api ─────────────────────────────────────────────────────────────────────
FROM base AS api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ─── worker ──────────────────────────────────────────────────────────────────
FROM base AS worker

RUN pip install --no-cache-dir playwright && \
    playwright install chromium && \
    playwright install-deps chromium

CMD ["celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=info"]
