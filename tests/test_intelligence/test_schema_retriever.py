"""
Tests for Ask VJ Schema Retriever.

Covers GOLD_SCHEMA metadata, rule-based matching, and prompt formatting.
"""

import pytest

from backend.config import LLMConfig, VectorDBConfig
from backend.intelligence.schema_retriever import SchemaRetriever, GOLD_SCHEMA, TableSchema


def _table_names(schemas: list[TableSchema]) -> list[str]:
    return [s.table_name for s in schemas]


@pytest.fixture
def retriever():
    return SchemaRetriever(LLMConfig(), VectorDBConfig())


# ── Schema metadata ────────────────────────────────────────────

def test_gold_schema_has_all_tables():
    """Verify we have the expected number of Gold schema entries."""
    assert len(GOLD_SCHEMA) >= 15, f"Expected at least 15 GOLD_SCHEMA entries, got {len(GOLD_SCHEMA)}"


def test_gold_schema_table_names():
    """Verify that key expected table/view names are present."""
    names = {s.table_name for s in GOLD_SCHEMA}
    # Views (over Silver)
    assert "gold.v_projects" in names
    assert "gold.v_units" in names
    assert "gold.v_buyers" in names
    assert "gold.v_employees" in names
    assert "gold.v_channel_partners" in names
    assert "gold.v_leads" in names
    assert "gold.v_site_visits" in names
    # Kept tables
    assert "gold.dim_date" in names
    assert "gold.fact_bookings" in names
    assert "gold.fact_receipts" in names
    assert "gold.snapshot_outstanding" in names
    assert "gold.snapshot_inventory" in names
    assert "gold.snapshot_referrals" in names
    assert "gold.fact_daily_funnel_snapshot" in names


# ── Rule-based matching ──────────────────────────────────────────

def test_rule_match_booking_query(retriever):
    """Booking questions should match fact_bookings and v_projects."""
    matched = retriever._rule_based_match("How many bookings this month?", None)
    names = _table_names(matched)
    assert "gold.fact_bookings" in names
    assert "gold.v_projects" in names


def test_rule_match_collection_query(retriever):
    """Collection questions should match fact_receipts and v_projects."""
    matched = retriever._rule_based_match("What is the collection this quarter?", None)
    names = _table_names(matched)
    assert "gold.fact_receipts" in names
    assert "gold.v_projects" in names


def test_rule_match_outstanding_query(retriever):
    """Outstanding questions should match snapshot_outstanding."""
    matched = retriever._rule_based_match("Show outstanding aging analysis", None)
    names = _table_names(matched)
    assert "gold.snapshot_outstanding" in names


def test_rule_match_inventory_query(retriever):
    """Inventory questions should match snapshot_inventory."""
    matched = retriever._rule_based_match("Available inventory in project X", None)
    names = _table_names(matched)
    assert "gold.snapshot_inventory" in names


def test_rule_match_referral_query(retriever):
    """Referral questions should match snapshot_referrals."""
    matched = retriever._rule_based_match("Top referrers from VJOP", None)
    names = _table_names(matched)
    assert "gold.snapshot_referrals" in names


def test_rule_match_typology_query(retriever):
    """Typology/BHK questions should match v_units (has unit_type/display_unit_type)."""
    matched = retriever._rule_based_match("Show 3 BHK flats available", None)
    names = _table_names(matched)
    # Should match v_units which has unit_type and display_unit_type
    assert any("v_units" in n or "snapshot_inventory" in n for n in names)


def test_rule_match_lead_query(retriever):
    """Lead questions should match v_leads."""
    matched = retriever._rule_based_match("How many leads this month?", None)
    names = _table_names(matched)
    assert "gold.v_leads" in names


def test_rule_match_funnel_query(retriever):
    """Funnel/conversion questions should match funnel snapshot."""
    matched = retriever._rule_based_match("Show conversion rate trend this quarter", None)
    names = _table_names(matched)
    assert "gold.fact_daily_funnel_snapshot" in names or "gold.v_conversion_rates" in names


def test_rule_match_customer_query(retriever):
    """Customer/buyer questions should match v_buyers."""
    matched = retriever._rule_based_match("Show customer details for buyer X", None)
    names = _table_names(matched)
    assert "gold.v_buyers" in names


def test_rule_match_site_visit_query(retriever):
    """Site visit questions should match v_site_visits."""
    matched = retriever._rule_based_match("How many site visits this month?", None)
    names = _table_names(matched)
    assert "gold.v_site_visits" in names


@pytest.mark.asyncio
async def test_dim_date_auto_included_with_facts(retriever):
    """dim_date should be auto-included when fact tables are matched."""
    schemas = await retriever.retrieve("Total bookings this month", "bookings")
    names = _table_names(schemas)
    has_fact = any(n.startswith("gold.fact_") or n.startswith("gold.snapshot_") for n in names)
    if has_fact:
        assert "gold.dim_date" in names


def test_format_schema_for_prompt_contains_columns(retriever):
    """Formatted schema should contain column information."""
    schemas = [GOLD_SCHEMA[0]]  # dim_date
    formatted = retriever.format_schema_for_prompt(schemas)
    assert "date_key" in formatted
    assert "gold.dim_date" in formatted


def test_format_schema_for_prompt_empty():
    """Empty schema list should produce empty string."""
    retriever = SchemaRetriever(LLMConfig(), VectorDBConfig())
    assert retriever.format_schema_for_prompt([]) == ""
