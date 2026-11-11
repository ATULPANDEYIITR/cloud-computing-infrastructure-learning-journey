/*
 * SECURITY MONITORING AND AUDITING
 *
 * PostgreSQL 14+
 *
 * Relational security monitoring platform:
 * - Organizations and monitored systems
 * - Users and role assignments
 * - Audit logs
 * - Access logs
 * - Security alerts
 * - Anomaly detection
 * - Alert investigation
 * - Immutable audit records
 * - Branch-independent governance
 *
 * Execute using psql.
 */

BEGIN;

CREATE SCHEMA IF NOT EXISTS security_monitoring;

SET search_path TO security_monitoring, public;

-- ============================================================
-- ENUM TYPES
-- ============================================================

CREATE TYPE event_type AS ENUM (
    'LOGIN_SUCCESS',
    'LOGIN_FAILURE',
    'LOGOUT',
    'ACCESS_GRANTED',
    'ACCESS_DENIED',
    'PRIVILEGE_CHANGE',
    'DATA_EXPORT',
    'CONFIGURATION_CHANGE',
    'PASSWORD_CHANGE',
    'FIREWALL_CHANGE'
);

CREATE TYPE severity_level AS ENUM (
    'LOW',
    'MEDIUM',
    'HIGH',
    'CRITICAL'
);

CREATE TYPE alert_status AS ENUM (
    'OPEN',
    'INVESTIGATING',
    'RESOLVED',
    'FALSE_POSITIVE'
);

CREATE TYPE review_decision AS ENUM (
    'UNREVIEWED',
    'CONFIRMED',
    'FALSE_POSITIVE',
    'INCONCLUSIVE'
);

-- ============================================================
-- ORGANIZATIONS
-- ============================================================

CREATE TABLE organizations (
    organization_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    organization_name VARCHAR(150) NOT NULL UNIQUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (length(trim(organization_name)) > 0)
);

-- ============================================================
-- MONITORED SYSTEMS
-- ============================================================

CREATE TABLE monitored_systems (
    system_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),

    system_name VARCHAR(150) NOT NULL,

    environment VARCHAR(30) NOT NULL
        CHECK (
            environment IN (
                'DEVELOPMENT',
                'TESTING',
                'STAGING',
                'PRODUCTION'
            )
        ),

    criticality SMALLINT NOT NULL
        CHECK (criticality BETWEEN 1 AND 5),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (organization_id, system_name)
);

CREATE INDEX idx_systems_organization
ON monitored_systems(organization_id, is_active);

-- ============================================================
-- USERS
-- ============================================================

CREATE TABLE security_users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),

    username VARCHAR(100) NOT NULL,

    email VARCHAR(255) NOT NULL,

    account_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (
            account_status IN (
                'ACTIVE',
                'SUSPENDED',
                'DISABLED'
            )
        ),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (organization_id, username),

    UNIQUE (organization_id, email)
);

-- ============================================================
-- SECURITY ROLES
-- ============================================================

CREATE TABLE security_roles (
    role_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    role_name VARCHAR(60) NOT NULL UNIQUE,

    description TEXT NOT NULL
);

CREATE TABLE user_role_assignments (
    assignment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id BIGINT NOT NULL
        REFERENCES security_users(user_id),

    role_id BIGINT NOT NULL
        REFERENCES security_roles(role_id),

    assigned_by BIGINT
        REFERENCES security_users(user_id),

    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    revoked_at TIMESTAMPTZ,

    CHECK (
        revoked_at IS NULL OR revoked_at >= assigned_at
    )
);

CREATE UNIQUE INDEX uq_active_user_role
ON user_role_assignments(user_id, role_id)
WHERE revoked_at IS NULL;

CREATE INDEX idx_user_role_active
ON user_role_assignments(user_id)
WHERE revoked_at IS NULL;

-- ============================================================
-- RESOURCE PERMISSIONS
-- ============================================================

CREATE TABLE resource_permissions (
    permission_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    role_id BIGINT NOT NULL
        REFERENCES security_roles(role_id),

    resource VARCHAR(255) NOT NULL,

    permission VARCHAR(20) NOT NULL
        CHECK (
            permission IN (
                'READ',
                'WRITE',
                'DELETE',
                'ADMIN',
                'EXPORT'
            )
        ),

    UNIQUE (role_id, resource, permission)
);

-- ============================================================
-- AUDIT LOGS
-- ============================================================

CREATE TABLE audit_logs (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    event_uuid UUID NOT NULL UNIQUE,

    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),

    system_id BIGINT NOT NULL
        REFERENCES monitored_systems(system_id),

    user_id BIGINT
        REFERENCES security_users(user_id),

    event_timestamp TIMESTAMPTZ NOT NULL,

    event_type event_type NOT NULL,

    source_ip INET NOT NULL,

    resource VARCHAR(512) NOT NULL,

    success BOOLEAN NOT NULL,

    details JSONB NOT NULL DEFAULT '{}'::JSONB,

    previous_hash VARCHAR(64),

    record_hash VARCHAR(64) NOT NULL,

    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (jsonb_typeof(details) = 'object'),

    CHECK (
        previous_hash IS NULL OR
        previous_hash ~ '^[0-9a-f]{64}$'
    ),

    CHECK (record_hash ~ '^[0-9a-f]{64}$'),

    CHECK (octet_length(details::TEXT) <= 8192)
);

CREATE INDEX idx_audit_event_time
ON audit_logs(organization_id, event_timestamp DESC);

CREATE INDEX idx_audit_user_time
ON audit_logs(user_id, event_timestamp DESC);

CREATE INDEX idx_audit_event_type
ON audit_logs(event_type, event_timestamp DESC);

CREATE INDEX idx_audit_source_ip
ON audit_logs(source_ip, event_timestamp DESC);

CREATE INDEX idx_audit_details
ON audit_logs USING GIN(details);

-- ============================================================
-- ACCESS LOGS
-- ============================================================

CREATE TABLE access_logs (
    access_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    audit_id BIGINT NOT NULL UNIQUE
        REFERENCES audit_logs(audit_id),

    user_id BIGINT
        REFERENCES security_users(user_id),

    resource VARCHAR(512) NOT NULL,

    permission_requested VARCHAR(20) NOT NULL
        CHECK (
            permission_requested IN (
                'READ',
                'WRITE',
                'DELETE',
                'ADMIN',
                'EXPORT'
            )
        ),

    decision VARCHAR(10) NOT NULL
        CHECK (
            decision IN ('ALLOW', 'DENY')
        ),

    source_ip INET NOT NULL,

    accessed_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_access_user_time
ON access_logs(user_id, accessed_at DESC);

CREATE INDEX idx_access_decision
ON access_logs(decision, accessed_at DESC);

-- ============================================================
-- DETECTION RULES
-- ============================================================

CREATE TABLE detection_rules (
    rule_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    rule_code VARCHAR(80) NOT NULL UNIQUE,

    rule_name VARCHAR(150) NOT NULL,

    description TEXT NOT NULL,

    event_filter event_type,

    threshold INTEGER NOT NULL
        CHECK (threshold > 0),

    window_minutes INTEGER NOT NULL
        CHECK (window_minutes > 0),

    severity severity_level NOT NULL,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- SECURITY ALERTS
-- ============================================================

CREATE TABLE security_alerts (
    alert_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    alert_uuid UUID NOT NULL UNIQUE,

    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),

    system_id BIGINT NOT NULL
        REFERENCES monitored_systems(system_id),

    user_id BIGINT
        REFERENCES security_users(user_id),

    rule_id BIGINT
        REFERENCES detection_rules(rule_id),

    severity severity_level NOT NULL,

    category VARCHAR(120) NOT NULL,

    description TEXT NOT NULL,

    anomaly_score NUMERIC(6,3) NOT NULL
        CHECK (anomaly_score BETWEEN 0 AND 1),

    status alert_status NOT NULL DEFAULT 'OPEN',

    assigned_to BIGINT
        REFERENCES security_users(user_id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    resolved_at TIMESTAMPTZ,

    CHECK (
        resolved_at IS NULL OR
        resolved_at >= created_at
    )
);

CREATE INDEX idx_alert_open_severity
ON security_alerts(severity, created_at DESC)
WHERE status IN ('OPEN', 'INVESTIGATING');

CREATE INDEX idx_alert_user_time
ON security_alerts(user_id, created_at DESC);

CREATE INDEX idx_alert_system_status
ON security_alerts(system_id, status);

-- ============================================================
-- ALERT EVIDENCE
-- ============================================================

CREATE TABLE alert_evidence (
    alert_id BIGINT NOT NULL
        REFERENCES security_alerts(alert_id),

    audit_id BIGINT NOT NULL
        REFERENCES audit_logs(audit_id),

    evidence_type VARCHAR(60) NOT NULL,

    PRIMARY KEY (alert_id, audit_id)
);

-- ============================================================
-- ALERT INVESTIGATION
-- ============================================================

CREATE TABLE alert_investigations (
    investigation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    alert_id BIGINT NOT NULL
        REFERENCES security_alerts(alert_id),

    analyst_id BIGINT NOT NULL
        REFERENCES security_users(user_id),

    decision review_decision NOT NULL DEFAULT 'UNREVIEWED',

    investigation_notes TEXT NOT NULL,

    investigated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_investigation_alert
ON alert_investigations(alert_id, investigated_at DESC);

-- ============================================================
-- AUDIT IMMUTABILITY
-- ============================================================

CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'Audit records are append-only. UPDATE and DELETE are prohibited.';
END;
$$;

CREATE TRIGGER trg_audit_immutable
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW
EXECUTE FUNCTION prevent_audit_modification();

-- ============================================================
-- AUDIT INSERT VALIDATION
-- ============================================================

CREATE OR REPLACE FUNCTION validate_audit_insert()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_organization BIGINT;
    v_system_active BOOLEAN;
    v_previous_hash VARCHAR(64);
BEGIN

    SELECT organization_id, is_active
    INTO v_organization, v_system_active
    FROM monitored_systems
    WHERE system_id = NEW.system_id
    FOR SHARE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown monitored system';
    END IF;

    IF v_organization <> NEW.organization_id THEN
        RAISE EXCEPTION
            'System does not belong to supplied organization';
    END IF;

    IF NOT v_system_active THEN
        RAISE EXCEPTION 'System is inactive';
    END IF;

    IF NEW.user_id IS NOT NULL THEN

        IF NOT EXISTS (
            SELECT 1
            FROM security_users u
            WHERE u.user_id = NEW.user_id
              AND u.organization_id = NEW.organization_id
        ) THEN
            RAISE EXCEPTION
                'User does not belong to supplied organization';
        END IF;

    END IF;

    IF NEW.event_type = 'DATA_EXPORT' THEN

        IF NOT (NEW.details ? 'record_count') THEN
            RAISE EXCEPTION
                'Data export requires record_count';
        END IF;

        IF NEW.details->>'record_count' !~ '^[0-9]+$' THEN
            RAISE EXCEPTION
                'record_count must be a non-negative integer';
        END IF;

    END IF;

    /*
     * A transaction-level advisory lock serializes hash-chain
     * inserts per monitored system.
     *
     * The application supplies the hash values. This trigger
     * validates sequence linkage, not cryptographic authenticity.
     */

    PERFORM pg_advisory_xact_lock(NEW.system_id);

    SELECT record_hash
    INTO v_previous_hash
    FROM audit_logs
    WHERE system_id = NEW.system_id
    ORDER BY audit_id DESC
    LIMIT 1;

    IF NOT FOUND THEN
        IF NEW.previous_hash IS NOT NULL THEN
            RAISE EXCEPTION
                'First audit record must not have a previous hash';
        END IF;
    ELSE
        IF NEW.previous_hash IS DISTINCT FROM v_previous_hash THEN
            RAISE EXCEPTION
                'Audit hash-chain predecessor mismatch';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_audit_insert
BEFORE INSERT ON audit_logs
FOR EACH ROW
EXECUTE FUNCTION validate_audit_insert();

-- ============================================================
-- AUDIT EVENT INSERT FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION record_security_event(
    p_event_uuid UUID,
    p_organization_id BIGINT,
    p_system_id BIGINT,
    p_user_id BIGINT,
    p_event_timestamp TIMESTAMPTZ,
    p_event_type event_type,
    p_source_ip INET,
    p_resource VARCHAR,
    p_success BOOLEAN,
    p_details JSONB,
    p_previous_hash VARCHAR,
    p_record_hash VARCHAR
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_audit_id BIGINT;
BEGIN

    INSERT INTO audit_logs (
        event_uuid,
        organization_id,
        system_id,
        user_id,
        event_timestamp,
        event_type,
        source_ip,
        resource,
        success,
        details,
        previous_hash,
        record_hash
    )
    VALUES (
        p_event_uuid,
        p_organization_id,
        p_system_id,
        p_user_id,
        p_event_timestamp,
        p_event_type,
        p_source_ip,
        p_resource,
        p_success,
        COALESCE(p_details, '{}'::JSONB),
        p_previous_hash,
        p_record_hash
    )
    RETURNING audit_id INTO v_audit_id;

    RETURN v_audit_id;
END;
$$;

-- ============================================================
-- ACCESS AUTHORIZATION FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION check_access_permission(
    p_user_id BIGINT,
    p_resource VARCHAR,
    p_permission VARCHAR
)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM user_role_assignments ura
        JOIN security_roles sr
          ON sr.role_id = ura.role_id
        JOIN resource_permissions rp
          ON rp.role_id = sr.role_id
        JOIN security_users u
          ON u.user_id = ura.user_id
        WHERE ura.user_id = p_user_id
          AND ura.revoked_at IS NULL
          AND u.account_status = 'ACTIVE'
          AND rp.resource = p_resource
          AND rp.permission = p_permission
    );
$$;

-- ============================================================
-- ACCESS DECISION FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION evaluate_access(
    p_user_id BIGINT,
    p_resource VARCHAR,
    p_permission VARCHAR
)
RETURNS VARCHAR
LANGUAGE plpgsql
STABLE
AS $$
BEGIN

    IF check_access_permission(
        p_user_id,
        p_resource,
        p_permission
    ) THEN
        RETURN 'ALLOW';
    END IF;

    RETURN 'DENY';
END;
$$;

-- ============================================================
-- ACCESS LOG INSERT TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION validate_access_decision()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_audit_type event_type;
    v_audit_user BIGINT;
    v_audit_resource VARCHAR;
    v_audit_success BOOLEAN;
    v_expected VARCHAR;
BEGIN

    SELECT
        event_type,
        user_id,
        resource,
        success
    INTO
        v_audit_type,
        v_audit_user,
        v_audit_resource,
        v_audit_success
    FROM audit_logs
    WHERE audit_id = NEW.audit_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown audit record';
    END IF;

    IF v_audit_type NOT IN (
        'ACCESS_GRANTED',
        'ACCESS_DENIED'
    ) THEN
        RAISE EXCEPTION
            'Access log must reference an access event';
    END IF;

    IF NEW.user_id IS DISTINCT FROM v_audit_user THEN
        RAISE EXCEPTION 'Access log user mismatch';
    END IF;

    IF NEW.resource <> v_audit_resource THEN
        RAISE EXCEPTION 'Access log resource mismatch';
    END IF;

    IF NEW.source_ip IS DISTINCT FROM (
        SELECT source_ip
        FROM audit_logs
        WHERE audit_id = NEW.audit_id
    ) THEN
        RAISE EXCEPTION 'Access log source IP mismatch';
    END IF;

    IF NEW.decision = 'ALLOW' THEN
        IF NOT v_audit_success OR v_audit_type <> 'ACCESS_GRANTED' THEN
            RAISE EXCEPTION
                'Allowed access must reference successful granted access';
        END IF;

        v_expected := evaluate_access(
            NEW.user_id,
            NEW.resource,
            NEW.permission_requested
        );

        IF v_expected <> 'ALLOW' THEN
            RAISE EXCEPTION
                'Access granted despite insufficient permissions';
        END IF;
    ELSE
        IF v_audit_success OR v_audit_type <> 'ACCESS_DENIED' THEN
            RAISE EXCEPTION
                'Denied access must reference unsuccessful denied access';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_access
BEFORE INSERT ON access_logs
FOR EACH ROW
EXECUTE FUNCTION validate_access_decision();

-- ============================================================
-- ALERT STATE VALIDATION
-- ============================================================

CREATE OR REPLACE FUNCTION validate_alert_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN

    IF OLD.status IN ('RESOLVED', 'FALSE_POSITIVE') THEN

        RAISE EXCEPTION
            'Closed alerts cannot be modified';
    END IF;

    IF NEW.status = 'INVESTIGATING'
       AND NEW.assigned_to IS NULL THEN

        RAISE EXCEPTION
            'Investigating alerts require an assigned analyst';
    END IF;

    IF NEW.status IN ('RESOLVED', 'FALSE_POSITIVE') THEN

        NEW.resolved_at := COALESCE(
            NEW.resolved_at,
            NOW()
        );

    ELSE
        NEW.resolved_at := NULL;
    END IF;

    NEW.updated_at := NOW();

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_alert_transition
BEFORE UPDATE ON security_alerts
FOR EACH ROW
EXECUTE FUNCTION validate_alert_transition();

-- ============================================================
-- DETECTION RULE EVALUATION
-- ============================================================

CREATE OR REPLACE FUNCTION detect_security_anomalies(
    p_system_id BIGINT,
    p_user_id BIGINT,
    p_event_type event_type,
    p_event_time TIMESTAMPTZ
)
RETURNS TABLE (
    rule_code VARCHAR,
    matched_count BIGINT,
    severity severity_level
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        dr.rule_code,
        COUNT(al.audit_id),
        dr.severity
    FROM detection_rules dr
    JOIN audit_logs al
      ON al.system_id = p_system_id
     AND (dr.event_filter IS NULL OR
          al.event_type = dr.event_filter)
     AND al.event_timestamp BETWEEN
         p_event_time - make_interval(mins => dr.window_minutes)
         AND p_event_time
    WHERE dr.enabled
      AND (
          dr.event_filter IS NULL OR
          dr.event_filter = p_event_type
      )
      AND al.user_id = p_user_id
    GROUP BY
        dr.rule_id,
        dr.rule_code,
        dr.threshold,
        dr.severity
    HAVING COUNT(al.audit_id) >= dr.threshold;
$$;

-- ============================================================
-- ALERT CREATION PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE create_alert_from_event(
    p_audit_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_event audit_logs%ROWTYPE;
    v_rule RECORD;
    v_score NUMERIC(6,3);
    v_alert_id BIGINT;
BEGIN

    SELECT *
    INTO v_event
    FROM audit_logs
    WHERE audit_id = p_audit_id
    FOR SHARE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Audit event not found';
    END IF;

    FOR v_rule IN
        SELECT *
        FROM detect_security_anomalies(
            v_event.system_id,
            v_event.user_id,
            v_event.event_type,
            v_event.event_timestamp
        )
    LOOP

        v_score := CASE v_rule.severity
            WHEN 'LOW' THEN 0.150
            WHEN 'MEDIUM' THEN 0.350
            WHEN 'HIGH' THEN 0.650
            WHEN 'CRITICAL' THEN 0.900
        END;

        INSERT INTO security_alerts (
            alert_uuid,
            organization_id,
            system_id,
            user_id,
            rule_id,
            severity,
            category,
            description,
            anomaly_score
        )
        SELECT
            gen_random_uuid(),
            v_event.organization_id,
            v_event.system_id,
            v_event.user_id,
            dr.rule_id,
            v_rule.severity,
            v_rule.rule_code,
            'Threshold-based security anomaly detected',
            v_score
        FROM detection_rules dr
        WHERE dr.rule_code = v_rule.rule_code
        RETURNING alert_id INTO v_alert_id;

        INSERT INTO alert_evidence (
            alert_id,
            audit_id,
            evidence_type
        )
        VALUES (
            v_alert_id,
            p_audit_id,
            'TRIGGERING_EVENT'
        );

    END LOOP;

END;
$$;

-- ============================================================
-- SECURITY REPORTING VIEW
-- ============================================================

CREATE VIEW v_security_alert_dashboard AS
SELECT
    a.alert_id,
    a.alert_uuid,
    o.organization_name,
    ms.system_name,
    ms.environment,
    u.username,
    a.severity,
    a.category,
    a.anomaly_score,
    a.status,
    analyst.username AS assigned_analyst,
    a.created_at,
    a.updated_at,
    a.resolved_at
FROM security_alerts a
JOIN organizations o
  ON o.organization_id = a.organization_id
JOIN monitored_systems ms
  ON ms.system_id = a.system_id
LEFT JOIN security_users u
  ON u.user_id = a.user_id
LEFT JOIN security_users analyst
  ON analyst.user_id = a.assigned_to;

-- ============================================================
-- ACCESS ACTIVITY VIEW
-- ============================================================

CREATE VIEW v_access_activity AS
SELECT
    al.access_id,
    su.username,
    al.resource,
    al.permission_requested,
    al.decision,
    al.source_ip,
    al.accessed_at
FROM access_logs al
LEFT JOIN security_users su
  ON su.user_id = al.user_id;

-- ============================================================
-- HOURLY SECURITY AGGREGATION
-- ============================================================

CREATE VIEW v_hourly_security_metrics AS
SELECT
    organization_id,
    system_id,
    date_trunc('hour', event_timestamp) AS event_hour,
    event_type,
    COUNT(*) AS event_count,
    COUNT(*) FILTER (
        WHERE NOT success
    ) AS failed_events,
    COUNT(DISTINCT user_id) AS unique_users,
    COUNT(DISTINCT source_ip) AS unique_source_ips
FROM audit_logs
GROUP BY
    organization_id,
    system_id,
    date_trunc('hour', event_timestamp),
    event_type;

-- ============================================================
-- SAMPLE ORGANIZATIONS
-- ============================================================

INSERT INTO organizations (organization_name)
VALUES
    ('Enterprise Technology Division'),
    ('Financial Services Division');

-- ============================================================
-- SAMPLE SYSTEMS
-- ============================================================

INSERT INTO monitored_systems (
    organization_id,
    system_name,
    environment,
    criticality
)
VALUES
    (1, 'Core Application', 'PRODUCTION', 5),
    (1, 'Identity Management', 'PRODUCTION', 5),
    (2, 'Financial Reporting', 'PRODUCTION', 5);

-- ============================================================
-- SAMPLE USERS
-- ============================================================

INSERT INTO security_users (
    organization_id,
    username,
    email
)
VALUES
    (1, 'alice', 'alice@example.org'),
    (1, 'bob', 'bob@example.org'),
    (1, 'carol', 'carol@example.org'),
    (1, 'david', 'david@example.org'),
    (1, 'security_analyst', 'analyst@example.org'),
    (2, 'finance_admin', 'finance@example.org');

-- ============================================================
-- SAMPLE ROLES
-- ============================================================

INSERT INTO security_roles (
    role_name,
    description
)
VALUES
    ('administrator', 'Full system administration'),
    ('developer', 'Application development'),
    ('auditor', 'Read-only compliance auditing'),
    ('analyst', 'Operational data analysis');

-- ============================================================
-- SAMPLE ROLE ASSIGNMENTS
-- ============================================================

INSERT INTO user_role_assignments (
    user_id,
    role_id,
    assigned_by
)
SELECT
    u.user_id,
    r.role_id,
    NULL
FROM (
    VALUES
        ('alice', 'developer'),
        ('bob', 'administrator'),
        ('carol', 'auditor'),
        ('david', 'analyst'),
        ('security_analyst', 'auditor'),
        ('finance_admin', 'administrator')
) AS mapping(username, role_name)
JOIN security_users u
  ON u.username = mapping.username
JOIN security_roles r
  ON r.role_name = mapping.role_name;

-- ============================================================
-- SAMPLE PERMISSIONS
-- ============================================================

INSERT INTO resource_permissions (
    role_id,
    resource,
    permission
)
SELECT
    r.role_id,
    mapping.resource,
    mapping.permission
FROM (
    VALUES
        ('administrator', '/admin', 'READ'),
        ('administrator', '/admin', 'WRITE'),
        ('administrator', '/admin', 'ADMIN'),
        ('administrator', '/credentials', 'READ'),
        ('administrator', '/database', 'READ'),
        ('administrator', '/database', 'WRITE'),
        ('administrator', '/financial-records', 'READ'),
        ('administrator', '/financial-records', 'EXPORT'),
        ('developer', '/application', 'READ'),
        ('developer', '/application', 'WRITE'),
        ('developer', '/database', 'READ'),
        ('auditor', '/financial-records', 'READ'),
        ('auditor', '/reports', 'READ'),
        ('analyst', '/reports', 'READ'),
        ('analyst', '/application', 'READ')
) AS mapping(role_name, resource, permission)
JOIN security_roles r
  ON r.role_name = mapping.role_name;

-- ============================================================
-- DETECTION RULES
-- ============================================================

INSERT INTO detection_rules (
    rule_code,
    rule_name,
    description,
    event_filter,
    threshold,
    window_minutes,
    severity
)
VALUES
    (
        'BRUTE_FORCE_LOGIN',
        'Repeated login failures',
        'Detects repeated authentication failures',
        'LOGIN_FAILURE',
        5,
        10,
        'HIGH'
    ),
    (
        'REPEATED_ACCESS_DENIAL',
        'Repeated access denial',
        'Detects repeated access denials',
        'ACCESS_DENIED',
        5,
        10,
        'MEDIUM'
    ),
    (
        'PRIVILEGE_CHANGE_MONITOR',
        'Privilege modification',
        'Detects privileged role changes',
        'PRIVILEGE_CHANGE',
        1,
        60,
        'CRITICAL'
    ),
    (
        'LARGE_DATA_EXPORT',
        'Large export activity',
        'Detects unusually large exports using an event threshold',
        'DATA_EXPORT',
        1,
        60,
        'HIGH'
    );

-- ============================================================
-- SAMPLE AUDIT RECORDS
-- ============================================================

INSERT INTO audit_logs (
    event_uuid,
    organization_id,
    system_id,
    user_id,
    event_timestamp,
    event_type,
    source_ip,
    resource,
    success,
    details,
    previous_hash,
    record_hash
)
VALUES
(
    '10000000-0000-4000-8000-000000000001',
    1, 1, 1,
    NOW() - INTERVAL '10 minutes',
    'LOGIN_SUCCESS',
    '192.168.1.10',
    '/authentication',
    TRUE,
    '{"method":"password+mfa"}',
    NULL,
    repeat('a', 64)
),
(
    '10000000-0000-4000-8000-000000000002',
    1, 1, 4,
    NOW() - INTERVAL '8 minutes',
    'LOGIN_FAILURE',
    '203.0.113.50',
    '/authentication',
    FALSE,
    '{"attempt":1}',
    repeat('a', 64),
    repeat('b', 64)
),
(
    '10000000-0000-4000-8000-000000000003',
    1, 1, 4,
    NOW() - INTERVAL '7 minutes',
    'LOGIN_FAILURE',
    '203.0.113.50',
    '/authentication',
    FALSE,
    '{"attempt":2}',
    repeat('b', 64),
    repeat('c', 64)
),
(
    '10000000-0000-4000-8000-000000000004',
    1, 1, 4,
    NOW() - INTERVAL '6 minutes',
    'LOGIN_FAILURE',
    '203.0.113.50',
    '/authentication',
    FALSE,
    '{"attempt":3}',
    repeat('c', 64),
    repeat('d', 64)
),
(
    '10000000-0000-4000-8000-000000000005',
    1, 1, 4,
    NOW() - INTERVAL '5 minutes',
    'LOGIN_FAILURE',
    '203.0.113.50',
    '/authentication',
    FALSE,
    '{"attempt":4}',
    repeat('d', 64),
    repeat('e', 64)
),
(
    '10000000-0000-4000-8000-000000000006',
    1, 1, 4,
    NOW() - INTERVAL '4 minutes',
    'LOGIN_FAILURE',
    '203.0.113.50',
    '/authentication',
    FALSE,
    '{"attempt":5}',
    repeat('e', 64),
    repeat('f', 64)
),
(
    '10000000-0000-4000-8000-000000000007',
    1, 1, 1,
    NOW() - INTERVAL '3 minutes',
    'ACCESS_DENIED',
    '192.168.1.10',
    '/credentials',
    FALSE,
    '{"reason":"insufficient_permission"}',
    repeat('f', 64),
    repeat('1', 64)
),
(
    '10000000-0000-4000-8000-000000000008',
    1, 1, 2,
    NOW() - INTERVAL '2 minutes',
    'PRIVILEGE_CHANGE',
    '192.168.1.20',
    '/admin',
    TRUE,
    '{"target_user":"alice","new_role":"administrator"}',
    repeat('1', 64),
    repeat('2', 64)
),
(
    '10000000-0000-4000-8000-000000000009',
    1, 3, 4,
    NOW() - INTERVAL '1 minute',
    'DATA_EXPORT',
    '203.0.113.50',
    '/financial-records',
    TRUE,
    '{"record_count":5000}',
    NULL,
    repeat('3', 64)
);

-- ============================================================
-- ACCESS LOG EXAMPLES
-- ============================================================

INSERT INTO access_logs (
    audit_id,
    user_id,
    resource,
    permission_requested,
    decision,
    source_ip,
    accessed_at
)
SELECT
    audit_id,
    user_id,
    resource,
    'READ',
    'ALLOW',
    source_ip,
    event_timestamp
FROM audit_logs
WHERE event_type = 'LOGIN_SUCCESS';

INSERT INTO access_logs (
    audit_id,
    user_id,
    resource,
    permission_requested,
    decision,
    source_ip,
    accessed_at
)
SELECT
    audit_id,
    user_id,
    resource,
    'READ',
    'DENY',
    source_ip,
    event_timestamp
FROM audit_logs
WHERE event_type = 'ACCESS_DENIED';

-- ============================================================
-- SAMPLE ALERTS
-- ============================================================

INSERT INTO security_alerts (
    alert_uuid,
    organization_id,
    system_id,
    user_id,
    rule_id,
    severity,
    category,
    description,
    anomaly_score
)
SELECT
    gen_random_uuid(),
    1,
    1,
    4,
    rule_id,
    'HIGH',
    'BRUTE_FORCE_LOGIN',
    'Repeated authentication failures detected',
    0.850
FROM detection_rules
WHERE rule_code = 'BRUTE_FORCE_LOGIN';

INSERT INTO security_alerts (
    alert_uuid,
    organization_id,
    system_id,
    user_id,
    rule_id,
    severity,
    category,
    description,
    anomaly_score
)
SELECT
    gen_random_uuid(),
    1,
    1,
    2,
    rule_id,
    'CRITICAL',
    'PRIVILEGE_CHANGE',
    'Administrative privilege modification observed',
    0.950
FROM detection_rules
WHERE rule_code = 'PRIVILEGE_CHANGE_MONITOR';

-- ============================================================
-- SAMPLE EVIDENCE
-- ============================================================

INSERT INTO alert_evidence (
    alert_id,
    audit_id,
    evidence_type
)
SELECT
    sa.alert_id,
    al.audit_id,
    'CORRELATED_EVENT'
FROM security_alerts sa
JOIN audit_logs al
  ON al.user_id = sa.user_id
 AND al.system_id = sa.system_id
WHERE sa.category = 'BRUTE_FORCE_LOGIN'
  AND al.event_type = 'LOGIN_FAILURE';

-- ============================================================
-- SAMPLE INVESTIGATION
-- ============================================================

INSERT INTO alert_investigations (
    alert_id,
    analyst_id,
    decision,
    investigation_notes
)
SELECT
    sa.alert_id,
    analyst.user_id,
    'UNREVIEWED',
    'Authentication pattern assigned for investigation'
FROM security_alerts sa
JOIN security_users analyst
  ON analyst.username = 'security_analyst'
WHERE sa.category = 'BRUTE_FORCE_LOGIN';

-- ============================================================
-- RETRIEVAL QUERY
-- ============================================================

SELECT
    audit_id,
    event_type,
    user_id,
    source_ip,
    resource,
    success,
    event_timestamp
FROM audit_logs
ORDER BY event_timestamp DESC;

-- ============================================================
-- ACCESS VALIDATION QUERY
-- ============================================================

SELECT
    u.username,
    r.resource,
    r.permission,
    check_access_permission(
        u.user_id,
        r.resource,
        r.permission
    ) AS authorized
FROM security_users u
CROSS JOIN (
    VALUES
        ('/application', 'READ'),
        ('/credentials', 'READ'),
        ('/financial-records', 'EXPORT'),
        ('/reports', 'READ')
) AS r(resource, permission)
WHERE u.username IN ('alice', 'carol', 'david')
ORDER BY u.username, r.resource;

-- ============================================================
-- AGGREGATION QUERY
-- ============================================================

SELECT
    event_type,
    COUNT(*) AS total_events,
    COUNT(*) FILTER (
        WHERE success
    ) AS successful_events,
    COUNT(*) FILTER (
        WHERE NOT success
    ) AS failed_events,
    COUNT(DISTINCT user_id) AS unique_users
FROM audit_logs
GROUP BY event_type
ORDER BY total_events DESC;

-- ============================================================
-- EVALUATION QUERY
-- ============================================================

SELECT
    username,
    COUNT(*) AS failed_attempts,
    COUNT(DISTINCT source_ip) AS source_addresses,
    MIN(event_timestamp) AS first_attempt,
    MAX(event_timestamp) AS last_attempt
FROM audit_logs al
JOIN security_users su
  ON su.user_id = al.user_id
WHERE al.event_type = 'LOGIN_FAILURE'
  AND al.event_timestamp >= NOW() - INTERVAL '10 minutes'
GROUP BY username
HAVING COUNT(*) >= 5;

-- ============================================================
-- REPORTING QUERY
-- ============================================================

SELECT
    organization_name,
    system_name,
    severity,
    status,
    COUNT(*) AS alert_count,
    ROUND(AVG(anomaly_score), 3) AS average_score
FROM v_security_alert_dashboard
GROUP BY
    organization_name,
    system_name,
    severity,
    status
ORDER BY alert_count DESC;

-- ============================================================
-- CTE: CORRELATE MULTIPLE SECURITY EVENTS
-- ============================================================

WITH user_activity AS (
    SELECT
        user_id,
        COUNT(*) AS total_events,
        COUNT(*) FILTER (
            WHERE event_type = 'LOGIN_FAILURE'
        ) AS failed_logins,
        COUNT(DISTINCT source_ip) AS source_count,
        COUNT(*) FILTER (
            WHERE event_type = 'DATA_EXPORT'
        ) AS exports
    FROM audit_logs
    WHERE event_timestamp >= NOW() - INTERVAL '1 hour'
    GROUP BY user_id
),
risk_evaluation AS (
    SELECT
        *,
        (
            CASE WHEN failed_logins >= 5
                THEN 0.40 ELSE 0 END
            +
            CASE WHEN source_count >= 3
                THEN 0.25 ELSE 0 END
            +
            CASE WHEN exports >= 2
                THEN 0.35 ELSE 0 END
        ) AS risk_score
    FROM user_activity
)
SELECT
    u.username,
    r.total_events,
    r.failed_logins,
    r.source_count,
    r.exports,
    ROUND(r.risk_score::NUMERIC, 3) AS risk_score,
    CASE
        WHEN r.risk_score >= 0.75 THEN 'CRITICAL'
        WHEN r.risk_score >= 0.50 THEN 'HIGH'
        WHEN r.risk_score >= 0.25 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS risk_level
FROM risk_evaluation r
JOIN security_users u
  ON u.user_id = r.user_id
ORDER BY risk_score DESC;

-- ============================================================
-- WORKFLOW PROCESSING
-- ============================================================

/*
 * The procedure correlates an existing audit event with
 * enabled detection rules and creates alerts with evidence.
 *
 * Repeated invocation can create repeated alerts. A production
 * deployment should add a rule/event deduplication key.
 */

CALL create_alert_from_event(2);

-- ============================================================
-- ELIGIBILITY AND ALERT INVESTIGATION
-- ============================================================

UPDATE security_alerts
SET
    status = 'INVESTIGATING',
    assigned_to = (
        SELECT user_id
        FROM security_users
        WHERE username = 'security_analyst'
    )
WHERE category = 'BRUTE_FORCE_LOGIN'
  AND status = 'OPEN';

-- ============================================================
-- ALERT STATUS REPORT
-- ============================================================

SELECT
    status,
    severity,
    COUNT(*) AS total
FROM security_alerts
GROUP BY status, severity
ORDER BY severity, status;

-- ============================================================
-- TRANSACTION FAILURE DEMONSTRATION
-- ============================================================

/*
 * This block intentionally attempts to assign an invalid
 * alert transition. The nested exception block rolls back
 * only its own subtransaction and leaves the main transaction
 * usable.
 */

DO $$
DECLARE
    v_alert_id BIGINT;
BEGIN

    SELECT alert_id
    INTO v_alert_id
    FROM security_alerts
    WHERE status = 'INVESTIGATING'
    LIMIT 1;

    IF v_alert_id IS NOT NULL THEN

        BEGIN

            UPDATE security_alerts
            SET status = 'RESOLVED'
            WHERE alert_id = v_alert_id;

            RAISE NOTICE
                'Alert resolved through valid state transition';

        EXCEPTION
            WHEN OTHERS THEN

                RAISE NOTICE
                    'Alert transition failed: %',
                    SQLERRM;

        END;

    END IF;

END;
$$;

-- ============================================================
-- FINAL REPORT
-- ============================================================

SELECT
    alert_id,
    username,
    system_name,
    severity,
    category,
    status,
    anomaly_score,
    assigned_analyst,
    created_at
FROM v_security_alert_dashboard
ORDER BY created_at DESC;

SELECT *
FROM v_hourly_security_metrics
ORDER BY event_hour DESC;

COMMIT;
