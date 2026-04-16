-- ============================================================
-- ASK VJ: Gold Layer Schema (Business-Facing View Layer)
-- ============================================================
-- The Gold layer is a thin, LLM-friendly view layer over the
-- Silver dimensional model.  Most "tables" here are views that
-- pre-join Silver dimensions and facts so the LLM can write
-- simple single-table SELECTs.
--
-- Tables that remain as physical Gold tables:
--   - dim_date          (backward compat for existing fact FKs)
--   - fact_bookings     (Farvision — no Silver equivalent yet)
--   - fact_receipts     (Farvision — no Silver equivalent yet)
--   - fact_invoices     (Farvision — no Silver equivalent yet)
--   - snapshot_outstanding  (Farvision aging)
--   - snapshot_inventory    (VJ Sales pricing — will move to Silver)
--   - snapshot_referrals    (VJOP — will move to Silver)
--   - fact_daily_funnel_snapshot (aggregated counts)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS gold;

-- ============================================================
-- DIMENSION: Date (kept for existing fact table FK references)
-- Source: Generated calendar table
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.dim_date (
    date_key INT PRIMARY KEY,              -- YYYYMMDD format
    full_date DATE NOT NULL UNIQUE,
    day_of_week VARCHAR(10),               -- Monday, Tuesday, ...
    day_of_month INT,
    week_of_year INT,
    month_number INT,                      -- 1-12
    month_name VARCHAR(20),                -- January, February, ...
    quarter VARCHAR(5),                    -- Q1, Q2, Q3, Q4 (calendar)
    fiscal_quarter VARCHAR(5),             -- Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar
    calendar_year INT,
    fiscal_year INT,                       -- FY2026 = Apr 2025 - Mar 2026
    fiscal_year_label VARCHAR(10),         -- 'FY2026'
    fiscal_year_id INT,                    -- Farvision FiscalYearId: 56=FY2025-26, 52=FY2024-25
    is_weekend BOOLEAN,
    is_month_end BOOLEAN
);

COMMENT ON TABLE gold.dim_date IS
    'Calendar dimension with Indian fiscal year support. Grain: one row per date. '
    'Generated, not extracted. FiscalYearId: 56=FY2025-26, 52=FY2024-25. Owner: Platform.';

-- ############################################################
--  VIEWS — thin business-facing layer over Silver tables
-- ############################################################

-- ============================================================
-- VIEW: Projects (human-readable from Silver)
-- ============================================================
CREATE OR REPLACE VIEW gold.v_projects AS
SELECT
    p.project_skey,
    p.bu_id,
    p.project_name,
    p.project_type,
    p.rera_number,
    p.city,
    p.state,
    p.is_completed,
    p.is_active
FROM silver.dim_project p;

-- ============================================================
-- VIEW: Units (joins project + unit for flat queries)
-- ============================================================
CREATE OR REPLACE VIEW gold.v_units AS
SELECT
    pu.project_unit_skey,
    p.project_name,
    p.bu_id,
    pu.wing_name,
    pu.floor_no,
    pu.unit_no,
    pu.unit_type,
    pu.display_unit_type,
    pu.unit_status,
    pu.saleable_area,
    pu.chargeable_area,
    pu.total_cost_amt,
    pu.bsp_amt,
    pu.fv_status,
    pu.fv_unit_id
FROM silver.dim_project_unit pu
JOIN silver.dim_project p ON pu.project_skey = p.project_skey;

-- ============================================================
-- VIEW: Buyers (human-readable customer view)
-- ============================================================
CREATE OR REPLACE VIEW gold.v_buyers AS
SELECT
    b.buyer_skey,
    b.buyer_id,
    b.name AS buyer_name,
    b.contact_number,
    b.email,
    b.gender,
    b.pan,
    b.rm_name,
    b.is_verified
FROM silver.dim_buyer b;

-- ============================================================
-- VIEW: Employees
-- ============================================================
CREATE OR REPLACE VIEW gold.v_employees AS
SELECT
    e.employee_skey,
    e.employee_name,
    e.email,
    e.role_name,
    e.crm_designation,
    e.is_active
FROM silver.dim_employee e;

-- ============================================================
-- VIEW: Channel Partners
-- ============================================================
CREATE OR REPLACE VIEW gold.v_channel_partners AS
SELECT
    cp.channel_partner_skey,
    cp.cp_display_id,
    cp.cp_type,
    cp.billing_name,
    cp.approval_status,
    cp.is_disabled
FROM silver.dim_channel_partner cp;

-- ============================================================
-- VIEW: Leads (pre-joined with all dimensions for easy querying)
-- ============================================================
CREATE OR REPLACE VIEW gold.v_leads AS
SELECT
    fl.fact_lead_skey,
    fl.lead_id,
    fl.lead_display_id,
    fl.display_dt AS lead_date,
    b.name AS buyer_name,
    b.contact_number AS buyer_phone,
    p.project_name,
    p.bu_id,
    cp.billing_name AS channel_partner,
    fos.name AS fos_name,
    ph.employee_name AS project_head,
    sm.employee_name AS sales_manager,
    cb.employee_name AS claimed_by,
    ls.lov_value AS lead_status,
    lt.lov_value AS lead_type,
    lst.lov_value AS lead_sub_type,
    lc.lov_value AS lead_category,
    lr.lov_value AS lead_response,
    fl.src_created_ts,
    fl.src_updated_ts
FROM silver.fact_lead fl
LEFT JOIN silver.dim_buyer b ON fl.buyer_skey = b.buyer_skey
LEFT JOIN silver.dim_project p ON fl.project_skey = p.project_skey
LEFT JOIN silver.dim_channel_partner cp ON fl.channel_partner_skey = cp.channel_partner_skey
LEFT JOIN silver.dim_channel_partner_fos fos ON fl.channel_partner_fos_skey = fos.channel_partner_fos_skey
LEFT JOIN silver.dim_employee ph ON fl.project_head_employee_skey = ph.employee_skey
LEFT JOIN silver.dim_employee sm ON fl.sales_manager_employee_skey = sm.employee_skey
LEFT JOIN silver.dim_employee cb ON fl.claimed_by_employee_skey = cb.employee_skey
LEFT JOIN silver.dim_lov ls ON fl.lead_status_lov_skey = ls.lov_skey
LEFT JOIN silver.dim_lov lt ON fl.lead_type_lov_skey = lt.lov_skey
LEFT JOIN silver.dim_lov lst ON fl.lead_sub_type_lov_skey = lst.lov_skey
LEFT JOIN silver.dim_lov lc ON fl.lead_category_lov_skey = lc.lov_skey
LEFT JOIN silver.dim_lov lr ON fl.lead_response_lov_skey = lr.lov_skey;

-- ============================================================
-- VIEW: Site Visits (pre-joined)
-- ============================================================
CREATE OR REPLACE VIEW gold.v_site_visits AS
SELECT
    sv.fact_site_visit_skey,
    sv.site_visit_id,
    fl.lead_display_id,
    b.name AS buyer_name,
    p.project_name,
    e.employee_name AS accompanied_by,
    cp.billing_name AS channel_partner,
    c.calendar_dt AS visit_date,
    sv.site_visit_ts,
    sv.mode,
    sv.remarks
FROM silver.fact_site_visit sv
LEFT JOIN silver.fact_lead fl ON sv.fact_lead_skey = fl.fact_lead_skey
LEFT JOIN silver.dim_buyer b ON fl.buyer_skey = b.buyer_skey
LEFT JOIN silver.dim_project p ON sv.project_skey = p.project_skey
LEFT JOIN silver.dim_employee e ON sv.employee_skey = e.employee_skey
LEFT JOIN silver.dim_channel_partner cp ON sv.channel_partner_skey = cp.channel_partner_skey
LEFT JOIN silver.dim_calendar c ON sv.site_visit_dt_skey = c.calendar_skey;

-- ============================================================
-- VIEW: Conversion Rates (computed from Silver lead/visit counts)
-- ============================================================
CREATE OR REPLACE VIEW gold.v_conversion_rates AS
SELECT
    p.project_name,
    p.bu_id,
    COUNT(DISTINCT fl.lead_id) AS total_leads,
    COUNT(DISTINCT sv.site_visit_id) AS total_site_visits,
    ROUND(COUNT(DISTINCT sv.site_visit_id) * 100.0 / NULLIF(COUNT(DISTINCT fl.lead_id), 0), 2) AS lead_to_visit_rate
FROM silver.fact_lead fl
LEFT JOIN silver.dim_project p ON fl.project_skey = p.project_skey
LEFT JOIN silver.fact_site_visit sv ON fl.fact_lead_skey = sv.fact_lead_skey
GROUP BY p.project_name, p.bu_id;

-- ############################################################
--  TABLES — Farvision financials (no Silver equivalent yet)
-- ############################################################

-- ============================================================
-- FACT: Bookings (one row per booking)
-- Source: Farvision CRMG.FactBooking + DimAgreement + DimRegistration
-- The core transactional fact — each row is a single booking
-- linking customer, project, unit, typology, and financials.
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.fact_bookings (
    booking_key SERIAL PRIMARY KEY,
    farvision_booking_id INT,              -- Farvision FactBooking.BookingId
    booking_no VARCHAR(50),
    booking_date DATE,

    -- Dimension FKs
    customer_key INT REFERENCES gold.dim_customers,
    project_key INT REFERENCES gold.dim_projects,
    unit_key INT REFERENCES gold.dim_units,
    sales_person_key INT REFERENCES gold.dim_sales_persons,
    typology_key INT REFERENCES gold.dim_typologies,

    -- Financial details
    net_basic_price DECIMAL(15, 2),
    agreement_value DECIMAL(15, 2),
    discount_percentage DECIMAL(5, 2),

    -- Lifecycle flags
    is_cancelled BOOLEAN DEFAULT FALSE,
    cancellation_date DATE,

    -- Agreement details
    agreement_date DATE,
    agreement_no VARCHAR(50),

    -- Registration details
    registration_date DATE,
    registration_no VARCHAR(50),

    -- Allotment
    allotment_date DATE,

    -- Broker / Channel Partner
    broker_id INT,

    -- Farvision fiscal year mapping
    fiscal_year_id INT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE gold.fact_bookings IS
    'One row per booking. Full lifecycle: booking → agreement → registration → cancellation. '
    'Upsert on farvision_booking_id. Source: Farvision CRMG.DimBookingMaster. Owner: Sales.';

CREATE INDEX IF NOT EXISTS idx_fact_bookings_project
    ON gold.fact_bookings (project_key);
CREATE INDEX IF NOT EXISTS idx_fact_bookings_customer
    ON gold.fact_bookings (customer_key);
CREATE INDEX IF NOT EXISTS idx_fact_bookings_unit
    ON gold.fact_bookings (unit_key);
CREATE INDEX IF NOT EXISTS idx_fact_bookings_date
    ON gold.fact_bookings (booking_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_fact_bookings_farvision
    ON gold.fact_bookings (farvision_booking_id);
CREATE INDEX IF NOT EXISTS idx_fact_bookings_typology
    ON gold.fact_bookings (typology_key);
CREATE INDEX IF NOT EXISTS idx_fact_bookings_cancelled
    ON gold.fact_bookings (is_cancelled);
CREATE INDEX IF NOT EXISTS idx_fact_bookings_fiscal_year
    ON gold.fact_bookings (fiscal_year_id);

-- ============================================================
-- FACT: Receipts (payments received against bookings)
-- Source: Farvision CRMG.FactReceipt
-- One row per payment received from a customer.
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.fact_receipts (
    receipt_key SERIAL PRIMARY KEY,
    farvision_receipt_id INT,              -- Farvision FactReceipt.ReceiptId

    -- Dimension FKs
    booking_key INT REFERENCES gold.fact_bookings,
    customer_key INT REFERENCES gold.dim_customers,
    project_key INT REFERENCES gold.dim_projects,
    unit_key INT REFERENCES gold.dim_units,
    date_key INT REFERENCES gold.dim_date,

    -- Payment details
    amount DECIMAL(15, 2),
    payment_mode VARCHAR(50),              -- Cheque, NEFT, RTGS, Cash, etc.
    instrument_no VARCHAR(100),            -- Cheque/NEFT reference number
    document_no VARCHAR(100),              -- Farvision document number

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE gold.fact_receipts IS
    'Payments received from customers. Grain: one row per receipt. '
    'Upsert on farvision_receipt_id. Source: Farvision CRMG.DimReceipt. Owner: Finance.';

CREATE INDEX IF NOT EXISTS idx_fact_receipts_booking
    ON gold.fact_receipts (booking_key);
CREATE INDEX IF NOT EXISTS idx_fact_receipts_customer
    ON gold.fact_receipts (customer_key);
CREATE INDEX IF NOT EXISTS idx_fact_receipts_project
    ON gold.fact_receipts (project_key);
CREATE INDEX IF NOT EXISTS idx_fact_receipts_date
    ON gold.fact_receipts (date_key);
CREATE UNIQUE INDEX IF NOT EXISTS idx_fact_receipts_farvision
    ON gold.fact_receipts (farvision_receipt_id);

-- ============================================================
-- FACT: Invoices (demand letters / invoices raised)
-- Source: Farvision CRMG.FactInvoice / DemandLetter
-- One row per demand/invoice issued to a customer against
-- a booking, typically tied to construction milestones.
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.fact_invoices (
    invoice_key SERIAL PRIMARY KEY,
    farvision_invoice_id INT,              -- Farvision FactInvoice.InvoiceId

    -- Dimension FKs
    booking_key INT REFERENCES gold.fact_bookings,
    customer_key INT REFERENCES gold.dim_customers,
    project_key INT REFERENCES gold.dim_projects,
    unit_key INT REFERENCES gold.dim_units,
    date_key INT REFERENCES gold.dim_date,

    -- Invoice details
    basic_amount DECIMAL(15, 2),
    total_amount DECIMAL(15, 2),
    due_date DATE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE gold.fact_invoices IS
    'Demand letters/invoices raised. Grain: one row per invoice. '
    'Upsert on farvision_invoice_id. Source: Farvision CRMG.DimInvoice. Owner: Finance.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_fact_invoices_farvision
    ON gold.fact_invoices (farvision_invoice_id);
CREATE INDEX IF NOT EXISTS idx_fact_invoices_booking
    ON gold.fact_invoices (booking_key);
CREATE INDEX IF NOT EXISTS idx_fact_invoices_customer
    ON gold.fact_invoices (customer_key);
CREATE INDEX IF NOT EXISTS idx_fact_invoices_project
    ON gold.fact_invoices (project_key);
CREATE INDEX IF NOT EXISTS idx_fact_invoices_date
    ON gold.fact_invoices (date_key);
CREATE INDEX IF NOT EXISTS idx_fact_invoices_due_date
    ON gold.fact_invoices (due_date);

-- ############################################################
--  SNAPSHOT TABLES — daily-reload tables still in Gold
-- ############################################################

-- ============================================================
-- SNAPSHOT: Outstanding (aging buckets for overdue amounts)
-- Source: Farvision CRMG.FactDueDatewiseOutstanding
-- TRUNCATE-reload daily — NOT an append-only fact.
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.snapshot_outstanding (
    outstanding_key SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,

    -- Dimension FKs
    customer_key INT REFERENCES gold.dim_customers,
    project_key INT REFERENCES gold.dim_projects,
    unit_key INT REFERENCES gold.dim_units,

    -- Denormalized for fast LLM queries
    customer_name VARCHAR(255),
    unit_no VARCHAR(50),

    -- Amounts
    bill_amount DECIMAL(15, 2),
    paid_amount DECIMAL(15, 2),
    due_amount DECIMAL(15, 2),
    on_account_amount DECIMAL(15, 2),

    -- Aging
    overdue_days INT,
    day_amt_15 DECIMAL(15, 2),             -- Amount overdue 0-15 days
    day_amt_30 DECIMAL(15, 2),             -- Amount overdue 16-30 days
    day_amt_60 DECIMAL(15, 2),             -- Amount overdue 31-60 days
    day_amt_90 DECIMAL(15, 2),             -- Amount overdue 61-90 days
    day_amt_120 DECIMAL(15, 2),            -- Amount overdue 91-120 days
    day_amt_180 DECIMAL(15, 2),            -- Amount overdue 121-180 days
    day_amt_more_180 DECIMAL(15, 2),       -- Amount overdue >180 days

    -- Dates
    document_date DATE,
    due_date DATE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE gold.snapshot_outstanding IS 'Point-in-time aging snapshot. Rebuilt daily. Grain: one row per (customer, unit, due_date). Source: Farvision CRMG.FactDueDatewiseOutstanding. Owner: Finance.';

CREATE INDEX IF NOT EXISTS idx_snapshot_outstanding_customer
    ON gold.snapshot_outstanding (customer_key);
CREATE INDEX IF NOT EXISTS idx_snapshot_outstanding_project
    ON gold.snapshot_outstanding (project_key);
CREATE INDEX IF NOT EXISTS idx_snapshot_outstanding_unit
    ON gold.snapshot_outstanding (unit_key);
CREATE INDEX IF NOT EXISTS idx_snapshot_outstanding_overdue
    ON gold.snapshot_outstanding (overdue_days);

-- ============================================================
-- SNAPSHOT: Inventory (available unit pricing and status)
-- Source: VJ Sales App Inventory tables
-- Will eventually move to Silver.
-- TRUNCATE-reload daily — NOT an append-only fact.
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.snapshot_inventory (
    inventory_key SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,

    -- Dimension FKs
    project_key INT REFERENCES gold.dim_projects,
    unit_key INT REFERENCES gold.dim_units,
    typology_key INT REFERENCES gold.dim_typologies,

    -- Status and pricing
    inventory_status VARCHAR(50),          -- Available, On Hold, Sold
    total_cost DECIMAL(15, 2),
    bsp DECIMAL(15, 2),                    -- Base selling price
    saleable_area DECIMAL(10, 2),
    chargeable_area DECIMAL(10, 2),
    display_unit_type VARCHAR(50),         -- Display label e.g. "3 BHK - Tower A"

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE gold.snapshot_inventory IS 'Point-in-time inventory status. Rebuilt daily. Grain: one row per unit. Source: VJ Sales Inventory. Owner: Sales.';

CREATE INDEX IF NOT EXISTS idx_snapshot_inventory_project
    ON gold.snapshot_inventory (project_key);
CREATE INDEX IF NOT EXISTS idx_snapshot_inventory_unit
    ON gold.snapshot_inventory (unit_key);
CREATE INDEX IF NOT EXISTS idx_snapshot_inventory_typology
    ON gold.snapshot_inventory (typology_key);
CREATE INDEX IF NOT EXISTS idx_snapshot_inventory_status
    ON gold.snapshot_inventory (inventory_status);

-- ============================================================
-- SNAPSHOT: Referrals (VJOP loyalty referral tracking)
-- Source: VJOP leads + lead_allotments + loyalty_points
-- Will eventually move to Silver.
-- TRUNCATE-reload daily — NOT an append-only fact.
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.snapshot_referrals (
    referral_key SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,

    -- Who referred
    referrer_customer_key INT REFERENCES gold.dim_customers,

    -- Who was referred (may not yet be a dim_customers entry)
    referred_lead_name VARCHAR(255),
    referred_mobile VARCHAR(50),

    -- Context
    project_key INT REFERENCES gold.dim_projects,

    -- Lifecycle
    referral_status VARCHAR(50),           -- Unclaimed, Claimed, Site Visit Done, Agreement Done
    vjop_lead_id INT,                      -- VJOP leads table ID
    sales_app_lead_id UUID,                -- Linked VJ Sales App lead UUID
    booking_id INT,                        -- From VJOP lead_allotments (NOT leads)

    -- Loyalty points
    points_earned DECIMAL(10, 2),
    points_redeemed DECIMAL(10, 2),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE gold.snapshot_referrals IS 'Point-in-time referral status. Rebuilt daily. Grain: one row per referral lead. Source: VJOP leads + allotments + points. Owner: Marketing.';

CREATE INDEX IF NOT EXISTS idx_snapshot_referrals_referrer
    ON gold.snapshot_referrals (referrer_customer_key);
CREATE INDEX IF NOT EXISTS idx_snapshot_referrals_project
    ON gold.snapshot_referrals (project_key);
CREATE INDEX IF NOT EXISTS idx_snapshot_referrals_status
    ON gold.snapshot_referrals (referral_status);
CREATE INDEX IF NOT EXISTS idx_snapshot_referrals_vjop_lead
    ON gold.snapshot_referrals (vjop_lead_id);

-- ############################################################
--  AGGREGATED FACT TABLE
-- ############################################################

-- ============================================================
-- FACT: Daily Funnel Snapshot (for trend analysis)
-- Source: Aggregated daily from fact_lead_pipeline + fact_bookings
-- Pre-computed daily counts per project for fast dashboard queries.
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.fact_daily_funnel_snapshot (
    snapshot_id SERIAL PRIMARY KEY,
    snapshot_date_key INT NOT NULL REFERENCES gold.dim_date,
    project_key INT NOT NULL REFERENCES gold.dim_projects,

    total_inquiries INT DEFAULT 0,
    total_site_visits INT DEFAULT 0,
    total_bookings INT DEFAULT 0,
    total_agreements INT DEFAULT 0,
    total_registered INT DEFAULT 0,
    total_cancelled INT DEFAULT 0,
    total_active_leads INT DEFAULT 0,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(snapshot_date_key, project_key)
);

COMMENT ON TABLE gold.fact_daily_funnel_snapshot IS
    'Daily lead funnel counts per project. Grain: one row per (date, project). '
    'Source: Aggregated from fact_lead_pipeline + fact_bookings. Freshness: daily. Owner: Sales.';

CREATE INDEX IF NOT EXISTS idx_fact_funnel_date
    ON gold.fact_daily_funnel_snapshot (snapshot_date_key);
CREATE INDEX IF NOT EXISTS idx_fact_funnel_project
    ON gold.fact_daily_funnel_snapshot (project_key);
