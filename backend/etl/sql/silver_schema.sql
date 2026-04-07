-- ============================================================
-- ASK VJ: Silver Layer Schema (Entity Resolution + Warehouse)
-- ============================================================
-- Links records across source systems (Farvision, VJ Sales App,
-- VJOP) into unified entities using shared IDs.
--
-- KEY INSIGHT: The three source systems share common identifiers
-- — BookingId, UnitId, and BUId — so entity resolution is
-- primarily ID-based joins, NOT fuzzy name matching.
--
-- Resolution priority:
--   1. Exact ID joins (BookingId, UnitId, BUId, LedgerId)
--   2. Fuzzy fallback ONLY for unconverted leads that lack IDs
-- ============================================================

CREATE SCHEMA IF NOT EXISTS silver;

-- pg_trgm is retained ONLY as a fallback for unconverted leads
-- (pre-booking leads that have no BookingId/UnitId to join on).
-- All converted bookings resolve via exact ID joins below.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- PROJECT CROSSWALK
-- ============================================================
-- Maps BUId (Farvision's ENGG.DimBusinessUnit.BusinessUnitId)
-- to VJ Sales project names and VJOP project references.
-- BUId is the universal project identifier across all systems.
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.project_crosswalk (
    crosswalk_id        SERIAL PRIMARY KEY,
    canonical_name      VARCHAR(255) NOT NULL,  -- Unified project name for gold layer
    phase_name          VARCHAR(100),

    -- Farvision: the universal project key
    farvision_bu_id     INT NOT NULL,           -- ENGG.DimBusinessUnit.BusinessUnitId

    -- VJ Sales App identifiers
    vjsales_project_name VARCHAR(255),

    -- VJOP identifiers
    vjop_project_id     INT,
    vjop_project_name   VARCHAR(255),

    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(farvision_bu_id),
    UNIQUE(vjsales_project_name),
    UNIQUE(vjop_project_id)
);

CREATE INDEX IF NOT EXISTS idx_crosswalk_bu_id
    ON silver.project_crosswalk (farvision_bu_id);
CREATE INDEX IF NOT EXISTS idx_crosswalk_vjsales_project
    ON silver.project_crosswalk (vjsales_project_name);
CREATE INDEX IF NOT EXISTS idx_crosswalk_vjop_project
    ON silver.project_crosswalk (vjop_project_id);

-- ============================================================
-- ENTITY MAP
-- ============================================================
-- Links customer/booking identities across systems using
-- direct ID joins. Each row represents one resolved identity
-- that may span Farvision, VJ Sales, and VJOP.
--
-- Resolution is ID-based:
--   - BookingId joins Farvision bookings to VJ Sales allotments
--   - UnitId joins unit records across systems
--   - BUId anchors everything to a project via project_crosswalk
--   - LedgerId identifies the customer in Farvision financials
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.entity_map (
    entity_map_id           SERIAL PRIMARY KEY,
    unified_customer_id     UUID DEFAULT gen_random_uuid(),

    -- Farvision ERP identifiers (the primary system of record)
    farvision_booking_id    INT,        -- CRMG.DimBookingMaster.BookingId
    farvision_unit_id       INT,        -- CRMG.DimUnitMaster.UnitId
    farvision_bu_id         INT,        -- ENGG.DimBusinessUnit.BusinessUnitId
    farvision_ledger_id     INT,        -- FIN.DimLedger.LedgerId (customer ID)

    -- VJ Sales App identifiers
    vjsales_lead_id         UUID,       -- Leads.leadId
    vjsales_allotment_id    UUID,       -- AllotmentPayment.allotmentPaymentId
    vjsales_unit_id         UUID,       -- Inventory.unitId

    -- VJOP identifiers
    vjop_customer_id        INT,        -- dbo.customers.id
    vjop_lead_id            INT,        -- dbo.leads.id

    -- Resolution metadata
    match_method            VARCHAR(50) NOT NULL,
        -- 'booking_id_exact'  — matched on BookingId across systems
        -- 'unit_id_exact'     — matched on UnitId across systems
        -- 'lead_id_exact'     — matched on lead/customer ID
        -- 'fuzzy_fallback'    — fuzzy name/phone match (unconverted leads only)
        -- 'manual'            — manually resolved by ops team
    match_confidence        DECIMAL(3, 2) NOT NULL DEFAULT 1.00,  -- 0.00 to 1.00
    resolved_by             VARCHAR(50) NOT NULL DEFAULT 'etl_auto',
    resolved_at             TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    notes                   TEXT,

    UNIQUE(farvision_booking_id),
    UNIQUE(vjsales_lead_id),
    UNIQUE(vjsales_allotment_id)
);

-- Indexes on the unified ID (used by gold layer joins)
CREATE INDEX IF NOT EXISTS idx_entity_map_unified
    ON silver.entity_map (unified_customer_id);

-- Indexes on Farvision IDs (primary join keys)
CREATE INDEX IF NOT EXISTS idx_entity_map_fv_booking
    ON silver.entity_map (farvision_booking_id);
CREATE INDEX IF NOT EXISTS idx_entity_map_fv_unit
    ON silver.entity_map (farvision_unit_id);
CREATE INDEX IF NOT EXISTS idx_entity_map_fv_bu
    ON silver.entity_map (farvision_bu_id);
CREATE INDEX IF NOT EXISTS idx_entity_map_fv_ledger
    ON silver.entity_map (farvision_ledger_id);

-- Indexes on VJ Sales IDs
CREATE INDEX IF NOT EXISTS idx_entity_map_vjs_lead
    ON silver.entity_map (vjsales_lead_id);
CREATE INDEX IF NOT EXISTS idx_entity_map_vjs_allotment
    ON silver.entity_map (vjsales_allotment_id);
CREATE INDEX IF NOT EXISTS idx_entity_map_vjs_unit
    ON silver.entity_map (vjsales_unit_id);

-- Indexes on VJOP IDs
CREATE INDEX IF NOT EXISTS idx_entity_map_vjop_customer
    ON silver.entity_map (vjop_customer_id);
CREATE INDEX IF NOT EXISTS idx_entity_map_vjop_lead
    ON silver.entity_map (vjop_lead_id);

-- Index on match method for auditing/monitoring
CREATE INDEX IF NOT EXISTS idx_entity_map_method
    ON silver.entity_map (match_method);

-- ============================================================
-- ENTITY RESOLUTION QUEUE
-- ============================================================
-- Fuzzy-match fallback for records that CANNOT be joined by ID.
-- This applies ONLY to unconverted leads (pre-booking stage)
-- that exist in VJ Sales but have no BookingId/UnitId yet,
-- so there is no shared key to join on.
--
-- Once a lead converts to a booking, it gets a BookingId and
-- moves to entity_map via exact ID join instead.
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.entity_resolution_queue (
    queue_id                SERIAL PRIMARY KEY,

    -- Candidate from VJ Sales (unconverted lead)
    vjsales_lead_id         UUID,
    vjsales_lead_name       VARCHAR(255),
    vjsales_phone           VARCHAR(50),
    vjsales_email           VARCHAR(255),
    vjsales_project         VARCHAR(255),

    -- Candidate from Farvision (potential match)
    farvision_customer_name VARCHAR(255),
    farvision_ledger_id     INT,
    farvision_bu_id         INT,

    -- Candidate from VJOP (potential match)
    vjop_customer_id        INT,
    vjop_lead_id            INT,

    -- Fuzzy match details
    candidate_confidence    DECIMAL(3, 2),
    match_method            VARCHAR(50),    -- 'name_trgm', 'phone_exact', 'email_exact'
    reason                  VARCHAR(500),   -- Why exact ID join was not possible

    -- Review status
    status                  VARCHAR(20) DEFAULT 'pending',  -- pending, confirmed, rejected, skipped
    reviewed_by             VARCHAR(100),
    reviewed_at             TIMESTAMP WITH TIME ZONE,

    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_resolution_queue_status
    ON silver.entity_resolution_queue (status);
CREATE INDEX IF NOT EXISTS idx_resolution_queue_vjsales_lead
    ON silver.entity_resolution_queue (vjsales_lead_id);
CREATE INDEX IF NOT EXISTS idx_resolution_queue_fv_ledger
    ON silver.entity_resolution_queue (farvision_ledger_id);


-- ============================================================
-- ============================================================
--   WAREHOUSE DIMENSION & FACT TABLES (from relations.xlsx)
-- ============================================================
-- ============================================================

-- ============================================================
-- CROSS-REFERENCE MAP (value standardization)
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.xref_map (
    xref_map_skey UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    mapping_name VARCHAR(256),
    from_domain VARCHAR(256),
    to_domain VARCHAR(256),
    from_value VARCHAR(256),
    to_value VARCHAR(256),
    is_active BOOLEAN DEFAULT TRUE,
    dw_load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dw_update_ts TIMESTAMP,
    dw_created_by VARCHAR(256)
);

-- ============================================================
-- LOV (List of Values) — centralized status/type lookups
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.dim_lov (
    lov_skey UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    lov_type VARCHAR(256) NOT NULL,
    lov_code VARCHAR(256),
    lov_value VARCHAR(256) NOT NULL,
    lov_description VARCHAR(4000),
    is_active BOOLEAN DEFAULT TRUE,
    src_created_ts TIMESTAMP,
    src_updated_ts TIMESTAMP,
    dw_load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dw_update_ts TIMESTAMP,
    dw_created_by VARCHAR(256)
);

-- ============================================================
-- CALENDAR DIMENSION (replaces gold.dim_date)
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.dim_calendar (
    calendar_skey VARCHAR(256) PRIMARY KEY,
    calendar_dt DATE NOT NULL,
    day_of_month_num INTEGER,
    day_of_week_num INTEGER,
    day_name VARCHAR(256),
    is_weekend BOOLEAN DEFAULT FALSE,
    week_of_year_num INTEGER,
    week_of_month_num INTEGER,
    week_start_dt DATE,
    week_end_dt DATE,
    month_num INTEGER,
    month_name VARCHAR(256),
    month_short_name VARCHAR(256),
    month_start_dt DATE,
    month_end_dt DATE,
    quarter_num INTEGER,
    quarter_start_dt DATE,
    quarter_end_dt DATE,
    year_num INTEGER,
    year_start_dt DATE,
    year_end_dt DATE,
    month_year VARCHAR(256),
    week_year VARCHAR(256),
    fiscal_day INTEGER,
    fiscal_week INTEGER,
    fiscal_month INTEGER,
    fiscal_quarter INTEGER,
    fiscal_year INTEGER,
    fiscal_month_year VARCHAR(256),
    fiscal_week_year VARCHAR(256),
    fiscal_year_start_dt DATE,
    fiscal_year_end_dt DATE,
    is_holiday BOOLEAN DEFAULT FALSE,
    holiday_name VARCHAR(256),
    holiday_type VARCHAR(256),
    is_sale_event BOOLEAN DEFAULT FALSE,
    sale_event_name VARCHAR(256),
    dw_load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dw_update_ts TIMESTAMP,
    dw_created_by VARCHAR(256),
    is_active BOOLEAN DEFAULT TRUE
);

-- ============================================================
-- COUNTRY DIMENSION
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.dim_country (
    country_skey UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    country_iso_2 VARCHAR(256),
    country_iso_3 VARCHAR(256),
    country_full_name VARCHAR(256),
    currency VARCHAR(256),
    dw_load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dw_update_ts TIMESTAMP,
    dw_created_by VARCHAR(256)
);

-- ============================================================
-- LOCATION DIMENSION
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.dim_location (
    location_skey UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    pin_code VARCHAR(256),
    circle_name VARCHAR(256),
    region_name VARCHAR(256),
    division_name VARCHAR(256),
    area_name VARCHAR(256),
    district VARCHAR(256),
    state VARCHAR(256),
    latitude VARCHAR(256),
    longitude VARCHAR(256),
    country_skey UUID REFERENCES silver.dim_country(country_skey),
    dw_load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dw_update_ts TIMESTAMP,
    dw_created_by VARCHAR(256)
);

-- ============================================================
-- EXTERNAL REFERRER DIMENSION
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.dim_external_referrer (
    external_referrer_skey UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    referrer_name VARCHAR(256),
    referrer_type VARCHAR(256),
    referrer_source VARCHAR(256),
    src_created_ts TIMESTAMP,
    src_updated_ts TIMESTAMP,
    dw_load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dw_update_ts TIMESTAMP,
    dw_created_by VARCHAR(256)
);

-- ============================================================
-- VIRTUAL ACCOUNT DIMENSION
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.dim_virtual_account (
    virtual_account_skey UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    bank_account_number VARCHAR(256),
    bank_ifsc_code VARCHAR(256),
    bank_upi_id VARCHAR(256),
    bank_beneficiary_name VARCHAR(256),
    status VARCHAR(256),
    src_created_dt DATE,
    src_created_ts TIMESTAMP,
    src_updated_ts TIMESTAMP,
    dw_load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dw_update_ts TIMESTAMP,
    dw_created_by VARCHAR(256)
);

-- ============================================================
-- PROJECT DIMENSION
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.dim_project (
    project_skey UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id UUID,
    bu_id VARCHAR(256),
    project_name VARCHAR(256),
    project_short_code VARCHAR(256),
    project_type VARCHAR(256),
    rera_number VARCHAR(256),
    address_line_1 VARCHAR(4000),
    address_line_2 VARCHAR(4000),
    address_line_3 VARCHAR(4000),
    city VARCHAR(256),
    state VARCHAR(256),
    country VARCHAR(256),
    pincode VARCHAR(256),
    latitude VARCHAR(256),
    longitude VARCHAR(256),
    start_after DATE,
    start_dt DATE,
    booking_sdr_amt NUMERIC(18,4),
    booking_ocr_amt NUMERIC(18,4),
    booking_gst_amt NUMERIC(18,4),
    booking_total_amt NUMERIC(18,4),
    legal_charge_amt NUMERIC(18,4),
    registration_charge_amt NUMERIC(18,4),
    is_completed BOOLEAN DEFAULT FALSE,
    is_published BOOLEAN DEFAULT FALSE,
    is_female_discount_applicable BOOLEAN DEFAULT FALSE,
    is_commercial BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT FALSE,
    ocr_bank_jd JSON,
    ocr_ledger_jd JSON,
    gst_bank_jd JSON,
    gst_ledger_jd JSON,
    ocr_bank JSON,
    ocr_ledger JSON,
    gst_bank JSON,
    gst_ledger JSON,
    jd_bu_id VARCHAR(256),
    sdr_per VARCHAR(256),
    project_created_by VARCHAR(256),
    src_created_dt DATE,
    src_created_ts TIMESTAMP,
    src_updated_ts TIMESTAMP,
    dw_load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dw_update_ts TIMESTAMP,
    dw_created_by VARCHAR(256)
);

COMMENT ON TABLE silver.dim_project IS 'Real estate projects developed by VJ. bu_id = Farvision BusinessUnitId.';
CREATE INDEX IF NOT EXISTS idx_dim_project_bu_id ON silver.dim_project (bu_id);
CREATE INDEX IF NOT EXISTS idx_dim_project_name ON silver.dim_project (project_name);

-- ============================================================
-- PROJECT UNIT DIMENSION
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.dim_project_unit (
    project_unit_skey UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    project_skey UUID REFERENCES silver.dim_project(project_skey),
    unit_id UUID,
    fv_unit_id VARCHAR(256),
    wing_name VARCHAR(256),
    floor_no VARCHAR(256),
    unit_no VARCHAR(256),
    saleable_area NUMERIC(18,4),
    chargeable_area NUMERIC(18,4),
    total_cost_amt NUMERIC(18,4),
    bsp_amt NUMERIC(18,4),
    gst_amt NUMERIC(18,4),
    sdr_amt NUMERIC(18,4),
    ocr_amt NUMERIC(18,4),
    reg_amt NUMERIC(18,4),
    unit_status VARCHAR(256),
    unit_type VARCHAR(256),
    unit_sub_type VARCHAR(256),
    display_unit_type VARCHAR(256),
    sold_dt DATE,
    paid_amt NUMERIC(18,4),
    fv_status VARCHAR(256),
    is_sanctioned BOOLEAN,
    src_created_dt DATE,
    src_created_ts TIMESTAMP,
    src_updated_ts TIMESTAMP,
    dw_load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dw_update_ts TIMESTAMP,
    dw_created_by VARCHAR(256)
);

COMMENT ON TABLE silver.dim_project_unit IS 'Individual units (flats/shops) within projects. fv_unit_id = Farvision UnitId.';
CREATE INDEX IF NOT EXISTS idx_dim_project_unit_project ON silver.dim_project_unit (project_skey);
CREATE INDEX IF NOT EXISTS idx_dim_project_unit_fv ON silver.dim_project_unit (fv_unit_id);

-- ============================================================
-- EMPLOYEE DIMENSION
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.dim_employee (
    employee_skey UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    employee_id UUID,
    employee_name VARCHAR(256),
    email VARCHAR(256),
    contact_number VARCHAR(256),
    manager_id UUID,
    manager_skey UUID REFERENCES silver.dim_employee(employee_skey),
    role_name VARCHAR(256),
    crm_designation VARCHAR(256),
    is_crm_user BOOLEAN,
    is_team_lead BOOLEAN,
    is_active BOOLEAN,
    target_amt NUMERIC(18,4),
    src_created_dt DATE,
    src_created_ts TIMESTAMP,
    src_updated_ts TIMESTAMP,
    dw_load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dw_update_ts TIMESTAMP,
    dw_created_by VARCHAR(256)
);

COMMENT ON TABLE silver.dim_employee IS 'VJ employees: sales managers, project heads, CRM users.';

-- ============================================================
-- CHANNEL PARTNER DIMENSION
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.dim_channel_partner (
    channel_partner_skey UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    referred_by_employee_skey UUID REFERENCES silver.dim_employee(employee_skey),
    cp_id UUID,
    cp_display_id VARCHAR(256),
    cp_type VARCHAR(256),
    contact_number VARCHAR(256),
    email VARCHAR(256),
    type_of_agent VARCHAR(256),
    billing_name VARCHAR(256),
    gst_business_name VARCHAR(256),
    gst_legal_name VARCHAR(256),
    proprietorship_name VARCHAR(256),
    is_gst_applicable BOOLEAN,
    msme_type VARCHAR(256),
    msme_number VARCHAR(256),
    approval_status VARCHAR(256),
    rejection_reason VARCHAR(4000),
    is_disabled BOOLEAN,
    ledger_id VARCHAR(256),
    bank_account_holder_name VARCHAR(256),
    bank_account_number VARCHAR(256),
    bank_ifsc_code VARCHAR(256),
    bank_branch_name VARCHAR(256),
    rera_start_dt DATE,
    rera_end_dt DATE,
    src_created_dt DATE,
    src_created_ts TIMESTAMP,
    src_updated_ts TIMESTAMP,
    dw_load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dw_update_ts TIMESTAMP,
    dw_created_by VARCHAR(256)
);

COMMENT ON TABLE silver.dim_channel_partner IS 'External brokers/channel partners who refer leads.';

-- ============================================================
-- CHANNEL PARTNER FOS (Field Officer) DIMENSION
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.dim_channel_partner_fos (
    channel_partner_fos_skey UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    channel_partner_skey UUID REFERENCES silver.dim_channel_partner(channel_partner_skey),
    fos_id UUID,
    name VARCHAR(256),
    contact_number VARCHAR(256),
    email VARCHAR(256),
    approval_status VARCHAR(256),
    rejection_reason VARCHAR(4000),
    fos_display_id VARCHAR(256),
    bank_account_holder_name VARCHAR(256),
    bank_account_number VARCHAR(256),
    bank_ifsc_code VARCHAR(256),
    bank_branch_name VARCHAR(256),
    is_disabled BOOLEAN,
    src_created_dt DATE,
    src_created_ts TIMESTAMP,
    src_updated_ts TIMESTAMP,
    dw_load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dw_update_ts TIMESTAMP,
    dw_created_by VARCHAR(256)
);

COMMENT ON TABLE silver.dim_channel_partner_fos IS 'Field officers under channel partners.';

-- ============================================================
-- BUYER DIMENSION (unified customer)
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.dim_buyer (
    buyer_skey UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nationality_country_skey UUID REFERENCES silver.dim_country(country_skey),
    buyer_id UUID,
    op_user_id VARCHAR(256),
    name VARCHAR(256),
    contact_number VARCHAR(256),
    alternate_contact_number VARCHAR(256),
    email VARCHAR(256),
    gender VARCHAR(256),
    role VARCHAR(256),
    is_verified BOOLEAN,
    dob VARCHAR(256),
    pan VARCHAR(256),
    is_pan_verified BOOLEAN,
    is_survey_completed BOOLEAN,
    rm_name VARCHAR(256),
    op_rm_id VARCHAR(256),
    src_created_dt DATE,
    src_created_ts TIMESTAMP,
    src_updated_ts TIMESTAMP,
    dw_load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dw_update_ts TIMESTAMP,
    dw_created_by VARCHAR(256)
);

COMMENT ON TABLE silver.dim_buyer IS 'Unified buyer/customer. buyer_id = VJ Sales personId. op_user_id = VJOP customer ID.';

-- ============================================================
-- FACT: LEADS
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.fact_lead (
    fact_lead_skey UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    lead_id UUID,
    buyer_skey UUID REFERENCES silver.dim_buyer(buyer_skey),
    project_skey UUID REFERENCES silver.dim_project(project_skey),
    channel_partner_skey UUID REFERENCES silver.dim_channel_partner(channel_partner_skey),
    channel_partner_fos_skey UUID REFERENCES silver.dim_channel_partner_fos(channel_partner_fos_skey),
    lead_dt_skey VARCHAR(256) REFERENCES silver.dim_calendar(calendar_skey),
    project_head_employee_skey UUID REFERENCES silver.dim_employee(employee_skey),
    sales_manager_employee_skey UUID REFERENCES silver.dim_employee(employee_skey),
    claimed_by_employee_skey UUID REFERENCES silver.dim_employee(employee_skey),
    referred_by_employee_skey UUID REFERENCES silver.dim_employee(employee_skey),
    external_referrer_skey UUID REFERENCES silver.dim_external_referrer(external_referrer_skey),
    referred_by_buyer_skey UUID REFERENCES silver.dim_buyer(buyer_skey),
    lead_status_lov_skey UUID REFERENCES silver.dim_lov(lov_skey),
    lead_type_lov_skey UUID REFERENCES silver.dim_lov(lov_skey),
    lead_sub_type_lov_skey UUID REFERENCES silver.dim_lov(lov_skey),
    lead_category_lov_skey UUID REFERENCES silver.dim_lov(lov_skey),
    lead_response_lov_skey UUID REFERENCES silver.dim_lov(lov_skey),
    verification_status_lov_skey UUID REFERENCES silver.dim_lov(lov_skey),
    referrer_type_lov_skey UUID REFERENCES silver.dim_lov(lov_skey),
    virtual_account_skey UUID REFERENCES silver.dim_virtual_account(virtual_account_skey),
    lead_display_id VARCHAR(256),
    display_dt DATE,
    src_created_dt DATE,
    src_created_ts TIMESTAMP,
    src_updated_ts TIMESTAMP,
    dw_load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dw_update_ts TIMESTAMP,
    dw_created_by VARCHAR(256)
);

COMMENT ON TABLE silver.fact_lead IS 'All customer enquiries/leads. One row per lead.';
CREATE INDEX IF NOT EXISTS idx_fact_lead_buyer ON silver.fact_lead (buyer_skey);
CREATE INDEX IF NOT EXISTS idx_fact_lead_project ON silver.fact_lead (project_skey);
CREATE INDEX IF NOT EXISTS idx_fact_lead_date ON silver.fact_lead (lead_dt_skey);
CREATE INDEX IF NOT EXISTS idx_fact_lead_status ON silver.fact_lead (lead_status_lov_skey);

-- ============================================================
-- FACT: SITE VISITS
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.fact_site_visit (
    fact_site_visit_skey UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    site_visit_id UUID,
    fact_lead_skey UUID REFERENCES silver.fact_lead(fact_lead_skey),
    project_skey UUID REFERENCES silver.dim_project(project_skey),
    employee_skey UUID REFERENCES silver.dim_employee(employee_skey),
    channel_partner_skey UUID REFERENCES silver.dim_channel_partner(channel_partner_skey),
    channel_partner_fos_skey UUID REFERENCES silver.dim_channel_partner_fos(channel_partner_fos_skey),
    site_visit_dt_skey VARCHAR(256) REFERENCES silver.dim_calendar(calendar_skey),
    site_visit_ts TIMESTAMP,
    photo_url VARCHAR(4000),
    remarks VARCHAR(4000),
    mode VARCHAR(256),
    src_created_dt DATE,
    src_created_ts TIMESTAMP,
    src_updated_ts TIMESTAMP,
    dw_load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dw_update_ts TIMESTAMP,
    dw_created_by VARCHAR(256)
);

COMMENT ON TABLE silver.fact_site_visit IS 'Site visit interactions. One row per visit.';
CREATE INDEX IF NOT EXISTS idx_fact_sv_lead ON silver.fact_site_visit (fact_lead_skey);
CREATE INDEX IF NOT EXISTS idx_fact_sv_project ON silver.fact_site_visit (project_skey);
CREATE INDEX IF NOT EXISTS idx_fact_sv_date ON silver.fact_site_visit (site_visit_dt_skey);

-- ============================================================
-- FACT: KYC DOCUMENTS
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.fact_kyc_documents (
    fact_kyc_documents_skey UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    kyc_id UUID,
    fact_lead_skey UUID REFERENCES silver.fact_lead(fact_lead_skey),
    kyc_created_dt_skey VARCHAR(256) REFERENCES silver.dim_calendar(calendar_skey),
    buyer_skey UUID REFERENCES silver.dim_buyer(buyer_skey),
    channel_partner_skey UUID REFERENCES silver.dim_channel_partner(channel_partner_skey),
    channel_partner_fos_skey UUID REFERENCES silver.dim_channel_partner_fos(channel_partner_fos_skey),
    document_number VARCHAR(256),
    document_holder_name VARCHAR(4000),
    document_type VARCHAR(256),
    document_url VARCHAR(4000),
    other_details JSON,
    is_rera_verification_skipped BOOLEAN DEFAULT FALSE,
    src_created_dt DATE,
    src_created_ts TIMESTAMP,
    src_updated_ts TIMESTAMP,
    dw_load_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dw_update_ts TIMESTAMP,
    dw_created_by VARCHAR(256)
);

COMMENT ON TABLE silver.fact_kyc_documents IS 'KYC document submissions per lead.';


-- ============================================================
-- SEED DATA: dim_lov (List of Values)
-- ============================================================
INSERT INTO silver.dim_lov (lov_type, lov_code, lov_value, lov_description, dw_created_by)
VALUES
    -- Lead statuses
    ('LEAD_STATUS', 'NEW',               'New',               'Freshly created lead',                      'seed'),
    ('LEAD_STATUS', 'CONTACTED',         'Contacted',         'Lead has been contacted',                   'seed'),
    ('LEAD_STATUS', 'SITE_VISIT_PLANNED','Site Visit Planned','Site visit scheduled',                      'seed'),
    ('LEAD_STATUS', 'SITE_VISITED',      'Site Visited',      'Customer visited the site',                 'seed'),
    ('LEAD_STATUS', 'NEGOTIATION',       'Negotiation',       'Pricing/terms under discussion',            'seed'),
    ('LEAD_STATUS', 'BOOKED',            'Booked',            'Unit booked by customer',                   'seed'),
    ('LEAD_STATUS', 'LOST',              'Lost',              'Lead lost / not converting',                'seed'),
    ('LEAD_STATUS', 'JUNK',              'Junk',              'Invalid or spam lead',                      'seed'),

    -- Lead types
    ('LEAD_TYPE', 'WALK_IN',             'Walk In',           'Customer walked into site office',          'seed'),
    ('LEAD_TYPE', 'REFERRAL',            'Referral',          'Referred by existing customer or employee', 'seed'),
    ('LEAD_TYPE', 'CP',                  'Channel Partner',   'Sourced through channel partner',           'seed'),
    ('LEAD_TYPE', 'DIGITAL',             'Digital',           'Online / digital marketing lead',           'seed'),
    ('LEAD_TYPE', 'SELF',                'Self',              'Customer-initiated enquiry',                'seed'),

    -- Lead sub-types
    ('LEAD_SUB_TYPE', 'ONLINE',          'Online',            'Lead from online channel',                  'seed'),
    ('LEAD_SUB_TYPE', 'OFFLINE',         'Offline',           'Lead from offline channel',                 'seed'),

    -- Lead categories
    ('LEAD_CATEGORY', 'HOT',             'Hot',               'High-intent buyer',                         'seed'),
    ('LEAD_CATEGORY', 'WARM',            'Warm',              'Medium-intent buyer',                       'seed'),
    ('LEAD_CATEGORY', 'COLD',            'Cold',              'Low-intent / early-stage buyer',            'seed'),

    -- Lead response
    ('LEAD_RESPONSE', 'INTERESTED',      'Interested',        'Customer showed interest',                  'seed'),
    ('LEAD_RESPONSE', 'NOT_INTERESTED',  'Not Interested',    'Customer declined',                         'seed'),
    ('LEAD_RESPONSE', 'NO_RESPONSE',     'No Response',       'Customer did not respond',                  'seed'),
    ('LEAD_RESPONSE', 'CALL_BACK',       'Call Back',         'Customer requested callback',               'seed'),

    -- Verification statuses
    ('VERIFICATION_STATUS', 'PENDING',   'Pending',           'Verification not yet done',                 'seed'),
    ('VERIFICATION_STATUS', 'VERIFIED',  'Verified',          'Successfully verified',                     'seed'),
    ('VERIFICATION_STATUS', 'REJECTED',  'Rejected',          'Verification failed',                       'seed'),

    -- Referrer types
    ('REFERRER_TYPE', 'EMPLOYEE',        'Employee',          'Referred by VJ employee',                   'seed'),
    ('REFERRER_TYPE', 'CP',              'Channel Partner',   'Referred by channel partner',               'seed'),
    ('REFERRER_TYPE', 'CUSTOMER',        'Customer',          'Referred by existing customer',             'seed'),
    ('REFERRER_TYPE', 'EXTERNAL',        'External',          'Referred by external source',               'seed')
ON CONFLICT DO NOTHING;


-- ============================================================
-- SEED DATA: dim_country (common countries for Indian real estate)
-- ============================================================
INSERT INTO silver.dim_country (country_iso_2, country_iso_3, country_full_name, currency, dw_created_by)
VALUES
    ('IN', 'IND', 'India',                 'INR', 'seed'),
    ('US', 'USA', 'United States',         'USD', 'seed'),
    ('AE', 'ARE', 'United Arab Emirates',  'AED', 'seed'),
    ('GB', 'GBR', 'United Kingdom',        'GBP', 'seed'),
    ('SG', 'SGP', 'Singapore',             'SGD', 'seed'),
    ('CA', 'CAN', 'Canada',               'CAD', 'seed'),
    ('AU', 'AUS', 'Australia',             'AUD', 'seed'),
    ('SA', 'SAU', 'Saudi Arabia',          'SAR', 'seed'),
    ('QA', 'QAT', 'Qatar',                'QAR', 'seed'),
    ('KW', 'KWT', 'Kuwait',               'KWD', 'seed'),
    ('OM', 'OMN', 'Oman',                 'OMR', 'seed'),
    ('BH', 'BHR', 'Bahrain',              'BHD', 'seed'),
    ('NP', 'NPL', 'Nepal',                'NPR', 'seed'),
    ('DE', 'DEU', 'Germany',              'EUR', 'seed'),
    ('NL', 'NLD', 'Netherlands',          'EUR', 'seed')
ON CONFLICT DO NOTHING;
