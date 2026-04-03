"""
Tests for backend.intelligence.schema_retriever — SchemaRetriever rule-based matching.

These tests exercise _rule_based_match and format_schema_for_prompt directly,
so no LLM or vector DB connection is needed.
"""

import pytest

from backend.config import LLMConfig, VectorDBConfig
from backend.intelligence.schema_retriever import GOLD_SCHEMA, SchemaRetriever


@pytest.fixture
def retriever():
    """Create a SchemaRetriever with dummy configs (not called for rule-based tests)."""
    return SchemaRetriever(
        llm_config=LLMConfig(),
        vector_db_config=VectorDBConfig(),
    )


def _table_names(schemas):
    """Extract table names from a list of TableSchema objects."""
    return [s.table_name for s in schemas]


# ── GOLD_SCHEMA structure ────────────────────────────────────────

def test_gold_schema_has_all_tables():
    """The gold schema should contain exactly 15 tables."""
    assert len(GOLD_SCHEMA) == 15


def test_gold_schema_table_names():
    """Verify that specific expected table names are present."""
    names = {s.table_name for s in GOLD_SCHEMA}
    expected = {
        "gold.dim_date",
        "gold.dim_projects",
        "gold.dim_typologies",
        "gold.dim_units",
        "gold.dim_customers",
        "gold.dim_sales_persons",
        "gold.dim_lead_sources",
        "gold.fact_lead_pipeline",
        "gold.fact_bookings",
        "gold.fact_receipts",
        "gold.fact_invoices",
        "gold.snapshot_outstanding",
        "gold.snapshot_inventory",
        "gold.snapshot_referrals",
        "gold.fact_daily_funnel_snapshot",
    }
    assert expected == names


# ── Rule-based matching ──────────────────────────────────────────

def test_rule_match_booking_query(retriever):
    """Booking questions should match fact_bookings and dim_projects."""
    matched = retriever._rule_based_match("How many bookings this month?", None)
    names = _table_names(matched)
    assert "gold.fact_bookings" in names
    assert "gold.dim_projects" in names


def test_rule_match_collection_query(retriever):
    """Collection questions should match fact_receipts and dim_projects."""
    matched = retriever._rule_based_match("What is the collection this quarter?", None)
    names = _table_names(matched)
    assert "gold.fact_receipts" in names
    assert "gold.dim_projects" in names


def test_rule_match_outstanding_query(retriever):
    """Outstanding questions should match fact_outstanding."""
    matched = retriever._rule_based_match("Show outstanding aging analysis", None)
    names = _table_names(matched)
    assert "gold.snapshot_outstanding" in names


def test_rule_match_inventory_query(retriever):
    """Inventory questions should match fact_inventory."""
    matched = retriever._rule_based_match("Available inventory in project X", None)
    names = _table_names(matched)
    assert "gold.snapshot_inventory" in names


def test_rule_match_referral_query(retriever):
    """Referral questions should match fact_referrals."""
    matched = retriever._rule_based_match("Top referrers from VJOP", None)
    names = _table_names(matched)
    assert "gold.snapshot_referrals" in names


def test_rule_match_typology_query(retriever):
    """Typology / BHK questions should match dim_typologies."""
    matched = retriever._rule_based_match("Show 3 BHK breakdown", None)
    names = _table_names(matched)
    assert "gold.dim_typologies" in names


def test_rule_match_lead_query(retriever):
    """Lead/pipeline questions should match fact_lead_pipeline."""
    matched = retriever._rule_based_match("How many leads this month?", None)
    names = _table_names(matched)
    assert "gold.fact_lead_pipeline" in names


def test_rule_match_funnel_query(retriever):
    """Funnel/conversion questions should match fact_daily_funnel_snapshot."""
    matched = retriever._rule_based_match("Show funnel conversion rates", None)
    names = _table_names(matched)
    assert "gold.fact_daily_funnel_snapshot" in names


def test_rule_match_customer_query(retriever):
    """Customer questions should match dim_customers."""
    matched = retriever._rule_based_match("List all customers", None)
    names = _table_names(matched)
    assert "gold.dim_customers" in names


# ── dim_date auto-inclusion ──────────────────────────────────────

@pytest.mark.asyncio
async def test_dim_date_auto_included_with_facts(retriever):
    """When fact tables are matched, dim_date should be auto-included by retrieve()."""
    # Mock embedding to avoid network calls -- make it raise so only rule-based runs
    retriever._embedding_match = lambda *a, **kw: (_ for _ in ()).throw(Exception("skip"))

    schemas = await retriever.retrieve("How many bookings this month?", top_k=10)
    names = _table_names(schemas)
    assert "gold.fact_bookings" in names
    assert "gold.dim_date" in names


# ── format_schema_for_prompt ─────────────────────────────────────

def test_format_schema_for_prompt_contains_columns(retriever):
    """Formatted schema output should include table names, descriptions, and column names."""
    schemas = retriever._rule_based_match("How many bookings?", None)
    output = retriever.format_schema_for_prompt(schemas)

    assert "gold.fact_bookings" in output
    assert "booking_key" in output
    assert "is_cancelled" in output
    assert "-- Columns:" in output


def test_format_schema_for_prompt_contains_joins(retriever):
    """Formatted output should include join information when present."""
    schemas = retriever._rule_based_match("Show all units", None)
    output = retriever.format_schema_for_prompt(schemas)

    assert "-- Joins:" in output


def test_format_schema_for_prompt_empty(retriever):
    """Formatting an empty schema list should return an empty string."""
    output = retriever.format_schema_for_prompt([])
    assert output == ""
