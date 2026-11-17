/*
===============================================================================
DOCKER IMAGES AND DOCKERFILES
===============================================================================

PostgreSQL 15+

Relational image build, layer, registry, security, and optimization system.

Models:
1. Repositories
2. Dockerfiles and Dockerfile instructions
3. Base images and image stages
4. Build executions
5. Image layers and layer dependencies
6. Build-cache entries
7. Image artifacts and tags
8. Vulnerability and security assessments
9. Build policies
10. Deployment records

The estimated image sizes in the sample data are illustrative metadata.
They are not measurements produced by the Docker engine.
*/

BEGIN;

CREATE SCHEMA IF NOT EXISTS docker_platform;

SET search_path TO docker_platform, public;

-- ============================================================================
-- ENUM TYPES
-- ============================================================================

CREATE TYPE instruction_type AS ENUM (
    'FROM',
    'RUN',
    'COPY',
    'ADD',
    'WORKDIR',
    'ENV',
    'ARG',
    'EXPOSE',
    'USER',
    'CMD',
    'ENTRYPOINT',
    'LABEL',
    'HEALTHCHECK',
    'VOLUME',
    'SHELL'
);

CREATE TYPE build_status AS ENUM (
    'QUEUED',
    'VALIDATING',
    'BUILDING',
    'BUILT',
    'FAILED',
    'CANCELLED'
);

CREATE TYPE layer_status AS ENUM (
    'BUILT',
    'CACHED',
    'FAILED'
);

CREATE TYPE severity_level AS ENUM (
    'INFO',
    'LOW',
    'MEDIUM',
    'HIGH',
    'CRITICAL'
);

CREATE TYPE assessment_status AS ENUM (
    'PENDING',
    'PASSED',
    'WARNING',
    'FAILED'
);

CREATE TYPE deployment_status AS ENUM (
    'PENDING',
    'RUNNING',
    'SUCCEEDED',
    'FAILED',
    'ROLLED_BACK'
);

-- ============================================================================
-- REPOSITORIES
-- ============================================================================

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_name VARCHAR(150) NOT NULL UNIQUE,

    description TEXT,

    source_control_url TEXT,

    owner_name VARCHAR(150) NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (length(trim(repository_name)) > 0)
);

-- ============================================================================
-- BASE IMAGES
-- ============================================================================

CREATE TABLE base_images (
    base_image_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    image_name VARCHAR(255) NOT NULL,

    image_tag VARCHAR(150) NOT NULL,

    digest VARCHAR(255),

    operating_system VARCHAR(100),

    architecture VARCHAR(50),

    is_verified BOOLEAN NOT NULL DEFAULT FALSE,

    is_deprecated BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (image_name, image_tag),

    CHECK (length(trim(image_name)) > 0)
);

CREATE INDEX idx_base_images_name
    ON base_images (image_name);

-- ============================================================================
-- DOCKERFILES
-- ============================================================================

CREATE TABLE dockerfiles (
    dockerfile_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    file_path VARCHAR(500) NOT NULL DEFAULT 'Dockerfile',

    dockerfile_version INTEGER NOT NULL DEFAULT 1,

    content TEXT NOT NULL,

    content_sha256 VARCHAR(64) NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (
        repository_id,
        file_path,
        dockerfile_version
    ),

    CHECK (dockerfile_version > 0),

    CHECK (length(trim(content)) > 0),

    CHECK (content_sha256 ~ '^[a-f0-9]{64}$')
);

CREATE INDEX idx_dockerfiles_repository
    ON dockerfiles (repository_id, created_at DESC);

-- ============================================================================
-- DOCKERFILE INSTRUCTIONS
-- ============================================================================

CREATE TABLE dockerfile_instructions (
    instruction_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    dockerfile_id BIGINT NOT NULL
        REFERENCES dockerfiles(dockerfile_id)
        ON DELETE CASCADE,

    stage_number INTEGER NOT NULL DEFAULT 0,

    instruction_number INTEGER NOT NULL,

    instruction instruction_type NOT NULL,

    arguments TEXT NOT NULL,

    creates_filesystem_layer BOOLEAN NOT NULL DEFAULT FALSE,

    estimated_size_bytes BIGINT NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (
        dockerfile_id,
        instruction_number
    ),

    CHECK (stage_number >= 0),

    CHECK (instruction_number > 0),

    CHECK (estimated_size_bytes >= 0)
);

CREATE INDEX idx_instructions_dockerfile
    ON dockerfile_instructions (
        dockerfile_id,
        instruction_number
    );

CREATE INDEX idx_instructions_type
    ON dockerfile_instructions (instruction);

-- ============================================================================
-- IMAGE BUILD EXECUTIONS
-- ============================================================================

CREATE TABLE image_builds (
    build_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    dockerfile_id BIGINT NOT NULL
        REFERENCES dockerfiles(dockerfile_id),

    image_name VARCHAR(255) NOT NULL,

    image_tag VARCHAR(150) NOT NULL,

    build_status build_status NOT NULL DEFAULT 'QUEUED',

    builder_name VARCHAR(150),

    platform VARCHAR(100) NOT NULL DEFAULT 'linux/amd64',

    build_arguments JSONB NOT NULL DEFAULT '{}'::jsonb,

    dockerfile_sha256 VARCHAR(64) NOT NULL,

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (length(trim(image_name)) > 0),

    CHECK (length(trim(image_tag)) > 0),

    CHECK (dockerfile_sha256 ~ '^[a-f0-9]{64}$'),

    CHECK (
        completed_at IS NULL
        OR started_at IS NULL
        OR completed_at >= started_at
    )
);

CREATE INDEX idx_builds_status
    ON image_builds (build_status, created_at DESC);

CREATE INDEX idx_builds_image
    ON image_builds (image_name, image_tag);

CREATE INDEX idx_builds_dockerfile
    ON image_builds (dockerfile_id, created_at DESC);

CREATE INDEX idx_builds_arguments
    ON image_builds USING GIN (build_arguments);

-- ============================================================================
-- IMAGE LAYERS
-- ============================================================================

CREATE TABLE image_layers (
    layer_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    build_id BIGINT NOT NULL
        REFERENCES image_builds(build_id)
        ON DELETE CASCADE,

    instruction_id BIGINT
        REFERENCES dockerfile_instructions(instruction_id),

    layer_number INTEGER NOT NULL,

    parent_layer_id BIGINT,

    layer_digest VARCHAR(64) NOT NULL,

    compressed_size_bytes BIGINT NOT NULL DEFAULT 0,

    uncompressed_size_bytes BIGINT NOT NULL DEFAULT 0,

    layer_status layer_status NOT NULL DEFAULT 'BUILT',

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (build_id, layer_number),

    UNIQUE (build_id, layer_id),

    FOREIGN KEY (build_id, parent_layer_id)
        REFERENCES image_layers(build_id, layer_id),

    CHECK (layer_number > 0),

    CHECK (compressed_size_bytes >= 0),

    CHECK (uncompressed_size_bytes >= 0),

    CHECK (layer_digest ~ '^[a-f0-9]{64}$'),

    CHECK (
        parent_layer_id IS NULL
        OR parent_layer_id <> layer_id
    )
);

CREATE INDEX idx_layers_digest
    ON image_layers (layer_digest);

CREATE INDEX idx_layers_build
    ON image_layers (build_id, layer_number);

-- ============================================================================
-- BUILD CACHE
-- ============================================================================

CREATE TABLE build_cache (
    cache_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    cache_key VARCHAR(64) NOT NULL UNIQUE,

    layer_digest VARCHAR(64) NOT NULL,

    size_bytes BIGINT NOT NULL,

    source_build_id BIGINT
        REFERENCES image_builds(build_id),

    last_used_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (cache_key ~ '^[a-f0-9]{64}$'),

    CHECK (layer_digest ~ '^[a-f0-9]{64}$'),

    CHECK (size_bytes >= 0)
);

CREATE INDEX idx_build_cache_last_used
    ON build_cache (last_used_at DESC);

-- ============================================================================
-- IMAGE ARTIFACTS
-- ============================================================================

CREATE TABLE image_artifacts (
    artifact_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    build_id BIGINT NOT NULL UNIQUE
        REFERENCES image_builds(build_id),

    image_name VARCHAR(255) NOT NULL,

    image_tag VARCHAR(150) NOT NULL,

    image_digest VARCHAR(64) NOT NULL UNIQUE,

    total_size_bytes BIGINT NOT NULL,

    architecture VARCHAR(50) NOT NULL,

    operating_system VARCHAR(50) NOT NULL,

    is_signed BOOLEAN NOT NULL DEFAULT FALSE,

    published_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (image_name, image_tag),

    CHECK (total_size_bytes >= 0),

    CHECK (image_digest ~ '^[a-f0-9]{64}$')
);

CREATE INDEX idx_artifacts_image
    ON image_artifacts (image_name, published_at DESC);

-- ============================================================================
-- IMAGE SECURITY ASSESSMENTS
-- ============================================================================

CREATE TABLE security_assessments (
    assessment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    artifact_id BIGINT NOT NULL
        REFERENCES image_artifacts(artifact_id)
        ON DELETE CASCADE,

    scanner_name VARCHAR(150) NOT NULL,

    scanner_version VARCHAR(100),

    status assessment_status NOT NULL DEFAULT 'PENDING',

    scanned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    completed_at TIMESTAMPTZ,

    total_findings INTEGER NOT NULL DEFAULT 0,

    critical_count INTEGER NOT NULL DEFAULT 0,

    high_count INTEGER NOT NULL DEFAULT 0,

    medium_count INTEGER NOT NULL DEFAULT 0,

    low_count INTEGER NOT NULL DEFAULT 0,

    information_count INTEGER NOT NULL DEFAULT 0,

    CHECK (total_findings >= 0),

    CHECK (critical_count >= 0),

    CHECK (high_count >= 0),

    CHECK (medium_count >= 0),

    CHECK (low_count >= 0),

    CHECK (information_count >= 0),

    CHECK (
        total_findings >=
        critical_count +
        high_count +
        medium_count +
        low_count +
        information_count
    )
);

CREATE INDEX idx_security_artifact
    ON security_assessments (
        artifact_id,
        scanned_at DESC
    );

CREATE INDEX idx_security_status
    ON security_assessments (status, scanned_at DESC);

-- ============================================================================
-- VULNERABILITY FINDINGS
-- ============================================================================

CREATE TABLE vulnerability_findings (
    finding_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    assessment_id BIGINT NOT NULL
        REFERENCES security_assessments(assessment_id)
        ON DELETE CASCADE,

    vulnerability_code VARCHAR(100) NOT NULL,

    package_name VARCHAR(255) NOT NULL,

    installed_version VARCHAR(100),

    fixed_version VARCHAR(100),

    severity severity_level NOT NULL,

    description TEXT,

    is_suppressed BOOLEAN NOT NULL DEFAULT FALSE,

    UNIQUE (
        assessment_id,
        vulnerability_code,
        package_name
    )
);

CREATE INDEX idx_vulnerability_severity
    ON vulnerability_findings (
        severity,
        is_suppressed
    );

-- ============================================================================
-- BUILD POLICIES
-- ============================================================================

CREATE TABLE build_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,

    policy_name VARCHAR(150) NOT NULL,

    require_non_root BOOLEAN NOT NULL DEFAULT TRUE,

    require_digest_pinned_base BOOLEAN NOT NULL DEFAULT FALSE,

    require_successful_scan BOOLEAN NOT NULL DEFAULT TRUE,

    allow_latest_tag BOOLEAN NOT NULL DEFAULT FALSE,

    maximum_image_size_bytes BIGINT,

    maximum_critical_vulnerabilities INTEGER NOT NULL DEFAULT 0,

    maximum_high_vulnerabilities INTEGER NOT NULL DEFAULT 5,

    require_signed_image BOOLEAN NOT NULL DEFAULT FALSE,

    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (repository_id, policy_name),

    CHECK (
        maximum_image_size_bytes IS NULL
        OR maximum_image_size_bytes > 0
    ),

    CHECK (maximum_critical_vulnerabilities >= 0),

    CHECK (maximum_high_vulnerabilities >= 0)
);

CREATE INDEX idx_build_policies_repository
    ON build_policies (repository_id, is_enabled);

-- ============================================================================
-- POLICY EVALUATIONS
-- ============================================================================

CREATE TABLE policy_evaluations (
    evaluation_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    artifact_id BIGINT NOT NULL
        REFERENCES image_artifacts(artifact_id),

    policy_id BIGINT NOT NULL
        REFERENCES build_policies(policy_id),

    status assessment_status NOT NULL,

    violations JSONB NOT NULL DEFAULT '[]'::jsonb,

    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (artifact_id, policy_id),

    CHECK (jsonb_typeof(violations) = 'array')
);

CREATE INDEX idx_policy_evaluations_status
    ON policy_evaluations (status, evaluated_at DESC);

-- ============================================================================
-- DEPLOYMENTS
-- ============================================================================

CREATE TABLE image_deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    artifact_id BIGINT NOT NULL
        REFERENCES image_artifacts(artifact_id),

    environment VARCHAR(100) NOT NULL,

    deployment_status deployment_status NOT NULL DEFAULT 'PENDING',

    deployed_by VARCHAR(150) NOT NULL,

    deployed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    completed_at TIMESTAMPTZ,

    rollback_reason TEXT,

    CHECK (
        completed_at IS NULL
        OR completed_at >= deployed_at
    )
);

CREATE INDEX idx_deployments_environment
    ON image_deployments (
        environment,
        deployed_at DESC
    );

CREATE INDEX idx_deployments_status
    ON image_deployments (deployment_status);

-- ============================================================================
-- BUILD STATUS VALIDATION
-- ============================================================================

CREATE OR REPLACE FUNCTION validate_build_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.build_status = OLD.build_status THEN
        RETURN NEW;
    END IF;

    IF NOT (
        (OLD.build_status = 'QUEUED'
            AND NEW.build_status IN ('VALIDATING', 'CANCELLED', 'FAILED'))
        OR
        (OLD.build_status = 'VALIDATING'
            AND NEW.build_status IN ('BUILDING', 'FAILED', 'CANCELLED'))
        OR
        (OLD.build_status = 'BUILDING'
            AND NEW.build_status IN ('BUILT', 'FAILED', 'CANCELLED'))
    ) THEN
        RAISE EXCEPTION
            'Invalid build transition: % -> %',
            OLD.build_status,
            NEW.build_status;
    END IF;

    IF NEW.build_status = 'BUILDING'
       AND NEW.started_at IS NULL THEN
        NEW.started_at := CURRENT_TIMESTAMP;
    END IF;

    IF NEW.build_status IN ('BUILT', 'FAILED', 'CANCELLED')
       AND NEW.completed_at IS NULL THEN
        NEW.completed_at := CURRENT_TIMESTAMP;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_build_transition
BEFORE UPDATE OF build_status
ON image_builds
FOR EACH ROW
EXECUTE FUNCTION validate_build_transition();

-- ============================================================================
-- LAYER VALIDATION
-- ============================================================================

CREATE OR REPLACE FUNCTION validate_layer_parent()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    parent_number INTEGER;
BEGIN
    IF NEW.parent_layer_id IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT layer_number
    INTO parent_number
    FROM image_layers
    WHERE layer_id = NEW.parent_layer_id
      AND build_id = NEW.build_id;

    IF parent_number IS NULL THEN
        RAISE EXCEPTION
            'Parent layer does not exist in this build.';
    END IF;

    IF parent_number >= NEW.layer_number THEN
        RAISE EXCEPTION
            'Parent layer must precede its child layer.';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_layer_parent
BEFORE INSERT OR UPDATE
ON image_layers
FOR EACH ROW
EXECUTE FUNCTION validate_layer_parent();

-- ============================================================================
-- IMAGE PUBLICATION VALIDATION
-- ============================================================================

CREATE OR REPLACE FUNCTION validate_artifact_publication()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    current_status build_status;
BEGIN
    SELECT build_status
    INTO current_status
    FROM image_builds
    WHERE build_id = NEW.build_id
    FOR UPDATE;

    IF current_status <> 'BUILT' THEN
        RAISE EXCEPTION
            'Only successfully built images can be published.';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM image_artifacts
        WHERE image_digest = NEW.image_digest
    ) THEN
        RAISE EXCEPTION
            'Image digest already exists.';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_artifact_publication
BEFORE INSERT
ON image_artifacts
FOR EACH ROW
EXECUTE FUNCTION validate_artifact_publication();

-- ============================================================================
-- SECURITY ASSESSMENT CONSISTENCY
-- ============================================================================

CREATE OR REPLACE FUNCTION update_security_assessment_counts()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    target_assessment BIGINT;
BEGIN
    target_assessment := COALESCE(
        NEW.assessment_id,
        OLD.assessment_id
    );

    UPDATE security_assessments
    SET
        total_findings = (
            SELECT COUNT(*)
            FROM vulnerability_findings
            WHERE assessment_id = target_assessment
              AND NOT is_suppressed
        ),

        critical_count = (
            SELECT COUNT(*)
            FROM vulnerability_findings
            WHERE assessment_id = target_assessment
              AND severity = 'CRITICAL'
              AND NOT is_suppressed
        ),

        high_count = (
            SELECT COUNT(*)
            FROM vulnerability_findings
            WHERE assessment_id = target_assessment
              AND severity = 'HIGH'
              AND NOT is_suppressed
        ),

        medium_count = (
            SELECT COUNT(*)
            FROM vulnerability_findings
            WHERE assessment_id = target_assessment
              AND severity = 'MEDIUM'
              AND NOT is_suppressed
        ),

        low_count = (
            SELECT COUNT(*)
            FROM vulnerability_findings
            WHERE assessment_id = target_assessment
              AND severity = 'LOW'
              AND NOT is_suppressed
        ),

        information_count = (
            SELECT COUNT(*)
            FROM vulnerability_findings
            WHERE assessment_id = target_assessment
              AND severity = 'INFO'
              AND NOT is_suppressed
        )

    WHERE assessment_id = target_assessment;

    RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE TRIGGER trg_security_finding_counts
AFTER INSERT OR UPDATE OR DELETE
ON vulnerability_findings
FOR EACH ROW
EXECUTE FUNCTION update_security_assessment_counts();

-- ============================================================================
-- REPORTING VIEW
-- ============================================================================

CREATE OR REPLACE VIEW image_inventory_report AS
SELECT
    a.artifact_id,
    a.image_name,
    a.image_tag,
    a.image_digest,
    a.total_size_bytes,
    ROUND(
        a.total_size_bytes / 1048576.0,
        2
    ) AS image_size_mb,
    a.architecture,
    a.operating_system,
    a.is_signed,
    b.build_id,
    b.build_status,
    b.platform,
    r.repository_name,
    COALESCE(s.status::TEXT, 'NOT_SCANNED') AS scan_status,
    COALESCE(s.critical_count, 0) AS critical_vulnerabilities,
    COALESCE(s.high_count, 0) AS high_vulnerabilities,
    a.published_at

FROM image_artifacts a

JOIN image_builds b
    ON b.build_id = a.build_id

JOIN dockerfiles d
    ON d.dockerfile_id = b.dockerfile_id

JOIN repositories r
    ON r.repository_id = d.repository_id

LEFT JOIN LATERAL (
    SELECT *
    FROM security_assessments sa
    WHERE sa.artifact_id = a.artifact_id
    ORDER BY sa.scanned_at DESC
    LIMIT 1
) s ON TRUE;

-- ============================================================================
-- LAYER REPORTING VIEW
-- ============================================================================

CREATE OR REPLACE VIEW image_layer_report AS
SELECT
    b.build_id,
    b.image_name,
    b.image_tag,
    l.layer_number,
    i.instruction,
    i.arguments,
    l.layer_digest,
    l.compressed_size_bytes,
    l.uncompressed_size_bytes,
    l.layer_status,
    l.parent_layer_id

FROM image_layers l

JOIN image_builds b
    ON b.build_id = l.build_id

LEFT JOIN dockerfile_instructions i
    ON i.instruction_id = l.instruction_id;

-- ============================================================================
-- BUILD VALIDATION FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION validate_dockerfile(
    p_dockerfile_id BIGINT
)
RETURNS TABLE (
    check_name TEXT,
    passed BOOLEAN,
    details TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    has_from BOOLEAN;
    has_user BOOLEAN;
    has_start BOOLEAN;
    has_secret BOOLEAN;
    has_latest BOOLEAN;
BEGIN
    SELECT
        COALESCE(BOOL_OR(instruction = 'FROM'), FALSE),
        COALESCE(BOOL_OR(instruction = 'USER'), FALSE),
        COALESCE(
            BOOL_OR(instruction IN ('CMD', 'ENTRYPOINT')),
            FALSE
        ),
        COALESCE(
            BOOL_OR(
                instruction = 'ENV'
                AND arguments ~* '(PASSWORD|SECRET|TOKEN|API_KEY)'
            ),
            FALSE
        ),
        COALESCE(
            BOOL_OR(
                instruction = 'FROM'
                AND arguments ~* ':latest([[:space:]]|$)'
            ),
            FALSE
        )
    INTO
        has_from,
        has_user,
        has_start,
        has_secret,
        has_latest
    FROM dockerfile_instructions
    WHERE dockerfile_id = p_dockerfile_id;

    RETURN QUERY VALUES
        (
            'BASE_IMAGE',
            has_from,
            'A Dockerfile must contain FROM.'
        ),
        (
            'NON_ROOT_USER',
            has_user,
            'An explicit runtime user is recommended.'
        ),
        (
            'START_COMMAND',
            has_start,
            'CMD or ENTRYPOINT should be defined.'
        ),
        (
            'SECRET_HANDLING',
            NOT has_secret,
            'Credentials must not be stored in ENV.'
        ),
        (
            'BASE_IMAGE_PINNING',
            NOT has_latest,
            'Avoid mutable latest tags.'
        );
END;
$$;

-- ============================================================================
-- IMAGE ELIGIBILITY FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION evaluate_image_eligibility(
    p_artifact_id BIGINT,
    p_policy_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    violations JSONB
)
LANGUAGE plpgsql
AS $$
DECLARE
    artifact RECORD;
    policy RECORD;
    latest_scan RECORD;
    problems JSONB := '[]'::jsonb;
BEGIN
    SELECT *
    INTO artifact
    FROM image_artifacts
    WHERE artifact_id = p_artifact_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Image artifact % does not exist.',
            p_artifact_id;
    END IF;

    SELECT *
    INTO policy
    FROM build_policies
    WHERE policy_id = p_policy_id
      AND repository_id = (
          SELECT d.repository_id
          FROM image_builds b
          JOIN dockerfiles d
              ON d.dockerfile_id = b.dockerfile_id
          WHERE b.build_id = artifact.build_id
      );

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Policy does not belong to the artifact repository.';
    END IF;

    IF NOT policy.is_enabled THEN
        RAISE EXCEPTION
            'The selected policy is disabled.';
    END IF;

    IF policy.maximum_image_size_bytes IS NOT NULL
       AND artifact.total_size_bytes >
           policy.maximum_image_size_bytes THEN

        problems := problems || jsonb_build_array(
            jsonb_build_object(
                'code', 'IMAGE_TOO_LARGE',
                'actual', artifact.total_size_bytes,
                'maximum', policy.maximum_image_size_bytes
            )
        );
    END IF;

    IF policy.require_signed_image
       AND NOT artifact.is_signed THEN

        problems := problems || jsonb_build_array(
            jsonb_build_object(
                'code', 'IMAGE_NOT_SIGNED'
            )
        );
    END IF;

    IF policy.require_successful_scan THEN
        SELECT *
        INTO latest_scan
        FROM security_assessments
        WHERE artifact_id = p_artifact_id
        ORDER BY scanned_at DESC
        LIMIT 1;

        IF NOT FOUND THEN
            problems := problems || jsonb_build_array(
                jsonb_build_object(
                    'code', 'SCAN_MISSING'
                )
            );

        ELSIF latest_scan.status NOT IN ('PASSED', 'WARNING') THEN
            problems := problems || jsonb_build_array(
                jsonb_build_object(
                    'code', 'SCAN_NOT_PASSED'
                )
            );
        END IF;

        IF FOUND THEN
            IF latest_scan.critical_count >
               policy.maximum_critical_vulnerabilities THEN

                problems := problems || jsonb_build_array(
                    jsonb_build_object(
                        'code', 'CRITICAL_LIMIT_EXCEEDED',
                        'actual', latest_scan.critical_count,
                        'maximum',
                            policy.maximum_critical_vulnerabilities
                    )
                );
            END IF;

            IF latest_scan.high_count >
               policy.maximum_high_vulnerabilities THEN

                problems := problems || jsonb_build_array(
                    jsonb_build_object(
                        'code', 'HIGH_LIMIT_EXCEEDED',
                        'actual', latest_scan.high_count,
                        'maximum',
                            policy.maximum_high_vulnerabilities
                    )
                );
            END IF;
        END IF;
    END IF;

    RETURN QUERY
    SELECT
        jsonb_array_length(problems) = 0,
        problems;
END;
$$;

-- ============================================================================
-- SAMPLE DATA
-- ============================================================================

INSERT INTO repositories (
    repository_name,
    description,
    source_control_url,
    owner_name
)
VALUES
(
    'inventory-api',
    'Inventory management API service.',
    'https://github.com/example/inventory-api',
    'Platform Engineering'
),
(
    'analytics-worker',
    'Background analytics processing service.',
    'https://github.com/example/analytics-worker',
    'Data Engineering'
);

INSERT INTO base_images (
    image_name,
    image_tag,
    digest,
    operating_system,
    architecture,
    is_verified
)
VALUES
(
    'python',
    '3.12-slim',
    repeat('a', 64),
    'linux',
    'amd64',
    TRUE
),
(
    'node',
    '22-alpine',
    repeat('b', 64),
    'linux',
    'amd64',
    TRUE
),
(
    'python',
    'latest',
    repeat('c', 64),
    'linux',
    'amd64',
    FALSE
);

INSERT INTO dockerfiles (
    repository_id,
    file_path,
    dockerfile_version,
    content,
    content_sha256
)
VALUES
(
    1,
    'Dockerfile',
    1,
    'FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
USER 10001
EXPOSE 8000
CMD ["python", "main.py"]',
    repeat('1', 64)
),
(
    2,
    'Dockerfile',
    1,
    'FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
FROM node:22-alpine
USER node
CMD ["node", "server.js"]',
    repeat('2', 64)
);

INSERT INTO dockerfile_instructions (
    dockerfile_id,
    stage_number,
    instruction_number,
    instruction,
    arguments,
    creates_filesystem_layer,
    estimated_size_bytes
)
VALUES
(1, 0, 1, 'FROM', 'python:3.12-slim', TRUE, 125000000),
(1, 0, 2, 'WORKDIR', '/app', FALSE, 0),
(1, 0, 3, 'COPY', 'requirements.txt .', TRUE, 100000),
(1, 0, 4, 'RUN', 'pip install --no-cache-dir -r requirements.txt', TRUE, 25000000),
(1, 0, 5, 'COPY', '. .', TRUE, 5000000),
(1, 0, 6, 'USER', '10001', FALSE, 0),
(1, 0, 7, 'EXPOSE', '8000', FALSE, 0),
(1, 0, 8, 'CMD', '["python", "main.py"]', FALSE, 0),

(2, 0, 1, 'FROM', 'node:22-alpine AS builder', TRUE, 150000000),
(2, 0, 2, 'WORKDIR', '/app', FALSE, 0),
(2, 0, 3, 'COPY', 'package*.json ./', TRUE, 100000),
(2, 0, 4, 'RUN', 'npm ci', TRUE, 80000000),
(2, 0, 5, 'COPY', '. .', TRUE, 5000000),
(2, 0, 6, 'RUN', 'npm run build', TRUE, 20000000),
(2, 1, 7, 'FROM', 'node:22-alpine', TRUE, 150000000),
(2, 1, 8, 'USER', 'node', FALSE, 0),
(2, 1, 9, 'CMD', '["node", "server.js"]', FALSE, 0);

INSERT INTO image_builds (
    dockerfile_id,
    image_name,
    image_tag,
    build_status,
    builder_name,
    platform,
    dockerfile_sha256
)
VALUES
(
    1,
    'inventory-api',
    '1.0.0',
    'QUEUED',
    'builder-01',
    'linux/amd64',
    repeat('1', 64)
),
(
    2,
    'analytics-worker',
    '1.0.0',
    'QUEUED',
    'builder-02',
    'linux/amd64',
    repeat('2', 64)
);

-- Demonstrate valid build-state transitions.

UPDATE image_builds
SET build_status = 'VALIDATING'
WHERE build_id IN (1, 2);

UPDATE image_builds
SET build_status = 'BUILDING'
WHERE build_id IN (1, 2);

UPDATE image_builds
SET
    build_status = 'BUILT',
    completed_at = CURRENT_TIMESTAMP
WHERE build_id IN (1, 2);

INSERT INTO image_layers (
    build_id,
    instruction_id,
    layer_number,
    parent_layer_id,
    layer_digest,
    compressed_size_bytes,
    uncompressed_size_bytes,
    layer_status
)
VALUES
(
    1,
    1,
    1,
    NULL,
    repeat('a', 64),
    50000000,
    125000000,
    'BUILT'
),
(
    1,
    3,
    2,
    1,
    repeat('b', 64),
    100000,
    100000,
    'BUILT'
),
(
    1,
    4,
    3,
    2,
    repeat('d', 64),
    12000000,
    25000000,
    'BUILT'
),
(
    1,
    5,
    4,
    3,
    repeat('e', 64),
    2500000,
    5000000,
    'BUILT'
),
(
    2,
    9,
    1,
    NULL,
    repeat('f', 64),
    60000000,
    150000000,
    'BUILT'
),
(
    2,
    11,
    2,
    5,
    repeat('1', 64),
    100000,
    100000,
    'BUILT'
);

INSERT INTO build_cache (
    cache_key,
    layer_digest,
    size_bytes,
    source_build_id
)
VALUES
(
    repeat('a', 64),
    repeat('a', 64),
    125000000,
    1
),
(
    repeat('b', 64),
    repeat('b', 64),
    100000,
    1
);

INSERT INTO image_artifacts (
    build_id,
    image_name,
    image_tag,
    image_digest,
    total_size_bytes,
    architecture,
    operating_system,
    is_signed
)
VALUES
(
    1,
    'inventory-api',
    '1.0.0',
    repeat('3', 64),
    152600000,
    'amd64',
    'linux',
    TRUE
),
(
    2,
    'analytics-worker',
    '1.0.0',
    repeat('4', 64),
    405200000,
    'amd64',
    'linux',
    FALSE
);

INSERT INTO security_assessments (
    artifact_id,
    scanner_name,
    scanner_version,
    status
)
VALUES
(1, 'Trivy', '0.58.0', 'PENDING'),
(2, 'Trivy', '0.58.0', 'PENDING');

INSERT INTO vulnerability_findings (
    assessment_id,
    vulnerability_code,
    package_name,
    installed_version,
    fixed_version,
    severity,
    description
)
VALUES
(
    1,
    'CVE-2025-10001',
    'example-package',
    '1.0.0',
    '1.0.2',
    'MEDIUM',
    'Sample medium-severity vulnerability.'
),
(
    2,
    'CVE-2025-10002',
    'example-runtime',
    '2.0.0',
    '2.1.0',
    'HIGH',
    'Sample high-severity vulnerability.'
),
(
    2,
    'CVE-2025-10003',
    'example-library',
    '3.0.0',
    '3.0.2',
    'CRITICAL',
    'Sample critical-severity vulnerability.'
);

UPDATE security_assessments
SET
    status = 'PASSED',
    completed_at = CURRENT_TIMESTAMP
WHERE assessment_id = 1;

UPDATE security_assessments
SET
    status = 'FAILED',
    completed_at = CURRENT_TIMESTAMP
WHERE assessment_id = 2;

INSERT INTO build_policies (
    repository_id,
    policy_name,
    require_non_root,
    require_digest_pinned_base,
    require_successful_scan,
    allow_latest_tag,
    maximum_image_size_bytes,
    maximum_critical_vulnerabilities,
    maximum_high_vulnerabilities,
    require_signed_image
)
VALUES
(
    1,
    'production-policy',
    TRUE,
    TRUE,
    TRUE,
    FALSE,
    300000000,
    0,
    2,
    TRUE
),
(
    2,
    'production-policy',
    TRUE,
    TRUE,
    TRUE,
    FALSE,
    300000000,
    0,
    0,
    TRUE
);

INSERT INTO image_deployments (
    artifact_id,
    environment,
    deployment_status,
    deployed_by
)
VALUES
(
    1,
    'staging',
    'SUCCEEDED',
    'release-engineer'
),
(
    2,
    'production',
    'FAILED',
    'deployment-service'
);

-- ============================================================================
-- POLICY EVALUATION PROCEDURE
-- ============================================================================

CREATE OR REPLACE PROCEDURE evaluate_all_images()
LANGUAGE plpgsql
AS $$
DECLARE
    item RECORD;
    result RECORD;
BEGIN
    FOR item IN
        SELECT
            a.artifact_id,
            p.policy_id
        FROM image_artifacts a
        JOIN image_builds b
            ON b.build_id = a.build_id
        JOIN dockerfiles d
            ON d.dockerfile_id = b.dockerfile_id
        JOIN build_policies p
            ON p.repository_id = d.repository_id
        WHERE p.is_enabled
    LOOP
        SELECT *
        INTO result
        FROM evaluate_image_eligibility(
            item.artifact_id,
            item.policy_id
        );

        INSERT INTO policy_evaluations (
            artifact_id,
            policy_id,
            status,
            violations
        )
        VALUES (
            item.artifact_id,
            item.policy_id,
            CASE
                WHEN result.eligible THEN 'PASSED'::assessment_status
                ELSE 'FAILED'::assessment_status
            END,
            result.violations
        )
        ON CONFLICT (artifact_id, policy_id)
        DO UPDATE SET
            status = EXCLUDED.status,
            violations = EXCLUDED.violations,
            evaluated_at = CURRENT_TIMESTAMP;
    END LOOP;
END;
$$;

CALL evaluate_all_images();

-- ============================================================================
-- QUERY 1: DOCKERFILE INSTRUCTION RETRIEVAL
-- ============================================================================

SELECT
    d.file_path,
    d.dockerfile_version,
    i.instruction_number,
    i.stage_number,
    i.instruction,
    i.arguments,
    i.creates_filesystem_layer
FROM dockerfiles d
JOIN dockerfile_instructions i
    ON i.dockerfile_id = d.dockerfile_id
WHERE d.repository_id = 1
ORDER BY
    d.dockerfile_version,
    i.instruction_number;

-- ============================================================================
-- QUERY 2: DOCKERFILE VALIDATION
-- ============================================================================

SELECT *
FROM validate_dockerfile(1);

-- ============================================================================
-- QUERY 3: IMAGE SIZE AGGREGATION
-- ============================================================================

SELECT
    repository_name,
    COUNT(*) AS published_images,
    ROUND(
        AVG(image_size_mb),
        2
    ) AS average_size_mb,
    ROUND(
        MAX(image_size_mb),
        2
    ) AS largest_image_mb
FROM image_inventory_report
GROUP BY repository_name
ORDER BY largest_image_mb DESC;

-- ============================================================================
-- QUERY 4: LAYER CACHE UTILIZATION
-- ============================================================================

SELECT
    build_id,
    image_name,
    image_tag,
    COUNT(*) AS total_layers,
    COUNT(*) FILTER (
        WHERE layer_status = 'CACHED'
    ) AS cached_layers,
    COUNT(*) FILTER (
        WHERE layer_status = 'BUILT'
    ) AS newly_built_layers,
    ROUND(
        100.0 *
        COUNT(*) FILTER (
            WHERE layer_status = 'CACHED'
        ) /
        NULLIF(COUNT(*), 0),
        2
    ) AS cache_hit_percentage
FROM image_layer_report
GROUP BY
    build_id,
    image_name,
    image_tag
ORDER BY build_id;

-- ============================================================================
-- QUERY 5: SECURITY REPORT
-- ============================================================================

SELECT
    a.image_name,
    a.image_tag,
    s.scanner_name,
    s.status,
    s.total_findings,
    s.critical_count,
    s.high_count,
    s.medium_count,
    s.low_count
FROM image_inventory_report a
JOIN security_assessments s
    ON s.artifact_id = a.artifact_id
ORDER BY s.scanned_at DESC;

-- ============================================================================
-- QUERY 6: VULNERABILITY DETAILS
-- ============================================================================

SELECT
    a.image_name,
    a.image_tag,
    v.vulnerability_code,
    v.package_name,
    v.installed_version,
    v.fixed_version,
    v.severity
FROM vulnerability_findings v
JOIN security_assessments s
    ON s.assessment_id = v.assessment_id
JOIN image_artifacts a
    ON a.artifact_id = s.artifact_id
WHERE NOT v.is_suppressed
ORDER BY
    CASE v.severity
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        WHEN 'LOW' THEN 4
        ELSE 5
    END;

-- ============================================================================
-- QUERY 7: IMAGE ELIGIBILITY REPORT
-- ============================================================================

SELECT
    a.image_name,
    a.image_tag,
    p.policy_name,
    pe.status,
    pe.violations,
    pe.evaluated_at
FROM policy_evaluations pe
JOIN image_artifacts a
    ON a.artifact_id = pe.artifact_id
JOIN build_policies p
    ON p.policy_id = pe.policy_id
ORDER BY pe.evaluated_at DESC;

-- ============================================================================
-- QUERY 8: DEPLOYMENT REPORT
-- ============================================================================

SELECT
    a.image_name,
    a.image_tag,
    d.environment,
    d.deployment_status,
    d.deployed_by,
    d.deployed_at,
    d.completed_at,
    d.rollback_reason
FROM image_deployments d
JOIN image_artifacts a
    ON a.artifact_id = d.artifact_id
ORDER BY d.deployed_at DESC;

-- ============================================================================
-- QUERY 9: MULTI-STAGE BUILD ANALYSIS
-- ============================================================================

SELECT
    d.file_path,
    COUNT(DISTINCT i.stage_number) AS stage_count,
    COUNT(*) FILTER (
        WHERE i.instruction = 'FROM'
    ) AS from_count,
    COUNT(*) FILTER (
        WHERE i.instruction = 'RUN'
    ) AS run_count,
    COUNT(*) FILTER (
        WHERE i.instruction IN ('COPY', 'ADD')
    ) AS file_operations
FROM dockerfiles d
JOIN dockerfile_instructions i
    ON i.dockerfile_id = d.dockerfile_id
GROUP BY d.dockerfile_id, d.file_path
ORDER BY stage_count DESC;

-- ============================================================================
-- QUERY 10: COMMON BUILD OPTIMIZATION OPPORTUNITIES
-- ============================================================================

SELECT
    d.dockerfile_id,
    r.repository_name,
    COUNT(*) FILTER (
        WHERE i.instruction = 'RUN'
    ) AS run_count,
    COUNT(*) FILTER (
        WHERE i.instruction = 'ADD'
    ) AS add_count,
    COUNT(*) FILTER (
        WHERE i.instruction = 'FROM'
    ) AS stage_count,
    BOOL_OR(
        i.instruction = 'ENV'
        AND i.arguments ~* '(PASSWORD|SECRET|TOKEN|API_KEY)'
    ) AS possible_secret_exposure
FROM dockerfiles d
JOIN repositories r
    ON r.repository_id = d.repository_id
JOIN dockerfile_instructions i
    ON i.dockerfile_id = d.dockerfile_id
GROUP BY
    d.dockerfile_id,
    r.repository_name
ORDER BY r.repository_name;

-- ============================================================================
-- QUERY 11: RECURSIVE LAYER DEPENDENCY CHAIN
-- ============================================================================

WITH RECURSIVE layer_chain AS (
    SELECT
        layer_id,
        build_id,
        parent_layer_id,
        layer_number,
        1 AS depth
    FROM image_layers
    WHERE parent_layer_id IS NULL
      AND build_id = 1

    UNION ALL

    SELECT
        child.layer_id,
        child.build_id,
        child.parent_layer_id,
        child.layer_number,
        parent.depth + 1
    FROM image_layers child
    JOIN layer_chain parent
        ON child.parent_layer_id = parent.layer_id
    WHERE child.build_id = 1
)
SELECT
    layer_id,
    build_id,
    parent_layer_id,
    layer_number,
    depth
FROM layer_chain
ORDER BY depth;

-- ============================================================================
-- QUERY 12: REPOSITORY BUILD PERFORMANCE
-- ============================================================================

SELECT
    r.repository_name,
    COUNT(b.build_id) AS total_builds,
    COUNT(*) FILTER (
        WHERE b.build_status = 'BUILT'
    ) AS successful_builds,
    COUNT(*) FILTER (
        WHERE b.build_status = 'FAILED'
    ) AS failed_builds,
    ROUND(
        100.0 *
        COUNT(*) FILTER (
            WHERE b.build_status = 'BUILT'
        ) /
        NULLIF(COUNT(b.build_id), 0),
        2
    ) AS success_percentage
FROM repositories r
LEFT JOIN dockerfiles d
    ON d.repository_id = r.repository_id
LEFT JOIN image_builds b
    ON b.dockerfile_id = d.dockerfile_id
GROUP BY r.repository_id, r.repository_name
ORDER BY r.repository_name;

-- ============================================================================
-- TRANSACTION DEMONSTRATION: FAILED BUILD TRANSITION
-- ============================================================================

SAVEPOINT before_failed_build;

-- This transition is valid because the build is currently BUILT.
-- It is deliberately not executed because BUILT is a terminal state.

-- The following statement demonstrates an invalid transition.
-- It is isolated in a PL/pgSQL exception block so the script can continue.

DO $$
BEGIN
    BEGIN
        UPDATE image_builds
        SET build_status = 'BUILDING'
        WHERE build_id = 1;

    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE
                'Expected transition rejection: %',
                SQLERRM;
    END;
END;
$$;

-- ============================================================================
-- TRANSACTION DEMONSTRATION: ATOMIC POLICY DECISION
-- ============================================================================

SAVEPOINT before_policy_check;

DO $$
DECLARE
    eligibility RECORD;
BEGIN
    SELECT *
    INTO eligibility
    FROM evaluate_image_eligibility(1, 1);

    IF eligibility.eligible THEN
        RAISE NOTICE
            'Image is eligible for production publication.';
    ELSE
        RAISE NOTICE
            'Image rejected: %',
            eligibility.violations;
    END IF;
END;
$$;

RELEASE SAVEPOINT before_policy_check;

-- The sample records remain available for subsequent reporting.
COMMIT;

RESET search_path;
