# ── Stage 1: build dependencies ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools needed by chromadb / onnxruntime
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim

# Cloud Run requires the app to listen on the PORT env-var (default 8080)
ENV PORT=8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy the full application (Chroma DB is baked in; see .dockerignore for exclusions)
COPY . .

# Create a non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app
USER appuser

# Health check — Cloud Run also polls /api/health for startup probes
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/api/health')"

EXPOSE $PORT

# Cloud Run sends SIGTERM on scale-down; uvicorn handles it cleanly
CMD exec uvicorn app:app --host 0.0.0.0 --port "$PORT" --workers 1 --timeout-keep-alive 75
