"""
FastAPI application entry point for Football RAG Mobile Backend.
"""

from __future__ import annotations

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import actions, context, notes_photos
from pipeline.db import init_db

app = FastAPI(
    title="Football RAG Mobile API",
    description="Backend API supporting fast match-day actions, tactical pitch, notes, and photos.",
    version="1.0.0",
)

# Enable CORS for Flutter mobile / web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure database tables exist
init_db()

# Ensure uploads directory exists and mount static file server
UPLOAD_DIR = Path("data") / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Include Routers
app.include_router(context.router)
app.include_router(actions.router)
app.include_router(notes_photos.router)


@app.get("/api/health")
def health_check() -> dict:
    """Basic health check probe."""
    return {
        "status": "healthy",
        "service": "football_rag_mobile_api",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
