# ─────────────────────────────────────────────────────────────
# AutoMapper — Backend Dockerfile
# Runs FastAPI on port 8003
# Ollama stays on the Mac HOST — reached via host.docker.internal
# ─────────────────────────────────────────────────────────────

FROM python:3.11-slim

LABEL maintainer="AutoMapper"
LABEL description="LLM-Powered ETL Schema Mapping Service"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer cache optimisation)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/   ./backend/
COPY config/    ./config/

# Create data directories
RUN mkdir -p data/uploads data/output data/sample

# Environment defaults (override in docker-compose)
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
# When inside Docker, Ollama is on the Mac host
ENV OLLAMA_HOST=http://host.docker.internal:11434

# Expose API port
EXPOSE 8003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

# Start FastAPI with Uvicorn
CMD ["uvicorn", "backend.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8003", \
     "--workers", "1", \
     "--log-level", "info"]
