-- ============================================================
-- ASK VJ: Bronze Layer Schema (Raw Staging)
-- ============================================================
-- 1:1 copies of source system tables. Append-only.
-- No transformations. Full audit trail with sync metadata.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS bronze;

-- ============================================================
-- VJ SALES APP — Leads
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_vjsales_leads (
    _sync_id BIGSERIAL PRIMARY KEY,
    _synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'vjsales',
    _batch_id UUID,

    -- Original columns (preserved as-is from source)
    lead_id INT NOT NULL,
    lead_name VARCHAR(255),
    phone VARCHAR(50),
    email VARCHAR(255),
    source VARCHAR(100),         -- walk-in, referral, digital, channel_partner
    status VARCHAR(50),          -- new, contacted, site_visit, negotiation, booked, lost
    assigned_to VARCHAR(255),
    project_interest VARCHAR(255),
    unit_interest VARCHAR(100),
    remarks TEXT,
    created_date TIMESTAMP,
    updated_date TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_stg_vjsales_leads_lead_id
    ON bronze.stg_vjsales_leads (lead_id);
CREATE INDEX IF NOT EXISTS idx_stg_vjsales_leads_synced
    ON bronze.stg_vjsales_leads (_synced_at);

-- ============================================================
-- VJ SALES APP — Site Visits
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_vjsales_site_visits (
    _sync_id BIGSERIAL PRIMARY KEY,
    _synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'vjsales',
    _batch_id UUID,

    visit_id INT NOT NULL,
    lead_id INT NOT NULL,
    visit_date DATE,
    project_name VARCHAR(255),
    accompanied_by VARCHAR(255),  -- sales person
    feedback TEXT,
    next_follow_up DATE,
    created_date TIMESTAMP,
    updated_date TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_stg_vjsales_visits_lead_id
    ON bronze.stg_vjsales_site_visits (lead_id);

-- ============================================================
-- VJ SALES APP — Bookings
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_vjsales_bookings (
    _sync_id BIGSERIAL PRIMARY KEY,
    _synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'vjsales',
    _batch_id UUID,

    booking_id INT NOT NULL,
    lead_id INT NOT NULL,
    project_name VARCHAR(255),
    unit_no VARCHAR(50),
    wing VARCHAR(50),
    floor INT,
    unit_type VARCHAR(50),        -- 1BHK, 2BHK, 3BHK, shop, office
    carpet_area DECIMAL(10, 2),
    agreement_value DECIMAL(15, 2),
    booking_amount DECIMAL(15, 2),
    booking_date DATE,
    status VARCHAR(50),            -- booked, agreement, registered, cancelled
    cancellation_date DATE,
    cancellation_reason VARCHAR(500),
    sales_person VARCHAR(255),
    channel_partner VARCHAR(255),
    created_date TIMESTAMP,
    updated_date TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_stg_vjsales_bookings_lead_id
    ON bronze.stg_vjsales_bookings (lead_id);
CREATE INDEX IF NOT EXISTS idx_stg_vjsales_bookings_booking_id
    ON bronze.stg_vjsales_bookings (booking_id);

-- ============================================================
-- FARVISION ERP — Receipts (Payments received)
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_farvision_receipts (
    _sync_id BIGSERIAL PRIMARY KEY,
    _synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id UUID,

    receipt_id INT NOT NULL,
    customer_name VARCHAR(255),
    project_code VARCHAR(50),
    unit_no VARCHAR(50),
    amount DECIMAL(15, 2),
    receipt_date DATE,
    payment_mode VARCHAR(50),      -- cheque, neft, rtgs, cash, upi
    cheque_no VARCHAR(50),
    bank_name VARCHAR(100),
    narration TEXT,
    created_date TIMESTAMP,
    updated_date TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_stg_farvision_receipts_unit
    ON bronze.stg_farvision_receipts (project_code, unit_no);

-- ============================================================
-- FARVISION ERP — Demand Letters
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.stg_farvision_demands (
    _sync_id BIGSERIAL PRIMARY KEY,
    _synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_system VARCHAR(20) DEFAULT 'farvision',
    _batch_id UUID,

    demand_id INT NOT NULL,
    customer_name VARCHAR(255),
    project_code VARCHAR(50),
    unit_no VARCHAR(50),
    milestone VARCHAR(255),
    demand_amount DECIMAL(15, 2),
    demand_date DATE,
    due_date DATE,
    status VARCHAR(50),            -- raised, partially_paid, paid, overdue
    created_date TIMESTAMP,
    updated_date TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_stg_farvision_demands_unit
    ON bronze.stg_farvision_demands (project_code, unit_no);

-- ============================================================
-- SYNC METADATA — Tracks ETL run history
-- ============================================================
CREATE TABLE IF NOT EXISTS bronze.sync_log (
    sync_id SERIAL PRIMARY KEY,
    batch_id UUID NOT NULL,
    source_system VARCHAR(50) NOT NULL,
    table_name VARCHAR(100) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    records_extracted INT DEFAULT 0,
    last_source_timestamp TIMESTAMP,  -- watermark for incremental pulls
    status VARCHAR(20) DEFAULT 'running',  -- running, success, failed
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_sync_log_source
    ON bronze.sync_log (source_system, table_name);
