"""
Ask VJ — API Routes

Endpoints for querying, feedback, and system health.
"""

import logging
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text, create_engine

from backend.config import load_config
from backend.auth.dependencies import get_current_user
from backend.auth.models import UserInfo
from backend.intelligence.pipeline import IntelligencePipeline

logger = logging.getLogger(__name__)
router = APIRouter()

# Lazy-initialized pipeline (created on first request)
_pipeline: IntelligencePipeline | None = None


def _get_pipeline() -> IntelligencePipeline:
    global _pipeline
    if _pipeline is None:
        config = load_config()
        _pipeline = IntelligencePipeline(config)
    return _pipeline


# ── Request / Response Models ──


class QueryRequest(BaseModel):
    question: str
    session_id: str | None = None


class QueryResponse(BaseModel):
    answer: str
    confidence: str              # "high", "medium", "low"
    confidence_score: float      # 0.0 to 1.0
    data_sources: list[str]
    filters_applied: dict
    intent: str
    last_sync: str | None
    response_time_ms: int
    warnings: list[str] = []


class HealthResponse(BaseModel):
    status: str
    warehouse: str
    llm: str
    version: str


class FeedbackRequest(BaseModel):
    query_id: str
    is_correct: bool
    correction: str | None = None


# ── Endpoints ──


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """System health check — warehouse connectivity and LLM availability."""
    config = load_config()

    # Check warehouse
    warehouse_status = "disconnected"
    try:
        engine = create_engine(config.warehouse.connection_string)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        warehouse_status = "connected"
    except Exception as e:
        warehouse_status = f"error: {e}"

    # Check LLM
    llm_status = "unavailable"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{config.llm.reasoning_endpoint}/api/tags")
            if resp.status_code == 200:
                llm_status = "ready"
    except Exception:
        llm_status = "unavailable"

    overall = "ok" if warehouse_status == "connected" and llm_status == "ready" else "degraded"

    return HealthResponse(
        status=overall,
        warehouse=warehouse_status,
        llm=llm_status,
        version="0.2.0",
    )


@router.post("/query", response_model=QueryResponse)
async def query(body: QueryRequest, user: UserInfo = Depends(get_current_user)):
    """
    Submit a natural language question to Ask VJ.

    The intelligence pipeline will:
    1. Parse intent and extract entities
    2. Retrieve relevant schema context via RAG
    3. Generate and validate SQL
    4. Execute against the warehouse and verify results
    5. Format a natural language response
    """
    pipeline = _get_pipeline()

    try:
        result = await pipeline.ask(
            question=body.question,
            session_id=body.session_id,
            user_id=user.user_id,
        )
    except Exception as e:
        logger.exception("Pipeline error for question: %s", body.question)
        return QueryResponse(
            answer=f"An error occurred while processing your question. Please try again.",
            confidence="low",
            confidence_score=0.0,
            data_sources=[],
            filters_applied={},
            intent="error",
            last_sync=None,
            response_time_ms=0,
            warnings=[str(e)],
        )

    return QueryResponse(
        answer=result.answer,
        confidence=result.confidence,
        confidence_score=result.confidence_score,
        data_sources=result.data_sources,
        filters_applied=result.filters_applied,
        intent=result.intent,
        last_sync=result.last_sync,
        response_time_ms=result.response_time_ms,
        warnings=result.warnings,
    )


@router.post("/feedback")
async def submit_feedback(body: FeedbackRequest, user: UserInfo = Depends(get_current_user)):
    """User validates or corrects an answer. Used to improve accuracy over time."""
    # Store feedback in warehouse for model improvement
    try:
        config = load_config()
        engine = create_engine(config.warehouse.connection_string)
        with engine.begin() as conn:
            conn.execute(
                text("""
                    CREATE TABLE IF NOT EXISTS gold.user_feedback (
                        feedback_id SERIAL PRIMARY KEY,
                        query_id VARCHAR(100),
                        is_correct BOOLEAN,
                        correction TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)
            )
            conn.execute(
                text("""
                    INSERT INTO gold.user_feedback (query_id, is_correct, correction)
                    VALUES (:query_id, :is_correct, :correction)
                """),
                {
                    "query_id": body.query_id,
                    "is_correct": body.is_correct,
                    "correction": body.correction,
                },
            )
        return {"status": "feedback_received", "query_id": body.query_id}
    except Exception as e:
        logger.error("Failed to store feedback: %s", e)
        return {"status": "feedback_received", "query_id": body.query_id}


@router.get("/glossary")
async def get_glossary():
    """Return the business glossary for reference."""
    from backend.intelligence.glossary import GLOSSARY
    return [
        {
            "term": entry.term,
            "definition": entry.definition,
            "formula": entry.formula,
            "category": entry.category,
        }
        for entry in GLOSSARY
    ]
