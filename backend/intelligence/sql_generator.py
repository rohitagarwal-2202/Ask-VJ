"""
SQL Generator — Stage 3 of the Intelligence Pipeline

Generates safe, schema-aware PostgreSQL queries from natural language
using a local SQL-specialized LLM (SQLCoder) with retrieved context.

Few-shot examples adapted from verified erp-chatbot queries running
against the real Farvision / VJ Sales / VJOP databases.
"""

import logging
import re

import httpx

from backend.config import LLMConfig
from backend.intelligence.query_parser import ParsedQuery, QueryIntent
from backend.intelligence.schema_retriever import TableSchema

logger = logging.getLogger(__name__)


SQL_GENERATION_PROMPT = """You are a PostgreSQL SQL expert for Vilas Javdekar (VJ), a real estate developer.
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
- For "this quarter": Filter on d.fiscal_quarter and d.fiscal_year matching CURRENT_DATE
- For fiscal year: VJ uses Indian FY (April-March). FY2026 = Apr 2025 - Mar 2026. Use d.fiscal_year column.
- For percentages, ROUND to 2 decimal places
- Use NULLIF to prevent division by zero
- For INR amounts, do NOT format — return raw numbers
- NEVER use DELETE, UPDATE, INSERT, DROP, ALTER, CREATE, TRUNCATE, GRANT, or EXECUTE
- NEVER use subqueries in WHERE when a JOIN works
- For "3 BHK" queries: use t.typology_id = 6 (base variant only, NOT 23/35 which are XL/XR)
- For active bookings: always filter is_cancelled = false
- For unit status: 1 = sold, 2 = available, 3 = blocked

=== EXAMPLES ===
Q: "How many bookings this month?"
SQL:
SELECT COUNT(*) AS total_bookings
FROM gold.fact_bookings b
JOIN gold.dim_date d ON d.date_key = CAST(TO_CHAR(b.booking_date, 'YYYYMMDD') AS INT)
WHERE b.is_cancelled = false
  AND b.booking_date >= DATE_TRUNC('month', CURRENT_DATE)
LIMIT 1000;

Q: "Total booking value this fiscal year"
SQL:
SELECT
  SUM(b.net_basic_price) AS total_booking_value,
  COUNT(*) AS total_bookings
FROM gold.fact_bookings b
JOIN gold.dim_date d ON d.date_key = CAST(TO_CHAR(b.booking_date, 'YYYYMMDD') AS INT)
WHERE b.is_cancelled = false
  AND d.fiscal_year = (SELECT fiscal_year FROM gold.dim_date WHERE full_date = CURRENT_DATE)
LIMIT 1000;

Q: "Project wise booking summary this FY"
SQL:
SELECT
  p.project_name,
  COUNT(*) AS total_bookings,
  SUM(b.net_basic_price) AS total_value,
  ROUND(AVG(b.net_basic_price), 2) AS avg_booking_value
FROM gold.fact_bookings b
JOIN gold.dim_projects p ON b.project_key = p.project_key
JOIN gold.dim_date d ON d.date_key = CAST(TO_CHAR(b.booking_date, 'YYYYMMDD') AS INT)
WHERE b.is_cancelled = false
  AND d.fiscal_year = (SELECT fiscal_year FROM gold.dim_date WHERE full_date = CURRENT_DATE)
GROUP BY p.project_name
ORDER BY total_bookings DESC
LIMIT 1000;

Q: "Show 3 BHK available inventory with rates"
SQL:
SELECT
  p.project_name,
  u.wing,
  u.unit_no,
  u.floor,
  u.carpet_area,
  i.saleable_area,
  i.bsp AS rate_per_sqft,
  i.total_cost
FROM gold.fact_inventory i
JOIN gold.dim_units u ON i.unit_key = u.unit_key
JOIN gold.dim_projects p ON i.project_key = p.project_key
JOIN gold.dim_typologies t ON i.typology_key = t.typology_key
WHERE i.inventory_status = 'Available'
  AND t.typology_id = 6
ORDER BY p.project_name, u.wing, u.floor
LIMIT 1000;

Q: "Collection efficiency for this month"
SQL:
SELECT
  p.project_name,
  SUM(r.amount) AS total_collected,
  SUM(inv.total_amount) AS total_demanded,
  ROUND(
    SUM(r.amount) * 100.0 / NULLIF(SUM(inv.total_amount), 0),
    2
  ) AS collection_efficiency_pct
FROM gold.fact_receipts r
JOIN gold.dim_projects p ON r.project_key = p.project_key
JOIN gold.dim_date d ON r.date_key = d.date_key
LEFT JOIN gold.fact_invoices inv ON r.booking_key = inv.booking_key
WHERE d.full_date >= DATE_TRUNC('month', CURRENT_DATE)
GROUP BY p.project_name
ORDER BY collection_efficiency_pct DESC
LIMIT 1000;

Q: "Outstanding aging analysis by project"
SQL:
SELECT
  p.project_name,
  COUNT(*) AS total_customers,
  SUM(o.bill_amount) AS total_billed,
  SUM(o.paid_amount) AS total_paid,
  SUM(o.due_amount) AS total_due,
  SUM(o.day_amt_15) AS overdue_0_15,
  SUM(o.day_amt_30) AS overdue_16_30,
  SUM(o.day_amt_60) AS overdue_31_60,
  SUM(o.day_amt_90) AS overdue_61_90,
  SUM(o.day_amt_120) AS overdue_91_120,
  SUM(o.day_amt_180) AS overdue_121_180,
  SUM(o.day_amt_more_180) AS overdue_above_180
FROM gold.fact_outstanding o
JOIN gold.dim_projects p ON o.project_key = p.project_key
GROUP BY p.project_name
ORDER BY total_due DESC
LIMIT 1000;

Q: "Customers with outstanding more than 90 days"
SQL:
SELECT
  o.customer_name,
  p.project_name,
  o.unit_no,
  o.bill_amount,
  o.paid_amount,
  o.due_amount,
  o.overdue_days,
  o.day_amt_90 + o.day_amt_120 + o.day_amt_180 + o.day_amt_more_180 AS overdue_above_90
FROM gold.fact_outstanding o
JOIN gold.dim_projects p ON o.project_key = p.project_key
WHERE (o.day_amt_90 + o.day_amt_120 + o.day_amt_180 + o.day_amt_more_180) > 0
ORDER BY overdue_above_90 DESC
LIMIT 1000;

Q: "Payment mode wise collection this month"
SQL:
SELECT
  r.payment_mode,
  COUNT(*) AS receipt_count,
  SUM(r.amount) AS total_amount
FROM gold.fact_receipts r
JOIN gold.dim_date d ON r.date_key = d.date_key
WHERE d.full_date >= DATE_TRUNC('month', CURRENT_DATE)
GROUP BY r.payment_mode
ORDER BY total_amount DESC
LIMIT 1000;

Q: "Cancellation rate by project this FY"
SQL:
SELECT
  p.project_name,
  COUNT(*) AS total_bookings,
  SUM(CASE WHEN b.is_cancelled THEN 1 ELSE 0 END) AS cancelled,
  ROUND(
    SUM(CASE WHEN b.is_cancelled THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0),
    2
  ) AS cancellation_rate_pct
FROM gold.fact_bookings b
JOIN gold.dim_projects p ON b.project_key = p.project_key
JOIN gold.dim_date d ON d.date_key = CAST(TO_CHAR(b.booking_date, 'YYYYMMDD') AS INT)
WHERE d.fiscal_year = (SELECT fiscal_year FROM gold.dim_date WHERE full_date = CURRENT_DATE)
GROUP BY p.project_name
ORDER BY cancellation_rate_pct DESC
LIMIT 1000;

Q: "Top 10 referrers by points earned"
SQL:
SELECT
  c.customer_name,
  c.mobile,
  p.project_name,
  COUNT(*) AS total_referrals,
  SUM(ref.points_earned) AS total_points_earned,
  SUM(ref.points_redeemed) AS total_points_redeemed
FROM gold.fact_referrals ref
JOIN gold.dim_customers c ON ref.referrer_customer_key = c.customer_key
LEFT JOIN gold.dim_projects p ON ref.project_key = p.project_key
GROUP BY c.customer_name, c.mobile, p.project_name
ORDER BY total_points_earned DESC
LIMIT 10;

Q: "Lead conversion rate this quarter"
SQL:
SELECT
  p.project_name,
  f.inquiry_to_visit_rate,
  f.visit_to_booking_rate,
  f.booking_to_agreement_rate,
  f.total_inquiries,
  f.total_site_visits,
  f.total_bookings,
  f.total_agreements
FROM gold.fact_daily_funnel_snapshot f
JOIN gold.dim_date d ON f.snapshot_date_key = d.date_key
JOIN gold.dim_projects p ON f.project_key = p.project_key
WHERE d.full_date = (SELECT MAX(full_date) FROM gold.dim_date WHERE full_date <= CURRENT_DATE)
ORDER BY p.project_name
LIMIT 1000;

Q: "Which sales person has the most bookings this quarter?"
SQL:
SELECT
  sp.name AS sales_person,
  COUNT(*) AS booking_count,
  SUM(b.net_basic_price) AS total_value
FROM gold.fact_bookings b
JOIN gold.dim_sales_persons sp ON b.sales_person_key = sp.sales_person_key
JOIN gold.dim_date d ON d.date_key = CAST(TO_CHAR(b.booking_date, 'YYYYMMDD') AS INT)
WHERE b.is_cancelled = false
  AND d.fiscal_quarter = (SELECT fiscal_quarter FROM gold.dim_date WHERE full_date = CURRENT_DATE)
  AND d.fiscal_year = (SELECT fiscal_year FROM gold.dim_date WHERE full_date = CURRENT_DATE)
GROUP BY sp.name
ORDER BY booking_count DESC
LIMIT 1000;

Q: "Agreements done but not yet registered"
SQL:
SELECT
  p.project_name,
  c.customer_name,
  u.unit_no,
  b.agreement_date,
  b.agreement_no,
  b.net_basic_price
FROM gold.fact_bookings b
JOIN gold.dim_projects p ON b.project_key = p.project_key
JOIN gold.dim_customers c ON b.customer_key = c.customer_key
JOIN gold.dim_units u ON b.unit_key = u.unit_key
WHERE b.agreement_date IS NOT NULL
  AND b.registration_date IS NULL
  AND b.is_cancelled = false
ORDER BY b.agreement_date
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
