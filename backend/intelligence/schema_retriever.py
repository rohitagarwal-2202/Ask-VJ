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
        table_name="gold.v_projects",
        description="VJ real estate projects (view over Silver). bu_id is the Farvision BusinessUnitId — "
                    "the universal project key across all Farvision tables.",
        columns=[
            {"name": "project_skey", "type": "INT", "description": "Surrogate primary key"},
            {"name": "bu_id", "type": "INT", "description": "Farvision BusinessUnitId (universal project key)"},
            {"name": "project_name", "type": "VARCHAR", "description": "Canonical project name from crosswalk"},
            {"name": "project_type", "type": "VARCHAR", "description": "High-rise, Plotted, Township, etc."},
            {"name": "rera_number", "type": "VARCHAR", "description": "RERA registration number"},
            {"name": "city", "type": "VARCHAR", "description": "City where the project is located"},
            {"name": "state", "type": "VARCHAR", "description": "State where the project is located"},
            {"name": "is_completed", "type": "BOOLEAN", "description": "True if the project is completed"},
            {"name": "is_active", "type": "BOOLEAN", "description": "True if the project is currently active"},
        ],
        joins=[],
        sample_queries=["Project X", "active projects", "residential projects", "projects in Pune"],
    ),
    TableSchema(
        table_name="gold.v_units",
        description="Individual flats, apartments, shops, or offices within projects (view over Silver).",
        columns=[
            {"name": "project_unit_skey", "type": "INT", "description": "Surrogate primary key"},
            {"name": "project_name", "type": "VARCHAR", "description": "Denormalized project name"},
            {"name": "bu_id", "type": "INT", "description": "Farvision BusinessUnitId"},
            {"name": "wing_name", "type": "VARCHAR", "description": "Building wing name"},
            {"name": "floor_no", "type": "INT", "description": "Floor number"},
            {"name": "unit_no", "type": "VARCHAR", "description": "Unit number (e.g., A-501)"},
            {"name": "unit_type", "type": "VARCHAR", "description": "Raw unit type code"},
            {"name": "display_unit_type", "type": "VARCHAR", "description": "Human-friendly e.g. '3 BHK - Tower A'"},
            {"name": "unit_status", "type": "VARCHAR", "description": "Unit availability status"},
            {"name": "saleable_area", "type": "DECIMAL", "description": "Saleable area in sq ft"},
            {"name": "chargeable_area", "type": "DECIMAL", "description": "Chargeable area in sq ft"},
            {"name": "total_cost_amt", "type": "DECIMAL", "description": "Total unit cost in INR"},
            {"name": "bsp_amt", "type": "DECIMAL", "description": "Base selling price per sq ft"},
            {"name": "fv_status", "type": "VARCHAR", "description": "Farvision status label"},
            {"name": "fv_unit_id", "type": "INT", "description": "Farvision DimUnit.UnitId"},
        ],
        joins=[
            "gold.v_projects ON bu_id",
        ],
        sample_queries=["2BHK units", "available flats", "units in wing A", "sold units"],
    ),
    TableSchema(
        table_name="gold.v_buyers",
        description="Buyer / customer records (view over Silver).",
        columns=[
            {"name": "buyer_skey", "type": "INT", "description": "Surrogate primary key"},
            {"name": "buyer_id", "type": "VARCHAR", "description": "Source buyer identifier"},
            {"name": "buyer_name", "type": "VARCHAR", "description": "Full buyer name"},
            {"name": "contact_number", "type": "VARCHAR", "description": "Contact phone number"},
            {"name": "email", "type": "VARCHAR", "description": "Email address"},
            {"name": "gender", "type": "VARCHAR", "description": "Gender"},
            {"name": "pan", "type": "VARCHAR", "description": "PAN card number"},
            {"name": "rm_name", "type": "VARCHAR", "description": "Relationship manager name"},
            {"name": "is_verified", "type": "BOOLEAN", "description": "True if buyer identity is verified"},
        ],
        joins=[],
        sample_queries=["customer details", "buyer list", "customer by PAN"],
    ),
    TableSchema(
        table_name="gold.v_employees",
        description="Sales team / employee records (view over Silver).",
        columns=[
            {"name": "employee_skey", "type": "INT", "description": "Surrogate primary key"},
            {"name": "employee_name", "type": "VARCHAR", "description": "Employee name"},
            {"name": "email", "type": "VARCHAR", "description": "Email address"},
            {"name": "role_name", "type": "VARCHAR", "description": "Role / designation"},
            {"name": "crm_designation", "type": "VARCHAR", "description": "CRM-specific designation"},
            {"name": "is_active", "type": "BOOLEAN", "description": "Currently active"},
        ],
        joins=[],
        sample_queries=["sales person performance", "top performers", "team wise bookings"],
    ),
    TableSchema(
        table_name="gold.v_channel_partners",
        description="Channel partners / brokers who refer leads to VJ (view over Silver).",
        columns=[
            {"name": "channel_partner_skey", "type": "INT", "description": "Surrogate primary key"},
            {"name": "cp_display_id", "type": "VARCHAR", "description": "Display identifier for the CP"},
            {"name": "cp_type", "type": "VARCHAR", "description": "Channel partner type"},
            {"name": "billing_name", "type": "VARCHAR", "description": "Billing / company name"},
            {"name": "approval_status", "type": "VARCHAR", "description": "Approval status of the CP"},
            {"name": "is_disabled", "type": "BOOLEAN", "description": "True if CP is disabled"},
        ],
        joins=[],
        sample_queries=["channel partner list", "approved CPs", "CP performance"],
    ),
    # ── Views & Facts ──────────────────────────────────────────
    TableSchema(
        table_name="gold.v_leads",
        description="Lead records with denormalized buyer, project, and channel partner details (view over Silver). "
                    "One row per lead. Use for lead counts, status breakdowns, and attribution analysis.",
        columns=[
            {"name": "fact_lead_skey", "type": "INT", "description": "Surrogate primary key"},
            {"name": "lead_id", "type": "VARCHAR", "description": "Source lead identifier"},
            {"name": "lead_display_id", "type": "VARCHAR", "description": "Human-readable lead display ID"},
            {"name": "lead_date", "type": "DATE", "description": "Date the lead was created"},
            {"name": "buyer_name", "type": "VARCHAR", "description": "Buyer / prospect name"},
            {"name": "buyer_phone", "type": "VARCHAR", "description": "Buyer phone number"},
            {"name": "project_name", "type": "VARCHAR", "description": "Denormalized project name"},
            {"name": "bu_id", "type": "INT", "description": "Farvision BusinessUnitId"},
            {"name": "channel_partner", "type": "VARCHAR", "description": "Channel partner name"},
            {"name": "fos_name", "type": "VARCHAR", "description": "Field officer name"},
            {"name": "project_head", "type": "VARCHAR", "description": "Project head name"},
            {"name": "sales_manager", "type": "VARCHAR", "description": "Sales manager name"},
            {"name": "claimed_by", "type": "VARCHAR", "description": "Who claimed the lead"},
            {"name": "lead_status", "type": "VARCHAR", "description": "Current lead status"},
            {"name": "lead_type", "type": "VARCHAR", "description": "Lead type classification"},
            {"name": "lead_sub_type", "type": "VARCHAR", "description": "Lead sub-type classification"},
            {"name": "lead_category", "type": "VARCHAR", "description": "Lead category"},
            {"name": "lead_response", "type": "VARCHAR", "description": "Lead response status"},
            {"name": "src_created_ts", "type": "TIMESTAMP", "description": "Source system created timestamp"},
            {"name": "src_updated_ts", "type": "TIMESTAMP", "description": "Source system updated timestamp"},
        ],
        joins=[
            "gold.v_projects ON bu_id",
        ],
        sample_queries=[
            "Total leads this month",
            "Lead status breakdown by project",
            "Which channel partner brought the most leads?",
            "Leads claimed by sales manager",
        ],
    ),
    TableSchema(
        table_name="gold.v_site_visits",
        description="Site visit records with denormalized lead, buyer, and project details (view over Silver). "
                    "One row per site visit.",
        columns=[
            {"name": "fact_site_visit_skey", "type": "INT", "description": "Surrogate primary key"},
            {"name": "site_visit_id", "type": "VARCHAR", "description": "Source site visit identifier"},
            {"name": "lead_display_id", "type": "VARCHAR", "description": "Linked lead display ID"},
            {"name": "buyer_name", "type": "VARCHAR", "description": "Buyer / prospect name"},
            {"name": "project_name", "type": "VARCHAR", "description": "Denormalized project name"},
            {"name": "accompanied_by", "type": "VARCHAR", "description": "Who accompanied the visitor"},
            {"name": "channel_partner", "type": "VARCHAR", "description": "Channel partner name"},
            {"name": "visit_date", "type": "DATE", "description": "Date of the site visit"},
            {"name": "site_visit_ts", "type": "TIMESTAMP", "description": "Exact timestamp of the visit"},
            {"name": "mode", "type": "VARCHAR", "description": "Visit mode (walk-in, scheduled, etc.)"},
            {"name": "remarks", "type": "VARCHAR", "description": "Visit remarks / notes"},
        ],
        joins=[
            "gold.v_leads ON lead_display_id",
            "gold.v_projects ON project_name",
        ],
        sample_queries=[
            "Site visits this month",
            "Site visits by project",
            "Which channel partner has most site visits?",
            "Walk-in vs scheduled visits",
        ],
    ),
    TableSchema(
        table_name="gold.v_conversion_rates",
        description="Pre-calculated lead-to-site-visit conversion rates per project (view over Silver).",
        columns=[
            {"name": "project_name", "type": "VARCHAR", "description": "Project name"},
            {"name": "bu_id", "type": "INT", "description": "Farvision BusinessUnitId"},
            {"name": "total_leads", "type": "INT", "description": "Total leads for the project"},
            {"name": "total_site_visits", "type": "INT", "description": "Total site visits for the project"},
            {"name": "lead_to_visit_rate", "type": "DECIMAL", "description": "Lead to site visit conversion rate %"},
        ],
        joins=[],
        sample_queries=[
            "Lead to visit conversion rate",
            "Conversion rate by project",
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
        table_name="gold.snapshot_outstanding",
        description="Point-in-time snapshot of aging analysis per customer+unit from Farvision. "
                    "Rebuilt daily. Used for collections dashboards and overdue reporting. "
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
        table_name="gold.snapshot_inventory",
        description="Point-in-time snapshot of each unit in the sales inventory from VJ Sales App. "
                    "Rebuilt daily. Includes pricing, availability status, and area details.",
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
        table_name="gold.snapshot_referrals",
        description="Point-in-time snapshot of customer-to-customer referrals from the VJOP owner portal. "
                    "Rebuilt daily. Referral lifecycle: Unclaimed -> Claimed -> Site Visit Done -> Agreement Done, "
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

        # Always include dim_date if any fact/snapshot table is present
        fact_tables = [s for s in matched if s.table_name.startswith(("gold.fact_", "gold.snapshot_"))]
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
            matched.append(self._schema_map["gold.v_projects"])

        # Receipt / payment / collection related
        if any(kw in q for kw in ["receipt", "payment", "collection"]):
            matched.append(self._schema_map["gold.fact_receipts"])
            matched.append(self._schema_map["gold.v_projects"])

        # Invoice / demand related
        if any(kw in q for kw in ["invoice", "demand"]):
            matched.append(self._schema_map["gold.fact_invoices"])

        # Outstanding / overdue / aging / dues related
        if any(kw in q for kw in ["outstanding", "overdue", "aging", "dues", "due amount"]):
            matched.append(self._schema_map["gold.snapshot_outstanding"])

        # Inventory / available / unsold / pricing / rate / bsp related
        if any(kw in q for kw in ["inventory", "available", "unsold", "pricing",
                                   "rate", "bsp", "on hold"]):
            matched.append(self._schema_map["gold.snapshot_inventory"])

        # Referral / loyalty / points / vjop related
        if any(kw in q for kw in ["referral", "loyalty", "points", "vjop", "referrer"]):
            matched.append(self._schema_map["gold.snapshot_referrals"])

        # Lead / inquiry related
        if any(kw in q for kw in ["lead", "inquiry", "pipeline",
                                   "negotiation", "allotment_status"]):
            matched.append(self._schema_map["gold.v_leads"])
            matched.append(self._schema_map["gold.v_projects"])

        # Site visit related
        if any(kw in q for kw in ["site visit", "walk-in visit", "scheduled visit"]):
            matched.append(self._schema_map["gold.v_site_visits"])
            matched.append(self._schema_map["gold.v_projects"])

        # Conversion rate / trend / funnel → snapshot table or v_conversion_rates
        if any(kw in q for kw in ["conversion rate", "trend", "month over month",
                                   "funnel snapshot", "active leads", "funnel"]):
            matched.append(self._schema_map["gold.fact_daily_funnel_snapshot"])
            matched.append(self._schema_map["gold.v_conversion_rates"])

        # Sales person / employee
        if any(kw in q for kw in ["sales person", "salesperson", "team", "performer",
                                   "employee"]):
            matched.append(self._schema_map["gold.v_employees"])

        # Lead source / channel partner
        if any(kw in q for kw in ["source", "channel partner", "digital", "walk-in",
                                   "organic", "paid lead", "broker", "cp "]):
            matched.append(self._schema_map["gold.v_channel_partners"])

        # Customer / buyer specific
        if any(kw in q for kw in ["customer", "buyer"]):
            matched.append(self._schema_map["gold.v_buyers"])

        # Unit specific
        if any(kw in q for kw in ["unit", "flat", "apartment", "carpet area", "wing", "floor"]):
            matched.append(self._schema_map["gold.v_units"])

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
