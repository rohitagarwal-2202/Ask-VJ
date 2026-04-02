-- ============================================================
-- ASK VJ: Silver Layer Schema (Entity Resolution)
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
