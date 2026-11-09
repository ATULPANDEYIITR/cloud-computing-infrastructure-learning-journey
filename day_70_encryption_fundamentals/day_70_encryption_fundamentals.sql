/*
===============================================================================
ENCRYPTION FUNDAMENTALS
PostgreSQL 15+

Domain:
- Symmetric encryption
- Asymmetric encryption
- Hybrid encryption
- Encryption at rest
- Encryption in transit
- Key management and rotation
- Cryptographic policy enforcement
- Encrypted resource inventory
- TLS connection compliance
- Audit and eligibility reporting

Security boundary:
This database manages encryption metadata, policy decisions,
key references, and security audit information.

Cryptographic key material is NOT stored in these tables.
Actual encryption must be performed by a trusted application,
KMS, HSM, or database encryption extension.

Run in a dedicated development database.
===============================================================================
*/

BEGIN;

CREATE SCHEMA IF NOT EXISTS encryption_lab;

SET search_path TO encryption_lab, public;

CREATE EXTENSION IF NOT EXISTS pgcrypto;


/* ============================================================================
   1. DOMAIN TYPES
============================================================================ */

CREATE TYPE encryption_type AS ENUM (
    'SYMMETRIC',
    'ASYMMETRIC',
    'HYBRID'
);

CREATE TYPE protection_location AS ENUM (
    'AT_REST',
    'IN_TRANSIT'
);

CREATE TYPE key_status AS ENUM (
    'ACTIVE',
    'RETIRED',
    'REVOKED'
);

CREATE TYPE resource_status AS ENUM (
    'PENDING',
    'PROTECTED',
    'FAILED',
    'DECOMMISSIONED'
);

CREATE TYPE policy_decision AS ENUM (
    'ALLOWED',
    'DENIED'
);

CREATE TYPE audit_event_type AS ENUM (
    'KEY_CREATED',
    'KEY_ROTATED',
    'KEY_RETIRED',
    'KEY_REVOKED',
    'ENCRYPTION_SUCCEEDED',
    'ENCRYPTION_FAILED',
    'DECRYPTION_SUCCEEDED',
    'DECRYPTION_FAILED',
    'POLICY_EVALUATED'
);


/* ============================================================================
   2. ORGANIZATIONAL IDENTITIES
============================================================================ */

CREATE TABLE security_principals (
    principal_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    principal_name VARCHAR(120) NOT NULL UNIQUE,

    principal_role VARCHAR(40) NOT NULL
        CHECK (
            principal_role IN (
                'SECURITY_ADMIN',
                'KEY_ADMIN',
                'APPLICATION',
                'AUDITOR',
                'SERVICE'
            )
        ),

    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


/* ============================================================================
   3. ENCRYPTION ALGORITHM CATALOG
============================================================================ */

CREATE TABLE algorithms (
    algorithm_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    algorithm_name VARCHAR(100) NOT NULL UNIQUE,

    encryption_category encryption_type NOT NULL,

    minimum_key_bits INTEGER NOT NULL
        CHECK (minimum_key_bits > 0),

    provides_authentication BOOLEAN NOT NULL,

    approved BOOLEAN NOT NULL DEFAULT TRUE,

    description TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO algorithms (
    algorithm_name,
    encryption_category,
    minimum_key_bits,
    provides_authentication,
    description
)
VALUES
(
    'AES-256-GCM',
    'SYMMETRIC',
    256,
    TRUE,
    'Authenticated symmetric encryption for data protection.'
),
(
    'RSA-OAEP-SHA256',
    'ASYMMETRIC',
    3072,
    FALSE,
    'Asymmetric encryption for small messages and key wrapping.'
),
(
    'AES-256-GCM+RSA-OAEP-SHA256',
    'HYBRID',
    3072,
    TRUE,
    'AES-GCM data encryption with RSA-OAEP key protection.'
);


/* ============================================================================
   4. REPOSITORIES / APPLICATION SYSTEMS
============================================================================ */

CREATE TABLE applications (
    application_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    application_name VARCHAR(150) NOT NULL UNIQUE,

    owner_principal_id BIGINT NOT NULL
        REFERENCES security_principals(principal_id),

    classification VARCHAR(30) NOT NULL
        CHECK (
            classification IN (
                'PUBLIC',
                'INTERNAL',
                'CONFIDENTIAL',
                'RESTRICTED'
            )
        ),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


/* ============================================================================
   5. CRYPTOGRAPHIC KEY INVENTORY

   Key material is deliberately excluded.
   key_reference identifies an external KMS/HSM object.
============================================================================ */

CREATE TABLE encryption_keys (
    key_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    external_key_reference VARCHAR(255) NOT NULL UNIQUE,

    application_id BIGINT NOT NULL
        REFERENCES applications(application_id),

    algorithm_id BIGINT NOT NULL
        REFERENCES algorithms(algorithm_id),

    key_version INTEGER NOT NULL
        CHECK (key_version > 0),

    key_status key_status NOT NULL DEFAULT 'ACTIVE',

    created_by BIGINT NOT NULL
        REFERENCES security_principals(principal_id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    retired_at TIMESTAMPTZ,

    revoked_at TIMESTAMPTZ,

    UNIQUE(application_id, key_version),

    CHECK (
        (key_status <> 'RETIRED' OR retired_at IS NOT NULL)
        AND
        (key_status <> 'REVOKED' OR revoked_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX one_active_key_per_application
ON encryption_keys(application_id)
WHERE key_status = 'ACTIVE';

CREATE INDEX idx_encryption_keys_status
ON encryption_keys(key_status, application_id);


/* ============================================================================
   6. KEY LIFECYCLE HISTORY
============================================================================ */

CREATE TABLE key_lifecycle_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    key_id BIGINT NOT NULL
        REFERENCES encryption_keys(key_id),

    previous_status key_status,

    new_status key_status NOT NULL,

    performed_by BIGINT NOT NULL
        REFERENCES security_principals(principal_id),

    event_reason TEXT NOT NULL,

    event_time TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_key_lifecycle_history
ON key_lifecycle_events(key_id, event_time DESC);


/* ============================================================================
   7. ENCRYPTION POLICIES
============================================================================ */

CREATE TABLE encryption_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    policy_name VARCHAR(120) NOT NULL UNIQUE,

    location protection_location NOT NULL,

    required_type encryption_type NOT NULL,

    minimum_key_bits INTEGER NOT NULL
        CHECK (minimum_key_bits >= 256),

    authentication_required BOOLEAN NOT NULL DEFAULT TRUE,

    unique_nonce_required BOOLEAN NOT NULL DEFAULT TRUE,

    certificate_validation_required BOOLEAN NOT NULL DEFAULT FALSE,

    minimum_tls_version NUMERIC(3, 1) NOT NULL DEFAULT 1.2
        CHECK (minimum_tls_version IN (1.2, 1.3)),

    require_managed_key BOOLEAN NOT NULL DEFAULT TRUE,

    require_active_key BOOLEAN NOT NULL DEFAULT TRUE,

    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


/* ============================================================================
   8. RESOURCE INVENTORY
============================================================================ */

CREATE TABLE protected_resources (
    resource_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    application_id BIGINT NOT NULL
        REFERENCES applications(application_id),

    resource_name VARCHAR(180) NOT NULL,

    location protection_location NOT NULL,

    classification VARCHAR(30) NOT NULL
        CHECK (
            classification IN (
                'PUBLIC',
                'INTERNAL',
                'CONFIDENTIAL',
                'RESTRICTED'
            )
        ),

    resource_status resource_status NOT NULL DEFAULT 'PENDING',

    policy_id BIGINT NOT NULL
        REFERENCES encryption_policies(policy_id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(application_id, resource_name)
);

CREATE INDEX idx_resource_status
ON protected_resources(resource_status, location);

CREATE INDEX idx_resource_application
ON protected_resources(application_id);


/* ============================================================================
   9. ENCRYPTION OPERATIONS
============================================================================ */

CREATE TABLE encryption_operations (
    operation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    resource_id BIGINT NOT NULL
        REFERENCES protected_resources(resource_id),

    key_id BIGINT
        REFERENCES encryption_keys(key_id),

    algorithm_id BIGINT NOT NULL
        REFERENCES algorithms(algorithm_id),

    operation_type VARCHAR(20) NOT NULL
        CHECK (
            operation_type IN ('ENCRYPT', 'DECRYPT')
        ),

    nonce_fingerprint VARCHAR(128),

    ciphertext_fingerprint VARCHAR(128),

    authenticated BOOLEAN NOT NULL DEFAULT FALSE,

    operation_successful BOOLEAN NOT NULL DEFAULT FALSE,

    failure_reason TEXT,

    performed_by BIGINT NOT NULL
        REFERENCES security_principals(principal_id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (
        operation_successful = FALSE
        OR failure_reason IS NULL
    )
);

CREATE INDEX idx_operations_resource_time
ON encryption_operations(resource_id, created_at DESC);

CREATE INDEX idx_operations_key
ON encryption_operations(key_id);


/* ============================================================================
   10. TRANSPORT SECURITY RECORDS
============================================================================ */

CREATE TABLE transport_connections (
    connection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    application_id BIGINT NOT NULL
        REFERENCES applications(application_id),

    remote_service VARCHAR(180) NOT NULL,

    tls_version NUMERIC(3, 1) NOT NULL
        CHECK (tls_version IN (1.2, 1.3)),

    cipher_suite VARCHAR(150) NOT NULL,

    certificate_validated BOOLEAN NOT NULL,

    hostname_validated BOOLEAN NOT NULL,

    certificate_expiry TIMESTAMPTZ,

    connected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    disconnected_at TIMESTAMPTZ,

    CHECK (
        disconnected_at IS NULL
        OR disconnected_at >= connected_at
    )
);

CREATE INDEX idx_transport_application_time
ON transport_connections(application_id, connected_at DESC);


/* ============================================================================
   11. AUDIT EVENTS
============================================================================ */

CREATE TABLE security_audit_events (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    event_type audit_event_type NOT NULL,

    principal_id BIGINT
        REFERENCES security_principals(principal_id),

    resource_id BIGINT
        REFERENCES protected_resources(resource_id),

    key_id BIGINT
        REFERENCES encryption_keys(key_id),

    event_details JSONB NOT NULL DEFAULT '{}'::JSONB,

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_event_time
ON security_audit_events(occurred_at DESC);

CREATE INDEX idx_audit_event_details
ON security_audit_events USING GIN(event_details);


/* ============================================================================
   12. KEY LIFECYCLE TRIGGER
============================================================================ */

CREATE OR REPLACE FUNCTION record_key_lifecycle()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    actor_id BIGINT;
BEGIN
    actor_id := COALESCE(
        NULLIF(current_setting('encryption.actor_id', TRUE), '')::BIGINT,
        NEW.created_by
    );

    IF TG_OP = 'INSERT' THEN
        INSERT INTO key_lifecycle_events (
            key_id,
            previous_status,
            new_status,
            performed_by,
            event_reason
        )
        VALUES (
            NEW.key_id,
            NULL,
            NEW.key_status,
            NEW.created_by,
            'Key registered'
        );

        RETURN NEW;
    END IF;

    IF OLD.key_status <> NEW.key_status THEN

        IF NEW.key_status = 'RETIRED'
           AND NEW.retired_at IS NULL THEN
            NEW.retired_at := NOW();
        END IF;

        IF NEW.key_status = 'REVOKED'
           AND NEW.revoked_at IS NULL THEN
            NEW.revoked_at := NOW();
        END IF;

        IF OLD.key_status = 'REVOKED' THEN
            RAISE EXCEPTION 'A revoked key cannot be reactivated';
        END IF;

        INSERT INTO key_lifecycle_events (
            key_id,
            previous_status,
            new_status,
            performed_by,
            event_reason
        )
        VALUES (
            NEW.key_id,
            OLD.key_status,
            NEW.key_status,
            actor_id,
            'Key status transition'
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_key_lifecycle
BEFORE INSERT OR UPDATE OF key_status
ON encryption_keys
FOR EACH ROW
EXECUTE FUNCTION record_key_lifecycle();


/* ============================================================================
   13. PROTECT RESOURCE STATUS TRANSITIONS
============================================================================ */

CREATE OR REPLACE FUNCTION validate_resource_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.resource_status = 'DECOMMISSIONED'
       AND NEW.resource_status <> 'DECOMMISSIONED' THEN
        RAISE EXCEPTION 'Decommissioned resources cannot be reactivated';
    END IF;

    IF NEW.resource_status = 'PROTECTED' THEN
        IF NOT EXISTS (
            SELECT 1
            FROM encryption_operations eo
            JOIN encryption_keys ek
              ON ek.key_id = eo.key_id
            JOIN algorithms a
              ON a.algorithm_id = eo.algorithm_id
            WHERE eo.resource_id = NEW.resource_id
              AND eo.operation_type = 'ENCRYPT'
              AND eo.operation_successful = TRUE
              AND eo.authenticated = TRUE
              AND ek.key_status = 'ACTIVE'
              AND a.approved = TRUE
        ) THEN
            RAISE EXCEPTION
                'Resource cannot be marked protected without a successful authenticated encryption operation';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_resource_transition
BEFORE UPDATE OF resource_status
ON protected_resources
FOR EACH ROW
EXECUTE FUNCTION validate_resource_transition();


/* ============================================================================
   14. CENTRALIZED POLICY EVALUATION
============================================================================ */

CREATE OR REPLACE FUNCTION evaluate_encryption_request(
    p_resource_id BIGINT,
    p_key_id BIGINT,
    p_algorithm_id BIGINT,
    p_authenticated BOOLEAN,
    p_nonce_unique BOOLEAN,
    p_certificate_valid BOOLEAN,
    p_tls_version NUMERIC
)
RETURNS TABLE (
    decision policy_decision,
    reasons TEXT[]
)
LANGUAGE plpgsql
AS $$
DECLARE
    r RECORD;
    k RECORD;
    a RECORD;
    p RECORD;

    errors TEXT[] := ARRAY[]::TEXT[];
BEGIN

    SELECT *
    INTO r
    FROM protected_resources
    WHERE resource_id = p_resource_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT
            'DENIED'::policy_decision,
            ARRAY['Unknown resource']::TEXT[];
        RETURN;
    END IF;

    SELECT *
    INTO p
    FROM encryption_policies
    WHERE policy_id = r.policy_id
      AND is_enabled = TRUE;

    IF NOT FOUND THEN
        errors := array_append(errors, 'No active encryption policy');
    END IF;

    SELECT *
    INTO a
    FROM algorithms
    WHERE algorithm_id = p_algorithm_id;

    IF NOT FOUND THEN
        errors := array_append(errors, 'Unknown algorithm');
    ELSE
        IF a.approved = FALSE THEN
            errors := array_append(errors, 'Algorithm is not approved');
        END IF;

        IF a.encryption_category IS DISTINCT FROM p.required_type THEN
            errors := array_append(errors, 'Encryption type mismatch');
        END IF;

        IF a.minimum_key_bits < p.minimum_key_bits THEN
            errors := array_append(errors, 'Algorithm strength below policy');
        END IF;
    END IF;

    IF p IS NOT NULL THEN
        IF p.location <> r.location THEN
            errors := array_append(errors, 'Protection location mismatch');
        END IF;

        IF p.authentication_required AND NOT p_authenticated THEN
            errors := array_append(errors, 'Authentication is required');
        END IF;

        IF p.unique_nonce_required AND NOT p_nonce_unique THEN
            errors := array_append(errors, 'Nonce uniqueness is required');
        END IF;

        IF p.certificate_validation_required
           AND NOT p_certificate_valid THEN
            errors := array_append(errors, 'Certificate validation failed');
        END IF;

        IF r.location = 'IN_TRANSIT'
           AND (
               p_tls_version IS NULL
               OR p_tls_version < p.minimum_tls_version
           ) THEN
            errors := array_append(errors, 'TLS version below policy minimum');
        END IF;
    END IF;

    IF p_key_id IS NULL THEN
        errors := array_append(errors, 'Encryption key is missing');
    ELSE
        SELECT *
        INTO k
        FROM encryption_keys
        WHERE key_id = p_key_id;

        IF NOT FOUND THEN
            errors := array_append(errors, 'Unknown key');
        ELSE
            IF k.key_status <> 'ACTIVE' THEN
                errors := array_append(errors, 'Key is not active');
            END IF;

            IF k.application_id <> r.application_id THEN
                errors := array_append(errors, 'Key belongs to another application');
            END IF;

            IF p IS NOT NULL AND k.algorithm_id IS DISTINCT FROM a.algorithm_id THEN
                errors := array_append(errors, 'Key algorithm mismatch');
            END IF;
        END IF;
    END IF;

    RETURN QUERY
    SELECT
        CASE
            WHEN cardinality(errors) = 0
                THEN 'ALLOWED'::policy_decision
            ELSE 'DENIED'::policy_decision
        END,
        errors;
END;
$$;


/* ============================================================================
   15. ENCRYPTION OPERATION VALIDATION
============================================================================ */

CREATE OR REPLACE FUNCTION validate_encryption_operation(
    p_resource_id BIGINT,
    p_key_id BIGINT,
    p_algorithm_id BIGINT,
    p_authenticated BOOLEAN
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    result RECORD;
BEGIN
    SELECT *
    INTO result
    FROM evaluate_encryption_request(
        p_resource_id,
        p_key_id,
        p_algorithm_id,
        p_authenticated,
        TRUE,
        TRUE,
        1.3
    );

    RETURN result.decision = 'ALLOWED';
END;
$$;


/* ============================================================================
   16. PROCEDURE: KEY ROTATION
============================================================================ */

CREATE OR REPLACE PROCEDURE rotate_application_key(
    p_application_id BIGINT,
    p_new_external_reference VARCHAR,
    p_new_algorithm_id BIGINT,
    p_actor_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    next_version INTEGER;
    old_key_id BIGINT;
BEGIN

    IF NOT EXISTS (
        SELECT 1
        FROM security_principals
        WHERE principal_id = p_actor_id
          AND is_enabled = TRUE
          AND principal_role IN ('KEY_ADMIN', 'SECURITY_ADMIN')
    ) THEN
        RAISE EXCEPTION 'Principal is not authorized to rotate keys';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM applications
        WHERE application_id = p_application_id
    ) THEN
        RAISE EXCEPTION 'Application does not exist';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM algorithms
        WHERE algorithm_id = p_new_algorithm_id
          AND approved = TRUE
    ) THEN
        RAISE EXCEPTION 'Replacement algorithm is not approved';
    END IF;

    SELECT COALESCE(MAX(key_version), 0) + 1
    INTO next_version
    FROM encryption_keys
    WHERE application_id = p_application_id;

    UPDATE encryption_keys
    SET key_status = 'RETIRED',
        retired_at = NOW()
    WHERE application_id = p_application_id
      AND key_status = 'ACTIVE'
    RETURNING key_id INTO old_key_id;

    PERFORM set_config(
        'encryption.actor_id',
        p_actor_id::TEXT,
        TRUE
    );

    INSERT INTO encryption_keys (
        external_key_reference,
        application_id,
        algorithm_id,
        key_version,
        key_status,
        created_by
    )
    VALUES (
        p_new_external_reference,
        p_application_id,
        p_new_algorithm_id,
        next_version,
        'ACTIVE',
        p_actor_id
    );

    INSERT INTO security_audit_events (
        event_type,
        principal_id,
        key_id,
        event_details
    )
    VALUES (
        'KEY_ROTATED',
        p_actor_id,
        old_key_id,
        jsonb_build_object(
            'application_id', p_application_id,
            'new_version', next_version
        )
    );

END;
$$;


/* ============================================================================
   17. REPORTING VIEWS
============================================================================ */

CREATE OR REPLACE VIEW v_resource_encryption_status AS
SELECT
    r.resource_id,
    r.resource_name,
    a.application_name,
    r.location,
    r.classification,
    r.resource_status,
    p.policy_name,
    p.required_type,
    COUNT(eo.operation_id) FILTER (
        WHERE eo.operation_successful = TRUE
    ) AS successful_operations,
    MAX(eo.created_at) AS last_operation_at

FROM protected_resources r

JOIN applications a
  ON a.application_id = r.application_id

JOIN encryption_policies p
  ON p.policy_id = r.policy_id

LEFT JOIN encryption_operations eo
  ON eo.resource_id = r.resource_id

GROUP BY
    r.resource_id,
    r.resource_name,
    a.application_name,
    r.location,
    r.classification,
    r.resource_status,
    p.policy_name,
    p.required_type;


CREATE OR REPLACE VIEW v_active_key_inventory AS
SELECT
    ek.key_id,
    ek.external_key_reference,
    a.application_name,
    alg.algorithm_name,
    ek.key_version,
    ek.key_status,
    ek.created_at

FROM encryption_keys ek

JOIN applications a
  ON a.application_id = ek.application_id

JOIN algorithms alg
  ON alg.algorithm_id = ek.algorithm_id

WHERE ek.key_status = 'ACTIVE';


CREATE OR REPLACE VIEW v_transport_compliance AS
SELECT
    tc.connection_id,
    a.application_name,
    tc.remote_service,
    tc.tls_version,
    tc.cipher_suite,
    tc.certificate_validated,
    tc.hostname_validated,

    CASE
        WHEN tc.tls_version >= 1.2
         AND tc.certificate_validated
         AND tc.hostname_validated
        THEN TRUE
        ELSE FALSE
    END AS transport_compliant

FROM transport_connections tc

JOIN applications a
  ON a.application_id = tc.application_id;


/* ============================================================================
   18. SAMPLE ORGANIZATIONAL RECORDS
============================================================================ */

INSERT INTO security_principals (
    principal_name,
    principal_role
)
VALUES
('security_admin', 'SECURITY_ADMIN'),
('key_manager', 'KEY_ADMIN'),
('payment_service', 'APPLICATION'),
('audit_officer', 'AUDITOR'),
('storage_service', 'SERVICE');


INSERT INTO applications (
    application_name,
    owner_principal_id,
    classification
)
SELECT
    'Payment Processing Platform',
    principal_id,
    'RESTRICTED'
FROM security_principals
WHERE principal_name = 'security_admin';


INSERT INTO applications (
    application_name,
    owner_principal_id,
    classification
)
SELECT
    'Enterprise Document Storage',
    principal_id,
    'CONFIDENTIAL'
FROM security_principals
WHERE principal_name = 'security_admin';


INSERT INTO encryption_policies (
    policy_name,
    location,
    required_type,
    minimum_key_bits,
    authentication_required,
    unique_nonce_required,
    certificate_validation_required,
    minimum_tls_version
)
VALUES
(
    'Confidential Data at Rest',
    'AT_REST',
    'SYMMETRIC',
    256,
    TRUE,
    TRUE,
    FALSE,
    1.2
),
(
    'Secure Enterprise Transport',
    'IN_TRANSIT',
    'HYBRID',
    256,
    TRUE,
    TRUE,
    TRUE,
    1.2
);


/* ============================================================================
   19. SAMPLE KEYS
============================================================================ */

INSERT INTO encryption_keys (
    external_key_reference,
    application_id,
    algorithm_id,
    key_version,
    key_status,
    created_by
)
SELECT
    'kms/payment/aes-key/v1',
    app.application_id,
    alg.algorithm_id,
    1,
    'ACTIVE',
    principal.principal_id
FROM applications app
JOIN algorithms alg
  ON alg.algorithm_name = 'AES-256-GCM'
JOIN security_principals principal
  ON principal.principal_name = 'key_manager'
WHERE app.application_name = 'Payment Processing Platform';


INSERT INTO encryption_keys (
    external_key_reference,
    application_id,
    algorithm_id,
    key_version,
    key_status,
    created_by
)
SELECT
    'kms/document/aes-key/v1',
    app.application_id,
    alg.algorithm_id,
    1,
    'ACTIVE',
    principal.principal_id
FROM applications app
JOIN algorithms alg
  ON alg.algorithm_name = 'AES-256-GCM'
JOIN security_principals principal
  ON principal.principal_name = 'key_manager'
WHERE app.application_name = 'Enterprise Document Storage';


/* ============================================================================
   20. SAMPLE RESOURCES
============================================================================ */

INSERT INTO protected_resources (
    application_id,
    resource_name,
    location,
    classification,
    policy_id
)
SELECT
    app.application_id,
    'customer-payment-records',
    'AT_REST',
    'RESTRICTED',
    policy.policy_id
FROM applications app
JOIN encryption_policies policy
  ON policy.policy_name = 'Confidential Data at Rest'
WHERE app.application_name = 'Payment Processing Platform';


INSERT INTO protected_resources (
    application_id,
    resource_name,
    location,
    classification,
    policy_id
)
SELECT
    app.application_id,
    'customer-document-transfer',
    'IN_TRANSIT',
    'CONFIDENTIAL',
    policy.policy_id
FROM applications app
JOIN encryption_policies policy
  ON policy.policy_name = 'Secure Enterprise Transport'
WHERE app.application_name = 'Enterprise Document Storage';


/* ============================================================================
   21. SAMPLE ENCRYPTION OPERATIONS
============================================================================ */

INSERT INTO encryption_operations (
    resource_id,
    key_id,
    algorithm_id,
    operation_type,
    nonce_fingerprint,
    ciphertext_fingerprint,
    authenticated,
    operation_successful,
    performed_by
)
SELECT
    r.resource_id,
    k.key_id,
    alg.algorithm_id,
    'ENCRYPT',
    'nonce-fingerprint-001',
    'ciphertext-fingerprint-001',
    TRUE,
    TRUE,
    principal.principal_id
FROM protected_resources r
JOIN applications app
  ON app.application_id = r.application_id
JOIN encryption_keys k
  ON k.application_id = app.application_id
 AND k.key_status = 'ACTIVE'
JOIN algorithms alg
  ON alg.algorithm_name = 'AES-256-GCM'
JOIN security_principals principal
  ON principal.principal_name = 'storage_service'
WHERE r.resource_name = 'customer-payment-records';


INSERT INTO encryption_operations (
    resource_id,
    key_id,
    algorithm_id,
    operation_type,
    authenticated,
    operation_successful,
    failure_reason,
    performed_by
)
SELECT
    r.resource_id,
    k.key_id,
    alg.algorithm_id,
    'ENCRYPT',
    FALSE,
    FALSE,
    'Authentication configuration missing',
    principal.principal_id
FROM protected_resources r
JOIN applications app
  ON app.application_id = r.application_id
JOIN encryption_keys k
  ON k.application_id = app.application_id
 AND k.key_status = 'ACTIVE'
JOIN algorithms alg
  ON alg.algorithm_name = 'AES-256-GCM'
JOIN security_principals principal
  ON principal.principal_name = 'storage_service'
WHERE r.resource_name = 'customer-payment-records';


/* ============================================================================
   22. VALID RESOURCE STATE TRANSITION
============================================================================ */

UPDATE protected_resources
SET resource_status = 'PROTECTED'
WHERE resource_name = 'customer-payment-records';


/* ============================================================================
   23. TRANSPORT CONNECTION RECORDS
============================================================================ */

INSERT INTO transport_connections (
    application_id,
    remote_service,
    tls_version,
    cipher_suite,
    certificate_validated,
    hostname_validated,
    certificate_expiry
)
SELECT
    application_id,
    'internal-payment-gateway',
    1.3,
    'TLS_AES_256_GCM_SHA384',
    TRUE,
    TRUE,
    NOW() + INTERVAL '180 days'
FROM applications
WHERE application_name = 'Payment Processing Platform';


INSERT INTO transport_connections (
    application_id,
    remote_service,
    tls_version,
    cipher_suite,
    certificate_validated,
    hostname_validated
)
SELECT
    application_id,
    'legacy-integration-endpoint',
    1.2,
    'TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256',
    FALSE,
    FALSE
FROM applications
WHERE application_name = 'Payment Processing Platform';


/* ============================================================================
   24. AUDIT RECORDS
============================================================================ */

INSERT INTO security_audit_events (
    event_type,
    principal_id,
    event_details
)
SELECT
    'POLICY_EVALUATED',
    principal_id,
    jsonb_build_object(
        'policy', 'Confidential Data at Rest',
        'result', 'ALLOWED'
    )
FROM security_principals
WHERE principal_name = 'audit_officer';


/* ============================================================================
   25. RETRIEVAL
============================================================================ */

SELECT *
FROM v_resource_encryption_status
ORDER BY resource_id;


/* ============================================================================
   26. ACTIVE KEY INVENTORY
============================================================================ */

SELECT *
FROM v_active_key_inventory
ORDER BY application_name, key_version;


/* ============================================================================
   27. POLICY EVALUATION
============================================================================ */

SELECT *
FROM evaluate_encryption_request(
    (
        SELECT resource_id
        FROM protected_resources
        WHERE resource_name = 'customer-payment-records'
    ),
    (
        SELECT key_id
        FROM encryption_keys
        WHERE external_key_reference = 'kms/payment/aes-key/v1'
    ),
    (
        SELECT algorithm_id
        FROM algorithms
        WHERE algorithm_name = 'AES-256-GCM'
    ),
    TRUE,
    TRUE,
    TRUE,
    NULL
);


/* ============================================================================
   28. INVALID POLICY EVALUATION
============================================================================ */

SELECT *
FROM evaluate_encryption_request(
    (
        SELECT resource_id
        FROM protected_resources
        WHERE resource_name = 'customer-payment-records'
    ),
    (
        SELECT key_id
        FROM encryption_keys
        WHERE external_key_reference = 'kms/payment/aes-key/v1'
    ),
    (
        SELECT algorithm_id
        FROM algorithms
        WHERE algorithm_name = 'AES-256-GCM'
    ),
    FALSE,
    FALSE,
    TRUE,
    NULL
);


/* ============================================================================
   29. TRANSPORT SECURITY REPORT
============================================================================ */

SELECT
    application_name,
    remote_service,
    tls_version,
    certificate_validated,
    hostname_validated,
    transport_compliant

FROM v_transport_compliance

ORDER BY application_name, remote_service;


/* ============================================================================
   30. AGGREGATION
============================================================================ */

SELECT
    a.application_name,
    r.location,
    r.classification,
    COUNT(*) AS resource_count,

    COUNT(*) FILTER (
        WHERE r.resource_status = 'PROTECTED'
    ) AS protected_count,

    COUNT(*) FILTER (
        WHERE r.resource_status = 'FAILED'
    ) AS failed_count

FROM protected_resources r

JOIN applications a
  ON a.application_id = r.application_id

GROUP BY
    a.application_name,
    r.location,
    r.classification

ORDER BY a.application_name;


/* ============================================================================
   31. CTE: APPLICATION SECURITY POSTURE
============================================================================ */

WITH resource_metrics AS (
    SELECT
        application_id,
        COUNT(*) AS total_resources,

        COUNT(*) FILTER (
            WHERE resource_status = 'PROTECTED'
        ) AS protected_resources,

        COUNT(*) FILTER (
            WHERE resource_status <> 'PROTECTED'
        ) AS unprotected_resources

    FROM protected_resources

    GROUP BY application_id
),

transport_metrics AS (
    SELECT
        application_id,

        COUNT(*) AS connection_count,

        COUNT(*) FILTER (
            WHERE tls_version >= 1.2
              AND certificate_validated
              AND hostname_validated
        ) AS compliant_connections

    FROM transport_connections

    GROUP BY application_id
)

SELECT
    app.application_name,

    COALESCE(rm.total_resources, 0) AS total_resources,

    COALESCE(rm.protected_resources, 0) AS protected_resources,

    COALESCE(rm.unprotected_resources, 0) AS unprotected_resources,

    COALESCE(tm.connection_count, 0) AS connections,

    COALESCE(tm.compliant_connections, 0) AS compliant_connections

FROM applications app

LEFT JOIN resource_metrics rm
  ON rm.application_id = app.application_id

LEFT JOIN transport_metrics tm
  ON tm.application_id = app.application_id

ORDER BY app.application_name;


/* ============================================================================
   32. WORKFLOW PROCESSING: RESOURCE ELIGIBILITY
============================================================================ */

SELECT
    r.resource_name,

    CASE
        WHEN p.is_enabled = FALSE
            THEN 'POLICY_DISABLED'

        WHEN NOT EXISTS (
            SELECT 1
            FROM encryption_keys k
            WHERE k.application_id = r.application_id
              AND k.key_status = 'ACTIVE'
        )
            THEN 'NO_ACTIVE_KEY'

        WHEN r.resource_status = 'PROTECTED'
            THEN 'PROTECTED'

        ELSE 'REQUIRES_ENCRYPTION'
    END AS eligibility

FROM protected_resources r

JOIN encryption_policies p
  ON p.policy_id = r.policy_id;


/* ============================================================================
   33. FAILURE REPORT
============================================================================ */

SELECT
    r.resource_name,
    eo.operation_type,
    eo.failure_reason,
    eo.created_at

FROM encryption_operations eo

JOIN protected_resources r
  ON r.resource_id = eo.resource_id

WHERE eo.operation_successful = FALSE

ORDER BY eo.created_at DESC;


/* ============================================================================
   34. KEY ROTATION TRANSACTION DEMONSTRATION

   The procedure retires the previous active key and creates
   a new version. It does not re-encrypt existing data.
============================================================================ */

DO $$
DECLARE
    app_id BIGINT;
    algorithm_id BIGINT;
    actor_id BIGINT;
BEGIN

    SELECT application_id
    INTO app_id
    FROM applications
    WHERE application_name = 'Payment Processing Platform';

    SELECT algorithm_id
    INTO algorithm_id
    FROM algorithms
    WHERE algorithm_name = 'AES-256-GCM';

    SELECT principal_id
    INTO actor_id
    FROM security_principals
    WHERE principal_name = 'key_manager';

    CALL rotate_application_key(
        app_id,
        'kms/payment/aes-key/v2',
        algorithm_id,
        actor_id
    );

END;
$$;


/* ============================================================================
   35. ROTATION REPORT
============================================================================ */

SELECT
    a.application_name,
    k.external_key_reference,
    k.key_version,
    k.key_status,
    k.created_at,
    k.retired_at

FROM encryption_keys k

JOIN applications a
  ON a.application_id = k.application_id

ORDER BY a.application_name, k.key_version;


/* ============================================================================
   36. SECURITY AUDIT REPORT
============================================================================ */

SELECT
    e.event_type,
    p.principal_name,
    e.event_details,
    e.occurred_at

FROM security_audit_events e

LEFT JOIN security_principals p
  ON p.principal_id = e.principal_id

ORDER BY e.occurred_at DESC;


/* ============================================================================
   37. CONTROLLED FAILURE DEMONSTRATION

   This subtransaction attempts to reactivate a revoked key.
   The exception is caught, so the complete script remains executable.
============================================================================ */

DO $$
DECLARE
    target_key BIGINT;
BEGIN

    SELECT key_id
    INTO target_key
    FROM encryption_keys
    WHERE external_key_reference = 'kms/payment/aes-key/v1';

    UPDATE encryption_keys
    SET key_status = 'REVOKED',
        revoked_at = NOW()
    WHERE key_id = target_key;

    BEGIN
        UPDATE encryption_keys
        SET key_status = 'ACTIVE'
        WHERE key_id = target_key;

        RAISE EXCEPTION
            'Expected revoked-key transition rejection did not occur';

    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE
                'Expected security failure handled: %',
                SQLERRM;
    END;

END;
$$;


/* ============================================================================
   38. ADDITIONAL VALIDATION QUERIES
============================================================================ */

/* Find applications with no active encryption key. */

SELECT
    a.application_name

FROM applications a

WHERE NOT EXISTS (
    SELECT 1
    FROM encryption_keys k
    WHERE k.application_id = a.application_id
      AND k.key_status = 'ACTIVE'
);


/* Find weak or unapproved algorithms. */

SELECT
    algorithm_name,
    minimum_key_bits,
    approved

FROM algorithms

WHERE approved = FALSE
   OR minimum_key_bits < 256;


/* Find transport connections requiring remediation. */

SELECT
    remote_service,
    tls_version,
    certificate_validated,
    hostname_validated

FROM transport_connections

WHERE tls_version < 1.2
   OR certificate_validated = FALSE
   OR hostname_validated = FALSE;


/* ============================================================================
   39. FINAL DATABASE COUNTS
============================================================================ */

SELECT
    (SELECT COUNT(*) FROM applications) AS applications,

    (SELECT COUNT(*) FROM encryption_keys) AS registered_keys,

    (SELECT COUNT(*) FROM protected_resources) AS resources,

    (SELECT COUNT(*) FROM encryption_operations) AS operations,

    (SELECT COUNT(*) FROM encryption_policies) AS policies,

    (SELECT COUNT(*) FROM security_audit_events) AS audit_events;


/* ============================================================================
   TRANSACTION COMPLETION
============================================================================ */

COMMIT;
