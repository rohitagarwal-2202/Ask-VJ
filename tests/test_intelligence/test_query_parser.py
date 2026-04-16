"""
Tests for backend.intelligence.query_parser — QueryParser and ParsedQuery.

Mocks QueryParser._call_llm so no running Ollama instance is needed.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.config import LLMConfig
from backend.intelligence.query_parser import (
    ParsedQuery,
    QueryIntent,
    QueryParser,
)


@pytest.fixture
def llm_config():
    return LLMConfig()


@pytest.fixture
def parser(llm_config):
    return QueryParser(llm_config)


def _make_llm_json(**overrides):
    """Build a fake LLM JSON response with sensible defaults."""
    data = {
        "intent": "METRIC_QUERY",
        "metric": None,
        "project": None,
        "phase": None,
        "time_range": None,
        "time_start": None,
        "time_end": None,
        "group_by": None,
        "filters": [],
        "requires_previous_context": False,
        "confidence": 0.9,
    }
    data.update(overrides)
    return json.dumps(data)


def _patch_llm(json_body: str):
    """Return a patch context that mocks QueryParser._call_llm to return json_body."""
    return patch.object(
        QueryParser, "_call_llm", new_callable=AsyncMock, return_value=json_body,
    )


def _patch_llm_error():
    """Return a patch context that makes _call_llm raise an exception."""
    return patch.object(
        QueryParser, "_call_llm", new_callable=AsyncMock, side_effect=Exception("connection refused"),
    )


# ── Core parse flow ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_parse_returns_parsed_query(parser):
    """parse() should return a ParsedQuery with all fields populated from LLM JSON."""
    body = _make_llm_json(
        intent="METRIC_QUERY",
        metric="total_bookings",
        project="Yashwin Hinjawadi",
        time_range="this_month",
        confidence=0.92,
    )
    with _patch_llm(body):
        result = await parser.parse("How many bookings this month at Yashwin Hinjawadi?")

    assert isinstance(result, ParsedQuery)
    assert result.intent == QueryIntent.METRIC_QUERY
    assert result.metric == "total_bookings"
    assert result.project == "Yashwin Hinjawadi"
    assert result.time_range == "this_month"
    assert result.confidence == pytest.approx(0.92)
    assert result.raw_question == "How many bookings this month at Yashwin Hinjawadi?"


# ── Intent classification ────────────────────────────────────────

@pytest.mark.asyncio
async def test_intent_classification_sales_metric(parser):
    """Questions about booking counts should map to METRIC_QUERY."""
    body = _make_llm_json(intent="METRIC_QUERY", metric="booking_count")
    with _patch_llm(body):
        result = await parser.parse("How many bookings this month?")

    assert result.intent == QueryIntent.METRIC_QUERY


@pytest.mark.asyncio
async def test_intent_classification_collection(parser):
    """Collection efficiency questions should map to METRIC_QUERY."""
    body = _make_llm_json(intent="METRIC_QUERY", metric="collection_efficiency")
    with _patch_llm(body):
        result = await parser.parse("What is the collection efficiency this quarter?")

    assert result.intent == QueryIntent.METRIC_QUERY
    assert result.metric == "collection_efficiency"


@pytest.mark.asyncio
async def test_intent_classification_clarification(parser):
    """Terminology questions should map to CLARIFICATION."""
    body = _make_llm_json(intent="CLARIFICATION")
    with _patch_llm(body):
        result = await parser.parse("What is a booking?")

    assert result.intent == QueryIntent.CLARIFICATION


# ── Entity extraction ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_time_range_extraction(parser):
    """Verify time_range extraction for various natural language time references."""
    test_cases = [
        ("Show bookings this month", "this_month"),
        ("Collections last quarter", "last_quarter"),
        ("Total revenue for FY2026", "FY2026"),
    ]
    for question, expected_range in test_cases:
        body = _make_llm_json(time_range=expected_range)
        with _patch_llm(body):
            result = await parser.parse(question)
        assert result.time_range == expected_range, f"Failed for question: {question}"


@pytest.mark.asyncio
async def test_project_extraction(parser):
    """Verify project name extraction from the question."""
    body = _make_llm_json(project="Yashwin Hinjawadi")
    with _patch_llm(body):
        result = await parser.parse("How are bookings at Yashwin Hinjawadi?")

    assert result.project == "Yashwin Hinjawadi"


# ── Fallback on LLM error ───────────────────────────────────────

@pytest.mark.asyncio
async def test_fallback_on_llm_error(parser):
    """When the LLM call fails, parser should return a low-confidence METRIC_QUERY fallback."""
    with _patch_llm_error():
        result = await parser.parse("How many bookings?")

    assert isinstance(result, ParsedQuery)
    assert result.intent == QueryIntent.METRIC_QUERY
    assert result.confidence == pytest.approx(0.3)
    assert result.raw_question == "How many bookings?"


# ── _parse_llm_response handles markdown wrapping ────────────────

def test_parse_llm_response_strips_markdown(parser):
    """_parse_llm_response should handle markdown-fenced JSON from the LLM."""
    wrapped = "```json\n" + _make_llm_json(intent="LIST_QUERY") + "\n```"
    result = parser._parse_llm_response(wrapped, "show all bookings")
    assert result.intent == QueryIntent.LIST_QUERY


def test_parse_llm_response_with_filters(parser):
    """_parse_llm_response should correctly parse filter objects."""
    body = _make_llm_json(
        intent="LIST_QUERY",
        filters=[{"field": "project_name", "operator": "=", "value": "Yashwin"}],
    )
    result = parser._parse_llm_response(body, "bookings at Yashwin")
    assert len(result.filters) == 1
    assert result.filters[0].field == "project_name"
    assert result.filters[0].operator == "="
    assert result.filters[0].value == "Yashwin"


# ── Conversation history ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_conversation_history_updated_after_parse(parser):
    """parse() should append to conversation_history."""
    body = _make_llm_json(intent="METRIC_QUERY")
    with _patch_llm(body):
        await parser.parse("How many bookings?")

    assert len(parser.conversation_history) == 1
    assert parser.conversation_history[0]["question"] == "How many bookings?"
    assert parser.conversation_history[0]["intent"] == "METRIC_QUERY"


def test_clear_history(parser):
    """clear_history() should empty the conversation history."""
    parser.conversation_history = [{"question": "test", "intent": "METRIC_QUERY"}]
    parser.clear_history()
    assert parser.conversation_history == []
