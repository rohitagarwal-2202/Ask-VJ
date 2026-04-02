"""
Data Quality Checks — Validates gold layer data after each ETL run.

Checks:
1. Orphan record detection (facts without dimensions)
2. Null checks on critical fields
3. Negative/invalid amount detection
4. Entity resolution coverage
5. Booking data completeness
"""

import logging
from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


@dataclass
class QualityCheckResult:
    check_name: str
    passed: bool
    message: str
    severity: str  # "error", "warning", "info"


class QualityChecker:
    """Runs post-ETL data quality validations on the gold layer."""

    def __init__(self, warehouse_connection_string: str):
        self.engine: Engine = create_engine(warehouse_connection_string)

    def run_all_checks(self) -> list[QualityCheckResult]:
        """Run all quality checks and return results."""
        results = []

        with self.engine.connect() as conn:
            results.append(self._check_orphan_pipeline_facts(conn))
            results.append(self._check_orphan_booking_facts(conn))
            results.append(self._check_null_customer_names(conn))
            results.append(self._check_null_dates(conn))
            results.append(self._check_negative_receipt_amounts(conn))
            results.append(self._check_negative_outstanding(conn))
            results.append(self._check_entity_resolution_coverage(conn))
            results.append(self._check_booking_completeness(conn))

        # Log summary
        errors = [r for r in results if not r.passed and r.severity == "error"]
        warnings = [r for r in results if not r.passed and r.severity == "warning"]
        passed = [r for r in results if r.passed]

        logger.info(
            "Quality checks: %d passed, %d warnings, %d errors",
            len(passed), len(warnings), len(errors),
        )
        for error in errors:
            logger.error("QUALITY ERROR: %s — %s", error.check_name, error.message)
        for warning in warnings:
            logger.warning("QUALITY WARNING: %s — %s", warning.check_name, warning.message)

        return results

    def _check_orphan_pipeline_facts(self, conn) -> QualityCheckResult:
        """Check for pipeline records referencing non-existent customers."""
        result = conn.execute(text("""
            SELECT COUNT(*) FROM gold.fact_lead_pipeline
            WHERE customer_key IS NOT NULL
            AND customer_key NOT IN (SELECT customer_key FROM gold.dim_customers)
        """))
        orphan_count = result.scalar()

        if orphan_count > 0:
            return QualityCheckResult(
                "orphan_pipeline_records",
                False,
                f"{orphan_count} pipeline records reference non-existent customers",
                "error",
            )
        return QualityCheckResult("orphan_pipeline_records", True, "No orphan pipeline records", "info")

    def _check_orphan_booking_facts(self, conn) -> QualityCheckResult:
        """Check for booking records referencing non-existent dimensions."""
        result = conn.execute(text("""
            SELECT
                SUM(CASE WHEN b.project_key IS NOT NULL
                    AND b.project_key NOT IN (SELECT project_key FROM gold.dim_projects)
                    THEN 1 ELSE 0 END) AS orphan_projects,
                SUM(CASE WHEN b.unit_key IS NOT NULL
                    AND b.unit_key NOT IN (SELECT unit_key FROM gold.dim_units)
                    THEN 1 ELSE 0 END) AS orphan_units
            FROM gold.fact_bookings b
        """))
        row = result.fetchone()
        orphan_projects = row[0] or 0
        orphan_units = row[1] or 0
        total_orphans = orphan_projects + orphan_units

        if total_orphans > 0:
            return QualityCheckResult(
                "orphan_booking_records",
                False,
                f"{orphan_projects} orphan project refs, {orphan_units} orphan unit refs in fact_bookings",
                "error",
            )
        return QualityCheckResult("orphan_booking_records", True, "No orphan booking records", "info")

    def _check_null_customer_names(self, conn) -> QualityCheckResult:
        """Check for customers without names."""
        result = conn.execute(text("""
            SELECT COUNT(*) FROM gold.dim_customers
            WHERE (customer_name IS NULL OR customer_name = '')
              AND (full_name IS NULL OR full_name = '')
        """))
        null_count = result.scalar()

        if null_count > 0:
            return QualityCheckResult(
                "null_customer_names",
                False,
                f"{null_count} customers have no name (neither customer_name nor full_name)",
                "warning",
            )
        return QualityCheckResult("null_customer_names", True, "All customers have names", "info")

    def _check_null_dates(self, conn) -> QualityCheckResult:
        """Check for pipeline events without valid date keys."""
        result = conn.execute(text("""
            SELECT COUNT(*) FROM gold.fact_lead_pipeline
            WHERE event_date_key IS NULL
            OR event_date_key NOT IN (SELECT date_key FROM gold.dim_date)
        """))
        null_count = result.scalar()

        if null_count > 0:
            return QualityCheckResult(
                "null_event_dates",
                False,
                f"{null_count} pipeline events have invalid date keys",
                "error",
            )
        return QualityCheckResult("null_event_dates", True, "All events have valid dates", "info")

    def _check_negative_receipt_amounts(self, conn) -> QualityCheckResult:
        """Check for negative amounts in receipts."""
        result = conn.execute(text("""
            SELECT COUNT(*) FROM gold.fact_receipts WHERE amount < 0
        """))
        neg_count = result.scalar()

        if neg_count > 0:
            return QualityCheckResult(
                "negative_receipt_amounts",
                False,
                f"{neg_count} receipt records have negative amounts",
                "warning",
            )
        return QualityCheckResult("negative_receipt_amounts", True, "No negative receipt amounts", "info")

    def _check_negative_outstanding(self, conn) -> QualityCheckResult:
        """Check for negative due amounts in outstanding (should not happen)."""
        result = conn.execute(text("""
            SELECT COUNT(*) FROM gold.fact_outstanding WHERE due_amount < 0
        """))
        neg_count = result.scalar()

        if neg_count > 0:
            return QualityCheckResult(
                "negative_outstanding",
                False,
                f"{neg_count} outstanding records have negative due amounts",
                "warning",
            )
        return QualityCheckResult("negative_outstanding", True, "No negative outstanding amounts", "info")

    def _check_entity_resolution_coverage(self, conn) -> QualityCheckResult:
        """Check what percentage of Farvision bookings have been resolved via entity_map."""
        result = conn.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM gold.fact_bookings) AS total_bookings,
                (SELECT COUNT(*) FROM silver.entity_map
                 WHERE farvision_booking_id IS NOT NULL) AS resolved
        """))
        row = result.fetchone()
        total = row[0] or 0
        resolved = row[1] or 0

        if total == 0:
            return QualityCheckResult(
                "entity_resolution_coverage", True, "No bookings to resolve", "info"
            )

        coverage = (resolved / total) * 100
        if coverage < 70:
            return QualityCheckResult(
                "entity_resolution_coverage",
                False,
                f"Only {coverage:.1f}% of bookings resolved ({resolved}/{total})",
                "warning",
            )
        return QualityCheckResult(
            "entity_resolution_coverage",
            True,
            f"{coverage:.1f}% of bookings resolved ({resolved}/{total})",
            "info",
        )

    def _check_booking_completeness(self, conn) -> QualityCheckResult:
        """Check that bookings have essential fields populated."""
        result = conn.execute(text("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN booking_date IS NULL THEN 1 ELSE 0 END) AS no_date,
                SUM(CASE WHEN net_basic_price IS NULL OR net_basic_price = 0 THEN 1 ELSE 0 END) AS no_price,
                SUM(CASE WHEN project_key IS NULL THEN 1 ELSE 0 END) AS no_project
            FROM gold.fact_bookings
            WHERE is_cancelled = false
        """))
        row = result.fetchone()
        total = row[0] or 0
        no_date = row[1] or 0
        no_price = row[2] or 0
        no_project = row[3] or 0

        issues = []
        if no_date > 0:
            issues.append(f"{no_date} missing booking_date")
        if no_price > 0:
            issues.append(f"{no_price} missing net_basic_price")
        if no_project > 0:
            issues.append(f"{no_project} missing project_key")

        if issues:
            return QualityCheckResult(
                "booking_completeness",
                False,
                f"Active bookings with missing fields: {', '.join(issues)} (of {total} total)",
                "warning",
            )
        return QualityCheckResult(
            "booking_completeness",
            True,
            f"All {total} active bookings have essential fields",
            "info",
        )
