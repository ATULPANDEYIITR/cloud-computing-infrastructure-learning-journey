-- ============================================================
-- AUTHENTICATION AND AUTHORIZATION
-- PostgreSQL 15+
--
-- Models:
-- Password credentials, MFA, account lockout, sessions,
-- access tokens, OAuth clients and authorization codes,
-- RBAC, ABAC, authorization audits and security policies.
--
-- Passwords and MFA secrets are stored as hashes or encrypted
-- values. Token signing and OAuth cryptographic verification
-- must be performed by a trusted application security layer.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS identity;

SET search_path TO identity, public;

-- ============================================================
-- 1. Domain types
-- ============================================================

CREATE TYPE account_status AS ENUM (
    'active',
    'locked',
    'disabled'
);

CREATE TYPE session_status AS ENUM (
    'active',
    'revoked',
    'expired'
);

CREATE TYPE authorization_decision AS ENUM (
    'allow',
    'deny'
);

CREATE TYPE oauth_grant_status AS ENUM (
    'issued',
    'consumed',
    'expired',
    'revoked'
);

-- ============================================================
-- 2. Users
-- ============================================================

CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    username VARCHAR(40) NOT NULL UNIQUE,

    email VARCHAR(254) NOT NULL UNIQUE,

    password_hash TEXT NOT NULL,

    password_algorithm VARCHAR(40) NOT NULL
        DEFAULT 'argon2id',

    account_status account_status NOT NULL
        DEFAULT 'active',

    failed_attempts INTEGER NOT NULL DEFAULT 0,

    locked_until TIMESTAMPTZ,

    department VARCHAR(100) NOT NULL,

    clearance_level INTEGER NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    last_login_at TIMESTAMPTZ,

    CONSTRAINT username_format
        CHECK (username ~ '^[a-zA-Z0-9_.-]{3,40}$'),

    CONSTRAINT valid_failed_attempts
        CHECK (failed_attempts >= 0),

    CONSTRAINT valid_clearance
        CHECK (clearance_level BETWEEN 0 AND 10),

    CONSTRAINT valid_password_algorithm
        CHECK (password_algorithm IN ('argon2id', 'pbkdf2-sha256'))
);

CREATE INDEX idx_users_status
    ON users(account_status);

CREATE INDEX idx_users_department
    ON users(department);

-- ============================================================
-- 3. Roles and permissions
-- ============================================================

CREATE TABLE roles (
    role_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    role_name VARCHAR(60) NOT NULL UNIQUE,

    description TEXT NOT NULL
);

CREATE TABLE permissions (
    permission_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    permission_code VARCHAR(100) NOT NULL UNIQUE,

    description TEXT NOT NULL
);

CREATE TABLE role_permissions (
    role_id BIGINT NOT NULL
        REFERENCES roles(role_id) ON DELETE CASCADE,

    permission_id BIGINT NOT NULL
        REFERENCES permissions(permission_id) ON DELETE CASCADE,

    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE user_roles (
    user_id UUID NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE,

    role_id BIGINT NOT NULL
        REFERENCES roles(role_id) ON DELETE CASCADE,

    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    assigned_by UUID REFERENCES users(user_id),

    PRIMARY KEY (user_id, role_id)
);

CREATE INDEX idx_user_roles_role
    ON user_roles(role_id, user_id);

-- ============================================================
-- 4. MFA enrollment
-- ============================================================

CREATE TABLE mfa_methods (
    mfa_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE,

    method_type VARCHAR(30) NOT NULL,

    secret_ciphertext BYTEA,

    enabled BOOLEAN NOT NULL DEFAULT FALSE,

    verified_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    last_used_at TIMESTAMPTZ,

    CONSTRAINT valid_mfa_method
        CHECK (method_type IN (
            'totp',
            'webauthn',
            'recovery_code'
        ))
);

CREATE INDEX idx_mfa_user
    ON mfa_methods(user_id, enabled);

-- Recovery codes are stored as one-way hashes.
CREATE TABLE recovery_codes (
    recovery_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE,

    code_hash TEXT NOT NULL,

    used_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(user_id, code_hash)
);

-- ============================================================
-- 5. Authentication attempts
-- ============================================================

CREATE TABLE authentication_attempts (
    attempt_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,

    attempted_username VARCHAR(40) NOT NULL,

    source_ip INET,

    success BOOLEAN NOT NULL,

    failure_reason VARCHAR(100),

    mfa_used BOOLEAN NOT NULL DEFAULT FALSE,

    attempted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_auth_attempt_user_time
    ON authentication_attempts(user_id, attempted_at DESC);

CREATE INDEX idx_auth_attempt_failures
    ON authentication_attempts(attempted_at DESC)
    WHERE success = FALSE;

-- ============================================================
-- 6. Sessions
-- ============================================================

CREATE TABLE sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE,

    session_token_hash TEXT NOT NULL UNIQUE,

    status session_status NOT NULL DEFAULT 'active',

    ip_address INET,

    user_agent TEXT,

    mfa_verified BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    expires_at TIMESTAMPTZ NOT NULL,

    revoked_at TIMESTAMPTZ,

    CONSTRAINT valid_session_expiry
        CHECK (expires_at > created_at)
);

CREATE INDEX idx_sessions_active_user
    ON sessions(user_id, expires_at)
    WHERE status = 'active';

CREATE INDEX idx_sessions_expiry
    ON sessions(expires_at)
    WHERE status = 'active';

-- ============================================================
-- 7. Access-token registry
-- ============================================================

CREATE TABLE access_tokens (
    token_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE,

    token_jti VARCHAR(200) NOT NULL UNIQUE,

    token_hash TEXT NOT NULL UNIQUE,

    issuer VARCHAR(200) NOT NULL,

    audience VARCHAR(200) NOT NULL,

    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    expires_at TIMESTAMPTZ NOT NULL,

    revoked_at TIMESTAMPTZ,

    CONSTRAINT valid_token_lifetime
        CHECK (expires_at > issued_at)
);

CREATE INDEX idx_tokens_user_expiry
    ON access_tokens(user_id, expires_at);

-- ============================================================
-- 8. OAuth 2.0 clients
-- ============================================================

CREATE TABLE oauth_clients (
    client_id VARCHAR(100) PRIMARY KEY,

    client_name VARCHAR(150) NOT NULL,

    client_secret_hash TEXT,

    is_confidential BOOLEAN NOT NULL DEFAULT TRUE,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE oauth_redirect_uris (
    redirect_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    client_id VARCHAR(100) NOT NULL
        REFERENCES oauth_clients(client_id) ON DELETE CASCADE,

    redirect_uri TEXT NOT NULL,

    UNIQUE(client_id, redirect_uri)
);

CREATE TABLE oauth_scopes (
    scope_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    scope_name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE oauth_client_scopes (
    client_id VARCHAR(100) NOT NULL
        REFERENCES oauth_clients(client_id) ON DELETE CASCADE,

    scope_id BIGINT NOT NULL
        REFERENCES oauth_scopes(scope_id) ON DELETE CASCADE,

    PRIMARY KEY(client_id, scope_id)
);

-- Authorization codes are stored by hash, never in plaintext.
CREATE TABLE oauth_authorization_codes (
    code_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    code_hash TEXT NOT NULL UNIQUE,

    client_id VARCHAR(100) NOT NULL
        REFERENCES oauth_clients(client_id),

    user_id UUID NOT NULL
        REFERENCES users(user_id),

    redirect_uri TEXT NOT NULL,

    state_hash TEXT NOT NULL,

    code_challenge VARCHAR(43) NOT NULL,

    code_challenge_method VARCHAR(10) NOT NULL DEFAULT 'S256',

    grant_status oauth_grant_status NOT NULL DEFAULT 'issued',

    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    expires_at TIMESTAMPTZ NOT NULL,

    consumed_at TIMESTAMPTZ,

    CONSTRAINT valid_pkce_method
        CHECK (code_challenge_method = 'S256'),

    CONSTRAINT valid_challenge
        CHECK (code_challenge ~ '^[A-Za-z0-9_-]{43}$'),

    CONSTRAINT valid_code_expiry
        CHECK (expires_at > issued_at)
);

CREATE INDEX idx_oauth_codes_expiry
    ON oauth_authorization_codes(expires_at)
    WHERE grant_status = 'issued';

-- ============================================================
-- 9. ABAC resource model
-- ============================================================

CREATE TABLE protected_resources (
    resource_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    resource_name VARCHAR(150) NOT NULL,

    department VARCHAR(100) NOT NULL,

    owner_id UUID NOT NULL REFERENCES users(user_id),

    classification INTEGER NOT NULL DEFAULT 0,

    resource_attributes JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT valid_classification
        CHECK (classification BETWEEN 0 AND 10),

    CONSTRAINT attributes_are_object
        CHECK (jsonb_typeof(resource_attributes) = 'object')
);

CREATE INDEX idx_resources_department
    ON protected_resources(department);

CREATE INDEX idx_resources_attributes
    ON protected_resources USING GIN(resource_attributes);

-- ============================================================
-- 10. ABAC policies
-- ============================================================

CREATE TABLE authorization_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    policy_name VARCHAR(150) NOT NULL UNIQUE,

    action VARCHAR(50) NOT NULL,

    effect authorization_decision NOT NULL,

    policy_expression JSONB NOT NULL,

    priority INTEGER NOT NULL DEFAULT 100,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT valid_policy_expression
        CHECK (jsonb_typeof(policy_expression) = 'object')
);

CREATE INDEX idx_policies_active_priority
    ON authorization_policies(priority)
    WHERE enabled = TRUE;

-- ============================================================
-- 11. Authorization audit
-- ============================================================

CREATE TABLE authorization_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,

    resource_id UUID
        REFERENCES protected_resources(resource_id) ON DELETE SET NULL,

    action VARCHAR(50) NOT NULL,

    decision authorization_decision NOT NULL,

    decision_reason TEXT NOT NULL,

    policy_context JSONB NOT NULL DEFAULT '{}'::jsonb,

    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_user_time
    ON authorization_audit(user_id, evaluated_at DESC);

CREATE INDEX idx_audit_denials
    ON authorization_audit(evaluated_at DESC)
    WHERE decision = 'deny';

-- ============================================================
-- 12. Database integrity triggers
-- ============================================================

CREATE OR REPLACE FUNCTION update_modified_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_users_updated
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION update_modified_timestamp();


CREATE OR REPLACE FUNCTION enforce_account_lockout()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.failed_attempts >= 5 THEN
        NEW.account_status := 'locked';
        NEW.locked_until := now() + interval '15 minutes';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_account_lockout
BEFORE UPDATE OF failed_attempts ON users
FOR EACH ROW
EXECUTE FUNCTION enforce_account_lockout();


CREATE OR REPLACE FUNCTION prevent_session_reactivation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IN ('revoked', 'expired')
       AND NEW.status = 'active' THEN
        RAISE EXCEPTION
            'A revoked or expired session cannot be reactivated';
    END IF;

    IF NEW.status = 'revoked' AND NEW.revoked_at IS NULL THEN
        NEW.revoked_at := now();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_session_state
BEFORE UPDATE ON sessions
FOR EACH ROW
EXECUTE FUNCTION prevent_session_reactivation();


CREATE OR REPLACE FUNCTION prevent_oauth_code_reuse()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.grant_status <> 'issued'
       AND NEW.grant_status = 'issued' THEN
        RAISE EXCEPTION
            'Consumed, expired or revoked authorization codes cannot be reused';
    END IF;

    IF OLD.grant_status = 'issued'
       AND NEW.grant_status = 'consumed'
       AND NEW.consumed_at IS NULL THEN
        NEW.consumed_at := now();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_oauth_code_state
BEFORE UPDATE ON oauth_authorization_codes
FOR EACH ROW
EXECUTE FUNCTION prevent_oauth_code_reuse();

-- ============================================================
-- 13. RBAC authorization function
-- ============================================================

CREATE OR REPLACE FUNCTION check_rbac(
    p_user_id UUID,
    p_permission VARCHAR
)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM users u
        JOIN user_roles ur
            ON ur.user_id = u.user_id
        JOIN roles r
            ON r.role_id = ur.role_id
        JOIN role_permissions rp
            ON rp.role_id = r.role_id
        JOIN permissions p
            ON p.permission_id = rp.permission_id
        WHERE u.user_id = p_user_id
          AND u.account_status = 'active'
          AND p.permission_code = p_permission
    );
$$;

-- ============================================================
-- 14. ABAC authorization function
-- ============================================================

CREATE OR REPLACE FUNCTION check_abac(
    p_user_id UUID,
    p_resource_id UUID,
    p_action VARCHAR,
    p_mfa_verified BOOLEAN,
    p_risk_score INTEGER
)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_department VARCHAR;
    v_clearance INTEGER;
    v_status account_status;

    v_resource_department VARCHAR;
    v_resource_owner UUID;
    v_classification INTEGER;

    v_is_admin BOOLEAN;
BEGIN
    SELECT
        department,
        clearance_level,
        account_status
    INTO
        v_department,
        v_clearance,
        v_status
    FROM users
    WHERE user_id = p_user_id;

    IF NOT FOUND OR v_status <> 'active' THEN
        RETURN FALSE;
    END IF;

    IF p_mfa_verified IS NOT TRUE
       OR p_risk_score IS NULL
       OR p_risk_score > 70
       OR p_risk_score < 0 THEN
        RETURN FALSE;
    END IF;

    SELECT department, owner_id, classification
    INTO
        v_resource_department,
        v_resource_owner,
        v_classification
    FROM protected_resources
    WHERE resource_id = p_resource_id;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM user_roles ur
        JOIN roles r ON r.role_id = ur.role_id
        WHERE ur.user_id = p_user_id
          AND r.role_name = 'admin'
    )
    INTO v_is_admin;

    IF p_action = 'read' THEN
        RETURN v_department = v_resource_department
            OR v_is_admin;
    END IF;

    IF p_action = 'approve' THEN
        RETURN v_department = v_resource_department
            AND v_clearance >= v_classification
            AND p_user_id <> v_resource_owner;
    END IF;

    RETURN FALSE;
END;
$$;

-- ============================================================
-- 15. Central authorization evaluation and audit
-- ============================================================

CREATE OR REPLACE FUNCTION authorize_request(
    p_user_id UUID,
    p_resource_id UUID,
    p_action VARCHAR,
    p_permission VARCHAR,
    p_mfa_verified BOOLEAN,
    p_risk_score INTEGER
)
RETURNS authorization_decision
LANGUAGE plpgsql
AS $$
DECLARE
    v_rbac BOOLEAN;
    v_abac BOOLEAN;
    v_decision authorization_decision;
    v_reason TEXT;
BEGIN
    v_rbac := check_rbac(
        p_user_id,
        p_permission
    );

    v_abac := check_abac(
        p_user_id,
        p_resource_id,
        p_action,
        p_mfa_verified,
        p_risk_score
    );

    -- Both authorization layers must approve.
    IF v_rbac AND v_abac THEN
        v_decision := 'allow';
        v_reason := 'RBAC and ABAC conditions satisfied';
    ELSE
        v_decision := 'deny';
        v_reason := 'RBAC or ABAC policy rejected request';
    END IF;

    INSERT INTO authorization_audit (
        user_id,
        resource_id,
        action,
        decision,
        decision_reason,
        policy_context
    )
    VALUES (
        p_user_id,
        p_resource_id,
        p_action,
        v_decision,
        v_reason,
        jsonb_build_object(
            'rbac', v_rbac,
            'abac', v_abac,
            'mfa_verified', p_mfa_verified,
            'risk_score', p_risk_score
        )
    );

    RETURN v_decision;
END;
$$;

-- ============================================================
-- 16. Seed roles
-- ============================================================

INSERT INTO roles(role_name, description)
VALUES
    ('employee', 'Standard organizational employee'),
    ('analyst', 'Read-only reporting and analytical access'),
    ('admin', 'Administrative access')
ON CONFLICT(role_name) DO NOTHING;

INSERT INTO permissions(permission_code, description)
VALUES
    ('profile:read', 'Read user profile'),
    ('profile:update', 'Update own profile'),
    ('reports:read', 'Read analytical reports'),
    ('users:manage', 'Manage user identities'),
    ('security:manage', 'Manage security configuration')
ON CONFLICT(permission_code) DO NOTHING;

-- Employee permissions.
INSERT INTO role_permissions(role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM roles r
CROSS JOIN permissions p
WHERE r.role_name = 'employee'
AND p.permission_code IN (
    'profile:read',
    'profile:update'
)
ON CONFLICT DO NOTHING;

-- Analyst permissions.
INSERT INTO role_permissions(role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM roles r
CROSS JOIN permissions p
WHERE r.role_name = 'analyst'
AND p.permission_code IN (
    'profile:read',
    'reports:read'
)
ON CONFLICT DO NOTHING;

-- Administrator permissions.
INSERT INTO role_permissions(role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM roles r
CROSS JOIN permissions p
WHERE r.role_name = 'admin'
ON CONFLICT DO NOTHING;

-- OAuth scopes.
INSERT INTO oauth_scopes(scope_name)
VALUES
    ('profile.read'),
    ('reports.read'),
    ('users.manage')
ON CONFLICT DO NOTHING;

-- ============================================================
-- 17. Sample identities
-- Password hashes are illustrative encoded test values.
-- Applications must insert actual Argon2id/PBKDF2 outputs.
-- ============================================================

INSERT INTO users (
    user_id,
    username,
    email,
    password_hash,
    department,
    clearance_level
)
VALUES
(
    '10000000-0000-0000-0000-000000000001',
    'alice',
    'alice@example.com',
    'DEMO_HASH_ALICE',
    'engineering',
    2
),
(
    '10000000-0000-0000-0000-000000000002',
    'bob',
    'bob@example.com',
    'DEMO_HASH_BOB',
    'security',
    5
),
(
    '10000000-0000-0000-0000-000000000003',
    'charlie',
    'charlie@example.com',
    'DEMO_HASH_CHARLIE',
    'finance',
    1
)
ON CONFLICT DO NOTHING;

INSERT INTO user_roles(user_id, role_id)
SELECT
    u.user_id,
    r.role_id
FROM (
    VALUES
        ('alice', 'employee'),
        ('bob', 'admin'),
        ('charlie', 'analyst')
) AS assignments(username, role_name)
JOIN users u ON u.username = assignments.username
JOIN roles r ON r.role_name = assignments.role_name
ON CONFLICT DO NOTHING;

-- ============================================================
-- 18. MFA and authentication sample data
-- ============================================================

INSERT INTO mfa_methods (
    user_id,
    method_type,
    secret_ciphertext,
    enabled,
    verified_at
)
SELECT
    user_id,
    'totp',
    decode('AABBCCDD', 'hex'),
    TRUE,
    now()
FROM users
WHERE username = 'alice'
AND NOT EXISTS (
    SELECT 1
    FROM mfa_methods m
    WHERE m.user_id = users.user_id
      AND m.method_type = 'totp'
);

-- ============================================================
-- 19. Sample OAuth client
-- ============================================================

INSERT INTO oauth_clients (
    client_id,
    client_name,
    is_confidential
)
VALUES
    ('web-client', 'Enterprise Web Application', TRUE)
ON CONFLICT DO NOTHING;

INSERT INTO oauth_redirect_uris(client_id, redirect_uri)
VALUES
    ('web-client', 'https://client.example/callback')
ON CONFLICT DO NOTHING;

INSERT INTO oauth_client_scopes(client_id, scope_id)
SELECT
    'web-client',
    scope_id
FROM oauth_scopes
WHERE scope_name IN ('profile.read', 'reports.read')
ON CONFLICT DO NOTHING;

-- ============================================================
-- 20. Sample protected resources
-- ============================================================

INSERT INTO protected_resources (
    resource_id,
    resource_name,
    department,
    owner_id,
    classification,
    resource_attributes
)
SELECT
    '20000000-0000-0000-0000-000000000001',
    'Engineering Architecture Report',
    'engineering',
    user_id,
    1,
    '{"type":"document","confidential":false}'::jsonb
FROM users
WHERE username = 'bob'
ON CONFLICT DO NOTHING;

INSERT INTO protected_resources (
    resource_id,
    resource_name,
    department,
    owner_id,
    classification,
    resource_attributes
)
SELECT
    '20000000-0000-0000-0000-000000000002',
    'Restricted Security Assessment',
    'security',
    user_id,
    5,
    '{"type":"assessment","confidential":true}'::jsonb
FROM users
WHERE username = 'bob'
ON CONFLICT DO NOTHING;

-- ============================================================
-- 21. Sample ABAC policy definitions
-- ============================================================

INSERT INTO authorization_policies (
    policy_name,
    action,
    effect,
    policy_expression,
    priority
)
VALUES
(
    'Department Read Policy',
    'read',
    'allow',
    '{"same_department":true,"mfa_required":true,"max_risk":70}',
    10
),
(
    'Restricted Approval Policy',
    'approve',
    'allow',
    '{"same_department":true,"owner_approval_forbidden":true,"clearance_required":true}',
    20
)
ON CONFLICT(policy_name) DO NOTHING;

-- ============================================================
-- 22. Retrieval: user and effective permissions
-- ============================================================

SELECT
    u.username,
    r.role_name,
    p.permission_code
FROM users u
JOIN user_roles ur
    ON ur.user_id = u.user_id
JOIN roles r
    ON r.role_id = ur.role_id
JOIN role_permissions rp
    ON rp.role_id = r.role_id
JOIN permissions p
    ON p.permission_id = rp.permission_id
ORDER BY u.username, p.permission_code;

-- ============================================================
-- 23. Retrieval: effective session state
-- ============================================================

SELECT
    s.session_id,
    u.username,
    s.status,
    s.mfa_verified,
    s.created_at,
    s.expires_at
FROM sessions s
JOIN users u ON u.user_id = s.user_id
WHERE s.status = 'active'
  AND s.expires_at > now()
ORDER BY s.created_at DESC;

-- ============================================================
-- 24. Validation: RBAC eligibility
-- ============================================================

SELECT
    u.username,
    check_rbac(
        u.user_id,
        'users:manage'
    ) AS can_manage_users
FROM users u
ORDER BY u.username;

-- ============================================================
-- 25. Evaluation: ABAC
-- ============================================================

SELECT
    u.username,
    r.resource_name,
    check_abac(
        u.user_id,
        r.resource_id,
        'read',
        TRUE,
        20
    ) AS read_allowed
FROM users u
CROSS JOIN protected_resources r
ORDER BY u.username, r.resource_name;

-- ============================================================
-- 26. Central authorization evaluation
-- ============================================================

SELECT authorize_request(
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    'read',
    'profile:read',
    TRUE,
    20
);

-- A different department is rejected by ABAC.
SELECT authorize_request(
    '10000000-0000-0000-0000-000000000003',
    '20000000-0000-0000-0000-000000000001',
    'read',
    'reports:read',
    TRUE,
    20
);

-- High-risk access is rejected.
SELECT authorize_request(
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    'read',
    'profile:read',
    TRUE,
    95
);

-- ============================================================
-- 27. Aggregation: failed authentication attempts
-- ============================================================

SELECT
    attempted_username,
    COUNT(*) AS attempts,
    COUNT(*) FILTER (WHERE success = FALSE) AS failures,
    COUNT(*) FILTER (WHERE success = TRUE) AS successes
FROM authentication_attempts
WHERE attempted_at >= now() - interval '24 hours'
GROUP BY attempted_username
ORDER BY failures DESC;

-- ============================================================
-- 28. Aggregation: authorization decisions
-- ============================================================

SELECT
    action,
    decision,
    COUNT(*) AS decision_count
FROM authorization_audit
WHERE evaluated_at >= now() - interval '7 days'
GROUP BY action, decision
ORDER BY action, decision;

-- ============================================================
-- 29. Reporting: locked and disabled accounts
-- ============================================================

SELECT
    username,
    email,
    account_status,
    failed_attempts,
    locked_until
FROM users
WHERE account_status IN ('locked', 'disabled')
ORDER BY updated_at DESC;

-- ============================================================
-- 30. Reporting: expiring tokens and sessions
-- ============================================================

SELECT
    'session' AS credential_type,
    user_id,
    expires_at
FROM sessions
WHERE status = 'active'
  AND expires_at BETWEEN now() AND now() + interval '15 minutes'

UNION ALL

SELECT
    'access_token',
    user_id,
    expires_at
FROM access_tokens
WHERE revoked_at IS NULL
  AND expires_at BETWEEN now() AND now() + interval '15 minutes';

-- ============================================================
-- 31. CTE: users with excessive authentication failures
-- ============================================================

WITH recent_failures AS (
    SELECT
        user_id,
        COUNT(*) AS failure_count
    FROM authentication_attempts
    WHERE success = FALSE
      AND attempted_at >= now() - interval '1 hour'
      AND user_id IS NOT NULL
    GROUP BY user_id
),
risk_assessment AS (
    SELECT
        u.user_id,
        u.username,
        COALESCE(r.failure_count, 0) AS failures
    FROM users u
    LEFT JOIN recent_failures r
        ON r.user_id = u.user_id
)
SELECT
    username,
    failures,
    CASE
        WHEN failures >= 10 THEN 'high'
        WHEN failures >= 5 THEN 'medium'
        ELSE 'low'
    END AS risk_level
FROM risk_assessment
ORDER BY failures DESC;

-- ============================================================
-- 32. Workflow processing: revoke expired sessions
-- ============================================================

UPDATE sessions
SET
    status = 'expired'
WHERE status = 'active'
  AND expires_at <= now();

-- Revoke expired OAuth authorization codes.
UPDATE oauth_authorization_codes
SET grant_status = 'expired'
WHERE grant_status = 'issued'
  AND expires_at <= now();

-- ============================================================
-- 33. Workflow processing: revoke all user sessions
-- ============================================================

UPDATE sessions
SET
    status = 'revoked',
    revoked_at = now()
WHERE user_id = '10000000-0000-0000-0000-000000000001'
  AND status = 'active';

-- ============================================================
-- 34. Eligibility: OAuth client and redirect validation
-- ============================================================

SELECT
    c.client_id,
    c.enabled,
    EXISTS (
        SELECT 1
        FROM oauth_redirect_uris ru
        WHERE ru.client_id = c.client_id
          AND ru.redirect_uri =
              'https://client.example/callback'
    ) AS redirect_registered
FROM oauth_clients c
WHERE c.client_id = 'web-client';

-- ============================================================
-- 35. Eligibility: user MFA status
-- ============================================================

SELECT
    u.username,
    COUNT(m.mfa_id) FILTER (
        WHERE m.enabled = TRUE
    ) AS enabled_mfa_methods,
    EXISTS (
        SELECT 1
        FROM mfa_methods active_method
        WHERE active_method.user_id = u.user_id
          AND active_method.enabled = TRUE
          AND active_method.verified_at IS NOT NULL
    ) AS mfa_verified
FROM users u
LEFT JOIN mfa_methods m
    ON m.user_id = u.user_id
GROUP BY u.user_id, u.username;

-- ============================================================
-- 36. Transactional authorization example
-- ============================================================

SAVEPOINT before_security_change;

UPDATE users
SET
    clearance_level = 3
WHERE username = 'alice'
  AND account_status = 'active';

-- Validate the resulting clearance.
DO $$
DECLARE
    v_clearance INTEGER;
BEGIN
    SELECT clearance_level
    INTO v_clearance
    FROM users
    WHERE username = 'alice';

    IF v_clearance IS NULL OR v_clearance > 5 THEN
        RAISE EXCEPTION 'Invalid clearance assignment';
    END IF;
END;
$$;

RELEASE SAVEPOINT before_security_change;

-- ============================================================
-- 37. Useful administrative view
-- ============================================================

CREATE OR REPLACE VIEW active_identity_overview AS
SELECT
    u.user_id,
    u.username,
    u.department,
    u.account_status,
    COALESCE(
        array_agg(DISTINCT r.role_name)
            FILTER (WHERE r.role_name IS NOT NULL),
        ARRAY[]::VARCHAR[]
    ) AS assigned_roles,
    COUNT(DISTINCT s.session_id)
        FILTER (
            WHERE s.status = 'active'
              AND s.expires_at > now()
        ) AS active_sessions
FROM users u
LEFT JOIN user_roles ur
    ON ur.user_id = u.user_id
LEFT JOIN roles r
    ON r.role_id = ur.role_id
LEFT JOIN sessions s
    ON s.user_id = u.user_id
GROUP BY
    u.user_id,
    u.username,
    u.department,
    u.account_status;

SELECT *
FROM active_identity_overview
ORDER BY username;

-- ============================================================
-- 38. Audit review
-- ============================================================

SELECT
    a.audit_id,
    u.username,
    r.resource_name,
    a.action,
    a.decision,
    a.decision_reason,
    a.policy_context,
    a.evaluated_at
FROM authorization_audit a
LEFT JOIN users u ON u.user_id = a.user_id
LEFT JOIN protected_resources r
    ON r.resource_id = a.resource_id
ORDER BY a.evaluated_at DESC;

-- ============================================================
-- 39. Security implementation boundaries
-- ============================================================

COMMENT ON TABLE users IS
'Stores password hashes, account state and organizational attributes. Never store plaintext passwords.';

COMMENT ON TABLE mfa_methods IS
'MFA secrets must be encrypted outside ordinary database access.';

COMMENT ON TABLE sessions IS
'Stores hashed opaque session tokens. Cookies should use Secure, HttpOnly and appropriate SameSite attributes.';

COMMENT ON TABLE access_tokens IS
'Stores token identifiers and hashes for revocation and audit.';

COMMENT ON TABLE oauth_authorization_codes IS
'Stores authorization-code hashes. PKCE S256 verification must occur in the trusted application layer.';

COMMENT ON TABLE authorization_policies IS
'Stores policy definitions. Application services must validate and interpret policy expressions.';

COMMENT ON FUNCTION authorize_request IS
'Combines RBAC and ABAC decisions and records an authorization audit event.';

COMMIT;
