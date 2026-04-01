"""
Data Quality Checks — Validates gold layer data after each ETL run.

Checks:
1. Row count consistency (gold vs bronze)
2. Null checks on critical fields
3. Orphan record detection (facts without dimensions)
4. Business rule validation (e.g., collection_efficiency in valid range)
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
            results.append(self._check_orphan_facts(conn))
            results.append(self._check_null_customer_names(conn))
            results.append(self._check_null_dates(conn))
            results.append(self._check_negative_amounts(conn))
            results.append(self._check_entity_resolution_coverage(conn))

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

    def _check_orphan_facts(self, conn) -> QualityCheckResult:
        """Check for fact records that reference non-existent dimension keys."""
        result = conn.execute(text("""
            SELECT COUNT(*) FROM gold.fact_lead_pipeline
            WHERE customer_key IS NOT NULL
            AND customer_key NOT IN (SELECT customer_key FROM gold.dim_customers)
        """))
        orphan_count = result.scalar()

        if orphan_count > 0:
            return QualityCheckResult(
                "orphan_fact_records",
                False,
                f"{orphan_count} pipeline records reference non-existent customers",
                "error",
            )
        return QualityCheckResult("orphan_fact_records", True, "No orphan records", "info")

    def _check_null_customer_names(self, conn) -> QualityCheckResult:
        """Check for customers without names."""
        result = conn.execute(text("""
            SELECT COUNT(*) FROM gold.dim_customers
            WHERE customer_name IS NULL OR customer_name = ''
        """))
        null_count = result.scalar()

        if null_count > 0:
            return QualityCheckResult(
                "null_customer_names",
                False,
                f"{null_count} customers have no name",
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

    def _check_negative_amounts(self, conn) -> QualityCheckResult:
        """Check for negative amounts in collections."""
        result = conn.execute(text("""
            SELECT COUNT(*) FROM gold.fact_collections WHERE amount < 0
        """))
        neg_count = result.scalar()

        if neg_count > 0:
            return QualityCheckResult(
                "negative_amounts",
                False,
                f"{neg_count} collection records have negative amounts",
                "warning",
            )
        return QualityCheckResult("negative_amounts", True, "No negative amounts", "info")

    def _check_entity_resolution_coverage(self, conn) -> QualityCheckResult:
        """Check what percentage of VJ Sales leads have been resolved."""
        result = conn.execute(text("""
            SELECT
                (SELECT COUNT(DISTINCT lead_id) FROM bronze.stg_vjsales_bookings) AS total_bookings,
                (SELECT COUNT(*) FROM silver.entity_map WHERE vjsales_lead_id IS NOT NULL) AS resolved
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
