# ==============================================================================
# Football RAG - GCP Cloud Run Multi-Purpose Container (Streamlit & FastAPI)
# ==============================================================================
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080 \
    APP_MODE=streamlit

WORKDIR /app

# Install minimal OS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code (data directory is excluded via .dockerignore)
COPY . /app/

# Normalize line endings and set execute permission on entrypoint script
RUN sed -i 's/\r$//' /app/scripts/docker_entrypoint.sh && \
    chmod +x /app/scripts/docker_entrypoint.sh

# Create non-root user and ensure data mount directory exists
RUN useradd -m -u 1000 appuser && \
    mkdir -p /mnt/gcs /app/data && \
    chown -R appuser:appuser /app /mnt/gcs

USER appuser

EXPOSE 8080

ENTRYPOINT ["/bin/sh", "/app/scripts/docker_entrypoint.sh"]
