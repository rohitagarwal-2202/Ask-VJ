-- ============================================================
-- ASK VJ: App Schema (Authentication, Policies, Preferences)
-- ============================================================
-- Separate from bronze/silver/gold data warehouse schemas.
-- Contains user management, access control, and personalization.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS app;

-- ============================================================
-- USERS — Pre-registered users who can access Ask VJ
-- ============================================================
CREATE TABLE IF NOT EXISTS app.users (
    user_id       SERIAL PRIMARY KEY,
    phone         VARCHAR(15) UNIQUE NOT NULL,  -- E.164 format (+91XXXXXXXXXX)
    display_name  VARCHAR(100) NOT NULL,
    role          VARCHAR(20) NOT NULL DEFAULT 'viewer',  -- admin, viewer, manager
    is_active     BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by    INT REFERENCES app.users(user_id),
    last_login_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_phone ON app.users (phone);
CREATE INDEX IF NOT EXISTS idx_users_role ON app.users (role);

-- ============================================================
-- OTP REQUESTS — Transient OTP codes for phone verification
-- ============================================================
CREATE TABLE IF NOT EXISTS app.otp_requests (
    otp_id      SERIAL PRIMARY KEY,
    phone       VARCHAR(15) NOT NULL,
    otp_code    VARCHAR(6) NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    verified    BOOLEAN NOT NULL DEFAULT false,
    attempts    INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_otp_phone_active
    ON app.otp_requests (phone, expires_at) WHERE verified = false;

-- ============================================================
-- SESSIONS — JWT session tracking for revocation
-- ============================================================
CREATE TABLE IF NOT EXISTS app.sessions (
    session_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     INT NOT NULL REFERENCES app.users(user_id),
    jwt_jti     VARCHAR(64) UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked     BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON app.sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_jti ON app.sessions (jwt_jti);

-- ============================================================
-- DATA POLICIES — Per-user access restrictions
-- ============================================================
CREATE TABLE IF NOT EXISTS app.data_policies (
    policy_id    SERIAL PRIMARY KEY,
    user_id      INT NOT NULL REFERENCES app.users(user_id),
    policy_type  VARCHAR(20) NOT NULL,   -- project_filter, table_access, column_mask
    target       VARCHAR(100) NOT NULL,  -- table name, project name, or column
    action       VARCHAR(20) NOT NULL,   -- allow, deny, mask
    value        JSONB,                  -- e.g. {"project_keys": [1, 2, 3]}
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by   INT REFERENCES app.users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_policies_user
    ON app.data_policies (user_id, policy_type);

-- ============================================================
-- POLICY TEMPLATES — Reusable policy sets
-- ============================================================
CREATE TABLE IF NOT EXISTS app.policy_templates (
    template_id   SERIAL PRIMARY KEY,
    template_name VARCHAR(100) NOT NULL,
    description   TEXT,
    policies      JSONB NOT NULL  -- array of policy definitions
);

-- ============================================================
-- USER PREFERENCES — Per-user business term interpretations
-- ============================================================
CREATE TABLE IF NOT EXISTS app.user_preferences (
    preference_id  SERIAL PRIMARY KEY,
    user_id        INT NOT NULL REFERENCES app.users(user_id),
    term           VARCHAR(100) NOT NULL,
    definition     TEXT NOT NULL,
    sql_hint       TEXT,
    table_ref      VARCHAR(100),
    source         VARCHAR(20) NOT NULL DEFAULT 'manual',  -- manual, learned
    confidence     FLOAT NOT NULL DEFAULT 1.0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, term)
);

CREATE INDEX IF NOT EXISTS idx_prefs_user ON app.user_preferences (user_id);

-- ============================================================
-- CONVERSATION CORRECTIONS — Tracks user corrections for learning
-- ============================================================
CREATE TABLE IF NOT EXISTS app.conversation_corrections (
    correction_id  SERIAL PRIMARY KEY,
    user_id        INT NOT NULL REFERENCES app.users(user_id),
    session_id     VARCHAR(100),
    original_term  VARCHAR(100) NOT NULL,
    corrected_to   TEXT NOT NULL,
    question       TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_corrections_user_term
    ON app.conversation_corrections (user_id, original_term);

-- ============================================================
-- CLARIFICATION SESSIONS — Pending disambiguation choices
-- ============================================================
CREATE TABLE IF NOT EXISTS app.clarification_sessions (
    clarification_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           INT NOT NULL REFERENCES app.users(user_id),
    session_id        VARCHAR(100) NOT NULL,
    original_question TEXT NOT NULL,
    parsed_intent     VARCHAR(50),
    parsed_confidence FLOAT NOT NULL,
    options           JSONB NOT NULL,
    selected_option   INT,
    status            VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, resolved, expired
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_clarification_session
    ON app.clarification_sessions (session_id, status);

-- ============================================================
-- SEED: Bootstrap admin user (phone to be updated)
-- ============================================================
INSERT INTO app.users (phone, display_name, role)
VALUES ('+910000000000', 'System Admin', 'admin')
ON CONFLICT (phone) DO NOTHING;
