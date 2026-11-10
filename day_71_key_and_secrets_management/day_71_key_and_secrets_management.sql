/*
===============================================================================
KEY AND SECRETS MANAGEMENT
PostgreSQL 15+

Domain:
  Encryption keys
  Key versioning and rotation
  Secrets storage metadata
  Certificate inventory
  Access-control assignments
  Key usage records
  Audit events
  Security policies
  Eligibility evaluation

Security boundary:
  This database stores key and certificate metadata, encrypted secret
  envelopes, and wrapped data keys. It does not store plaintext master
  encryption keys or perform cryptographic encryption itself.

Production deployments should use an external KMS/HSM, tightly controlled
database roles, TLS, encrypted backups, and independent audit retention.
===============================================================================
*/

BEGIN;

CREATE SCHEMA IF NOT EXISTS key_management;

SET search_path TO key_management, public;

-- ============================================================
-- ENUMERATIONS
-- ============================================================

CREATE TYPE key_algorithm AS ENUM (
    'AES_256_GCM',
    'HMAC_SHA256',
    'ED25519'
);

CREATE TYPE key_status AS ENUM (
    'ACTIVE',
    'DECRYPT_ONLY',
    'REVOKED',
    'DESTROYED'
);

CREATE TYPE secret_status AS ENUM (
    'ACTIVE',
    'DISABLED'
);

CREATE TYPE certificate_status AS ENUM (
    'VALID',
    'EXPIRING',
    'EXPIRED',
    'REVOKED',
    'NOT_YET_VALID'
);

CREATE TYPE permission_type AS ENUM (
    'READ',
    'WRITE',
    'ROTATE',
    'REVOKE',
    'ADMIN'
);

CREATE TYPE operation_type AS ENUM (
    'ENCRYPT',
    'DECRYPT',
    'SIGN',
    'VERIFY',
    'WRAP',
    'UNWRAP'
);

CREATE TYPE audit_outcome AS ENUM (
    'SUCCESS',
    'DENIED',
    'FAILURE'
);

-- ============================================================
-- ORGANIZATIONS AND PRINCIPALS
-- ============================================================

CREATE TABLE organizations (
    organization_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_name VARCHAR(150) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE principals (
    principal_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),
    principal_name VARCHAR(150) NOT NULL,
    principal_type VARCHAR(30) NOT NULL
        CHECK (principal_type IN ('USER', 'SERVICE', 'APPLICATION')),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (organization_id, principal_name)
);

CREATE TABLE roles (
    role_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role_name VARCHAR(80) NOT NULL UNIQUE,
    description TEXT NOT NULL
);

CREATE TABLE permissions (
    permission_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    permission_name permission_type NOT NULL UNIQUE,
    description TEXT NOT NULL
);

CREATE TABLE role_permissions (
    role_id BIGINT NOT NULL REFERENCES roles(role_id),
    permission_id BIGINT NOT NULL REFERENCES permissions(permission_id),
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE principal_roles (
    principal_id BIGINT NOT NULL REFERENCES principals(principal_id),
    role_id BIGINT NOT NULL REFERENCES roles(role_id),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    granted_by BIGINT REFERENCES principals(principal_id),
    PRIMARY KEY (principal_id, role_id)
);

-- ============================================================
-- KEY INVENTORY
-- ============================================================

CREATE TABLE encryption_keys (
    key_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),

    key_alias VARCHAR(150) NOT NULL,

    algorithm key_algorithm NOT NULL,

    status key_status NOT NULL DEFAULT 'ACTIVE',

    current_version INTEGER NOT NULL DEFAULT 1
        CHECK (current_version > 0),

    provider_name VARCHAR(100) NOT NULL,

    provider_key_reference VARCHAR(500) NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    expires_at TIMESTAMPTZ NOT NULL,

    revoked_at TIMESTAMPTZ,

    UNIQUE (organization_id, key_alias),

    CHECK (expires_at > created_at),

    CHECK (
        (status <> 'REVOKED' AND revoked_at IS NULL)
        OR
        (status = 'REVOKED' AND revoked_at IS NOT NULL)
    )
);

CREATE TABLE key_versions (
    key_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    key_id UUID NOT NULL
        REFERENCES encryption_keys(key_id),

    version_number INTEGER NOT NULL
        CHECK (version_number > 0),

    algorithm key_algorithm NOT NULL,

    fingerprint CHAR(64) NOT NULL,

    provider_version_reference VARCHAR(500) NOT NULL,

    status key_status NOT NULL DEFAULT 'ACTIVE',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    expires_at TIMESTAMPTZ NOT NULL,

    rotated_at TIMESTAMPTZ,

    UNIQUE (key_id, version_number),

    UNIQUE (key_id, fingerprint),

    CHECK (expires_at > created_at)
);

CREATE INDEX idx_key_versions_key_status
    ON key_versions(key_id, status);

CREATE INDEX idx_encryption_keys_expiry
    ON encryption_keys(expires_at)
    WHERE status = 'ACTIVE';

-- A version cannot reference a key that has a different algorithm.
CREATE OR REPLACE FUNCTION validate_key_version()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    parent_algorithm key_algorithm;
BEGIN
    SELECT algorithm
    INTO parent_algorithm
    FROM encryption_keys
    WHERE key_id = NEW.key_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Parent encryption key does not exist';
    END IF;

    IF parent_algorithm <> NEW.algorithm THEN
        RAISE EXCEPTION 'Key algorithm mismatch';
    END IF;

    IF NEW.version_number > 1 AND NEW.status = 'ACTIVE' THEN
        IF EXISTS (
            SELECT 1
            FROM key_versions
            WHERE key_id = NEW.key_id
              AND status = 'ACTIVE'
        ) THEN
            RAISE EXCEPTION
                'Retire the previous active version before activating another';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_key_version
BEFORE INSERT ON key_versions
FOR EACH ROW
EXECUTE FUNCTION validate_key_version();

-- ============================================================
-- KEY ROTATION HISTORY
-- ============================================================

CREATE TABLE key_rotations (
    rotation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    key_id UUID NOT NULL
        REFERENCES encryption_keys(key_id),

    old_version INTEGER NOT NULL,

    new_version INTEGER NOT NULL,

    initiated_by BIGINT NOT NULL
        REFERENCES principals(principal_id),

    rotation_reason TEXT NOT NULL,

    rotated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (new_version > old_version),

    UNIQUE (key_id, new_version)
);

-- ============================================================
-- SECRET STORAGE
-- ============================================================

CREATE TABLE secrets (
    secret_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),

    secret_name VARCHAR(200) NOT NULL,

    description TEXT,

    status secret_status NOT NULL DEFAULT 'ACTIVE',

    created_by BIGINT NOT NULL REFERENCES principals(principal_id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (organization_id, secret_name)
);

CREATE TABLE secret_versions (
    secret_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    secret_id UUID NOT NULL
        REFERENCES secrets(secret_id),

    version_number INTEGER NOT NULL
        CHECK (version_number > 0),

    key_id UUID NOT NULL
        REFERENCES encryption_keys(key_id),

    key_version_id UUID NOT NULL
        REFERENCES key_versions(key_version_id),

    encryption_algorithm VARCHAR(50) NOT NULL
        CHECK (encryption_algorithm = 'AES-256-GCM'),

    encrypted_payload BYTEA NOT NULL,

    initialization_vector BYTEA NOT NULL
        CHECK (OCTET_LENGTH(initialization_vector) = 12),

    authentication_tag BYTEA NOT NULL
        CHECK (OCTET_LENGTH(authentication_tag) = 16),

    wrapped_data_key BYTEA NOT NULL,

    associated_data TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    created_by BIGINT NOT NULL
        REFERENCES principals(principal_id),

    UNIQUE (secret_id, version_number)
);

CREATE INDEX idx_secret_versions_lookup
    ON secret_versions(secret_id, version_number DESC);

CREATE INDEX idx_secrets_organization_status
    ON secrets(organization_id, status);

-- Verify that a secret version references a version of its selected key.
CREATE OR REPLACE FUNCTION validate_secret_key_reference()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    actual_key_id UUID;
    actual_status key_status;
BEGIN
    SELECT key_id, status
    INTO actual_key_id, actual_status
    FROM key_versions
    WHERE key_version_id = NEW.key_version_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Referenced key version not found';
    END IF;

    IF actual_key_id <> NEW.key_id THEN
        RAISE EXCEPTION 'Secret key and key version do not match';
    END IF;

    IF actual_status IN ('REVOKED', 'DESTROYED') THEN
        RAISE EXCEPTION 'Cannot use revoked or destroyed key version';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_secret_key_reference
BEFORE INSERT OR UPDATE ON secret_versions
FOR EACH ROW
EXECUTE FUNCTION validate_secret_key_reference();

-- ============================================================
-- CERTIFICATE INVENTORY
-- ============================================================

CREATE TABLE certificates (
    certificate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),

    common_name VARCHAR(255) NOT NULL,

    subject_name TEXT NOT NULL,

    issuer_name TEXT NOT NULL,

    serial_number VARCHAR(200) NOT NULL,

    fingerprint CHAR(64) NOT NULL,

    not_before TIMESTAMPTZ NOT NULL,

    not_after TIMESTAMPTZ NOT NULL,

    revoked BOOLEAN NOT NULL DEFAULT FALSE,

    revoked_at TIMESTAMPTZ,

    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (organization_id, fingerprint),

    UNIQUE (organization_id, serial_number),

    CHECK (not_after > not_before),

    CHECK (
        (revoked = FALSE AND revoked_at IS NULL)
        OR
        (revoked = TRUE AND revoked_at IS NOT NULL)
    )
);

CREATE INDEX idx_certificates_expiration
    ON certificates(not_after)
    WHERE revoked = FALSE;

CREATE INDEX idx_certificates_common_name
    ON certificates(organization_id, common_name);

CREATE OR REPLACE FUNCTION evaluate_certificate(
    p_certificate_id UUID
)
RETURNS certificate_status
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    cert certificates%ROWTYPE;
BEGIN
    SELECT *
    INTO cert
    FROM certificates
    WHERE certificate_id = p_certificate_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Certificate not found';
    END IF;

    IF cert.revoked THEN
        RETURN 'REVOKED';
    END IF;

    IF NOW() < cert.not_before THEN
        RETURN 'NOT_YET_VALID';
    END IF;

    IF NOW() >= cert.not_after THEN
        RETURN 'EXPIRED';
    END IF;

    IF NOW() >= cert.not_after - INTERVAL '30 days' THEN
        RETURN 'EXPIRING';
    END IF;

    RETURN 'VALID';
END;
$$;

-- ============================================================
-- USAGE RECORDS
-- ============================================================

CREATE TABLE key_usage (
    usage_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    key_id UUID NOT NULL
        REFERENCES encryption_keys(key_id),

    key_version_id UUID NOT NULL
        REFERENCES key_versions(key_version_id),

    principal_id BIGINT NOT NULL
        REFERENCES principals(principal_id),

    operation operation_type NOT NULL,

    outcome audit_outcome NOT NULL,

    request_reference VARCHAR(150),

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_key_usage_key_time
    ON key_usage(key_id, occurred_at DESC);

CREATE INDEX idx_key_usage_principal_time
    ON key_usage(principal_id, occurred_at DESC);

-- ============================================================
-- AUDIT EVENTS
-- ============================================================

CREATE TABLE audit_events (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    principal_id BIGINT REFERENCES principals(principal_id),

    action VARCHAR(100) NOT NULL,

    resource_type VARCHAR(80) NOT NULL,

    resource_id VARCHAR(200) NOT NULL,

    outcome audit_outcome NOT NULL,

    event_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_resource_time
    ON audit_events(resource_type, resource_id, occurred_at DESC);

CREATE INDEX idx_audit_principal_time
    ON audit_events(principal_id, occurred_at DESC);

CREATE INDEX idx_audit_failures
    ON audit_events(occurred_at DESC)
    WHERE outcome IN ('DENIED', 'FAILURE');

-- ============================================================
-- AUDIT AUTOMATION
-- ============================================================

CREATE OR REPLACE FUNCTION record_key_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO audit_events (
        action,
        resource_type,
        resource_id,
        outcome,
        event_metadata
    )
    VALUES (
        TG_OP,
        'ENCRYPTION_KEY',
        COALESCE(NEW.key_id, OLD.key_id)::TEXT,
        'SUCCESS',
        jsonb_build_object(
            'new_status',
            CASE WHEN TG_OP <> 'DELETE' THEN NEW.status::TEXT END,
            'old_status',
            CASE WHEN TG_OP <> 'INSERT' THEN OLD.status::TEXT END
        )
    );

    RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE TRIGGER trg_key_change_audit
AFTER INSERT OR UPDATE ON encryption_keys
FOR EACH ROW
EXECUTE FUNCTION record_key_change();

-- ============================================================
-- KEY ROTATION PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE rotate_key(
    p_key_id UUID,
    p_actor BIGINT,
    p_provider_reference VARCHAR(500),
    p_fingerprint CHAR(64),
    p_validity_days INTEGER,
    p_reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    current_key encryption_keys%ROWTYPE;
    active_version key_versions%ROWTYPE;
    next_version INTEGER;
    new_version_id UUID;
BEGIN
    IF p_validity_days <= 0 OR p_validity_days > 3650 THEN
        RAISE EXCEPTION 'Invalid key validity period';
    END IF;

    IF p_reason IS NULL OR LENGTH(TRIM(p_reason)) = 0 THEN
        RAISE EXCEPTION 'Rotation reason is required';
    END IF;

    SELECT *
    INTO current_key
    FROM encryption_keys
    WHERE key_id = p_key_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Key not found';
    END IF;

    IF current_key.status <> 'ACTIVE' THEN
        RAISE EXCEPTION 'Only active keys can be rotated';
    END IF;

    SELECT *
    INTO active_version
    FROM key_versions
    WHERE key_id = p_key_id
      AND version_number = current_key.current_version
    FOR UPDATE;

    IF NOT FOUND OR active_version.status <> 'ACTIVE' THEN
        RAISE EXCEPTION 'Current active key version unavailable';
    END IF;

    next_version := current_key.current_version + 1;

    UPDATE key_versions
    SET status = 'DECRYPT_ONLY',
        rotated_at = NOW()
    WHERE key_version_id = active_version.key_version_id;

    INSERT INTO key_versions (
        key_id,
        version_number,
        algorithm,
        fingerprint,
        provider_version_reference,
        status,
        expires_at
    )
    VALUES (
        p_key_id,
        next_version,
        current_key.algorithm,
        p_fingerprint,
        p_provider_reference,
        'ACTIVE',
        NOW() + MAKE_INTERVAL(days => p_validity_days)
    )
    RETURNING key_version_id INTO new_version_id;

    UPDATE encryption_keys
    SET current_version = next_version,
        expires_at = NOW() + MAKE_INTERVAL(days => p_validity_days)
    WHERE key_id = p_key_id;

    INSERT INTO key_rotations (
        key_id,
        old_version,
        new_version,
        initiated_by,
        rotation_reason
    )
    VALUES (
        p_key_id,
        current_key.current_version,
        next_version,
        p_actor,
        p_reason
    );

    INSERT INTO audit_events (
        principal_id,
        action,
        resource_type,
        resource_id,
        outcome,
        event_metadata
    )
    VALUES (
        p_actor,
        'ROTATE_KEY',
        'ENCRYPTION_KEY',
        p_key_id::TEXT,
        'SUCCESS',
        jsonb_build_object(
            'old_version', current_key.current_version,
            'new_version', next_version,
            'new_version_id', new_version_id,
            'reason', p_reason
        )
    );
END;
$$;

-- ============================================================
-- SECRET ROTATION PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE rotate_secret(
    p_secret_id UUID,
    p_key_id UUID,
    p_key_version_id UUID,
    p_encrypted_payload BYTEA,
    p_iv BYTEA,
    p_tag BYTEA,
    p_wrapped_data_key BYTEA,
    p_actor BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    next_version INTEGER;
    secret_record secrets%ROWTYPE;
BEGIN
    SELECT *
    INTO secret_record
    FROM secrets
    WHERE secret_id = p_secret_id
    FOR UPDATE;

    IF NOT FOUND OR secret_record.status <> 'ACTIVE' THEN
        RAISE EXCEPTION 'Secret is unavailable';
    END IF;

    SELECT COALESCE(MAX(version_number), 0) + 1
    INTO next_version
    FROM secret_versions
    WHERE secret_id = p_secret_id;

    INSERT INTO secret_versions (
        secret_id,
        version_number,
        key_id,
        key_version_id,
        encryption_algorithm,
        encrypted_payload,
        initialization_vector,
        authentication_tag,
        wrapped_data_key,
        associated_data,
        created_by
    )
    VALUES (
        p_secret_id,
        next_version,
        p_key_id,
        p_key_version_id,
        'AES-256-GCM',
        p_encrypted_payload,
        p_iv,
        p_tag,
        p_wrapped_data_key,
        'secret:' || p_secret_id::TEXT,
        p_actor
    );

    INSERT INTO audit_events (
        principal_id,
        action,
        resource_type,
        resource_id,
        outcome,
        event_metadata
    )
    VALUES (
        p_actor,
        'ROTATE_SECRET',
        'SECRET',
        p_secret_id::TEXT,
        'SUCCESS',
        jsonb_build_object('version', next_version)
    );
END;
$$;

-- ============================================================
-- ELIGIBILITY FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION key_is_eligible(
    p_key_id UUID,
    p_operation operation_type
)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    key_record encryption_keys%ROWTYPE;
    active_version_record key_versions%ROWTYPE;
BEGIN
    SELECT *
    INTO key_record
    FROM encryption_keys
    WHERE key_id = p_key_id;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    IF NOW() >= key_record.expires_at THEN
        RETURN FALSE;
    END IF;

    SELECT *
    INTO active_version_record
    FROM key_versions
    WHERE key_id = p_key_id
      AND version_number = key_record.current_version;

    IF NOT FOUND OR NOW() >= active_version_record.expires_at THEN
        RETURN FALSE;
    END IF;

    IF p_operation IN ('ENCRYPT', 'SIGN', 'WRAP') THEN
        RETURN key_record.status = 'ACTIVE'
           AND active_version_record.status = 'ACTIVE';
    END IF;

    IF p_operation IN ('DECRYPT', 'VERIFY', 'UNWRAP') THEN
        RETURN key_record.status IN ('ACTIVE', 'DECRYPT_ONLY')
           AND active_version_record.status IN (
               'ACTIVE',
               'DECRYPT_ONLY'
           );
    END IF;

    RETURN FALSE;
END;
$$;

-- ============================================================
-- REPORTING VIEWS
-- ============================================================

CREATE VIEW key_inventory_report AS
SELECT
    k.key_id,
    o.organization_name,
    k.key_alias,
    k.algorithm,
    k.status,
    k.current_version,
    k.provider_name,
    k.created_at,
    k.expires_at,
    CASE
        WHEN k.status = 'REVOKED' THEN 'REVOKED'
        WHEN k.status = 'DESTROYED' THEN 'DESTROYED'
        WHEN NOW() >= k.expires_at THEN 'EXPIRED'
        WHEN NOW() >= k.expires_at - INTERVAL '30 days'
            THEN 'EXPIRING'
        ELSE 'VALID'
    END AS lifecycle_condition
FROM encryption_keys k
JOIN organizations o
    ON o.organization_id = k.organization_id;

CREATE VIEW certificate_inventory_report AS
SELECT
    certificate_id,
    organization_id,
    common_name,
    issuer_name,
    serial_number,
    not_before,
    not_after,
    CASE
        WHEN revoked THEN 'REVOKED'
        WHEN NOW() < not_before THEN 'NOT_YET_VALID'
        WHEN NOW() >= not_after THEN 'EXPIRED'
        WHEN NOW() >= not_after - INTERVAL '30 days'
            THEN 'EXPIRING'
        ELSE 'VALID'
    END AS lifecycle_condition
FROM certificates;

CREATE VIEW secret_version_report AS
SELECT
    s.secret_id,
    s.secret_name,
    s.status,
    COUNT(sv.secret_version_id) AS version_count,
    MAX(sv.version_number) AS latest_version,
    MAX(sv.created_at) AS last_updated
FROM secrets s
LEFT JOIN secret_versions sv
    ON sv.secret_id = s.secret_id
GROUP BY s.secret_id, s.secret_name, s.status;

-- ============================================================
-- SAMPLE ORGANIZATION AND PRINCIPALS
-- ============================================================

INSERT INTO organizations (organization_name)
VALUES ('Example Financial Services')
RETURNING organization_id;

INSERT INTO principals (
    organization_id,
    principal_name,
    principal_type
)
SELECT organization_id, 'security-admin', 'USER'
FROM organizations
WHERE organization_name = 'Example Financial Services';

INSERT INTO principals (
    organization_id,
    principal_name,
    principal_type
)
SELECT organization_id, 'payments-service', 'APPLICATION'
FROM organizations
WHERE organization_name = 'Example Financial Services';

INSERT INTO principals (
    organization_id,
    principal_name,
    principal_type
)
SELECT organization_id, 'compliance-auditor', 'USER'
FROM organizations
WHERE organization_name = 'Example Financial Services';

INSERT INTO roles (role_name, description)
VALUES
    ('SECURITY_ADMIN', 'Full key lifecycle administration'),
    ('APPLICATION', 'Controlled application secret usage'),
    ('AUDITOR', 'Read-only security inventory access');

INSERT INTO permissions (permission_name, description)
VALUES
    ('READ', 'Read permitted security metadata'),
    ('WRITE', 'Create keys and encrypted secrets'),
    ('ROTATE', 'Rotate existing key material'),
    ('REVOKE', 'Revoke key material'),
    ('ADMIN', 'Full administrative permissions');

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM roles r
CROSS JOIN permissions p
WHERE r.role_name = 'SECURITY_ADMIN';

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM roles r
JOIN permissions p
    ON p.permission_name IN ('READ', 'WRITE')
WHERE r.role_name = 'APPLICATION';

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM roles r
JOIN permissions p
    ON p.permission_name = 'READ'
WHERE r.role_name = 'AUDITOR';

INSERT INTO principal_roles (principal_id, role_id)
SELECT p.principal_id, r.role_id
FROM principals p
JOIN roles r
    ON r.role_name = CASE p.principal_name
        WHEN 'security-admin' THEN 'SECURITY_ADMIN'
        WHEN 'payments-service' THEN 'APPLICATION'
        WHEN 'compliance-auditor' THEN 'AUDITOR'
    END
WHERE p.principal_name IN (
    'security-admin',
    'payments-service',
    'compliance-auditor'
);

-- ============================================================
-- SAMPLE KEY AND VERSION
-- ============================================================

INSERT INTO encryption_keys (
    organization_id,
    key_alias,
    algorithm,
    status,
    current_version,
    provider_name,
    provider_key_reference,
    expires_at
)
SELECT
    organization_id,
    'payments/master-key',
    'AES_256_GCM',
    'ACTIVE',
    1,
    'External-KMS',
    'kms://payments/master-key/version/1',
    NOW() + INTERVAL '365 days'
FROM organizations
WHERE organization_name = 'Example Financial Services';

INSERT INTO key_versions (
    key_id,
    version_number,
    algorithm,
    fingerprint,
    provider_version_reference,
    status,
    expires_at
)
SELECT
    key_id,
    1,
    algorithm,
    REPEAT('a', 64),
    'kms://payments/master-key/version/1',
    'ACTIVE',
    expires_at
FROM encryption_keys
WHERE key_alias = 'payments/master-key';

-- HMAC key.
INSERT INTO encryption_keys (
    organization_id,
    key_alias,
    algorithm,
    current_version,
    provider_name,
    provider_key_reference,
    expires_at
)
SELECT
    organization_id,
    'payments/integrity-key',
    'HMAC_SHA256',
    1,
    'External-KMS',
    'kms://payments/integrity-key/version/1',
    NOW() + INTERVAL '180 days'
FROM organizations
WHERE organization_name = 'Example Financial Services';

INSERT INTO key_versions (
    key_id,
    version_number,
    algorithm,
    fingerprint,
    provider_version_reference,
    status,
    expires_at
)
SELECT
    key_id,
    1,
    algorithm,
    REPEAT('b', 64),
    provider_key_reference,
    'ACTIVE',
    expires_at
FROM encryption_keys
WHERE key_alias = 'payments/integrity-key';

-- ============================================================
-- SAMPLE SECRET AND ENCRYPTED VERSION
-- ============================================================

INSERT INTO secrets (
    organization_id,
    secret_name,
    description,
    created_by
)
SELECT
    o.organization_id,
    'database/production-password',
    'Encrypted production database credential',
    p.principal_id
FROM organizations o
JOIN principals p
    ON p.organization_id = o.organization_id
WHERE o.organization_name = 'Example Financial Services'
  AND p.principal_name = 'security-admin';

INSERT INTO secret_versions (
    secret_id,
    version_number,
    key_id,
    key_version_id,
    encryption_algorithm,
    encrypted_payload,
    initialization_vector,
    authentication_tag,
    wrapped_data_key,
    associated_data,
    created_by
)
SELECT
    s.secret_id,
    1,
    k.key_id,
    kv.key_version_id,
    'AES-256-GCM',
    DECODE('0102030405060708', 'hex'),
    DECODE('0102030405060708090a0b0c', 'hex'),
    DECODE('0102030405060708090a0b0c0d0e0f10', 'hex'),
    DECODE('aabbccddeeff001122334455', 'hex'),
    'secret:' || s.secret_id::TEXT,
    p.principal_id
FROM secrets s
JOIN organizations o
    ON o.organization_id = s.organization_id
JOIN encryption_keys k
    ON k.organization_id = o.organization_id
   AND k.key_alias = 'payments/master-key'
JOIN key_versions kv
    ON kv.key_id = k.key_id
   AND kv.version_number = 1
JOIN principals p
    ON p.organization_id = o.organization_id
   AND p.principal_name = 'security-admin'
WHERE s.secret_name = 'database/production-password';

-- ============================================================
-- SAMPLE CERTIFICATES
-- ============================================================

INSERT INTO certificates (
    organization_id,
    common_name,
    subject_name,
    issuer_name,
    serial_number,
    fingerprint,
    not_before,
    not_after
)
SELECT
    organization_id,
    'api.internal.example',
    'CN=api.internal.example',
    'CN=Internal Root CA',
    'CERT-1001',
    REPEAT('c', 64),
    NOW() - INTERVAL '30 days',
    NOW() + INTERVAL '120 days'
FROM organizations
WHERE organization_name = 'Example Financial Services';

-- Expiring certificate example.
INSERT INTO certificates (
    organization_id,
    common_name,
    subject_name,
    issuer_name,
    serial_number,
    fingerprint,
    not_before,
    not_after
)
SELECT
    organization_id,
    'legacy.internal.example',
    'CN=legacy.internal.example',
    'CN=Legacy CA',
    'CERT-1002',
    REPEAT('d', 64),
    NOW() - INTERVAL '300 days',
    NOW() + INTERVAL '10 days'
FROM organizations
WHERE organization_name = 'Example Financial Services';

-- ============================================================
-- SAMPLE USAGE AND AUDIT EVENTS
-- ============================================================

INSERT INTO key_usage (
    key_id,
    key_version_id,
    principal_id,
    operation,
    outcome,
    request_reference
)
SELECT
    k.key_id,
    kv.key_version_id,
    p.principal_id,
    'ENCRYPT',
    'SUCCESS',
    'PAYMENT-1001'
FROM encryption_keys k
JOIN key_versions kv ON kv.key_id = k.key_id
JOIN principals p ON p.principal_name = 'payments-service'
WHERE k.key_alias = 'payments/master-key';

INSERT INTO key_usage (
    key_id,
    key_version_id,
    principal_id,
    operation,
    outcome,
    request_reference
)
SELECT
    k.key_id,
    kv.key_version_id,
    p.principal_id,
    'ENCRYPT',
    'DENIED',
    'UNAUTHORIZED-1001'
FROM encryption_keys k
JOIN key_versions kv ON kv.key_id = k.key_id
JOIN principals p ON p.principal_name = 'compliance-auditor'
WHERE k.key_alias = 'payments/master-key';

INSERT INTO audit_events (
    principal_id,
    action,
    resource_type,
    resource_id,
    outcome,
    event_metadata
)
SELECT
    principal_id,
    'CREATE_KEY',
    'ENCRYPTION_KEY',
    k.key_id::TEXT,
    'SUCCESS',
    '{"provider":"External-KMS","version":1}'::JSONB
FROM principals p
CROSS JOIN encryption_keys k
WHERE p.principal_name = 'security-admin'
  AND k.key_alias = 'payments/master-key';

-- ============================================================
-- RETRIEVAL AND VALIDATION QUERIES
-- ============================================================

-- Query 1: Key inventory.
SELECT *
FROM key_inventory_report
ORDER BY organization_name, key_alias;

-- Query 2: All versions for each key.
SELECT
    k.key_alias,
    kv.version_number,
    kv.status,
    kv.fingerprint,
    kv.created_at,
    kv.expires_at
FROM encryption_keys k
JOIN key_versions kv
    ON kv.key_id = k.key_id
ORDER BY k.key_alias, kv.version_number;

-- Query 3: Current secret versions.
SELECT *
FROM secret_version_report
ORDER BY secret_name;

-- Query 4: Certificate validity.
SELECT
    common_name,
    serial_number,
    evaluate_certificate(certificate_id) AS certificate_state,
    not_after
FROM certificates
ORDER BY not_after;

-- Query 5: Key eligibility.
SELECT
    key_alias,
    key_is_eligible(key_id, 'ENCRYPT') AS can_encrypt,
    key_is_eligible(key_id, 'DECRYPT') AS can_decrypt,
    key_is_eligible(key_id, 'SIGN') AS can_sign
FROM encryption_keys;

-- ============================================================
-- AGGREGATION AND REPORTING
-- ============================================================

-- Query 6: Key distribution by algorithm and lifecycle state.
SELECT
    algorithm,
    status,
    COUNT(*) AS key_count
FROM encryption_keys
GROUP BY algorithm, status
ORDER BY algorithm, status;

-- Query 7: Key usage statistics.
SELECT
    k.key_alias,
    ku.operation,
    ku.outcome,
    COUNT(*) AS total_operations
FROM key_usage ku
JOIN encryption_keys k
    ON k.key_id = ku.key_id
GROUP BY k.key_alias, ku.operation, ku.outcome
ORDER BY k.key_alias, ku.operation;

-- Query 8: Certificate expiry monitoring.
SELECT
    common_name,
    not_after,
    not_after - NOW() AS remaining_validity
FROM certificates
WHERE revoked = FALSE
  AND not_after <= NOW() + INTERVAL '30 days'
ORDER BY not_after;

-- Query 9: Failed or denied operations.
SELECT
    p.principal_name,
    ku.operation,
    ku.request_reference,
    ku.occurred_at
FROM key_usage ku
JOIN principals p
    ON p.principal_id = ku.principal_id
WHERE ku.outcome IN ('DENIED', 'FAILURE')
ORDER BY ku.occurred_at DESC;

-- Query 10: Audit trail with metadata.
SELECT
    a.audit_id,
    p.principal_name,
    a.action,
    a.resource_type,
    a.resource_id,
    a.outcome,
    a.event_metadata,
    a.occurred_at
FROM audit_events a
LEFT JOIN principals p
    ON p.principal_id = a.principal_id
ORDER BY a.occurred_at DESC;

-- ============================================================
-- CTE: ORGANIZATION SECURITY POSTURE
-- ============================================================

WITH key_metrics AS (
    SELECT
        organization_id,
        COUNT(*) AS total_keys,
        COUNT(*) FILTER (
            WHERE status = 'ACTIVE'
        ) AS active_keys,
        COUNT(*) FILTER (
            WHERE expires_at <= NOW() + INTERVAL '30 days'
              AND status = 'ACTIVE'
        ) AS expiring_keys,
        COUNT(*) FILTER (
            WHERE status = 'REVOKED'
        ) AS revoked_keys
    FROM encryption_keys
    GROUP BY organization_id
),
certificate_metrics AS (
    SELECT
        organization_id,
        COUNT(*) AS total_certificates,
        COUNT(*) FILTER (
            WHERE NOT revoked AND not_after <= NOW() + INTERVAL '30 days'
        ) AS expiring_certificates
    FROM certificates
    GROUP BY organization_id
)
SELECT
    o.organization_name,
    COALESCE(k.total_keys, 0) AS total_keys,
    COALESCE(k.active_keys, 0) AS active_keys,
    COALESCE(k.expiring_keys, 0) AS expiring_keys,
    COALESCE(k.revoked_keys, 0) AS revoked_keys,
    COALESCE(c.total_certificates, 0) AS total_certificates,
    COALESCE(c.expiring_certificates, 0) AS expiring_certificates
FROM organizations o
LEFT JOIN key_metrics k
    ON k.organization_id = o.organization_id
LEFT JOIN certificate_metrics c
    ON c.organization_id = o.organization_id;

-- ============================================================
-- TRANSACTIONAL KEY ROTATION DEMONSTRATION
-- ============================================================

DO $$
DECLARE
    selected_key UUID;
    selected_actor BIGINT;
BEGIN
    SELECT k.key_id
    INTO selected_key
    FROM encryption_keys k
    WHERE k.key_alias = 'payments/master-key';

    SELECT principal_id
    INTO selected_actor
    FROM principals
    WHERE principal_name = 'security-admin';

    CALL rotate_key(
        selected_key,
        selected_actor,
        'kms://payments/master-key/version/2',
        REPEAT('e', 64),
        365,
        'Scheduled cryptographic key rotation'
    );

EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Rotation transaction failed: %', SQLERRM;
        RAISE;
END;
$$;

-- ============================================================
-- VALIDATE ROTATION RESULTS
-- ============================================================

SELECT
    k.key_alias,
    k.current_version,
    kv.version_number,
    kv.status,
    kv.provider_version_reference
FROM encryption_keys k
JOIN key_versions kv
    ON kv.key_id = k.key_id
WHERE k.key_alias = 'payments/master-key'
ORDER BY kv.version_number;

SELECT *
FROM key_rotations
ORDER BY rotated_at DESC;

-- Verify encryption eligibility after rotation.
SELECT
    key_alias,
    current_version,
    key_is_eligible(key_id, 'ENCRYPT') AS encryption_eligible,
    key_is_eligible(key_id, 'DECRYPT') AS decryption_eligible
FROM encryption_keys
WHERE key_alias = 'payments/master-key';

-- ============================================================
-- FAILURE CASES: SAFE VALIDATION EXAMPLES
-- ============================================================

-- Invalid key validity:
-- INSERT INTO encryption_keys (...) VALUES (..., NOW() - INTERVAL '1 day');

-- Duplicate secret:
-- INSERT INTO secrets (...) VALUES (...);

-- Invalid IV length:
-- INSERT INTO secret_versions (...) VALUES (...);

-- Mismatched key-version relationship:
-- The validation trigger rejects inconsistent references.

-- Attempting to activate a second key version:
-- The key-version trigger rejects a second active version.

-- Attempting to rotate a revoked key:
-- rotate_key() raises an exception.

-- ============================================================
-- FINAL INVENTORY
-- ============================================================

SELECT
    key_alias,
    algorithm,
    status,
    current_version,
    expires_at
FROM encryption_keys
ORDER BY key_alias;

SELECT
    secret_name,
    status,
    version_count,
    latest_version
FROM secret_version_report;

SELECT
    common_name,
    lifecycle_condition
FROM certificate_inventory_report;

COMMIT;

/*
Production notes:

1. gen_random_uuid() is available in supported modern PostgreSQL releases.
2. External KMS/HSM calls must occur in an application service.
3. Provider key references are identifiers, not raw key material.
4. Encrypted payloads, IVs, tags and wrapped data keys are persisted.
5. Application authorization must be enforced independently of UI logic.
6. Audit retention and tamper protection require separate operational controls.
7. PostgreSQL roles and grants must restrict direct table modification.
8. A database transaction cannot atomically roll back an external KMS action.
   Use idempotency, durable rotation states, and reconciliation for that boundary.
*/
