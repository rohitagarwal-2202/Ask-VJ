"""
Tests for QualityChecker — validates data quality check logic with mocked DB.
"""

import pytest
from unittest.mock import patch, MagicMock
from dataclasses import fields

from backend.etl.validators.quality_checks import QualityChecker, QualityCheckResult


@pytest.fixture()
def checker():
    with patch("backend.etl.validators.quality_checks.create_engine", return_value=MagicMock()):
        return QualityChecker(warehouse_connection_string="postgresql://dummy")


# ──────────────────────────────────────────────────────────────────────
# Structural / meta tests
# ──────────────────────────────────────────────────────────────────────

def test_quality_checker_has_all_check_methods(checker):
    """Verify the checker exposes all expected private check methods."""
    expected_methods = [
        "_check_orphan_pipeline_facts",
        "_check_orphan_booking_facts",
        "_check_null_customer_names",
        "_check_null_dates",
        "_check_negative_receipt_amounts",
        "_check_negative_outstanding",
        "_check_entity_resolution_coverage",
        "_check_booking_completeness",
    ]
    for method_name in expected_methods:
        assert hasattr(checker, method_name), f"Missing method: {method_name}"
        assert callable(getattr(checker, method_name)), f"{method_name} is not callable"


def test_check_result_dataclass_fields():
    """Verify QualityCheckResult has the expected fields."""
    field_names = {f.name for f in fields(QualityCheckResult)}
    assert field_names == {"check_name", "passed", "message", "severity"}


# ──────────────────────────────────────────────────────────────────────
# Orphan pipeline checks
# ──────────────────────────────────────────────────────────────────────

def test_orphan_pipeline_check_passes_when_zero(checker):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.scalar.return_value = 0

    result = checker._check_orphan_pipeline_facts(mock_conn)

    assert result.passed is True
    assert result.check_name == "orphan_pipeline_records"
    assert result.severity == "info"


def test_orphan_pipeline_check_fails_when_nonzero(checker):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.scalar.return_value = 5

    result = checker._check_orphan_pipeline_facts(mock_conn)

    assert result.passed is False
    assert result.severity == "error"
    assert "5" in result.message


# ──────────────────────────────────────────────────────────────────────
# Null customer names
# ──────────────────────────────────────────────────────────────────────

def test_null_customer_names_passes(checker):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.scalar.return_value = 0

    result = checker._check_null_customer_names(mock_conn)

    assert result.passed is True
    assert result.severity == "info"


def test_null_customer_names_warns(checker):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.scalar.return_value = 10

    result = checker._check_null_customer_names(mock_conn)

    assert result.passed is False
    assert result.severity == "warning"
    assert "10" in result.message


# ──────────────────────────────────────────────────────────────────────
# Negative receipts
# ──────────────────────────────────────────────────────────────────────

def test_negative_receipts_passes(checker):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.scalar.return_value = 0

    result = checker._check_negative_receipt_amounts(mock_conn)

    assert result.passed is True
    assert result.severity == "info"


def test_negative_receipts_warns(checker):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.scalar.return_value = 3

    result = checker._check_negative_receipt_amounts(mock_conn)

    assert result.passed is False
    assert result.severity == "warning"
    assert "3" in result.message


# ──────────────────────────────────────────────────────────────────────
# Entity resolution coverage
# ──────────────────────────────────────────────────────────────────────

def test_entity_resolution_good_coverage(checker):
    mock_conn = MagicMock()
    # fetchone returns (total_bookings, resolved)
    mock_conn.execute.return_value.fetchone.return_value = (100, 90)

    result = checker._check_entity_resolution_coverage(mock_conn)

    assert result.passed is True
    assert "90.0%" in result.message


def test_entity_resolution_low_coverage(checker):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = (100, 50)

    result = checker._check_entity_resolution_coverage(mock_conn)

    assert result.passed is False
    assert result.severity == "warning"
    assert "50.0%" in result.message


# ──────────────────────────────────────────────────────────────────────
# Booking completeness
# ──────────────────────────────────────────────────────────────────────

def test_booking_completeness_passes(checker):
    mock_conn = MagicMock()
    # fetchone returns (total, no_date, no_price, no_project)
    mock_conn.execute.return_value.fetchone.return_value = (200, 0, 0, 0)

    result = checker._check_booking_completeness(mock_conn)

    assert result.passed is True
    assert result.severity == "info"


def test_booking_completeness_warns(checker):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = (200, 5, 3, 0)

    result = checker._check_booking_completeness(mock_conn)

    assert result.passed is False
    assert result.severity == "warning"
    assert "missing booking_date" in result.message
    assert "missing net_basic_price" in result.message


# ──────────────────────────────────────────────────────────────────────
# run_all_checks integration
# ──────────────────────────────────────────────────────────────────────

def test_run_all_checks_returns_list(checker):
    """Verify run_all_checks returns a list of QualityCheckResult items."""
    mock_conn = MagicMock()

    # For scalar-based checks, return 0 (passing)
    mock_conn.execute.return_value.scalar.return_value = 0
    # For fetchone-based checks, return tuples that satisfy all branches
    mock_conn.execute.return_value.fetchone.return_value = (100, 0, 0, 0)

    # Patch engine.connect() to yield our mock connection
    checker.engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    checker.engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    results = checker.run_all_checks()

    assert isinstance(results, list)
    assert len(results) >= 8, f"Expected at least 8 check results, got {len(results)}"
    for r in results:
        assert isinstance(r, QualityCheckResult)
