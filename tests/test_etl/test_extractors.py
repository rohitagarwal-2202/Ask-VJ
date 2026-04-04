"""
Tests for ETL extractors — validates task configuration without real DB connections.

Instantiates extractors with dummy connection strings to test that
extract_tasks are properly defined with required fields and naming conventions.
"""

import pytest
from unittest.mock import patch, MagicMock


# Patch create_engine before importing extractors so __init__ does not
# attempt a real database connection.
@pytest.fixture()
def farvision_extractor():
    with patch("backend.etl.extractors.base.create_engine", return_value=MagicMock()):
        from backend.etl.extractors.farvision import FarvisionExtractor
        return FarvisionExtractor(
            source_connection_string="mssql+pyodbc://dummy",
            warehouse_connection_string="postgresql://dummy",
        )


@pytest.fixture()
def vjsales_extractor():
    with patch("backend.etl.extractors.base.create_engine", return_value=MagicMock()):
        from backend.etl.extractors.vj_sales import VJSalesExtractor
        return VJSalesExtractor(
            source_connection_string="postgresql://dummy",
            warehouse_connection_string="postgresql://dummy",
        )


@pytest.fixture()
def vjop_extractor():
    with patch("backend.etl.extractors.base.create_engine", return_value=MagicMock()):
        from backend.etl.extractors.vjop import VJOPExtractor
        return VJOPExtractor(
            source_connection_string="mssql+pyodbc://dummy",
            warehouse_connection_string="postgresql://dummy",
        )


# ──────────────────────────────────────────────────────────────────────
# Farvision Extractor Tests
# ──────────────────────────────────────────────────────────────────────

class TestFarvisionExtractor:

    def test_farvision_extractor_has_tasks(self, farvision_extractor):
        tasks = farvision_extractor.get_extract_tasks()
        assert len(tasks) > 0, "Farvision extractor should have at least one task"

    def test_farvision_all_tasks_have_required_fields(self, farvision_extractor):
        tasks = farvision_extractor.get_extract_tasks()
        required_fields = {"staging_table", "full_query", "source_query"}
        for i, task in enumerate(tasks):
            missing = required_fields - set(task.keys())
            assert not missing, (
                f"Task {i} ({task.get('staging_table', '?')}) missing fields: {missing}"
            )

    def test_farvision_all_queries_have_tenant_filter(self, farvision_extractor):
        tasks = farvision_extractor.get_extract_tasks()
        for task in tasks:
            full_q = task["full_query"]
            # Some tables don't have TenantId column
            if "dbo.DimDate" in full_q or "DimBookingCancellation" in full_q:
                continue
            assert "TenantId" in full_q or "Tenantid" in full_q, (
                f"full_query for {task['staging_table']} should contain TenantId filter, "
                f"got: {full_q[:120]}..."
            )

    def test_farvision_task_count(self, farvision_extractor):
        tasks = farvision_extractor.get_extract_tasks()
        assert len(tasks) == 16, f"Expected 16 Farvision tasks, got {len(tasks)}"

    def test_farvision_staging_tables_start_with_bronze(self, farvision_extractor):
        tasks = farvision_extractor.get_extract_tasks()
        for task in tasks:
            assert task["staging_table"].startswith("bronze.stg_fv_"), (
                f"Staging table should start with 'bronze.stg_fv_', "
                f"got: {task['staging_table']}"
            )

    def test_farvision_source_name(self, farvision_extractor):
        assert farvision_extractor.source_name == "farvision"


# ──────────────────────────────────────────────────────────────────────
# VJ Sales Extractor Tests
# ──────────────────────────────────────────────────────────────────────

class TestVJSalesExtractor:

    def test_vjsales_extractor_has_tasks(self, vjsales_extractor):
        tasks = vjsales_extractor.get_extract_tasks()
        assert len(tasks) > 0, "VJ Sales extractor should have at least one task"

    def test_vjsales_task_count(self, vjsales_extractor):
        tasks = vjsales_extractor.get_extract_tasks()
        assert 10 <= len(tasks) <= 12, (
            f"Expected 10-12 VJ Sales tasks, got {len(tasks)}"
        )

    def test_vjsales_staging_tables_start_with_bronze(self, vjsales_extractor):
        tasks = vjsales_extractor.get_extract_tasks()
        for task in tasks:
            assert task["staging_table"].startswith("bronze.stg_vj_"), (
                f"Staging table should start with 'bronze.stg_vj_', "
                f"got: {task['staging_table']}"
            )

    def test_vjsales_all_tasks_have_required_fields(self, vjsales_extractor):
        tasks = vjsales_extractor.get_extract_tasks()
        required_fields = {"staging_table", "full_query", "source_query"}
        for i, task in enumerate(tasks):
            missing = required_fields - set(task.keys())
            assert not missing, (
                f"Task {i} ({task.get('staging_table', '?')}) missing fields: {missing}"
            )

    def test_vjsales_source_name(self, vjsales_extractor):
        assert vjsales_extractor.source_name == "vjsales"


# ──────────────────────────────────────────────────────────────────────
# VJOP Extractor Tests
# ──────────────────────────────────────────────────────────────────────

class TestVJOPExtractor:

    def test_vjop_extractor_has_tasks(self, vjop_extractor):
        tasks = vjop_extractor.get_extract_tasks()
        assert len(tasks) > 0, "VJOP extractor should have at least one task"

    def test_vjop_task_count(self, vjop_extractor):
        tasks = vjop_extractor.get_extract_tasks()
        assert len(tasks) == 6, f"Expected 6 VJOP tasks, got {len(tasks)}"

    def test_vjop_staging_tables_start_with_bronze(self, vjop_extractor):
        tasks = vjop_extractor.get_extract_tasks()
        for task in tasks:
            assert task["staging_table"].startswith("bronze.stg_rnl_"), (
                f"Staging table should start with 'bronze.stg_rnl_', "
                f"got: {task['staging_table']}"
            )

    def test_vjop_source_name_is_vjop(self, vjop_extractor):
        assert vjop_extractor.source_name == "vjop"

    def test_vjop_all_tasks_have_required_fields(self, vjop_extractor):
        tasks = vjop_extractor.get_extract_tasks()
        required_fields = {"staging_table", "full_query", "source_query"}
        for i, task in enumerate(tasks):
            missing = required_fields - set(task.keys())
            assert not missing, (
                f"Task {i} ({task.get('staging_table', '?')}) missing fields: {missing}"
            )
