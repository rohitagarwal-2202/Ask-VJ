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
    # ── Dimensions ──────────────────────────────────────────────
    TableSchema(
        table_name="gold.dim_date",
        description="Date dimension with calendar and Indian fiscal year support. "
                    "Join on date_key (YYYYMMDD integer format).",
        columns=[
            {"name": "date_key", "type": "INT", "description": "Primary key in YYYYMMDD format"},
            {"name": "full_date", "type": "DATE", "description": "Actual date value"},
            {"name": "day_of_week", "type": "VARCHAR", "description": "Monday, Tuesday, ..."},
            {"name": "month_number", "type": "INT", "description": "1-12"},
            {"name": "month_name", "type": "VARCHAR", "description": "January, February, ..."},
            {"name": "quarter", "type": "VARCHAR", "description": "Calendar quarter Q1-Q4"},
            {"name": "fiscal_quarter", "type": "VARCHAR", "description": "Indian FY quarter: Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar"},
            {"name": "calendar_year", "type": "INT", "description": "Calendar year"},
            {"name": "fiscal_year", "type": "INT", "description": "Indian fiscal year (FY2026 = Apr 2025 - Mar 2026)"},
            {"name": "fiscal_year_label", "type": "VARCHAR", "description": "Label like 'FY2026'"},
            {"name": "fiscal_year_id", "type": "INT", "description": "Farvision FiscalYearId: 56=FY2025-26, 52=FY2024-25"},
            {"name": "is_weekend", "type": "BOOLEAN", "description": "True if Saturday or Sunday"},
            {"name": "is_month_end", "type": "BOOLEAN", "description": "True if last day of month"},
        ],
        joins=[],
        sample_queries=["this month", "last quarter", "FY2026", "this fiscal year"],
    ),
    TableSchema(
        table_name="gold.dim_projects",
        description="VJ real estate projects. bu_id is the Farvision BusinessUnitId — "
                    "the universal project key across all Farvision tables.",
        columns=[
            {"name": "project_key", "type": "INT", "description": "Surrogate primary key"},
            {"name": "bu_id", "type": "INT", "description": "Farvision BusinessUnitId (universal project key)"},
            {"name": "project_name", "type": "VARCHAR", "description": "Canonical project name from crosswalk"},
            {"name": "phase_name", "type": "VARCHAR", "description": "Phase within the project"},
            {"name": "segment", "type": "VARCHAR", "description": "Residential, Commercial, etc."},
            {"name": "project_type", "type": "VARCHAR", "description": "High-rise, Plotted, Township, etc."},
            {"name": "total_units", "type": "INT", "description": "Total units in project"},
            {"name": "launch_date", "type": "DATE", "description": "Project launch date"},
            {"name": "status", "type": "VARCHAR", "description": "active, completed, or upcoming"},
        ],
        joins=[],
        sample_queries=["Project X", "Phase 2", "active projects", "residential projects"],
    ),
    TableSchema(
        table_name="gold.dim_typologies",
        description="Unit typologies (e.g. 1 BHK, 2 BHK). Maps Farvision TypologyId to readable names. "
                    "IMPORTANT: For '3 BHK' queries use typology_id=6 only (not XL/XR variants 23,35). "
                    "Check is_base_variant=TRUE for base typologies.",
        columns=[
            {"name": "typology_key", "type": "INT", "description": "Surrogate primary key"},
            {"name": "typology_id", "type": "INT", "description": "Farvision TypologyId"},
            {"name": "typology_code", "type": "VARCHAR", "description": "Source code e.g. '3BHK-XL'"},
            {"name": "typology", "type": "VARCHAR", "description": "Raw value e.g. '3.00BHK'"},
            {"name": "display_name", "type": "VARCHAR", "description": "Human-friendly e.g. '3 BHK'"},
            {"name": "is_base_variant", "type": "BOOLEAN", "description": "True for base 3BHK, false for XL/XR variants"},
        ],
        joins=[],
        sample_queries=["3 BHK units", "typology breakdown", "1BHK vs 2BHK"],
    ),
    TableSchema(
        table_name="gold.dim_units",
        description="Individual flats, apartments, shops, or offices within projects.",
        columns=[
            {"name": "unit_key", "type": "INT", "description": "Surrogate primary key"},
            {"name": "farvision_unit_id", "type": "INT", "description": "Farvision DimUnit.UnitId"},
            {"name": "project_key", "type": "INT", "description": "FK to dim_projects"},
            {"name": "typology_key", "type": "INT", "description": "FK to dim_typologies"},
            {"name": "unit_no", "type": "VARCHAR", "description": "Unit number (e.g., A-501)"},
            {"name": "wing", "type": "VARCHAR", "description": "Building wing"},
            {"name": "floor", "type": "INT", "description": "Floor number"},
            {"name": "unit_status", "type": "INT", "description": "Farvision status: 1=sold, 2=available, 3=blocked"},
            {"name": "farvision_status", "type": "VARCHAR", "description": "Raw status label from Farvision"},
            {"name": "saleable_area", "type": "DECIMAL", "description": "Saleable area in sq ft"},
            {"name": "carpet_area", "type": "DECIMAL", "description": "Carpet area in sq ft"},
        ],
        joins=[
            "gold.dim_projects ON project_key",
            "gold.dim_typologies ON typology_key",
        ],
        sample_queries=["2BHK units", "available flats", "units in wing A", "sold units"],
    ),
    TableSchema(
        table_name="gold.dim_customers",
        description="Unified customer records linked across VJ Sales and Farvision via entity resolution.",
        columns=[
            {"name": "customer_key", "type": "INT", "description": "Surrogate primary key"},
            {"name": "unified_customer_id", "type": "UUID", "description": "From silver.entity_map"},
            {"name": "farvision_ledger_id", "type": "INT", "description": "Farvision Ledger/CustomerId"},
            {"name": "full_name", "type": "VARCHAR", "description": "Full name"},
            {"name": "customer_name", "type": "VARCHAR", "description": "Display name"},
            {"name": "phone", "type": "VARCHAR", "description": "Phone number"},
            {"name": "mobile", "type": "VARCHAR", "description": "Mobile number"},
            {"name": "email", "type": "VARCHAR", "description": "Email address"},
            {"name": "pan_number", "type": "VARCHAR", "description": "PAN card number"},
            {"name": "first_inquiry_date", "type": "DATE", "description": "When the customer first inquired"},
            {"name": "lead_source", "type": "VARCHAR", "description": "How the customer found VJ"},
            {"name": "source_system_origin", "type": "VARCHAR", "description": "Where first seen: vjsales, farvision"},
            {"name": "is_active", "type": "BOOLEAN", "description": "Currently active customer"},
        ],
        joins=[],
        sample_queries=["customer details", "customer list", "customer by PAN"],
    ),
    TableSchema(
        table_name="gold.dim_sales_persons",
        description="Sales team members who handle leads and bookings.",
        columns=[
            {"name": "sales_person_key", "type": "INT", "description": "Surrogate primary key"},
            {"name": "farvision_sales_person_id", "type": "INT", "description": "Farvision SalesPersonId"},
            {"name": "name", "type": "VARCHAR", "description": "Sales person name"},
            {"name": "team", "type": "VARCHAR", "description": "Sales team name"},
            {"name": "region", "type": "VARCHAR", "description": "Region"},
            {"name": "is_active", "type": "BOOLEAN", "description": "Currently active"},
        ],
        joins=[],
        sample_queries=["sales person performance", "top performers", "team wise bookings"],
    ),
    TableSchema(
        table_name="gold.dim_lead_sources",
        description="Lead acquisition channels: walk-in, referral, digital (FB/Google), channel partners.",
        columns=[
            {"name": "source_key", "type": "INT", "description": "Surrogate primary key"},
            {"name": "source_name", "type": "VARCHAR", "description": "Specific source name"},
            {"name": "source_category", "type": "VARCHAR", "description": "organic, paid, referral, channel_partner"},
            {"name": "channel_partner_name", "type": "VARCHAR", "description": "CP name if applicable, else NULL"},
            {"name": "cp_id", "type": "UUID", "description": "Channel partner reference UUID"},
        ],
        joins=[],
        sample_queries=["lead sources", "channel partner performance", "digital leads"],
    ),
    # ── Facts ───────────────────────────────────────────────────
    TableSchema(
        table_name="gold.fact_lead_pipeline",
        description="Every stage transition in a lead's lifecycle. One row per stage change. "
                    "Stages: inquiry -> site_visit -> negotiation -> booking -> agreement -> registered | cancelled.",
        columns=[
            {"name": "pipeline_event_id", "type": "INT", "description": "Primary key"},
            {"name": "vjsales_lead_id", "type": "UUID", "description": "VJ Sales App lead UUID"},
            {"name": "vjsales_allotment_id", "type": "UUID", "description": "VJ Sales AllotmentPayment UUID"},
            {"name": "customer_key", "type": "INT", "description": "FK to dim_customers"},
            {"name": "project_key", "type": "INT", "description": "FK to dim_projects"},
            {"name": "unit_key", "type": "INT", "description": "FK to dim_units (NULL until booking)"},
            {"name": "sales_person_key", "type": "INT", "description": "FK to dim_sales_persons"},
            {"name": "source_key", "type": "INT", "description": "FK to dim_lead_sources"},
            {"name": "event_date_key", "type": "INT", "description": "FK to dim_date"},
            {"name": "pipeline_stage", "type": "VARCHAR", "description": "inquiry, site_visit, negotiation, booking, agreement, registered, cancelled"},
            {"name": "previous_stage", "type": "VARCHAR", "description": "Stage before this transition"},
            {"name": "days_in_previous_stage", "type": "INT", "description": "Days spent in previous stage"},
            {"name": "allotment_status", "type": "VARCHAR", "description": "Payment Complete, Agreement Done, Booked, Cancelled, etc."},
            {"name": "agreement_value", "type": "DECIMAL", "description": "Total agreement value in INR"},
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
            "Lead conversion rate for Project X",
            "Average time from inquiry to booking",
            "Which sales person has most site visits?",
            "Pipeline stage distribution",
        ],
    ),
    TableSchema(
        table_name="gold.fact_bookings",
        description="One row per booking from Farvision. The core transactional fact linking "
                    "customer, project, unit, typology, and financials. Covers booking, "
                    "agreement, registration, and cancellation lifecycle.",
        columns=[
            {"name": "booking_key", "type": "INT", "description": "Surrogate primary key"},
            {"name": "farvision_booking_id", "type": "INT", "description": "Farvision FactBooking.BookingId"},
            {"name": "booking_no", "type": "VARCHAR", "description": "Booking number"},
            {"name": "booking_date", "type": "DATE", "description": "Date of booking"},
            {"name": "customer_key", "type": "INT", "description": "FK to dim_customers"},
            {"name": "project_key", "type": "INT", "description": "FK to dim_projects"},
            {"name": "unit_key", "type": "INT", "description": "FK to dim_units"},
            {"name": "sales_person_key", "type": "INT", "description": "FK to dim_sales_persons"},
            {"name": "typology_key", "type": "INT", "description": "FK to dim_typologies"},
            {"name": "net_basic_price", "type": "DECIMAL", "description": "Net basic price in INR"},
            {"name": "agreement_value", "type": "DECIMAL", "description": "Total agreement value in INR"},
            {"name": "discount_percentage", "type": "DECIMAL", "description": "Discount percentage applied"},
            {"name": "is_cancelled", "type": "BOOLEAN", "description": "True if booking was cancelled"},
            {"name": "cancellation_date", "type": "DATE", "description": "Date of cancellation (NULL if active)"},
            {"name": "agreement_date", "type": "DATE", "description": "Date of agreement execution"},
            {"name": "agreement_no", "type": "VARCHAR", "description": "Agreement number"},
            {"name": "registration_date", "type": "DATE", "description": "Date of registration"},
            {"name": "registration_no", "type": "VARCHAR", "description": "Registration number"},
            {"name": "allotment_date", "type": "DATE", "description": "Date of allotment"},
            {"name": "broker_id", "type": "INT", "description": "Broker / channel partner ID"},
            {"name": "fiscal_year_id", "type": "INT", "description": "Farvision FiscalYearId: 56=FY2025-26, 52=FY2024-25"},
        ],
        joins=[
            "gold.dim_customers ON customer_key",
            "gold.dim_projects ON project_key",
            "gold.dim_units ON unit_key",
            "gold.dim_sales_persons ON sales_person_key",
            "gold.dim_typologies ON typology_key",
        ],
        sample_queries=[
            "How many bookings this month?",
            "Total booking value this FY",
            "Cancellation rate",
            "Agreement done but not registered",
            "Which sales person has most bookings?",
        ],
    ),
    TableSchema(
        table_name="gold.fact_receipts",
        description="Payments received against bookings. One row per payment from Farvision FactReceipt.",
        columns=[
            {"name": "receipt_key", "type": "INT", "description": "Surrogate primary key"},
            {"name": "farvision_receipt_id", "type": "INT", "description": "Farvision FactReceipt.ReceiptId"},
            {"name": "booking_key", "type": "INT", "description": "FK to fact_bookings"},
            {"name": "customer_key", "type": "INT", "description": "FK to dim_customers"},
            {"name": "project_key", "type": "INT", "description": "FK to dim_projects"},
            {"name": "unit_key", "type": "INT", "description": "FK to dim_units"},
            {"name": "date_key", "type": "INT", "description": "FK to dim_date"},
            {"name": "amount", "type": "DECIMAL", "description": "Receipt amount in INR"},
            {"name": "payment_mode", "type": "VARCHAR", "description": "Cheque, NEFT, RTGS, Cash, etc."},
            {"name": "instrument_no", "type": "VARCHAR", "description": "Cheque/NEFT reference number"},
            {"name": "document_no", "type": "VARCHAR", "description": "Farvision document number"},
        ],
        joins=[
            "gold.fact_bookings ON booking_key",
            "gold.dim_customers ON customer_key",
            "gold.dim_projects ON project_key",
            "gold.dim_units ON unit_key",
            "gold.dim_date ON date_key",
        ],
        sample_queries=[
            "Collections this month",
            "Payment mode breakdown",
            "Receipts by project",
            "Total receipts this FY",
        ],
    ),
    TableSchema(
        table_name="gold.fact_invoices",
        description="Demand letters / invoices raised against bookings. One row per invoice "
                    "from Farvision, typically tied to construction milestones.",
        columns=[
            {"name": "invoice_key", "type": "INT", "description": "Surrogate primary key"},
            {"name": "farvision_invoice_id", "type": "INT", "description": "Farvision FactInvoice.InvoiceId"},
            {"name": "booking_key", "type": "INT", "description": "FK to fact_bookings"},
            {"name": "customer_key", "type": "INT", "description": "FK to dim_customers"},
            {"name": "project_key", "type": "INT", "description": "FK to dim_projects"},
            {"name": "unit_key", "type": "INT", "description": "FK to dim_units"},
            {"name": "date_key", "type": "INT", "description": "FK to dim_date"},
            {"name": "basic_amount", "type": "DECIMAL", "description": "Basic invoice amount in INR"},
            {"name": "total_amount", "type": "DECIMAL", "description": "Total invoice amount in INR"},
            {"name": "due_date", "type": "DATE", "description": "Payment due date"},
        ],
        joins=[
            "gold.fact_bookings ON booking_key",
            "gold.dim_customers ON customer_key",
            "gold.dim_projects ON project_key",
            "gold.dim_units ON unit_key",
            "gold.dim_date ON date_key",
        ],
        sample_queries=[
            "Total demand raised this quarter",
            "Invoices due this month",
            "Demand vs collection gap",
        ],
    ),
    TableSchema(
        table_name="gold.fact_outstanding",
        description="Pre-aggregated aging analysis per customer+unit from Farvision. "
                    "Used for collections dashboards and overdue reporting. "
                    "Aging buckets: 0-15, 16-30, 31-60, 61-90, 91-120, 121-180, >180 days.",
        columns=[
            {"name": "outstanding_key", "type": "INT", "description": "Surrogate primary key"},
            {"name": "customer_key", "type": "INT", "description": "FK to dim_customers"},
            {"name": "project_key", "type": "INT", "description": "FK to dim_projects"},
            {"name": "unit_key", "type": "INT", "description": "FK to dim_units"},
            {"name": "customer_name", "type": "VARCHAR", "description": "Denormalized customer name for fast queries"},
            {"name": "unit_no", "type": "VARCHAR", "description": "Denormalized unit number"},
            {"name": "bill_amount", "type": "DECIMAL", "description": "Total billed amount"},
            {"name": "paid_amount", "type": "DECIMAL", "description": "Total paid amount"},
            {"name": "due_amount", "type": "DECIMAL", "description": "Amount currently due"},
            {"name": "on_account_amount", "type": "DECIMAL", "description": "Advance / on-account amount"},
            {"name": "overdue_days", "type": "INT", "description": "Number of days overdue"},
            {"name": "day_amt_15", "type": "DECIMAL", "description": "Amount overdue 0-15 days"},
            {"name": "day_amt_30", "type": "DECIMAL", "description": "Amount overdue 16-30 days"},
            {"name": "day_amt_60", "type": "DECIMAL", "description": "Amount overdue 31-60 days"},
            {"name": "day_amt_90", "type": "DECIMAL", "description": "Amount overdue 61-90 days"},
            {"name": "day_amt_120", "type": "DECIMAL", "description": "Amount overdue 91-120 days"},
            {"name": "day_amt_180", "type": "DECIMAL", "description": "Amount overdue 121-180 days"},
            {"name": "day_amt_more_180", "type": "DECIMAL", "description": "Amount overdue >180 days"},
            {"name": "document_date", "type": "DATE", "description": "Document date"},
            {"name": "due_date", "type": "DATE", "description": "Payment due date"},
        ],
        joins=[
            "gold.dim_customers ON customer_key",
            "gold.dim_projects ON project_key",
            "gold.dim_units ON unit_key",
        ],
        sample_queries=[
            "Total outstanding amount",
            "Aging analysis",
            "Customers overdue more than 90 days",
            "Outstanding by project",
        ],
    ),
    TableSchema(
        table_name="gold.fact_inventory",
        description="Current state of each unit in the sales inventory from VJ Sales App. "
                    "Includes pricing, availability status, and area details.",
        columns=[
            {"name": "inventory_key", "type": "INT", "description": "Surrogate primary key"},
            {"name": "project_key", "type": "INT", "description": "FK to dim_projects"},
            {"name": "unit_key", "type": "INT", "description": "FK to dim_units"},
            {"name": "typology_key", "type": "INT", "description": "FK to dim_typologies"},
            {"name": "inventory_status", "type": "VARCHAR", "description": "Available, On Hold, Sold"},
            {"name": "total_cost", "type": "DECIMAL", "description": "Total unit cost in INR"},
            {"name": "bsp", "type": "DECIMAL", "description": "Base selling price per sqft"},
            {"name": "saleable_area", "type": "DECIMAL", "description": "Saleable area in sq ft"},
            {"name": "chargeable_area", "type": "DECIMAL", "description": "Chargeable area in sq ft"},
            {"name": "display_unit_type", "type": "VARCHAR", "description": "Display label e.g. '3 BHK - Tower A'"},
        ],
        joins=[
            "gold.dim_projects ON project_key",
            "gold.dim_units ON unit_key",
            "gold.dim_typologies ON typology_key",
        ],
        sample_queries=[
            "Available units in Project X",
            "Average rate per sqft",
            "Unsold inventory value",
            "Inventory by typology",
        ],
    ),
    TableSchema(
        table_name="gold.fact_referrals",
        description="Customer-to-customer referrals from the VJOP owner portal. "
                    "Referral lifecycle: Unclaimed -> Claimed -> Site Visit Done -> Agreement Done, "
                    "with loyalty points earned at each milestone.",
        columns=[
            {"name": "referral_key", "type": "INT", "description": "Surrogate primary key"},
            {"name": "referrer_customer_key", "type": "INT", "description": "FK to dim_customers (who referred)"},
            {"name": "referred_lead_name", "type": "VARCHAR", "description": "Name of referred person"},
            {"name": "referred_mobile", "type": "VARCHAR", "description": "Mobile of referred person"},
            {"name": "project_key", "type": "INT", "description": "FK to dim_projects"},
            {"name": "referral_status", "type": "VARCHAR", "description": "Unclaimed, Claimed, Site Visit Done, Agreement Done"},
            {"name": "vjop_lead_id", "type": "INT", "description": "VJOP leads table ID"},
            {"name": "sales_app_lead_id", "type": "UUID", "description": "Linked VJ Sales App lead UUID"},
            {"name": "booking_id", "type": "INT", "description": "From VJOP lead_allotments (NOT leads)"},
            {"name": "points_earned", "type": "DECIMAL", "description": "Loyalty points earned"},
            {"name": "points_redeemed", "type": "DECIMAL", "description": "Loyalty points redeemed"},
        ],
        joins=[
            "gold.dim_customers ON referrer_customer_key",
            "gold.dim_projects ON project_key",
        ],
        sample_queries=[
            "Top referrers",
            "Referral conversion rate",
            "Total points earned",
            "VJOP referral status breakdown",
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

    async def retrieve(
        self,
        question: str,
        parsed_metric: str | None = None,
        top_k: int = 5,
        excluded_tables: set[str] | None = None,
    ) -> list[TableSchema]:
        """
        Retrieve the most relevant table schemas for a question.

        Uses a hybrid approach:
        1. Rule-based matching (fast, reliable for known patterns)
        2. Embedding-based similarity (for novel queries)

        Args:
            excluded_tables: Set of table names to exclude (e.g. from guardrails).
        """
        # Start with rule-based matching
        matched = self._rule_based_match(question, parsed_metric)

        if len(matched) >= top_k:
            matched = matched[:top_k]
        else:
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

        # Filter out excluded tables (guardrails)
        if excluded_tables:
            matched = [s for s in matched if s.table_name not in excluded_tables]

        return matched[:top_k]

    def _rule_based_match(self, question: str, metric: str | None) -> list[TableSchema]:
        """Fast rule-based schema matching for common query patterns."""
        q = question.lower()
        matched = []

        # Booking / sold / agreement / registration related
        if any(kw in q for kw in ["booking", "sold", "agreement", "registration",
                                   "cancel", "allotment", "discount"]):
            matched.append(self._schema_map["gold.fact_bookings"])
            matched.append(self._schema_map["gold.dim_projects"])

        # Receipt / payment / collection related
        if any(kw in q for kw in ["receipt", "payment", "collection"]):
            matched.append(self._schema_map["gold.fact_receipts"])
            matched.append(self._schema_map["gold.dim_projects"])

        # Invoice / demand related
        if any(kw in q for kw in ["invoice", "demand"]):
            matched.append(self._schema_map["gold.fact_invoices"])

        # Outstanding / overdue / aging / dues related
        if any(kw in q for kw in ["outstanding", "overdue", "aging", "dues", "due amount"]):
            matched.append(self._schema_map["gold.fact_outstanding"])

        # Inventory / available / unsold / pricing / rate / bsp related
        if any(kw in q for kw in ["inventory", "available", "unsold", "pricing",
                                   "rate", "bsp", "on hold"]):
            matched.append(self._schema_map["gold.fact_inventory"])

        # Referral / loyalty / points / vjop related
        if any(kw in q for kw in ["referral", "loyalty", "points", "vjop", "referrer"]):
            matched.append(self._schema_map["gold.fact_referrals"])

        # Pipeline / lead / inquiry / site visit related
        if any(kw in q for kw in ["lead", "inquiry", "site visit", "pipeline",
                                   "negotiation", "allotment_status"]):
            matched.append(self._schema_map["gold.fact_lead_pipeline"])
            matched.append(self._schema_map["gold.dim_projects"])

        # Conversion rate / trend / funnel → snapshot table
        if any(kw in q for kw in ["conversion rate", "trend", "month over month",
                                   "funnel snapshot", "active leads", "funnel"]):
            matched.append(self._schema_map["gold.fact_daily_funnel_snapshot"])

        # Typology specific
        if any(kw in q for kw in ["typology", "bhk", "1bhk", "2bhk", "3bhk",
                                   "1 bhk", "2 bhk", "3 bhk"]):
            matched.append(self._schema_map["gold.dim_typologies"])

        # Sales person
        if any(kw in q for kw in ["sales person", "salesperson", "team", "performer"]):
            matched.append(self._schema_map["gold.dim_sales_persons"])

        # Lead source / channel partner
        if any(kw in q for kw in ["source", "channel partner", "digital", "walk-in",
                                   "organic", "paid lead"]):
            matched.append(self._schema_map["gold.dim_lead_sources"])

        # Customer specific
        if any(kw in q for kw in ["customer", "buyer"]):
            matched.append(self._schema_map["gold.dim_customers"])

        # Unit specific
        if any(kw in q for kw in ["unit", "flat", "apartment", "carpet area", "wing", "floor"]):
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
