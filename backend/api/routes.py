"""
Ask VJ — API Routes

Endpoints for querying, feedback, and system health.
"""

from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    session_id: str | None = None


class QueryResponse(BaseModel):
    answer: str
    confidence: str  # "high", "medium", "low"
    data_sources: list[str]
    last_sync: str
    response_time_ms: int


class HealthResponse(BaseModel):
    status: str
    warehouse: str
    llm: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request):
    """System health check — warehouse, LLM, and API status."""
    return HealthResponse(
        status="ok",
        warehouse="connected",  # TODO: actual DB ping
        llm="ready",            # TODO: actual LLM ping
        version="0.1.0",
    )


@router.post("/query", response_model=QueryResponse)
async def query(request: Request, body: QueryRequest):
    """
    Submit a natural language query.

    The intelligence engine will:
    1. Parse intent and entities
    2. Retrieve relevant schema context
    3. Generate and execute SQL
    4. Verify results
    5. Format a natural language response
    """
    start = datetime.now()

    # TODO: Wire up the full intelligence pipeline
    # For now, return a placeholder
    elapsed = int((datetime.now() - start).total_seconds() * 1000)

    return QueryResponse(
        answer=f'Received your question: "{body.question}". Intelligence engine coming soon.',
        confidence="low",
        data_sources=[],
        last_sync="N/A",
        response_time_ms=elapsed,
    )


class FeedbackRequest(BaseModel):
    query_id: str
    is_correct: bool
    correction: str | None = None


@router.post("/feedback")
async def submit_feedback(body: FeedbackRequest):
    """User validates or corrects an answer. Used to improve accuracy over time."""
    # TODO: Store feedback for model improvement
    return {"status": "feedback_received", "query_id": body.query_id}
