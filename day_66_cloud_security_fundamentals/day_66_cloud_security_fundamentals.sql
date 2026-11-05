/*
 * CLOUD SECURITY FUNDAMENTALS
 *
 * PostgreSQL cloud security governance and assessment database.
 *
 * Models:
 * - Cloud providers
 * - Service models
 * - Shared responsibility
 * - Cloud resources and attack surfaces
 * - IAM permissions
 * - Security controls
 * - Threat detection
 * - Security findings
 * - Remediation workflows
 * - Risk aggregation and compliance reporting
 *
 * Compatible with PostgreSQL 14+.
 */

BEGIN;

CREATE SCHEMA IF NOT EXISTS cloud_security;

SET search_path TO cloud_security, public;

-- ============================================================
-- 1. ENUMERATED DOMAIN TYPES
-- ============================================================

CREATE TYPE cloud_provider AS ENUM (
    'AWS',
    'AZURE',
    'GCP'
);

CREATE TYPE service_model AS ENUM (
    'IAAS',
    'PAAS',
    'SAAS'
);

CREATE TYPE asset_type AS ENUM (
    'COMPUTE',
    'STORAGE',
    'DATABASE',
    'NETWORK',
    'IDENTITY',
    'SERVERLESS'
);

CREATE TYPE responsibility_owner AS ENUM (
    'PROVIDER',
    'CUSTOMER',
    'SHARED'
);

CREATE TYPE severity_level AS ENUM (
    'LOW',
    'MEDIUM',
    'HIGH',
    'CRITICAL'
);

CREATE TYPE finding_status AS ENUM (
    'OPEN',
    'IN_PROGRESS',
    'REMEDIATED',
    'ACCEPTED'
);

CREATE TYPE threat_category AS ENUM (
    'DATA_BREACH',
    'ACCOUNT_COMPROMISE',
    'MISCONFIGURATION',
    'DENIAL_OF_SERVICE',
    'MALWARE',
    'INSIDER_THREAT',
    'SUPPLY_CHAIN'
);

-- ============================================================
-- 2. CLOUD PROVIDERS AND SERVICE MODELS
-- ============================================================

CREATE TABLE providers (
    provider_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_name cloud_provider NOT NULL UNIQUE,
    description TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE service_models (
    service_model_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model service_model NOT NULL UNIQUE,
    description TEXT NOT NULL
);

INSERT INTO providers (provider_name, description)
VALUES
(
    'AWS',
    'Amazon Web Services cloud infrastructure and managed services.'
),
(
    'AZURE',
    'Microsoft Azure cloud infrastructure and managed services.'
),
(
    'GCP',
    'Google Cloud Platform infrastructure and managed services.'
);

INSERT INTO service_models (model, description)
VALUES
(
    'IAAS',
    'Infrastructure as a Service.'
),
(
    'PAAS',
    'Platform as a Service.'
),
(
    'SAAS',
    'Software as a Service.'
);

-- ============================================================
-- 3. SHARED RESPONSIBILITY
-- ============================================================

CREATE TABLE security_controls (
    control_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    control_code VARCHAR(60) NOT NULL UNIQUE,
    control_name VARCHAR(150) NOT NULL,
    description TEXT NOT NULL,
    default_owner responsibility_owner NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE service_responsibilities (
    responsibility_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_model_id BIGINT NOT NULL
        REFERENCES service_models(service_model_id),
    control_id BIGINT NOT NULL
        REFERENCES security_controls(control_id),
    owner responsibility_owner NOT NULL,

    UNIQUE (service_model_id, control_id)
);

INSERT INTO security_controls (
    control_code,
    control_name,
    description,
    default_owner
)
VALUES
(
    'PHYSICAL_DATACENTER',
    'Physical Datacenter Security',
    'Protection of physical facilities and hardware.',
    'PROVIDER'
),
(
    'HYPERVISOR',
    'Hypervisor Security',
    'Security of the virtualization layer.',
    'PROVIDER'
),
(
    'GUEST_OS',
    'Guest Operating System',
    'Operating system configuration and patching.',
    'CUSTOMER'
),
(
    'APPLICATION',
    'Application Security',
    'Application vulnerabilities and secure development.',
    'CUSTOMER'
),
(
    'DATA',
    'Data Protection',
    'Classification, access, retention and protection of data.',
    'CUSTOMER'
),
(
    'IDENTITY',
    'Identity and Access Management',
    'Identity lifecycle and permission governance.',
    'CUSTOMER'
),
(
    'NETWORK_CONFIGURATION',
    'Network Configuration',
    'Security groups, routing and segmentation.',
    'CUSTOMER'
),
(
    'MANAGED_RUNTIME',
    'Managed Runtime Security',
    'Security of provider-managed execution environments.',
    'SHARED'
),
(
    'MONITORING',
    'Security Monitoring',
    'Detection, monitoring and coordinated incident response.',
    'SHARED'
);

-- Infrastructure as a Service.
INSERT INTO service_responsibilities (
    service_model_id,
    control_id,
    owner
)
SELECT
    sm.service_model_id,
    sc.control_id,
    CASE sc.control_code
        WHEN 'PHYSICAL_DATACENTER' THEN 'PROVIDER'
        WHEN 'HYPERVISOR' THEN 'PROVIDER'
        ELSE 'CUSTOMER'
    END::responsibility_owner
FROM service_models sm
CROSS JOIN security_controls sc
WHERE sm.model = 'IAAS';

-- Platform as a Service.
INSERT INTO service_responsibilities (
    service_model_id,
    control_id,
    owner
)
SELECT
    sm.service_model_id,
    sc.control_id,
    CASE
        WHEN sc.control_code IN (
            'PHYSICAL_DATACENTER',
            'HYPERVISOR',
            'GUEST_OS',
            'MANAGED_RUNTIME'
        ) THEN 'PROVIDER'::responsibility_owner
        WHEN sc.control_code = 'MONITORING'
            THEN 'SHARED'::responsibility_owner
        ELSE 'CUSTOMER'::responsibility_owner
    END
FROM service_models sm
CROSS JOIN security_controls sc
WHERE sm.model = 'PAAS';

-- Software as a Service.
INSERT INTO service_responsibilities (
    service_model_id,
    control_id,
    owner
)
SELECT
    sm.service_model_id,
    sc.control_id,
    CASE
        WHEN sc.control_code IN (
            'PHYSICAL_DATACENTER',
            'HYPERVISOR',
            'GUEST_OS',
            'MANAGED_RUNTIME',
            'APPLICATION'
        ) THEN 'PROVIDER'::responsibility_owner
        WHEN sc.control_code IN (
            'MONITORING'
        ) THEN 'SHARED'::responsibility_owner
        ELSE 'CUSTOMER'::responsibility_owner
    END
FROM service_models sm
CROSS JOIN security_controls sc
WHERE sm.model = 'SAAS';

-- ============================================================
-- 4. CLOUD ACCOUNTS AND ASSET INVENTORY
-- ============================================================

CREATE TABLE cloud_accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_id BIGINT NOT NULL REFERENCES providers(provider_id),
    account_name VARCHAR(150) NOT NULL,
    external_account_reference VARCHAR(120) NOT NULL UNIQUE,
    environment VARCHAR(30) NOT NULL
        CHECK (
            environment IN (
                'DEVELOPMENT',
                'TESTING',
                'STAGING',
                'PRODUCTION'
            )
        ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cloud_assets (
    asset_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES cloud_accounts(account_id),
    asset_reference VARCHAR(150) NOT NULL UNIQUE,
    asset_name VARCHAR(150) NOT NULL,
    type asset_type NOT NULL,
    region VARCHAR(100) NOT NULL,

    internet_exposed BOOLEAN NOT NULL DEFAULT FALSE,
    encrypted_at_rest BOOLEAN NOT NULL DEFAULT TRUE,
    tls_required BOOLEAN NOT NULL DEFAULT TRUE,
    logging_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    mfa_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    least_privilege BOOLEAN NOT NULL DEFAULT TRUE,
    network_restricted BOOLEAN NOT NULL DEFAULT TRUE,
    backup_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    sensitive_data BOOLEAN NOT NULL DEFAULT FALSE,

    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_assessed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (
        NOT sensitive_data OR encrypted_at_rest
        OR type IN ('STORAGE', 'DATABASE')
    )
);

CREATE INDEX idx_assets_account
ON cloud_assets(account_id);

CREATE INDEX idx_assets_type_active
ON cloud_assets(type, active);

CREATE INDEX idx_assets_exposure
ON cloud_assets(internet_exposed, active)
WHERE internet_exposed = TRUE;

CREATE INDEX idx_assets_sensitive
ON cloud_assets(sensitive_data, encrypted_at_rest)
WHERE sensitive_data = TRUE;

-- ============================================================
-- 5. IAM USERS, ROLES AND PERMISSIONS
-- ============================================================

CREATE TABLE cloud_identities (
    identity_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES cloud_accounts(account_id),
    identity_name VARCHAR(150) NOT NULL,
    identity_type VARCHAR(30) NOT NULL
        CHECK (
            identity_type IN (
                'HUMAN',
                'SERVICE_ACCOUNT',
                'ROLE',
                'APPLICATION'
            )
        ),
    mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (account_id, identity_name)
);

CREATE TABLE iam_permissions (
    permission_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    identity_id BIGINT NOT NULL
        REFERENCES cloud_identities(identity_id),
    resource_id BIGINT REFERENCES cloud_assets(asset_id),
    action_name VARCHAR(150) NOT NULL,
    permission_effect VARCHAR(10) NOT NULL
        CHECK (
            permission_effect IN ('ALLOW', 'DENY')
        ),
    wildcard_permission BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_iam_identity
ON iam_permissions(identity_id);

CREATE INDEX idx_iam_wildcards
ON iam_permissions(wildcard_permission)
WHERE wildcard_permission = TRUE;

-- ============================================================
-- 6. SECURITY THREATS AND DETECTION RULES
-- ============================================================

CREATE TABLE threats (
    threat_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    threat_code VARCHAR(60) NOT NULL UNIQUE,
    threat_name VARCHAR(150) NOT NULL,
    category threat_category NOT NULL,
    description TEXT NOT NULL,
    severity severity_level NOT NULL
);

INSERT INTO threats (
    threat_code,
    threat_name,
    category,
    description,
    severity
)
VALUES
(
    'THREAT-001',
    'Public Storage Exposure',
    'DATA_BREACH',
    'Unauthorized access through publicly accessible storage.',
    'CRITICAL'
),
(
    'THREAT-002',
    'Account Compromise',
    'ACCOUNT_COMPROMISE',
    'Unauthorized access using compromised identities.',
    'CRITICAL'
),
(
    'THREAT-003',
    'Cloud Misconfiguration',
    'MISCONFIGURATION',
    'Security controls are configured incorrectly.',
    'HIGH'
),
(
    'THREAT-004',
    'Denial of Service',
    'DENIAL_OF_SERVICE',
    'Service availability is affected by resource exhaustion.',
    'HIGH'
),
(
    'THREAT-005',
    'Malware Execution',
    'MALWARE',
    'Malicious software executes in a cloud workload.',
    'HIGH'
),
(
    'THREAT-006',
    'Insider Threat',
    'INSIDER_THREAT',
    'Authorized users misuse their access privileges.',
    'HIGH'
),
(
    'THREAT-007',
    'Supply Chain Compromise',
    'SUPPLY_CHAIN',
    'Compromise of a software dependency or external service.',
    'HIGH'
);

CREATE TABLE security_rules (
    rule_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rule_code VARCHAR(80) NOT NULL UNIQUE,
    rule_name VARCHAR(150) NOT NULL,
    threat_id BIGINT REFERENCES threats(threat_id),
    severity severity_level NOT NULL,
    base_risk_score INTEGER NOT NULL
        CHECK (base_risk_score BETWEEN 0 AND 100),
    remediation TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO security_rules (
    rule_code,
    rule_name,
    threat_id,
    severity,
    base_risk_score,
    remediation
)
SELECT
    'PUBLIC_STORAGE',
    'Public Storage Access',
    threat_id,
    'CRITICAL',
    40,
    'Disable public access and enforce identity-based storage policies.'
FROM threats
WHERE threat_code = 'THREAT-001';

INSERT INTO security_rules (
    rule_code,
    rule_name,
    threat_id,
    severity,
    base_risk_score,
    remediation
)
SELECT
    'EXCESSIVE_IAM',
    'Excessive IAM Permissions',
    threat_id,
    'HIGH',
    25,
    'Remove wildcard permissions and apply least privilege.'
FROM threats
WHERE threat_code = 'THREAT-002';

INSERT INTO security_rules (
    rule_code,
    rule_name,
    threat_id,
    severity,
    base_risk_score,
    remediation
)
SELECT
    'UNENCRYPTED_DATA',
    'Sensitive Data Without Encryption',
    threat_id,
    'CRITICAL',
    35,
    'Enable encryption at rest and configure key management.'
FROM threats
WHERE threat_code = 'THREAT-001';

INSERT INTO security_rules (
    rule_code,
    rule_name,
    threat_id,
    severity,
    base_risk_score,
    remediation
)
SELECT
    'MFA_DISABLED',
    'MFA Not Enabled',
    threat_id,
    'HIGH',
    25,
    'Enforce multi-factor authentication.'
FROM threats
WHERE threat_code = 'THREAT-002';

INSERT INTO security_rules (
    rule_code,
    rule_name,
    threat_id,
    severity,
    base_risk_score,
    remediation
)
SELECT
    'LOGGING_DISABLED',
    'Audit Logging Disabled',
    threat_id,
    'HIGH',
    20,
    'Enable centralized and protected security logging.'
FROM threats
WHERE threat_code = 'THREAT-003';

INSERT INTO security_rules (
    rule_code,
    rule_name,
    threat_id,
    severity,
    base_risk_score,
    remediation
)
SELECT
    'NETWORK_UNRESTRICTED',
    'Unrestricted Network Access',
    threat_id,
    'HIGH',
    20,
    'Restrict network access using segmentation and firewall policies.'
FROM threats
WHERE threat_code = 'THREAT-003';

INSERT INTO security_rules (
    rule_code,
    rule_name,
    threat_id,
    severity,
    base_risk_score,
    remediation
)
SELECT
    'TLS_NOT_REQUIRED',
    'Secure Transport Not Enforced',
    threat_id,
    'HIGH',
    25,
    'Require TLS for data transmission.'
FROM threats
WHERE threat_code = 'THREAT-003';

INSERT INTO security_rules (
    rule_code,
    rule_name,
    threat_id,
    severity,
    base_risk_score,
    remediation
)
SELECT
    'BACKUP_DISABLED',
    'Backup Protection Disabled',
    threat_id,
    'MEDIUM',
    15,
    'Configure encrypted backups and validate recovery.'
FROM threats
WHERE threat_code = 'THREAT-003';

-- ============================================================
-- 7. SECURITY FINDINGS
-- ============================================================

CREATE TABLE security_findings (
    finding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_id BIGINT NOT NULL REFERENCES cloud_assets(asset_id),
    rule_id BIGINT NOT NULL REFERENCES security_rules(rule_id),
    severity severity_level NOT NULL,
    risk_score INTEGER NOT NULL
        CHECK (risk_score BETWEEN 0 AND 100),
    description TEXT NOT NULL,
    remediation TEXT NOT NULL,
    status finding_status NOT NULL DEFAULT 'OPEN',
    detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (asset_id, rule_id)
);

CREATE INDEX idx_findings_open_risk
ON security_findings(risk_score DESC)
WHERE status IN ('OPEN', 'IN_PROGRESS');

CREATE INDEX idx_findings_severity
ON security_findings(severity, detected_at DESC);

CREATE INDEX idx_findings_asset
ON security_findings(asset_id);

-- ============================================================
-- 8. FINDING STATUS VALIDATION
-- ============================================================

CREATE OR REPLACE FUNCTION validate_finding_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status = 'REMEDIATED'
       AND NEW.status <> 'REMEDIATED' THEN
        RAISE EXCEPTION
            'A remediated finding cannot be reopened directly.';
    END IF;

    IF OLD.status = 'ACCEPTED'
       AND NEW.status <> 'ACCEPTED' THEN
        RAISE EXCEPTION
            'An accepted finding requires a new review workflow.';
    END IF;

    NEW.updated_at := CURRENT_TIMESTAMP;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_finding_transition
BEFORE UPDATE OF status ON security_findings
FOR EACH ROW
EXECUTE FUNCTION validate_finding_transition();

-- ============================================================
-- 9. SECURITY ASSESSMENT FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION assess_cloud_asset(
    p_asset_id BIGINT
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_asset cloud_assets%ROWTYPE;
    v_count INTEGER := 0;
BEGIN
    SELECT *
    INTO v_asset
    FROM cloud_assets
    WHERE asset_id = p_asset_id
      AND active = TRUE
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Active cloud asset % does not exist.',
            p_asset_id;
    END IF;

    -- Public storage.
    IF v_asset.type = 'STORAGE'
       AND v_asset.internet_exposed THEN

        INSERT INTO security_findings (
            asset_id,
            rule_id,
            severity,
            risk_score,
            description,
            remediation
        )
        SELECT
            p_asset_id,
            rule_id,
            severity,
            base_risk_score,
            'Storage is publicly accessible.',
            remediation
        FROM security_rules
        WHERE rule_code = 'PUBLIC_STORAGE'
          AND enabled = TRUE

        ON CONFLICT (asset_id, rule_id)
        DO UPDATE SET
            severity = EXCLUDED.severity,
            risk_score = EXCLUDED.risk_score,
            description = EXCLUDED.description,
            remediation = EXCLUDED.remediation,
            status = CASE
                WHEN security_findings.status = 'REMEDIATED'
                    THEN 'OPEN'::finding_status
                WHEN security_findings.status = 'ACCEPTED'
                    THEN 'ACCEPTED'::finding_status
                ELSE 'OPEN'::finding_status
            END;

        v_count := v_count + 1;
    END IF;

    -- Unencrypted sensitive data.
    IF v_asset.sensitive_data
       AND NOT v_asset.encrypted_at_rest THEN

        INSERT INTO security_findings (
            asset_id,
            rule_id,
            severity,
            risk_score,
            description,
            remediation
        )
        SELECT
            p_asset_id,
            rule_id,
            severity,
            base_risk_score,
            'Sensitive data lacks encryption at rest.',
            remediation
        FROM security_rules
        WHERE rule_code = 'UNENCRYPTED_DATA'
          AND enabled = TRUE

        ON CONFLICT (asset_id, rule_id)
        DO UPDATE SET
            severity = EXCLUDED.severity,
            risk_score = EXCLUDED.risk_score,
            description = EXCLUDED.description,
            remediation = EXCLUDED.remediation,
            status = 'OPEN';

        v_count := v_count + 1;
    END IF;

    -- Excessive IAM permissions.
    IF EXISTS (
        SELECT 1
        FROM iam_permissions ip
        JOIN cloud_identities ci
            ON ci.identity_id = ip.identity_id
        WHERE ci.account_id = v_asset.account_id
          AND ci.active = TRUE
          AND ip.resource_id = p_asset_id
          AND (
              ip.wildcard_permission = TRUE
              OR ip.action_name = '*'
          )
          AND ip.permission_effect = 'ALLOW'
    ) THEN

        INSERT INTO security_findings (
            asset_id,
            rule_id,
            severity,
            risk_score,
            description,
            remediation
        )
        SELECT
            p_asset_id,
            rule_id,
            severity,
            base_risk_score,
            'Wildcard IAM permission detected.',
            remediation
        FROM security_rules
        WHERE rule_code = 'EXCESSIVE_IAM'
          AND enabled = TRUE

        ON CONFLICT (asset_id, rule_id)
        DO UPDATE SET
            status = 'OPEN',
            risk_score = EXCLUDED.risk_score;

        v_count := v_count + 1;
    END IF;

    -- Missing MFA.
    IF EXISTS (
        SELECT 1
        FROM cloud_identities ci
        WHERE ci.account_id = v_asset.account_id
          AND ci.active = TRUE
          AND ci.mfa_enabled = FALSE
    ) THEN

        INSERT INTO security_findings (
            asset_id,
            rule_id,
            severity,
            risk_score,
            description,
            remediation
        )
        SELECT
            p_asset_id,
            rule_id,
            severity,
            base_risk_score,
            'An active cloud identity lacks MFA.',
            remediation
        FROM security_rules
        WHERE rule_code = 'MFA_DISABLED'
          AND enabled = TRUE

        ON CONFLICT (asset_id, rule_id)
        DO UPDATE SET
            status = 'OPEN',
            risk_score = EXCLUDED.risk_score;

        v_count := v_count + 1;
    END IF;

    -- Missing audit logging.
    IF NOT v_asset.logging_enabled THEN
        INSERT INTO security_findings (
            asset_id,
            rule_id,
            severity,
            risk_score,
            description,
            remediation
        )
        SELECT
            p_asset_id,
            rule_id,
            severity,
            base_risk_score,
            'Audit logging is disabled.',
            remediation
        FROM security_rules
        WHERE rule_code = 'LOGGING_DISABLED'
          AND enabled = TRUE

        ON CONFLICT (asset_id, rule_id)
        DO UPDATE SET
            status = 'OPEN',
            risk_score = EXCLUDED.risk_score;

        v_count := v_count + 1;
    END IF;

    -- Unrestricted network access.
    IF NOT v_asset.network_restricted THEN
        INSERT INTO security_findings (
            asset_id,
            rule_id,
            severity,
            risk_score,
            description,
            remediation
        )
        SELECT
            p_asset_id,
            rule_id,
            severity,
            base_risk_score,
            'Network access is insufficiently restricted.',
            remediation
        FROM security_rules
        WHERE rule_code = 'NETWORK_UNRESTRICTED'
          AND enabled = TRUE

        ON CONFLICT (asset_id, rule_id)
        DO UPDATE SET
            status = 'OPEN',
            risk_score = EXCLUDED.risk_score;

        v_count := v_count + 1;
    END IF;

    -- Missing transport encryption enforcement.
    IF NOT v_asset.tls_required THEN
        INSERT INTO security_findings (
            asset_id,
            rule_id,
            severity,
            risk_score,
            description,
            remediation
        )
        SELECT
            p_asset_id,
            rule_id,
            severity,
            base_risk_score,
            'TLS is not enforced.',
            remediation
        FROM security_rules
        WHERE rule_code = 'TLS_NOT_REQUIRED'
          AND enabled = TRUE

        ON CONFLICT (asset_id, rule_id)
        DO UPDATE SET
            status = 'OPEN',
            risk_score = EXCLUDED.risk_score;

        v_count := v_count + 1;
    END IF;

    -- Missing backups.
    IF NOT v_asset.backup_enabled THEN
        INSERT INTO security_findings (
            asset_id,
            rule_id,
            severity,
            risk_score,
            description,
            remediation
        )
        SELECT
            p_asset_id,
            rule_id,
            severity,
            base_risk_score,
            'Backup protection is disabled.',
            remediation
        FROM security_rules
        WHERE rule_code = 'BACKUP_DISABLED'
          AND enabled = TRUE

        ON CONFLICT (asset_id, rule_id)
        DO UPDATE SET
            status = 'OPEN',
            risk_score = EXCLUDED.risk_score;

        v_count := v_count + 1;
    END IF;

    UPDATE cloud_assets
    SET last_assessed_at = CURRENT_TIMESTAMP
    WHERE asset_id = p_asset_id;

    RETURN v_count;
END;
$$;

-- ============================================================
-- 10. ASSESSMENT PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE assess_all_cloud_assets()
LANGUAGE plpgsql
AS $$
DECLARE
    v_asset RECORD;
BEGIN
    FOR v_asset IN
        SELECT asset_id
        FROM cloud_assets
        WHERE active = TRUE
        ORDER BY asset_id
    LOOP
        PERFORM assess_cloud_asset(v_asset.asset_id);
    END LOOP;
END;
$$;

-- ============================================================
-- 11. ATTACK SURFACE VIEW
-- ============================================================

CREATE OR REPLACE VIEW attack_surface_report AS
SELECT
    a.asset_id,
    a.asset_reference,
    a.asset_name,
    a.type,
    p.provider_name,
    a.region,
    a.internet_exposed,
    a.sensitive_data,
    a.encrypted_at_rest,
    a.network_restricted,
    CASE
        WHEN a.internet_exposed AND a.sensitive_data
            THEN 'CRITICAL_EXPOSURE'
        WHEN a.internet_exposed
            THEN 'INTERNET_EXPOSED'
        WHEN a.sensitive_data AND NOT a.encrypted_at_rest
            THEN 'UNENCRYPTED_SENSITIVE_DATA'
        ELSE 'RESTRICTED'
    END AS exposure_classification
FROM cloud_assets a
JOIN cloud_accounts ca
    ON ca.account_id = a.account_id
JOIN providers p
    ON p.provider_id = ca.provider_id
WHERE a.active = TRUE;

-- ============================================================
-- 12. SECURITY FINDINGS VIEW
-- ============================================================

CREATE OR REPLACE VIEW open_security_findings AS
SELECT
    f.finding_id,
    a.asset_reference,
    a.asset_name,
    p.provider_name,
    r.rule_code,
    f.severity,
    f.risk_score,
    f.status,
    f.description,
    f.remediation,
    f.detected_at
FROM security_findings f
JOIN cloud_assets a
    ON a.asset_id = f.asset_id
JOIN cloud_accounts ca
    ON ca.account_id = a.account_id
JOIN providers p
    ON p.provider_id = ca.provider_id
JOIN security_rules r
    ON r.rule_id = f.rule_id
WHERE f.status IN ('OPEN', 'IN_PROGRESS');

-- ============================================================
-- 13. SAMPLE CLOUD ACCOUNTS
-- ============================================================

INSERT INTO cloud_accounts (
    provider_id,
    account_name,
    external_account_reference,
    environment
)
SELECT
    provider_id,
    'Production AWS Account',
    'aws-prod-001',
    'PRODUCTION'
FROM providers
WHERE provider_name = 'AWS';

INSERT INTO cloud_accounts (
    provider_id,
    account_name,
    external_account_reference,
    environment
)
SELECT
    provider_id,
    'Azure Application Account',
    'azure-app-001',
    'PRODUCTION'
FROM providers
WHERE provider_name = 'AZURE';

INSERT INTO cloud_accounts (
    provider_id,
    account_name,
    external_account_reference,
    environment
)
SELECT
    provider_id,
    'GCP Database Account',
    'gcp-db-001',
    'PRODUCTION'
FROM providers
WHERE provider_name = 'GCP';

-- ============================================================
-- 14. SAMPLE CLOUD ASSETS
-- ============================================================

INSERT INTO cloud_assets (
    account_id,
    asset_reference,
    asset_name,
    type,
    region,
    internet_exposed,
    encrypted_at_rest,
    tls_required,
    logging_enabled,
    mfa_enabled,
    least_privilege,
    network_restricted,
    backup_enabled,
    sensitive_data
)
SELECT
    account_id,
    'AWS-STORAGE-001',
    'Customer Documents',
    'STORAGE',
    'ap-south-1',
    TRUE,
    FALSE,
    TRUE,
    FALSE,
    TRUE,
    FALSE,
    FALSE,
    FALSE,
    TRUE
FROM cloud_accounts
WHERE external_account_reference = 'aws-prod-001';

INSERT INTO cloud_assets (
    account_id,
    asset_reference,
    asset_name,
    type,
    region,
    internet_exposed,
    encrypted_at_rest,
    tls_required,
    logging_enabled,
    mfa_enabled,
    least_privilege,
    network_restricted,
    backup_enabled,
    sensitive_data
)
SELECT
    account_id,
    'AZURE-VM-001',
    'Application Server',
    'COMPUTE',
    'centralindia',
    FALSE,
    TRUE,
    FALSE,
    TRUE,
    FALSE,
    TRUE,
    FALSE,
    TRUE,
    FALSE
FROM cloud_accounts
WHERE external_account_reference = 'azure-app-001';

INSERT INTO cloud_assets (
    account_id,
    asset_reference,
    asset_name,
    type,
    region,
    internet_exposed,
    encrypted_at_rest,
    tls_required,
    logging_enabled,
    mfa_enabled,
    least_privilege,
    network_restricted,
    backup_enabled,
    sensitive_data
)
SELECT
    account_id,
    'GCP-DB-001',
    'Production Database',
    'DATABASE',
    'asia-south1',
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    FALSE,
    TRUE
FROM cloud_accounts
WHERE external_account_reference = 'gcp-db-001';

-- ============================================================
-- 15. SAMPLE IDENTITIES AND IAM PERMISSIONS
-- ============================================================

INSERT INTO cloud_identities (
    account_id,
    identity_name,
    identity_type,
    mfa_enabled
)
SELECT
    account_id,
    'application-admin',
    'HUMAN',
    FALSE
FROM cloud_accounts
WHERE external_account_reference = 'aws-prod-001';

INSERT INTO cloud_identities (
    account_id,
    identity_name,
    identity_type,
    mfa_enabled
)
SELECT
    account_id,
    'application-service-role',
    'SERVICE_ACCOUNT',
    TRUE
FROM cloud_accounts
WHERE external_account_reference = 'gcp-db-001';

INSERT INTO iam_permissions (
    identity_id,
    resource_id,
    action_name,
    permission_effect,
    wildcard_permission
)
SELECT
    ci.identity_id,
    a.asset_id,
    '*',
    'ALLOW',
    TRUE
FROM cloud_identities ci
JOIN cloud_accounts ca
    ON ca.account_id = ci.account_id
JOIN cloud_assets a
    ON a.account_id = ca.account_id
WHERE ci.identity_name = 'application-admin'
  AND a.asset_reference = 'AWS-STORAGE-001';

INSERT INTO iam_permissions (
    identity_id,
    resource_id,
    action_name,
    permission_effect,
    wildcard_permission
)
SELECT
    ci.identity_id,
    a.asset_id,
    'database:read',
    'ALLOW',
    FALSE
FROM cloud_identities ci
JOIN cloud_accounts ca
    ON ca.account_id = ci.account_id
JOIN cloud_assets a
    ON a.account_id = ca.account_id
WHERE ci.identity_name = 'application-service-role'
  AND a.asset_reference = 'GCP-DB-001';

-- ============================================================
-- 16. RUN SECURITY ASSESSMENT
-- ============================================================

CALL assess_all_cloud_assets();

-- ============================================================
-- 17. RESPONSIBILITY RETRIEVAL
-- ============================================================

SELECT
    sm.model,
    sc.control_code,
    sc.control_name,
    sr.owner
FROM service_responsibilities sr
JOIN service_models sm
    ON sm.service_model_id = sr.service_model_id
JOIN security_controls sc
    ON sc.control_id = sr.control_id
ORDER BY sm.model, sc.control_code;

-- ============================================================
-- 18. ATTACK SURFACE RETRIEVAL
-- ============================================================

SELECT *
FROM attack_surface_report
ORDER BY internet_exposed DESC, asset_reference;

-- ============================================================
-- 19. SECURITY FINDING RETRIEVAL
-- ============================================================

SELECT *
FROM open_security_findings
ORDER BY
    CASE severity
        WHEN 'CRITICAL' THEN 4
        WHEN 'HIGH' THEN 3
        WHEN 'MEDIUM' THEN 2
        WHEN 'LOW' THEN 1
    END DESC,
    risk_score DESC;

-- ============================================================
-- 20. SEVERITY AGGREGATION
-- ============================================================

SELECT
    severity,
    COUNT(*) AS finding_count,
    SUM(risk_score) AS cumulative_risk,
    ROUND(AVG(risk_score), 2) AS average_risk
FROM security_findings
GROUP BY severity
ORDER BY cumulative_risk DESC;

-- ============================================================
-- 21. PROVIDER-LEVEL SECURITY REPORT
-- ============================================================

SELECT
    p.provider_name,
    COUNT(DISTINCT a.asset_id) AS total_assets,
    COUNT(DISTINCT f.finding_id) AS total_findings,
    COUNT(DISTINCT f.finding_id)
        FILTER (WHERE f.severity = 'CRITICAL') AS critical_findings,
    COALESCE(SUM(f.risk_score), 0) AS total_risk
FROM providers p
LEFT JOIN cloud_accounts ca
    ON ca.provider_id = p.provider_id
LEFT JOIN cloud_assets a
    ON a.account_id = ca.account_id
LEFT JOIN security_findings f
    ON f.asset_id = a.asset_id
   AND f.status IN ('OPEN', 'IN_PROGRESS')
GROUP BY p.provider_name
ORDER BY total_risk DESC;

-- ============================================================
-- 22. LEAST-PRIVILEGE VALIDATION
-- ============================================================

SELECT
    ci.identity_name,
    ca.external_account_reference,
    ip.action_name,
    ip.permission_effect,
    ip.wildcard_permission,
    a.asset_reference
FROM iam_permissions ip
JOIN cloud_identities ci
    ON ci.identity_id = ip.identity_id
JOIN cloud_accounts ca
    ON ca.account_id = ci.account_id
LEFT JOIN cloud_assets a
    ON a.asset_id = ip.resource_id
WHERE ip.wildcard_permission = TRUE
   OR ip.action_name = '*';

-- ============================================================
-- 23. RISK-BASED REMEDIATION QUEUE
-- ============================================================

WITH ranked_findings AS (
    SELECT
        f.finding_id,
        a.asset_reference,
        r.rule_code,
        f.severity,
        f.risk_score,
        f.status,
        ROW_NUMBER() OVER (
            PARTITION BY f.asset_id
            ORDER BY f.risk_score DESC, f.detected_at
        ) AS asset_priority
    FROM security_findings f
    JOIN cloud_assets a
        ON a.asset_id = f.asset_id
    JOIN security_rules r
        ON r.rule_id = f.rule_id
    WHERE f.status IN ('OPEN', 'IN_PROGRESS')
)
SELECT
    finding_id,
    asset_reference,
    rule_code,
    severity,
    risk_score,
    asset_priority
FROM ranked_findings
ORDER BY risk_score DESC, asset_reference;

-- ============================================================
-- 24. ASSET SECURITY ELIGIBILITY
-- ============================================================

CREATE OR REPLACE VIEW cloud_asset_eligibility AS
SELECT
    a.asset_id,
    a.asset_reference,
    a.asset_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM security_findings f
            WHERE f.asset_id = a.asset_id
              AND f.severity = 'CRITICAL'
              AND f.status IN ('OPEN', 'IN_PROGRESS')
        ) THEN 'BLOCKED_CRITICAL_FINDING'

        WHEN EXISTS (
            SELECT 1
            FROM security_findings f
            WHERE f.asset_id = a.asset_id
              AND f.status IN ('OPEN', 'IN_PROGRESS')
        ) THEN 'REQUIRES_REMEDIATION'

        ELSE 'ELIGIBLE'
    END AS eligibility
FROM cloud_assets a
WHERE a.active = TRUE;

SELECT *
FROM cloud_asset_eligibility
ORDER BY eligibility, asset_reference;

-- ============================================================
-- 25. TRANSACTIONAL REMEDIATION
-- ============================================================

-- Demonstrate safe remediation status management.
-- This example resolves the public storage finding after
-- an administrator has verified the corrective configuration.

DO $$
DECLARE
    v_finding_id BIGINT;
BEGIN
    SELECT f.finding_id
    INTO v_finding_id
    FROM security_findings f
    JOIN cloud_assets a
        ON a.asset_id = f.asset_id
    JOIN security_rules r
        ON r.rule_id = f.rule_id
    WHERE a.asset_reference = 'AWS-STORAGE-001'
      AND r.rule_code = 'PUBLIC_STORAGE'
    LIMIT 1;

    IF v_finding_id IS NOT NULL THEN
        UPDATE security_findings
        SET status = 'IN_PROGRESS'
        WHERE finding_id = v_finding_id
          AND status = 'OPEN';
    END IF;
END;
$$;

COMMIT;

-- ============================================================
-- 26. POST-TRANSACTION VALIDATION QUERIES
-- ============================================================

SELECT
    asset_reference,
    asset_name,
    eligibility
FROM cloud_asset_eligibility
ORDER BY asset_reference;

SELECT
    status,
    COUNT(*) AS finding_count
FROM security_findings
GROUP BY status
ORDER BY status;

SELECT
    COUNT(*) AS active_assets
FROM cloud_assets
WHERE active = TRUE;

SELECT
    COUNT(*) AS open_critical_findings
FROM security_findings
WHERE severity = 'CRITICAL'
  AND status IN ('OPEN', 'IN_PROGRESS');
