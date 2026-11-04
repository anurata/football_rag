#!/bin/sh
set -e

# Default port assigned by Cloud Run or fallback to 8080
PORT="${PORT:-8080}"
APP_MODE="${APP_MODE:-streamlit}"

echo "Starting Football RAG container in mode: ${APP_MODE} on port ${PORT}..."

# If GCS volume mount is present, link files and directories from /mnt/gcs into /app/data
# so legacy or relative paths (e.g. data/football.db, data/structured) resolve seamlessly.
if [ -d "/mnt/gcs" ] && [ -f "/mnt/gcs/football.db" ]; then
    echo "GCS volume detected at /mnt/gcs. Linking data into /app/data..."
    mkdir -p /app/data
    for item in /mnt/gcs/*; do
        target="/app/data/$(basename "$item")"
        if [ ! -e "$target" ]; then
            ln -sfn "$item" "$target" 2>/dev/null || true
        fi
    done
fi

if [ "$APP_MODE" = "api" ]; then
    exec uvicorn api.main:app --host 0.0.0.0 --port "$PORT"
else
    exec streamlit run app.py \
        --server.port "$PORT" \
        --server.address 0.0.0.0 \
        --server.enableCORS false \
        --server.enableXsrfProtection false \
        --browser.gatherUsageStats false
fi
