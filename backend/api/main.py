"""
Ask VJ — FastAPI Application Entry Point

Usage:
    uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
    # or
    python -m backend.api.main
"""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine

from backend.api.routes import router
from backend.auth.routes import router as auth_router
from backend.auth.admin_routes import router as admin_router
from backend.auth.guardrail_routes import router as guardrail_router
from backend.auth.preference_routes import router as preference_router
from backend.auth.otp_gateway import create_otp_gateway
from backend.config import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialize shared resources on startup."""
    config = load_config()
    application.state.config = config
    application.state.auth_engine = create_engine(config.warehouse.connection_string)
    application.state.otp_gateway = create_otp_gateway(config.auth)
    yield
    application.state.auth_engine.dispose()


app = FastAPI(
    title="Ask VJ",
    description="Natural language interface for VJ real estate data",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth routes — no authentication required
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

# Admin routes — admin role required (enforced in router)
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])

# Guardrail admin routes — admin role required
app.include_router(guardrail_router, prefix="/api/admin", tags=["admin"])

# Preference routes — authentication required
app.include_router(preference_router, prefix="/api", tags=["preferences"])

# Main API routes — authentication required (enforced per-endpoint)
app.include_router(router, prefix="/api", tags=["query"])


if __name__ == "__main__":
    config = load_config()
    uvicorn.run(
        "backend.api.main:app",
        host=config.api_host,
        port=config.api_port,
        reload=config.debug,
    )
