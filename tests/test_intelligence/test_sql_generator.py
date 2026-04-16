"""
Tests for backend.intelligence.sql_generator — SQL cleaning, safety validation, and generation.

Tests for _clean_sql and _validate_safety run without any LLM.
The generate() test mocks the httpx call.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.config import LLMConfig
from backend.intelligence.query_parser import ParsedQuery, QueryIntent
from backend.intelligence.sql_generator import SQLGenerator


@pytest.fixture
def generator():
    return SQLGenerator(LLMConfig())


# ── _clean_sql ───────────────────────────────────────────────────

def test_clean_sql_strips_markdown_fences(generator):
    """Markdown code fences should be removed."""
    raw = "```sql\nSELECT 1\n```"
    assert generator._clean_sql(raw) == "SELECT 1;"


def test_clean_sql_strips_sql_tag(generator):
    """A leading 'sql' language tag (from markdown) should be stripped."""
    raw = "sql\nSELECT * FROM gold.fact_bookings"
    assert generator._clean_sql(raw) == "SELECT * FROM gold.fact_bookings;"


def test_clean_sql_adds_semicolon(generator):
    """A missing trailing semicolon should be appended."""
    raw = "SELECT COUNT(*) FROM gold.fact_bookings"
    result = generator._clean_sql(raw)
    assert result.endswith(";")


def test_clean_sql_no_double_semicolon(generator):
    """If a semicolon already exists, do not add another."""
    raw = "SELECT 1;"
    result = generator._clean_sql(raw)
    assert result == "SELECT 1;"
    assert not result.endswith(";;")


def test_clean_sql_strips_whitespace(generator):
    """Leading/trailing whitespace should be removed."""
    raw = "  \n  SELECT 1;  \n  "
    assert generator._clean_sql(raw) == "SELECT 1;"


# ── _validate_safety — blocked keywords ──────────────────────────

def test_validate_safety_blocks_delete(generator):
    is_safe, _ = generator._validate_safety("DELETE FROM gold.fact_bookings;")
    assert not is_safe


def test_validate_safety_blocks_drop(generator):
    is_safe, _ = generator._validate_safety("DROP TABLE gold.fact_bookings;")
    assert not is_safe


def test_validate_safety_blocks_insert(generator):
    is_safe, _ = generator._validate_safety("INSERT INTO gold.fact_bookings VALUES (1);")
    assert not is_safe


def test_validate_safety_blocks_update(generator):
    is_safe, _ = generator._validate_safety("UPDATE gold.fact_bookings SET x = 1;")
    assert not is_safe


def test_validate_safety_blocks_truncate(generator):
    is_safe, _ = generator._validate_safety("TRUNCATE gold.fact_bookings;")
    assert not is_safe


# ── _validate_safety — allowed statements ────────────────────────

def test_validate_safety_allows_select(generator):
    is_safe, msg = generator._validate_safety(
        "SELECT COUNT(*) FROM gold.fact_bookings LIMIT 100;"
    )
    assert is_safe, f"Expected safe, got: {msg}"


def test_validate_safety_allows_with_cte(generator):
    sql = (
        "WITH cte AS (SELECT * FROM gold.fact_bookings) "
        "SELECT COUNT(*) FROM cte LIMIT 100;"
    )
    is_safe, msg = generator._validate_safety(sql)
    assert is_safe, f"Expected safe, got: {msg}"


# ── _validate_safety — structural checks ─────────────────────────

def test_validate_safety_requires_gold_schema(generator):
    """Queries that don't reference the gold schema should be rejected."""
    is_safe, msg = generator._validate_safety("SELECT 1;")
    assert not is_safe
    assert "gold schema" in msg.lower()


def test_validate_safety_rejects_non_select(generator):
    """Queries not starting with SELECT or WITH should be rejected."""
    is_safe, msg = generator._validate_safety("EXPLAIN SELECT * FROM gold.fact_bookings;")
    assert not is_safe
    assert "SELECT" in msg or "WITH" in msg


def test_validate_safety_rejects_too_long(generator):
    """Queries exceeding MAX_QUERY_LENGTH should be rejected."""
    long_sql = "SELECT * FROM gold.fact_bookings WHERE " + "x = 1 AND " * 1000 + "1 = 1;"
    assert len(long_sql) > generator.MAX_QUERY_LENGTH
    is_safe, msg = generator._validate_safety(long_sql)
    assert not is_safe
    assert "too long" in msg.lower()


def test_validate_safety_auto_adds_limit(generator):
    """A query without LIMIT should have one auto-appended rather than being rejected."""
    sql = "SELECT COUNT(*) FROM gold.fact_bookings;"
    is_safe, msg = generator._validate_safety(sql)
    assert is_safe
    # The returned message (which is the possibly-modified SQL) should contain LIMIT
    assert "LIMIT" in msg.upper()


# ── Full generate() flow with mocked LLM ────────────────────────

@pytest.mark.asyncio
async def test_generate_mocks_llm(generator):
    """generate() should call the LLM, clean the SQL, validate it, and return safe SQL."""
    fake_sql = "SELECT COUNT(*) FROM gold.fact_bookings WHERE is_cancelled = false LIMIT 1000;"

    parsed = ParsedQuery(
        intent=QueryIntent.METRIC_QUERY,
        raw_question="How many active bookings?",
        metric="booking_count",
        time_range="this_month",
        confidence=0.9,
    )

    schema_context = "-- Table: gold.fact_bookings\n-- Columns: booking_key INT, is_cancelled BOOLEAN"

    with patch.object(SQLGenerator, "_call_llm", new_callable=AsyncMock, return_value=fake_sql):
        result = await generator.generate(
            question="How many active bookings?",
            parsed=parsed,
            schema_context=schema_context,
        )

    assert "SELECT" in result.upper()
    assert "gold.fact_bookings" in result
    assert result.endswith(";")


@pytest.mark.asyncio
async def test_generate_raises_on_unsafe_sql(generator):
    """generate() should raise ValueError if the LLM returns unsafe SQL."""
    unsafe_sql = "DROP TABLE gold.fact_bookings;"

    parsed = ParsedQuery(
        intent=QueryIntent.METRIC_QUERY,
        raw_question="Drop the bookings table",
        confidence=0.5,
    )

    with patch.object(SQLGenerator, "_call_llm", new_callable=AsyncMock, return_value=unsafe_sql):
        with pytest.raises(ValueError, match="Unsafe SQL"):
            await generator.generate(
                question="Drop the bookings table",
                parsed=parsed,
                schema_context="-- gold.fact_bookings",
            )
