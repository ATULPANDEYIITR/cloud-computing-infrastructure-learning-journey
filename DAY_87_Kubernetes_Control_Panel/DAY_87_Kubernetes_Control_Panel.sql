/*
============================================================
KUBERNETES CONTROL PLANE
PostgreSQL cluster-state management model
============================================================

Models:
1. API server resource registration
2. etcd-style versioned state persistence
3. Nodes and resource capacity
4. Deployments and desired state
5. Pods and scheduling
6. Controllers and reconciliation
7. Resource reservations
8. Cluster events and audit history
9. Optimistic concurrency
10. Cluster health and reporting

Target: PostgreSQL 15+
============================================================
*/


BEGIN;

CREATE SCHEMA IF NOT EXISTS k8s;

SET search_path TO k8s, public;


-- =========================================================
-- ENUMERATIONS
-- =========================================================

CREATE TYPE node_condition AS ENUM (
    'Ready',
    'NotReady'
);

CREATE TYPE pod_phase AS ENUM (
    'Pending',
    'Running',
    'Failed',
    'Succeeded'
);

CREATE TYPE resource_kind AS ENUM (
    'Node',
    'Deployment',
    'Pod'
);

CREATE TYPE event_type AS ENUM (
    'CREATED',
    'UPDATED',
    'DELETED',
    'SCHEDULED',
    'UNSCHEDULABLE',
    'RECONCILED',
    'FAILED'
);


-- =========================================================
-- RESOURCE VERSION SEQUENCE
-- =========================================================

CREATE SEQUENCE cluster_revision_seq
    AS BIGINT
    START WITH 1
    INCREMENT BY 1;


-- =========================================================
-- RESOURCE REGISTRY
-- =========================================================

CREATE TABLE resources (
    resource_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    resource_kind resource_kind NOT NULL,

    namespace VARCHAR(63) NOT NULL DEFAULT 'default',

    resource_name VARCHAR(253) NOT NULL,

    resource_version BIGINT NOT NULL DEFAULT 0,

    generation BIGINT NOT NULL DEFAULT 1,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        resource_kind,
        namespace,
        resource_name
    ),

    CHECK (resource_version >= 0),

    CHECK (generation >= 1),

    CHECK (
        resource_name ~
        '^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'
    ),

    CHECK (
        namespace ~
        '^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'
    )
);


-- =========================================================
-- NODES
-- =========================================================

CREATE TABLE nodes (
    resource_id UUID PRIMARY KEY
        REFERENCES resources(resource_id)
        ON DELETE CASCADE,

    cpu_capacity INTEGER NOT NULL,

    memory_capacity_mb INTEGER NOT NULL,

    cpu_allocated INTEGER NOT NULL DEFAULT 0,

    memory_allocated_mb INTEGER NOT NULL DEFAULT 0,

    condition node_condition NOT NULL DEFAULT 'Ready',

    kubelet_version VARCHAR(50),

    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (cpu_capacity > 0),

    CHECK (memory_capacity_mb > 0),

    CHECK (cpu_allocated >= 0),

    CHECK (memory_allocated_mb >= 0),

    CHECK (cpu_allocated <= cpu_capacity),

    CHECK (memory_allocated_mb <= memory_capacity_mb)
);


-- =========================================================
-- DEPLOYMENTS
-- =========================================================

CREATE TABLE deployments (
    resource_id UUID PRIMARY KEY
        REFERENCES resources(resource_id)
        ON DELETE CASCADE,

    desired_replicas INTEGER NOT NULL,

    observed_replicas INTEGER NOT NULL DEFAULT 0,

    ready_replicas INTEGER NOT NULL DEFAULT 0,

    container_image TEXT NOT NULL,

    cpu_request INTEGER NOT NULL,

    memory_request_mb INTEGER NOT NULL,

    selector JSONB NOT NULL,

    observed_generation BIGINT NOT NULL DEFAULT 0,

    CHECK (
        desired_replicas BETWEEN 0 AND 10000
    ),

    CHECK (observed_replicas >= 0),

    CHECK (ready_replicas >= 0),

    CHECK (cpu_request > 0),

    CHECK (memory_request_mb > 0),

    CHECK (jsonb_typeof(selector) = 'object'),

    CHECK (container_image <> '')
);


-- =========================================================
-- PODS
-- =========================================================

CREATE TABLE pods (
    resource_id UUID PRIMARY KEY
        REFERENCES resources(resource_id)
        ON DELETE CASCADE,

    deployment_id UUID
        REFERENCES deployments(resource_id)
        ON DELETE SET NULL,

    node_id UUID
        REFERENCES nodes(resource_id)
        ON DELETE SET NULL,

    container_image TEXT NOT NULL,

    cpu_request INTEGER NOT NULL,

    memory_request_mb INTEGER NOT NULL,

    phase pod_phase NOT NULL DEFAULT 'Pending',

    labels JSONB NOT NULL DEFAULT '{}'::jsonb,

    restart_count INTEGER NOT NULL DEFAULT 0,

    scheduled_at TIMESTAMPTZ,

    started_at TIMESTAMPTZ,

    CHECK (cpu_request > 0),

    CHECK (memory_request_mb > 0),

    CHECK (restart_count >= 0),

    CHECK (jsonb_typeof(labels) = 'object'),

    CHECK (
        phase <> 'Running'
        OR node_id IS NOT NULL
    )
);


-- =========================================================
-- CONTROL PLANE COMPONENTS
-- =========================================================

CREATE TABLE control_plane_components (
    component_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    component_name VARCHAR(100) NOT NULL UNIQUE,

    component_type VARCHAR(50) NOT NULL,

    endpoint TEXT,

    healthy BOOLEAN NOT NULL DEFAULT TRUE,

    last_heartbeat TIMESTAMPTZ,

    version VARCHAR(50),

    CHECK (
        component_type IN (
            'API_SERVER',
            'SCHEDULER',
            'CONTROLLER_MANAGER',
            'ETCD'
        )
    )
);


-- =========================================================
-- CLUSTER EVENTS
-- =========================================================

CREATE TABLE cluster_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    resource_id UUID
        REFERENCES resources(resource_id)
        ON DELETE SET NULL,

    event event_type NOT NULL,

    component VARCHAR(100) NOT NULL,

    message TEXT NOT NULL,

    event_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    details JSONB NOT NULL DEFAULT '{}'::jsonb
);


-- =========================================================
-- RESOURCE VERSION TRIGGER
-- =========================================================

CREATE OR REPLACE FUNCTION assign_resource_version()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN

    NEW.resource_version :=
        nextval('k8s.cluster_revision_seq');

    NEW.updated_at := NOW();

    IF TG_OP = 'INSERT' THEN
        NEW.created_at := NOW();
    END IF;

    RETURN NEW;

END;
$$;


CREATE TRIGGER resources_version_trigger
BEFORE INSERT OR UPDATE ON resources
FOR EACH ROW
EXECUTE FUNCTION assign_resource_version();


-- =========================================================
-- GENERATION TRACKING
-- =========================================================

CREATE OR REPLACE FUNCTION update_deployment_generation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN

    IF ROW(
        NEW.desired_replicas,
        NEW.container_image,
        NEW.cpu_request,
        NEW.memory_request_mb,
        NEW.selector
    ) IS DISTINCT FROM ROW(
        OLD.desired_replicas,
        OLD.container_image,
        OLD.cpu_request,
        OLD.memory_request_mb,
        OLD.selector
    ) THEN

        UPDATE resources
        SET generation = generation + 1
        WHERE resource_id = NEW.resource_id;

    END IF;

    RETURN NEW;

END;
$$;


CREATE TRIGGER deployment_generation_trigger
BEFORE UPDATE ON deployments
FOR EACH ROW
EXECUTE FUNCTION update_deployment_generation();


-- =========================================================
-- AUDIT EVENT FUNCTION
-- =========================================================

CREATE OR REPLACE FUNCTION record_cluster_event(
    p_resource_id UUID,
    p_event event_type,
    p_component TEXT,
    p_message TEXT,
    p_details JSONB DEFAULT '{}'::jsonb
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_event_id BIGINT;
BEGIN

    INSERT INTO cluster_events (
        resource_id,
        event,
        component,
        message,
        details
    )
    VALUES (
        p_resource_id,
        p_event,
        p_component,
        p_message,
        p_details
    )
    RETURNING event_id INTO v_event_id;

    RETURN v_event_id;

END;
$$;


-- =========================================================
-- RESOURCE REGISTRATION FUNCTION
-- =========================================================

CREATE OR REPLACE FUNCTION register_node(
    p_name TEXT,
    p_cpu INTEGER,
    p_memory_mb INTEGER,
    p_kubelet_version TEXT
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_resource_id UUID;
BEGIN

    IF p_cpu <= 0 OR p_memory_mb <= 0 THEN
        RAISE EXCEPTION
            'Node capacity must be positive';
    END IF;

    INSERT INTO resources (
        resource_kind,
        namespace,
        resource_name
    )
    VALUES (
        'Node',
        'default',
        p_name
    )
    RETURNING resource_id INTO v_resource_id;

    INSERT INTO nodes (
        resource_id,
        cpu_capacity,
        memory_capacity_mb,
        kubelet_version
    )
    VALUES (
        v_resource_id,
        p_cpu,
        p_memory_mb,
        p_kubelet_version
    );

    PERFORM record_cluster_event(
        v_resource_id,
        'CREATED',
        'API_SERVER',
        'Worker node registered'
    );

    RETURN v_resource_id;

END;
$$;


-- =========================================================
-- DEPLOYMENT REGISTRATION
-- =========================================================

CREATE OR REPLACE FUNCTION create_deployment(
    p_name TEXT,
    p_replicas INTEGER,
    p_image TEXT,
    p_cpu INTEGER,
    p_memory_mb INTEGER,
    p_selector JSONB
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_resource_id UUID;
BEGIN

    IF p_replicas < 0 OR p_replicas > 10000 THEN
        RAISE EXCEPTION 'Invalid replica count';
    END IF;

    IF p_cpu <= 0 OR p_memory_mb <= 0 THEN
        RAISE EXCEPTION 'Invalid resource requests';
    END IF;

    IF p_selector IS NULL
       OR jsonb_typeof(p_selector) <> 'object'
       OR p_selector = '{}'::jsonb THEN
        RAISE EXCEPTION 'Nonempty selector required';
    END IF;

    INSERT INTO resources (
        resource_kind,
        namespace,
        resource_name
    )
    VALUES (
        'Deployment',
        'default',
        p_name
    )
    RETURNING resource_id INTO v_resource_id;

    INSERT INTO deployments (
        resource_id,
        desired_replicas,
        container_image,
        cpu_request,
        memory_request_mb,
        selector
    )
    VALUES (
        v_resource_id,
        p_replicas,
        p_image,
        p_cpu,
        p_memory_mb,
        p_selector
    );

    PERFORM record_cluster_event(
        v_resource_id,
        'CREATED',
        'API_SERVER',
        'Deployment created'
    );

    RETURN v_resource_id;

END;
$$;


-- =========================================================
-- POD CREATION FUNCTION
-- =========================================================

CREATE OR REPLACE FUNCTION create_pod(
    p_name TEXT,
    p_deployment_id UUID,
    p_image TEXT,
    p_cpu INTEGER,
    p_memory_mb INTEGER,
    p_labels JSONB
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_resource_id UUID;
BEGIN

    IF p_cpu <= 0 OR p_memory_mb <= 0 THEN
        RAISE EXCEPTION 'Invalid Pod resource requests';
    END IF;

    INSERT INTO resources (
        resource_kind,
        namespace,
        resource_name
    )
    VALUES (
        'Pod',
        'default',
        p_name
    )
    RETURNING resource_id INTO v_resource_id;

    INSERT INTO pods (
        resource_id,
        deployment_id,
        container_image,
        cpu_request,
        memory_request_mb,
        labels
    )
    VALUES (
        v_resource_id,
        p_deployment_id,
        p_image,
        p_cpu,
        p_memory_mb,
        COALESCE(p_labels, '{}'::jsonb)
    );

    PERFORM record_cluster_event(
        v_resource_id,
        'CREATED',
        'CONTROLLER_MANAGER',
        'Pod created in Pending state'
    );

    RETURN v_resource_id;

END;
$$;


-- =========================================================
-- SCHEDULER
-- =========================================================

CREATE OR REPLACE FUNCTION schedule_pending_pod(
    p_pod_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_pod RECORD;
    v_node RECORD;
BEGIN

    -- Lock the Pod to avoid duplicate concurrent scheduling.
    SELECT
        p.*,
        r.resource_name,
        r.namespace
    INTO v_pod
    FROM pods p
    JOIN resources r
        ON r.resource_id = p.resource_id
    WHERE p.resource_id = p_pod_id
    FOR UPDATE OF p;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pod not found';
    END IF;

    IF v_pod.phase <> 'Pending' THEN
        RETURN FALSE;
    END IF;

    -- Candidate selection uses row locking and capacity checks.
    SELECT
        n.resource_id,
        nr.resource_name
    INTO v_node
    FROM nodes n
    JOIN resources nr
        ON nr.resource_id = n.resource_id
    WHERE n.condition = 'Ready'
      AND n.cpu_capacity - n.cpu_allocated >=
          v_pod.cpu_request
      AND n.memory_capacity_mb - n.memory_allocated_mb >=
          v_pod.memory_request_mb
    ORDER BY
        n.cpu_capacity - n.cpu_allocated DESC,
        n.memory_capacity_mb - n.memory_allocated_mb DESC,
        nr.resource_name
    LIMIT 1
    FOR UPDATE OF n SKIP LOCKED;

    IF NOT FOUND THEN

        PERFORM record_cluster_event(
            p_pod_id,
            'UNSCHEDULABLE',
            'SCHEDULER',
            'No suitable worker node available'
        );

        RETURN FALSE;

    END IF;

    UPDATE nodes
    SET
        cpu_allocated =
            cpu_allocated + v_pod.cpu_request,
        memory_allocated_mb =
            memory_allocated_mb + v_pod.memory_request_mb
    WHERE resource_id = v_node.resource_id;

    UPDATE pods
    SET
        node_id = v_node.resource_id,
        phase = 'Running',
        scheduled_at = NOW(),
        started_at = NOW()
    WHERE resource_id = p_pod_id
      AND phase = 'Pending';

    PERFORM record_cluster_event(
        p_pod_id,
        'SCHEDULED',
        'SCHEDULER',
        'Pod bound to worker node',
        jsonb_build_object(
            'node', v_node.resource_name
        )
    );

    RETURN TRUE;

END;
$$;


-- =========================================================
-- DEPLOYMENT RECONCILIATION
-- =========================================================

CREATE OR REPLACE FUNCTION reconcile_deployment(
    p_deployment_id UUID
)
RETURNS TABLE (
    desired INTEGER,
    running INTEGER,
    created INTEGER,
    removed INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_deployment RECORD;
    v_running INTEGER;
    v_total INTEGER;
    v_missing INTEGER;
    v_excess INTEGER;
    v_created INTEGER := 0;
    v_removed INTEGER := 0;
    v_index INTEGER;
    v_pod RECORD;
    v_pod_name TEXT;
BEGIN

    SELECT
        d.*,
        r.resource_name,
        r.namespace
    INTO v_deployment
    FROM deployments d
    JOIN resources r
        ON r.resource_id = d.resource_id
    WHERE d.resource_id = p_deployment_id
    FOR UPDATE OF d;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Deployment not found';
    END IF;

    -- Count actual owned Pods matching the Deployment selector.
    SELECT
        COUNT(*) FILTER (
            WHERE p.phase = 'Running'
        ),
        COUNT(*)
    INTO v_running, v_total
    FROM pods p
    WHERE p.deployment_id = p_deployment_id
      AND p.labels @> v_deployment.selector;

    v_missing := GREATEST(
        0,
        v_deployment.desired_replicas - v_running
    );

    v_excess := GREATEST(
        0,
        v_total - v_deployment.desired_replicas
    );

    -- Remove excess Pods and release their reservations.
    FOR v_pod IN
        SELECT *
        FROM pods
        WHERE deployment_id = p_deployment_id
        ORDER BY resource_id DESC
        LIMIT v_excess
        FOR UPDATE
    LOOP

        IF v_pod.node_id IS NOT NULL THEN

            UPDATE nodes
            SET
                cpu_allocated = GREATEST(
                    0,
                    cpu_allocated - v_pod.cpu_request
                ),
                memory_allocated_mb = GREATEST(
                    0,
                    memory_allocated_mb -
                        v_pod.memory_request_mb
                )
            WHERE resource_id = v_pod.node_id;

        END IF;

        DELETE FROM resources
        WHERE resource_id = v_pod.resource_id;

        v_removed := v_removed + 1;

    END LOOP;

    -- Create missing replicas in Pending state.
    FOR v_index IN 1..v_missing LOOP

        v_pod_name :=
            v_deployment.resource_name ||
            '-' ||
            substr(
                replace(gen_random_uuid()::text, '-', ''),
                1,
                12
            );

        PERFORM create_pod(
            v_pod_name,
            p_deployment_id,
            v_deployment.container_image,
            v_deployment.cpu_request,
            v_deployment.memory_request_mb,
            v_deployment.selector
        );

        v_created := v_created + 1;

    END LOOP;

    UPDATE deployments
    SET
        observed_replicas = v_total - v_removed + v_created,
        ready_replicas = v_running,
        observed_generation = (
            SELECT generation
            FROM resources
            WHERE resource_id = p_deployment_id
        )
    WHERE resource_id = p_deployment_id;

    PERFORM record_cluster_event(
        p_deployment_id,
        'RECONCILED',
        'CONTROLLER_MANAGER',
        'Deployment desired state evaluated',
        jsonb_build_object(
            'desired', v_deployment.desired_replicas,
            'running', v_running,
            'created', v_created,
            'removed', v_removed
        )
    );

    RETURN QUERY
    SELECT
        v_deployment.desired_replicas,
        v_running,
        v_created,
        v_removed;

END;
$$;


-- =========================================================
-- NODE HEALTH MANAGEMENT
-- =========================================================

CREATE OR REPLACE FUNCTION update_node_condition(
    p_node_id UUID,
    p_condition node_condition
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN

    UPDATE nodes
    SET
        condition = p_condition,
        last_heartbeat = NOW()
    WHERE resource_id = p_node_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Node not found';
    END IF;

    PERFORM record_cluster_event(
        p_node_id,
        'UPDATED',
        'CONTROLLER_MANAGER',
        'Node condition updated',
        jsonb_build_object(
            'condition', p_condition
        )
    );

END;
$$;


-- =========================================================
-- INDEXES
-- =========================================================

CREATE INDEX idx_resources_kind_namespace
    ON resources(resource_kind, namespace);

CREATE INDEX idx_resources_name
    ON resources(resource_name);

CREATE INDEX idx_pods_phase
    ON pods(phase);

CREATE INDEX idx_pods_node
    ON pods(node_id);

CREATE INDEX idx_pods_deployment_phase
    ON pods(deployment_id, phase);

CREATE INDEX idx_pods_labels
    ON pods USING GIN(labels);

CREATE INDEX idx_nodes_condition
    ON nodes(condition);

CREATE INDEX idx_cluster_events_time
    ON cluster_events(event_time DESC);

CREATE INDEX idx_cluster_events_resource
    ON cluster_events(resource_id, event_time DESC);


-- =========================================================
-- CONTROL PLANE COMPONENT REGISTRATION
-- =========================================================

INSERT INTO control_plane_components (
    component_name,
    component_type,
    endpoint,
    healthy,
    version,
    last_heartbeat
)
VALUES
(
    'kube-apiserver',
    'API_SERVER',
    'https://127.0.0.1:6443',
    TRUE,
    '1.31.0',
    NOW()
),
(
    'kube-scheduler',
    'SCHEDULER',
    NULL,
    TRUE,
    '1.31.0',
    NOW()
),
(
    'kube-controller-manager',
    'CONTROLLER_MANAGER',
    NULL,
    TRUE,
    '1.31.0',
    NOW()
),
(
    'etcd',
    'ETCD',
    'https://127.0.0.1:2379',
    TRUE,
    '3.5.16',
    NOW()
);


-- =========================================================
-- SAMPLE CLUSTER
-- =========================================================

DO $$
DECLARE
    v_node_1 UUID;
    v_node_2 UUID;
    v_deployment UUID;
BEGIN

    v_node_1 := register_node(
        'worker-01',
        8,
        16384,
        'v1.31.0'
    );

    v_node_2 := register_node(
        'worker-02',
        4,
        8192,
        'v1.31.0'
    );

    v_deployment := create_deployment(
        'web-api',
        4,
        'nginx:1.27',
        1,
        512,
        '{"app": "web"}'::jsonb
    );

    -- Generate desired Pod instances.
    PERFORM reconcile_deployment(v_deployment);

    -- Schedule Pending Pods.
    PERFORM schedule_pending_pod(resource_id)
    FROM pods
    WHERE phase = 'Pending';

    -- Run reconciliation again to verify convergence.
    PERFORM reconcile_deployment(v_deployment);

    -- Demonstrate a worker node entering NotReady state.
    PERFORM update_node_condition(
        v_node_2,
        'NotReady'
    );

END;
$$;


-- =========================================================
-- CLUSTER RESOURCE VIEW
-- =========================================================

CREATE OR REPLACE VIEW cluster_resource_overview AS
SELECT
    r.resource_id,
    r.resource_kind,
    r.namespace,
    r.resource_name,
    r.resource_version,
    r.generation,
    r.created_at,
    r.updated_at
FROM resources r;


-- =========================================================
-- NODE CAPACITY REPORT
-- =========================================================

CREATE OR REPLACE VIEW node_capacity_report AS
SELECT
    r.resource_name AS node_name,
    n.condition,
    n.cpu_capacity,
    n.cpu_allocated,
    n.cpu_capacity - n.cpu_allocated AS cpu_available,
    n.memory_capacity_mb,
    n.memory_allocated_mb,
    n.memory_capacity_mb -
        n.memory_allocated_mb AS memory_available,
    ROUND(
        100.0 * n.cpu_allocated /
        NULLIF(n.cpu_capacity, 0),
        2
    ) AS cpu_utilization_percent
FROM nodes n
JOIN resources r
    ON r.resource_id = n.resource_id;


-- =========================================================
-- POD STATUS REPORT
-- =========================================================

CREATE OR REPLACE VIEW pod_status_report AS
SELECT
    pr.resource_name AS pod_name,
    dr.resource_name AS deployment_name,
    nr.resource_name AS node_name,
    p.container_image,
    p.phase,
    p.cpu_request,
    p.memory_request_mb,
    p.restart_count,
    p.scheduled_at
FROM pods p
JOIN resources pr
    ON pr.resource_id = p.resource_id
LEFT JOIN resources dr
    ON dr.resource_id = p.deployment_id
LEFT JOIN resources nr
    ON nr.resource_id = p.node_id;


-- =========================================================
-- DEPLOYMENT CONVERGENCE REPORT
-- =========================================================

CREATE OR REPLACE VIEW deployment_convergence_report AS
SELECT
    r.resource_name AS deployment_name,
    d.desired_replicas,
    COUNT(p.resource_id) AS actual_pods,
    COUNT(p.resource_id) FILTER (
        WHERE p.phase = 'Running'
    ) AS running_pods,
    COUNT(p.resource_id) FILTER (
        WHERE p.phase = 'Pending'
    ) AS pending_pods,
    COUNT(p.resource_id) FILTER (
        WHERE p.phase = 'Failed'
    ) AS failed_pods,
    d.desired_replicas =
        COUNT(p.resource_id) FILTER (
            WHERE p.phase = 'Running'
        ) AS desired_state_reached
FROM deployments d
JOIN resources r
    ON r.resource_id = d.resource_id
LEFT JOIN pods p
    ON p.deployment_id = d.resource_id
GROUP BY
    r.resource_name,
    d.desired_replicas;


-- =========================================================
-- VALIDATION QUERIES
-- =========================================================

-- 1. Pods without a valid node assignment.
SELECT
    resource_name,
    resource_version
FROM resources
WHERE resource_kind = 'Pod'
AND resource_id NOT IN (
    SELECT resource_id
    FROM pods
);

-- 2. Nodes exceeding capacity.
SELECT *
FROM nodes
WHERE cpu_allocated > cpu_capacity
   OR memory_allocated_mb > memory_capacity_mb;

-- 3. Running Pods without node assignment.
SELECT resource_id
FROM pods
WHERE phase = 'Running'
AND node_id IS NULL;

-- 4. Deployments not reaching desired state.
SELECT *
FROM deployment_convergence_report
WHERE desired_state_reached = FALSE;


-- =========================================================
-- AGGREGATION AND CAPACITY EVALUATION
-- =========================================================

SELECT
    condition,
    COUNT(*) AS total_nodes,
    SUM(cpu_capacity) AS total_cpu,
    SUM(cpu_allocated) AS allocated_cpu,
    SUM(memory_capacity_mb) AS total_memory_mb,
    SUM(memory_allocated_mb) AS allocated_memory_mb
FROM nodes
GROUP BY condition;


-- =========================================================
-- COMPONENT HEALTH REPORT
-- =========================================================

SELECT
    component_name,
    component_type,
    healthy,
    version,
    last_heartbeat,
    NOW() - last_heartbeat AS heartbeat_age
FROM control_plane_components
ORDER BY component_type;


-- =========================================================
-- RECENT CONTROL PLANE EVENTS
-- =========================================================

SELECT
    event_id,
    component,
    event,
    message,
    event_time,
    details
FROM cluster_events
ORDER BY event_time DESC
LIMIT 50;


-- =========================================================
-- TRANSACTIONAL NODE CAPACITY UPDATE
-- =========================================================

-- Demonstrates atomic reservation and rollback on failure.
DO $$
DECLARE
    v_node RECORD;
    v_cpu INTEGER := 1;
    v_memory INTEGER := 256;
BEGIN

    SELECT *
    INTO v_node
    FROM nodes
    WHERE condition = 'Ready'
      AND cpu_capacity - cpu_allocated >= v_cpu
      AND memory_capacity_mb - memory_allocated_mb >=
          v_memory
    ORDER BY cpu_capacity - cpu_allocated DESC
    LIMIT 1
    FOR UPDATE SKIP LOCKED;

    IF NOT FOUND THEN
        RAISE NOTICE 'No eligible node for reservation';
    ELSE

        UPDATE nodes
        SET
            cpu_allocated = cpu_allocated + v_cpu,
            memory_allocated_mb =
                memory_allocated_mb + v_memory
        WHERE resource_id = v_node.resource_id;

        RAISE NOTICE
            'Reservation committed for node %',
            v_node.resource_id;

        -- This example reservation is intentionally released
        -- within the same transaction.
        UPDATE nodes
        SET
            cpu_allocated = cpu_allocated - v_cpu,
            memory_allocated_mb =
                memory_allocated_mb - v_memory
        WHERE resource_id = v_node.resource_id;

    END IF;

END;
$$;


-- =========================================================
-- OPTIMISTIC CONCURRENCY DEMONSTRATION
-- =========================================================

-- Update succeeds only when the expected resource version
-- still matches the persisted version.
DO $$
DECLARE
    v_resource UUID;
    v_version BIGINT;
BEGIN

    SELECT
        resource_id,
        resource_version
    INTO
        v_resource,
        v_version
    FROM resources
    WHERE resource_kind = 'Deployment'
      AND resource_name = 'web-api';

    UPDATE resources
    SET updated_at = NOW()
    WHERE resource_id = v_resource
      AND resource_version = v_version;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Optimistic concurrency conflict';
    END IF;

END;
$$;


-- =========================================================
-- FINAL REPORTS
-- =========================================================

SELECT * FROM cluster_resource_overview
ORDER BY resource_kind, resource_name;

SELECT * FROM node_capacity_report
ORDER BY node_name;

SELECT * FROM pod_status_report
ORDER BY pod_name;

SELECT * FROM deployment_convergence_report
ORDER BY deployment_name;


COMMIT;
