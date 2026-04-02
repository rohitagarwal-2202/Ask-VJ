"""
Tests for Ask VJ API routes.

Covers health, query, feedback, and glossary endpoints.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport

from backend.api.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_pipeline_result(**overrides):
    """Return a mock object that looks like a pipeline result."""
    defaults = {
        "answer": "Total sales are AED 1.2M.",
        "confidence": "high",
        "confidence_score": 0.92,
        "data_sources": ["gold.sales_summary"],
        "filters_applied": {"tenant_id": 75},
        "intent": "aggregation",
        "last_sync": "2026-04-01T12:00:00Z",
        "response_time_ms": 340,
        "warnings": [],
    }
    defaults.update(overrides)
    result = MagicMock()
    for k, v in defaults.items():
        setattr(result, k, v)
    return result


@pytest.fixture
def async_client():
    """Provide an httpx AsyncClient wired to the FastAPI app."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# /api/health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(async_client):
    with (
        patch("backend.api.routes.create_engine") as mock_engine,
        patch("backend.api.routes.httpx.AsyncClient") as mock_httpx,
    ):
        # Warehouse check succeeds
        mock_conn = MagicMock()
        mock_engine.return_value.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.return_value.connect.return_value.__exit__ = MagicMock(return_value=False)

        # LLM check succeeds
        mock_resp = MagicMock(status_code=200)
        mock_http_instance = AsyncMock()
        mock_http_instance.get.return_value = mock_resp
        mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
        mock_http_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_http_instance

        async with async_client as ac:
            resp = await ac.get("/api/health")

        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_endpoint_response_fields(async_client):
    with (
        patch("backend.api.routes.create_engine") as mock_engine,
        patch("backend.api.routes.httpx.AsyncClient") as mock_httpx,
    ):
        mock_conn = MagicMock()
        mock_engine.return_value.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.return_value.connect.return_value.__exit__ = MagicMock(return_value=False)

        mock_resp = MagicMock(status_code=200)
        mock_http_instance = AsyncMock()
        mock_http_instance.get.return_value = mock_resp
        mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
        mock_http_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_http_instance

        async with async_client as ac:
            resp = await ac.get("/api/health")

        data = resp.json()
        assert "status" in data
        assert "warehouse" in data
        assert "llm" in data
        assert "version" in data


@pytest.mark.asyncio
async def test_health_degraded_when_warehouse_fails(async_client):
    with (
        patch("backend.api.routes.create_engine") as mock_engine,
        patch("backend.api.routes.httpx.AsyncClient") as mock_httpx,
    ):
        # Warehouse check raises
        mock_engine.return_value.connect.side_effect = Exception("connection refused")

        # LLM check succeeds
        mock_resp = MagicMock(status_code=200)
        mock_http_instance = AsyncMock()
        mock_http_instance.get.return_value = mock_resp
        mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
        mock_http_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_http_instance

        async with async_client as ac:
            resp = await ac.get("/api/health")

        data = resp.json()
        assert data["status"] == "degraded"


# ---------------------------------------------------------------------------
# /api/query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_endpoint_returns_200(async_client):
    mock_result = _mock_pipeline_result()
    mock_pipeline = MagicMock()
    mock_pipeline.ask = AsyncMock(return_value=mock_result)

    with patch("backend.api.routes._get_pipeline", return_value=mock_pipeline):
        async with async_client as ac:
            resp = await ac.post("/api/query", json={"question": "What are total sales?"})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_query_endpoint_requires_question(async_client):
    async with async_client as ac:
        resp = await ac.post("/api/query", json={})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_query_endpoint_handles_pipeline_error(async_client):
    mock_pipeline = MagicMock()
    mock_pipeline.ask = AsyncMock(side_effect=RuntimeError("LLM timeout"))

    with patch("backend.api.routes._get_pipeline", return_value=mock_pipeline):
        async with async_client as ac:
            resp = await ac.post("/api/query", json={"question": "break things"})

    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data["answer"].lower() or data["intent"] == "error"
    assert data["confidence"] == "low"
    assert data["confidence_score"] == 0.0


@pytest.mark.asyncio
async def test_query_response_has_all_fields(async_client):
    mock_result = _mock_pipeline_result()
    mock_pipeline = MagicMock()
    mock_pipeline.ask = AsyncMock(return_value=mock_result)

    with patch("backend.api.routes._get_pipeline", return_value=mock_pipeline):
        async with async_client as ac:
            resp = await ac.post("/api/query", json={"question": "What are total sales?"})

    data = resp.json()
    expected_fields = [
        "answer", "confidence", "confidence_score", "data_sources",
        "filters_applied", "intent", "last_sync", "response_time_ms", "warnings",
    ]
    for field in expected_fields:
        assert field in data, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# /api/feedback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feedback_endpoint_returns_200(async_client):
    with patch("backend.api.routes.create_engine") as mock_engine:
        mock_conn = MagicMock()
        mock_conn.execute = MagicMock()
        mock_engine.return_value.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.return_value.begin.return_value.__exit__ = MagicMock(return_value=False)

        async with async_client as ac:
            resp = await ac.post("/api/feedback", json={
                "query_id": "abc-123",
                "is_correct": True,
            })

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "feedback_received"
    assert data["query_id"] == "abc-123"


@pytest.mark.asyncio
async def test_feedback_requires_fields(async_client):
    async with async_client as ac:
        resp = await ac.post("/api/feedback", json={"is_correct": True})

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /api/glossary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_glossary_endpoint_returns_list(async_client):
    async with async_client as ac:
        resp = await ac.get("/api/glossary")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_glossary_entries_have_fields(async_client):
    async with async_client as ac:
        resp = await ac.get("/api/glossary")

    data = resp.json()
    assert len(data) > 0, "Glossary should not be empty for field check"
    entry = data[0]
    for field in ("term", "definition", "formula", "category"):
        assert field in entry, f"Glossary entry missing field: {field}"


@pytest.mark.asyncio
async def test_glossary_not_empty(async_client):
    async with async_client as ac:
        resp = await ac.get("/api/glossary")

    data = resp.json()
    assert len(data) > 0, "Glossary should contain at least one entry"
