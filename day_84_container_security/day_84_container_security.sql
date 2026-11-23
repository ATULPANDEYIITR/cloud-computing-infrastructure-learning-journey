/*
===============================================================================
CONTAINER SECURITY GOVERNANCE DATABASE
PostgreSQL 15+

Domain:
- Container repositories and image artifacts
- Immutable image digests
- Vulnerability inventory
- CVE severity assessment
- Image scanning
- Minimal image requirements
- Image provenance
- Secret exposure
- Runtime security events
- Deployment admission
- Audit and reporting

The schema separates image metadata, scan results, policies,
runtime observations and deployment decisions.
===============================================================================
*/

BEGIN;

CREATE SCHEMA IF NOT EXISTS container_security;

SET search_path TO container_security, public;

-- ============================================================================
-- 1. DOMAIN TYPES
-- ============================================================================

CREATE TYPE severity_level AS ENUM (
    'CRITICAL',
    'HIGH',
    'MEDIUM',
    'LOW',
    'UNKNOWN'
);

CREATE TYPE scan_status AS ENUM (
    'PENDING',
    'RUNNING',
    'COMPLETED',
    'FAILED'
);

CREATE TYPE admission_decision AS ENUM (
    'ALLOW',
    'DENY',
    'REVIEW'
);

CREATE TYPE image_lifecycle AS ENUM (
    'REGISTERED',
    'SCANNED',
    'APPROVED',
    'BLOCKED',
    'RETIRED'
);

CREATE TYPE runtime_event_type AS ENUM (
    'PROCESS_EXECUTION',
    'SHELL_EXECUTION',
    'PRIVILEGED_EXECUTION',
    'SECRET_ACCESS',
    'FILESYSTEM_WRITE',
    'NETWORK_CONNECTION'
);

-- ============================================================================
-- 2. REPOSITORIES
-- ============================================================================

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    repository_name VARCHAR(150) NOT NULL UNIQUE,

    registry_name VARCHAR(150) NOT NULL,

    owner_team VARCHAR(100) NOT NULL,

    environment VARCHAR(30) NOT NULL
        CHECK (
            environment IN (
                'DEVELOPMENT',
                'TEST',
                'STAGING',
                'PRODUCTION'
            )
        ),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    active BOOLEAN NOT NULL DEFAULT TRUE
);

-- ============================================================================
-- 3. CONTAINER IMAGES
-- ============================================================================

CREATE TABLE container_images (
    image_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    image_name VARCHAR(200) NOT NULL,

    image_tag VARCHAR(100) NOT NULL,

    image_digest VARCHAR(71) NOT NULL
        CHECK (
            image_digest ~ '^sha256:[a-f0-9]{64}$'
        ),

    base_image VARCHAR(250) NOT NULL,

    image_size_mb NUMERIC(12,2) NOT NULL
        CHECK (image_size_mb > 0),

    user_id INTEGER NOT NULL
        CHECK (user_id >= 0),

    contains_shell BOOLEAN NOT NULL DEFAULT FALSE,

    privileged BOOLEAN NOT NULL DEFAULT FALSE,

    signature_verified BOOLEAN NOT NULL DEFAULT FALSE,

    provenance_verified BOOLEAN NOT NULL DEFAULT FALSE,

    lifecycle image_lifecycle NOT NULL DEFAULT 'REGISTERED',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(repository_id, image_digest)
);

CREATE INDEX idx_images_repository
ON container_images(repository_id, created_at DESC);

CREATE INDEX idx_images_lifecycle
ON container_images(lifecycle);

CREATE INDEX idx_images_digest
ON container_images(image_digest);

-- ============================================================================
-- 4. IMAGE PACKAGES
-- ============================================================================

CREATE TABLE image_packages (
    package_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    image_id BIGINT NOT NULL
        REFERENCES container_images(image_id)
        ON DELETE CASCADE,

    package_name VARCHAR(200) NOT NULL,

    installed_version VARCHAR(100) NOT NULL,

    package_type VARCHAR(30) NOT NULL
        CHECK (
            package_type IN (
                'OS',
                'APPLICATION',
                'RUNTIME',
                'LIBRARY'
            )
        ),

    UNIQUE(image_id, package_name, installed_version)
);

CREATE INDEX idx_image_packages_name
ON image_packages(package_name);

-- ============================================================================
-- 5. VULNERABILITY CATALOG
-- ============================================================================

CREATE TABLE vulnerabilities (
    vulnerability_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cve_id VARCHAR(30) NOT NULL UNIQUE
        CHECK (
            cve_id ~ '^CVE-[0-9]{4}-[0-9]{4,}$'
        ),

    severity severity_level NOT NULL,

    cvss_score NUMERIC(3,1)
        CHECK (
            cvss_score IS NULL OR
            cvss_score BETWEEN 0 AND 10
        ),

    description TEXT NOT NULL,

    fixed_version VARCHAR(100),

    exploitable BOOLEAN NOT NULL DEFAULT FALSE,

    published_at TIMESTAMPTZ,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_vulnerabilities_severity
ON vulnerabilities(severity);

CREATE INDEX idx_vulnerabilities_exploitable
ON vulnerabilities(exploitable)
WHERE exploitable = TRUE;

-- ============================================================================
-- 6. IMAGE VULNERABILITY FINDINGS
-- ============================================================================

CREATE TABLE image_vulnerabilities (
    finding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    image_id BIGINT NOT NULL
        REFERENCES container_images(image_id)
        ON DELETE CASCADE,

    package_id BIGINT NOT NULL
        REFERENCES image_packages(package_id)
        ON DELETE CASCADE,

    vulnerability_id BIGINT NOT NULL
        REFERENCES vulnerabilities(vulnerability_id),

    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    resolved BOOLEAN NOT NULL DEFAULT FALSE,

    resolved_at TIMESTAMPTZ,

    UNIQUE(image_id, package_id, vulnerability_id),

    CHECK (
        (resolved = FALSE AND resolved_at IS NULL)
        OR
        (resolved = TRUE AND resolved_at IS NOT NULL)
    )
);

CREATE INDEX idx_image_vulnerabilities_image
ON image_vulnerabilities(image_id, resolved);

CREATE INDEX idx_image_vulnerabilities_vulnerability
ON image_vulnerabilities(vulnerability_id);

-- ============================================================================
-- 7. IMAGE SCANS
-- ============================================================================

CREATE TABLE image_scans (
    scan_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    image_id BIGINT NOT NULL
        REFERENCES container_images(image_id),

    scanner_name VARCHAR(100) NOT NULL,

    scanner_version VARCHAR(50) NOT NULL,

    scan_status scan_status NOT NULL DEFAULT 'PENDING',

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    decision admission_decision,

    total_vulnerabilities INTEGER NOT NULL DEFAULT 0
        CHECK (total_vulnerabilities >= 0),

    critical_count INTEGER NOT NULL DEFAULT 0
        CHECK (critical_count >= 0),

    high_count INTEGER NOT NULL DEFAULT 0
        CHECK (high_count >= 0),

    medium_count INTEGER NOT NULL DEFAULT 0
        CHECK (medium_count >= 0),

    low_count INTEGER NOT NULL DEFAULT 0
        CHECK (low_count >= 0),

    unknown_count INTEGER NOT NULL DEFAULT 0
        CHECK (unknown_count >= 0),

    failure_reason TEXT,

    CHECK (
        scan_status <> 'COMPLETED'
        OR (
            completed_at IS NOT NULL
            AND decision IS NOT NULL
        )
    ),

    CHECK (
        completed_at IS NULL
        OR started_at IS NULL
        OR completed_at >= started_at
    )
);

CREATE INDEX idx_scans_image
ON image_scans(image_id, started_at DESC);

CREATE INDEX idx_scans_decision
ON image_scans(decision, completed_at DESC);

-- ============================================================================
-- 8. SECRETS DETECTED IN IMAGES
-- ============================================================================

CREATE TABLE image_secrets (
    secret_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    image_id BIGINT NOT NULL
        REFERENCES container_images(image_id)
        ON DELETE CASCADE,

    secret_type VARCHAR(80) NOT NULL,

    file_path TEXT,

    detection_method VARCHAR(100) NOT NULL,

    fingerprint VARCHAR(128),

    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    remediated BOOLEAN NOT NULL DEFAULT FALSE,

    remediated_at TIMESTAMPTZ,

    CHECK (
        (remediated = FALSE AND remediated_at IS NULL)
        OR
        (remediated = TRUE AND remediated_at IS NOT NULL)
    )
);

CREATE INDEX idx_image_secrets_unresolved
ON image_secrets(image_id, detected_at DESC)
WHERE remediated = FALSE;

-- ============================================================================
-- 9. IMAGE PROVENANCE
-- ============================================================================

CREATE TABLE image_provenance (
    provenance_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    image_id BIGINT NOT NULL UNIQUE
        REFERENCES container_images(image_id),

    publisher VARCHAR(200) NOT NULL,

    signature_algorithm VARCHAR(50) NOT NULL,

    signature_reference TEXT NOT NULL,

    attestation_reference TEXT,

    build_pipeline VARCHAR(200) NOT NULL,

    source_revision VARCHAR(100),

    verified BOOLEAN NOT NULL DEFAULT FALSE,

    verified_at TIMESTAMPTZ,

    CHECK (
        verified = FALSE OR verified_at IS NOT NULL
    )
);

-- ============================================================================
-- 10. SECURITY POLICIES
-- ============================================================================

CREATE TABLE security_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    policy_name VARCHAR(150) NOT NULL UNIQUE,

    environment VARCHAR(30) NOT NULL
        CHECK (
            environment IN (
                'DEVELOPMENT',
                'TEST',
                'STAGING',
                'PRODUCTION'
            )
        ),

    maximum_critical INTEGER NOT NULL DEFAULT 0
        CHECK (maximum_critical >= 0),

    maximum_high INTEGER NOT NULL DEFAULT 0
        CHECK (maximum_high >= 0),

    maximum_medium INTEGER NOT NULL DEFAULT 5
        CHECK (maximum_medium >= 0),

    maximum_image_size_mb NUMERIC(12,2) NOT NULL DEFAULT 200
        CHECK (maximum_image_size_mb > 0),

    require_non_root BOOLEAN NOT NULL DEFAULT TRUE,

    forbid_privileged BOOLEAN NOT NULL DEFAULT TRUE,

    forbid_shell BOOLEAN NOT NULL DEFAULT FALSE,

    require_signature BOOLEAN NOT NULL DEFAULT TRUE,

    require_provenance BOOLEAN NOT NULL DEFAULT TRUE,

    require_no_secrets BOOLEAN NOT NULL DEFAULT TRUE,

    block_unknown_severity BOOLEAN NOT NULL DEFAULT TRUE,

    require_fixed_vulnerabilities BOOLEAN NOT NULL DEFAULT FALSE,

    require_runtime_controls BOOLEAN NOT NULL DEFAULT TRUE,

    active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_active_policies
ON security_policies(environment)
WHERE active = TRUE;

-- ============================================================================
-- 11. POLICY EVALUATION HISTORY
-- ============================================================================

CREATE TABLE policy_evaluations (
    evaluation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    image_id BIGINT NOT NULL
        REFERENCES container_images(image_id),

    scan_id BIGINT NOT NULL
        REFERENCES image_scans(scan_id),

    policy_id BIGINT NOT NULL
        REFERENCES security_policies(policy_id),

    decision admission_decision NOT NULL,

    evaluation_reason TEXT NOT NULL,

    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_policy_evaluations_image
ON policy_evaluations(image_id, evaluated_at DESC);

-- ============================================================================
-- 12. RUNTIME SECURITY EVENTS
-- ============================================================================

CREATE TABLE runtime_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    image_id BIGINT NOT NULL
        REFERENCES container_images(image_id),

    container_id VARCHAR(150) NOT NULL,

    event_type runtime_event_type NOT NULL,

    process_name VARCHAR(200) NOT NULL,

    user_id INTEGER NOT NULL
        CHECK (user_id >= 0),

    event_details JSONB NOT NULL DEFAULT '{}'::JSONB,

    decision admission_decision NOT NULL,

    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_runtime_events_image
ON runtime_events(image_id, observed_at DESC);

CREATE INDEX idx_runtime_events_denied
ON runtime_events(decision, observed_at DESC)
WHERE decision = 'DENY';

CREATE INDEX idx_runtime_events_details
ON runtime_events USING GIN(event_details);

-- ============================================================================
-- 13. DEPLOYMENT RECORDS
-- ============================================================================

CREATE TABLE deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    image_id BIGINT NOT NULL
        REFERENCES container_images(image_id),

    environment VARCHAR(30) NOT NULL,

    cluster_name VARCHAR(150) NOT NULL,

    namespace_name VARCHAR(150) NOT NULL,

    deployment_decision admission_decision NOT NULL,

    deployed_at TIMESTAMPTZ,

    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    rejection_reason TEXT,

    CHECK (
        deployment_decision <> 'ALLOW'
        OR deployed_at IS NOT NULL
    )
);

CREATE INDEX idx_deployments_environment
ON deployments(environment, requested_at DESC);

-- ============================================================================
-- 14. TRIGGER: VALIDATE IMAGE STATE TRANSITIONS
-- ============================================================================

CREATE OR REPLACE FUNCTION validate_image_state_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.lifecycle = 'RETIRED'
       AND NEW.lifecycle <> 'RETIRED' THEN
        RAISE EXCEPTION 'Retired images cannot be reactivated';
    END IF;

    IF OLD.lifecycle = 'APPROVED'
       AND NEW.lifecycle = 'REGISTERED' THEN
        RAISE EXCEPTION 'Approved image cannot return to registered state';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_image_state_transition
BEFORE UPDATE OF lifecycle ON container_images
FOR EACH ROW
EXECUTE FUNCTION validate_image_state_transition();

-- ============================================================================
-- 15. TRIGGER: MAINTAIN IMAGE LIFECYCLE
-- ============================================================================

CREATE OR REPLACE FUNCTION maintain_image_lifecycle()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.scan_status = 'COMPLETED' THEN
        UPDATE container_images
        SET lifecycle = CASE
            WHEN NEW.decision = 'ALLOW' THEN 'APPROVED'::image_lifecycle
            WHEN NEW.decision = 'DENY' THEN 'BLOCKED'::image_lifecycle
            ELSE 'SCANNED'::image_lifecycle
        END
        WHERE image_id = NEW.image_id
          AND lifecycle <> 'RETIRED';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_scan_lifecycle
AFTER INSERT OR UPDATE OF scan_status, decision ON image_scans
FOR EACH ROW
EXECUTE FUNCTION maintain_image_lifecycle();

-- ============================================================================
-- 16. TRIGGER: PREVENT DEPLOYMENT WITHOUT APPROVAL
-- ============================================================================

CREATE OR REPLACE FUNCTION validate_deployment_admission()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    current_state image_lifecycle;
BEGIN
    SELECT lifecycle
    INTO current_state
    FROM container_images
    WHERE image_id = NEW.image_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Image does not exist';
    END IF;

    IF NEW.deployment_decision = 'ALLOW'
       AND current_state <> 'APPROVED' THEN
        RAISE EXCEPTION
            'Deployment blocked: image is not approved';
    END IF;

    IF NEW.deployment_decision = 'ALLOW'
       AND NEW.deployed_at IS NULL THEN
        RAISE EXCEPTION
            'Approved deployment requires deployed_at';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_deployment_admission
BEFORE INSERT OR UPDATE ON deployments
FOR EACH ROW
EXECUTE FUNCTION validate_deployment_admission();

-- ============================================================================
-- 17. FUNCTION: DETERMINE IMAGE ELIGIBILITY
-- ============================================================================

CREATE OR REPLACE FUNCTION evaluate_image(
    p_image_id BIGINT,
    p_policy_id BIGINT
)
RETURNS admission_decision
LANGUAGE plpgsql
AS $$
DECLARE
    image_record container_images%ROWTYPE;
    policy_record security_policies%ROWTYPE;

    critical_total INTEGER;
    high_total INTEGER;
    medium_total INTEGER;
    unknown_total INTEGER;
    unresolved_secrets INTEGER;

    result admission_decision := 'ALLOW';
BEGIN
    SELECT *
    INTO image_record
    FROM container_images
    WHERE image_id = p_image_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Image not found: %', p_image_id;
    END IF;

    SELECT *
    INTO policy_record
    FROM security_policies
    WHERE policy_id = p_policy_id
      AND active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active policy not found: %', p_policy_id;
    END IF;

    SELECT
        COUNT(*) FILTER (
            WHERE v.severity = 'CRITICAL'
        )::INTEGER,

        COUNT(*) FILTER (
            WHERE v.severity = 'HIGH'
        )::INTEGER,

        COUNT(*) FILTER (
            WHERE v.severity = 'MEDIUM'
        )::INTEGER,

        COUNT(*) FILTER (
            WHERE v.severity = 'UNKNOWN'
        )::INTEGER

    INTO
        critical_total,
        high_total,
        medium_total,
        unknown_total

    FROM image_vulnerabilities iv

    JOIN vulnerabilities v
      ON v.vulnerability_id = iv.vulnerability_id

    WHERE iv.image_id = p_image_id
      AND iv.resolved = FALSE;

    SELECT COUNT(*)::INTEGER
    INTO unresolved_secrets
    FROM image_secrets
    WHERE image_id = p_image_id
      AND remediated = FALSE;

    IF policy_record.require_non_root
       AND image_record.user_id = 0 THEN
        result := 'DENY';
    END IF;

    IF policy_record.forbid_privileged
       AND image_record.privileged THEN
        result := 'DENY';
    END IF;

    IF policy_record.forbid_shell
       AND image_record.contains_shell THEN
        result := 'REVIEW';
    END IF;

    IF image_record.image_size_mb >
       policy_record.maximum_image_size_mb THEN
        result := 'REVIEW';
    END IF;

    IF policy_record.require_signature
       AND NOT image_record.signature_verified THEN
        result := 'DENY';
    END IF;

    IF policy_record.require_provenance
       AND NOT image_record.provenance_verified THEN
        result := 'DENY';
    END IF;

    IF policy_record.require_no_secrets
       AND unresolved_secrets > 0 THEN
        result := 'DENY';
    END IF;

    IF policy_record.block_unknown_severity
       AND unknown_total > 0 THEN
        result := 'DENY';
    END IF;

    IF policy_record.require_fixed_vulnerabilities
       AND EXISTS (
           SELECT 1
           FROM image_vulnerabilities iv
           JOIN vulnerabilities v
             ON v.vulnerability_id = iv.vulnerability_id
           WHERE iv.image_id = p_image_id
             AND iv.resolved = FALSE
             AND v.fixed_version IS NULL
       ) THEN
        result := 'DENY';
    END IF;

    IF critical_total > policy_record.maximum_critical
       OR high_total > policy_record.maximum_high THEN
        result := 'DENY';
    ELSIF medium_total > policy_record.maximum_medium
       AND result = 'ALLOW' THEN
        result := 'REVIEW';
    END IF;

    RETURN result;
END;
$$;

-- ============================================================================
-- 18. PROCEDURE: COMPLETE AN IMAGE SCAN
-- ============================================================================

CREATE OR REPLACE PROCEDURE complete_image_scan(
    p_scan_id BIGINT,
    p_policy_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    scan_record image_scans%ROWTYPE;

    critical_total INTEGER;
    high_total INTEGER;
    medium_total INTEGER;
    low_total INTEGER;
    unknown_total INTEGER;

    total_count INTEGER;
    final_decision admission_decision;
BEGIN
    SELECT *
    INTO scan_record
    FROM image_scans
    WHERE scan_id = p_scan_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Scan does not exist';
    END IF;

    IF scan_record.scan_status <> 'RUNNING' THEN
        RAISE EXCEPTION 'Only running scans can be completed';
    END IF;

    SELECT
        COUNT(*) FILTER (WHERE v.severity = 'CRITICAL')::INTEGER,
        COUNT(*) FILTER (WHERE v.severity = 'HIGH')::INTEGER,
        COUNT(*) FILTER (WHERE v.severity = 'MEDIUM')::INTEGER,
        COUNT(*) FILTER (WHERE v.severity = 'LOW')::INTEGER,
        COUNT(*) FILTER (WHERE v.severity = 'UNKNOWN')::INTEGER

    INTO
        critical_total,
        high_total,
        medium_total,
        low_total,
        unknown_total

    FROM image_vulnerabilities iv

    JOIN vulnerabilities v
      ON v.vulnerability_id = iv.vulnerability_id

    WHERE iv.image_id = scan_record.image_id
      AND iv.resolved = FALSE;

    total_count :=
        critical_total +
        high_total +
        medium_total +
        low_total +
        unknown_total;

    final_decision := evaluate_image(
        scan_record.image_id,
        p_policy_id
    );

    UPDATE image_scans
    SET
        scan_status = 'COMPLETED',
        completed_at = NOW(),
        decision = final_decision,
        total_vulnerabilities = total_count,
        critical_count = critical_total,
        high_count = high_total,
        medium_count = medium_total,
        low_count = low_total,
        unknown_count = unknown_total
    WHERE scan_id = p_scan_id;

    INSERT INTO policy_evaluations (
        image_id,
        scan_id,
        policy_id,
        decision,
        evaluation_reason
    )
    VALUES (
        scan_record.image_id,
        p_scan_id,
        p_policy_id,
        final_decision,
        'Completed vulnerability and image configuration assessment'
    );
END;
$$;

-- ============================================================================
-- 19. VIEW: IMAGE SECURITY POSTURE
-- ============================================================================

CREATE OR REPLACE VIEW image_security_posture AS
SELECT
    i.image_id,
    r.repository_name,
    i.image_name,
    i.image_tag,
    i.image_digest,
    i.base_image,
    i.image_size_mb,
    i.user_id,
    i.lifecycle,

    COUNT(DISTINCT iv.finding_id) FILTER (
        WHERE iv.resolved = FALSE
    ) AS unresolved_findings,

    COUNT(DISTINCT iv.finding_id) FILTER (
        WHERE v.severity = 'CRITICAL'
          AND iv.resolved = FALSE
    ) AS critical_findings,

    COUNT(DISTINCT iv.finding_id) FILTER (
        WHERE v.severity = 'HIGH'
          AND iv.resolved = FALSE
    ) AS high_findings,

    COUNT(DISTINCT s.secret_id) FILTER (
        WHERE s.remediated = FALSE
    ) AS unresolved_secrets,

    i.signature_verified,
    i.provenance_verified

FROM container_images i

JOIN repositories r
  ON r.repository_id = i.repository_id

LEFT JOIN image_vulnerabilities iv
  ON iv.image_id = i.image_id

LEFT JOIN vulnerabilities v
  ON v.vulnerability_id = iv.vulnerability_id

LEFT JOIN image_secrets s
  ON s.image_id = i.image_id

GROUP BY
    i.image_id,
    r.repository_name,
    i.image_name,
    i.image_tag,
    i.image_digest,
    i.base_image,
    i.image_size_mb,
    i.user_id,
    i.lifecycle,
    i.signature_verified,
    i.provenance_verified;

-- ============================================================================
-- 20. VIEW: RUNTIME SECURITY REPORT
-- ============================================================================

CREATE OR REPLACE VIEW runtime_security_report AS
SELECT
    i.image_name,
    re.container_id,
    re.event_type,
    re.process_name,
    re.user_id,
    re.decision,
    COUNT(*) AS event_count,
    MAX(re.observed_at) AS last_observed

FROM runtime_events re

JOIN container_images i
  ON i.image_id = re.image_id

GROUP BY
    i.image_name,
    re.container_id,
    re.event_type,
    re.process_name,
    re.user_id,
    re.decision;

-- ============================================================================
-- 21. SAMPLE REPOSITORIES
-- ============================================================================

INSERT INTO repositories (
    repository_name,
    registry_name,
    owner_team,
    environment
)
VALUES
(
    'payments-api',
    'registry.internal',
    'PAYMENTS',
    'PRODUCTION'
),
(
    'inventory-api',
    'registry.internal',
    'INVENTORY',
    'STAGING'
),
(
    'legacy-worker',
    'registry.internal',
    'PLATFORM',
    'DEVELOPMENT'
);

-- ============================================================================
-- 22. SAMPLE IMAGES
-- ============================================================================

INSERT INTO container_images (
    repository_id,
    image_name,
    image_tag,
    image_digest,
    base_image,
    image_size_mb,
    user_id,
    contains_shell,
    privileged,
    signature_verified,
    provenance_verified
)
SELECT
    repository_id,
    'payments-api',
    '1.4.2',
    'sha256:' || repeat('a', 64),
    'distroless/python3',
    48,
    10001,
    FALSE,
    FALSE,
    TRUE,
    TRUE
FROM repositories
WHERE repository_name = 'payments-api';

INSERT INTO container_images (
    repository_id,
    image_name,
    image_tag,
    image_digest,
    base_image,
    image_size_mb,
    user_id,
    contains_shell,
    privileged,
    signature_verified,
    provenance_verified
)
SELECT
    repository_id,
    'inventory-api',
    '2.0.0',
    'sha256:' || repeat('b', 64),
    'minimal-runtime',
    75,
    10002,
    FALSE,
    FALSE,
    TRUE,
    TRUE
FROM repositories
WHERE repository_name = 'inventory-api';

INSERT INTO container_images (
    repository_id,
    image_name,
    image_tag,
    image_digest,
    base_image,
    image_size_mb,
    user_id,
    contains_shell,
    privileged,
    signature_verified,
    provenance_verified
)
SELECT
    repository_id,
    'legacy-worker',
    'latest',
    'sha256:' || repeat('c', 64),
    'generic-linux',
    450,
    0,
    TRUE,
    TRUE,
    FALSE,
    FALSE
FROM repositories
WHERE repository_name = 'legacy-worker';

-- ============================================================================
-- 23. SAMPLE PACKAGES
-- ============================================================================

INSERT INTO image_packages (
    image_id,
    package_name,
    installed_version,
    package_type
)
SELECT image_id, 'example-library', '1.0.0', 'APPLICATION'
FROM container_images
WHERE image_name = 'payments-api';

INSERT INTO image_packages (
    image_id,
    package_name,
    installed_version,
    package_type
)
SELECT image_id, 'runtime-library', '2.0.0', 'LIBRARY'
FROM container_images
WHERE image_name = 'inventory-api';

INSERT INTO image_packages (
    image_id,
    package_name,
    installed_version,
    package_type
)
SELECT image_id, 'unsafe-package', '1.0.0', 'OS'
FROM container_images
WHERE image_name = 'legacy-worker';

-- ============================================================================
-- 24. SAMPLE CVE RECORDS
-- ============================================================================

INSERT INTO vulnerabilities (
    cve_id,
    severity,
    cvss_score,
    description,
    fixed_version,
    exploitable
)
VALUES
(
    'CVE-2024-12345',
    'LOW',
    3.2,
    'Example low-severity package vulnerability',
    '1.0.2',
    FALSE
),
(
    'CVE-2024-23456',
    'CRITICAL',
    9.8,
    'Critical remote execution vulnerability',
    '2.0.1',
    TRUE
),
(
    'CVE-2024-34567',
    'HIGH',
    8.1,
    'High-severity runtime vulnerability',
    NULL,
    TRUE
),
(
    'CVE-2024-45678',
    'MEDIUM',
    5.4,
    'Medium-severity library vulnerability',
    '2.1.0',
    FALSE
);

-- ============================================================================
-- 25. ASSOCIATE CVES WITH IMAGE PACKAGES
-- ============================================================================

INSERT INTO image_vulnerabilities (
    image_id,
    package_id,
    vulnerability_id
)
SELECT
    i.image_id,
    p.package_id,
    v.vulnerability_id

FROM container_images i

JOIN image_packages p
  ON p.image_id = i.image_id

JOIN vulnerabilities v
  ON (
      i.image_name = 'payments-api'
      AND v.cve_id = 'CVE-2024-12345'
      AND p.package_name = 'example-library'
  )
  OR (
      i.image_name = 'legacy-worker'
      AND v.cve_id = 'CVE-2024-23456'
      AND p.package_name = 'unsafe-package'
  );

-- ============================================================================
-- 26. SAMPLE SECRETS
-- ============================================================================

INSERT INTO image_secrets (
    image_id,
    secret_type,
    file_path,
    detection_method,
    fingerprint
)
SELECT
    image_id,
    'PRIVATE_KEY',
    '/app/config/credentials.pem',
    'LAYER_SCAN',
    'sha256-secret-fingerprint'
FROM container_images
WHERE image_name = 'legacy-worker';

-- ============================================================================
-- 27. SAMPLE PROVENANCE
-- ============================================================================

INSERT INTO image_provenance (
    image_id,
    publisher,
    signature_algorithm,
    signature_reference,
    attestation_reference,
    build_pipeline,
    source_revision,
    verified,
    verified_at
)
SELECT
    image_id,
    'internal-build-system',
    'ED25519',
    'signature://payments-api/1.4.2',
    'attestation://payments-api/1.4.2',
    'payments-ci',
    'a1b2c3d4',
    TRUE,
    NOW()
FROM container_images
WHERE image_name = 'payments-api';

INSERT INTO image_provenance (
    image_id,
    publisher,
    signature_algorithm,
    signature_reference,
    attestation_reference,
    build_pipeline,
    source_revision,
    verified,
    verified_at
)
SELECT
    image_id,
    'internal-build-system',
    'ED25519',
    'signature://inventory-api/2.0.0',
    'attestation://inventory-api/2.0.0',
    'inventory-ci',
    'e5f6a7b8',
    TRUE,
    NOW()
FROM container_images
WHERE image_name = 'inventory-api';

-- ============================================================================
-- 28. SAMPLE SECURITY POLICIES
-- ============================================================================

INSERT INTO security_policies (
    policy_name,
    environment,
    maximum_critical,
    maximum_high,
    maximum_medium,
    maximum_image_size_mb,
    require_non_root,
    forbid_privileged,
    forbid_shell,
    require_signature,
    require_provenance,
    require_no_secrets,
    block_unknown_severity
)
VALUES
(
    'production-strict',
    'PRODUCTION',
    0,
    0,
    3,
    100,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    TRUE
),
(
    'staging-standard',
    'STAGING',
    0,
    1,
    5,
    200,
    TRUE,
    TRUE,
    FALSE,
    TRUE,
    TRUE,
    TRUE,
    TRUE
),
(
    'development-observe',
    'DEVELOPMENT',
    0,
    3,
    10,
    500,
    TRUE,
    TRUE,
    FALSE,
    FALSE,
    FALSE,
    TRUE,
    TRUE
);

-- ============================================================================
-- 29. SAMPLE SCAN RECORDS
-- ============================================================================

INSERT INTO image_scans (
    image_id,
    scanner_name,
    scanner_version,
    scan_status,
    started_at
)
SELECT
    image_id,
    'container-vulnerability-scanner',
    '2.5.0',
    'RUNNING',
    NOW()
FROM container_images
WHERE image_name IN (
    'payments-api',
    'inventory-api',
    'legacy-worker'
);

-- ============================================================================
-- 30. COMPLETE SCANS USING TRANSACTIONAL PROCEDURE
-- ============================================================================

DO $$
DECLARE
    scan_record RECORD;
    policy_record RECORD;
BEGIN
    FOR scan_record IN
        SELECT s.scan_id, i.image_name
        FROM image_scans s
        JOIN container_images i
          ON i.image_id = s.image_id
        WHERE s.scan_status = 'RUNNING'
    LOOP
        SELECT policy_id
        INTO policy_record
        FROM security_policies
        WHERE environment = CASE scan_record.image_name
            WHEN 'payments-api' THEN 'PRODUCTION'
            WHEN 'inventory-api' THEN 'STAGING'
            ELSE 'DEVELOPMENT'
        END
        AND active = TRUE
        LIMIT 1;

        CALL complete_image_scan(
            scan_record.scan_id,
            policy_record.policy_id
        );
    END LOOP;
END;
$$;

COMMIT;

-- ============================================================================
-- 31. RETRIEVAL: IMAGE INVENTORY
-- ============================================================================

SELECT
    repository_name,
    image_name,
    image_tag,
    image_digest,
    base_image,
    image_size_mb,
    user_id,
    lifecycle
FROM image_security_posture
ORDER BY repository_name, image_name;

-- ============================================================================
-- 32. RETRIEVAL: UNRESOLVED VULNERABILITIES
-- ============================================================================

SELECT
    i.image_name,
    v.cve_id,
    v.severity,
    v.cvss_score,
    p.package_name,
    p.installed_version,
    v.fixed_version,
    v.exploitable
FROM image_vulnerabilities iv
JOIN container_images i
  ON i.image_id = iv.image_id
JOIN vulnerabilities v
  ON v.vulnerability_id = iv.vulnerability_id
JOIN image_packages p
  ON p.package_id = iv.package_id
WHERE iv.resolved = FALSE
ORDER BY
    CASE v.severity
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        WHEN 'LOW' THEN 4
        ELSE 5
    END;

-- ============================================================================
-- 33. VALIDATION: ROOT AND PRIVILEGED IMAGES
-- ============================================================================

SELECT
    image_name,
    user_id,
    privileged,
    CASE
        WHEN user_id = 0 AND privileged THEN 'CRITICAL'
        WHEN user_id = 0 THEN 'HIGH'
        WHEN privileged THEN 'CRITICAL'
        ELSE 'PASS'
    END AS security_result
FROM container_images;

-- ============================================================================
-- 34. VALIDATION: SECRET EXPOSURE
-- ============================================================================

SELECT
    i.image_name,
    s.secret_type,
    s.file_path,
    s.detection_method,
    s.detected_at
FROM image_secrets s
JOIN container_images i
  ON i.image_id = s.image_id
WHERE s.remediated = FALSE;

-- ============================================================================
-- 35. AGGREGATION: VULNERABILITY DISTRIBUTION
-- ============================================================================

SELECT
    i.image_name,
    v.severity,
    COUNT(*) AS vulnerability_count,
    COUNT(*) FILTER (
        WHERE v.exploitable = TRUE
    ) AS exploitable_count
FROM image_vulnerabilities iv
JOIN container_images i
  ON i.image_id = iv.image_id
JOIN vulnerabilities v
  ON v.vulnerability_id = iv.vulnerability_id
WHERE iv.resolved = FALSE
GROUP BY i.image_name, v.severity
ORDER BY i.image_name, v.severity;

-- ============================================================================
-- 36. EVALUATION: DEPLOYMENT ELIGIBILITY
-- ============================================================================

SELECT
    i.image_name,
    p.policy_name,
    evaluate_image(i.image_id, p.policy_id) AS admission_decision
FROM container_images i
JOIN repositories r
  ON r.repository_id = i.repository_id
JOIN security_policies p
  ON p.environment = r.environment
WHERE p.active = TRUE;

-- ============================================================================
-- 37. WORKFLOW: DEPLOY APPROVED IMAGE
-- ============================================================================

DO $$
DECLARE
    selected_image_id BIGINT;
    selected_policy_id BIGINT;
    selected_decision admission_decision;
BEGIN
    SELECT i.image_id, p.policy_id
    INTO selected_image_id, selected_policy_id
    FROM container_images i
    JOIN repositories r
      ON r.repository_id = i.repository_id
    JOIN security_policies p
      ON p.environment = r.environment
    WHERE i.image_name = 'payments-api'
      AND p.active = TRUE
    LIMIT 1;

    selected_decision := evaluate_image(
        selected_image_id,
        selected_policy_id
    );

    IF selected_decision <> 'ALLOW' THEN
        INSERT INTO deployments (
            image_id,
            environment,
            cluster_name,
            namespace_name,
            deployment_decision,
            rejection_reason
        )
        VALUES (
            selected_image_id,
            'PRODUCTION',
            'production-cluster',
            'payments',
            selected_decision,
            'Image failed deployment eligibility evaluation'
        );

    ELSE
        INSERT INTO deployments (
            image_id,
            environment,
            cluster_name,
            namespace_name,
            deployment_decision,
            deployed_at
        )
        VALUES (
            selected_image_id,
            'PRODUCTION',
            'production-cluster',
            'payments',
            'ALLOW',
            NOW()
        );
    END IF;
END;
$$;

-- ============================================================================
-- 38. REPORTING: IMAGE SECURITY POSTURE
-- ============================================================================

SELECT
    repository_name,
    image_name,
    image_tag,
    image_size_mb,
    lifecycle,
    critical_findings,
    high_findings,
    unresolved_secrets,
    signature_verified,
    provenance_verified
FROM image_security_posture
ORDER BY
    critical_findings DESC,
    high_findings DESC,
    unresolved_secrets DESC;

-- ============================================================================
-- 39. REPORTING: SCAN HISTORY
-- ============================================================================

SELECT
    i.image_name,
    s.scanner_name,
    s.scanner_version,
    s.scan_status,
    s.total_vulnerabilities,
    s.critical_count,
    s.high_count,
    s.medium_count,
    s.low_count,
    s.unknown_count,
    s.decision,
    s.completed_at
FROM image_scans s
JOIN container_images i
  ON i.image_id = s.image_id
ORDER BY s.completed_at DESC NULLS LAST;

-- ============================================================================
-- 40. REPORTING: RUNTIME SECURITY VIOLATIONS
-- ============================================================================

SELECT
    image_name,
    container_id,
    event_type,
    process_name,
    user_id,
    decision,
    event_count,
    last_observed
FROM runtime_security_report
WHERE decision IN ('DENY', 'REVIEW')
ORDER BY last_observed DESC;

-- ============================================================================
-- 41. REPORTING: DEPLOYMENT REJECTIONS
-- ============================================================================

SELECT
    d.deployment_id,
    i.image_name,
    d.environment,
    d.cluster_name,
    d.namespace_name,
    d.deployment_decision,
    d.rejection_reason,
    d.requested_at
FROM deployments d
JOIN container_images i
  ON i.image_id = d.image_id
WHERE d.deployment_decision <> 'ALLOW'
ORDER BY d.requested_at DESC;

-- ============================================================================
-- 42. CTE: PRIORITIZED IMAGE REMEDIATION
-- ============================================================================

WITH vulnerability_summary AS (
    SELECT
        i.image_id,
        i.image_name,
        COUNT(*) FILTER (
            WHERE v.severity = 'CRITICAL'
        ) AS critical_count,
        COUNT(*) FILTER (
            WHERE v.severity = 'HIGH'
        ) AS high_count,
        COUNT(*) FILTER (
            WHERE v.exploitable = TRUE
        ) AS exploitable_count
    FROM container_images i
    LEFT JOIN image_vulnerabilities iv
      ON iv.image_id = i.image_id
     AND iv.resolved = FALSE
    LEFT JOIN vulnerabilities v
      ON v.vulnerability_id = iv.vulnerability_id
    GROUP BY i.image_id, i.image_name
)
SELECT
    image_name,
    critical_count,
    high_count,
    exploitable_count,
    CASE
        WHEN critical_count > 0 THEN 'IMMEDIATE'
        WHEN exploitable_count > 0 THEN 'URGENT'
        WHEN high_count > 0 THEN 'HIGH_PRIORITY'
        ELSE 'ROUTINE'
    END AS remediation_priority
FROM vulnerability_summary
ORDER BY
    critical_count DESC,
    exploitable_count DESC,
    high_count DESC;

-- ============================================================================
-- 43. TRANSACTION EXAMPLE: REMEDIATE A FINDING
-- ============================================================================

BEGIN;

UPDATE image_vulnerabilities
SET
    resolved = TRUE,
    resolved_at = NOW()
WHERE finding_id = (
    SELECT finding_id
    FROM image_vulnerabilities
    ORDER BY finding_id
    LIMIT 1
)
AND resolved = FALSE;

COMMIT;

-- ============================================================================
-- 44. FINAL SECURITY DASHBOARD
-- ============================================================================

SELECT
    COUNT(*) AS total_images,

    COUNT(*) FILTER (
        WHERE lifecycle = 'APPROVED'
    ) AS approved_images,

    COUNT(*) FILTER (
        WHERE lifecycle = 'BLOCKED'
    ) AS blocked_images,

    COUNT(*) FILTER (
        WHERE user_id = 0
    ) AS root_images,

    COUNT(*) FILTER (
        WHERE privileged = TRUE
    ) AS privileged_images,

    COUNT(*) FILTER (
        WHERE signature_verified = FALSE
    ) AS unsigned_images

FROM container_images;
