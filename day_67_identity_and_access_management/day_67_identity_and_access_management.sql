-- ============================================================
-- IDENTITY AND ACCESS MANAGEMENT
-- Users, groups, roles, policies, permissions and least privilege
-- PostgreSQL implementation
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS iam;

SET search_path TO iam, public;

-- ------------------------------------------------------------
-- 1. ENUMERATED DOMAIN TYPES
-- ------------------------------------------------------------

CREATE TYPE iam.user_status AS ENUM (
    'ACTIVE',
    'SUSPENDED',
    'DISABLED'
);

CREATE TYPE iam.policy_effect AS ENUM (
    'ALLOW',
    'DENY'
);

CREATE TYPE iam.access_decision AS ENUM (
    'ALLOW',
    'DENY'
);

CREATE TYPE iam.assignment_status AS ENUM (
    'ACTIVE',
    'REVOKED',
    'EXPIRED'
);

-- ------------------------------------------------------------
-- 2. IDENTITY TABLES
-- ------------------------------------------------------------

CREATE TABLE iam.users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    department VARCHAR(100) NOT NULL,
    status iam.user_status NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_username
        CHECK (username ~ '^[A-Za-z0-9_.-]{3,80}$'),

    CONSTRAINT valid_email
        CHECK (email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'),

    CONSTRAINT valid_department
        CHECK (length(trim(department)) > 0)
);

CREATE TABLE iam.groups (
    group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_group_name
        CHECK (length(trim(group_name)) > 0)
);

CREATE TABLE iam.user_groups (
    user_id BIGINT NOT NULL
        REFERENCES iam.users(user_id) ON DELETE CASCADE,

    group_id BIGINT NOT NULL
        REFERENCES iam.groups(group_id) ON DELETE CASCADE,

    assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (user_id, group_id)
);

-- ------------------------------------------------------------
-- 3. ROLE-BASED ACCESS CONTROL
-- ------------------------------------------------------------

CREATE TABLE iam.roles (
    role_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    is_system_role BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_role_name
        CHECK (length(trim(role_name)) > 0)
);

CREATE TABLE iam.permissions (
    permission_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    resource_pattern VARCHAR(255) NOT NULL,
    action VARCHAR(80) NOT NULL,
    description TEXT,

    CONSTRAINT unique_permission
        UNIQUE (resource_pattern, action),

    CONSTRAINT valid_resource_pattern
        CHECK (
            length(trim(resource_pattern)) > 0
            AND position('..' IN resource_pattern) = 0
        ),

    CONSTRAINT valid_action
        CHECK (
            action = '*'
            OR action ~ '^[a-z][a-z0-9_]*$'
        )
);

CREATE TABLE iam.role_permissions (
    role_id BIGINT NOT NULL
        REFERENCES iam.roles(role_id) ON DELETE CASCADE,

    permission_id BIGINT NOT NULL
        REFERENCES iam.permissions(permission_id) ON DELETE CASCADE,

    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE iam.group_roles (
    group_id BIGINT NOT NULL
        REFERENCES iam.groups(group_id) ON DELETE CASCADE,

    role_id BIGINT NOT NULL
        REFERENCES iam.roles(role_id) ON DELETE CASCADE,

    assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (group_id, role_id)
);

CREATE TABLE iam.role_assignments (
    assignment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id BIGINT NOT NULL
        REFERENCES iam.users(user_id) ON DELETE CASCADE,

    role_id BIGINT NOT NULL
        REFERENCES iam.roles(role_id) ON DELETE CASCADE,

    assigned_by BIGINT
        REFERENCES iam.users(user_id) ON DELETE SET NULL,

    assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,

    CONSTRAINT valid_assignment_expiry
        CHECK (expires_at IS NULL OR expires_at > assigned_at),

    CONSTRAINT valid_revocation
        CHECK (revoked_at IS NULL OR revoked_at >= assigned_at)
);

-- ------------------------------------------------------------
-- 4. POLICY-BASED ACCESS CONTROL
-- ------------------------------------------------------------

CREATE TABLE iam.policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    policy_name VARCHAR(150) NOT NULL UNIQUE,
    effect iam.policy_effect NOT NULL,

    permission_id BIGINT NOT NULL
        REFERENCES iam.permissions(permission_id),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    priority INTEGER NOT NULL DEFAULT 100,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ,

    CONSTRAINT valid_policy_expiry
        CHECK (expires_at IS NULL OR expires_at > created_at)
);

CREATE TABLE iam.policy_users (
    policy_id BIGINT NOT NULL
        REFERENCES iam.policies(policy_id) ON DELETE CASCADE,

    user_id BIGINT NOT NULL
        REFERENCES iam.users(user_id) ON DELETE CASCADE,

    PRIMARY KEY (policy_id, user_id)
);

CREATE TABLE iam.policy_groups (
    policy_id BIGINT NOT NULL
        REFERENCES iam.policies(policy_id) ON DELETE CASCADE,

    group_id BIGINT NOT NULL
        REFERENCES iam.groups(group_id) ON DELETE CASCADE,

    PRIMARY KEY (policy_id, group_id)
);

CREATE TABLE iam.policy_conditions (
    condition_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    policy_id BIGINT NOT NULL
        REFERENCES iam.policies(policy_id) ON DELETE CASCADE,

    attribute_name VARCHAR(100) NOT NULL,
    expected_value VARCHAR(255) NOT NULL,

    CONSTRAINT unique_policy_condition
        UNIQUE (policy_id, attribute_name)
);

-- ------------------------------------------------------------
-- 5. ACCESS AUDIT
-- ------------------------------------------------------------

CREATE TABLE iam.access_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    request_id UUID NOT NULL DEFAULT gen_random_uuid(),

    user_id BIGINT
        REFERENCES iam.users(user_id) ON DELETE SET NULL,

    resource VARCHAR(255) NOT NULL,
    action VARCHAR(80) NOT NULL,

    decision iam.access_decision NOT NULL,

    reason TEXT NOT NULL,

    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    context JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE TABLE iam.security_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id BIGINT
        REFERENCES iam.users(user_id) ON DELETE SET NULL,

    event_type VARCHAR(100) NOT NULL,
    event_details JSONB NOT NULL DEFAULT '{}'::JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 6. PERFORMANCE INDEXES
-- ------------------------------------------------------------

CREATE INDEX idx_user_groups_group
    ON iam.user_groups(group_id, user_id);

CREATE INDEX idx_group_roles_role
    ON iam.group_roles(role_id, group_id);

CREATE INDEX idx_role_assignments_user
    ON iam.role_assignments(user_id, role_id);

CREATE INDEX idx_role_assignments_active
    ON iam.role_assignments(user_id, expires_at)
    WHERE revoked_at IS NULL;

CREATE INDEX idx_policy_users_user
    ON iam.policy_users(user_id, policy_id);

CREATE INDEX idx_policy_groups_group
    ON iam.policy_groups(group_id, policy_id);

CREATE INDEX idx_policies_active
    ON iam.policies(policy_id, permission_id)
    WHERE is_active = TRUE;

CREATE INDEX idx_access_audit_user_time
    ON iam.access_audit(user_id, evaluated_at DESC);

CREATE INDEX idx_access_audit_decision
    ON iam.access_audit(decision, evaluated_at DESC);

CREATE INDEX idx_security_events_time
    ON iam.security_events(occurred_at DESC);

-- ------------------------------------------------------------
-- 7. INTEGRITY TRIGGERS
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION iam.prevent_system_role_deletion()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.is_system_role THEN
        RAISE EXCEPTION
            'System role % cannot be deleted.',
            OLD.role_name;
    END IF;

    RETURN OLD;
END;
$$;

CREATE TRIGGER trg_protect_system_roles
BEFORE DELETE ON iam.roles
FOR EACH ROW
EXECUTE FUNCTION iam.prevent_system_role_deletion();


CREATE OR REPLACE FUNCTION iam.validate_policy_principal()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    has_user BOOLEAN;
    has_group BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM iam.policy_users
        WHERE policy_id = NEW.policy_id
    )
    INTO has_user;

    SELECT EXISTS (
        SELECT 1
        FROM iam.policy_groups
        WHERE policy_id = NEW.policy_id
    )
    INTO has_group;

    IF NOT has_user AND NOT has_group THEN
        RAISE EXCEPTION
            'Policy % must have at least one principal.',
            NEW.policy_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE CONSTRAINT TRIGGER trg_policy_principal_validation
AFTER INSERT OR UPDATE ON iam.policies
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION iam.validate_policy_principal();

-- ------------------------------------------------------------
-- 8. EFFECTIVE ROLE VIEW
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW iam.effective_roles AS

SELECT DISTINCT
    ug.user_id,
    gr.role_id,
    'GROUP'::TEXT AS assignment_source
FROM iam.user_groups ug
JOIN iam.users u
    ON u.user_id = ug.user_id
JOIN iam.group_roles gr
    ON gr.group_id = ug.group_id
WHERE u.status = 'ACTIVE'

UNION

SELECT DISTINCT
    ra.user_id,
    ra.role_id,
    'DIRECT'::TEXT AS assignment_source
FROM iam.role_assignments ra
JOIN iam.users u
    ON u.user_id = ra.user_id
WHERE u.status = 'ACTIVE'
  AND ra.revoked_at IS NULL
  AND (
      ra.expires_at IS NULL
      OR ra.expires_at > CURRENT_TIMESTAMP
  );

-- ------------------------------------------------------------
-- 9. EFFECTIVE PERMISSION VIEW
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW iam.effective_permissions AS

SELECT DISTINCT
    er.user_id,
    rp.permission_id,
    er.role_id,
    er.assignment_source
FROM iam.effective_roles er
JOIN iam.role_permissions rp
    ON rp.role_id = er.role_id;

-- ------------------------------------------------------------
-- 10. PERMISSION MATCHING FUNCTION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION iam.permission_matches(
    p_pattern TEXT,
    p_requested_resource TEXT,
    p_action TEXT,
    p_requested_action TEXT
)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT
        (
            p_pattern = '*'
            OR p_pattern = p_requested_resource
            OR (
                right(p_pattern, 2) = '/*'
                AND left(
                    p_requested_resource,
                    length(p_pattern) - 1
                ) = left(p_pattern, length(p_pattern) - 1)
            )
        )
        AND (
            p_action = '*'
            OR p_action = p_requested_action
        );
$$;

-- ------------------------------------------------------------
-- 11. CENTRAL AUTHORIZATION FUNCTION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION iam.evaluate_access(
    p_user_id BIGINT,
    p_resource TEXT,
    p_action TEXT,
    p_context JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE (
    decision iam.access_decision,
    reason TEXT,
    matched_roles BIGINT[],
    matched_policies BIGINT[]
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_status iam.user_status;
    v_role_grant BOOLEAN;
    v_policy_allow BOOLEAN;
    v_policy_deny BOOLEAN;
    v_roles BIGINT[];
    v_policies BIGINT[];
    v_decision iam.access_decision;
    v_reason TEXT;
BEGIN
    IF p_resource IS NULL OR trim(p_resource) = ''
       OR p_action IS NULL OR trim(p_action) = '' THEN
        RAISE EXCEPTION 'Resource and action are required.';
    END IF;

    SELECT status
    INTO v_status
    FROM iam.users
    WHERE user_id = p_user_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown user ID: %', p_user_id;
    END IF;

    IF v_status <> 'ACTIVE' THEN
        v_decision := 'DENY';
        v_reason := 'Identity is not active.';
        v_roles := ARRAY[]::BIGINT[];
        v_policies := ARRAY[]::BIGINT[];

    ELSE
        -- Resolve permissions inherited from groups and direct roles.
        SELECT
            COALESCE(
                bool_or(
                    iam.permission_matches(
                        p.resource_pattern,
                        p_resource,
                        p.action,
                        p_action
                    )
                ),
                FALSE
            ),
            COALESCE(
                array_agg(DISTINCT er.role_id)
                FILTER (
                    WHERE iam.permission_matches(
                        p.resource_pattern,
                        p_resource,
                        p.action,
                        p_action
                    )
                ),
                ARRAY[]::BIGINT[]
            )
        INTO v_role_grant, v_roles
        FROM iam.effective_roles er
        JOIN iam.role_permissions rp
            ON rp.role_id = er.role_id
        JOIN iam.permissions p
            ON p.permission_id = rp.permission_id
        WHERE er.user_id = p_user_id;

        -- Evaluate applicable policies.
        -- A matching DENY overrides every matching ALLOW.
        WITH applicable AS (
            SELECT
                pol.policy_id,
                pol.effect
            FROM iam.policies pol
            JOIN iam.permissions p
                ON p.permission_id = pol.permission_id
            WHERE pol.is_active = TRUE
              AND (
                  pol.expires_at IS NULL
                  OR pol.expires_at > CURRENT_TIMESTAMP
              )
              AND iam.permission_matches(
                  p.resource_pattern,
                  p_resource,
                  p.action,
                  p_action
              )
              AND (
                  EXISTS (
                      SELECT 1
                      FROM iam.policy_users pu
                      WHERE pu.policy_id = pol.policy_id
                        AND pu.user_id = p_user_id
                  )
                  OR EXISTS (
                      SELECT 1
                      FROM iam.policy_groups pg
                      JOIN iam.user_groups ug
                          ON ug.group_id = pg.group_id
                      WHERE pg.policy_id = pol.policy_id
                        AND ug.user_id = p_user_id
                  )
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM iam.policy_conditions pc
                  WHERE pc.policy_id = pol.policy_id
                    AND (
                        p_context ->> pc.attribute_name
                    ) IS DISTINCT FROM pc.expected_value
              )
        )
        SELECT
            COALESCE(
                bool_or(effect = 'ALLOW'),
                FALSE
            ),
            COALESCE(
                bool_or(effect = 'DENY'),
                FALSE
            ),
            COALESCE(
                array_agg(policy_id),
                ARRAY[]::BIGINT[]
            )
        INTO
            v_policy_allow,
            v_policy_deny,
            v_policies
        FROM applicable;

        IF v_policy_deny THEN
            v_decision := 'DENY';
            v_reason := 'Explicit deny policy takes precedence.';

        ELSIF v_role_grant OR v_policy_allow THEN
            v_decision := 'ALLOW';
            v_reason := 'Matching role or policy grant.';

        ELSE
            v_decision := 'DENY';
            v_reason := 'No matching authorization grant.';
        END IF;
    END IF;

    -- Record every completed decision.
    INSERT INTO iam.access_audit (
        user_id,
        resource,
        action,
        decision,
        reason,
        context
    )
    VALUES (
        p_user_id,
        p_resource,
        p_action,
        v_decision,
        v_reason,
        p_context
    );

    RETURN QUERY
    SELECT
        v_decision,
        v_reason,
        v_roles,
        v_policies;
END;
$$;

-- ------------------------------------------------------------
-- 12. ACCESS ENFORCEMENT PROCEDURE
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE iam.require_access(
    p_user_id BIGINT,
    p_resource TEXT,
    p_action TEXT,
    p_context JSONB DEFAULT '{}'::JSONB
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_decision iam.access_decision;
    v_reason TEXT;
BEGIN
    SELECT decision, reason
    INTO v_decision, v_reason
    FROM iam.evaluate_access(
        p_user_id,
        p_resource,
        p_action,
        p_context
    );

    IF v_decision = 'DENY' THEN
        RAISE EXCEPTION
            'Access denied: %',
            v_reason
            USING ERRCODE = '42501';
    END IF;
END;
$$;

-- ------------------------------------------------------------
-- 13. ROLE REVOCATION PROCEDURE
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE iam.revoke_role(
    p_assignment_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_user_id BIGINT;
    v_role_id BIGINT;
BEGIN
    UPDATE iam.role_assignments
    SET revoked_at = CURRENT_TIMESTAMP
    WHERE assignment_id = p_assignment_id
      AND revoked_at IS NULL
    RETURNING user_id, role_id
    INTO v_user_id, v_role_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Active role assignment % not found.',
            p_assignment_id;
    END IF;

    INSERT INTO iam.security_events (
        user_id,
        event_type,
        event_details
    )
    VALUES (
        v_user_id,
        'ROLE_REVOKED',
        jsonb_build_object(
            'assignment_id', p_assignment_id,
            'role_id', v_role_id
        )
    );
END;
$$;

-- ------------------------------------------------------------
-- 14. SAMPLE USERS
-- ------------------------------------------------------------

INSERT INTO iam.users (
    username,
    email,
    department
)
VALUES
    ('alice', 'alice@example.com', 'Engineering'),
    ('bob', 'bob@example.com', 'Security'),
    ('carol', 'carol@example.com', 'Finance'),
    ('david', 'david@example.com', 'Engineering');

-- ------------------------------------------------------------
-- 15. SAMPLE GROUPS
-- ------------------------------------------------------------

INSERT INTO iam.groups (group_name, description)
VALUES
    ('Developers', 'Application development team'),
    ('SecurityTeam', 'Security auditing team'),
    ('FinanceTeam', 'Finance operations team');

-- ------------------------------------------------------------
-- 16. SAMPLE ROLES
-- ------------------------------------------------------------

INSERT INTO iam.roles (role_name, description, is_system_role)
VALUES
    ('Developer', 'Project development access', TRUE),
    ('SecurityAuditor', 'Read-only security auditing', TRUE),
    ('FinanceAnalyst', 'Finance reporting access', TRUE),
    ('IncidentAdministrator', 'Temporary incident response access', TRUE);

-- ------------------------------------------------------------
-- 17. SAMPLE PERMISSIONS
-- ------------------------------------------------------------

INSERT INTO iam.permissions (
    resource_pattern,
    action,
    description
)
VALUES
    ('applications/project-a', 'read', 'Read project A'),
    ('applications/project-a', 'write', 'Modify project A'),
    ('applications/project-a', 'delete', 'Delete project A'),
    ('security/logs', 'read', 'Read security logs'),
    ('security/reports', 'read', 'Read security reports'),
    ('production/secrets', '*', 'All production secret operations'),
    ('deployment/reports', 'read', 'Read deployment reports'),
    ('finance/reports', 'read', 'Read financial reports'),
    ('*', '*', 'Universal administrative permission');

-- ------------------------------------------------------------
-- 18. GROUP MEMBERSHIP
-- ------------------------------------------------------------

INSERT INTO iam.user_groups (user_id, group_id)
SELECT u.user_id, g.group_id
FROM (
    VALUES
        ('alice', 'Developers'),
        ('bob', 'SecurityTeam'),
        ('carol', 'FinanceTeam'),
        ('david', 'Developers')
) AS membership(username, group_name)
JOIN iam.users u
    ON u.username = membership.username
JOIN iam.groups g
    ON g.group_name = membership.group_name;

-- ------------------------------------------------------------
-- 19. ROLE PERMISSIONS
-- ------------------------------------------------------------

INSERT INTO iam.role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM (
    VALUES
        ('Developer', 'applications/project-a', 'read'),
        ('Developer', 'applications/project-a', 'write'),
        ('SecurityAuditor', 'security/logs', 'read'),
        ('SecurityAuditor', 'security/reports', 'read'),
        ('FinanceAnalyst', 'finance/reports', 'read'),
        ('IncidentAdministrator', '*', '*')
) AS mapping(role_name, resource_pattern, action)
JOIN iam.roles r
    ON r.role_name = mapping.role_name
JOIN iam.permissions p
    ON p.resource_pattern = mapping.resource_pattern
   AND p.action = mapping.action;

-- ------------------------------------------------------------
-- 20. GROUP ROLE ASSIGNMENTS
-- ------------------------------------------------------------

INSERT INTO iam.group_roles (group_id, role_id)
SELECT g.group_id, r.role_id
FROM (
    VALUES
        ('Developers', 'Developer'),
        ('SecurityTeam', 'SecurityAuditor'),
        ('FinanceTeam', 'FinanceAnalyst')
) AS mapping(group_name, role_name)
JOIN iam.groups g
    ON g.group_name = mapping.group_name
JOIN iam.roles r
    ON r.role_name = mapping.role_name;

-- ------------------------------------------------------------
-- 21. TEMPORARY DIRECT ROLE ASSIGNMENT
-- ------------------------------------------------------------

INSERT INTO iam.role_assignments (
    user_id,
    role_id,
    assigned_by,
    expires_at
)
SELECT
    u.user_id,
    r.role_id,
    admin.user_id,
    CURRENT_TIMESTAMP + INTERVAL '30 minutes'
FROM iam.users u
JOIN iam.roles r
    ON r.role_name = 'IncidentAdministrator'
JOIN iam.users admin
    ON admin.username = 'bob'
WHERE u.username = 'bob';

-- ------------------------------------------------------------
-- 22. POLICY CREATION
-- ------------------------------------------------------------

INSERT INTO iam.policies (
    policy_name,
    effect,
    permission_id,
    priority
)
SELECT
    'Deny developer access to production secrets',
    'DENY',
    permission_id,
    1
FROM iam.permissions
WHERE resource_pattern = 'production/secrets'
  AND action = '*';

INSERT INTO iam.policy_groups (policy_id, group_id)
SELECT p.policy_id, g.group_id
FROM iam.policies p
JOIN iam.groups g
    ON g.group_name = 'Developers'
WHERE p.policy_name =
    'Deny developer access to production secrets';

INSERT INTO iam.policies (
    policy_name,
    effect,
    permission_id
)
SELECT
    'Allow Alice to read deployment reports',
    'ALLOW',
    permission_id
FROM iam.permissions
WHERE resource_pattern = 'deployment/reports'
  AND action = 'read';

INSERT INTO iam.policy_users (policy_id, user_id)
SELECT p.policy_id, u.user_id
FROM iam.policies p
CROSS JOIN iam.users u
WHERE p.policy_name = 'Allow Alice to read deployment reports'
  AND u.username = 'alice';

-- Department condition for the deployment-report policy.
INSERT INTO iam.policy_conditions (
    policy_id,
    attribute_name,
    expected_value
)
SELECT
    policy_id,
    'department',
    'Engineering'
FROM iam.policies
WHERE policy_name = 'Allow Alice to read deployment reports';

-- ------------------------------------------------------------
-- 23. ACCESS EVALUATION
-- ------------------------------------------------------------

SELECT
    u.username,
    request.resource,
    request.action,
    result.decision,
    result.reason,
    result.matched_roles,
    result.matched_policies
FROM (
    VALUES
        ('alice', 'applications/project-a', 'read',
         '{"department":"Engineering"}'::JSONB),

        ('alice', 'applications/project-a', 'delete',
         '{"department":"Engineering"}'::JSONB),

        ('alice', 'production/secrets', 'read',
         '{"department":"Engineering"}'::JSONB),

        ('alice', 'deployment/reports', 'read',
         '{"department":"Engineering"}'::JSONB),

        ('alice', 'deployment/reports', 'read',
         '{"department":"Finance"}'::JSONB),

        ('bob', 'security/logs', 'read',
         '{"department":"Security"}'::JSONB),

        ('carol', 'finance/reports', 'read',
         '{"department":"Finance"}'::JSONB),

        ('david', 'security/logs', 'read',
         '{"department":"Engineering"}'::JSONB)
) AS request(username, resource, action, context)
JOIN iam.users u
    ON u.username = request.username
CROSS JOIN LATERAL iam.evaluate_access(
    u.user_id,
    request.resource,
    request.action,
    request.context
) AS result;

-- ------------------------------------------------------------
-- 24. EFFECTIVE ROLE RETRIEVAL
-- ------------------------------------------------------------

SELECT
    u.username,
    r.role_name,
    er.assignment_source
FROM iam.effective_roles er
JOIN iam.users u
    ON u.user_id = er.user_id
JOIN iam.roles r
    ON r.role_id = er.role_id
ORDER BY u.username, r.role_name;

-- ------------------------------------------------------------
-- 25. EFFECTIVE PERMISSION RETRIEVAL
-- ------------------------------------------------------------

SELECT
    u.username,
    r.role_name,
    p.resource_pattern,
    p.action,
    ep.assignment_source
FROM iam.effective_permissions ep
JOIN iam.users u
    ON u.user_id = ep.user_id
JOIN iam.roles r
    ON r.role_id = ep.role_id
JOIN iam.permissions p
    ON p.permission_id = ep.permission_id
ORDER BY u.username, p.resource_pattern;

-- ------------------------------------------------------------
-- 26. LEAST-PRIVILEGE AUDIT
-- ------------------------------------------------------------

WITH expected_permissions(username, resource, action) AS (
    VALUES
        ('alice', 'applications/project-a', 'read'),
        ('alice', 'applications/project-a', 'delete'),
        ('alice', 'production/secrets', 'read'),
        ('alice', 'deployment/reports', 'read'),
        ('bob', 'security/logs', 'read'),
        ('carol', 'finance/reports', 'read')
),
evaluated AS (
    SELECT
        e.username,
        e.resource,
        e.action,
        u.user_id,
        result.decision,
        result.reason
    FROM expected_permissions e
    JOIN iam.users u
        ON u.username = e.username
    CROSS JOIN LATERAL iam.evaluate_access(
        u.user_id,
        e.resource,
        e.action,
        jsonb_build_object('department', u.department)
    ) result
)
SELECT
    username,
    resource,
    action,
    decision,
    reason,
    CASE
        WHEN decision = 'ALLOW'
            THEN 'AUTHORIZED'
        ELSE 'NOT AUTHORIZED'
    END AS access_status
FROM evaluated
ORDER BY username, resource;

-- ------------------------------------------------------------
-- 27. ACCESS AUDIT AGGREGATION
-- ------------------------------------------------------------

SELECT
    decision,
    COUNT(*) AS total_requests,
    COUNT(DISTINCT user_id) AS distinct_users
FROM iam.access_audit
GROUP BY decision
ORDER BY decision;

-- ------------------------------------------------------------
-- 28. USER ACCESS REPORT
-- ------------------------------------------------------------

SELECT
    u.username,
    u.department,
    u.status,
    COUNT(a.audit_id) AS total_requests,
    COUNT(*) FILTER (
        WHERE a.decision = 'ALLOW'
    ) AS allowed_requests,
    COUNT(*) FILTER (
        WHERE a.decision = 'DENY'
    ) AS denied_requests
FROM iam.users u
LEFT JOIN iam.access_audit a
    ON a.user_id = u.user_id
GROUP BY
    u.user_id,
    u.username,
    u.department,
    u.status
ORDER BY u.username;

-- ------------------------------------------------------------
-- 29. EXPIRED AND REVOKED ASSIGNMENT DETECTION
-- ------------------------------------------------------------

SELECT
    u.username,
    r.role_name,
    ra.assignment_id,
    CASE
        WHEN ra.revoked_at IS NOT NULL THEN 'REVOKED'
        WHEN ra.expires_at <= CURRENT_TIMESTAMP THEN 'EXPIRED'
        ELSE 'ACTIVE'
    END AS assignment_state,
    ra.expires_at
FROM iam.role_assignments ra
JOIN iam.users u
    ON u.user_id = ra.user_id
JOIN iam.roles r
    ON r.role_id = ra.role_id
ORDER BY ra.assignment_id;

-- ------------------------------------------------------------
-- 30. POLICY PRINCIPAL VALIDATION
-- ------------------------------------------------------------

SELECT
    p.policy_name,
    p.effect,
    EXISTS (
        SELECT 1
        FROM iam.policy_users pu
        WHERE pu.policy_id = p.policy_id
    )
    OR EXISTS (
        SELECT 1
        FROM iam.policy_groups pg
        WHERE pg.policy_id = p.policy_id
    ) AS has_principal
FROM iam.policies p;

-- ------------------------------------------------------------
-- 31. TRANSACTIONAL ROLE REVOCATION EXAMPLE
-- ------------------------------------------------------------

SAVEPOINT before_role_revocation;

-- Revoke the temporary administrator assignment.
CALL iam.revoke_role(
    (
        SELECT assignment_id
        FROM iam.role_assignments ra
        JOIN iam.users u
            ON u.user_id = ra.user_id
        JOIN iam.roles r
            ON r.role_id = ra.role_id
        WHERE u.username = 'bob'
          AND r.role_name = 'IncidentAdministrator'
          AND ra.revoked_at IS NULL
        ORDER BY ra.assignment_id
        LIMIT 1
    )
);

-- Confirm that the assignment is no longer active.
SELECT
    u.username,
    r.role_name,
    ra.revoked_at,
    CASE
        WHEN ra.revoked_at IS NOT NULL THEN 'REVOKED'
        WHEN ra.expires_at <= CURRENT_TIMESTAMP THEN 'EXPIRED'
        ELSE 'ACTIVE'
    END AS assignment_state
FROM iam.role_assignments ra
JOIN iam.users u
    ON u.user_id = ra.user_id
JOIN iam.roles r
    ON r.role_id = ra.role_id
WHERE u.username = 'bob';

-- ------------------------------------------------------------
-- 32. SECURITY EVENT REPORT
-- ------------------------------------------------------------

SELECT
    event_type,
    COUNT(*) AS event_count,
    MAX(occurred_at) AS latest_event
FROM iam.security_events
GROUP BY event_type
ORDER BY event_type;

-- ------------------------------------------------------------
-- 33. QUERY PLANNING EXAMPLE
-- ------------------------------------------------------------

EXPLAIN
SELECT
    u.username,
    ra.role_id,
    ra.expires_at
FROM iam.role_assignments ra
JOIN iam.users u
    ON u.user_id = ra.user_id
WHERE ra.user_id = 1
  AND ra.revoked_at IS NULL
  AND (
      ra.expires_at IS NULL
      OR ra.expires_at > CURRENT_TIMESTAMP
  );

-- The example transaction is committed as one unit.
COMMIT;
