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

# Hugging Face Spaces defaults to port 7860; can be overridden by $PORT on Cloud Run / Render
ENV PORT=7860 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy the full application (Chroma DB is baked in; see .dockerignore for exclusions)
COPY . .

# Create a non-root user for security (Hugging Face user id 1000)
RUN useradd -u 1000 --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/api/health')"

EXPOSE 7860

CMD exec uvicorn app:app --host 0.0.0.0 --port "$PORT" --workers 1 --timeout-keep-alive 75
