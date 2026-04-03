"""
Ask VJ — User Preference API Routes

Endpoints for managing per-user business term overrides.
All routes require authentication.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from backend.auth.dependencies import get_current_user
from backend.auth.models import UserInfo
from backend.intelligence.user_context import UserContextManager

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request/Response Models ──


class PreferenceBody(BaseModel):
    term: str
    definition: str
    sql_hint: str | None = None


class AcceptSuggestionBody(BaseModel):
    term: str
    definition: str


# ── Routes ──


@router.get("/preferences")
async def list_preferences(
    request: Request,
    user: UserInfo = Depends(get_current_user),
):
    """List current user's preferences."""
    engine = request.app.state.auth_engine
    ctx = UserContextManager(engine)
    prefs = ctx.load_preferences(user.user_id)
    return [
        {
            "term": p.term,
            "definition": p.definition,
            "sql_hint": p.sql_hint,
            "source": p.source,
            "confidence": p.confidence,
        }
        for p in prefs
    ]


@router.post("/preferences", status_code=status.HTTP_201_CREATED)
async def save_preference(
    body: PreferenceBody,
    request: Request,
    user: UserInfo = Depends(get_current_user),
):
    """Add or update a user preference."""
    engine = request.app.state.auth_engine
    ctx = UserContextManager(engine)
    ctx.save_preference(
        user_id=user.user_id,
        term=body.term,
        definition=body.definition,
        sql_hint=body.sql_hint,
        source="manual",
    )
    return {"status": "saved", "term": body.term}


@router.delete("/preferences/{term}")
async def delete_preference(
    term: str,
    request: Request,
    user: UserInfo = Depends(get_current_user),
):
    """Delete a user preference."""
    engine = request.app.state.auth_engine
    ctx = UserContextManager(engine)
    ctx.delete_preference(user.user_id, term)
    return {"status": "deleted", "term": term}


@router.get("/preferences/suggestions")
async def get_suggestions(
    request: Request,
    user: UserInfo = Depends(get_current_user),
):
    """Get auto-detected patterns (corrections made 3+ times)."""
    engine = request.app.state.auth_engine
    ctx = UserContextManager(engine)
    suggestions = ctx.check_learned_patterns(user.user_id)
    return [
        {
            "term": s.term,
            "suggested_definition": s.suggested_definition,
            "occurrence_count": s.occurrence_count,
        }
        for s in suggestions
    ]


@router.post("/preferences/accept-suggestion")
async def accept_suggestion(
    body: AcceptSuggestionBody,
    request: Request,
    user: UserInfo = Depends(get_current_user),
):
    """Accept a suggestion and save it as a learned preference."""
    engine = request.app.state.auth_engine
    ctx = UserContextManager(engine)
    ctx.save_preference(
        user_id=user.user_id,
        term=body.term,
        definition=body.definition,
        source="learned",
    )
    return {"status": "accepted", "term": body.term}
