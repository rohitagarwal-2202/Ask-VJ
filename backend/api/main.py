"""
Ask VJ — FastAPI Application Entry Point

Usage:
    uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
    # or
    python -m backend.api.main
"""

import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.config import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(
    title="Ask VJ",
    description="Natural language interface for VJ real estate data",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


if __name__ == "__main__":
    config = load_config()
    uvicorn.run(
        "backend.api.main:app",
        host=config.api_host,
        port=config.api_port,
        reload=config.debug,
    )
