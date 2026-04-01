"""
Ask VJ — FastAPI Entry Point

The intelligence engine API that accepts natural language queries
and returns verified, data-backed answers.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.config import load_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup, clean up on shutdown."""
    config = load_config()
    app.state.config = config
    yield


app = FastAPI(
    title="Ask VJ",
    description="Enterprise Intelligence Engine — Query Farvision, VJ Sales, and VJOP using natural language.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    config = load_config()
    uvicorn.run(
        "backend.main:app",
        host=config.api_host,
        port=config.api_port,
        reload=config.debug,
    )
