-- ============================================================
-- ASK VJ: Gold Layer Schema (Business-Ready Star Schema)
-- ============================================================
-- Optimized for LLM SQL generation. Self-documenting names.
-- Pre-calculated metrics. Simple JOINs only.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS gold;

-- ============================================================
-- DIMENSION: Date (supports natural language time filtering)
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
    is_weekend BOOLEAN,
    is_month_end BOOLEAN
);

-- ============================================================
-- DIMENSION: Projects
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.dim_projects (
    project_key SERIAL PRIMARY KEY,
    project_name VARCHAR(255) NOT NULL,    -- Canonical name from crosswalk
    phase_name VARCHAR(100),
    location VARCHAR(255),
    rera_number VARCHAR(100),
    total_units INT,
    launch_date DATE,
    status VARCHAR(50),                    -- active, completed, upcoming
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- DIMENSION: Units (individual flats/shops)
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.dim_units (
    unit_key SERIAL PRIMARY KEY,
    project_key INT NOT NULL REFERENCES gold.dim_projects,
    unit_no VARCHAR(50) NOT NULL,
    wing VARCHAR(50),
    floor INT,
    unit_type VARCHAR(50),                 -- 1BHK, 2BHK, 3BHK, shop, office
    carpet_area_sqft DECIMAL(10, 2),
    base_price DECIMAL(15, 2),
    current_status VARCHAR(50),            -- available, booked, agreement, registered, cancelled
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dim_units_project
    ON gold.dim_units (project_key);

-- ============================================================
-- DIMENSION: Customers (unified from entity_map)
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.dim_customers (
    customer_key SERIAL PRIMARY KEY,
    unified_customer_id UUID NOT NULL,     -- From silver.entity_map
    customer_name VARCHAR(255),
    phone VARCHAR(50),
    email VARCHAR(255),
    first_inquiry_date DATE,
    lead_source VARCHAR(100),
    source_system_origin VARCHAR(20),      -- Where first seen: vjsales, farvision
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dim_customers_unified
    ON gold.dim_customers (unified_customer_id);

-- ============================================================
-- DIMENSION: Sales Persons
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.dim_sales_persons (
    sales_person_key SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    team VARCHAR(100),
    region VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE
);

-- ============================================================
-- DIMENSION: Lead Sources
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.dim_lead_sources (
    source_key SERIAL PRIMARY KEY,
    source_name VARCHAR(100) NOT NULL,     -- walk-in, referral, digital-fb, digital-google, CP-BrokerName
    source_category VARCHAR(50),           -- organic, paid, referral, channel_partner
    channel_partner_name VARCHAR(255)      -- NULL if not channel partner
);

-- ============================================================
-- FACT: Lead Pipeline (every stage transition)
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.fact_lead_pipeline (
    pipeline_event_id SERIAL PRIMARY KEY,
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

    -- Booking/Agreement details (NULL until relevant stage)
    agreement_value DECIMAL(15, 2),
    booking_amount DECIMAL(15, 2),

    event_timestamp TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fact_pipeline_date
    ON gold.fact_lead_pipeline (event_date_key);
CREATE INDEX IF NOT EXISTS idx_fact_pipeline_project
    ON gold.fact_lead_pipeline (project_key);
CREATE INDEX IF NOT EXISTS idx_fact_pipeline_stage
    ON gold.fact_lead_pipeline (pipeline_stage);

-- ============================================================
-- FACT: Collections (demands and receipts)
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.fact_collections (
    collection_id SERIAL PRIMARY KEY,
    customer_key INT REFERENCES gold.dim_customers,
    project_key INT REFERENCES gold.dim_projects,
    unit_key INT REFERENCES gold.dim_units,
    transaction_date_key INT REFERENCES gold.dim_date,

    transaction_type VARCHAR(20) NOT NULL,  -- 'demand' or 'receipt'
    amount DECIMAL(15, 2) NOT NULL,
    payment_mode VARCHAR(50),               -- NULL for demands
    milestone VARCHAR(255),                 -- Construction milestone for demand letters

    -- Pre-calculated running totals (per customer+unit)
    cumulative_demanded DECIMAL(15, 2),
    cumulative_collected DECIMAL(15, 2),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fact_collections_date
    ON gold.fact_collections (transaction_date_key);
CREATE INDEX IF NOT EXISTS idx_fact_collections_project
    ON gold.fact_collections (project_key);
CREATE INDEX IF NOT EXISTS idx_fact_collections_type
    ON gold.fact_collections (transaction_type);

-- ============================================================
-- FACT: Daily Funnel Snapshot (for trend analysis)
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

    -- Pre-calculated conversion rates (as percentages)
    inquiry_to_visit_rate DECIMAL(5, 2),
    visit_to_booking_rate DECIMAL(5, 2),
    booking_to_agreement_rate DECIMAL(5, 2),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(snapshot_date_key, project_key)
);
