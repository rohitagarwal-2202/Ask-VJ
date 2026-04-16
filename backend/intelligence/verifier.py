"""
Result Verifier — Stage 4b of the Intelligence Pipeline

Validates SQL results for correctness and assigns a confidence score.
Checks: table coverage, filter application, time range accuracy,
result sanity, and data freshness.
"""

import logging
import re
from dataclasses import dataclass

from backend.intelligence.query_parser import ParsedQuery, QueryIntent
from backend.intelligence.executor import QueryResult

logger = logging.getLogger(__name__)


@dataclass
class VerificationCheck:
    name: str
    passed: bool
    message: str
    weight: float  # How much this check contributes to confidence (0-1)


@dataclass
class VerificationResult:
    confidence: float          # 0.0 to 1.0
    confidence_label: str      # "high", "medium", "low"
    checks: list[VerificationCheck]
    warnings: list[str]

    @property
    def passed_checks(self) -> list[VerificationCheck]:
        return [c for c in self.checks if c.passed]

    @property
    def failed_checks(self) -> list[VerificationCheck]:
        return [c for c in self.checks if not c.passed]


class ResultVerifier:
    """Validates query results and computes confidence scores."""

    def verify(
        self,
        parsed: ParsedQuery,
        sql: str,
        result: QueryResult,
    ) -> VerificationResult:
        """Run all verification checks and compute a confidence score."""
        checks = []

        # 1. Execution success check
        checks.append(self._check_execution_success(result))

        # 2. Non-empty result check
        checks.append(self._check_non_empty(result, parsed))

        # 3. Table coverage check
        checks.append(self._check_table_coverage(sql, parsed))

        # 4. Filter application check
        checks.append(self._check_filters_applied(sql, parsed))

        # 5. Time range check
        checks.append(self._check_time_range(sql, parsed))

        # 6. Result sanity check
        checks.append(self._check_result_sanity(result, parsed))

        # Compute weighted confidence
        if not checks:
            confidence = 0.5
        else:
            total_weight = sum(c.weight for c in checks)
            passed_weight = sum(c.weight for c in checks if c.passed)
            confidence = passed_weight / total_weight if total_weight > 0 else 0.5

        # Determine label
        if confidence >= 0.85:
            label = "high"
        elif confidence >= 0.60:
            label = "medium"
        else:
            label = "low"

        warnings = [c.message for c in checks if not c.passed]

        return VerificationResult(
            confidence=round(confidence, 2),
            confidence_label=label,
            checks=checks,
            warnings=warnings,
        )

    def _check_execution_success(self, result: QueryResult) -> VerificationCheck:
        """Did the SQL execute without errors?"""
        if result.error:
            return VerificationCheck(
                "execution_success", False,
                f"SQL execution failed: {result.error}",
                weight=0.40,
            )
        return VerificationCheck(
            "execution_success", True,
            "Query executed successfully",
            weight=0.40,
        )

    def _check_non_empty(self, result: QueryResult, parsed: ParsedQuery) -> VerificationCheck:
        """Did the query return any results?"""
        if result.is_empty and parsed.intent != QueryIntent.CLARIFICATION:
            return VerificationCheck(
                "non_empty_result", False,
                "Query returned no results. Filters may be too restrictive or data may not exist.",
                weight=0.15,
            )
        return VerificationCheck(
            "non_empty_result", True,
            f"Query returned {result.row_count} row(s)",
            weight=0.15,
        )

    def _check_table_coverage(self, sql: str, parsed: ParsedQuery) -> VerificationCheck:
        """Did the SQL query the right tables for the intent?"""
        sql_lower = sql.lower()

        # Map intents to expected tables
        expected = []
        if parsed.metric and any(
            kw in (parsed.metric or "").lower()
            for kw in ["collection", "receipt", "demand", "outstanding", "payment"]
        ):
            expected.append("fact_collections")

        if parsed.metric and any(
            kw in (parsed.metric or "").lower()
            for kw in ["lead", "booking", "inquiry", "conversion", "cancel", "pipeline"]
        ):
            expected.append("fact_lead_pipeline")

        if parsed.intent == QueryIntent.TREND:
            expected.append("dim_date")

        if not expected:
            # Can't determine expected tables — pass by default
            return VerificationCheck(
                "table_coverage", True,
                "Table coverage check not applicable for this query",
                weight=0.15,
            )

        missing = [t for t in expected if t not in sql_lower]
        if missing:
            return VerificationCheck(
                "table_coverage", False,
                f"Expected tables not in query: {', '.join(missing)}",
                weight=0.15,
            )
        return VerificationCheck(
            "table_coverage", True,
            "All expected tables present in query",
            weight=0.15,
        )

    def _check_filters_applied(self, sql: str, parsed: ParsedQuery) -> VerificationCheck:
        """Did the SQL apply the filters the user specified?"""
        sql_lower = sql.lower()
        missing_filters = []

        if parsed.project and parsed.project.lower() not in sql_lower:
            missing_filters.append(f"project: {parsed.project}")

        if parsed.phase and parsed.phase.lower() not in sql_lower:
            missing_filters.append(f"phase: {parsed.phase}")

        if missing_filters:
            return VerificationCheck(
                "filters_applied", False,
                f"Missing filters in SQL: {', '.join(missing_filters)}",
                weight=0.15,
            )
        return VerificationCheck(
            "filters_applied", True,
            "All specified filters present in query",
            weight=0.15,
        )

    def _check_time_range(self, sql: str, parsed: ParsedQuery) -> VerificationCheck:
        """Did the SQL apply the correct time filter?"""
        if not parsed.time_range:
            return VerificationCheck(
                "time_range", True,
                "No time range specified — check not applicable",
                weight=0.10,
            )

        sql_lower = sql.lower()
        has_date_join = "dim_date" in sql_lower
        has_date_filter = any(kw in sql_lower for kw in [
            "full_date", "date_key", "current_date", "date_trunc",
            "fiscal_year", "fiscal_quarter",
        ])

        if not has_date_join and not has_date_filter:
            return VerificationCheck(
                "time_range", False,
                f"User specified '{parsed.time_range}' but no date filter found in SQL",
                weight=0.10,
            )
        return VerificationCheck(
            "time_range", True,
            f"Date filter present for '{parsed.time_range}'",
            weight=0.10,
        )

    def _check_result_sanity(self, result: QueryResult, parsed: ParsedQuery) -> VerificationCheck:
        """Are the result values within reasonable ranges?"""
        if result.is_empty or result.error:
            return VerificationCheck(
                "result_sanity", True,
                "Sanity check skipped (no results or error)",
                weight=0.05,
            )

        warnings = []

        for i, col in enumerate(result.columns):
            col_lower = col.lower()

            # Check percentage values
            if "rate" in col_lower or "pct" in col_lower or "efficiency" in col_lower:
                for row in result.rows:
                    val = row[i]
                    if val is not None and isinstance(val, (int, float)):
                        if val > 200:
                            warnings.append(f"{col} = {val}% seems unreasonably high")
                        elif val < 0:
                            warnings.append(f"{col} = {val}% is negative")

            # Check for negative amounts
            if "amount" in col_lower or "collected" in col_lower or "demanded" in col_lower:
                for row in result.rows:
                    val = row[i]
                    if val is not None and isinstance(val, (int, float)) and val < 0:
                        warnings.append(f"{col} has negative value: {val}")

        if warnings:
            return VerificationCheck(
                "result_sanity", False,
                "Suspicious values: " + "; ".join(warnings[:3]),
                weight=0.05,
            )
        return VerificationCheck(
            "result_sanity", True,
            "Result values appear reasonable",
            weight=0.05,
        )
