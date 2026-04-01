-- ============================================================
-- ASK VJ: Silver Layer Schema (Entity Resolution)
-- ============================================================
-- Links records across source systems into unified entities.
-- Solves the "lifecycle spans systems" problem.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS silver;

-- Enable fuzzy string matching
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- PROJECT CROSSWALK
-- Maps project names/codes across systems
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.project_crosswalk (
    crosswalk_id SERIAL PRIMARY KEY,
    canonical_name VARCHAR(255) NOT NULL,    -- The unified project name used in gold layer
    phase_name VARCHAR(100),

    -- VJ Sales App identifiers
    vjsales_project_name VARCHAR(255),

    -- Farvision ERP identifiers
    farvision_project_code VARCHAR(50),

    -- VJOP identifiers (future)
    vjop_project_id INT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(vjsales_project_name),
    UNIQUE(farvision_project_code)
);

-- ============================================================
-- ENTITY MAP
-- Links customer/lead identities across systems
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.entity_map (
    entity_map_id SERIAL PRIMARY KEY,
    unified_customer_id UUID DEFAULT gen_random_uuid(),

    -- VJ Sales identifiers
    vjsales_lead_id INT,
    vjsales_booking_id INT,

    -- Farvision identifiers
    farvision_customer_name VARCHAR(255),
    farvision_project_code VARCHAR(50),
    farvision_unit_no VARCHAR(50),

    -- VJOP identifiers (future)
    vjop_customer_id INT,

    -- Resolution metadata
    match_method VARCHAR(50) NOT NULL,  -- unit_project_exact, phone_exact, name_fuzzy, manual
    match_confidence DECIMAL(3, 2) NOT NULL DEFAULT 0.00,  -- 0.00 to 1.00
    resolved_by VARCHAR(50) NOT NULL DEFAULT 'etl_auto',   -- etl_auto, manual_review
    resolved_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    notes TEXT,

    UNIQUE(vjsales_lead_id)
);

CREATE INDEX IF NOT EXISTS idx_entity_map_unified
    ON silver.entity_map (unified_customer_id);
CREATE INDEX IF NOT EXISTS idx_entity_map_farvision
    ON silver.entity_map (farvision_project_code, farvision_unit_no);

-- ============================================================
-- ENTITY RESOLUTION QUEUE
-- Unresolved or low-confidence matches for manual review
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.entity_resolution_queue (
    queue_id SERIAL PRIMARY KEY,

    -- Candidate from VJ Sales
    vjsales_lead_id INT,
    vjsales_lead_name VARCHAR(255),
    vjsales_phone VARCHAR(50),
    vjsales_project VARCHAR(255),
    vjsales_unit VARCHAR(50),

    -- Candidate from Farvision
    farvision_customer_name VARCHAR(255),
    farvision_project_code VARCHAR(50),
    farvision_unit_no VARCHAR(50),

    -- Match details
    candidate_confidence DECIMAL(3, 2),
    match_method VARCHAR(50),
    reason VARCHAR(500),  -- Why the auto-resolver wasn't confident

    -- Review status
    status VARCHAR(20) DEFAULT 'pending',  -- pending, confirmed, rejected, skipped
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_resolution_queue_status
    ON silver.entity_resolution_queue (status);
