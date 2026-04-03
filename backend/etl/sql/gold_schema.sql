-- ============================================================
-- ASK VJ: Gold Layer Schema (Business-Ready Star Schema)
-- ============================================================
-- Built from real column structures discovered in:
--   - Farvision ERP (CRMG schema: DimCustomerDetail, FactBooking,
--     FactReceipt, FactDueDatewiseOutstanding, DimUnit, etc.)
--   - VJ Sales App (leads, allotment_payments, inventory)
--   - VJOP (referrals, loyalty points)
--
-- Optimized for LLM SQL generation. Self-documenting names.
-- Simple JOINs only via surrogate keys.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS gold;

-- ============================================================
-- DIMENSION: Date (supports natural language time filtering)
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

-- ============================================================
-- DIMENSION: Projects
-- Source: Farvision DimProject / BusinessUnit mapping
-- bu_id is the Farvision BusinessUnitId — the universal project
-- key that connects across all Farvision tables.
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.dim_projects (
    project_key SERIAL PRIMARY KEY,
    bu_id INT NOT NULL,                    -- Farvision BusinessUnitId (universal project key)
    project_name VARCHAR(255) NOT NULL,    -- Canonical name from crosswalk
    phase_name VARCHAR(100),
    segment VARCHAR(100),                  -- Residential, Commercial, etc.
    project_type VARCHAR(100),             -- High-rise, Plotted, Township, etc.
    total_units INT,
    launch_date DATE,
    status VARCHAR(50),                    -- active, completed, upcoming
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE gold.dim_projects IS
    'VJ real estate projects. Grain: one row per project/phase. '
    'bu_id = Farvision BusinessUnitId (universal project key). '
    'Source: silver.project_crosswalk + Farvision ENGG.DimBusinessUnit. Owner: Operations.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_dim_projects_bu_id
    ON gold.dim_projects (bu_id);

-- ============================================================
-- DIMENSION: Typologies
-- Source: Farvision DimTypology
-- Maps Farvision TypologyId to readable names. Variants like
-- "3.00BHK XL" or "3.00BHK XR" share a base typology "3 BHK".
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.dim_typologies (
    typology_key SERIAL PRIMARY KEY,
    typology_id INT,                       -- Farvision TypologyId
    typology_code VARCHAR(50),             -- Source code e.g. "3BHK-XL"
    typology VARCHAR(50),                  -- Raw value e.g. "3.00BHK"
    display_name VARCHAR(50),              -- Human-friendly e.g. "3 BHK"
    is_base_variant BOOLEAN DEFAULT TRUE   -- true for base 3BHK, false for XL/XR variants
);

COMMENT ON TABLE gold.dim_typologies IS
    'Unit type classification (1BHK, 2BHK, 3BHK, etc). Grain: one row per typology variant. '
    'is_base_variant=true for base types, false for XL/XR variants. '
    'For "3 BHK" queries use is_base_variant=true. Source: Farvision CRMG.DimTypologyMaster. Owner: Sales.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_dim_typologies_typology_id
    ON gold.dim_typologies (typology_id);

-- ============================================================
-- DIMENSION: Units (individual flats/shops)
-- Source: Farvision DimUnit + VJ Sales Inventory
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.dim_units (
    unit_key SERIAL PRIMARY KEY,
    farvision_unit_id INT,                 -- Farvision DimUnit.UnitId
    project_key INT NOT NULL REFERENCES gold.dim_projects,
    typology_key INT REFERENCES gold.dim_typologies,
    unit_no VARCHAR(50) NOT NULL,
    wing VARCHAR(50),
    floor INT,
    unit_status INT,                       -- Farvision status: 1=sold, 2=available, 3=blocked
    farvision_status VARCHAR(50),          -- Raw status label from Farvision
    saleable_area DECIMAL(10, 2),
    carpet_area DECIMAL(10, 2),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE gold.dim_units IS
    'Individual flats/shops/offices. Grain: one row per unit. unit_status: 1=sold, 2=available, 3=blocked. '
    'Source: Farvision CRMG.DimUnitMaster + VJ Sales Inventory. Owner: Sales.';

CREATE INDEX IF NOT EXISTS idx_dim_units_project
    ON gold.dim_units (project_key);
CREATE INDEX IF NOT EXISTS idx_dim_units_typology
    ON gold.dim_units (typology_key);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dim_units_farvision
    ON gold.dim_units (farvision_unit_id);
CREATE INDEX IF NOT EXISTS idx_dim_units_status
    ON gold.dim_units (unit_status);

-- ============================================================
-- DIMENSION: Customers (unified from Farvision + VJ Sales)
-- Source: Farvision CRMG.DimCustomerDetail + VJ Sales Person
-- Linked via silver.entity_map for cross-system identity.
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.dim_customers (
    customer_key SERIAL PRIMARY KEY,
    unified_customer_id UUID NOT NULL,     -- From silver.entity_map
    farvision_ledger_id INT,               -- Farvision Ledger/CustomerId
    full_name VARCHAR(255),
    customer_name VARCHAR(255),            -- Display name
    phone VARCHAR(50),
    mobile VARCHAR(50),
    email VARCHAR(255),
    pan_number VARCHAR(20),
    first_inquiry_date DATE,
    lead_source VARCHAR(100),
    source_system_origin VARCHAR(20),      -- Where first seen: vjsales, farvision
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE gold.dim_customers IS
    'Unified customer records linked across systems via silver.entity_map. '
    'Grain: one row per customer. Source: Farvision DimCustomerDetail + VJ Sales Person. Owner: Sales.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_dim_customers_unified
    ON gold.dim_customers (unified_customer_id);
CREATE INDEX IF NOT EXISTS idx_dim_customers_farvision
    ON gold.dim_customers (farvision_ledger_id);
CREATE INDEX IF NOT EXISTS idx_dim_customers_mobile
    ON gold.dim_customers (mobile);

-- ============================================================
-- DIMENSION: Sales Persons
-- Source: Farvision SalesPerson + VJ Sales App users
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.dim_sales_persons (
    sales_person_key SERIAL PRIMARY KEY,
    farvision_sales_person_id INT,         -- Farvision SalesPersonId
    name VARCHAR(255) NOT NULL,
    team VARCHAR(100),
    region VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE
);

COMMENT ON TABLE gold.dim_sales_persons IS
    'Sales team members. Grain: one row per sales person. Source: Farvision DimBookingMaster. Owner: Sales.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_dim_sales_persons_farvision
    ON gold.dim_sales_persons (farvision_sales_person_id);

-- ============================================================
-- DIMENSION: Lead Sources
-- Source: VJ Sales App lead_sources + channel partner records
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.dim_lead_sources (
    source_key SERIAL PRIMARY KEY,
    source_name VARCHAR(100) NOT NULL,     -- walk-in, referral, digital-fb, digital-google, CP-BrokerName
    source_category VARCHAR(50),           -- organic, paid, referral, channel_partner
    channel_partner_name VARCHAR(255),     -- NULL if not channel partner
    cp_id UUID                             -- Channel partner reference UUID
);

COMMENT ON TABLE gold.dim_lead_sources IS
    'Lead acquisition channels. Grain: one row per source. Source: VJ Sales App + CP records. Owner: Marketing.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_dim_lead_sources_source_name
    ON gold.dim_lead_sources (source_name);
CREATE INDEX IF NOT EXISTS idx_dim_lead_sources_cp
    ON gold.dim_lead_sources (cp_id);

-- ============================================================
-- FACT: Lead Pipeline (every stage transition)
-- Source: VJ Sales App leads + allotment_payments
-- Tracks the journey from inquiry through site visit,
-- negotiation, booking, agreement, registration or cancellation.
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.fact_lead_pipeline (
    pipeline_event_id SERIAL PRIMARY KEY,
    vjsales_lead_id UUID,                  -- VJ Sales App lead UUID
    vjsales_allotment_id UUID,             -- VJ Sales AllotmentPayment UUID
    customer_key INT REFERENCES gold.dim_customers,
    project_key INT REFERENCES gold.dim_projects,
    unit_key INT REFERENCES gold.dim_units,
    sales_person_key INT REFERENCES gold.dim_sales_persons,
    source_key INT REFERENCES gold.dim_lead_sources,
    event_date_key INT REFERENCES gold.dim_date,

    -- Pipeline stage this event represents
    pipeline_stage VARCHAR(50) NOT NULL,   -- inquiry, site_visit, negotiation, booking, agreement, registered, cancelled
    previous_stage VARCHAR(50),
    days_in_previous_stage INT,

    -- Allotment status from VJ Sales AllotmentPayment
    allotment_status VARCHAR(50),          -- 'Payment Complete','Agreement Done','Booked','Cancelled', etc.

    -- Booking/Agreement details (NULL until relevant stage)
    agreement_value DECIMAL(15, 2),
    booking_amount DECIMAL(15, 2),

    event_timestamp TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE gold.fact_lead_pipeline IS
    'Lead lifecycle stage transitions. Grain: one row per stage change per lead. '
    'Append-only. Source: VJ Sales App leads + allotments. Owner: Sales.';

CREATE INDEX IF NOT EXISTS idx_fact_pipeline_date
    ON gold.fact_lead_pipeline (event_date_key);
CREATE INDEX IF NOT EXISTS idx_fact_pipeline_project
    ON gold.fact_lead_pipeline (project_key);
CREATE INDEX IF NOT EXISTS idx_fact_pipeline_stage
    ON gold.fact_lead_pipeline (pipeline_stage);
CREATE INDEX IF NOT EXISTS idx_fact_pipeline_customer
    ON gold.fact_lead_pipeline (customer_key);
CREATE INDEX IF NOT EXISTS idx_fact_pipeline_allotment_status
    ON gold.fact_lead_pipeline (allotment_status);

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

-- ============================================================
-- SNAPSHOT: Outstanding (aging buckets for overdue amounts)
-- Source: Farvision CRMG.FactDueDatewiseOutstanding
-- Pre-aggregated aging analysis per customer+unit. Used for
-- collections dashboards and overdue reporting.
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
-- Current state of each unit in the sales inventory,
-- including pricing and availability status.
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
-- Tracks customer-to-customer referrals from the owner portal.
-- Referral lifecycle: Unclaimed → Claimed → Site Visit Done →
-- Agreement Done, with points earned at each milestone.
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

-- ============================================================
-- FACT: Daily Funnel Snapshot (for trend analysis)
-- Source: Aggregated daily from fact_lead_pipeline + fact_bookings
-- Pre-computed daily counts per project for fast dashboard queries.
-- Conversion rates are computed via gold.v_conversion_rates view.
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

-- ============================================================
-- VIEW: Conversion Rates (derived from funnel counts)
-- Computed on-the-fly to avoid storing derived metrics in facts.
-- ============================================================
CREATE OR REPLACE VIEW gold.v_conversion_rates AS
SELECT
    f.snapshot_date_key,
    f.project_key,
    p.project_name,
    d.full_date AS snapshot_date,
    f.total_inquiries,
    f.total_site_visits,
    f.total_bookings,
    f.total_agreements,
    ROUND(
        f.total_site_visits * 100.0 / NULLIF(f.total_inquiries, 0), 2
    ) AS inquiry_to_visit_rate,
    ROUND(
        f.total_bookings * 100.0 / NULLIF(f.total_site_visits, 0), 2
    ) AS visit_to_booking_rate,
    ROUND(
        f.total_agreements * 100.0 / NULLIF(f.total_bookings, 0), 2
    ) AS booking_to_agreement_rate
FROM gold.fact_daily_funnel_snapshot f
JOIN gold.dim_projects p ON f.project_key = p.project_key
JOIN gold.dim_date d ON f.snapshot_date_key = d.date_key;
