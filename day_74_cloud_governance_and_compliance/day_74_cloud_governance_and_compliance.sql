/*
===============================================================================
CLOUD GOVERNANCE AND COMPLIANCE MANAGEMENT DATABASE
===============================================================================

PostgreSQL 14+

Implements:
- Cloud provider and resource inventory
- Resource ownership and classification
- Governance policies
- Regulatory frameworks and controls
- Data residency requirements
- Policy evaluation
- Compliance findings
- Remediation workflows
- Approval records
- Audit events
- Compliance reporting
- Eligibility determination

The schema separates policy definitions, assessment results,
regulatory obligations and operational audit history.
===============================================================================
*/

BEGIN;

CREATE SCHEMA IF NOT EXISTS cloud_governance;

SET search_path TO cloud_governance, public;

-- ============================================================
-- ENUMERATED DOMAIN TYPES
-- ============================================================

DO $$
BEGIN
    CREATE TYPE resource_type AS ENUM (
        'STORAGE',
        'DATABASE',
        'COMPUTE',
        'NETWORK'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE data_classification AS ENUM (
        'PUBLIC',
        'INTERNAL',
        'CONFIDENTIAL',
        'RESTRICTED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE severity_level AS ENUM (
        'LOW',
        'MEDIUM',
        'HIGH',
        'CRITICAL'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE compliance_status AS ENUM (
        'COMPLIANT',
        'NON_COMPLIANT',
        'NOT_APPLICABLE'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE remediation_status AS ENUM (
        'OPEN',
        'IN_PROGRESS',
        'PENDING_APPROVAL',
        'APPROVED',
        'REJECTED',
        'RESOLVED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE audit_action AS ENUM (
        'RESOURCE_REGISTERED',
        'POLICY_EVALUATED',
        'VIOLATION_DETECTED',
        'REMEDIATION_CREATED',
        'REMEDIATION_APPROVED',
        'REMEDIATION_REJECTED',
        'REMEDIATION_COMPLETED',
        'RESOURCE_UPDATED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

-- ============================================================
-- ORGANIZATIONAL IDENTITY
-- ============================================================

CREATE TABLE IF NOT EXISTS organizations (
    organization_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    organization_name VARCHAR(200) NOT NULL UNIQUE,

    industry VARCHAR(100) NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS governance_users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),

    username VARCHAR(100) NOT NULL,

    role_name VARCHAR(50) NOT NULL,

    active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (organization_id, username),

    CHECK (
        role_name IN (
            'CLOUD_ADMIN',
            'SECURITY_ADMIN',
            'COMPLIANCE_OFFICER',
            'RESOURCE_OWNER',
            'AUDITOR',
            'VIEWER'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_governance_users_role
ON governance_users(role_name, active);

-- ============================================================
-- CLOUD PROVIDERS
-- ============================================================

CREATE TABLE IF NOT EXISTS cloud_providers (
    provider_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    provider_name VARCHAR(100) NOT NULL UNIQUE,

    active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- CLOUD RESOURCE INVENTORY
-- ============================================================

CREATE TABLE IF NOT EXISTS cloud_resources (
    resource_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),

    provider_id BIGINT NOT NULL
        REFERENCES cloud_providers(provider_id),

    owner_id BIGINT NOT NULL
        REFERENCES governance_users(user_id),

    resource_identifier VARCHAR(255) NOT NULL UNIQUE,

    resource_name VARCHAR(200) NOT NULL,

    resource_type resource_type NOT NULL,

    classification data_classification NOT NULL,

    cloud_region VARCHAR(100) NOT NULL,

    encrypted_at_rest BOOLEAN NOT NULL DEFAULT FALSE,

    encrypted_in_transit BOOLEAN NOT NULL DEFAULT FALSE,

    public_access_enabled BOOLEAN NOT NULL DEFAULT FALSE,

    backup_enabled BOOLEAN NOT NULL DEFAULT FALSE,

    logging_enabled BOOLEAN NOT NULL DEFAULT FALSE,

    deletion_protected BOOLEAN NOT NULL DEFAULT FALSE,

    tags JSONB NOT NULL DEFAULT '{}'::JSONB,

    active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        organization_id,
        resource_identifier
    ),

    CHECK (LENGTH(TRIM(resource_name)) > 0),

    CHECK (LENGTH(TRIM(cloud_region)) > 0),

    CHECK (jsonb_typeof(tags) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_resources_organization
ON cloud_resources(organization_id);

CREATE INDEX IF NOT EXISTS idx_resources_classification
ON cloud_resources(classification);

CREATE INDEX IF NOT EXISTS idx_resources_region
ON cloud_resources(cloud_region);

CREATE INDEX IF NOT EXISTS idx_resources_provider_region
ON cloud_resources(provider_id, cloud_region);

CREATE INDEX IF NOT EXISTS idx_resources_active
ON cloud_resources(active)
WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS idx_resources_tags
ON cloud_resources USING GIN(tags);

-- ============================================================
-- REGULATORY FRAMEWORKS
-- ============================================================

CREATE TABLE IF NOT EXISTS regulatory_frameworks (
    framework_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    framework_code VARCHAR(50) NOT NULL UNIQUE,

    framework_name VARCHAR(200) NOT NULL,

    description TEXT NOT NULL,

    jurisdiction VARCHAR(100) NOT NULL,

    version VARCHAR(50) NOT NULL,

    effective_date DATE,

    active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Regulatory controls are distinct from internal policies.
-- They describe external obligations mapped to cloud operations.

CREATE TABLE IF NOT EXISTS regulatory_controls (
    control_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    framework_id BIGINT NOT NULL
        REFERENCES regulatory_frameworks(framework_id),

    control_code VARCHAR(100) NOT NULL,

    control_name VARCHAR(200) NOT NULL,

    control_description TEXT NOT NULL,

    mandatory BOOLEAN NOT NULL DEFAULT TRUE,

    UNIQUE(framework_id, control_code)
);

-- ============================================================
-- DATA RESIDENCY REQUIREMENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS residency_rules (
    residency_rule_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),

    framework_id BIGINT
        REFERENCES regulatory_frameworks(framework_id),

    rule_name VARCHAR(200) NOT NULL,

    classification data_classification NOT NULL,

    permitted_regions TEXT[] NOT NULL,

    prohibited_regions TEXT[] NOT NULL DEFAULT '{}',

    effective_from DATE NOT NULL DEFAULT CURRENT_DATE,

    effective_until DATE,

    active BOOLEAN NOT NULL DEFAULT TRUE,

    CHECK (CARDINALITY(permitted_regions) > 0),

    CHECK (
        effective_until IS NULL
        OR effective_until >= effective_from
    )
);

CREATE INDEX IF NOT EXISTS idx_residency_active
ON residency_rules(organization_id, classification, active);

-- ============================================================
-- GOVERNANCE POLICIES
-- ============================================================

CREATE TABLE IF NOT EXISTS governance_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),

    policy_code VARCHAR(100) NOT NULL,

    policy_name VARCHAR(200) NOT NULL,

    description TEXT NOT NULL,

    severity severity_level NOT NULL,

    require_encryption BOOLEAN NOT NULL DEFAULT FALSE,

    prohibit_public_access BOOLEAN NOT NULL DEFAULT FALSE,

    require_backup BOOLEAN NOT NULL DEFAULT FALSE,

    require_logging BOOLEAN NOT NULL DEFAULT FALSE,

    permitted_regions TEXT[] NOT NULL DEFAULT '{}',

    applicable_classifications data_classification[]
        NOT NULL DEFAULT '{}',

    active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(organization_id, policy_code)
);

CREATE INDEX IF NOT EXISTS idx_policy_active
ON governance_policies(organization_id, active);

-- ============================================================
-- FRAMEWORK-TO-POLICY MAPPING
-- ============================================================

CREATE TABLE IF NOT EXISTS policy_control_mappings (
    mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    policy_id BIGINT NOT NULL
        REFERENCES governance_policies(policy_id),

    control_id BIGINT NOT NULL
        REFERENCES regulatory_controls(control_id),

    mapping_rationale TEXT NOT NULL,

    UNIQUE(policy_id, control_id)
);

-- ============================================================
-- ASSESSMENT RUNS
-- ============================================================

CREATE TABLE IF NOT EXISTS assessment_runs (
    assessment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),

    initiated_by BIGINT NOT NULL
        REFERENCES governance_users(user_id),

    assessment_type VARCHAR(50) NOT NULL,

    assessment_status VARCHAR(30) NOT NULL DEFAULT 'COMPLETED',

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    completed_at TIMESTAMPTZ,

    CHECK (
        assessment_type IN (
            'FULL',
            'RESOURCE',
            'POLICY',
            'RESIDENCY',
            'FRAMEWORK'
        )
    ),

    CHECK (
        assessment_status IN (
            'RUNNING',
            'COMPLETED',
            'FAILED',
            'CANCELLED'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_assessment_runs_org
ON assessment_runs(organization_id, started_at DESC);

-- ============================================================
-- POLICY EVALUATION RESULTS
-- ============================================================

CREATE TABLE IF NOT EXISTS policy_evaluations (
    evaluation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    assessment_id BIGINT NOT NULL
        REFERENCES assessment_runs(assessment_id),

    resource_id BIGINT NOT NULL
        REFERENCES cloud_resources(resource_id),

    policy_id BIGINT NOT NULL
        REFERENCES governance_policies(policy_id),

    status compliance_status NOT NULL,

    severity severity_level NOT NULL,

    violation_details JSONB NOT NULL DEFAULT '[]'::JSONB,

    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(
        assessment_id,
        resource_id,
        policy_id
    ),

    CHECK (
        jsonb_typeof(violation_details) = 'array'
    )
);

CREATE INDEX IF NOT EXISTS idx_evaluations_resource
ON policy_evaluations(resource_id, evaluated_at DESC);

CREATE INDEX IF NOT EXISTS idx_evaluations_status
ON policy_evaluations(status, severity);

CREATE INDEX IF NOT EXISTS idx_evaluations_assessment
ON policy_evaluations(assessment_id);

-- ============================================================
-- RESIDENCY EVALUATION RESULTS
-- ============================================================

CREATE TABLE IF NOT EXISTS residency_evaluations (
    residency_evaluation_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    assessment_id BIGINT NOT NULL
        REFERENCES assessment_runs(assessment_id),

    resource_id BIGINT NOT NULL
        REFERENCES cloud_resources(resource_id),

    residency_rule_id BIGINT NOT NULL
        REFERENCES residency_rules(residency_rule_id),

    status compliance_status NOT NULL,

    evaluated_region VARCHAR(100) NOT NULL,

    evaluation_details JSONB NOT NULL DEFAULT '{}'::JSONB,

    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(
        assessment_id,
        resource_id,
        residency_rule_id
    ),

    CHECK (
        jsonb_typeof(evaluation_details) = 'object'
    )
);

CREATE INDEX IF NOT EXISTS idx_residency_evaluation_status
ON residency_evaluations(status, resource_id);

-- ============================================================
-- COMPLIANCE FINDINGS
-- ============================================================

CREATE TABLE IF NOT EXISTS compliance_findings (
    finding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    evaluation_id BIGINT NOT NULL
        REFERENCES policy_evaluations(evaluation_id),

    finding_code VARCHAR(100) NOT NULL,

    finding_description TEXT NOT NULL,

    severity severity_level NOT NULL,

    remediation_state remediation_status NOT NULL DEFAULT 'OPEN',

    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_findings_open
ON compliance_findings(severity, detected_at DESC)
WHERE remediation_state NOT IN (
    'RESOLVED',
    'REJECTED'
);

-- ============================================================
-- REMEDIATION WORKFLOW
-- ============================================================

CREATE TABLE IF NOT EXISTS remediation_requests (
    remediation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    finding_id BIGINT NOT NULL
        REFERENCES compliance_findings(finding_id),

    requested_by BIGINT NOT NULL
        REFERENCES governance_users(user_id),

    assigned_to BIGINT
        REFERENCES governance_users(user_id),

    remediation_description TEXT NOT NULL,

    proposed_changes JSONB NOT NULL,

    status remediation_status NOT NULL DEFAULT 'OPEN',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (
        jsonb_typeof(proposed_changes) = 'object'
    )
);

CREATE INDEX IF NOT EXISTS idx_remediation_status
ON remediation_requests(status, created_at);

-- ============================================================
-- REMEDIATION APPROVALS
-- ============================================================

CREATE TABLE IF NOT EXISTS remediation_approvals (
    approval_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    remediation_id BIGINT NOT NULL
        REFERENCES remediation_requests(remediation_id),

    reviewer_id BIGINT NOT NULL
        REFERENCES governance_users(user_id),

    approved BOOLEAN NOT NULL,

    justification TEXT NOT NULL,

    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(remediation_id, reviewer_id)
);

-- ============================================================
-- AUDIT EVENT TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_events (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),

    actor_id BIGINT
        REFERENCES governance_users(user_id),

    action audit_action NOT NULL,

    resource_id BIGINT
        REFERENCES cloud_resources(resource_id),

    event_details JSONB NOT NULL DEFAULT '{}'::JSONB,

    previous_hash TEXT NOT NULL,

    event_hash TEXT NOT NULL,

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (jsonb_typeof(event_details) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_audit_org_time
ON audit_events(organization_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_resource
ON audit_events(resource_id, occurred_at DESC);

-- ============================================================
-- AUDIT CHAIN TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION cloud_governance.audit_chain_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    previous_event_hash TEXT;
    canonical_payload TEXT;
BEGIN

    /*
     * Serialize chain appends within an organization.
     * This avoids concurrent events selecting the same predecessor.
     */

    PERFORM pg_advisory_xact_lock(NEW.organization_id);

    SELECT event_hash
    INTO previous_event_hash
    FROM cloud_governance.audit_events
    WHERE organization_id = NEW.organization_id
    ORDER BY audit_id DESC
    LIMIT 1;

    NEW.previous_hash := COALESCE(
        previous_event_hash,
        'GENESIS'
    );

    canonical_payload := jsonb_build_object(
        'organization_id', NEW.organization_id,
        'actor_id', NEW.actor_id,
        'action', NEW.action::TEXT,
        'resource_id', NEW.resource_id,
        'event_details', NEW.event_details,
        'occurred_at', NEW.occurred_at,
        'previous_hash', NEW.previous_hash
    )::TEXT;

    NEW.event_hash := encode(
        digest(canonical_payload, 'sha256'),
        'hex'
    );

    RETURN NEW;
END;
$$;

-- pgcrypto supplies SHA-256.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP TRIGGER IF EXISTS trg_audit_chain
ON audit_events;

CREATE TRIGGER trg_audit_chain
BEFORE INSERT ON audit_events
FOR EACH ROW
EXECUTE FUNCTION cloud_governance.audit_chain_trigger();

-- ============================================================
-- AUDIT IMMUTABILITY
-- ============================================================

CREATE OR REPLACE FUNCTION prevent_audit_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'Audit events cannot be updated or deleted.';
END;
$$;

DROP TRIGGER IF EXISTS trg_prevent_audit_update
ON audit_events;

CREATE TRIGGER trg_prevent_audit_update
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW
EXECUTE FUNCTION prevent_audit_mutation();

-- ============================================================
-- AUTOMATIC RESOURCE UPDATE TIMESTAMP
-- ============================================================

CREATE OR REPLACE FUNCTION update_resource_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_resource_timestamp
ON cloud_resources;

CREATE TRIGGER trg_resource_timestamp
BEFORE UPDATE ON cloud_resources
FOR EACH ROW
EXECUTE FUNCTION update_resource_timestamp();

-- ============================================================
-- POLICY EVALUATION FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION evaluate_cloud_resource(
    p_resource_id BIGINT,
    p_assessment_id BIGINT
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE

    resource_record RECORD;
    policy_record RECORD;

    violations JSONB;
    violation_count INTEGER := 0;

    evaluation_status compliance_status;

    total_evaluations INTEGER := 0;

BEGIN

    SELECT *
    INTO resource_record
    FROM cloud_resources
    WHERE resource_id = p_resource_id
      AND active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Active cloud resource % not found.',
            p_resource_id;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM assessment_runs
        WHERE assessment_id = p_assessment_id
          AND organization_id = resource_record.organization_id
          AND assessment_status = 'RUNNING'
    ) THEN
        RAISE EXCEPTION
            'Assessment is missing, inactive, or belongs to another organization.';
    END IF;

    FOR policy_record IN
        SELECT *
        FROM governance_policies
        WHERE organization_id = resource_record.organization_id
          AND active = TRUE
    LOOP

        violations := '[]'::JSONB;

        IF (
            CARDINALITY(policy_record.applicable_classifications) > 0
            AND NOT (
                resource_record.classification =
                ANY(policy_record.applicable_classifications)
            )
        ) THEN

            evaluation_status := 'NOT_APPLICABLE';

        ELSE

            IF (
                policy_record.require_encryption
                AND NOT resource_record.encrypted_at_rest
            ) THEN
                violations := violations ||
                    '["Encryption at rest is required."]'::JSONB;
            END IF;

            IF (
                policy_record.prohibit_public_access
                AND resource_record.public_access_enabled
            ) THEN
                violations := violations ||
                    '["Public access is prohibited."]'::JSONB;
            END IF;

            IF (
                policy_record.require_backup
                AND NOT resource_record.backup_enabled
            ) THEN
                violations := violations ||
                    '["Backup is required."]'::JSONB;
            END IF;

            IF (
                policy_record.require_logging
                AND NOT resource_record.logging_enabled
            ) THEN
                violations := violations ||
                    '["Logging is required."]'::JSONB;
            END IF;

            IF (
                CARDINALITY(policy_record.permitted_regions) > 0
                AND NOT (
                    resource_record.cloud_region =
                    ANY(policy_record.permitted_regions)
                )
            ) THEN
                violations := violations ||
                    '["Cloud region is not permitted."]'::JSONB;
            END IF;

            evaluation_status :=
                CASE
                    WHEN jsonb_array_length(violations) > 0
                    THEN 'NON_COMPLIANT'::compliance_status
                    ELSE 'COMPLIANT'::compliance_status
                END;

        END IF;

        INSERT INTO policy_evaluations (
            assessment_id,
            resource_id,
            policy_id,
            status,
            severity,
            violation_details
        )
        VALUES (
            p_assessment_id,
            p_resource_id,
            policy_record.policy_id,
            evaluation_status,
            policy_record.severity,
            violations
        )
        ON CONFLICT (
            assessment_id,
            resource_id,
            policy_id
        )
        DO UPDATE SET
            status = EXCLUDED.status,
            severity = EXCLUDED.severity,
            violation_details = EXCLUDED.violation_details,
            evaluated_at = NOW();

        IF evaluation_status = 'NON_COMPLIANT' THEN

            violation_count :=
                violation_count +
                jsonb_array_length(violations);

        END IF;

        total_evaluations := total_evaluations + 1;

    END LOOP;

    RETURN total_evaluations;
END;
$$;

-- ============================================================
-- DATA RESIDENCY EVALUATION FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION evaluate_data_residency(
    p_resource_id BIGINT,
    p_assessment_id BIGINT
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE

    resource_record RECORD;
    rule_record RECORD;

    evaluation_status compliance_status;

    evaluation_count INTEGER := 0;

BEGIN

    SELECT *
    INTO resource_record
    FROM cloud_resources
    WHERE resource_id = p_resource_id
      AND active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Resource not found.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM assessment_runs
        WHERE assessment_id = p_assessment_id
          AND organization_id = resource_record.organization_id
          AND assessment_status = 'RUNNING'
    ) THEN
        RAISE EXCEPTION 'Invalid assessment context.';
    END IF;

    FOR rule_record IN

        SELECT *
        FROM residency_rules
        WHERE organization_id = resource_record.organization_id
          AND classification = resource_record.classification
          AND active = TRUE
          AND CURRENT_DATE >= effective_from
          AND (
              effective_until IS NULL
              OR CURRENT_DATE <= effective_until
          )

    LOOP

        evaluation_status :=
            CASE
                WHEN resource_record.cloud_region =
                    ANY(rule_record.permitted_regions)
                    AND NOT (
                        resource_record.cloud_region =
                        ANY(rule_record.prohibited_regions)
                    )
                THEN 'COMPLIANT'::compliance_status
                ELSE 'NON_COMPLIANT'::compliance_status
            END;

        INSERT INTO residency_evaluations (
            assessment_id,
            resource_id,
            residency_rule_id,
            status,
            evaluated_region,
            evaluation_details
        )
        VALUES (
            p_assessment_id,
            p_resource_id,
            rule_record.residency_rule_id,
            evaluation_status,
            resource_record.cloud_region,
            jsonb_build_object(
                'permitted_regions',
                rule_record.permitted_regions,
                'prohibited_regions',
                rule_record.prohibited_regions
            )
        )
        ON CONFLICT (
            assessment_id,
            resource_id,
            residency_rule_id
        )
        DO UPDATE SET
            status = EXCLUDED.status,
            evaluated_region = EXCLUDED.evaluated_region,
            evaluation_details = EXCLUDED.evaluation_details,
            evaluated_at = NOW();

        evaluation_count := evaluation_count + 1;

    END LOOP;

    RETURN evaluation_count;
END;
$$;

-- ============================================================
-- ASSESSMENT PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE run_resource_assessment(
    p_resource_id BIGINT,
    p_user_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE

    resource_org_id BIGINT;
    new_assessment_id BIGINT;

BEGIN

    SELECT organization_id
    INTO resource_org_id
    FROM cloud_resources
    WHERE resource_id = p_resource_id
      AND active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Resource not found.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM governance_users
        WHERE user_id = p_user_id
          AND organization_id = resource_org_id
          AND active = TRUE
          AND role_name IN (
              'CLOUD_ADMIN',
              'SECURITY_ADMIN',
              'COMPLIANCE_OFFICER',
              'AUDITOR'
          )
    ) THEN
        RAISE EXCEPTION
            'User is not authorized to run assessments.';
    END IF;

    INSERT INTO assessment_runs (
        organization_id,
        initiated_by,
        assessment_type,
        assessment_status
    )
    VALUES (
        resource_org_id,
        p_user_id,
        'RESOURCE',
        'RUNNING'
    )
    RETURNING assessment_id
    INTO new_assessment_id;

    PERFORM evaluate_cloud_resource(
        p_resource_id,
        new_assessment_id
    );

    PERFORM evaluate_data_residency(
        p_resource_id,
        new_assessment_id
    );

    UPDATE assessment_runs
    SET assessment_status = 'COMPLETED',
        completed_at = NOW()
    WHERE assessment_id = new_assessment_id;

    INSERT INTO audit_events (
        organization_id,
        actor_id,
        action,
        resource_id,
        event_details
    )
    VALUES (
        resource_org_id,
        p_user_id,
        'POLICY_EVALUATED',
        p_resource_id,
        jsonb_build_object(
            'assessment_id',
            new_assessment_id
        )
    );

EXCEPTION
    WHEN OTHERS THEN

        RAISE EXCEPTION
            'Resource assessment failed: %',
            SQLERRM;

END;
$$;

-- ============================================================
-- APPROVAL VALIDATION TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION validate_remediation_approval()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    reviewer_role VARCHAR(50);
    requested_user BIGINT;
BEGIN

    SELECT role_name
    INTO reviewer_role
    FROM governance_users
    WHERE user_id = NEW.reviewer_id
      AND active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Reviewer is inactive or does not exist.';
    END IF;

    SELECT requested_by
    INTO requested_user
    FROM remediation_requests
    WHERE remediation_id = NEW.remediation_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Remediation request does not exist.';
    END IF;

    IF requested_user = NEW.reviewer_id THEN
        RAISE EXCEPTION
            'A requester cannot approve their own remediation.';
    END IF;

    IF reviewer_role NOT IN (
        'SECURITY_ADMIN',
        'COMPLIANCE_OFFICER'
    ) THEN
        RAISE EXCEPTION
            'Reviewer lacks remediation approval authority.';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_validate_remediation_approval
ON remediation_approvals;

CREATE TRIGGER trg_validate_remediation_approval
BEFORE INSERT ON remediation_approvals
FOR EACH ROW
EXECUTE FUNCTION validate_remediation_approval();

-- ============================================================
-- REMEDIATION DECISION FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION determine_remediation_decision(
    p_remediation_id BIGINT
)
RETURNS remediation_status
LANGUAGE plpgsql
AS $$
DECLARE

    total_approvals INTEGER;
    rejected_approvals INTEGER;

    result remediation_status;

BEGIN

    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE approved = FALSE
        )
    INTO
        total_approvals,
        rejected_approvals
    FROM remediation_approvals
    WHERE remediation_id = p_remediation_id;

    IF NOT EXISTS (
        SELECT 1
        FROM remediation_requests
        WHERE remediation_id = p_remediation_id
    ) THEN
        RAISE EXCEPTION 'Remediation request not found.';
    END IF;

    IF rejected_approvals > 0 THEN

        result := 'REJECTED';

    ELSIF total_approvals = 0 THEN

        result := 'PENDING_APPROVAL';

    ELSE

        result := 'APPROVED';

    END IF;

    UPDATE remediation_requests
    SET status = result,
        updated_at = NOW()
    WHERE remediation_id = p_remediation_id;

    RETURN result;
END;
$$;

-- ============================================================
-- REPORTING VIEW: CURRENT RESOURCE POSTURE
-- ============================================================

CREATE OR REPLACE VIEW v_resource_posture AS

SELECT

    r.resource_id,

    r.resource_identifier,

    r.resource_name,

    p.provider_name,

    r.resource_type,

    r.classification,

    r.cloud_region,

    r.encrypted_at_rest,

    r.public_access_enabled,

    r.backup_enabled,

    r.logging_enabled,

    u.username AS owner,

    r.active,

    r.updated_at

FROM cloud_resources r

JOIN cloud_providers p
    ON p.provider_id = r.provider_id

JOIN governance_users u
    ON u.user_id = r.owner_id;

-- ============================================================
-- REPORTING VIEW: POLICY COMPLIANCE
-- ============================================================

CREATE OR REPLACE VIEW v_policy_compliance AS

SELECT

    e.assessment_id,

    e.resource_id,

    r.resource_name,

    p.policy_code,

    p.policy_name,

    e.severity,

    e.status,

    e.violation_details,

    e.evaluated_at

FROM policy_evaluations e

JOIN cloud_resources r
    ON r.resource_id = e.resource_id

JOIN governance_policies p
    ON p.policy_id = e.policy_id;

-- ============================================================
-- REPORTING VIEW: OPEN REMEDIATION
-- ============================================================

CREATE OR REPLACE VIEW v_open_remediation AS

SELECT

    rr.remediation_id,

    cf.finding_id,

    cf.severity,

    rr.remediation_description,

    rr.status,

    requester.username AS requested_by,

    assignee.username AS assigned_to,

    rr.created_at

FROM remediation_requests rr

JOIN compliance_findings cf
    ON cf.finding_id = rr.finding_id

JOIN governance_users requester
    ON requester.user_id = rr.requested_by

LEFT JOIN governance_users assignee
    ON assignee.user_id = rr.assigned_to

WHERE rr.status NOT IN (
    'RESOLVED',
    'REJECTED'
);

-- ============================================================
-- REPORTING VIEW: ASSESSMENT SUMMARY
-- ============================================================

CREATE OR REPLACE VIEW v_assessment_summary AS

SELECT

    assessment_id,

    COUNT(*) AS total_evaluations,

    COUNT(*) FILTER (
        WHERE status = 'COMPLIANT'
    ) AS compliant,

    COUNT(*) FILTER (
        WHERE status = 'NON_COMPLIANT'
    ) AS non_compliant,

    COUNT(*) FILTER (
        WHERE status = 'NOT_APPLICABLE'
    ) AS not_applicable,

    ROUND(
        100.0 *
        COUNT(*) FILTER (
            WHERE status = 'COMPLIANT'
        ) /
        NULLIF(
            COUNT(*) FILTER (
                WHERE status <> 'NOT_APPLICABLE'
            ),
            0
        ),
        2
    ) AS compliance_percentage

FROM policy_evaluations

GROUP BY assessment_id;

-- ============================================================
-- SAMPLE ORGANIZATION
-- ============================================================

INSERT INTO organizations (
    organization_name,
    industry
)
VALUES (
    'Example Enterprise',
    'Technology'
)
ON CONFLICT (organization_name) DO NOTHING;

INSERT INTO cloud_providers(provider_name)
VALUES
    ('AWS'),
    ('Azure'),
    ('Google Cloud')
ON CONFLICT (provider_name) DO NOTHING;

INSERT INTO governance_users (
    organization_id,
    username,
    role_name
)
SELECT
    o.organization_id,
    sample.username,
    sample.role_name
FROM organizations o
CROSS JOIN (
    VALUES
        ('cloud-admin', 'CLOUD_ADMIN'),
        ('security-admin', 'SECURITY_ADMIN'),
        ('compliance-officer', 'COMPLIANCE_OFFICER'),
        ('data-owner', 'RESOURCE_OWNER'),
        ('auditor', 'AUDITOR')
) AS sample(username, role_name)
WHERE o.organization_name = 'Example Enterprise'
ON CONFLICT (organization_id, username) DO NOTHING;

-- ============================================================
-- SAMPLE REGULATORY FRAMEWORKS
-- ============================================================

INSERT INTO regulatory_frameworks (
    framework_code,
    framework_name,
    description,
    jurisdiction,
    version,
    effective_date
)
VALUES
(
    'GDPR',
    'General Data Protection Regulation',
    'European Union personal data protection framework.',
    'European Union',
    '2016/679',
    '2018-05-25'
),
(
    'ISO27001',
    'ISO/IEC 27001',
    'Information security management system standard.',
    'International',
    '2022',
    '2022-10-25'
),
(
    'DPDPA',
    'Digital Personal Data Protection Act',
    'Indian personal data protection legislation.',
    'India',
    '2023',
    '2023-08-11'
)
ON CONFLICT (framework_code) DO NOTHING;

INSERT INTO regulatory_controls (
    framework_id,
    control_code,
    control_name,
    control_description
)
SELECT
    framework_id,
    'DATA-PROTECTION-001',
    'Data Protection and Security',
    'Maintain appropriate technical and organizational safeguards.'
FROM regulatory_frameworks
WHERE framework_code = 'ISO27001'
ON CONFLICT (framework_id, control_code) DO NOTHING;

INSERT INTO regulatory_controls (
    framework_id,
    control_code,
    control_name,
    control_description
)
SELECT
    framework_id,
    'PERSONAL-DATA-001',
    'Personal Data Protection',
    'Apply applicable requirements for personal data processing.'
FROM regulatory_frameworks
WHERE framework_code = 'DPDPA'
ON CONFLICT (framework_id, control_code) DO NOTHING;

INSERT INTO regulatory_controls (
    framework_id,
    control_code,
    control_name,
    control_description
)
SELECT
    framework_id,
    'TRANSFER-001',
    'International Data Transfers',
    'Assess applicable restrictions on international data transfers.'
FROM regulatory_frameworks
WHERE framework_code = 'GDPR'
ON CONFLICT (framework_id, control_code) DO NOTHING;

-- ============================================================
-- SAMPLE GOVERNANCE POLICIES
-- ============================================================

INSERT INTO governance_policies (
    organization_id,
    policy_code,
    policy_name,
    description,
    severity,
    require_encryption,
    prohibit_public_access,
    require_backup,
    require_logging,
    permitted_regions,
    applicable_classifications
)
SELECT
    organization_id,
    'ENC-001',
    'Sensitive Data Encryption',
    'Confidential and restricted data must be encrypted at rest.',
    'CRITICAL',
    TRUE,
    FALSE,
    FALSE,
    FALSE,
    '{}',
    ARRAY['CONFIDENTIAL', 'RESTRICTED']::data_classification[]
FROM organizations
WHERE organization_name = 'Example Enterprise'
ON CONFLICT (organization_id, policy_code) DO NOTHING;

INSERT INTO governance_policies (
    organization_id,
    policy_code,
    policy_name,
    description,
    severity,
    prohibit_public_access,
    applicable_classifications
)
SELECT
    organization_id,
    'PUB-001',
    'Prevent Public Data Exposure',
    'Sensitive resources must not permit public access.',
    'CRITICAL',
    TRUE,
    ARRAY['CONFIDENTIAL', 'RESTRICTED']::data_classification[]
FROM organizations
WHERE organization_name = 'Example Enterprise'
ON CONFLICT (organization_id, policy_code) DO NOTHING;

INSERT INTO governance_policies (
    organization_id,
    policy_code,
    policy_name,
    description,
    severity,
    require_backup,
    applicable_classifications
)
SELECT
    organization_id,
    'BKP-001',
    'Restricted Data Backup',
    'Restricted resources require a backup configuration.',
    'HIGH',
    TRUE,
    ARRAY['RESTRICTED']::data_classification[]
FROM organizations
WHERE organization_name = 'Example Enterprise'
ON CONFLICT (organization_id, policy_code) DO NOTHING;

INSERT INTO governance_policies (
    organization_id,
    policy_code,
    policy_name,
    description,
    severity,
    permitted_regions,
    applicable_classifications
)
SELECT
    organization_id,
    'REG-001',
    'Approved Region Deployment',
    'Restricted data must remain in approved Indian regions.',
    'CRITICAL',
    ARRAY['ap-south-1', 'ap-south-2'],
    ARRAY['RESTRICTED']::data_classification[]
FROM organizations
WHERE organization_name = 'Example Enterprise'
ON CONFLICT (organization_id, policy_code) DO NOTHING;

INSERT INTO governance_policies (
    organization_id,
    policy_code,
    policy_name,
    description,
    severity,
    require_logging,
    applicable_classifications
)
SELECT
    organization_id,
    'LOG-001',
    'Security Logging',
    'Restricted resources require enabled security logging.',
    'HIGH',
    TRUE,
    ARRAY['RESTRICTED']::data_classification[]
FROM organizations
WHERE organization_name = 'Example Enterprise'
ON CONFLICT (organization_id, policy_code) DO NOTHING;

-- ============================================================
-- RESIDENCY RULES
-- ============================================================

INSERT INTO residency_rules (
    organization_id,
    framework_id,
    rule_name,
    classification,
    permitted_regions,
    prohibited_regions
)
SELECT
    o.organization_id,
    f.framework_id,
    'Enterprise Restricted Data Residency',
    'RESTRICTED',
    ARRAY['ap-south-1', 'ap-south-2'],
    ARRAY['restricted-region']
FROM organizations o
LEFT JOIN regulatory_frameworks f
    ON f.framework_code = 'DPDPA'
WHERE o.organization_name = 'Example Enterprise'
AND NOT EXISTS (
    SELECT 1
    FROM residency_rules existing
    WHERE existing.organization_id = o.organization_id
      AND existing.rule_name =
          'Enterprise Restricted Data Residency'
);

INSERT INTO residency_rules (
    organization_id,
    framework_id,
    rule_name,
    classification,
    permitted_regions
)
SELECT
    o.organization_id,
    f.framework_id,
    'Enterprise Confidential Data Residency',
    'CONFIDENTIAL',
    ARRAY['ap-south-1', 'ap-south-2']
FROM organizations o
LEFT JOIN regulatory_frameworks f
    ON f.framework_code = 'ISO27001'
WHERE o.organization_name = 'Example Enterprise'
AND NOT EXISTS (
    SELECT 1
    FROM residency_rules existing
    WHERE existing.organization_id = o.organization_id
      AND existing.rule_name =
          'Enterprise Confidential Data Residency'
);

-- ============================================================
-- FRAMEWORK MAPPING
-- ============================================================

INSERT INTO policy_control_mappings (
    policy_id,
    control_id,
    mapping_rationale
)
SELECT
    p.policy_id,
    c.control_id,
    'Internal encryption policy supports the mapped security control.'
FROM governance_policies p
JOIN organizations o
    ON o.organization_id = p.organization_id
JOIN regulatory_frameworks f
    ON f.framework_code = 'ISO27001'
JOIN regulatory_controls c
    ON c.framework_id = f.framework_id
WHERE o.organization_name = 'Example Enterprise'
AND p.policy_code = 'ENC-001'
ON CONFLICT (policy_id, control_id) DO NOTHING;

-- ============================================================
-- SAMPLE CLOUD RESOURCES
-- ============================================================

INSERT INTO cloud_resources (
    organization_id,
    provider_id,
    owner_id,
    resource_identifier,
    resource_name,
    resource_type,
    classification,
    cloud_region,
    encrypted_at_rest,
    encrypted_in_transit,
    public_access_enabled,
    backup_enabled,
    logging_enabled,
    deletion_protected,
    tags
)
SELECT
    o.organization_id,
    p.provider_id,
    u.user_id,
    sample.resource_identifier,
    sample.resource_name,
    sample.resource_type::resource_type,
    sample.classification::data_classification,
    sample.cloud_region,
    sample.encrypted_at_rest,
    sample.encrypted_in_transit,
    sample.public_access_enabled,
    sample.backup_enabled,
    sample.logging_enabled,
    sample.deletion_protected,
    sample.tags::JSONB
FROM organizations o
JOIN cloud_providers p
    ON p.provider_name = 'AWS'
JOIN governance_users u
    ON u.organization_id = o.organization_id
   AND u.username = 'data-owner'
CROSS JOIN (
    VALUES
    (
        'aws:db:customer-001',
        'Customer Production Database',
        'DATABASE',
        'RESTRICTED',
        'ap-south-1',
        FALSE,
        FALSE,
        TRUE,
        FALSE,
        FALSE,
        TRUE,
        '{"environment":"production","team":"data"}'
    ),
    (
        'aws:compute:application-001',
        'Application Compute Server',
        'COMPUTE',
        'INTERNAL',
        'ap-south-1',
        TRUE,
        TRUE,
        FALSE,
        TRUE,
        TRUE,
        FALSE,
        '{"environment":"production","team":"engineering"}'
    ),
    (
        'aws:storage:analytics-001',
        'Analytics Data Storage',
        'STORAGE',
        'RESTRICTED',
        'us-east-1',
        TRUE,
        TRUE,
        FALSE,
        TRUE,
        TRUE,
        TRUE,
        '{"environment":"analytics","team":"analytics"}'
    )
) AS sample(
    resource_identifier,
    resource_name,
    resource_type,
    classification,
    cloud_region,
    encrypted_at_rest,
    encrypted_in_transit,
    public_access_enabled,
    backup_enabled,
    logging_enabled,
    deletion_protected,
    tags
)
WHERE o.organization_name = 'Example Enterprise'
ON CONFLICT (resource_identifier) DO NOTHING;

-- ============================================================
-- INITIAL ASSESSMENT EXECUTION
-- ============================================================

DO $$
DECLARE

    v_user_id BIGINT;
    v_resource_id BIGINT;

BEGIN

    SELECT user_id
    INTO v_user_id
    FROM governance_users
    WHERE username = 'compliance-officer';

    FOR v_resource_id IN

        SELECT resource_id
        FROM cloud_resources
        WHERE active = TRUE

    LOOP

        CALL run_resource_assessment(
            v_resource_id,
            v_user_id
        );

    END LOOP;

END;
$$;

-- ============================================================
-- FINDING GENERATION
-- ============================================================

INSERT INTO compliance_findings (
    evaluation_id,
    finding_code,
    finding_description,
    severity
)
SELECT
    e.evaluation_id,
    'POLICY-' || p.policy_code,
    e.violation_details::TEXT,
    e.severity
FROM policy_evaluations e
JOIN governance_policies p
    ON p.policy_id = e.policy_id
WHERE e.status = 'NON_COMPLIANT'
AND NOT EXISTS (
    SELECT 1
    FROM compliance_findings f
    WHERE f.evaluation_id = e.evaluation_id
      AND f.finding_code = 'POLICY-' || p.policy_code
);

-- ============================================================
-- SAMPLE REMEDIATION REQUEST
-- ============================================================

INSERT INTO remediation_requests (
    finding_id,
    requested_by,
    assigned_to,
    remediation_description,
    proposed_changes,
    status
)
SELECT
    f.finding_id,
    requester.user_id,
    assignee.user_id,
    'Enable encryption and disable public access on the affected resource.',
    jsonb_build_object(
        'encrypted_at_rest', TRUE,
        'public_access_enabled', FALSE,
        'backup_enabled', TRUE
    ),
    'PENDING_APPROVAL'
FROM compliance_findings f
JOIN policy_evaluations e
    ON e.evaluation_id = f.evaluation_id
JOIN governance_users requester
    ON requester.username = 'data-owner'
JOIN governance_users assignee
    ON assignee.username = 'security-admin'
WHERE f.finding_code = 'POLICY-ENC-001'
AND NOT EXISTS (
    SELECT 1
    FROM remediation_requests rr
    WHERE rr.finding_id = f.finding_id
);

-- ============================================================
-- APPROVAL DEMONSTRATION
-- ============================================================

INSERT INTO remediation_approvals (
    remediation_id,
    reviewer_id,
    approved,
    justification
)
SELECT
    rr.remediation_id,
    reviewer.user_id,
    TRUE,
    'Security review completed. Proposed remediation is approved.'
FROM remediation_requests rr
JOIN governance_users reviewer
    ON reviewer.username = 'security-admin'
WHERE rr.status = 'PENDING_APPROVAL'
AND NOT EXISTS (
    SELECT 1
    FROM remediation_approvals ra
    WHERE ra.remediation_id = rr.remediation_id
      AND ra.reviewer_id = reviewer.user_id
);

-- ============================================================
-- REPORTING AND RETRIEVAL QUERIES
-- ============================================================

-- 1. Complete cloud resource inventory.

SELECT *
FROM v_resource_posture
ORDER BY classification DESC, resource_name;

-- 2. Policy evaluation results.

SELECT *
FROM v_policy_compliance
ORDER BY assessment_id, resource_id, policy_code;

-- 3. Compliance aggregation.

SELECT

    status,

    severity,

    COUNT(*) AS evaluation_count

FROM policy_evaluations

GROUP BY status, severity

ORDER BY severity DESC, status;

-- 4. Resource-level compliance aggregation using CTEs.

WITH resource_results AS (

    SELECT

        resource_id,

        COUNT(*) FILTER (
            WHERE status = 'COMPLIANT'
        ) AS compliant,

        COUNT(*) FILTER (
            WHERE status = 'NON_COMPLIANT'
        ) AS non_compliant,

        COUNT(*) FILTER (
            WHERE status <> 'NOT_APPLICABLE'
        ) AS applicable

    FROM policy_evaluations

    GROUP BY resource_id

)

SELECT

    r.resource_name,

    rr.compliant,

    rr.non_compliant,

    rr.applicable,

    ROUND(
        100.0 * rr.compliant /
        NULLIF(rr.applicable, 0),
        2
    ) AS compliance_percentage

FROM resource_results rr

JOIN cloud_resources r
    ON r.resource_id = rr.resource_id

ORDER BY compliance_percentage ASC NULLS LAST;

-- 5. Data residency violations.

SELECT

    r.resource_name,

    r.cloud_region,

    rr.rule_name,

    re.status,

    re.evaluation_details

FROM residency_evaluations re

JOIN cloud_resources r
    ON r.resource_id = re.resource_id

JOIN residency_rules rr
    ON rr.residency_rule_id = re.residency_rule_id

WHERE re.status = 'NON_COMPLIANT';

-- 6. High-risk open findings.

SELECT

    f.finding_id,

    f.finding_code,

    f.severity,

    f.finding_description,

    f.remediation_state,

    f.detected_at

FROM compliance_findings f

WHERE f.remediation_state IN (
    'OPEN',
    'IN_PROGRESS',
    'PENDING_APPROVAL'
)

ORDER BY
    CASE f.severity
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        ELSE 4
    END,
    f.detected_at;

-- 7. Regulatory policy mapping.

SELECT

    framework.framework_code,

    control.control_code,

    control.control_name,

    policy.policy_code,

    policy.policy_name,

    mapping.mapping_rationale

FROM policy_control_mappings mapping

JOIN governance_policies policy
    ON policy.policy_id = mapping.policy_id

JOIN regulatory_controls control
    ON control.control_id = mapping.control_id

JOIN regulatory_frameworks framework
    ON framework.framework_id = control.framework_id

ORDER BY framework.framework_code, control.control_code;

-- 8. Approval eligibility.

SELECT

    rr.remediation_id,

    rr.status,

    COUNT(ra.approval_id) AS approval_count,

    BOOL_AND(ra.approved) FILTER (
        WHERE ra.approval_id IS NOT NULL
    ) AS all_approvals_positive

FROM remediation_requests rr

LEFT JOIN remediation_approvals ra
    ON ra.remediation_id = rr.remediation_id

GROUP BY rr.remediation_id, rr.status;

-- 9. Audit event history.

SELECT

    audit_id,

    action,

    actor_id,

    resource_id,

    previous_hash,

    event_hash,

    occurred_at

FROM audit_events

ORDER BY audit_id DESC;

-- 10. Current open remediation queue.

SELECT *
FROM v_open_remediation
ORDER BY created_at;

-- ============================================================
-- APPROVAL DECISION EXECUTION
-- ============================================================

DO $$
DECLARE
    v_remediation_id BIGINT;
    v_decision remediation_status;
BEGIN

    SELECT remediation_id
    INTO v_remediation_id
    FROM remediation_requests
    WHERE status = 'PENDING_APPROVAL'
    ORDER BY created_at
    LIMIT 1;

    IF FOUND THEN

        v_decision := determine_remediation_decision(
            v_remediation_id
        );

        RAISE NOTICE
            'Remediation % decision: %',
            v_remediation_id,
            v_decision;

    END IF;

END;
$$;

-- ============================================================
-- AUDIT CHAIN VERIFICATION QUERY
-- ============================================================

WITH ordered_events AS (

    SELECT

        audit_id,

        organization_id,

        previous_hash,

        event_hash,

        LAG(event_hash) OVER (
            PARTITION BY organization_id
            ORDER BY audit_id
        ) AS expected_previous_hash

    FROM audit_events

)

SELECT

    audit_id,

    organization_id,

    CASE

        WHEN expected_previous_hash IS NULL
             AND previous_hash = 'GENESIS'
        THEN 'VALID'

        WHEN previous_hash = expected_previous_hash
        THEN 'VALID'

        ELSE 'CHAIN_MISMATCH'

    END AS chain_status

FROM ordered_events

ORDER BY audit_id;

COMMIT;

-- ============================================================
-- OPERATIONAL NOTES
-- ============================================================

1. The policy evaluation function records the evaluation result
   separately from the cloud resource's actual configuration.

2. Residency evaluation checks an explicitly configured
   organizational region allowlist. It does not claim that a
   regulation universally requires a specific region.

3. Regulatory controls and internal governance policies are
   separate relational entities.

4. The audit chain uses pgcrypto SHA-256 and organization-scoped
   advisory transaction locks.

5. Database triggers prevent ordinary UPDATE and DELETE operations
   on audit records. Database superusers and privileged operators
   remain capable of bypassing or altering database-level controls.

6. Production deployment should use restricted database roles,
   independent audit exports, encryption, backups, secrets
   management and separation of duties.

7. Assessment results are historical records. A new assessment
   should be executed after resource remediation.

8. The reporting views aggregate stored assessments. They do not
   independently guarantee that a resource has been assessed
   recently.
*/
