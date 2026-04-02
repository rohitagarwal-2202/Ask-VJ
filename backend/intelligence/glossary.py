"""
Business Glossary — VJ-specific business terms, formulas, and domain knowledge.

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
    category: str = "general"            # sales, collections, operations, general


# The canonical business glossary for VJ
GLOSSARY: list[GlossaryEntry] = [
    # ── Sales & CRM ──
    GlossaryEntry(
        term="lead",
        definition="A potential customer who has shown interest in purchasing a property from VJ. "
                   "Leads enter the system via walk-ins, referrals, digital marketing, or channel partners.",
        table="gold.fact_lead_pipeline",
        category="sales",
    ),
    GlossaryEntry(
        term="pipeline stage",
        definition="The current status of a lead in the sales funnel. "
                   "Stages in order: inquiry → site_visit → negotiation → booking → agreement → registered. "
                   "A lead can also be marked as 'cancelled' at any point.",
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
        term="site visit to booking ratio",
        definition="Percentage of site visits that convert to bookings. A key sales efficiency metric.",
        formula="COUNT(bookings) / COUNT(site_visits) * 100",
        sql_hint="visit_to_booking_rate column in gold.fact_daily_funnel_snapshot",
        table="gold.fact_daily_funnel_snapshot",
        good_range="15-30%",
        category="sales",
    ),
    GlossaryEntry(
        term="booking",
        definition="When a lead commits to purchasing a unit by paying a booking amount. "
                   "A booking is not the same as a sale — it precedes the agreement and registration.",
        table="gold.fact_lead_pipeline",
        category="sales",
    ),
    GlossaryEntry(
        term="agreement value",
        definition="The total value of the property agreement in INR, as agreed between buyer and VJ. "
                   "This is the contract value, not the amount collected.",
        table="gold.fact_lead_pipeline",
        category="sales",
    ),
    GlossaryEntry(
        term="cancellation",
        definition="When a booked unit is cancelled by the customer. "
                   "Tracked with cancellation date and reason in the pipeline.",
        sql_hint="WHERE pipeline_stage = 'cancelled' in gold.fact_lead_pipeline",
        table="gold.fact_lead_pipeline",
        category="sales",
    ),
    GlossaryEntry(
        term="lead source",
        definition="Where a lead originated from. Categories: organic (walk-in), "
                   "paid (digital-fb, digital-google), referral, channel_partner.",
        table="gold.dim_lead_sources",
        category="sales",
    ),
    GlossaryEntry(
        term="channel partner",
        definition="External real estate broker or agent who refers leads to VJ. "
                   "Also known as CP. Channel partners earn brokerage on successful bookings.",
        sql_hint="source_category = 'channel_partner' in gold.dim_lead_sources",
        table="gold.dim_lead_sources",
        category="sales",
    ),
    GlossaryEntry(
        term="active lead",
        definition="A lead whose latest pipeline stage is NOT 'cancelled' or 'registered'. "
                   "These are leads still in the active sales funnel.",
        sql_hint="pipeline_stage NOT IN ('cancelled', 'registered') in gold.fact_lead_pipeline",
        table="gold.fact_lead_pipeline",
        category="sales",
    ),

    # ── Collections & Finance ──
    GlossaryEntry(
        term="collection efficiency",
        definition="The ratio of total amount collected (receipts) to total amount demanded, "
                   "expressed as a percentage. A key financial health metric.",
        formula="SUM(amount WHERE transaction_type='receipt') / "
                "SUM(amount WHERE transaction_type='demand') * 100",
        sql_hint="Calculate from gold.fact_collections: "
                 "SUM(CASE WHEN transaction_type='receipt' THEN amount ELSE 0 END) * 100.0 / "
                 "NULLIF(SUM(CASE WHEN transaction_type='demand' THEN amount ELSE 0 END), 0)",
        table="gold.fact_collections",
        good_range="80-100%",
        alert_threshold="< 70%",
        category="collections",
    ),
    GlossaryEntry(
        term="demand letter",
        definition="A formal request for payment sent to a customer, usually linked to a "
                   "construction milestone. The demanded amount becomes a receivable.",
        sql_hint="transaction_type = 'demand' in gold.fact_collections",
        table="gold.fact_collections",
        category="collections",
    ),
    GlossaryEntry(
        term="receipt",
        definition="A payment received from a customer. Can be via cheque, NEFT, RTGS, UPI, or cash.",
        sql_hint="transaction_type = 'receipt' in gold.fact_collections",
        table="gold.fact_collections",
        category="collections",
    ),
    GlossaryEntry(
        term="outstanding amount",
        definition="Total demanded minus total collected. The amount still owed by customers.",
        formula="SUM(demands) - SUM(receipts)",
        sql_hint="SUM(CASE WHEN transaction_type='demand' THEN amount ELSE 0 END) - "
                 "SUM(CASE WHEN transaction_type='receipt' THEN amount ELSE 0 END) "
                 "FROM gold.fact_collections",
        table="gold.fact_collections",
        category="collections",
    ),

    # ── Projects & Units ──
    GlossaryEntry(
        term="project",
        definition="A real estate development by VJ. Projects may have multiple phases. "
                   "Each project has a RERA registration number.",
        table="gold.dim_projects",
        category="general",
    ),
    GlossaryEntry(
        term="phase",
        definition="A sub-division of a project. Different phases may launch at different times "
                   "and have different pricing.",
        table="gold.dim_projects",
        category="general",
    ),
    GlossaryEntry(
        term="unit",
        definition="An individual flat, apartment, shop, or office within a project. "
                   "Identified by unit number, wing, and floor.",
        table="gold.dim_units",
        category="general",
    ),
    GlossaryEntry(
        term="carpet area",
        definition="The net usable floor area of a unit, excluding walls, balconies, and common areas. "
                   "Measured in square feet (sq. ft.). This is the RERA-defined area.",
        table="gold.dim_units",
        category="general",
    ),
    GlossaryEntry(
        term="RERA",
        definition="Real Estate Regulatory Authority. All projects must be registered with RERA. "
                   "The RERA number is a unique project identifier.",
        table="gold.dim_projects",
        category="general",
    ),

    # ── Time & Calendar ──
    GlossaryEntry(
        term="fiscal year",
        definition="VJ follows the Indian fiscal year: April to March. "
                   "FY2026 = April 2025 to March 2026. FY2027 = April 2026 to March 2027.",
        sql_hint="Use fiscal_year and fiscal_quarter columns in gold.dim_date. "
                 "fiscal_quarter: Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar.",
        table="gold.dim_date",
        category="general",
    ),
]


def get_glossary_dict() -> dict[str, GlossaryEntry]:
    """Return glossary as a dict keyed by term."""
    return {entry.term: entry for entry in GLOSSARY}


def find_relevant_terms(question: str) -> list[GlossaryEntry]:
    """Find glossary entries relevant to a question via simple keyword matching."""
    question_lower = question.lower()
    relevant = []
    for entry in GLOSSARY:
        # Check if the term or key words from definition appear in the question
        if entry.term.lower() in question_lower:
            relevant.append(entry)
        elif entry.formula and any(
            kw in question_lower
            for kw in entry.term.lower().split()
            if len(kw) > 3
        ):
            relevant.append(entry)
    return relevant


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
