"""
Ask VJ -- Warehouse Architecture PDF Generator
Run: python docs/generate_pdf.py
"""
from fpdf import FPDF
import os

NAVY = (30, 58, 95)
GOLD = (232, 168, 56)
GRAY_LIGHT = (240, 242, 245)
GRAY_TEXT = (100, 100, 100)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

class PDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(*GRAY_TEXT)
            self.cell(0, 5, "Ask VJ -- Warehouse Architecture Reference Manual", align="C")
            self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GRAY_TEXT)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def chapter_title(self, title):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*NAVY)
        self.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*GOLD)
        self.set_line_width(0.8)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(6)

    def section_title(self, title):
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*NAVY)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def subsection_title(self, title):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(60, 60, 60)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, text):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*BLACK)
        self.multi_cell(0, 5, text)
        self.ln(2)

    def code_block(self, text):
        self.set_font("Courier", "", 7)
        self.set_fill_color(*GRAY_LIGHT)
        self.set_text_color(30, 30, 30)
        x = self.get_x()
        w = self.w - self.l_margin - self.r_margin
        for line in text.split("\n"):
            if self.get_y() > 270:
                self.add_page()
            self.cell(w, 4, line, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.set_text_color(*BLACK)

    def table_header(self, cols, widths):
        self.set_font("Helvetica", "B", 8)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        for i, col in enumerate(cols):
            self.cell(widths[i], 6, col, border=1, fill=True, align="C")
        self.ln()
        self.set_text_color(*BLACK)

    def table_row(self, cells, widths, fill=False):
        self.set_font("Helvetica", "", 7.5)
        if fill:
            self.set_fill_color(*GRAY_LIGHT)
        else:
            self.set_fill_color(*WHITE)
        max_h = 5
        for i, cell in enumerate(cells):
            self.cell(widths[i], max_h, str(cell)[:50], border=1, fill=True)
        self.ln()

    def check_page_break(self, h=30):
        if self.get_y() + h > 270:
            self.add_page()

    def add_bronze_table(self, name, source, cols_data):
        """Add a bronze table definition."""
        self.check_page_break(40)
        self.subsection_title(f"Table: {name}")
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GRAY_TEXT)
        self.cell(0, 4, f"Source: {source}", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self.set_text_color(*BLACK)
        widths = [55, 35, 80]
        self.table_header(["Column", "Type", "Description"], widths)
        for i, (col, typ, desc) in enumerate(cols_data):
            self.table_row([col, typ, desc], widths, fill=(i % 2 == 0))

    def add_gold_table(self, name, grain, source, refresh, cols_data):
        """Add a gold table definition."""
        self.check_page_break(50)
        self.subsection_title(f"Table: {name}")
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GRAY_TEXT)
        self.cell(0, 4, f"Grain: {grain} | Source: {source} | Refresh: {refresh}", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self.set_text_color(*BLACK)
        widths = [45, 30, 95]
        self.table_header(["Column", "Type", "Description"], widths)
        for i, (col, typ, desc) in enumerate(cols_data):
            self.table_row([col, typ, desc], widths, fill=(i % 2 == 0))


def build_pdf():
    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ── COVER PAGE ──
    pdf.add_page()
    pdf.ln(60)
    pdf.set_font("Helvetica", "B", 32)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 15, "Ask VJ", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 18)
    pdf.set_text_color(*GRAY_TEXT)
    pdf.cell(0, 10, "Data Warehouse Architecture", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Technical Reference Manual", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_draw_color(*GOLD)
    pdf.set_line_width(1.5)
    pdf.line(60, pdf.get_y(), 150, pdf.get_y())
    pdf.ln(15)
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 7, "Version 1.0 | April 2026", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, "Vilas Javdekar (VJ) Developers", align="C", new_x="LMARGIN", new_y="NEXT")

    # ── TABLE OF CONTENTS ──
    pdf.add_page()
    pdf.chapter_title("Table of Contents")
    toc = [
        ("1", "Architecture Overview", "3"),
        ("2", "Bronze Layer -- Raw Staging (36 Tables)", "5"),
        ("3", "Silver Layer -- Entity Resolution", "18"),
        ("4", "Gold Layer -- Star Schema (15 Tables + 1 View)", "21"),
        ("5", "ETL Pipeline Orchestration", "32"),
        ("6", "Data Lineage Maps", "35"),
        ("7", "Business Rules Reference", "38"),
        ("8", "Cross-System Join Keys", "40"),
    ]
    for num, title, page in toc:
        pdf.set_font("Helvetica", "B" if num.isdigit() and int(num) < 9 else "", 10)
        pdf.cell(10, 7, num)
        pdf.cell(130, 7, title)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, page, align="R", new_x="LMARGIN", new_y="NEXT")

    print("Part 1/7 done: Cover + TOC")

    # ── CHAPTER 1: ARCHITECTURE OVERVIEW ──
    pdf.add_page()
    pdf.chapter_title("Chapter 1: Architecture Overview")

    pdf.section_title("1.1 Medallion Architecture")
    pdf.body_text(
        "Ask VJ uses a three-layer medallion architecture (Bronze > Silver > Gold) to unify "
        "customer, booking, and sales data from three independent source systems into a "
        "single business-ready data warehouse. An AI layer sits on top of Gold, generating "
        "SQL from natural language questions."
    )

    pdf.section_title("1.2 Source Systems")
    widths = [45, 35, 45, 45]
    pdf.table_header(["System", "Database", "Type", "Key Identifier"], widths)
    pdf.table_row(["Farvision ERP", "VJDLIVE45", "SQL Server", "TenantId = 75"], widths, True)
    pdf.table_row(["VJ Sales App", "PostgreSQL", "Supabase", "UUID IDs"], widths)
    pdf.table_row(["VJOP Portal", "RefferalAndLoyalty", "SQL Server", "INT IDs"], widths, True)

    pdf.ln(4)
    pdf.section_title("1.3 Universal Project Key: BUId")
    pdf.body_text(
        "BUId (BusinessUnitId) is the universal project identifier across all three systems:\n"
        "  - Farvision: ENGG.DimBusinessUnit.BusinessUnitId\n"
        "  - VJ Sales: Projects.buId\n"
        "  - VJOP: customer_bookings_units.BUId\n\n"
        "All cross-system project joins resolve through BUId via silver.project_crosswalk."
    )

    pdf.section_title("1.4 Cross-System Join Keys")
    widths = [40, 50, 50, 30]
    pdf.table_header(["Join Key", "Farvision Column", "Other System", "Confidence"], widths)
    pdf.table_row(["BookingId", "DimBookingMaster.BookingId", "VJ Sales: bookingId", "0.99"], widths, True)
    pdf.table_row(["", "", "VJOP: fv_booking_id", "0.99"], widths)
    pdf.table_row(["UnitId", "DimUnitMaster.UnitId", "VJ Sales: farvisionUnitId", "0.95"], widths, True)
    pdf.table_row(["", "", "VJOP: farvisionUnitId", "0.95"], widths)
    pdf.table_row(["BUId", "DimBusinessUnit.BusinessUnitId", "VJ Sales: buId", "1.00"], widths, True)
    pdf.table_row(["", "", "VJOP: BUId", "1.00"], widths)
    pdf.table_row(["LedgerId", "DimCustomerDetail.LedgerCustId", "VJOP: FV_LedgerID", "0.95"], widths, True)
    pdf.table_row(["LeadId", "(none)", "VJ Sales: leadId <> VJOP: sales_app_lead_id", "0.95"], widths)

    pdf.ln(4)
    pdf.section_title("1.5 Architecture Diagram")
    pdf.code_block(
        "SOURCE SYSTEMS           BRONZE              SILVER              GOLD               AI LAYER\n"
        "+----------------+     +----------+       +----------+       +----------+       +----------+\n"
        "| Farvision ERP  |---->| Raw      |------>| Entity   |------>| Star     |------>| LLM SQL  |\n"
        "| (SQL Server)   |     | Staging  |       | Resolution|      | Schema   |       | Generation|\n"
        "+----------------+     | 16 tables|       |          |       | 7 dims   |       |          |\n"
        "| VJ Sales App   |---->|          |       | ID-based |       | 4 facts  |       | Natural  |\n"
        "| (PostgreSQL)   |     | 13 tables|       | Matching |       | 3 snaps  |       | Language |\n"
        "+----------------+     |          |       |          |       | 1 view   |       | Answers  |\n"
        "| VJOP Portal    |---->| 7 tables |       | Fuzzy    |       |          |       |          |\n"
        "| (SQL Server)   |     |          |       | Fallback |       |          |       |          |\n"
        "+----------------+     +----------+       +----------+       +----------+       +----------+"
    )

    print("Part 2/7 done: Architecture Overview")
    return pdf

pdf = build_pdf()
pdf.output("/tmp/ask-vj-part1.pdf")
print("Part 1-2 saved to /tmp/ask-vj-part1.pdf")

def add_bronze_chapter(pdf):
    """Chapter 2: Bronze Layer"""
    pdf.add_page()
    pdf.chapter_title("Chapter 2: Bronze Layer -- Raw Staging")
    pdf.body_text(
        "The Bronze layer contains 36 staging tables: 16 from Farvision ERP, 13 from VJ Sales App, "
        "and 7 from VJOP. All tables are append-only with audit metadata: _sync_id (BIGSERIAL), "
        "_synced_at (TIMESTAMPTZ), _source_system (VARCHAR), _batch_id (UUID). No transformations "
        "are applied -- data is preserved exactly as received from source systems."
    )

    # ── FARVISION TABLES ──
    pdf.section_title("2.1 Farvision ERP (16 Tables)")
    pdf.body_text("All Farvision queries include WHERE TenantId = 75. Column names are PascalCase (quoted).")

    pdf.add_bronze_table("bronze.stg_fv_dim_booking_master", "CRMG.DimBookingMaster", [
        ("BookingId", "INT PK", "Booking identifier"),
        ("LedgerId", "INT", "Customer ledger ID (financial)"),
        ("FiscalYearId", "INT", "56=FY2025-26, 52=FY2024-25"),
        ("BUId", "INT", "Universal project key"),
        ("BookingDate", "DATE", "When booking was made"),
        ("BookingNo", "VARCHAR", "Booking reference number"),
        ("PrimaryUnitId", "INT", "Main unit in booking"),
        ("CustomerName", "VARCHAR", "Customer display name"),
        ("NetBasicPrice", "DECIMAL", "Base price before taxes"),
        ("SalesPersonId", "INT", "Sales person reference"),
        ("SalesPersonName", "VARCHAR", "Sales person name"),
        ("IsCancelled", "BOOLEAN", "0=active, 1=cancelled"),
        ("DiscountPercentage", "DECIMAL", "Discount applied"),
        ("AllotmentDate", "DATE", "Unit allotment date"),
        ("AgreementDate", "DATE", "Agreement signing date"),
        ("AgreementNo", "VARCHAR", "Agreement reference"),
        ("RegistrationDate", "DATE", "Legal registration date"),
        ("RegistrationNo", "VARCHAR", "Registration reference"),
    ])

    pdf.add_bronze_table("bronze.stg_fv_fact_unit_movement", "CRMG.FactUnitMovement", [
        ("UnitId", "INT", "Unit identifier"),
        ("UnitStatus", "INT", "1=Sold, 2=Available, 3=Blocked"),
        ("BUId", "INT", "Project key"),
        ("TypologyId", "INT", "Unit type (1BHK, 2BHK, etc)"),
        ("Area", "DECIMAL", "Saleable area"),
        ("CarpetArea", "DECIMAL", "Net usable area"),
        ("BookingId", "INT", "Linked booking"),
        ("Value", "DECIMAL", "Total unit value"),
    ])

    pdf.add_bronze_table("bronze.stg_fv_dim_unit_master", "CRMG.DimUnitMaster", [
        ("UnitId", "INT PK", "Unit identifier"),
        ("UnitCode", "VARCHAR", "Unit code/number"),
        ("BUId", "INT", "Project key"),
        ("TypologyId", "INT", "Unit type reference"),
        ("FloorId", "INT", "Floor reference"),
    ])

    pdf.add_bronze_table("bronze.stg_fv_dim_typology_master", "CRMG.DimTypologyMaster", [
        ("TypologyId", "INT PK", "Typology identifier"),
        ("TypologyCode", "VARCHAR", "Code e.g. 3BHK-XL"),
        ("Typology", "VARCHAR", "Name e.g. 3.00BHK"),
    ])

    pdf.add_bronze_table("bronze.stg_fv_dim_receipt", "CRMG.DimReceipt", [
        ("RecieptId", "INT PK", "Receipt ID (sic spelling)"),
        ("BookingId", "INT", "Linked booking"),
        ("AmountLCY", "DECIMAL", "Amount in local currency"),
        ("PaymentMode", "VARCHAR", "Cheque/NEFT/RTGS/Cash"),
        ("InstrumentNo", "VARCHAR", "Cheque/NEFT reference"),
        ("DocumentNo", "VARCHAR", "Document reference"),
        ("DocumentDate", "DATE", "Payment date"),
        ("LedgerId", "INT", "Customer ledger"),
    ])

    pdf.add_bronze_table("bronze.stg_fv_dim_invoice", "CRMG.DimInvoice", [
        ("InvoiceId", "INT PK", "Invoice identifier"),
        ("BookingId", "INT", "Linked booking"),
        ("BasicAmount", "DECIMAL", "Base invoice amount"),
        ("AmountLCY", "DECIMAL", "Total invoice amount"),
        ("DocumentDate", "DATE", "Invoice date"),
    ])

    pdf.add_bronze_table("bronze.stg_fv_fact_duedate_outstanding", "CRMG.FactDueDatewiseOutstanding", [
        ("LedgerId", "INT", "Customer ledger"),
        ("CustomerName", "VARCHAR", "Customer name"),
        ("UnitNo", "VARCHAR", "Unit number"),
        ("Bill_Amount", "DECIMAL", "Total billed"),
        ("Paid_Amount", "DECIMAL", "Total paid"),
        ("Due_Amount", "DECIMAL", "Outstanding due"),
        ("OverdueDays", "INT", "Days overdue"),
        ("DayAmt_15 to DayAmt_More180", "DECIMAL", "7 aging buckets"),
        ("BuId", "INT", "Project key"),
    ])

    pdf.add_bronze_table("bronze.stg_fv_dim_customer_detail", "CRMG.DimCustomerDetail", [
        ("LedgerCustId", "INT PK", "Customer/ledger ID"),
        ("Customer", "VARCHAR", "Display name"),
        ("FullName", "VARCHAR", "Full legal name"),
        ("MobileNo", "VARCHAR", "Mobile number"),
        ("EmailId", "VARCHAR", "Email address"),
        ("PanNo", "VARCHAR", "PAN number"),
    ])

    pdf.add_bronze_table("bronze.stg_fv_dim_business_unit", "ENGG.DimBusinessUnit", [
        ("BusinessUnitId", "INT PK", "Universal project key (BUId)"),
        ("BusinessUnit", "VARCHAR", "Project name"),
        ("BusinessUnitType", "VARCHAR", "Type classification"),
        ("SegmentId", "INT", "Segment reference"),
    ])

    # ── VJ SALES TABLES ──
    pdf.section_title("2.2 VJ Sales App (13 Tables)")
    pdf.body_text("Timestamps are EPOCH MILLISECONDS (BIGINT). IDs are UUIDs. JSONB preserved as-is.")

    pdf.add_bronze_table("bronze.stg_vj_projects", '"Projects"', [
        ("projectId", "UUID PK", "Project identifier"),
        ("projectName", "VARCHAR", "Project name"),
        ("buId", "INT", "Maps to Farvision BUId"),
        ("reraNumber", "VARCHAR", "RERA registration"),
        ("isCompleted", "BOOLEAN", "Project completed flag"),
    ])

    pdf.add_bronze_table("bronze.stg_vj_inventory", '"Inventory"', [
        ("unitId", "UUID PK", "Unit identifier"),
        ("projectId", "UUID", "Project reference"),
        ("farvisionUnitId", "INT", "Cross-system key to Farvision"),
        ("totalCost", "DECIMAL", "Total flat price"),
        ("BSP", "DECIMAL", "Base selling price/sqft"),
        ("saleableArea", "DECIMAL", "Saleable area"),
        ("inventoryStatusId", "INT", "Status lookup"),
    ])

    pdf.add_bronze_table("bronze.stg_vj_leads", '"Leads"', [
        ("leadId", "UUID PK", "Lead identifier"),
        ("personId", "UUID", "Person reference"),
        ("cpId", "UUID", "Channel partner ref"),
        ("leadType", "VARCHAR", "walk-in/referral/digital"),
        ("created_at", "BIGINT", "Epoch milliseconds"),
    ])

    pdf.add_bronze_table("bronze.stg_vj_allotment_payment", '"AllotmentPayment"', [
        ("allotmentPaymentId", "UUID PK", "Allotment identifier"),
        ("leadId", "UUID", "Lead reference"),
        ("unitId", "UUID", "Unit reference"),
        ("bookingId", "INT", "Cross-system key to Farvision"),
        ("status", "VARCHAR", "Payment Complete/Agreement Done"),
        ("paidAmount", "DECIMAL", "Amount paid"),
        ("bookingAmt", "JSONB", "Booking amount details"),
        ("unitCost", "JSONB", "Unit cost details"),
    ])

    pdf.add_bronze_table("bronze.stg_vj_person", '"Person"', [
        ("personId", "UUID PK", "Person identifier"),
        ("name", "VARCHAR", "Full name"),
        ("contactNumber", "VARCHAR", "Phone number"),
        ("email", "VARCHAR", "Email address"),
    ])

    # ── VJOP TABLES ──
    pdf.section_title("2.3 VJOP Referral & Loyalty (7 Tables)")

    pdf.add_bronze_table("bronze.stg_rnl_customers", "dbo.customers", [
        ("id", "INT PK", "VJOP customer ID"),
        ("name", "VARCHAR", "Customer name"),
        ("mobile", "VARCHAR", "Mobile number"),
        ("FV_LedgerID", "INT", "Cross-system key to Farvision LedgerId"),
        ("PAN", "VARCHAR", "PAN number"),
    ])

    pdf.add_bronze_table("bronze.stg_rnl_customer_bookings_units", "dbo.customer_bookings_units", [
        ("id", "INT PK", "Record ID"),
        ("customer_id", "INT", "VJOP customer ref"),
        ("fv_booking_id", "INT", "Cross-system key to Farvision BookingId"),
        ("BUId", "INT", "Cross-system key to Farvision BUId"),
        ("project", "VARCHAR", "Project name"),
    ])

    pdf.add_bronze_table("bronze.stg_rnl_leads", "dbo.leads", [
        ("id", "INT PK", "VJOP lead ID"),
        ("name", "VARCHAR", "Lead name"),
        ("sales_app_lead_id", "UUID", "Cross-system key to VJ Sales leadId"),
        ("referred_by", "INT", "Referrer customer ID"),
        ("status", "VARCHAR", "Referral status"),
        ("booking_id", "INT", "Booking reference"),
    ])

    print("Part 3/7 done: Bronze Layer")
    return pdf

pdf = build_pdf()
add_bronze_chapter(pdf)
pdf.output("/tmp/ask-vj-part3.pdf")
print("Parts 1-3 saved")

def add_silver_chapter(pdf):
    """Chapter 3: Silver Layer"""
    pdf.add_page()
    pdf.chapter_title("Chapter 3: Silver Layer -- Entity Resolution")
    pdf.body_text(
        "The Silver layer resolves cross-system identities using shared IDs. "
        "ID-based matching is the PRIMARY strategy. Fuzzy matching (pg_trgm) is "
        "only used as a fallback for unconverted leads with no BookingId/UnitId."
    )

    pdf.section_title("3.1 silver.project_crosswalk")
    pdf.body_text("Maps BUId (universal project key) to project names across all 3 systems.")
    widths = [50, 30, 90]
    pdf.table_header(["Column", "Type", "Description"], widths)
    for i, r in enumerate([
        ("crosswalk_id", "SERIAL PK", "Auto-increment ID"),
        ("canonical_name", "VARCHAR", "Unified project name for Gold"),
        ("farvision_bu_id", "INT UNIQUE", "Farvision BusinessUnitId (universal key)"),
        ("vjsales_project_name", "VARCHAR", "Name from VJ Sales Projects table"),
        ("vjop_project_name", "VARCHAR", "Name from VJOP customer_bookings_units"),
        ("phase_name", "VARCHAR", "Phase within project"),
    ]):
        pdf.table_row(r, widths, i % 2 == 0)

    pdf.ln(4)
    pdf.section_title("3.2 silver.entity_map")
    pdf.body_text("Links customer/booking identities across systems. Each row = one resolved identity.")
    widths = [50, 30, 90]
    pdf.table_header(["Column", "Type", "Description"], widths)
    for i, r in enumerate([
        ("entity_map_id", "SERIAL PK", "Auto-increment ID"),
        ("unified_customer_id", "UUID", "System-generated unified ID"),
        ("farvision_booking_id", "INT UNIQUE", "DimBookingMaster.BookingId"),
        ("farvision_unit_id", "INT", "DimUnitMaster.UnitId"),
        ("farvision_bu_id", "INT", "DimBusinessUnit.BusinessUnitId"),
        ("farvision_ledger_id", "INT", "DimCustomerDetail.LedgerCustId"),
        ("vjsales_lead_id", "UUID UNIQUE", "Leads.leadId"),
        ("vjsales_allotment_id", "UUID UNIQUE", "AllotmentPayment.allotmentPaymentId"),
        ("vjsales_unit_id", "UUID", "Inventory.unitId"),
        ("vjop_customer_id", "INT", "customers.id"),
        ("vjop_lead_id", "INT", "leads.id"),
        ("match_method", "VARCHAR", "booking_id_exact/unit_id_exact/lead_id_exact/fuzzy"),
        ("match_confidence", "DECIMAL", "0.00-1.00 (0.99 for booking match)"),
    ]):
        pdf.table_row(r, widths, i % 2 == 0)

    pdf.ln(4)
    pdf.section_title("3.3 Resolution Strategy (Priority Order)")
    pdf.code_block(
        "Strategy 1: BookingId Exact Match (confidence: 0.99)\n"
        "  Farvision BookingId <-> VJ Sales bookingId <-> VJOP fv_booking_id\n"
        "  JOIN: stg_fv_dim_booking_master.BookingId = stg_vj_allotment_payment.bookingId\n"
        "        stg_fv_dim_booking_master.BookingId = stg_rnl_customer_bookings_units.fv_booking_id\n\n"
        "Strategy 2: UnitId Exact Match (confidence: 0.95)\n"
        "  Farvision UnitId <-> VJ Sales farvisionUnitId\n"
        "  JOIN: stg_vj_inventory.farvisionUnitId = (Farvision UnitId)\n\n"
        "Strategy 3: LeadId Exact Match (confidence: 0.95)\n"
        "  VJ Sales leadId <-> VJOP sales_app_lead_id\n"
        "  JOIN: stg_rnl_leads.sales_app_lead_id = stg_vj_leads.leadId\n\n"
        "Strategy 4: Fuzzy Fallback (queue only)\n"
        "  For unconverted leads with no BookingId/UnitId\n"
        "  Queued in silver.entity_resolution_queue for manual review"
    )
    print("Part 4/7 done: Silver Layer")
    return pdf


def add_gold_chapter(pdf):
    """Chapter 4: Gold Layer"""
    pdf.add_page()
    pdf.chapter_title("Chapter 4: Gold Layer -- Star Schema")
    pdf.body_text(
        "The Gold layer provides business-ready tables optimized for LLM SQL generation. "
        "7 dimension tables, 4 append-only fact tables, 3 daily snapshot tables, "
        "and 1 computed view. All use surrogate keys for simple JOINs."
    )

    # DIMENSIONS
    pdf.section_title("4.1 Dimension Tables")

    pdf.add_gold_table("gold.dim_date", "One row per date", "Generated (2015-2035)", "One-time", [
        ("date_key", "INT PK", "YYYYMMDD format"),
        ("full_date", "DATE", "Actual date value"),
        ("fiscal_quarter", "VARCHAR", "Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar"),
        ("fiscal_year", "INT", "Indian FY (2026 = Apr 2025 - Mar 2026)"),
        ("fiscal_year_id", "INT", "Farvision ID: 56=FY2025-26, 52=FY2024-25"),
        ("is_weekend", "BOOLEAN", "Saturday or Sunday"),
    ])

    pdf.add_gold_table("gold.dim_projects", "One row per project", "silver.project_crosswalk", "Upsert on bu_id", [
        ("project_key", "SERIAL PK", "Surrogate key"),
        ("bu_id", "INT UNIQUE", "Farvision BusinessUnitId (universal)"),
        ("project_name", "VARCHAR", "Canonical project name"),
        ("phase_name", "VARCHAR", "Phase within project"),
        ("segment", "VARCHAR", "Residential/Commercial"),
        ("status", "VARCHAR", "active/completed/upcoming"),
    ])

    pdf.add_gold_table("gold.dim_typologies", "One row per typology variant", "stg_fv_dim_typology_master", "Upsert", [
        ("typology_key", "SERIAL PK", "Surrogate key"),
        ("typology_id", "INT", "Farvision TypologyId"),
        ("display_name", "VARCHAR", "Human-friendly: 3 BHK"),
        ("is_base_variant", "BOOLEAN", "true=base, false=XL/XR"),
    ])

    pdf.add_gold_table("gold.dim_units", "One row per unit", "stg_fv_dim_unit_master + FactUnitMovement", "Upsert", [
        ("unit_key", "SERIAL PK", "Surrogate key"),
        ("farvision_unit_id", "INT UNIQUE", "Farvision UnitId"),
        ("project_key", "INT FK", "-> dim_projects"),
        ("typology_key", "INT FK", "-> dim_typologies"),
        ("unit_no", "VARCHAR", "Unit number e.g. A-501"),
        ("unit_status", "INT", "1=sold, 2=available, 3=blocked"),
        ("carpet_area", "DECIMAL", "Net usable area sqft"),
        ("saleable_area", "DECIMAL", "Total saleable area"),
    ])

    pdf.add_gold_table("gold.dim_customers", "One row per customer", "stg_fv_dim_customer_detail + entity_map", "Insert", [
        ("customer_key", "SERIAL PK", "Surrogate key"),
        ("unified_customer_id", "UUID UNIQUE", "From silver.entity_map"),
        ("farvision_ledger_id", "INT", "Farvision LedgerCustId"),
        ("full_name", "VARCHAR", "Legal name from Farvision"),
        ("mobile", "VARCHAR", "Mobile number"),
        ("email", "VARCHAR", "Email address"),
        ("pan_number", "VARCHAR", "PAN number"),
    ])

    pdf.add_gold_table("gold.dim_sales_persons", "One row per sales person", "stg_fv_dim_booking_master", "Upsert", [
        ("sales_person_key", "SERIAL PK", "Surrogate key"),
        ("farvision_sales_person_id", "INT UNIQUE", "Farvision SalesPersonId"),
        ("name", "VARCHAR", "Sales person name"),
    ])

    pdf.add_gold_table("gold.dim_lead_sources", "One row per source", "stg_vj_leads + stg_vj_cp", "Upsert", [
        ("source_key", "SERIAL PK", "Surrogate key"),
        ("source_name", "VARCHAR UNIQUE", "walk-in/referral/digital-fb/CP-Name"),
        ("source_category", "VARCHAR", "organic/paid/referral/channel_partner"),
        ("cp_id", "UUID", "Channel partner UUID (if applicable)"),
    ])

    # FACTS
    pdf.section_title("4.2 Fact Tables (Append-Only / Upsert)")

    pdf.add_gold_table("gold.fact_bookings", "One row per booking", "stg_fv_dim_booking_master", "Upsert on farvision_booking_id", [
        ("booking_key", "SERIAL PK", "Surrogate key"),
        ("farvision_booking_id", "INT UNIQUE", "Farvision BookingId"),
        ("booking_date", "DATE", "Booking date"),
        ("customer_key", "INT FK", "-> dim_customers (via entity_map)"),
        ("project_key", "INT FK", "-> dim_projects (via BUId)"),
        ("unit_key", "INT FK", "-> dim_units (via PrimaryUnitId)"),
        ("typology_key", "INT FK", "-> dim_typologies (via FactUnitMovement)"),
        ("net_basic_price", "DECIMAL", "Base price before taxes"),
        ("agreement_value", "DECIMAL", "Total agreement value"),
        ("is_cancelled", "BOOLEAN", "false=active, true=cancelled"),
        ("cancellation_date", "DATE", "From DimBookingCancellation"),
        ("agreement_date", "DATE", "From DimUnitAgreement"),
        ("registration_date", "DATE", "From DimUnitAgreement"),
        ("broker_id", "INT", "From FactSalesDetailWise"),
        ("fiscal_year_id", "INT", "56=FY2025-26"),
    ])

    pdf.add_gold_table("gold.fact_receipts", "One row per payment", "stg_fv_dim_receipt", "Upsert on farvision_receipt_id", [
        ("receipt_key", "SERIAL PK", "Surrogate key"),
        ("farvision_receipt_id", "INT UNIQUE", "Farvision RecieptId (sic)"),
        ("booking_key", "INT FK", "-> fact_bookings (via BookingId)"),
        ("amount", "DECIMAL", "Payment amount"),
        ("payment_mode", "VARCHAR", "Cheque/NEFT/RTGS/Cash"),
        ("date_key", "INT FK", "-> dim_date (from DocumentDate)"),
    ])

    pdf.add_gold_table("gold.fact_invoices", "One row per invoice", "stg_fv_dim_invoice", "Upsert on farvision_invoice_id", [
        ("invoice_key", "SERIAL PK", "Surrogate key"),
        ("farvision_invoice_id", "INT UNIQUE", "Farvision InvoiceId"),
        ("booking_key", "INT FK", "-> fact_bookings (via BookingId)"),
        ("basic_amount", "DECIMAL", "Base invoice amount"),
        ("total_amount", "DECIMAL", "Total with taxes"),
        ("due_date", "DATE", "Payment due date"),
    ])

    pdf.add_gold_table("gold.fact_lead_pipeline", "One row per stage change", "stg_vj_leads/visits/allotments", "Append-only", [
        ("pipeline_event_id", "SERIAL PK", "Surrogate key"),
        ("vjsales_lead_id", "UUID", "VJ Sales lead UUID"),
        ("pipeline_stage", "VARCHAR", "inquiry/site_visit/booking/agreement/cancelled"),
        ("allotment_status", "VARCHAR", "Payment Complete/Agreement Done/etc"),
        ("event_date_key", "INT FK", "-> dim_date"),
        ("project_key", "INT FK", "-> dim_projects (via buId)"),
    ])

    # SNAPSHOTS
    pdf.section_title("4.3 Snapshot Tables (Daily Refresh)")

    pdf.add_gold_table("gold.snapshot_outstanding", "One row per (customer, unit, due_date)", "stg_fv_fact_duedate_outstanding", "DELETE+INSERT daily", [
        ("snapshot_date", "DATE", "Snapshot date (CURRENT_DATE)"),
        ("customer_name", "VARCHAR", "Denormalized for fast queries"),
        ("bill_amount", "DECIMAL", "Total billed"),
        ("paid_amount", "DECIMAL", "Total paid"),
        ("due_amount", "DECIMAL", "Outstanding balance"),
        ("overdue_days", "INT", "Days past due"),
        ("day_amt_15..more_180", "DECIMAL", "7 aging buckets"),
    ])

    pdf.add_gold_table("gold.snapshot_inventory", "One row per unit", "stg_vj_inventory", "DELETE+INSERT daily", [
        ("snapshot_date", "DATE", "Snapshot date"),
        ("inventory_status", "VARCHAR", "Available/On Hold/Sold"),
        ("total_cost", "DECIMAL", "Total flat price"),
        ("bsp", "DECIMAL", "Base selling price per sqft"),
        ("saleable_area", "DECIMAL", "Saleable area"),
    ])

    pdf.add_gold_table("gold.snapshot_referrals", "One row per referral lead", "stg_rnl_leads + allotments + points", "DELETE+INSERT daily", [
        ("snapshot_date", "DATE", "Snapshot date"),
        ("referrer_customer_key", "INT FK", "-> dim_customers (who referred)"),
        ("referred_lead_name", "VARCHAR", "Name of referred person"),
        ("referral_status", "VARCHAR", "Unclaimed/Claimed/Site Visit Done/Agreement Done"),
        ("booking_id", "INT", "From lead_allotments (NOT leads)"),
        ("points_earned", "DECIMAL", "Loyalty points earned"),
        ("points_redeemed", "DECIMAL", "Loyalty points redeemed"),
    ])

    pdf.section_title("4.4 View: gold.v_conversion_rates")
    pdf.body_text("Derived conversion metrics computed on-the-fly from fact_daily_funnel_snapshot. "
                  "Not stored (Medallion principle: no derived metrics in facts).")
    pdf.code_block(
        "inquiry_to_visit_rate  = total_site_visits / total_inquiries * 100\n"
        "visit_to_booking_rate  = total_bookings / total_site_visits * 100\n"
        "booking_to_agreement_rate = total_agreements / total_bookings * 100"
    )

    print("Part 5/7 done: Gold Layer")
    return pdf


def add_etl_lineage_rules(pdf):
    """Chapters 5-7: ETL, Lineage, Business Rules"""
    # ── CHAPTER 5: ETL PIPELINE ──
    pdf.add_page()
    pdf.chapter_title("Chapter 5: ETL Pipeline Orchestration")
    pdf.body_text("Pipeline runs every 2 hours via cron. Execution: python -m backend.etl.run_pipeline")

    pdf.section_title("5.1 Pipeline Stages")
    pdf.code_block(
        "Stage 1: EXTRACT (Bronze)\n"
        "  - Farvision: 16 full-load queries (TenantId=75)\n"
        "  - VJ Sales: 12 incremental queries (watermark on timestamp)\n"
        "  - VJOP: 6 incremental queries (watermark on created_at)\n\n"
        "Stage 2: RESOLVE (Silver)\n"
        "  - Auto-discover projects from stg_fv_dim_business_unit\n"
        "  - Match VJ Sales projects via buId\n"
        "  - Run entity resolution: BookingId -> UnitId -> LeadId -> Fuzzy queue\n\n"
        "Stage 2.5: PRE-GOLD QUALITY GATE\n"
        "  - Check silver.project_crosswalk is populated\n"
        "  - If errors: BLOCK Gold transforms, return early\n\n"
        "Stage 3: TRANSFORM (Gold)\n"
        "  - Build 7 dimensions (in dependency order)\n"
        "  - Build 4 facts + 3 snapshots\n"
        "  - Build daily funnel snapshot\n\n"
        "Stage 4: POST-GOLD VALIDATE\n"
        "  - Orphan record detection\n"
        "  - Null/negative checks\n"
        "  - Entity resolution coverage\n"
        "  - Booking completeness"
    )

    pdf.section_title("5.2 Dimension Build Order (Dependencies)")
    pdf.code_block(
        "1. dim_date         (independent - generated)\n"
        "2. dim_projects     (reads: silver.project_crosswalk)\n"
        "3. dim_typologies   (reads: stg_fv_dim_typology_master)\n"
        "4. dim_units        (REQUIRES: dim_projects, dim_typologies)\n"
        "5. dim_customers    (reads: stg_fv_dim_customer_detail)\n"
        "6. dim_sales_persons (reads: stg_fv_dim_booking_master)\n"
        "7. dim_lead_sources (reads: stg_vj_leads + stg_vj_cp)"
    )

    # ── CHAPTER 6: DATA LINEAGE ──
    pdf.add_page()
    pdf.chapter_title("Chapter 6: Data Lineage Maps")

    pdf.section_title("6.1 Booking Lineage")
    pdf.code_block(
        "Farvision CRMG.DimBookingMaster\n"
        "  -> bronze.stg_fv_dim_booking_master (raw copy)\n"
        "    -> silver.entity_map (matched on BookingId, confidence 0.99)\n"
        "      -> gold.fact_bookings (via farvision_booking_id)\n"
        "        -> gold.fact_receipts (via booking_key FK)\n"
        "        -> gold.fact_invoices (via booking_key FK)\n\n"
        "Agreement/Registration dates come from:\n"
        "  stg_fv_dim_unit_agreement (LATERAL join on BookingId)\n\n"
        "Cancellation date comes from:\n"
        "  stg_fv_dim_booking_cancellation (LATERAL join on BookingId)\n\n"
        "Broker ID comes from:\n"
        "  stg_fv_fact_sales_detail_wise (LATERAL join on BookingId)"
    )

    pdf.section_title("6.2 Customer Lineage")
    pdf.code_block(
        "Farvision CRMG.DimCustomerDetail\n"
        "  -> bronze.stg_fv_dim_customer_detail\n"
        "    -> gold.dim_customers (LedgerCustId -> farvision_ledger_id)\n\n"
        "VJ Sales 'Person' + 'Leads'\n"
        "  -> bronze.stg_vj_person + stg_vj_leads\n"
        "    -> silver.entity_map (vjsales_lead_id)\n"
        "      -> gold.dim_customers (unified_customer_id)\n\n"
        "VJOP dbo.customers\n"
        "  -> bronze.stg_rnl_customers\n"
        "    -> silver.entity_map (FV_LedgerID -> farvision_ledger_id)"
    )

    pdf.section_title("6.3 Inventory Lineage")
    pdf.code_block(
        "VJ Sales 'Inventory'\n"
        "  -> bronze.stg_vj_inventory\n"
        "    -> gold.snapshot_inventory (farvisionUnitId -> dim_units)\n"
        "    -> gold.dim_units (farvisionUnitId -> farvision_unit_id)\n\n"
        "Farvision CRMG.DimUnitMaster + FactUnitMovement\n"
        "  -> bronze.stg_fv_dim_unit_master + stg_fv_fact_unit_movement\n"
        "    -> gold.dim_units (UnitId -> farvision_unit_id)\n"
        "    Unit status (1=sold/2=available/3=blocked) from FactUnitMovement"
    )

    pdf.section_title("6.4 Outstanding Lineage")
    pdf.code_block(
        "Farvision CRMG.FactDueDatewiseOutstanding\n"
        "  -> bronze.stg_fv_fact_duedate_outstanding\n"
        "    -> gold.snapshot_outstanding (BuId -> dim_projects.bu_id)\n"
        "    7 aging buckets: DayAmt_15 through DayAmt_More180"
    )

    pdf.section_title("6.5 Referral Lineage")
    pdf.code_block(
        "VJOP dbo.leads\n"
        "  -> bronze.stg_rnl_leads\n"
        "    -> gold.snapshot_referrals\n"
        "      Referrer: referred_by -> stg_rnl_customers -> FV_LedgerID -> dim_customers\n"
        "      Booking: LATERAL stg_rnl_lead_allotments.booking_id\n"
        "      Points: LATERAL SUM(stg_rnl_points_history.points) credit/debit"
    )

    # ── CHAPTER 7: BUSINESS RULES ──
    pdf.add_page()
    pdf.chapter_title("Chapter 7: Business Rules Reference")

    pdf.section_title("7.1 Indian Fiscal Year")
    pdf.body_text("April-March cycle. FY2026 = April 2025 to March 2026.\n"
                  "Fiscal quarters: Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar.\n"
                  "FiscalYearId mapping: 56 = FY2025-26, 52 = FY2024-25.")

    pdf.section_title("7.2 Unit Status Codes")
    widths = [30, 50, 90]
    pdf.table_header(["Code", "Status", "Description"], widths)
    pdf.table_row(["1", "Sold", "Unit has been booked/sold"], widths, True)
    pdf.table_row(["2", "Available", "Unit is available for sale"], widths)
    pdf.table_row(["3", "Blocked", "Unit is reserved/blocked"], widths, True)

    pdf.section_title("7.3 Typology Classification")
    pdf.body_text("is_base_variant = true for base types (1BHK, 2BHK, 3BHK).\n"
                  "is_base_variant = false for variants (3BHK XL, 3BHK XR, DUPLEX, PENTHOUSE).\n"
                  "For '3 BHK' queries: use WHERE is_base_variant = true AND display_name LIKE '3 BHK%'.")

    pdf.section_title("7.4 Pipeline Stages (VJ Sales)")
    pdf.body_text("inquiry -> site_visit -> negotiation -> booking -> agreement -> registered | cancelled")

    pdf.section_title("7.5 Allotment Status Values")
    pdf.body_text("Payment Pending, Partial Payment Done, Payment Complete, Booked, "
                  "Agreement Done, Cancelled, Refund Initiated, Refund Processed.")

    pdf.section_title("7.6 Aging Buckets (Outstanding)")
    widths = [40, 50, 80]
    pdf.table_header(["Column", "Range", "Description"], widths)
    for i, r in enumerate([
        ("day_amt_15", "0-15 days", "Recently overdue"),
        ("day_amt_30", "16-30 days", "One month overdue"),
        ("day_amt_60", "31-60 days", "Two months overdue"),
        ("day_amt_90", "61-90 days", "Three months overdue"),
        ("day_amt_120", "91-120 days", "Four months overdue"),
        ("day_amt_180", "121-180 days", "Six months overdue"),
        ("day_amt_more_180", ">180 days", "Severely overdue"),
    ]):
        pdf.table_row(r, widths, i % 2 == 0)

    pdf.section_title("7.7 Timestamp Handling")
    pdf.body_text("VJ Sales App stores created_at and last_updated_at as EPOCH MILLISECONDS "
                  "(not seconds). Conversion: to_timestamp(created_at / 1000). "
                  "In the Gold layer, all timestamps are proper TIMESTAMP columns.")

    pdf.section_title("7.8 TenantId Filter")
    pdf.body_text("ALL Farvision ERP queries MUST include WHERE TenantId = 75. "
                  "This is hardcoded as FARVISION_TENANT_ID = 75 in the transformer module.")

    # ── CHAPTER 8: CROSS-SYSTEM KEYS ──
    pdf.add_page()
    pdf.chapter_title("Chapter 8: Cross-System Join Key Reference")

    widths = [25, 55, 55, 35]
    pdf.table_header(["Key", "Farvision", "Other System", "Confidence"], widths)
    for i, r in enumerate([
        ("BookingId", "DimBookingMaster.BookingId", "VJ Sales: AllotmentPayment.bookingId", "0.99"),
        ("BookingId", "DimBookingMaster.BookingId", "VJOP: customer_bookings_units.fv_booking_id", "0.99"),
        ("UnitId", "DimUnitMaster.UnitId", "VJ Sales: Inventory.farvisionUnitId", "0.95"),
        ("UnitId", "DimUnitMaster.UnitId", "VJOP: lead_allotments.farvisionUnitId", "0.95"),
        ("BUId", "DimBusinessUnit.BusinessUnitId", "VJ Sales: Projects.buId", "1.00"),
        ("BUId", "DimBusinessUnit.BusinessUnitId", "VJOP: customer_bookings_units.BUId", "1.00"),
        ("LedgerId", "DimCustomerDetail.LedgerCustId", "VJOP: customers.FV_LedgerID", "0.95"),
        ("LeadId", "(none)", "VJ Sales leadId <-> VJOP sales_app_lead_id", "0.95"),
    ]):
        pdf.table_row(r, widths, i % 2 == 0)

    print("Part 6/7 done: ETL + Lineage + Business Rules")
    return pdf


# ── FINAL BUILD ──
pdf = build_pdf()
add_bronze_chapter(pdf)
add_silver_chapter(pdf)
add_gold_chapter(pdf)
add_etl_lineage_rules(pdf)

output_path = "/home/user/Ask-VJ/docs/Ask-VJ-Warehouse-Architecture.pdf"
pdf.output(output_path)
print(f"\nPart 7/7 done: PDF generated at {output_path}")
import os
size_mb = os.path.getsize(output_path) / (1024 * 1024)
print(f"File size: {size_mb:.1f} MB")
print(f"Total pages: {pdf.page_no()}")
