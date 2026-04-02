"""
SQL Generator — Stage 3 of the Intelligence Pipeline

Generates safe, schema-aware PostgreSQL queries from natural language
using a local SQL-specialized LLM (SQLCoder) with retrieved context.
"""

import logging
import re

import httpx

from backend.config import LLMConfig
from backend.intelligence.query_parser import ParsedQuery, QueryIntent
from backend.intelligence.schema_retriever import TableSchema

logger = logging.getLogger(__name__)


SQL_GENERATION_PROMPT = """You are a PostgreSQL SQL expert for a real estate company (Vilas Javdekar).
Generate a single SQL query to answer the user's question.

=== DATABASE SCHEMA (relevant tables only) ===
{schema_context}

{business_rules}

=== CONSTRAINTS ===
- Use ONLY the tables and columns listed above
- Always use explicit JOINs (never implicit/comma joins)
- Always include LIMIT 1000 unless the user specifically asks for all records
- Use gold schema prefix: gold.table_name
- For date filtering, JOIN with gold.dim_date and use the full_date column
- For "this month": WHERE d.full_date >= DATE_TRUNC('month', CURRENT_DATE)
- For "last month": WHERE d.full_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month') AND d.full_date < DATE_TRUNC('month', CURRENT_DATE)
- For "this quarter": WHERE d.fiscal_quarter = (current fiscal quarter) AND d.fiscal_year = (current FY)
- For fiscal year: VJ uses Indian FY (April-March). FY2026 = Apr 2025 - Mar 2026. Use d.fiscal_year column.
- For percentages, ROUND to 2 decimal places
- Use NULLIF to prevent division by zero
- For INR amounts, do NOT format — return raw numbers
- NEVER use DELETE, UPDATE, INSERT, DROP, ALTER, CREATE, TRUNCATE, GRANT, or EXECUTE
- NEVER use subqueries in WHERE when a JOIN works

=== EXAMPLES ===
Q: "How many bookings this month?"
SQL:
SELECT COUNT(*) AS total_bookings
FROM gold.fact_lead_pipeline f
JOIN gold.dim_date d ON f.event_date_key = d.date_key
WHERE f.pipeline_stage = 'booking'
  AND d.full_date >= DATE_TRUNC('month', CURRENT_DATE)
LIMIT 1000;

Q: "Collection efficiency for Phase 2?"
SQL:
SELECT
  ROUND(
    SUM(CASE WHEN c.transaction_type = 'receipt' THEN c.amount ELSE 0 END) * 100.0 /
    NULLIF(SUM(CASE WHEN c.transaction_type = 'demand' THEN c.amount ELSE 0 END), 0),
    2
  ) AS collection_efficiency_pct,
  SUM(CASE WHEN c.transaction_type = 'receipt' THEN c.amount ELSE 0 END) AS total_collected,
  SUM(CASE WHEN c.transaction_type = 'demand' THEN c.amount ELSE 0 END) AS total_demanded
FROM gold.fact_collections c
JOIN gold.dim_projects p ON c.project_key = p.project_key
WHERE p.phase_name ILIKE '%Phase 2%'
LIMIT 1000;

Q: "Which sales person has the most bookings this quarter?"
SQL:
SELECT sp.name AS sales_person, COUNT(*) AS booking_count
FROM gold.fact_lead_pipeline f
JOIN gold.dim_sales_persons sp ON f.sales_person_key = sp.sales_person_key
JOIN gold.dim_date d ON f.event_date_key = d.date_key
WHERE f.pipeline_stage = 'booking'
  AND d.fiscal_quarter = (
    SELECT fiscal_quarter FROM gold.dim_date WHERE full_date = CURRENT_DATE
  )
  AND d.fiscal_year = (
    SELECT fiscal_year FROM gold.dim_date WHERE full_date = CURRENT_DATE
  )
GROUP BY sp.name
ORDER BY booking_count DESC
LIMIT 1000;

Q: "Show cancelled bookings with reasons this month"
SQL:
SELECT
  c.customer_name,
  p.project_name,
  u.unit_no,
  d.full_date AS cancellation_date,
  f.pipeline_stage
FROM gold.fact_lead_pipeline f
JOIN gold.dim_customers c ON f.customer_key = c.customer_key
JOIN gold.dim_projects p ON f.project_key = p.project_key
LEFT JOIN gold.dim_units u ON f.unit_key = u.unit_key
JOIN gold.dim_date d ON f.event_date_key = d.date_key
WHERE f.pipeline_stage = 'cancelled'
  AND d.full_date >= DATE_TRUNC('month', CURRENT_DATE)
ORDER BY d.full_date DESC
LIMIT 1000;

=== USER QUESTION ===
{question}

=== PARSED INTENT ===
{intent_json}

Generate ONLY the SQL query. No explanation, no markdown fencing."""


SELF_CORRECT_PROMPT = """The previous SQL query had issues. Fix them.

Previous SQL:
{previous_sql}

Error / Issue:
{error}

Schema context:
{schema_context}

Generate ONLY the corrected SQL query. No explanation."""


class SQLGenerator:
    """Generates PostgreSQL queries from parsed questions using a local LLM."""

    # Statements that must never appear in generated SQL
    BLOCKED_KEYWORDS = frozenset([
        "DELETE", "UPDATE", "INSERT", "DROP", "ALTER", "CREATE",
        "TRUNCATE", "GRANT", "REVOKE", "EXEC", "EXECUTE",
    ])

    MAX_QUERY_LENGTH = 5000
    MAX_RETRIES = 1

    def __init__(self, llm_config: LLMConfig):
        self.config = llm_config

    async def generate(
        self,
        question: str,
        parsed: ParsedQuery,
        schema_context: str,
        business_rules: str = "",
    ) -> str:
        """
        Generate a SQL query for the given question.
        Returns validated SQL string.

        Raises ValueError if generated SQL is unsafe or invalid.
        """
        intent_json = {
            "intent": parsed.intent.value,
            "metric": parsed.metric,
            "project": parsed.project,
            "phase": parsed.phase,
            "time_range": parsed.time_range,
            "group_by": parsed.group_by,
        }

        prompt = SQL_GENERATION_PROMPT.format(
            schema_context=schema_context,
            business_rules=business_rules,
            question=question,
            intent_json=str(intent_json),
        )

        raw_sql = await self._call_llm(prompt)
        sql = self._clean_sql(raw_sql)

        is_safe, message = self._validate_safety(sql)
        if not is_safe:
            raise ValueError(f"Unsafe SQL generated: {message}")

        return sql

    async def self_correct(
        self,
        previous_sql: str,
        error: str,
        schema_context: str,
    ) -> str:
        """
        Attempt to fix a SQL query that failed execution.
        Returns corrected SQL or raises ValueError.
        """
        prompt = SELF_CORRECT_PROMPT.format(
            previous_sql=previous_sql,
            error=error,
            schema_context=schema_context,
        )

        raw_sql = await self._call_llm(prompt)
        sql = self._clean_sql(raw_sql)

        is_safe, message = self._validate_safety(sql)
        if not is_safe:
            raise ValueError(f"Unsafe corrected SQL: {message}")

        return sql

    async def _call_llm(self, prompt: str) -> str:
        """Call the local SQL LLM via Ollama-compatible API."""
        async with httpx.AsyncClient(timeout=self.config.request_timeout) as client:
            response = await client.post(
                f"{self.config.sql_endpoint}/api/chat",
                json={
                    "model": self.config.sql_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {
                        "temperature": 0.0,  # Deterministic for SQL
                        "num_predict": self.config.max_tokens,
                    },
                },
            )
            response.raise_for_status()
            return response.json()["message"]["content"]

    def _clean_sql(self, raw: str) -> str:
        """Strip markdown fences and whitespace from LLM output."""
        sql = raw.strip()

        # Remove markdown code fences
        if sql.startswith("```"):
            sql = sql.split("\n", 1)[1] if "\n" in sql else sql[3:]
        if sql.endswith("```"):
            sql = sql.rsplit("```", 1)[0]

        # Remove sql language tag
        if sql.lower().startswith("sql\n"):
            sql = sql[4:]

        sql = sql.strip()

        # Ensure it ends with semicolon
        if not sql.endswith(";"):
            sql += ";"

        return sql

    def _validate_safety(self, sql: str) -> tuple[bool, str]:
        """Validate that generated SQL is safe to execute."""
        sql_upper = sql.upper()

        # 1. Block dangerous statements
        tokens = set(re.findall(r'\b[A-Z]+\b', sql_upper))
        blocked = tokens & self.BLOCKED_KEYWORDS
        if blocked:
            return False, f"Blocked keywords found: {blocked}"

        # 2. Must start with SELECT or WITH (CTEs)
        first_keyword = sql_upper.lstrip().split()[0] if sql_upper.strip() else ""
        if first_keyword not in ("SELECT", "WITH"):
            return False, f"Query must start with SELECT or WITH, got: {first_keyword}"

        # 3. Must reference gold schema
        if "gold." not in sql.lower():
            return False, "Query must use gold schema tables"

        # 4. Length check
        if len(sql) > self.MAX_QUERY_LENGTH:
            return False, f"Query too long: {len(sql)} chars (max {self.MAX_QUERY_LENGTH})"

        # 5. Ensure LIMIT exists
        if "LIMIT" not in sql_upper:
            # Auto-append LIMIT instead of rejecting
            sql = sql.rstrip(";") + "\nLIMIT 1000;"

        return True, sql
