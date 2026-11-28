-- ============================================================
-- DEPLOYMENTS AND REPLICASETS
-- Declarative deployment, replica reconciliation,
-- rolling updates, rollbacks, and deployment reporting.
--
-- PostgreSQL 15+
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS orchestration;

SET search_path TO orchestration, public;

-- ------------------------------------------------------------
-- Domain types
-- ------------------------------------------------------------

CREATE TYPE deployment_phase AS ENUM (
    'PROGRESSING',
    'AVAILABLE',
    'DEGRADED',
    'PAUSED'
);

CREATE TYPE pod_phase AS ENUM (
    'PENDING',
    'RUNNING',
    'READY',
    'FAILED',
    'TERMINATING'
);

CREATE TYPE rollout_strategy AS ENUM (
    'ROLLING_UPDATE',
    'RECREATE'
);

CREATE TYPE deployment_event_type AS ENUM (
    'CREATED',
    'SPEC_UPDATED',
    'REPLICA_SET_CREATED',
    'SCALED',
    'POD_READY',
    'POD_FAILED',
    'ROLLOUT_STARTED',
    'ROLLOUT_COMPLETED',
    'ROLLOUT_FAILED',
    'ROLLBACK_STARTED',
    'PAUSED',
    'RESUMED',
    'DELETED'
);

-- ------------------------------------------------------------
-- Namespaces and container images
-- ------------------------------------------------------------

CREATE TABLE namespaces (
    namespace_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(63) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT namespace_name_valid CHECK (
        name ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'
    )
);

CREATE TABLE container_images (
    image_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    registry VARCHAR(255) NOT NULL,
    repository VARCHAR(255) NOT NULL,
    tag VARCHAR(128) NOT NULL,
    digest VARCHAR(128),
    approved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT image_reference_unique
        UNIQUE (registry, repository, tag),

    CONSTRAINT image_registry_nonempty
        CHECK (LENGTH(registry) > 0),

    CONSTRAINT image_repository_nonempty
        CHECK (LENGTH(repository) > 0),

    CONSTRAINT image_tag_nonempty
        CHECK (LENGTH(tag) > 0)
);

CREATE TABLE image_security_scans (
    scan_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    image_id BIGINT NOT NULL REFERENCES container_images(image_id),
    scanner_name VARCHAR(100) NOT NULL,
    scan_status VARCHAR(20) NOT NULL,
    critical_count INTEGER NOT NULL DEFAULT 0,
    high_count INTEGER NOT NULL DEFAULT 0,
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT scan_status_valid CHECK (
        scan_status IN ('PASSED', 'FAILED', 'PENDING')
    ),

    CONSTRAINT vulnerability_counts_valid CHECK (
        critical_count >= 0 AND high_count >= 0
    )
);

-- ------------------------------------------------------------
-- Deployments
-- ------------------------------------------------------------

CREATE TABLE deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    namespace_id BIGINT NOT NULL REFERENCES namespaces(namespace_id),
    name VARCHAR(63) NOT NULL,
    desired_replicas INTEGER NOT NULL,
    current_image_id BIGINT NOT NULL REFERENCES container_images(image_id),
    container_name VARCHAR(63) NOT NULL,
    container_port INTEGER NOT NULL DEFAULT 8080,
    max_surge INTEGER NOT NULL DEFAULT 1,
    max_unavailable INTEGER NOT NULL DEFAULT 0,
    revision_history_limit INTEGER NOT NULL DEFAULT 5,
    strategy rollout_strategy NOT NULL DEFAULT 'ROLLING_UPDATE',
    phase deployment_phase NOT NULL DEFAULT 'PROGRESSING',
    paused BOOLEAN NOT NULL DEFAULT FALSE,
    generation BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT deployment_name_valid CHECK (
        name ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'
    ),

    CONSTRAINT container_name_valid CHECK (
        container_name ~ '^[a-z][a-z0-9-]*$'
    ),

    CONSTRAINT desired_replicas_valid CHECK (
        desired_replicas BETWEEN 0 AND 10000
    ),

    CONSTRAINT max_surge_valid CHECK (
        max_surge BETWEEN 0 AND 1000
    ),

    CONSTRAINT max_unavailable_valid CHECK (
        max_unavailable BETWEEN 0 AND desired_replicas
    ),

    CONSTRAINT container_port_valid CHECK (
        container_port BETWEEN 1 AND 65535
    ),

    CONSTRAINT revision_history_valid CHECK (
        revision_history_limit BETWEEN 1 AND 100
    ),

    CONSTRAINT deployment_namespace_name_unique
        UNIQUE (namespace_id, name)
);

CREATE INDEX idx_deployments_namespace_phase
    ON deployments(namespace_id, phase);

CREATE INDEX idx_deployments_updated
    ON deployments(updated_at DESC);

-- ------------------------------------------------------------
-- ReplicaSets
-- ------------------------------------------------------------

CREATE TABLE replica_sets (
    replica_set_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    image_id BIGINT NOT NULL REFERENCES container_images(image_id),
    desired_replicas INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT replica_revision_positive CHECK (revision > 0),
    CONSTRAINT replica_desired_valid CHECK (
        desired_replicas BETWEEN 0 AND 10000
    ),

    CONSTRAINT deployment_revision_unique
        UNIQUE (deployment_id, revision)
);

CREATE INDEX idx_replica_sets_deployment_revision
    ON replica_sets(deployment_id, revision DESC);

CREATE INDEX idx_replica_sets_image
    ON replica_sets(image_id);

-- ------------------------------------------------------------
-- Pods
-- ------------------------------------------------------------

CREATE TABLE pods (
    pod_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    replica_set_id BIGINT NOT NULL
        REFERENCES replica_sets(replica_set_id) ON DELETE CASCADE,
    pod_name VARCHAR(128) NOT NULL UNIQUE,
    phase pod_phase NOT NULL DEFAULT 'PENDING',
    node_name VARCHAR(128),
    restart_count INTEGER NOT NULL DEFAULT 0,
    ready_since TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT restart_count_valid CHECK (restart_count >= 0)
);

CREATE INDEX idx_pods_replica_set_phase
    ON pods(replica_set_id, phase);

CREATE INDEX idx_pods_phase
    ON pods(phase);

CREATE INDEX idx_pods_ready
    ON pods(replica_set_id)
    WHERE phase = 'READY';

-- ------------------------------------------------------------
-- Deployment revision history
-- ------------------------------------------------------------

CREATE TABLE deployment_revisions (
    revision_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    image_id BIGINT NOT NULL REFERENCES container_images(image_id),
    desired_replicas INTEGER NOT NULL,
    strategy rollout_strategy NOT NULL,
    change_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT revision_number_valid CHECK (revision > 0),
    CONSTRAINT revision_replicas_valid CHECK (desired_replicas >= 0),
    CONSTRAINT deployment_revision_history_unique
        UNIQUE (deployment_id, revision)
);

CREATE INDEX idx_revision_history
    ON deployment_revisions(deployment_id, revision DESC);

-- ------------------------------------------------------------
-- Rollout operations
-- ------------------------------------------------------------

CREATE TABLE rollout_operations (
    rollout_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id) ON DELETE CASCADE,
    source_revision INTEGER,
    target_revision INTEGER NOT NULL,
    operation_type VARCHAR(20) NOT NULL,
    operation_status VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    failure_reason TEXT,

    CONSTRAINT operation_type_valid CHECK (
        operation_type IN ('UPDATE', 'ROLLBACK', 'RECREATE')
    ),

    CONSTRAINT operation_status_valid CHECK (
        operation_status IN ('RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')
    ),

    CONSTRAINT rollout_target_revision_valid CHECK (
        target_revision > 0
    )
);

CREATE INDEX idx_rollout_operations_deployment
    ON rollout_operations(deployment_id, started_at DESC);

-- ------------------------------------------------------------
-- Events and audit records
-- ------------------------------------------------------------

CREATE TABLE deployment_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id) ON DELETE CASCADE,
    replica_set_id BIGINT REFERENCES replica_sets(replica_set_id),
    pod_id BIGINT REFERENCES pods(pod_id),
    event_type deployment_event_type NOT NULL,
    message TEXT NOT NULL,
    event_data JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_deployment_events_history
    ON deployment_events(deployment_id, created_at DESC);

CREATE INDEX idx_deployment_events_type
    ON deployment_events(event_type, created_at DESC);

-- ------------------------------------------------------------
-- Database functions
-- ------------------------------------------------------------

CREATE FUNCTION active_replica_count(p_replica_set_id BIGINT)
RETURNS INTEGER
LANGUAGE SQL
STABLE
AS $$
    SELECT COUNT(*)::INTEGER
    FROM pods
    WHERE replica_set_id = p_replica_set_id
      AND phase IN ('PENDING', 'RUNNING', 'READY');
$$;

CREATE FUNCTION ready_replica_count(p_replica_set_id BIGINT)
RETURNS INTEGER
LANGUAGE SQL
STABLE
AS $$
    SELECT COUNT(*)::INTEGER
    FROM pods
    WHERE replica_set_id = p_replica_set_id
      AND phase = 'READY';
$$;

CREATE FUNCTION deployment_ready_count(p_deployment_id BIGINT)
RETURNS INTEGER
LANGUAGE SQL
STABLE
AS $$
    SELECT COUNT(*)::INTEGER
    FROM pods p
    JOIN replica_sets rs
      ON rs.replica_set_id = p.replica_set_id
    WHERE rs.deployment_id = p_deployment_id
      AND p.phase = 'READY';
$$;

CREATE FUNCTION deployment_active_count(p_deployment_id BIGINT)
RETURNS INTEGER
LANGUAGE SQL
STABLE
AS $$
    SELECT COUNT(*)::INTEGER
    FROM pods p
    JOIN replica_sets rs
      ON rs.replica_set_id = p.replica_set_id
    WHERE rs.deployment_id = p_deployment_id
      AND p.phase IN ('PENDING', 'RUNNING', 'READY');
$$;

-- ------------------------------------------------------------
-- Audit trigger
-- ------------------------------------------------------------

CREATE FUNCTION log_deployment_changes()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        INSERT INTO deployment_events (
            deployment_id,
            event_type,
            message,
            event_data
        )
        VALUES (
            NEW.deployment_id,
            'SPEC_UPDATED',
            'Deployment specification changed',
            jsonb_build_object(
                'old_replicas', OLD.desired_replicas,
                'new_replicas', NEW.desired_replicas,
                'old_generation', OLD.generation,
                'new_generation', NEW.generation,
                'old_phase', OLD.phase,
                'new_phase', NEW.phase
            )
        );

        NEW.updated_at = NOW();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_deployment_audit
BEFORE UPDATE ON deployments
FOR EACH ROW
EXECUTE FUNCTION log_deployment_changes();

-- ------------------------------------------------------------
-- Revision creation function
-- ------------------------------------------------------------

CREATE FUNCTION create_deployment_revision(
    p_deployment_id BIGINT,
    p_image_id BIGINT,
    p_reason TEXT DEFAULT 'Image update'
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_revision INTEGER;
    v_replicas INTEGER;
    v_strategy rollout_strategy;
BEGIN
    SELECT COALESCE(MAX(revision), 0) + 1
    INTO v_revision
    FROM replica_sets
    WHERE deployment_id = p_deployment_id;

    SELECT desired_replicas, strategy
    INTO v_replicas, v_strategy
    FROM deployments
    WHERE deployment_id = p_deployment_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Deployment % does not exist',
            p_deployment_id;
    END IF;

    INSERT INTO replica_sets (
        deployment_id,
        revision,
        image_id,
        desired_replicas
    )
    VALUES (
        p_deployment_id,
        v_revision,
        p_image_id,
        0
    );

    INSERT INTO deployment_revisions (
        deployment_id,
        revision,
        image_id,
        desired_replicas,
        strategy,
        change_reason
    )
    VALUES (
        p_deployment_id,
        v_revision,
        p_image_id,
        v_replicas,
        v_strategy,
        p_reason
    );

    INSERT INTO deployment_events (
        deployment_id,
        event_type,
        message,
        event_data
    )
    VALUES (
        p_deployment_id,
        'REPLICA_SET_CREATED',
        'New ReplicaSet created',
        jsonb_build_object(
            'revision', v_revision,
            'image_id', p_image_id,
            'reason', p_reason
        )
    );

    UPDATE deployments
    SET current_image_id = p_image_id,
        generation = generation + 1,
        phase = 'PROGRESSING'
    WHERE deployment_id = p_deployment_id;

    RETURN v_revision;
END;
$$;

-- ------------------------------------------------------------
-- Deployment creation procedure
-- ------------------------------------------------------------

CREATE PROCEDURE create_deployment(
    p_namespace_name VARCHAR(63),
    p_name VARCHAR(63),
    p_replicas INTEGER,
    p_image_id BIGINT,
    p_container_name VARCHAR(63),
    p_port INTEGER DEFAULT 8080,
    p_max_surge INTEGER DEFAULT 1,
    p_max_unavailable INTEGER DEFAULT 0
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_namespace_id BIGINT;
    v_deployment_id BIGINT;
BEGIN
    SELECT namespace_id
    INTO v_namespace_id
    FROM namespaces
    WHERE name = p_namespace_name;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Namespace % not found',
            p_namespace_name;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM container_images
        WHERE image_id = p_image_id
          AND approved = TRUE
    ) THEN
        RAISE EXCEPTION 'Container image is not approved';
    END IF;

    INSERT INTO deployments (
        namespace_id,
        name,
        desired_replicas,
        current_image_id,
        container_name,
        container_port,
        max_surge,
        max_unavailable
    )
    VALUES (
        v_namespace_id,
        p_name,
        p_replicas,
        p_image_id,
        p_container_name,
        p_port,
        p_max_surge,
        p_max_unavailable
    )
    RETURNING deployment_id INTO v_deployment_id;

    PERFORM create_deployment_revision(
        v_deployment_id,
        p_image_id,
        'Initial deployment'
    );

    INSERT INTO deployment_events (
        deployment_id,
        event_type,
        message
    )
    VALUES (
        v_deployment_id,
        'CREATED',
        'Deployment created'
    );
END;
$$;

-- ------------------------------------------------------------
-- Pod creation and readiness
-- ------------------------------------------------------------

CREATE PROCEDURE create_pod(
    p_replica_set_id BIGINT,
    p_pod_name VARCHAR(128),
    p_node_name VARCHAR(128) DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_deployment_id BIGINT;
BEGIN
    SELECT deployment_id
    INTO v_deployment_id
    FROM replica_sets
    WHERE replica_set_id = p_replica_set_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'ReplicaSet not found';
    END IF;

    INSERT INTO pods (
        replica_set_id,
        pod_name,
        node_name,
        phase
    )
    VALUES (
        p_replica_set_id,
        p_pod_name,
        p_node_name,
        'PENDING'
    );

    INSERT INTO deployment_events (
        deployment_id,
        replica_set_id,
        event_type,
        message
    )
    VALUES (
        v_deployment_id,
        p_replica_set_id,
        'SCALED',
        'Pod created: ' || p_pod_name
    );
END;
$$;

CREATE PROCEDURE mark_pod_ready(p_pod_id BIGINT)
LANGUAGE plpgsql
AS $$
DECLARE
    v_deployment_id BIGINT;
    v_replica_set_id BIGINT;
    v_phase pod_phase;
BEGIN
    SELECT rs.deployment_id, p.replica_set_id, p.phase
    INTO v_deployment_id, v_replica_set_id, v_phase
    FROM pods p
    JOIN replica_sets rs
      ON rs.replica_set_id = p.replica_set_id
    WHERE p.pod_id = p_pod_id
    FOR UPDATE OF p;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pod not found';
    END IF;

    IF v_phase NOT IN ('PENDING', 'RUNNING') THEN
        RAISE EXCEPTION 'Invalid Pod transition from %', v_phase;
    END IF;

    UPDATE pods
    SET phase = 'READY',
        ready_since = NOW(),
        updated_at = NOW()
    WHERE pod_id = p_pod_id;

    INSERT INTO deployment_events (
        deployment_id,
        replica_set_id,
        pod_id,
        event_type,
        message
    )
    VALUES (
        v_deployment_id,
        v_replica_set_id,
        p_pod_id,
        'POD_READY',
        'Pod passed readiness'
    );
END;
$$;

-- ------------------------------------------------------------
-- Declarative scaling procedure
-- ------------------------------------------------------------

CREATE PROCEDURE scale_deployment(
    p_deployment_id BIGINT,
    p_desired_replicas INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_current_revision INTEGER;
    v_current_rs BIGINT;
    v_total INTEGER;
    v_missing INTEGER;
    v_capacity INTEGER;
    v_create INTEGER;
    v_surge INTEGER;
    v_paused BOOLEAN;
BEGIN
    IF p_desired_replicas < 0 OR p_desired_replicas > 10000 THEN
        RAISE EXCEPTION 'Invalid desired replica count';
    END IF;

    SELECT paused, max_surge
    INTO v_paused, v_surge
    FROM deployments
    WHERE deployment_id = p_deployment_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Deployment not found';
    END IF;

    IF v_paused THEN
        RAISE EXCEPTION 'Deployment is paused';
    END IF;

    UPDATE deployments
    SET desired_replicas = p_desired_replicas,
        generation = generation + 1
    WHERE deployment_id = p_deployment_id;

    SELECT replica_set_id, revision
    INTO v_current_rs, v_current_revision
    FROM replica_sets
    WHERE deployment_id = p_deployment_id
    ORDER BY revision DESC
    LIMIT 1
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'No ReplicaSet found';
    END IF;

    UPDATE replica_sets
    SET desired_replicas = CASE
        WHEN replica_set_id = v_current_rs
        THEN p_desired_replicas
        ELSE 0
    END
    WHERE deployment_id = p_deployment_id;

    SELECT deployment_active_count(p_deployment_id)
    INTO v_total;

    v_missing := GREATEST(
        0,
        p_desired_replicas -
        active_replica_count(v_current_rs)
    );

    v_capacity := GREATEST(
        0,
        p_desired_replicas + v_surge - v_total
    );

    v_create := LEAST(v_missing, v_capacity);

    FOR i IN 1..v_create LOOP
        INSERT INTO pods (
            replica_set_id,
            pod_name,
            phase
        )
        VALUES (
            v_current_rs,
            'pod-' || p_deployment_id || '-' ||
                v_current_revision || '-' ||
                gen_random_uuid()::TEXT,
            'PENDING'
        );
    END LOOP;

    INSERT INTO deployment_events (
        deployment_id,
        event_type,
        message,
        event_data
    )
    VALUES (
        p_deployment_id,
        'SCALED',
        'Deployment reconciled',
        jsonb_build_object(
            'desired', p_desired_replicas,
            'created', v_create,
            'active_before', v_total
        )
    );
END;
$$;

-- ------------------------------------------------------------
-- Rolling update procedure
-- ------------------------------------------------------------

CREATE PROCEDURE start_rolling_update(
    p_deployment_id BIGINT,
    p_new_image_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_old_revision INTEGER;
    v_new_revision INTEGER;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM container_images
        WHERE image_id = p_new_image_id
          AND approved = TRUE
    ) THEN
        RAISE EXCEPTION 'New image is not approved';
    END IF;

    SELECT MAX(revision)
    INTO v_old_revision
    FROM replica_sets
    WHERE deployment_id = p_deployment_id;

    IF v_old_revision IS NULL THEN
        RAISE EXCEPTION 'Deployment has no revision history';
    END IF;

    INSERT INTO rollout_operations (
        deployment_id,
        source_revision,
        target_revision,
        operation_type,
        operation_status
    )
    VALUES (
        p_deployment_id,
        v_old_revision,
        v_old_revision + 1,
        'UPDATE',
        'RUNNING'
    );

    PERFORM create_deployment_revision(
        p_deployment_id,
        p_new_image_id,
        'Rolling update'
    );

    SELECT MAX(revision)
    INTO v_new_revision
    FROM replica_sets
    WHERE deployment_id = p_deployment_id;

    INSERT INTO deployment_events (
        deployment_id,
        event_type,
        message,
        event_data
    )
    VALUES (
        p_deployment_id,
        'ROLLOUT_STARTED',
        'Rolling update started',
        jsonb_build_object(
            'source_revision', v_old_revision,
            'target_revision', v_new_revision
        )
    );
END;
$$;

-- ------------------------------------------------------------
-- Rollback procedure
-- ------------------------------------------------------------

CREATE PROCEDURE rollback_deployment(
    p_deployment_id BIGINT,
    p_target_revision INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_target_image BIGINT;
    v_current_revision INTEGER;
    v_new_revision INTEGER;
BEGIN
    SELECT MAX(revision)
    INTO v_current_revision
    FROM replica_sets
    WHERE deployment_id = p_deployment_id
    FOR UPDATE;

    SELECT image_id
    INTO v_target_image
    FROM deployment_revisions
    WHERE deployment_id = p_deployment_id
      AND revision = p_target_revision;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Target revision does not exist';
    END IF;

    IF p_target_revision >= v_current_revision THEN
        RAISE EXCEPTION 'Rollback must target an older revision';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM container_images
        WHERE image_id = v_target_image
          AND approved = TRUE
    ) THEN
        RAISE EXCEPTION 'Historical image is not approved';
    END IF;

    INSERT INTO rollout_operations (
        deployment_id,
        source_revision,
        target_revision,
        operation_type,
        operation_status
    )
    VALUES (
        p_deployment_id,
        v_current_revision,
        p_target_revision,
        'ROLLBACK',
        'RUNNING'
    );

    -- A rollback creates a new revision with the old image.
    PERFORM create_deployment_revision(
        p_deployment_id,
        v_target_image,
        'Rollback to revision ' || p_target_revision
    );

    SELECT MAX(revision)
    INTO v_new_revision
    FROM replica_sets
    WHERE deployment_id = p_deployment_id;

    INSERT INTO deployment_events (
        deployment_id,
        event_type,
        message,
        event_data
    )
    VALUES (
        p_deployment_id,
        'ROLLBACK_STARTED',
        'Rollback initiated',
        jsonb_build_object(
            'historical_revision', p_target_revision,
            'new_revision', v_new_revision
        )
    );
END;
$$;

-- ------------------------------------------------------------
-- Eligibility and deployment evaluation view
-- ------------------------------------------------------------

CREATE VIEW deployment_status_report AS
WITH replica_counts AS (
    SELECT
        d.deployment_id,
        d.name,
        n.name AS namespace,
        d.desired_replicas,
        d.phase,
        d.generation,
        COUNT(p.pod_id) FILTER (
            WHERE p.phase IN ('PENDING', 'RUNNING', 'READY')
        ) AS active_replicas,
        COUNT(p.pod_id) FILTER (
            WHERE p.phase = 'READY'
        ) AS ready_replicas,
        COUNT(p.pod_id) FILTER (
            WHERE p.phase = 'FAILED'
        ) AS failed_replicas
    FROM deployments d
    JOIN namespaces n
      ON n.namespace_id = d.namespace_id
    LEFT JOIN replica_sets rs
      ON rs.deployment_id = d.deployment_id
    LEFT JOIN pods p
      ON p.replica_set_id = rs.replica_set_id
    GROUP BY
        d.deployment_id,
        d.name,
        n.name,
        d.desired_replicas,
        d.phase,
        d.generation
)
SELECT
    *,
    CASE
        WHEN desired_replicas = 0 THEN 'AVAILABLE'
        WHEN ready_replicas >= desired_replicas THEN 'AVAILABLE'
        WHEN failed_replicas > 0 THEN 'DEGRADED'
        ELSE 'PROGRESSING'
    END AS evaluated_phase,
    ready_replicas >= desired_replicas AS replica_target_met
FROM replica_counts;

-- ------------------------------------------------------------
-- ReplicaSet revision report
-- ------------------------------------------------------------

CREATE VIEW replica_set_report AS
SELECT
    d.deployment_id,
    d.name AS deployment_name,
    n.name AS namespace,
    rs.replica_set_id,
    rs.revision,
    ci.registry || '/' || ci.repository || ':' || ci.tag AS image,
    rs.desired_replicas,
    COUNT(p.pod_id) FILTER (
        WHERE p.phase IN ('PENDING', 'RUNNING', 'READY')
    ) AS active_replicas,
    COUNT(p.pod_id) FILTER (
        WHERE p.phase = 'READY'
    ) AS ready_replicas,
    COUNT(p.pod_id) FILTER (
        WHERE p.phase = 'FAILED'
    ) AS failed_replicas
FROM deployments d
JOIN namespaces n
  ON n.namespace_id = d.namespace_id
JOIN replica_sets rs
  ON rs.deployment_id = d.deployment_id
JOIN container_images ci
  ON ci.image_id = rs.image_id
LEFT JOIN pods p
  ON p.replica_set_id = rs.replica_set_id
GROUP BY
    d.deployment_id,
    d.name,
    n.name,
    rs.replica_set_id,
    rs.revision,
    ci.registry,
    ci.repository,
    ci.tag,
    rs.desired_replicas;

-- ------------------------------------------------------------
-- Eligibility function
-- ------------------------------------------------------------

CREATE FUNCTION deployment_eligibility(p_deployment_id BIGINT)
RETURNS TABLE (
    deployment_name VARCHAR,
    desired INTEGER,
    ready INTEGER,
    active INTEGER,
    eligible BOOLEAN,
    reason TEXT
)
LANGUAGE SQL
STABLE
AS $$
    SELECT
        d.name::VARCHAR,
        d.desired_replicas,
        deployment_ready_count(d.deployment_id),
        deployment_active_count(d.deployment_id),
        (
            NOT d.paused
            AND deployment_ready_count(d.deployment_id)
                >= d.desired_replicas
        ),
        CASE
            WHEN d.paused THEN 'Deployment is paused'
            WHEN deployment_ready_count(d.deployment_id)
                >= d.desired_replicas THEN 'Replica target satisfied'
            ELSE 'Waiting for ready replicas'
        END::TEXT
    FROM deployments d
    WHERE d.deployment_id = p_deployment_id;
$$;

-- ------------------------------------------------------------
-- Seed data
-- ------------------------------------------------------------

INSERT INTO namespaces (name)
VALUES
    ('production'),
    ('staging'),
    ('development');

INSERT INTO container_images (
    registry,
    repository,
    tag,
    approved
)
VALUES
    ('registry.example.com', 'inventory-api', 'v1', TRUE),
    ('registry.example.com', 'inventory-api', 'v2', TRUE),
    ('registry.example.com', 'inventory-api', 'v3', TRUE),
    ('registry.example.com', 'payment-api', 'v1', TRUE),
    ('registry.untrusted.com', 'inventory-api', 'unsafe', FALSE);

INSERT INTO image_security_scans (
    image_id,
    scanner_name,
    scan_status,
    critical_count,
    high_count
)
SELECT
    image_id,
    'enterprise-image-scanner',
    CASE
        WHEN approved THEN 'PASSED'
        ELSE 'FAILED'
    END,
    0,
    CASE WHEN approved THEN 0 ELSE 4 END
FROM container_images;

-- ------------------------------------------------------------
-- Transactional sample deployment
-- ------------------------------------------------------------

DO $$
DECLARE
    v_image BIGINT;
    v_deployment BIGINT;
    v_replica_set BIGINT;
BEGIN
    SELECT image_id
    INTO v_image
    FROM container_images
    WHERE repository = 'inventory-api'
      AND tag = 'v1';

    CALL create_deployment(
        'production',
        'inventory-api',
        3,
        v_image,
        'inventory',
        8080,
        1,
        0
    );

    SELECT deployment_id
    INTO v_deployment
    FROM deployments
    WHERE name = 'inventory-api';

    SELECT replica_set_id
    INTO v_replica_set
    FROM replica_sets
    WHERE deployment_id = v_deployment
    ORDER BY revision DESC
    LIMIT 1;

    CALL create_pod(
        v_replica_set,
        'inventory-v1-pod-001',
        'worker-01'
    );

    CALL create_pod(
        v_replica_set,
        'inventory-v1-pod-002',
        'worker-02'
    );

    CALL create_pod(
        v_replica_set,
        'inventory-v1-pod-003',
        'worker-03'
    );

    UPDATE deployments
    SET phase = 'PROGRESSING'
    WHERE deployment_id = v_deployment;
END;
$$;

COMMIT;

-- ------------------------------------------------------------
-- Retrieval
-- ------------------------------------------------------------

SELECT *
FROM deployment_status_report
ORDER BY namespace, name;

SELECT *
FROM replica_set_report
ORDER BY deployment_name, revision;

-- ------------------------------------------------------------
-- Validation
-- ------------------------------------------------------------

SELECT
    d.name,
    ci.registry,
    ci.repository,
    ci.tag,
    ci.approved,
    s.scan_status,
    s.critical_count,
    s.high_count
FROM deployments d
JOIN container_images ci
  ON ci.image_id = d.current_image_id
LEFT JOIN image_security_scans s
  ON s.image_id = ci.image_id
ORDER BY d.name;

-- ------------------------------------------------------------
-- Aggregation
-- ------------------------------------------------------------

SELECT
    n.name AS namespace,
    COUNT(DISTINCT d.deployment_id) AS deployments,
    SUM(d.desired_replicas) AS desired_replicas,
    SUM(deployment_ready_count(d.deployment_id)) AS ready_replicas,
    SUM(deployment_active_count(d.deployment_id)) AS active_replicas
FROM namespaces n
LEFT JOIN deployments d
  ON d.namespace_id = n.namespace_id
GROUP BY n.name
ORDER BY n.name;

-- ------------------------------------------------------------
-- Evaluation
-- ------------------------------------------------------------

SELECT *
FROM deployment_eligibility(
    (
        SELECT deployment_id
        FROM deployments
        WHERE name = 'inventory-api'
    )
);

-- ------------------------------------------------------------
-- Workflow processing: mark Pods ready
-- ------------------------------------------------------------

DO $$
DECLARE
    v_pod BIGINT;
BEGIN
    FOR v_pod IN
        SELECT p.pod_id
        FROM pods p
        JOIN replica_sets rs
          ON rs.replica_set_id = p.replica_set_id
        JOIN deployments d
          ON d.deployment_id = rs.deployment_id
        WHERE d.name = 'inventory-api'
          AND p.phase IN ('PENDING', 'RUNNING')
    LOOP
        CALL mark_pod_ready(v_pod);
    END LOOP;
END;
$$;

-- ------------------------------------------------------------
-- Demonstrate scaling
-- ------------------------------------------------------------

DO $$
DECLARE
    v_deployment BIGINT;
BEGIN
    SELECT deployment_id
    INTO v_deployment
    FROM deployments
    WHERE name = 'inventory-api';

    CALL scale_deployment(v_deployment, 4);
END;
$$;

-- ------------------------------------------------------------
-- Demonstrate rolling update
-- ------------------------------------------------------------

DO $$
DECLARE
    v_deployment BIGINT;
    v_image BIGINT;
BEGIN
    SELECT deployment_id
    INTO v_deployment
    FROM deployments
    WHERE name = 'inventory-api';

    SELECT image_id
    INTO v_image
    FROM container_images
    WHERE repository = 'inventory-api'
      AND tag = 'v2';

    CALL start_rolling_update(v_deployment, v_image);
END;
$$;

-- ------------------------------------------------------------
-- Demonstrate rollback logic in a separate transaction.
-- The selected revision must be older than the current revision.
-- ------------------------------------------------------------

-- Execute after inspecting deployment revisions:
--
-- BEGIN;
-- CALL rollback_deployment(1, 1);
-- COMMIT;

-- ------------------------------------------------------------
-- Reporting: rollout history
-- ------------------------------------------------------------

SELECT
    d.name,
    r.revision,
    ci.registry || '/' || ci.repository || ':' || ci.tag AS image,
    r.desired_replicas,
    r.change_reason,
    r.created_at
FROM deployment_revisions r
JOIN deployments d
  ON d.deployment_id = r.deployment_id
JOIN container_images ci
  ON ci.image_id = r.image_id
ORDER BY d.name, r.revision DESC;

-- ------------------------------------------------------------
-- Reporting: operational events
-- ------------------------------------------------------------

SELECT
    d.name,
    e.event_type,
    e.message,
    e.event_data,
    e.created_at
FROM deployment_events e
JOIN deployments d
  ON d.deployment_id = e.deployment_id
ORDER BY e.created_at DESC;

-- ------------------------------------------------------------
-- Reporting: failed Pods
-- ------------------------------------------------------------

SELECT
    d.name AS deployment,
    rs.revision,
    p.pod_name,
    p.restart_count,
    p.created_at
FROM pods p
JOIN replica_sets rs
  ON rs.replica_set_id = p.replica_set_id
JOIN deployments d
  ON d.deployment_id = rs.deployment_id
WHERE p.phase = 'FAILED'
ORDER BY p.created_at DESC;

-- ------------------------------------------------------------
-- Reporting: ReplicaSet capacity and surge utilization
-- ------------------------------------------------------------

SELECT
    d.name,
    d.desired_replicas,
    d.max_surge,
    deployment_active_count(d.deployment_id) AS active_replicas,
    d.desired_replicas + d.max_surge AS surge_limit,
    GREATEST(
        0,
        deployment_active_count(d.deployment_id)
        - d.desired_replicas
    ) AS surge_in_use,
    deployment_ready_count(d.deployment_id) AS ready_replicas
FROM deployments d;

-- ------------------------------------------------------------
-- Reporting: latest revision per deployment using a CTE
-- ------------------------------------------------------------

WITH latest_revisions AS (
    SELECT
        deployment_id,
        MAX(revision) AS latest_revision
    FROM replica_sets
    GROUP BY deployment_id
)
SELECT
    d.name,
    lr.latest_revision,
    rs.replica_set_id,
    ci.repository,
    ci.tag
FROM latest_revisions lr
JOIN deployments d
  ON d.deployment_id = lr.deployment_id
JOIN replica_sets rs
  ON rs.deployment_id = lr.deployment_id
 AND rs.revision = lr.latest_revision
JOIN container_images ci
  ON ci.image_id = rs.image_id;

-- ------------------------------------------------------------
-- Failed and incomplete rollout inspection
-- ------------------------------------------------------------

SELECT
    d.name,
    ro.rollout_id,
    ro.operation_type,
    ro.operation_status,
    ro.source_revision,
    ro.target_revision,
    ro.failure_reason,
    ro.started_at
FROM rollout_operations ro
JOIN deployments d
  ON d.deployment_id = ro.deployment_id
WHERE ro.operation_status IN ('RUNNING', 'FAILED')
ORDER BY ro.started_at DESC;

-- ------------------------------------------------------------
-- Production query optimization inspection
-- ------------------------------------------------------------

EXPLAIN
SELECT
    replica_set_id,
    COUNT(*)
FROM pods
WHERE phase = 'READY'
GROUP BY replica_set_id;

-- ------------------------------------------------------------
-- Transaction failure demonstration
-- The invalid operation is rolled back without modifying data.
-- ------------------------------------------------------------

BEGIN;

SAVEPOINT before_invalid_scaling;

DO $$
BEGIN
    BEGIN
        CALL scale_deployment(1, -5);
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Expected validation failure: %', SQLERRM;
    END;
END;
$$;

ROLLBACK TO SAVEPOINT before_invalid_scaling;
COMMIT;
