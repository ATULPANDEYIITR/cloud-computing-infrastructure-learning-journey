/*
===============================================================================
SECURE CLOUD ENVIRONMENT
PostgreSQL 15+

Relational governance model covering:

1. Cloud organizations and accounts
2. IAM identities and roles
3. IAM policies and policy statements
4. Encryption keys and key rotation
5. Storage resources and encryption metadata
6. Network segments and security rules
7. Pull-independent security audit events
8. Security assessments and findings
9. Cloud compliance and operational reporting

Encryption is enforced as a metadata and lifecycle requirement.
Actual encryption must be performed by a cloud KMS or HSM.

The script creates an isolated schema named cloud_security.
===============================================================================
*/

BEGIN;

CREATE SCHEMA IF NOT EXISTS cloud_security;

SET search_path TO cloud_security, public;


-- ============================================================================
-- 1. ORGANIZATIONS AND CLOUD ACCOUNTS
-- ============================================================================

CREATE TABLE organizations (
    organization_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_name VARCHAR(150) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cloud_accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),

    account_name VARCHAR(150) NOT NULL UNIQUE,

    environment VARCHAR(20) NOT NULL
        CHECK (
            environment IN (
                'DEVELOPMENT',
                'STAGING',
                'PRODUCTION'
            )
        ),

    region VARCHAR(50) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_accounts_organization
ON cloud_accounts(organization_id);


-- ============================================================================
-- 2. IAM IDENTITIES AND ROLES
-- ============================================================================

CREATE TABLE iam_roles (
    role_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL
        REFERENCES cloud_accounts(account_id),

    role_name VARCHAR(100) NOT NULL,

    description TEXT,

    privileged BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(account_id, role_name)
);

CREATE TABLE iam_identities (
    identity_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    account_id BIGINT NOT NULL
        REFERENCES cloud_accounts(account_id),

    identity_name VARCHAR(120) NOT NULL,

    identity_type VARCHAR(20) NOT NULL
        CHECK (
            identity_type IN (
                'USER',
                'SERVICE',
                'APPLICATION'
            )
        ),

    role_id BIGINT
        REFERENCES iam_roles(role_id),

    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (
            status IN (
                'ACTIVE',
                'SUSPENDED',
                'DISABLED'
            )
        ),

    mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,

    last_authenticated_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(account_id, identity_name)
);

CREATE INDEX idx_iam_identity_status
ON iam_identities(status, account_id);

CREATE INDEX idx_iam_identity_role
ON iam_identities(role_id);


-- ============================================================================
-- 3. IAM POLICY MODEL
-- ============================================================================

CREATE TABLE iam_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    account_id BIGINT NOT NULL
        REFERENCES cloud_accounts(account_id),

    policy_name VARCHAR(120) NOT NULL,

    policy_version INTEGER NOT NULL DEFAULT 1
        CHECK (policy_version > 0),

    description TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(account_id, policy_name)
);

CREATE TABLE iam_policy_statements (
    statement_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    policy_id BIGINT NOT NULL
        REFERENCES iam_policies(policy_id)
        ON DELETE CASCADE,

    effect VARCHAR(10) NOT NULL
        CHECK (effect IN ('ALLOW', 'DENY')),

    action_pattern VARCHAR(150) NOT NULL,

    resource_pattern VARCHAR(250) NOT NULL,

    CHECK (
        LENGTH(TRIM(action_pattern)) > 0
        AND LENGTH(TRIM(resource_pattern)) > 0
    )
);

CREATE INDEX idx_policy_statements_policy
ON iam_policy_statements(policy_id);

CREATE TABLE role_policy_assignments (
    role_id BIGINT NOT NULL
        REFERENCES iam_roles(role_id)
        ON DELETE CASCADE,

    policy_id BIGINT NOT NULL
        REFERENCES iam_policies(policy_id)
        ON DELETE CASCADE,

    assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY(role_id, policy_id)
);


-- ============================================================================
-- 4. ENCRYPTION KEY MANAGEMENT
-- ============================================================================

CREATE TABLE encryption_keys (
    key_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    account_id BIGINT NOT NULL
        REFERENCES cloud_accounts(account_id),

    key_alias VARCHAR(120) NOT NULL,

    external_key_reference VARCHAR(250) NOT NULL,

    algorithm VARCHAR(50) NOT NULL
        CHECK (
            algorithm IN (
                'AES-256-GCM',
                'RSA-3072',
                'RSA-4096',
                'CLOUD_KMS_MANAGED'
            )
        ),

    key_version INTEGER NOT NULL DEFAULT 1
        CHECK (key_version > 0),

    key_status VARCHAR(20) NOT NULL DEFAULT 'ENABLED'
        CHECK (
            key_status IN (
                'ENABLED',
                'DISABLED',
                'PENDING_DELETION',
                'DESTROYED'
            )
        ),

    rotation_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    rotation_interval_days INTEGER NOT NULL DEFAULT 90
        CHECK (rotation_interval_days BETWEEN 1 AND 3650),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    last_rotated_at TIMESTAMPTZ,

    UNIQUE(account_id, key_alias),
    UNIQUE(external_key_reference)
);

CREATE INDEX idx_encryption_key_status
ON encryption_keys(account_id, key_status);


CREATE TABLE key_rotation_history (
    rotation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    key_id BIGINT NOT NULL
        REFERENCES encryption_keys(key_id),

    previous_version INTEGER NOT NULL,

    new_version INTEGER NOT NULL,

    rotated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    rotated_by BIGINT
        REFERENCES iam_identities(identity_id),

    CHECK (new_version > previous_version)
);


-- ============================================================================
-- 5. CLOUD STORAGE RESOURCES
-- ============================================================================

CREATE TABLE storage_resources (
    resource_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    account_id BIGINT NOT NULL
        REFERENCES cloud_accounts(account_id),

    resource_name VARCHAR(150) NOT NULL,

    resource_type VARCHAR(30) NOT NULL
        CHECK (
            resource_type IN (
                'OBJECT_BUCKET',
                'DATABASE',
                'VOLUME',
                'BACKUP',
                'FILE_SYSTEM'
            )
        ),

    owner_identity_id BIGINT
        REFERENCES iam_identities(identity_id),

    data_classification VARCHAR(20) NOT NULL
        CHECK (
            data_classification IN (
                'PUBLIC',
                'INTERNAL',
                'CONFIDENTIAL',
                'RESTRICTED'
            )
        ),

    encryption_required BOOLEAN NOT NULL DEFAULT TRUE,

    key_id BIGINT
        REFERENCES encryption_keys(key_id),

    encryption_status VARCHAR(20) NOT NULL DEFAULT 'NOT_ENCRYPTED'
        CHECK (
            encryption_status IN (
                'NOT_ENCRYPTED',
                'ENCRYPTED',
                'FAILED'
            )
        ),

    public_access_enabled BOOLEAN NOT NULL DEFAULT FALSE,

    resource_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (
            resource_status IN (
                'ACTIVE',
                'BLOCKED',
                'DELETED'
            )
        ),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(account_id, resource_name),

    CHECK (
        encryption_status <> 'ENCRYPTED'
        OR key_id IS NOT NULL
    ),

    CHECK (
        data_classification <> 'RESTRICTED'
        OR public_access_enabled = FALSE
    )
);

CREATE INDEX idx_storage_account_classification
ON storage_resources(
    account_id,
    data_classification,
    encryption_status
);

CREATE INDEX idx_storage_key
ON storage_resources(key_id);


-- ============================================================================
-- 6. NETWORK ISOLATION
-- ============================================================================

CREATE TABLE network_segments (
    segment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    account_id BIGINT NOT NULL
        REFERENCES cloud_accounts(account_id),

    segment_name VARCHAR(100) NOT NULL,

    cidr_block CIDR NOT NULL,

    segment_type VARCHAR(20) NOT NULL
        CHECK (
            segment_type IN (
                'PUBLIC',
                'PRIVATE',
                'DATABASE',
                'MANAGEMENT'
            )
        ),

    internet_routable BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(account_id, segment_name)
);

CREATE TABLE network_security_rules (
    rule_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    segment_id BIGINT NOT NULL
        REFERENCES network_segments(segment_id)
        ON DELETE CASCADE,

    source_cidr CIDR NOT NULL,

    destination_segment_id BIGINT
        REFERENCES network_segments(segment_id),

    destination_port INTEGER NOT NULL
        CHECK (destination_port BETWEEN 1 AND 65535),

    protocol VARCHAR(10) NOT NULL
        CHECK (
            protocol IN (
                'TCP',
                'UDP',
                'ICMP'
            )
        ),

    effect VARCHAR(10) NOT NULL
        CHECK (effect IN ('ALLOW', 'DENY')),

    priority INTEGER NOT NULL DEFAULT 100
        CHECK (priority BETWEEN 1 AND 65535),

    description TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_network_rules_segment_priority
ON network_security_rules(segment_id, priority);


-- ============================================================================
-- 7. AUDIT LOGGING
-- ============================================================================

CREATE TABLE audit_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    event_uuid UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),

    account_id BIGINT
        REFERENCES cloud_accounts(account_id),

    identity_id BIGINT
        REFERENCES iam_identities(identity_id),

    action VARCHAR(150) NOT NULL,

    resource_reference VARCHAR(250) NOT NULL,

    outcome VARCHAR(20) NOT NULL
        CHECK (
            outcome IN (
                'SUCCESS',
                'DENIED',
                'FAILURE'
            )
        ),

    severity VARCHAR(15) NOT NULL
        CHECK (
            severity IN (
                'LOW',
                'MEDIUM',
                'HIGH',
                'CRITICAL'
            )
        ),

    source_ip INET,

    event_details JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_account_time
ON audit_events(account_id, created_at DESC);

CREATE INDEX idx_audit_severity_time
ON audit_events(severity, created_at DESC);

CREATE INDEX idx_audit_details
ON audit_events USING GIN(event_details);


-- ============================================================================
-- 8. SECURITY ASSESSMENTS
-- ============================================================================

CREATE TABLE security_assessments (
    assessment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    account_id BIGINT NOT NULL
        REFERENCES cloud_accounts(account_id),

    assessment_name VARCHAR(150) NOT NULL,

    assessment_status VARCHAR(20) NOT NULL DEFAULT 'RUNNING'
        CHECK (
            assessment_status IN (
                'RUNNING',
                'COMPLETED',
                'FAILED'
            )
        ),

    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    completed_at TIMESTAMPTZ,

    CHECK (
        completed_at IS NULL
        OR completed_at >= started_at
    )
);

CREATE TABLE security_findings (
    finding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    assessment_id BIGINT NOT NULL
        REFERENCES security_assessments(assessment_id)
        ON DELETE CASCADE,

    account_id BIGINT NOT NULL
        REFERENCES cloud_accounts(account_id),

    category VARCHAR(30) NOT NULL
        CHECK (
            category IN (
                'IAM',
                'ENCRYPTION',
                'NETWORK',
                'AUDIT',
                'PUBLIC_ACCESS',
                'KEY_MANAGEMENT'
            )
        ),

    severity VARCHAR(15) NOT NULL
        CHECK (
            severity IN (
                'LOW',
                'MEDIUM',
                'HIGH',
                'CRITICAL'
            )
        ),

    resource_reference VARCHAR(250) NOT NULL,

    description TEXT NOT NULL,

    remediation_status VARCHAR(20) NOT NULL DEFAULT 'OPEN'
        CHECK (
            remediation_status IN (
                'OPEN',
                'IN_PROGRESS',
                'RESOLVED',
                'ACCEPTED_RISK'
            )
        ),

    detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    resolved_at TIMESTAMPTZ
);

CREATE INDEX idx_findings_account_status
ON security_findings(
    account_id,
    remediation_status,
    severity
);


-- ============================================================================
-- 9. AUDIT IMMUTABILITY PROTECTION
-- ============================================================================

CREATE OR REPLACE FUNCTION prevent_audit_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'Audit events cannot be updated or deleted';
END;
$$;

CREATE TRIGGER audit_no_update
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW
EXECUTE FUNCTION prevent_audit_mutation();


-- ============================================================================
-- 10. AUDIT EVENT INSERTION FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION record_audit_event(
    p_account_id BIGINT,
    p_identity_id BIGINT,
    p_action VARCHAR,
    p_resource VARCHAR,
    p_outcome VARCHAR,
    p_severity VARCHAR,
    p_details JSONB DEFAULT '{}'::JSONB
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_event_id BIGINT;
BEGIN
    IF LENGTH(TRIM(p_action)) = 0 THEN
        RAISE EXCEPTION 'Audit action cannot be empty';
    END IF;

    INSERT INTO audit_events (
        account_id,
        identity_id,
        action,
        resource_reference,
        outcome,
        severity,
        event_details
    )
    VALUES (
        p_account_id,
        p_identity_id,
        p_action,
        p_resource,
        p_outcome,
        p_severity,
        COALESCE(p_details, '{}'::JSONB)
    )
    RETURNING event_id INTO v_event_id;

    RETURN v_event_id;
END;
$$;


-- ============================================================================
-- 11. IAM AUTHORIZATION FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION authorize_iam_action(
    p_identity_id BIGINT,
    p_action VARCHAR,
    p_resource VARCHAR,
    p_require_mfa BOOLEAN DEFAULT TRUE
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_role_id BIGINT;
    v_account_id BIGINT;
    v_allowed BOOLEAN := FALSE;
    v_denied BOOLEAN := FALSE;
    v_mfa BOOLEAN;
BEGIN

    SELECT
        i.role_id,
        i.account_id,
        i.mfa_enabled
    INTO
        v_role_id,
        v_account_id,
        v_mfa
    FROM iam_identities i
    JOIN cloud_accounts a
        ON a.account_id = i.account_id
    WHERE
        i.identity_id = p_identity_id
        AND i.status = 'ACTIVE'
        AND a.active = TRUE;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    IF p_require_mfa AND NOT v_mfa THEN
        RETURN FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM iam_roles r
        WHERE
            r.role_id = v_role_id
            AND r.account_id = v_account_id
    ) THEN
        RETURN FALSE;
    END IF;

    SELECT
        COALESCE(
            BOOL_OR(
                s.effect = 'ALLOW'
                AND (
                    s.action_pattern = '*'
                    OR p_action LIKE REPLACE(
                        s.action_pattern,
                        '*',
                        '%'
                    )
                )
                AND (
                    s.resource_pattern = '*'
                    OR p_resource LIKE REPLACE(
                        s.resource_pattern,
                        '*',
                        '%'
                    )
                )
            ),
            FALSE
        ),
        COALESCE(
            BOOL_OR(
                s.effect = 'DENY'
                AND (
                    s.action_pattern = '*'
                    OR p_action LIKE REPLACE(
                        s.action_pattern,
                        '*',
                        '%'
                    )
                )
                AND (
                    s.resource_pattern = '*'
                    OR p_resource LIKE REPLACE(
                        s.resource_pattern,
                        '*',
                        '%'
                    )
                )
            ),
            FALSE
        )
    INTO
        v_allowed,
        v_denied
    FROM role_policy_assignments rpa
    JOIN iam_policy_statements s
        ON s.policy_id = rpa.policy_id
    WHERE rpa.role_id = v_role_id;

    RETURN v_allowed AND NOT v_denied;
END;
$$;


-- ============================================================================
-- 12. STORAGE ENCRYPTION VALIDATION FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION storage_is_secure(
    p_resource_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM storage_resources s
        JOIN encryption_keys k
            ON k.key_id = s.key_id
        WHERE
            s.resource_id = p_resource_id
            AND s.encryption_required = TRUE
            AND s.encryption_status = 'ENCRYPTED'
            AND s.resource_status = 'ACTIVE'
            AND k.key_status = 'ENABLED'
    );
$$;


-- ============================================================================
-- 13. RESOURCE ENCRYPTION ENFORCEMENT
-- ============================================================================

CREATE OR REPLACE FUNCTION enforce_storage_encryption()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_key_account BIGINT;
    v_key_status VARCHAR;
BEGIN

    IF NEW.encryption_required THEN

        IF NEW.encryption_status <> 'ENCRYPTED' THEN
            RAISE EXCEPTION
                'Encryption is mandatory for resource %',
                NEW.resource_name;
        END IF;

        IF NEW.key_id IS NULL THEN
            RAISE EXCEPTION
                'Encryption key is required';
        END IF;

        SELECT account_id, key_status
        INTO v_key_account, v_key_status
        FROM encryption_keys
        WHERE key_id = NEW.key_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION
                'Encryption key does not exist';
        END IF;

        IF v_key_account <> NEW.account_id THEN
            RAISE EXCEPTION
                'Cross-account encryption key assignment is prohibited';
        END IF;

        IF v_key_status <> 'ENABLED' THEN
            RAISE EXCEPTION
                'Encryption key must be enabled';
        END IF;

    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER storage_encryption_guard
BEFORE INSERT OR UPDATE ON storage_resources
FOR EACH ROW
EXECUTE FUNCTION enforce_storage_encryption();


-- ============================================================================
-- 14. KEY ROTATION PROCEDURE
-- ============================================================================

CREATE OR REPLACE PROCEDURE rotate_encryption_key(
    p_key_id BIGINT,
    p_identity_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_previous_version INTEGER;
BEGIN

    SELECT key_version
    INTO v_previous_version
    FROM encryption_keys
    WHERE
        key_id = p_key_id
        AND key_status = 'ENABLED'
        AND rotation_enabled = TRUE
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Key cannot be rotated';
    END IF;

    UPDATE encryption_keys
    SET
        key_version = key_version + 1,
        last_rotated_at = CURRENT_TIMESTAMP
    WHERE key_id = p_key_id;

    INSERT INTO key_rotation_history (
        key_id,
        previous_version,
        new_version,
        rotated_by
    )
    VALUES (
        p_key_id,
        v_previous_version,
        v_previous_version + 1,
        p_identity_id
    );

    INSERT INTO audit_events (
        identity_id,
        action,
        resource_reference,
        outcome,
        severity,
        event_details
    )
    VALUES (
        p_identity_id,
        'kms:rotate',
        'key:' || p_key_id,
        'SUCCESS',
        'MEDIUM',
        jsonb_build_object(
            'previous_version', v_previous_version,
            'new_version', v_previous_version + 1
        )
    );

END;
$$;


-- ============================================================================
-- 15. NETWORK ACCESS EVALUATION
-- ============================================================================

CREATE OR REPLACE FUNCTION evaluate_network_access(
    p_segment_id BIGINT,
    p_source INET,
    p_destination_segment_id BIGINT,
    p_port INTEGER,
    p_protocol VARCHAR
)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_effect VARCHAR;
BEGIN

    IF p_port < 1 OR p_port > 65535 THEN
        RETURN FALSE;
    END IF;

    IF p_protocol NOT IN ('TCP', 'UDP', 'ICMP') THEN
        RETURN FALSE;
    END IF;

    /*
     * Lower priority numbers are evaluated first.
     * If no rule matches, network access is denied.
     */
    SELECT effect
    INTO v_effect
    FROM network_security_rules
    WHERE
        segment_id = p_segment_id
        AND source_cidr >>= p_source
        AND (
            destination_segment_id IS NULL
            OR destination_segment_id = p_destination_segment_id
        )
        AND destination_port = p_port
        AND protocol = p_protocol
    ORDER BY priority ASC, rule_id ASC
    LIMIT 1;

    RETURN COALESCE(v_effect = 'ALLOW', FALSE);
END;
$$;


-- ============================================================================
-- 16. SECURITY ASSESSMENT VIEW
-- ============================================================================

CREATE OR REPLACE VIEW storage_security_posture AS
SELECT
    s.resource_id,
    a.account_name,
    s.resource_name,
    s.resource_type,
    s.data_classification,
    s.encryption_required,
    s.encryption_status,
    k.key_alias,
    k.key_status,
    s.public_access_enabled,
    CASE
        WHEN s.encryption_required
             AND s.encryption_status <> 'ENCRYPTED'
            THEN 'CRITICAL'

        WHEN s.encryption_required
             AND k.key_status IS DISTINCT FROM 'ENABLED'
            THEN 'CRITICAL'

        WHEN s.public_access_enabled
             AND s.data_classification IN (
                 'CONFIDENTIAL',
                 'RESTRICTED'
             )
            THEN 'CRITICAL'

        ELSE 'COMPLIANT'
    END AS security_status
FROM storage_resources s
JOIN cloud_accounts a
    ON a.account_id = s.account_id
LEFT JOIN encryption_keys k
    ON k.key_id = s.key_id;


-- ============================================================================
-- 17. IAM IDENTITY SECURITY VIEW
-- ============================================================================

CREATE OR REPLACE VIEW iam_security_posture AS
SELECT
    i.identity_id,
    i.identity_name,
    i.identity_type,
    i.status,
    i.mfa_enabled,
    r.role_name,
    r.privileged,
    CASE
        WHEN i.status = 'ACTIVE'
             AND i.mfa_enabled = FALSE
            THEN 'MFA_REQUIRED'

        WHEN r.privileged = TRUE
             AND i.mfa_enabled = FALSE
            THEN 'PRIVILEGED_ACCESS_RISK'

        ELSE 'COMPLIANT'
    END AS security_status
FROM iam_identities i
LEFT JOIN iam_roles r
    ON r.role_id = i.role_id;


-- ============================================================================
-- 18. SECURITY FINDING AGGREGATION VIEW
-- ============================================================================

CREATE OR REPLACE VIEW security_finding_summary AS
SELECT
    account_id,
    category,
    severity,
    remediation_status,
    COUNT(*) AS finding_count
FROM security_findings
GROUP BY
    account_id,
    category,
    severity,
    remediation_status;


-- ============================================================================
-- 19. ELIGIBILITY VIEW
-- ============================================================================

CREATE OR REPLACE VIEW cloud_resource_eligibility AS
SELECT
    s.resource_id,
    s.resource_name,
    a.account_name,
    s.resource_status,
    CASE
        WHEN a.active = FALSE THEN FALSE
        WHEN s.resource_status <> 'ACTIVE' THEN FALSE
        WHEN s.encryption_required
             AND NOT storage_is_secure(s.resource_id)
            THEN FALSE
        WHEN s.public_access_enabled
             AND s.data_classification IN (
                 'CONFIDENTIAL',
                 'RESTRICTED'
             )
            THEN FALSE
        ELSE TRUE
    END AS eligible
FROM storage_resources s
JOIN cloud_accounts a
    ON a.account_id = s.account_id;


-- ============================================================================
-- 20. REPORTING QUERIES
-- ============================================================================

-- Storage security report.
SELECT *
FROM storage_security_posture
ORDER BY account_name, resource_name;

-- IAM security report.
SELECT *
FROM iam_security_posture
ORDER BY privileged DESC, identity_name;

-- Security finding aggregation.
SELECT *
FROM security_finding_summary
ORDER BY account_id, severity;

-- Audit event aggregation.
SELECT
    account_id,
    outcome,
    severity,
    COUNT(*) AS event_count
FROM audit_events
GROUP BY account_id, outcome, severity
ORDER BY account_id, severity;

-- Resource eligibility report.
SELECT *
FROM cloud_resource_eligibility
ORDER BY eligible, resource_name;


-- ============================================================================
-- 21. SAMPLE ORGANIZATION AND ACCOUNT DATA
-- ============================================================================

INSERT INTO organizations(organization_name)
VALUES ('Secure Enterprise Group');

INSERT INTO cloud_accounts(
    organization_id,
    account_name,
    environment,
    region
)
VALUES
(
    1,
    'production-account',
    'PRODUCTION',
    'ap-south-1'
),
(
    1,
    'development-account',
    'DEVELOPMENT',
    'ap-south-1'
);


-- ============================================================================
-- 22. SAMPLE IAM ROLES
-- ============================================================================

INSERT INTO iam_roles(
    account_id,
    role_name,
    description,
    privileged
)
VALUES
(
    1,
    'security-administrator',
    'Cloud security administration',
    TRUE
),
(
    1,
    'application-reader',
    'Read-only production application access',
    FALSE
),
(
    1,
    'database-service',
    'Database service identity',
    FALSE
),
(
    2,
    'development-operator',
    'Development environment operator',
    FALSE
);


-- ============================================================================
-- 23. SAMPLE IAM POLICIES
-- ============================================================================

INSERT INTO iam_policies(
    account_id,
    policy_name,
    description
)
VALUES
(
    1,
    'production-read-policy',
    'Read access to production resources'
),
(
    1,
    'restricted-delete-policy',
    'Explicitly denies destructive storage operations'
),
(
    1,
    'administrator-policy',
    'Controlled security administration'
);


INSERT INTO iam_policy_statements(
    policy_id,
    effect,
    action_pattern,
    resource_pattern
)
VALUES
(1, 'ALLOW', 'storage:read', 'bucket:production/*'),
(2, 'DENY', 'storage:delete', '*'),
(3, 'ALLOW', 'security:audit', '*');


INSERT INTO role_policy_assignments(role_id, policy_id)
VALUES
(2, 1),
(2, 2),
(1, 3);


-- ============================================================================
-- 24. SAMPLE IDENTITIES
-- ============================================================================

INSERT INTO iam_identities(
    account_id,
    identity_name,
    identity_type,
    role_id,
    status,
    mfa_enabled
)
VALUES
(
    1,
    'security-admin',
    'USER',
    1,
    'ACTIVE',
    TRUE
),
(
    1,
    'reporting-service',
    'SERVICE',
    2,
    'ACTIVE',
    TRUE
),
(
    1,
    'database-application',
    'APPLICATION',
    3,
    'ACTIVE',
    TRUE
),
(
    1,
    'legacy-user',
    'USER',
    2,
    'ACTIVE',
    FALSE
);


-- ============================================================================
-- 25. SAMPLE ENCRYPTION KEYS
-- ============================================================================

INSERT INTO encryption_keys(
    account_id,
    key_alias,
    external_key_reference,
    algorithm,
    key_version,
    key_status,
    rotation_enabled
)
VALUES
(
    1,
    'production-master-key',
    'kms://production/master-key',
    'AES-256-GCM',
    1,
    'ENABLED',
    TRUE
),
(
    1,
    'disabled-test-key',
    'kms://production/disabled-key',
    'AES-256-GCM',
    1,
    'DISABLED',
    TRUE
),
(
    2,
    'development-key',
    'kms://development/storage-key',
    'AES-256-GCM',
    1,
    'ENABLED',
    TRUE
);


-- ============================================================================
-- 26. SAMPLE STORAGE RESOURCES
-- ============================================================================

INSERT INTO storage_resources(
    account_id,
    resource_name,
    resource_type,
    owner_identity_id,
    data_classification,
    encryption_required,
    key_id,
    encryption_status,
    public_access_enabled
)
VALUES
(
    1,
    'production-database-backup',
    'BACKUP',
    3,
    'RESTRICTED',
    TRUE,
    1,
    'ENCRYPTED',
    FALSE
),
(
    1,
    'production-report-bucket',
    'OBJECT_BUCKET',
    2,
    'CONFIDENTIAL',
    TRUE,
    1,
    'ENCRYPTED',
    FALSE
),
(
    2,
    'development-assets',
    'OBJECT_BUCKET',
    NULL,
    'INTERNAL',
    TRUE,
    3,
    'ENCRYPTED',
    FALSE
);


-- ============================================================================
-- 27. SAMPLE NETWORK SEGMENTS
-- ============================================================================

INSERT INTO network_segments(
    account_id,
    segment_name,
    cidr_block,
    segment_type,
    internet_routable
)
VALUES
(
    1,
    'public-subnet',
    '10.10.1.0/24',
    'PUBLIC',
    TRUE
),
(
    1,
    'application-subnet',
    '10.10.2.0/24',
    'PRIVATE',
    FALSE
),
(
    1,
    'database-subnet',
    '10.10.3.0/24',
    'DATABASE',
    FALSE
);


-- ============================================================================
-- 28. SAMPLE NETWORK RULES
-- ============================================================================

INSERT INTO network_security_rules(
    segment_id,
    source_cidr,
    destination_segment_id,
    destination_port,
    protocol,
    effect,
    priority,
    description
)
VALUES
(
    3,
    '10.10.2.0/24',
    3,
    5432,
    'TCP',
    'ALLOW',
    100,
    'Application subnet to PostgreSQL'
),
(
    3,
    '0.0.0.0/0',
    3,
    5432,
    'TCP',
    'DENY',
    200,
    'Block internet access to database'
);


-- ============================================================================
-- 29. SECURITY ASSESSMENT SAMPLE
-- ============================================================================

INSERT INTO security_assessments(
    account_id,
    assessment_name,
    assessment_status,
    completed_at
)
VALUES
(
    1,
    'Production baseline assessment',
    'COMPLETED',
    CURRENT_TIMESTAMP
);

INSERT INTO security_findings(
    assessment_id,
    account_id,
    category,
    severity,
    resource_reference,
    description,
    remediation_status
)
VALUES
(
    1,
    1,
    'IAM',
    'HIGH',
    'legacy-user',
    'Active identity does not have MFA',
    'OPEN'
),
(
    1,
    1,
    'ENCRYPTION',
    'CRITICAL',
    'unmanaged-storage',
    'Storage resource requires encryption verification',
    'IN_PROGRESS'
);


-- ============================================================================
-- 30. IAM AUTHORIZATION TESTS
-- ============================================================================

SELECT
    authorize_iam_action(
        2,
        'storage:read',
        'bucket:production/reports'
    ) AS expected_allow;

SELECT
    authorize_iam_action(
        2,
        'storage:delete',
        'bucket:production/reports'
    ) AS expected_deny;

SELECT
    authorize_iam_action(
        4,
        'storage:read',
        'bucket:production/reports'
    ) AS expected_mfa_deny;


-- ============================================================================
-- 31. NETWORK ACCESS TESTS
-- ============================================================================

SELECT
    evaluate_network_access(
        3,
        '10.10.2.10'::INET,
        3,
        5432,
        'TCP'
    ) AS application_access;

SELECT
    evaluate_network_access(
        3,
        '192.0.2.10'::INET,
        3,
        5432,
        'TCP'
    ) AS external_access;


-- ============================================================================
-- 32. ENCRYPTION TESTS
-- ============================================================================

SELECT
    resource_name,
    storage_is_secure(resource_id) AS encryption_valid
FROM storage_resources;


-- ============================================================================
-- 33. TRANSACTIONAL KEY ROTATION
-- ============================================================================

BEGIN;

CALL rotate_encryption_key(1, 1);

COMMIT;


-- ============================================================================
-- 34. AUDIT INSERTION
-- ============================================================================

SELECT record_audit_event(
    1,
    1,
    'security:assessment',
    'production-account',
    'SUCCESS',
    'LOW',
    '{"source":"scheduled-assessment"}'::JSONB
);


-- ============================================================================
-- 35. OPERATIONAL SECURITY REPORT
-- ============================================================================

WITH account_metrics AS (
    SELECT
        a.account_id,
        a.account_name,
        COUNT(s.resource_id) AS total_resources,
        COUNT(*) FILTER (
            WHERE s.encryption_status = 'ENCRYPTED'
        ) AS encrypted_resources,
        COUNT(*) FILTER (
            WHERE s.public_access_enabled
        ) AS public_resources
    FROM cloud_accounts a
    LEFT JOIN storage_resources s
        ON s.account_id = a.account_id
    GROUP BY
        a.account_id,
        a.account_name
),
identity_metrics AS (
    SELECT
        account_id,
        COUNT(*) AS total_identities,
        COUNT(*) FILTER (
            WHERE status = 'ACTIVE' AND NOT mfa_enabled
        ) AS active_without_mfa
    FROM iam_identities
    GROUP BY account_id
),
finding_metrics AS (
    SELECT
        account_id,
        COUNT(*) FILTER (
            WHERE severity IN ('HIGH', 'CRITICAL')
              AND remediation_status = 'OPEN'
        ) AS open_high_risk_findings
    FROM security_findings
    GROUP BY account_id
)
SELECT
    am.account_name,
    am.total_resources,
    am.encrypted_resources,
    am.public_resources,
    COALESCE(im.total_identities, 0) AS total_identities,
    COALESCE(im.active_without_mfa, 0) AS active_without_mfa,
    COALESCE(fm.open_high_risk_findings, 0)
        AS open_high_risk_findings
FROM account_metrics am
LEFT JOIN identity_metrics im
    ON im.account_id = am.account_id
LEFT JOIN finding_metrics fm
    ON fm.account_id = am.account_id
ORDER BY am.account_name;


-- ============================================================================
-- 36. SECURITY EXCEPTIONS AND FAILED OPERATIONS
-- ============================================================================

-- Failed and denied operations.
SELECT
    event_id,
    created_at,
    action,
    resource_reference,
    outcome,
    severity
FROM audit_events
WHERE outcome IN ('DENIED', 'FAILURE')
ORDER BY created_at DESC;

-- Unresolved critical findings.
SELECT
    finding_id,
    category,
    resource_reference,
    description,
    detected_at
FROM security_findings
WHERE
    severity = 'CRITICAL'
    AND remediation_status IN ('OPEN', 'IN_PROGRESS')
ORDER BY detected_at DESC;


-- ============================================================================
-- 37. DATABASE SECURITY RECOMMENDATIONS
-- ============================================================================

/*
Production database deployment should additionally implement:

1. Separate application and migration database roles.
2. Least-privilege GRANT and REVOKE statements.
3. Row-level security where tenant separation is required.
4. TLS for client connections.
5. Encrypted database storage and backups.
6. Managed KMS key lifecycle and recovery controls.
7. External immutable audit-log replication.
8. Database connection restrictions.
9. Regular credential rotation.
10. Monitoring for suspicious database activity.

The audit mutation trigger is an integrity safeguard, not a
complete tamper-proof logging solution. Database owners and
superusers can bypass ordinary application-level controls.
*/


COMMIT;
