"""Ask VJ -- Warehouse Architecture PDF Generator (v2 -- post-migration)"""
from fpdf import FPDF
from datetime import date
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
            self.cell(0, 5, "Ask VJ -- Warehouse Architecture Reference Manual v2", align="C")
            self.ln(8)
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GRAY_TEXT)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")
    def chapter_title(self, t):
        self.set_font("Helvetica", "B", 16); self.set_text_color(*NAVY)
        self.cell(0, 12, t, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*GOLD); self.set_line_width(0.8)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y()); self.ln(6)
    def section_title(self, t):
        self.set_font("Helvetica", "B", 12); self.set_text_color(*NAVY)
        self.cell(0, 8, t, new_x="LMARGIN", new_y="NEXT"); self.ln(2)
    def sub(self, t):
        self.set_font("Helvetica", "B", 10); self.set_text_color(60,60,60)
        self.cell(0, 7, t, new_x="LMARGIN", new_y="NEXT"); self.ln(1)
    def body(self, t):
        self.set_font("Helvetica", "", 9); self.set_text_color(*BLACK)
        self.multi_cell(0, 5, t); self.ln(2)
    def code(self, t):
        self.set_font("Courier", "", 7); self.set_fill_color(*GRAY_LIGHT); self.set_text_color(30,30,30)
        w = self.w - self.l_margin - self.r_margin
        for line in t.split("\n"):
            if self.get_y() > 270: self.add_page()
            self.cell(w, 4, line, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(3); self.set_text_color(*BLACK)
    def th(self, cols, widths):
        self.set_font("Helvetica", "B", 8); self.set_fill_color(*NAVY); self.set_text_color(*WHITE)
        for i, c in enumerate(cols): self.cell(widths[i], 6, c, border=1, fill=True, align="C")
        self.ln(); self.set_text_color(*BLACK)
    def tr(self, cells, widths, f=False):
        self.set_font("Helvetica", "", 7.5)
        self.set_fill_color(*(GRAY_LIGHT if f else WHITE))
        for i, c in enumerate(cells): self.cell(widths[i], 5, str(c)[:55], border=1, fill=True)
        self.ln()
    def check(self, h=30):
        if self.get_y() + h > 270: self.add_page()
    def tbl(self, name, src, cols):
        self.check(40); self.sub(f"Table: {name}")
        self.set_font("Helvetica","I",8); self.set_text_color(*GRAY_TEXT)
        self.cell(0, 4, f"Source: {src}", new_x="LMARGIN", new_y="NEXT"); self.ln(2)
        self.set_text_color(*BLACK); w=[55,35,80]; self.th(["Column","Type","Description"],w)
        for i,(c,t,d) in enumerate(cols): self.tr([c,t,d],w,i%2==0)

pdf = PDF(); pdf.alias_nb_pages(); pdf.set_auto_page_break(auto=True, margin=20)

# ===== COVER =====
pdf.add_page(); pdf.ln(60)
pdf.set_font("Helvetica","B",32); pdf.set_text_color(*NAVY)
pdf.cell(0,15,"Ask VJ",align="C",new_x="LMARGIN",new_y="NEXT")
pdf.set_font("Helvetica","",18); pdf.set_text_color(*GRAY_TEXT)
pdf.cell(0,10,"Data Warehouse Architecture",align="C",new_x="LMARGIN",new_y="NEXT")
pdf.cell(0,8,"Technical Reference Manual v2",align="C",new_x="LMARGIN",new_y="NEXT")
pdf.ln(10); pdf.set_draw_color(*GOLD); pdf.set_line_width(1.5)
pdf.line(60,pdf.get_y(),150,pdf.get_y()); pdf.ln(15)
pdf.set_font("Helvetica","",12)
pdf.cell(0,7,"Post-Migration Architecture | April 2026",align="C",new_x="LMARGIN",new_y="NEXT")
pdf.cell(0,7,"Vilas Javdekar (VJ) Developers",align="C",new_x="LMARGIN",new_y="NEXT")
print("Cover done")

# ===== CH1: ARCHITECTURE =====
pdf.add_page(); pdf.chapter_title("Chapter 1: Architecture Overview")
pdf.section_title("1.1 Medallion Architecture (Post-Migration)")
pdf.body("Ask VJ uses a three-layer medallion architecture:\n"
    "- Bronze: 36 raw staging tables (Farvision + VJ Sales + VJOP)\n"
    "- Silver: 19 tables (3 entity resolution + 16 dimensional model from developer's design)\n"
    "- Gold: 8 views over Silver + 7 kept Farvision tables\n"
    "- AI Layer: LLM queries Gold views to generate SQL from natural language")
pdf.code(
    "SOURCE SYSTEMS         BRONZE           SILVER                 GOLD              AI LAYER\n"
    "+--------------+     +--------+     +----------------+     +----------+     +----------+\n"
    "| Farvision    |---->| 16 raw |---->| Entity         |---->| Views    |---->| LLM SQL  |\n"
    "| (SQL Server) |     | tables |     | Resolution     |     | over     |     | from NL  |\n"
    "+--------------+     |        |     |                |     | Silver   |     | questions|\n"
    "| VJ Sales     |---->| 13 raw |---->| Developer's    |     | +        |     |          |\n"
    "| (PostgreSQL) |     | tables |     | Dimensional    |     | Farvision|     |          |\n"
    "+--------------+     |        |     | Model:         |     | tables   |     |          |\n"
    "| VJOP Portal  |---->| 7 raw  |     | 8 dims, 3 fact|     |          |     |          |\n"
    "| (SQL Server) |     | tables |     | + LOV, xref    |     |          |     |          |\n"
    "+--------------+     +--------+     +----------------+     +----------+     +----------+")
pdf.section_title("1.2 Source Systems")
w=[45,35,45,45]; pdf.th(["System","Database","Type","Key ID"],w)
pdf.tr(["Farvision ERP","VJDLIVE45","SQL Server","TenantId=75"],w,True)
pdf.tr(["VJ Sales App","PostgreSQL","Supabase","UUID IDs"],w)
pdf.tr(["VJOP Portal","RefferalAndLoyalty","SQL Server","INT IDs"],w,True)
pdf.ln(4); pdf.section_title("1.3 Cross-System Join Keys")
w=[30,55,55,30]; pdf.th(["Key","Farvision","Other System","Confidence"],w)
pdf.tr(["BookingId","DimBookingMaster","VJ Sales: AllotmentPayment.bookingId","0.99"],w,True)
pdf.tr(["BookingId","","VJOP: customer_bookings_units.fv_booking_id","0.99"],w)
pdf.tr(["UnitId","DimUnitMaster","VJ Sales: Inventory.farvisionUnitId","0.95"],w,True)
pdf.tr(["BUId","DimBusinessUnit","VJ Sales: Projects.buId","1.00"],w)
pdf.tr(["BUId","","VJOP: customer_bookings_units.BUId","1.00"],w,True)
pdf.tr(["LedgerId","DimCustomerDetail","VJOP: customers.FV_LedgerID","0.95"],w)
pdf.tr(["LeadId","(none)","VJ Sales leadId <-> VJOP sales_app_lead_id","0.95"],w,True)
print("Ch1 done")

# ===== CH2: BRONZE =====
pdf.add_page(); pdf.chapter_title("Chapter 2: Bronze Layer -- Raw Staging (36 Tables)")
pdf.body("Append-only with audit metadata: _sync_id, _synced_at, _source_system, _batch_id.")
pdf.section_title("2.1 Farvision ERP (16 Tables)")
pdf.tbl("stg_fv_dim_booking_master","CRMG.DimBookingMaster",[
    ("BookingId","INT PK","Booking identifier"),("LedgerId","INT","Customer ledger"),
    ("BUId","INT","Universal project key"),("BookingDate","DATE","Booking date"),
    ("NetBasicPrice","DECIMAL","Base price"),("IsCancelled","BOOLEAN","0=active"),
    ("SalesPersonId","INT","Sales person"),("FiscalYearId","INT","56=FY25-26")])
pdf.tbl("stg_fv_dim_business_unit","ENGG.DimBusinessUnit",[
    ("BusinessUnitId","INT PK","Universal project key (BUId)"),
    ("BusinessUnit","VARCHAR","Project name"),("SegmentId","INT","Segment")])
pdf.tbl("stg_fv_dim_receipt","CRMG.DimReceipt",[
    ("RecieptId","INT PK","Receipt ID (sic)"),("BookingId","INT","Linked booking"),
    ("AmountLCY","DECIMAL","Amount"),("PaymentMode","VARCHAR","Cheque/NEFT/RTGS"),
    ("DocumentDate","DATE","Payment date")])
pdf.tbl("stg_fv_fact_duedate_outstanding","CRMG.FactDueDatewiseOutstanding",[
    ("LedgerId","INT","Customer"),("Bill_Amount","DECIMAL","Total billed"),
    ("Paid_Amount","DECIMAL","Total paid"),("Due_Amount","DECIMAL","Outstanding"),
    ("DayAmt_15..More180","DECIMAL","7 aging buckets"),("BuId","INT","Project")])
pdf.section_title("2.2 VJ Sales App (13 Tables)")
pdf.body("Timestamps are EPOCH MILLISECONDS. IDs are UUIDs. JSONB preserved.")
pdf.tbl("stg_vj_projects",'"Projects"',[
    ("projectId","UUID PK","Project ID"),("projectName","VARCHAR","Name"),
    ("buId","INT","Maps to Farvision BUId"),("reraNumber","VARCHAR","RERA")])
pdf.tbl("stg_vj_inventory",'"Inventory"',[
    ("unitId","UUID PK","Unit ID"),("farvisionUnitId","INT","Cross-system key"),
    ("totalCost","DECIMAL","Total price"),("BSP","DECIMAL","Base price/sqft")])
pdf.tbl("stg_vj_leads",'"Leads"',[
    ("leadId","UUID PK","Lead ID"),("personId","UUID","Person ref"),
    ("cpId","UUID","Channel partner"),("leadType","VARCHAR","walk-in/digital/CP")])
pdf.tbl("stg_vj_allotment_payment",'"AllotmentPayment"',[
    ("allotmentPaymentId","UUID PK","Allotment ID"),("bookingId","INT","Cross-system key"),
    ("status","VARCHAR","Payment Complete/Agreement Done"),("paidAmount","DECIMAL","Amount")])
pdf.section_title("2.3 VJOP (7 Tables)")
pdf.tbl("stg_rnl_customers","dbo.customers",[
    ("id","INT PK","VJOP customer"),("FV_LedgerID","INT","Cross-system to Farvision")])
pdf.tbl("stg_rnl_leads","dbo.leads",[
    ("id","INT PK","VJOP lead"),("sales_app_lead_id","UUID","Cross-system to VJ Sales"),
    ("referred_by","INT","Referrer customer ID"),("status","VARCHAR","Referral status")])
print("Ch2 done")

# ===== CH3: SILVER =====
pdf.add_page(); pdf.chapter_title("Chapter 3: Silver Layer -- Developer's Dimensional Model")
pdf.body("19 tables total: 3 entity resolution (existing) + 16 from developer's relations.xlsx design.\n"
    "All use UUID surrogate keys (_skey), DW audit columns, and centralized LOV lookups.")
pdf.section_title("3.1 Entity Resolution (Existing)")
pdf.tbl("silver.project_crosswalk","Auto-discovered from Bronze",[
    ("farvision_bu_id","INT UNIQUE","Universal project key"),
    ("canonical_name","VARCHAR","Unified project name"),
    ("vjsales_project_name","VARCHAR","VJ Sales name"),
    ("vjop_project_name","VARCHAR","VJOP name")])
pdf.tbl("silver.entity_map","ID-based matching",[
    ("unified_customer_id","UUID","System-generated unified ID"),
    ("farvision_booking_id","INT UNIQUE","Farvision BookingId"),
    ("vjsales_lead_id","UUID UNIQUE","VJ Sales leadId"),
    ("match_method","VARCHAR","booking_id_exact/unit_id_exact/lead_id_exact")])
pdf.section_title("3.2 Reference Tables")
pdf.tbl("silver.xref_map","Centralized value standardization",[
    ("mapping_name","VARCHAR","e.g. pincode_to_city"),
    ("from_domain","VARCHAR","Source domain"),("to_domain","VARCHAR","Target domain"),
    ("from_value","VARCHAR","Raw value"),("to_value","VARCHAR","Standardized value")])
pdf.tbl("silver.dim_lov","Centralized status/type lookups (29 seed rows)",[
    ("lov_skey","UUID PK","Surrogate key"),("lov_type","VARCHAR","lead_status/lead_type/etc"),
    ("lov_code","VARCHAR","Code"),("lov_value","VARCHAR","Display value")])
pdf.section_title("3.3 Dimension Tables")
pdf.tbl("silver.dim_calendar","Generated 2015-2035",[
    ("calendar_skey","VARCHAR PK","YYYYMMDD format"),("calendar_dt","DATE","Actual date"),
    ("fiscal_quarter","INT","Q1=Apr-Jun..Q4=Jan-Mar"),("fiscal_year","INT","Indian FY")])
pdf.tbl("silver.dim_project","stg_vj_projects + crosswalk",[
    ("project_skey","UUID PK","Surrogate key"),("bu_id","VARCHAR","Farvision BUId"),
    ("project_name","VARCHAR","Project name"),("rera_number","VARCHAR","RERA"),
    ("is_completed","BOOLEAN","Completion flag")])
pdf.tbl("silver.dim_project_unit","stg_vj_inventory",[
    ("project_unit_skey","UUID PK","Surrogate key"),
    ("project_skey","UUID FK","-> dim_project"),("unit_id","UUID","VJ Sales unitId"),
    ("fv_unit_id","VARCHAR","Farvision UnitId"),("wing_name","VARCHAR","Wing"),
    ("unit_no","VARCHAR","Unit number"),("unit_type","VARCHAR","1BHK/2BHK/3BHK"),
    ("total_cost_amt","NUMERIC","Total price"),("bsp_amt","NUMERIC","Base price/sqft")])
pdf.tbl("silver.dim_buyer","stg_vj_person + VJOP",[
    ("buyer_skey","UUID PK","Surrogate key"),("buyer_id","UUID","VJ Sales personId"),
    ("name","VARCHAR","Full name"),("contact_number","VARCHAR","Mobile"),
    ("email","VARCHAR","Email"),("pan","VARCHAR","PAN number"),("gender","VARCHAR","Gender")])
pdf.tbl("silver.dim_employee","stg_vj_users",[
    ("employee_skey","UUID PK","Surrogate key"),("employee_id","UUID","VJ Sales userId"),
    ("employee_name","VARCHAR","Name"),("role_name","VARCHAR","Role")])
pdf.tbl("silver.dim_channel_partner","stg_vj_cp",[
    ("channel_partner_skey","UUID PK","Surrogate key"),("cp_id","UUID","VJ Sales cpId"),
    ("billing_name","VARCHAR","Billing name"),("approval_status","VARCHAR","Status")])
pdf.section_title("3.4 Fact Tables")
pdf.tbl("silver.fact_lead","stg_vj_leads (20+ dimension FKs)",[
    ("fact_lead_skey","UUID PK","Surrogate key"),("lead_id","UUID UNIQUE","VJ Sales leadId"),
    ("buyer_skey","UUID FK","-> dim_buyer"),("project_skey","UUID FK","-> dim_project"),
    ("channel_partner_skey","UUID FK","-> dim_channel_partner"),
    ("lead_dt_skey","VARCHAR FK","-> dim_calendar"),
    ("lead_status_lov_skey","UUID FK","-> dim_lov (status)"),
    ("lead_type_lov_skey","UUID FK","-> dim_lov (type)")])
pdf.tbl("silver.fact_site_visit","stg_vj_site_visits",[
    ("fact_site_visit_skey","UUID PK","Surrogate key"),
    ("fact_lead_skey","UUID FK","-> fact_lead"),("project_skey","UUID FK","-> dim_project"),
    ("employee_skey","UUID FK","-> dim_employee"),("mode","VARCHAR","Onsite/Video/F2F")])
print("Ch3 done")

# ===== CH4: GOLD =====
pdf.add_page(); pdf.chapter_title("Chapter 4: Gold Layer -- Business Views + Farvision Tables")
pdf.body("Gold = thin business-facing layer. 8 views over Silver for LLM consumption.\n"
    "7 kept Farvision tables (bookings, receipts, invoices, outstanding, inventory, referrals, funnel).")
pdf.section_title("4.1 Views (pre-joined for LLM)")
w=[50,120]; pdf.th(["View","Description"],w)
pdf.tr(["gold.v_projects","Project name, bu_id, type, RERA, city, status"],w,True)
pdf.tr(["gold.v_units","Unit + project name, wing, floor, type, pricing, status"],w)
pdf.tr(["gold.v_buyers","Buyer name, phone, email, PAN, RM"],w,True)
pdf.tr(["gold.v_employees","Employee name, role, designation"],w)
pdf.tr(["gold.v_channel_partners","CP display ID, type, billing name, status"],w,True)
pdf.tr(["gold.v_leads","Pre-joined: buyer, project, CP, employees, LOV values"],w)
pdf.tr(["gold.v_site_visits","Pre-joined: lead, buyer, project, employee, CP, date"],w,True)
pdf.tr(["gold.v_conversion_rates","Lead-to-visit rate computed from Silver facts"],w)
pdf.ln(4); pdf.section_title("4.2 Kept Farvision Tables")
w=[55,115]; pdf.th(["Table","Description"],w)
pdf.tr(["gold.fact_bookings","One row per booking. Upsert on farvision_booking_id."],w,True)
pdf.tr(["gold.fact_receipts","Payments received. Upsert on farvision_receipt_id."],w)
pdf.tr(["gold.fact_invoices","Demand letters. Upsert on farvision_invoice_id."],w,True)
pdf.tr(["gold.snapshot_outstanding","Daily aging snapshot. 7 buckets (15-180+ days)."],w)
pdf.tr(["gold.snapshot_inventory","Daily inventory pricing snapshot."],w,True)
pdf.tr(["gold.snapshot_referrals","Daily VJOP referral status snapshot."],w)
pdf.tr(["gold.fact_daily_funnel_snapshot","Aggregated daily lead/booking counts."],w,True)
print("Ch4 done")

# ===== CH5: ETL =====
pdf.add_page(); pdf.chapter_title("Chapter 5: ETL Pipeline")
pdf.code(
    "Stage 1: EXTRACT (Bronze)\n"
    "  Farvision: 16 full-load queries (TenantId=75)\n"
    "  VJ Sales: 12 incremental (watermark on timestamp)\n"
    "  VJOP: 6 incremental (watermark on created_at)\n\n"
    "Stage 2: RESOLVE (Silver)\n"
    "  Auto-discover projects via BUId\n"
    "  Entity resolution: BookingId -> UnitId -> LeadId -> Fuzzy queue\n\n"
    "Stage 2.5: PRE-GOLD QUALITY GATE\n"
    "  Check silver.project_crosswalk populated\n\n"
    "Stage 3: TRANSFORM\n"
    "  Silver dims: calendar, country, project, project_unit, employee, CP, FOS, buyer\n"
    "  Silver facts: fact_lead (20+ FKs), fact_site_visit\n"
    "  Gold facts: bookings, receipts, invoices (Farvision)\n"
    "  Gold snapshots: outstanding, inventory, referrals\n\n"
    "Stage 4: POST-GOLD VALIDATE\n"
    "  Orphans, nulls, negatives, entity coverage, completeness")
print("Ch5 done")

# ===== CH6: LINEAGE =====
pdf.add_page(); pdf.chapter_title("Chapter 6: Data Lineage")
pdf.section_title("6.1 Lead Lineage")
pdf.code(
    'VJ Sales "Leads" -> bronze.stg_vj_leads\n'
    '  -> silver.fact_lead (buyer/project/CP/employee/LOV lookups)\n'
    '    -> gold.v_leads (pre-joined view for LLM)')
pdf.section_title("6.2 Site Visit Lineage")
pdf.code(
    'VJ Sales "SiteVisits" -> bronze.stg_vj_site_visits\n'
    '  -> silver.fact_site_visit (lead/project/employee lookups)\n'
    '    -> gold.v_site_visits (pre-joined view)')
pdf.section_title("6.3 Booking Lineage (Farvision)")
pdf.code(
    "Farvision CRMG.DimBookingMaster -> bronze.stg_fv_dim_booking_master\n"
    "  -> silver.entity_map (BookingId match, conf 0.99)\n"
    "    -> gold.fact_bookings (agreement/registration/cancellation LATERAL joins)")
pdf.section_title("6.4 Outstanding Lineage")
pdf.code(
    "Farvision FactDueDatewiseOutstanding -> bronze.stg_fv_fact_duedate_outstanding\n"
    "  -> gold.snapshot_outstanding (daily refresh, 7 aging buckets)")
print("Ch6 done")

# ===== CH7: BUSINESS RULES =====
pdf.add_page(); pdf.chapter_title("Chapter 7: Business Rules")
pdf.section_title("7.1 Indian Fiscal Year")
pdf.body("April-March. FY2026 = Apr 2025 - Mar 2026.\nQ1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar.")
pdf.section_title("7.2 Unit Status (Farvision)")
w=[30,50,90]; pdf.th(["Code","Status","Description"],w)
pdf.tr(["1","Sold","Booked/sold"],w,True); pdf.tr(["2","Available","For sale"],w)
pdf.tr(["3","Blocked","Reserved"],w,True)
pdf.section_title("7.3 LOV Categories (dim_lov)")
pdf.body("lead_status: New, Contacted, Follow Up, Site Visit Done, Negotiation, Booked, Lost, Cancelled\n"
    "lead_type: CP, Walk-In, Digital, Referral, Self, Employee\n"
    "lead_category: A, B, C (prioritization)\n"
    "lead_response: Hot, Warm, Cold")
pdf.section_title("7.4 Aging Buckets")
w=[40,50,80]; pdf.th(["Column","Range","Severity"],w)
for i,r in enumerate([("day_amt_15","0-15 days","Recent"),("day_amt_30","16-30","1 month"),
    ("day_amt_60","31-60","2 months"),("day_amt_90","61-90","3 months"),
    ("day_amt_120","91-120","4 months"),("day_amt_180","121-180","6 months"),
    ("day_amt_more_180",">180","Severe")]): pdf.tr(r,w,i%2==0)
pdf.section_title("7.5 DW Audit Columns (all Silver tables)")
pdf.body("dw_load_ts: When record was first loaded (CURRENT_TIMESTAMP)\n"
    "dw_update_ts: When record was last updated\ndw_created_by: ETL process identifier ('etl_pipeline')")
pdf.section_title("7.6 Surrogate Key Pattern")
pdf.body("All Silver dimension/fact tables use UUID surrogate keys (gen_random_uuid()).\n"
    "Named: {table}_skey (e.g. project_skey, buyer_skey, fact_lead_skey).\n"
    "NAVL sentinel: md5('NAVL')::uuid for Not Available values.\n"
    "NAPL sentinel: md5('NAPL')::uuid for Not Applicable values.")
print("Ch7 done")

out = "/home/user/Ask-VJ/docs/Ask-VJ-Warehouse-Architecture.pdf"
pdf.output(out)
sz = os.path.getsize(out)
print(f"\nPDF generated: {out}")
print(f"Pages: {pdf.page_no()}, Size: {sz/1024:.0f} KB")
