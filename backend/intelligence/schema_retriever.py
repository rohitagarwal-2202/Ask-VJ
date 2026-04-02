"""
Schema Retriever — Stage 2 of the Intelligence Pipeline

Embeds gold schema metadata into a vector database and retrieves
relevant tables/columns for a given user question.
"""

import json
import logging
from dataclasses import dataclass

import httpx

from backend.config import LLMConfig, VectorDBConfig

logger = logging.getLogger(__name__)


@dataclass
class TableSchema:
    """Metadata for a gold-layer table."""
    table_name: str
    description: str
    columns: list[dict]  # [{"name": ..., "type": ..., "description": ...}]
    joins: list[str]     # ["dim_customers ON customer_key", ...]
    sample_queries: list[str]


# Gold schema metadata — the "knowledge base" the LLM reasons over
GOLD_SCHEMA: list[TableSchema] = [
    TableSchema(
        table_name="gold.dim_date",
        description="Date dimension with calendar and Indian fiscal year support. "
                    "Join on date_key (YYYYMMDD integer format).",
        columns=[
            {"name": "date_key", "type": "INT", "description": "Primary key in YYYYMMDD format"},
            {"name": "full_date", "type": "DATE", "description": "Actual date value"},
            {"name": "month_name", "type": "VARCHAR", "description": "Full month name (January, February, ...)"},
            {"name": "quarter", "type": "VARCHAR", "description": "Calendar quarter (Q1-Q4)"},
            {"name": "fiscal_quarter", "type": "VARCHAR", "description": "Indian FY quarter: Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar"},
            {"name": "fiscal_year", "type": "INT", "description": "Indian fiscal year number (FY2026 = Apr 2025 - Mar 2026)"},
            {"name": "fiscal_year_label", "type": "VARCHAR", "description": "Label like 'FY2026'"},
            {"name": "is_weekend", "type": "BOOLEAN", "description": "True if Saturday or Sunday"},
        ],
        joins=[],
        sample_queries=["this month", "last quarter", "FY2026", "this fiscal year"],
    ),
    TableSchema(
        table_name="gold.dim_projects",
        description="VJ real estate projects. Each project can have multiple phases.",
        columns=[
            {"name": "project_key", "type": "INT", "description": "Primary key"},
            {"name": "project_name", "type": "VARCHAR", "description": "Canonical project name"},
            {"name": "phase_name", "type": "VARCHAR", "description": "Phase within the project"},
            {"name": "location", "type": "VARCHAR", "description": "Project location"},
            {"name": "rera_number", "type": "VARCHAR", "description": "RERA registration number"},
            {"name": "total_units", "type": "INT", "description": "Total units in project"},
            {"name": "status", "type": "VARCHAR", "description": "active, completed, or upcoming"},
        ],
        joins=[],
        sample_queries=["Project X", "Phase 2", "active projects"],
    ),
    TableSchema(
        table_name="gold.dim_units",
        description="Individual flats, apartments, shops, or offices within projects.",
        columns=[
            {"name": "unit_key", "type": "INT", "description": "Primary key"},
            {"name": "project_key", "type": "INT", "description": "FK to dim_projects"},
            {"name": "unit_no", "type": "VARCHAR", "description": "Unit number (e.g., A-501)"},
            {"name": "wing", "type": "VARCHAR", "description": "Building wing"},
            {"name": "floor", "type": "INT", "description": "Floor number"},
            {"name": "unit_type", "type": "VARCHAR", "description": "1BHK, 2BHK, 3BHK, shop, office"},
            {"name": "carpet_area_sqft", "type": "DECIMAL", "description": "Net usable area in sq ft"},
            {"name": "current_status", "type": "VARCHAR", "description": "available, booked, agreement, registered, cancelled"},
        ],
        joins=["gold.dim_projects ON project_key"],
        sample_queries=["2BHK units", "available flats", "units in wing A"],
    ),
    TableSchema(
        table_name="gold.dim_customers",
        description="Unified customer records linked across VJ Sales and Farvision via entity resolution.",
        columns=[
            {"name": "customer_key", "type": "INT", "description": "Primary key"},
            {"name": "customer_name", "type": "VARCHAR", "description": "Customer full name"},
            {"name": "phone", "type": "VARCHAR", "description": "Phone number"},
            {"name": "email", "type": "VARCHAR", "description": "Email address"},
            {"name": "first_inquiry_date", "type": "DATE", "description": "When the customer first inquired"},
            {"name": "lead_source", "type": "VARCHAR", "description": "How the customer found VJ"},
        ],
        joins=[],
        sample_queries=["customer details", "customer list"],
    ),
    TableSchema(
        table_name="gold.dim_sales_persons",
        description="Sales team members who handle leads and bookings.",
        columns=[
            {"name": "sales_person_key", "type": "INT", "description": "Primary key"},
            {"name": "name", "type": "VARCHAR", "description": "Sales person name"},
            {"name": "team", "type": "VARCHAR", "description": "Sales team name"},
            {"name": "is_active", "type": "BOOLEAN", "description": "Currently active"},
        ],
        joins=[],
        sample_queries=["sales person performance", "top performers"],
    ),
    TableSchema(
        table_name="gold.dim_lead_sources",
        description="Lead acquisition channels: walk-in, referral, digital (FB/Google), channel partners.",
        columns=[
            {"name": "source_key", "type": "INT", "description": "Primary key"},
            {"name": "source_name", "type": "VARCHAR", "description": "Specific source name"},
            {"name": "source_category", "type": "VARCHAR", "description": "organic, paid, referral, channel_partner"},
            {"name": "channel_partner_name", "type": "VARCHAR", "description": "CP name if applicable, else NULL"},
        ],
        joins=[],
        sample_queries=["lead sources", "channel partner performance", "digital leads"],
    ),
    TableSchema(
        table_name="gold.fact_lead_pipeline",
        description="Every stage transition in a lead's lifecycle. One row per stage change. "
                    "Stages: inquiry → site_visit → negotiation → booking → agreement → registered | cancelled.",
        columns=[
            {"name": "pipeline_event_id", "type": "INT", "description": "Primary key"},
            {"name": "customer_key", "type": "INT", "description": "FK to dim_customers"},
            {"name": "project_key", "type": "INT", "description": "FK to dim_projects"},
            {"name": "unit_key", "type": "INT", "description": "FK to dim_units (NULL until booking)"},
            {"name": "sales_person_key", "type": "INT", "description": "FK to dim_sales_persons"},
            {"name": "source_key", "type": "INT", "description": "FK to dim_lead_sources"},
            {"name": "event_date_key", "type": "INT", "description": "FK to dim_date"},
            {"name": "pipeline_stage", "type": "VARCHAR", "description": "inquiry, site_visit, negotiation, booking, agreement, registered, cancelled"},
            {"name": "previous_stage", "type": "VARCHAR", "description": "Stage before this transition"},
            {"name": "days_in_previous_stage", "type": "INT", "description": "Days spent in previous stage"},
            {"name": "agreement_value", "type": "DECIMAL", "description": "Total agreement value in INR (set at booking)"},
            {"name": "booking_amount", "type": "DECIMAL", "description": "Initial booking amount paid"},
            {"name": "event_timestamp", "type": "TIMESTAMP", "description": "When this stage change happened"},
        ],
        joins=[
            "gold.dim_customers ON customer_key",
            "gold.dim_projects ON project_key",
            "gold.dim_units ON unit_key",
            "gold.dim_sales_persons ON sales_person_key",
            "gold.dim_lead_sources ON source_key",
            "gold.dim_date ON event_date_key",
        ],
        sample_queries=[
            "How many bookings this month?",
            "Lead conversion rate for Project X",
            "Average time from inquiry to booking",
            "Which sales person has most bookings?",
            "Show cancelled bookings with reasons",
        ],
    ),
    TableSchema(
        table_name="gold.fact_collections",
        description="Financial transactions: demand letters raised and receipts collected. "
                    "Used for collection efficiency, outstanding amounts, and payment tracking.",
        columns=[
            {"name": "collection_id", "type": "INT", "description": "Primary key"},
            {"name": "customer_key", "type": "INT", "description": "FK to dim_customers"},
            {"name": "project_key", "type": "INT", "description": "FK to dim_projects"},
            {"name": "unit_key", "type": "INT", "description": "FK to dim_units"},
            {"name": "transaction_date_key", "type": "INT", "description": "FK to dim_date"},
            {"name": "transaction_type", "type": "VARCHAR", "description": "'demand' or 'receipt'"},
            {"name": "amount", "type": "DECIMAL", "description": "Transaction amount in INR"},
            {"name": "payment_mode", "type": "VARCHAR", "description": "cheque, neft, rtgs, upi, cash (only for receipts)"},
            {"name": "milestone", "type": "VARCHAR", "description": "Construction milestone (only for demands)"},
        ],
        joins=[
            "gold.dim_customers ON customer_key",
            "gold.dim_projects ON project_key",
            "gold.dim_units ON unit_key",
            "gold.dim_date ON transaction_date_key",
        ],
        sample_queries=[
            "Collection efficiency for Phase 2",
            "Total outstanding amount",
            "Receipts this month",
            "Payment mode breakdown",
        ],
    ),
    TableSchema(
        table_name="gold.fact_daily_funnel_snapshot",
        description="Pre-calculated daily snapshot of the lead funnel per project. "
                    "Use this for trend analysis and conversion rates over time.",
        columns=[
            {"name": "snapshot_id", "type": "INT", "description": "Primary key"},
            {"name": "snapshot_date_key", "type": "INT", "description": "FK to dim_date"},
            {"name": "project_key", "type": "INT", "description": "FK to dim_projects"},
            {"name": "total_inquiries", "type": "INT", "description": "Cumulative inquiries up to this date"},
            {"name": "total_site_visits", "type": "INT", "description": "Cumulative site visits"},
            {"name": "total_bookings", "type": "INT", "description": "Cumulative bookings"},
            {"name": "total_agreements", "type": "INT", "description": "Cumulative agreements"},
            {"name": "total_registered", "type": "INT", "description": "Cumulative registrations"},
            {"name": "total_cancelled", "type": "INT", "description": "Cumulative cancellations"},
            {"name": "total_active_leads", "type": "INT", "description": "Active leads (not cancelled/registered)"},
            {"name": "inquiry_to_visit_rate", "type": "DECIMAL", "description": "Inquiry to visit conversion rate %"},
            {"name": "visit_to_booking_rate", "type": "DECIMAL", "description": "Visit to booking conversion rate %"},
            {"name": "booking_to_agreement_rate", "type": "DECIMAL", "description": "Booking to agreement conversion rate %"},
        ],
        joins=[
            "gold.dim_date ON snapshot_date_key",
            "gold.dim_projects ON project_key",
        ],
        sample_queries=[
            "Conversion rate trend this quarter",
            "How has the funnel changed month over month?",
            "Active leads per project",
        ],
    ),
]


class SchemaRetriever:
    """Retrieves relevant schema context for a given query."""

    def __init__(self, llm_config: LLMConfig, vector_db_config: VectorDBConfig):
        self.llm_config = llm_config
        self.vector_db_config = vector_db_config
        self._schema_map = {s.table_name: s for s in GOLD_SCHEMA}
        self._embeddings_loaded = False

    async def retrieve(self, question: str, parsed_metric: str | None = None, top_k: int = 5) -> list[TableSchema]:
        """
        Retrieve the most relevant table schemas for a question.

        Uses a hybrid approach:
        1. Rule-based matching (fast, reliable for known patterns)
        2. Embedding-based similarity (for novel queries)
        """
        # Start with rule-based matching
        matched = self._rule_based_match(question, parsed_metric)

        if len(matched) >= top_k:
            return matched[:top_k]

        # Fill remaining slots with embedding-based retrieval
        try:
            embedding_matches = await self._embedding_match(question, top_k - len(matched))
            # Deduplicate
            matched_names = {s.table_name for s in matched}
            for schema in embedding_matches:
                if schema.table_name not in matched_names:
                    matched.append(schema)
        except Exception as e:
            logger.warning("Embedding retrieval failed, using rule-based only: %s", e)

        # Always include dim_date if any fact table is present
        fact_tables = [s for s in matched if s.table_name.startswith("gold.fact_")]
        if fact_tables and self._schema_map["gold.dim_date"] not in matched:
            matched.append(self._schema_map["gold.dim_date"])

        return matched[:top_k]

    def _rule_based_match(self, question: str, metric: str | None) -> list[TableSchema]:
        """Fast rule-based schema matching for common query patterns."""
        q = question.lower()
        matched = []

        # Collection-related
        if any(kw in q for kw in ["collection", "receipt", "demand", "outstanding", "payment"]):
            matched.append(self._schema_map["gold.fact_collections"])
            matched.append(self._schema_map["gold.dim_projects"])

        # Pipeline / lead / booking related
        if any(kw in q for kw in ["lead", "booking", "inquiry", "site visit", "cancel",
                                   "pipeline", "funnel", "conversion"]):
            matched.append(self._schema_map["gold.fact_lead_pipeline"])
            matched.append(self._schema_map["gold.dim_projects"])

        # Conversion rate / trend → snapshot table
        if any(kw in q for kw in ["conversion rate", "trend", "month over month",
                                   "funnel snapshot", "active leads"]):
            matched.append(self._schema_map["gold.fact_daily_funnel_snapshot"])

        # Sales person
        if any(kw in q for kw in ["sales person", "salesperson", "team", "performer"]):
            matched.append(self._schema_map["gold.dim_sales_persons"])

        # Lead source
        if any(kw in q for kw in ["source", "channel partner", "referral", "digital", "walk-in"]):
            matched.append(self._schema_map["gold.dim_lead_sources"])

        # Customer specific
        if any(kw in q for kw in ["customer", "buyer"]):
            matched.append(self._schema_map["gold.dim_customers"])

        # Unit specific
        if any(kw in q for kw in ["unit", "flat", "apartment", "bhk", "carpet area", "wing"]):
            matched.append(self._schema_map["gold.dim_units"])

        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for s in matched:
            if s.table_name not in seen:
                seen.add(s.table_name)
                deduped.append(s)
        return deduped

    async def _embedding_match(self, question: str, top_k: int) -> list[TableSchema]:
        """Semantic similarity search against embedded schema documents."""
        # Get embedding for the question
        embedding = await self._get_embedding(question)
        if not embedding:
            return []

        # Search ChromaDB
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"http://{self.vector_db_config.host}:{self.vector_db_config.port}"
                    f"/api/v1/collections/{self.vector_db_config.collection_name}/query",
                    json={
                        "query_embeddings": [embedding],
                        "n_results": top_k,
                    },
                )
                if response.status_code != 200:
                    return []

                results = response.json()
                table_names = [
                    meta["table_name"]
                    for meta in results.get("metadatas", [[]])[0]
                    if "table_name" in meta
                ]
                return [self._schema_map[name] for name in table_names if name in self._schema_map]
        except Exception as e:
            logger.warning("ChromaDB query failed: %s", e)
            return []

    async def _get_embedding(self, text: str) -> list[float] | None:
        """Get embedding vector from local model via Ollama."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.llm_config.embedding_endpoint}/api/embed",
                    json={"model": self.llm_config.embedding_model, "input": text},
                )
                response.raise_for_status()
                return response.json()["embeddings"][0]
        except Exception as e:
            logger.warning("Embedding generation failed: %s", e)
            return None

    def format_schema_for_prompt(self, schemas: list[TableSchema]) -> str:
        """Format retrieved schemas for injection into the SQL generation prompt."""
        lines = []
        for schema in schemas:
            lines.append(f"\n-- Table: {schema.table_name}")
            lines.append(f"-- Description: {schema.description}")
            lines.append(f"-- Columns:")
            for col in schema.columns:
                desc = f"  -- {col.get('description', '')}" if col.get('description') else ""
                lines.append(f"--   {col['name']} {col['type']}{desc}")
            if schema.joins:
                lines.append(f"-- Joins: {', '.join(schema.joins)}")
        return "\n".join(lines)
