#!/bin/sh
set -e

# Default port assigned by Cloud Run or fallback to 8080
PORT="${PORT:-8080}"
APP_MODE="${APP_MODE:-streamlit}"

echo "Starting Football RAG container in mode: ${APP_MODE} on port ${PORT}..."

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
