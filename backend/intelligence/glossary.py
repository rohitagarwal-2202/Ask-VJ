"""
Business Glossary — VJ-specific business terms, formulas, and domain knowledge.

Based on real schemas from Farvision ERP, VJ Sales App, and VJOP.

Used for:
1. Injecting into SQL generation prompts so the LLM calculates metrics correctly
2. Answering CLARIFICATION queries directly without hitting the database
3. Embedding into vector DB for semantic retrieval
"""

from dataclasses import dataclass


@dataclass
class GlossaryEntry:
    term: str
    definition: str
    formula: str | None = None
    sql_hint: str | None = None          # Direct SQL pattern for this metric
    table: str | None = None             # Primary table for this metric
    good_range: str | None = None        # Expected healthy range
    alert_threshold: str | None = None   # When to flag as concerning
    category: str = "general"            # sales, collections, operations, general, referrals


# The canonical business glossary for VJ
GLOSSARY: list[GlossaryEntry] = [

    # ═══════════════════════════════════════════════
    # SYSTEM RULES (critical for SQL generation)
    # ═══════════════════════════════════════════════
    GlossaryEntry(
        term="tenant id",
        definition="All Farvision ERP queries MUST include TenantId = 75. "
                   "This is a mandatory filter on every Farvision-sourced table.",
        sql_hint="Always include WHERE TenantId = 75 (or AND TenantId = 75) "
                 "when querying any gold table sourced from Farvision.",
        category="general",
    ),
    GlossaryEntry(
        term="fiscal year",
        definition="VJ follows the Indian fiscal year: April to March. "
                   "FY 2025-26 = FiscalYearId 56 (current). FY 2024-25 = FiscalYearId 52 (previous). "
                   "FY2026 = April 2025 to March 2026.",
        sql_hint="Use fiscal_year and fiscal_quarter columns in gold.dim_date. "
                 "fiscal_quarter: Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar. "
                 "For Farvision-specific queries, FiscalYearId 56 = current FY, 52 = previous FY.",
        table="gold.dim_date",
        category="general",
    ),
    GlossaryEntry(
        term="bu id",
        definition="BusinessUnitId (BUId) is the universal project identifier across all three systems. "
                   "Farvision uses ENGG.DimBusinessUnit.BusinessUnitId, VJ Sales stores it as Projects.buId, "
                   "VJOP stores it as customer_bookings_units.BUId. Use gold.dim_projects.bu_id to filter by project.",
        sql_hint="JOIN gold.dim_projects ON bu_id to filter by project.",
        table="gold.dim_projects",
        category="general",
    ),

    # ═══════════════════════════════════════════════
    # TYPOLOGY (unit types)
    # ═══════════════════════════════════════════════
    GlossaryEntry(
        term="typology",
        definition="Unit type classification in Farvision. Key mappings: "
                   "TypologyId 1 = 1.00BHK, 2 = 1.50BHK, 4 = 2.00BHK, 6 = 3.00BHK (base), "
                   "23 = 3.00BHK XL, 35 = 3.00BHK XR, 37 = 2.00BHK XL, 36 = 2.00BHK XR. "
                   "IMPORTANT: '3 BHK' means ONLY the base variant unless user explicitly says XL or XR.",
        sql_hint="Use gold.dim_typologies table. For '3 BHK' queries, filter: "
                 "WHERE t.is_base_variant = true AND t.display_name LIKE '3 BHK%'. "
                 "For 'all 3 BHK variants' (including XL/XR), use WHERE t.display_name LIKE '3 BHK%'.",
        table="gold.dim_typologies",
        category="general",
    ),

    # ═══════════════════════════════════════════════
    # SALES & BOOKINGS
    # ═══════════════════════════════════════════════
    GlossaryEntry(
        term="booking",
        definition="When a customer commits to purchasing a unit by paying a booking amount. "
                   "Tracked in Farvision's CRMG.DimBookingMaster. A booking proceeds through stages: "
                   "Booking → Allotment → Agreement → Registration. "
                   "Active bookings have IsCancelled = 0 (is_cancelled = false in gold).",
        sql_hint="Use gold.fact_bookings. Filter is_cancelled = false for active bookings.",
        table="gold.fact_bookings",
        category="sales",
    ),
    GlossaryEntry(
        term="net basic price",
        definition="The base price of the unit in the booking, before taxes and other charges. "
                   "This is the primary financial value of a booking in Farvision.",
        table="gold.fact_bookings",
        category="sales",
    ),
    GlossaryEntry(
        term="agreement value",
        definition="The total value of the property agreement in INR. "
                   "In VJ Sales App, extracted from AllotmentPayment JSONB fields. "
                   "In Farvision, tracked via CRMG.DimUnitAgreement.",
        table="gold.fact_bookings",
        category="sales",
    ),
    GlossaryEntry(
        term="cancellation",
        definition="When a booked unit is cancelled by the customer. "
                   "IsCancelled = 1 in Farvision, status = 'Cancelled' in VJ Sales. "
                   "Tracked with cancellation date, charge, and reason.",
        sql_hint="gold.fact_bookings WHERE is_cancelled = true. "
                 "For cancellation details, check cancellation_date.",
        table="gold.fact_bookings",
        category="sales",
    ),
    GlossaryEntry(
        term="unit status",
        definition="The current status of a unit. In Farvision FactUnitMovement: "
                   "UnitStatus 1 = Sold/Booked, 2 = Available/Unsold, 3 = Blocked/Reserved. "
                   "In VJ Sales: 'Available', 'On Hold', 'Sold'.",
        sql_hint="gold.dim_units.unit_status: 1=sold, 2=available, 3=blocked. "
                 "For available inventory, use gold.snapshot_inventory WHERE inventory_status = 'Available'.",
        table="gold.dim_units",
        category="sales",
    ),

    # ═══════════════════════════════════════════════
    # LEADS & PIPELINE
    # ═══════════════════════════════════════════════
    GlossaryEntry(
        term="lead",
        definition="A potential customer in the VJ Sales App. Leads enter via walk-ins, referrals, "
                   "digital marketing, or channel partners. The VJ Sales App tracks 108,000+ leads. "
                   "Lead IDs are UUIDs in VJ Sales.",
        table="gold.fact_lead_pipeline",
        category="sales",
    ),
    GlossaryEntry(
        term="pipeline stage",
        definition="The current status of a lead in the VJ Sales App. "
                   "Stages: New → Contacted → Site Visit → Negotiation → Booked → Agreement → Registered. "
                   "Can also be 'Lost' or 'Cancelled' at any point.",
        table="gold.fact_lead_pipeline",
        category="sales",
    ),
    GlossaryEntry(
        term="allotment",
        definition="When a lead is allotted a specific unit in VJ Sales App. "
                   "Tracked in AllotmentPayment table. Allotment statuses include: "
                   "'Payment Pending', 'Partial Payment Done', 'Payment Complete', 'Booked', "
                   "'Agreement Done', 'Cancelled', 'Refund Initiated', 'Refund Processed'.",
        sql_hint="Use gold.fact_lead_pipeline.allotment_status for current allotment state.",
        table="gold.fact_lead_pipeline",
        category="sales",
    ),
    GlossaryEntry(
        term="site visit",
        definition="A scheduled visit by a lead to a VJ project site. "
                   "VJ Sales tracks 62,000+ site visits with project, lead, CP, and sales person details.",
        table="gold.fact_lead_pipeline",
        category="sales",
    ),
    GlossaryEntry(
        term="conversion rate",
        definition="The percentage of leads that move from one pipeline stage to the next.",
        formula="COUNT(leads at stage N+1) / COUNT(leads at stage N) * 100",
        sql_hint="Use gold.fact_daily_funnel_snapshot for pre-calculated rates, "
                 "or calculate from gold.fact_lead_pipeline by comparing stage counts.",
        table="gold.fact_daily_funnel_snapshot",
        good_range="Inquiry→Visit: 30-50%, Visit→Booking: 15-30%, Booking→Agreement: 80-95%",
        category="sales",
    ),
    GlossaryEntry(
        term="channel partner",
        definition="External real estate broker (CP) who refers leads to VJ. "
                   "VJ Sales tracks 2,900+ CPs with company name, RERA number, and approval status. "
                   "Also known as broker. Channel partners have FOS (field officers) under them.",
        sql_hint="source_category = 'channel_partner' in gold.dim_lead_sources. "
                 "For CP-specific queries, join gold.dim_lead_sources on source_key.",
        table="gold.dim_lead_sources",
        category="sales",
    ),

    # ═══════════════════════════════════════════════
    # COLLECTIONS & FINANCE
    # ═══════════════════════════════════════════════
    GlossaryEntry(
        term="collection efficiency",
        definition="The ratio of total receipts collected to total invoices/demands raised, "
                   "expressed as a percentage. A key financial health metric for VJ.",
        formula="SUM(receipts) / SUM(invoices) * 100",
        sql_hint="Calculate: SUM(r.amount) from gold.fact_receipts r / "
                 "SUM(i.total_amount) from gold.fact_invoices i * 100, grouped by project.",
        good_range="80-100%",
        alert_threshold="< 70%",
        category="collections",
    ),
    GlossaryEntry(
        term="receipt",
        definition="A payment received from a customer. Tracked in Farvision's CRMG.DimReceipt. "
                   "Payment modes include: cheque, NEFT, RTGS, UPI, cash.",
        sql_hint="Use gold.fact_receipts. Join to dim_date for time filtering.",
        table="gold.fact_receipts",
        category="collections",
    ),
    GlossaryEntry(
        term="invoice",
        definition="A demand/invoice raised against a customer, usually linked to a payment schedule "
                   "or construction milestone. From Farvision's CRMG.DimInvoice.",
        sql_hint="Use gold.fact_invoices.",
        table="gold.fact_invoices",
        category="collections",
    ),
    GlossaryEntry(
        term="outstanding",
        definition="Amount billed but not yet collected. Tracked with aging buckets. "
                   "Farvision provides detailed aging: 15-day, 30-day, 60-day, 90-day, "
                   "120-day, 180-day, and 180+ day buckets.",
        formula="Bill Amount - Paid Amount = Due Amount",
        sql_hint="Use gold.snapshot_outstanding for detailed aging. "
                 "Columns: day_amt_15, day_amt_30, day_amt_60, day_amt_90, "
                 "day_amt_120, day_amt_180, day_amt_more_180.",
        table="gold.snapshot_outstanding",
        category="collections",
    ),
    GlossaryEntry(
        term="on account amount",
        definition="Advance payment received from customer that hasn't been adjusted against "
                   "a specific invoice/demand yet. Tracked in Farvision outstanding tables.",
        sql_hint="on_account_amount column in gold.snapshot_outstanding.",
        table="gold.snapshot_outstanding",
        category="collections",
    ),

    # ═══════════════════════════════════════════════
    # INVENTORY & PRICING
    # ═══════════════════════════════════════════════
    GlossaryEntry(
        term="available inventory",
        definition="Units that are currently unsold and available for purchase. "
                   "Pricing for available units comes from VJ Sales App's Inventory.totalCost "
                   "(NOT from Farvision, which only tracks sold units).",
        sql_hint="Use gold.snapshot_inventory WHERE inventory_status = 'Available'. "
                 "total_cost = total flat price, bsp = base selling price per sq ft.",
        table="gold.snapshot_inventory",
        category="sales",
    ),
    GlossaryEntry(
        term="rate",
        definition="Price per square foot (₹/sq ft). DIFFERENT from total price. "
                   "Example: Rate = ₹6,905/sq ft. To get total price: Rate × CarpetArea. "
                   "In Farvision FactUnitMovement, Value = total price (NOT rate).",
        sql_hint="For rate: use bsp from gold.snapshot_inventory (per sq ft). "
                 "For total price: use total_cost or net_basic_price.",
        category="sales",
    ),
    GlossaryEntry(
        term="carpet area",
        definition="Net usable floor area of a unit, excluding walls, balconies, and common areas. "
                   "Measured in square feet (sq. ft.). RERA-defined area. "
                   "IMPORTANT: CRM.UnitSummary does NOT reflect amended area post-booking. "
                   "Use FactUnitMovementDetail for accurate post-booking area.",
        table="gold.dim_units",
        category="general",
    ),
    GlossaryEntry(
        term="saleable area",
        definition="The total area used for pricing calculation, which may include balcony, "
                   "terrace, and other chargeable areas beyond carpet area.",
        table="gold.dim_units",
        category="general",
    ),

    # ═══════════════════════════════════════════════
    # PROJECTS
    # ═══════════════════════════════════════════════
    GlossaryEntry(
        term="project",
        definition="A real estate development by VJ. Projects are identified by BUId "
                   "(BusinessUnitId) in Farvision. Each project may have wings/towers.",
        table="gold.dim_projects",
        category="general",
    ),
    GlossaryEntry(
        term="RERA",
        definition="Real Estate Regulatory Authority. All projects must be registered with RERA. "
                   "The RERA number is stored in VJ Sales App's Projects table.",
        table="gold.dim_projects",
        category="general",
    ),
    GlossaryEntry(
        term="wing",
        definition="A building/tower within a project. Wings are tracked in VJ Sales App. "
                   "In Farvision, the project hierarchy (Level1-Level5) includes wing information.",
        category="general",
    ),

    # ═══════════════════════════════════════════════
    # REFERRALS & LOYALTY (VJOP)
    # ═══════════════════════════════════════════════
    GlossaryEntry(
        term="referral",
        definition="An existing VJ customer refers a new buyer through the VJOP portal. "
                   "Referral leads follow: Unclaimed → Claimed → Referral Sent → Site Visit Done → "
                   "Token Payment Complete → Allotment Payment Complete → Agreement Done.",
        sql_hint="Use gold.snapshot_referrals. Join on referrer_customer_key for the referrer.",
        table="gold.snapshot_referrals",
        category="referrals",
    ),
    GlossaryEntry(
        term="loyalty lead",
        definition="A lead where leadRelationship = 'Self' in VJOP — the customer is inquiring "
                   "for themselves, not referring someone else. Distinct from referral leads.",
        category="referrals",
    ),
    GlossaryEntry(
        term="referral points",
        definition="Reward points earned by customers for successful referrals. "
                   "type='credit' means earned, type='debit' means redeemed/paid out. "
                   "Only count status='success' or 'Success' for actual transactions.",
        formula="Points earned: SUM(points WHERE type='credit'). "
                "Points redeemed: SUM(points WHERE type='debit' AND status='success').",
        sql_hint="Use gold.snapshot_referrals for per-referral points. "
                 "points_earned and points_redeemed columns.",
        table="gold.snapshot_referrals",
        good_range="Varies by reward config",
        category="referrals",
    ),
    GlossaryEntry(
        term="reward type",
        definition="Type of reward in VJOP: 'initial_redeem_bonus' (welcome bonus), "
                   "'lead_agreement_done' (referral conversion reward), "
                   "'early_payment_reward' (early payment incentive), "
                   "'unit_bonus' (unit-specific bonus).",
        category="referrals",
    ),

    # ═══════════════════════════════════════════════
    # BROKERAGE
    # ═══════════════════════════════════════════════
    GlossaryEntry(
        term="brokerage",
        definition="Commission paid to channel partners/brokers for successful bookings. "
                   "Tracked in Farvision's CRMG.FactBrokerage with share percentages, "
                   "payable amounts, and release details.",
        table="gold.fact_bookings",
        category="sales",
    ),

    # ═══════════════════════════════════════════════
    # TIMESTAMP HANDLING
    # ═══════════════════════════════════════════════
    GlossaryEntry(
        term="vj sales timestamps",
        definition="VJ Sales App stores created_at and last_updated_at as epoch MILLISECONDS "
                   "(not seconds). Must divide by 1000 when converting: "
                   "to_timestamp(created_at / 1000). The ETL handles this conversion.",
        sql_hint="In the gold layer, all timestamps are already converted to proper TIMESTAMP. "
                 "No epoch conversion needed in gold queries.",
        category="general",
    ),
]


def get_glossary_dict() -> dict[str, GlossaryEntry]:
    """Return glossary as a dict keyed by term."""
    return {entry.term: entry for entry in GLOSSARY}


def find_relevant_terms(question: str) -> list[GlossaryEntry]:
    """Find glossary entries relevant to a question via keyword matching."""
    question_lower = question.lower()
    relevant = []
    for entry in GLOSSARY:
        term_lower = entry.term.lower()
        # Exact term match
        if term_lower in question_lower:
            relevant.append(entry)
            continue
        # Partial keyword match (for multi-word terms)
        term_words = [w for w in term_lower.split() if len(w) > 3]
        if term_words and any(w in question_lower for w in term_words):
            relevant.append(entry)
    return relevant


def override_glossary(base: list[GlossaryEntry], overrides: list[GlossaryEntry]) -> list[GlossaryEntry]:
    """Replace entries in base with matching overrides by term, append new ones."""
    override_map = {e.term.lower(): e for e in overrides}
    result = []
    for entry in base:
        if entry.term.lower() in override_map:
            result.append(override_map.pop(entry.term.lower()))
        else:
            result.append(entry)
    # Append any remaining overrides that weren't replacements
    result.extend(override_map.values())
    return result


def format_glossary_for_prompt(entries: list[GlossaryEntry]) -> str:
    """Format glossary entries for injection into LLM prompts."""
    if not entries:
        return ""

    lines = ["=== BUSINESS RULES & DEFINITIONS ==="]
    for entry in entries:
        lines.append(f"\n**{entry.term}**: {entry.definition}")
        if entry.formula:
            lines.append(f"  Formula: {entry.formula}")
        if entry.sql_hint:
            lines.append(f"  SQL hint: {entry.sql_hint}")
        if entry.good_range:
            lines.append(f"  Expected range: {entry.good_range}")
    return "\n".join(lines)
