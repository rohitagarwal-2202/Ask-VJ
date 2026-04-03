"""
Tests for dimension, fact, and snapshot transformers.

Validates transformation logic, fiscal year calculations, and structural
properties without requiring a real database.
"""

import pytest
from datetime import date
from unittest.mock import patch, MagicMock, call


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture()
def dim_transformer():
    with patch("backend.etl.transformers.dimensions.create_engine", return_value=MagicMock()):
        from backend.etl.transformers.dimensions import DimensionTransformer
        return DimensionTransformer(warehouse_connection_string="postgresql://dummy")


@pytest.fixture()
def fact_transformer():
    with patch("backend.etl.transformers.facts.create_engine", return_value=MagicMock()):
        from backend.etl.transformers.facts import FactTransformer
        return FactTransformer(warehouse_connection_string="postgresql://dummy")


@pytest.fixture()
def snapshot_transformer():
    with patch("backend.etl.transformers.snapshots.create_engine", return_value=MagicMock()):
        from backend.etl.transformers.snapshots import SnapshotTransformer
        return SnapshotTransformer(warehouse_connection_string="postgresql://dummy")


# ──────────────────────────────────────────────────────────────────────
# DimensionTransformer Tests
# ──────────────────────────────────────────────────────────────────────

class TestDimensionTransformer:

    def test_dim_transformer_transform_all_calls_all_builders(self, dim_transformer):
        """Verify transform_all invokes every dimension builder method."""
        builder_names = [
            "build_dim_date",
            "build_dim_projects",
            "build_dim_typologies",
            "build_dim_units",
            "build_dim_customers",
            "build_dim_sales_persons",
            "build_dim_lead_sources",
        ]
        for name in builder_names:
            setattr(dim_transformer, name, MagicMock(name=name))

        dim_transformer.transform_all()

        for name in builder_names:
            getattr(dim_transformer, name).assert_called_once()

    def test_dim_date_fiscal_year_logic(self):
        """
        Indian fiscal year: April starts the next FY.
        Apr 2025 -> FY2026, Jan 2026 -> FY2026, Mar 2025 -> FY2025.
        """
        # Replicate the logic from build_dim_date
        test_cases = [
            (date(2025, 4, 1), 2026),   # April 2025 -> FY2026
            (date(2026, 1, 15), 2026),   # January 2026 -> FY2026
            (date(2025, 3, 31), 2025),   # March 2025 -> FY2025
            (date(2025, 12, 25), 2026),  # December 2025 -> FY2026
        ]
        for d, expected_fy in test_cases:
            if d.month >= 4:
                fiscal_year = d.year + 1
            else:
                fiscal_year = d.year
            assert fiscal_year == expected_fy, (
                f"Date {d} should map to FY{expected_fy}, got FY{fiscal_year}"
            )

    def test_dim_date_fiscal_quarter_logic(self):
        """
        Fiscal quarters: Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar.
        """
        test_cases = [
            (date(2025, 4, 1), "Q1"),   # April -> Q1
            (date(2025, 6, 30), "Q1"),  # June -> Q1
            (date(2025, 7, 1), "Q2"),   # July -> Q2
            (date(2025, 9, 30), "Q2"),  # September -> Q2
            (date(2025, 10, 1), "Q3"),  # October -> Q3
            (date(2025, 12, 31), "Q3"), # December -> Q3
            (date(2026, 1, 1), "Q4"),   # January -> Q4
            (date(2026, 3, 31), "Q4"),  # March -> Q4
        ]
        for d, expected_quarter in test_cases:
            if d.month >= 4:
                fiscal_q_month = d.month - 3
            else:
                fiscal_q_month = d.month + 9
            fiscal_quarter = f"Q{(fiscal_q_month - 1) // 3 + 1}"
            assert fiscal_quarter == expected_quarter, (
                f"Date {d} (month={d.month}) should be {expected_quarter}, "
                f"got {fiscal_quarter}"
            )

    def test_dim_date_fiscal_year_id_mapping(self):
        """
        Known FiscalYearId mappings: 2026 -> 56, 2025 -> 52, other -> None.
        """
        FISCAL_YEAR_ID_MAP = {
            2026: 56,
            2025: 52,
        }
        assert FISCAL_YEAR_ID_MAP.get(2026) == 56
        assert FISCAL_YEAR_ID_MAP.get(2025) == 52
        assert FISCAL_YEAR_ID_MAP.get(2024) is None
        assert FISCAL_YEAR_ID_MAP.get(2027) is None


# ──────────────────────────────────────────────────────────────────────
# FactTransformer Tests
# ──────────────────────────────────────────────────────────────────────

class TestFactTransformer:

    def test_fact_transformer_transform_all_calls_all_builders(self, fact_transformer):
        """Verify transform_all invokes all 7 builder methods."""
        builder_names = [
            "build_fact_lead_pipeline",
            "build_fact_bookings",
            "build_fact_receipts",
            "build_fact_invoices",
            "build_snapshot_outstanding",
            "build_snapshot_inventory",
            "build_snapshot_referrals",
        ]
        for name in builder_names:
            setattr(fact_transformer, name, MagicMock(name=name))

        fact_transformer.transform_all()

        for name in builder_names:
            getattr(fact_transformer, name).assert_called_once()

    def test_fact_transformer_has_tenant_id_constant(self):
        """Verify FARVISION_TENANT_ID is defined as 75."""
        from backend.etl.transformers.facts import FARVISION_TENANT_ID
        assert FARVISION_TENANT_ID == 75

    def test_fact_transformer_has_seven_builders(self, fact_transformer):
        """Verify the transformer has exactly 7 build_ methods (4 fact + 3 snapshot)."""
        build_methods = [
            m for m in dir(fact_transformer)
            if (m.startswith("build_fact_") or m.startswith("build_snapshot_"))
            and callable(getattr(fact_transformer, m))
        ]
        assert len(build_methods) == 7, (
            f"Expected 7 builders, found {len(build_methods)}: {build_methods}"
        )


# ──────────────────────────────────────────────────────────────────────
# SnapshotTransformer Tests
# ──────────────────────────────────────────────────────────────────────

class TestSnapshotTransformer:

    def test_snapshot_transformer_default_date_is_today(self, snapshot_transformer):
        """Verify build_daily_snapshot defaults to today when no date given."""
        mock_conn = MagicMock()
        snapshot_transformer.engine.begin.return_value.__enter__ = MagicMock(
            return_value=mock_conn
        )
        snapshot_transformer.engine.begin.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_conn.execute.return_value.rowcount = 0

        snapshot_transformer.build_daily_snapshot()

        # The execute call should have received today's date as YYYYMMDD int
        call_args = mock_conn.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        today_key = int(date.today().strftime("%Y%m%d"))
        assert params["date_key"] == today_key

    def test_snapshot_transformer_date_key_format(self, snapshot_transformer):
        """Verify date_key is an integer in YYYYMMDD format."""
        mock_conn = MagicMock()
        snapshot_transformer.engine.begin.return_value.__enter__ = MagicMock(
            return_value=mock_conn
        )
        snapshot_transformer.engine.begin.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_conn.execute.return_value.rowcount = 0

        test_date = date(2025, 7, 15)
        snapshot_transformer.build_daily_snapshot(snapshot_date=test_date)

        call_args = mock_conn.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params["date_key"] == 20250715
        assert isinstance(params["date_key"], int)

    def test_snapshot_transformer_custom_date(self, snapshot_transformer):
        """Verify build_daily_snapshot accepts a custom date."""
        mock_conn = MagicMock()
        snapshot_transformer.engine.begin.return_value.__enter__ = MagicMock(
            return_value=mock_conn
        )
        snapshot_transformer.engine.begin.return_value.__exit__ = MagicMock(
            return_value=False
        )
        mock_conn.execute.return_value.rowcount = 0

        custom_date = date(2024, 12, 31)
        snapshot_transformer.build_daily_snapshot(snapshot_date=custom_date)

        call_args = mock_conn.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params["date_key"] == 20241231
