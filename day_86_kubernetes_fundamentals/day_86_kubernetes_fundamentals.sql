/*
    Kubernetes Fundamentals
    PostgreSQL Cluster Orchestration and Declarative Infrastructure

    PostgreSQL 15+

    Domain model:
    Organizations
      -> Clusters
      -> Nodes
      -> Namespaces
      -> Workloads
      -> ReplicaSets
      -> Pods
      -> Containers
      -> Services
      -> Service Endpoints
      -> Scheduling Events
      -> Reconciliation History
      -> Resource Policies

    The schema distinguishes:
      Desired state: deployment specifications and replica counts.
      Actual state: nodes, pods, container states, and allocations.
      Control-plane decisions: scheduling and reconciliation events.

    Execute as a database owner in a development database.
*/

BEGIN;

CREATE SCHEMA IF NOT EXISTS kube_lab;

SET search_path TO kube_lab, public;


-- ============================================================
-- 1. DOMAIN TYPES
-- ============================================================

CREATE TYPE node_status AS ENUM (
    'Ready',
    'NotReady',
    'Draining',
    'Unknown'
);

CREATE TYPE pod_phase AS ENUM (
    'Pending',
    'Running',
    'Succeeded',
    'Failed',
    'Terminating'
);

CREATE TYPE workload_kind AS ENUM (
    'Deployment',
    'StatefulSet',
    'DaemonSet',
    'Job'
);

CREATE TYPE container_status AS ENUM (
    'Waiting',
    'Running',
    'Terminated'
);

CREATE TYPE condition_status AS ENUM (
    'True',
    'False',
    'Unknown'
);

CREATE TYPE event_severity AS ENUM (
    'Normal',
    'Warning',
    'Error'
);


-- ============================================================
-- 2. CLUSTER AND NODE MANAGEMENT
-- ============================================================

CREATE TABLE clusters (
    cluster_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cluster_name VARCHAR(63) NOT NULL UNIQUE,

    environment VARCHAR(30) NOT NULL
        CHECK (
            environment IN (
                'development',
                'testing',
                'staging',
                'production'
            )
        ),

    kubernetes_version VARCHAR(30) NOT NULL,

    control_plane_endpoint TEXT,

    status VARCHAR(20) NOT NULL DEFAULT 'Active'
        CHECK (
            status IN ('Active', 'Degraded', 'Unavailable')
        ),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE nodes (
    node_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cluster_id BIGINT NOT NULL
        REFERENCES clusters(cluster_id)
        ON DELETE CASCADE,

    node_name VARCHAR(63) NOT NULL,

    node_role VARCHAR(20) NOT NULL
        CHECK (
            node_role IN ('ControlPlane', 'Worker')
        ),

    status node_status NOT NULL DEFAULT 'Ready',

    cpu_capacity_millicores INTEGER NOT NULL
        CHECK (cpu_capacity_millicores > 0),

    memory_capacity_mb INTEGER NOT NULL
        CHECK (memory_capacity_mb > 0),

    cpu_allocatable_millicores INTEGER NOT NULL
        CHECK (
            cpu_allocatable_millicores > 0
            AND cpu_allocatable_millicores
                <= cpu_capacity_millicores
        ),

    memory_allocatable_mb INTEGER NOT NULL
        CHECK (
            memory_allocatable_mb > 0
            AND memory_allocatable_mb <= memory_capacity_mb
        ),

    architecture VARCHAR(30) NOT NULL DEFAULT 'amd64',

    kubelet_version VARCHAR(30) NOT NULL,

    last_heartbeat TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(cluster_id, node_name)
);


CREATE INDEX idx_nodes_cluster_status
    ON nodes(cluster_id, status);


CREATE INDEX idx_nodes_schedulable
    ON nodes(cluster_id, status)
    WHERE status = 'Ready';


-- ============================================================
-- 3. NAMESPACES AND RESOURCE GOVERNANCE
-- ============================================================

CREATE TABLE namespaces (
    namespace_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cluster_id BIGINT NOT NULL
        REFERENCES clusters(cluster_id)
        ON DELETE CASCADE,

    namespace_name VARCHAR(63) NOT NULL,

    purpose TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(cluster_id, namespace_name)
);


CREATE TABLE resource_quotas (
    quota_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    namespace_id BIGINT NOT NULL
        REFERENCES namespaces(namespace_id)
        ON DELETE CASCADE,

    quota_name VARCHAR(100) NOT NULL,

    max_pods INTEGER NOT NULL CHECK (max_pods >= 0),

    max_cpu_millicores BIGINT NOT NULL
        CHECK (max_cpu_millicores >= 0),

    max_memory_mb BIGINT NOT NULL
        CHECK (max_memory_mb >= 0),

    UNIQUE(namespace_id, quota_name)
);


-- ============================================================
-- 4. DECLARATIVE WORKLOAD SPECIFICATIONS
-- ============================================================

CREATE TABLE workloads (
    workload_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    namespace_id BIGINT NOT NULL
        REFERENCES namespaces(namespace_id)
        ON DELETE CASCADE,

    workload_name VARCHAR(63) NOT NULL,

    workload_type workload_kind NOT NULL,

    container_image TEXT NOT NULL
        CHECK (
            length(container_image) > 0
            AND position(':' IN container_image) > 0
        ),

    desired_replicas INTEGER NOT NULL DEFAULT 1
        CHECK (desired_replicas >= 0),

    selector JSONB NOT NULL
        CHECK (
            jsonb_typeof(selector) = 'object'
            AND selector <> '{}'::jsonb
        ),

    cpu_request_millicores INTEGER NOT NULL
        CHECK (cpu_request_millicores > 0),

    memory_request_mb INTEGER NOT NULL
        CHECK (memory_request_mb > 0),

    cpu_limit_millicores INTEGER,

    memory_limit_mb INTEGER,

    generation INTEGER NOT NULL DEFAULT 1
        CHECK (generation > 0),

    revision INTEGER NOT NULL DEFAULT 1
        CHECK (revision > 0),

    desired_image TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(namespace_id, workload_name),

    CHECK (
        cpu_limit_millicores IS NULL
        OR cpu_limit_millicores >= cpu_request_millicores
    ),

    CHECK (
        memory_limit_mb IS NULL
        OR memory_limit_mb >= memory_request_mb
    )
);


CREATE INDEX idx_workloads_namespace
    ON workloads(namespace_id, workload_type);


CREATE INDEX idx_workloads_selector
    ON workloads USING GIN(selector);


-- ============================================================
-- 5. REPLICASETS
-- ============================================================

CREATE TABLE replica_sets (
    replicaset_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    workload_id BIGINT NOT NULL
        REFERENCES workloads(workload_id)
        ON DELETE CASCADE,

    revision INTEGER NOT NULL CHECK (revision > 0),

    image TEXT NOT NULL,

    desired_replicas INTEGER NOT NULL
        CHECK (desired_replicas >= 0),

    generation INTEGER NOT NULL DEFAULT 1,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(workload_id, revision)
);


-- ============================================================
-- 6. PODS AND CONTAINER INSTANCES
-- ============================================================

CREATE TABLE pods (
    pod_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    namespace_id BIGINT NOT NULL
        REFERENCES namespaces(namespace_id),

    workload_id BIGINT
        REFERENCES workloads(workload_id)
        ON DELETE SET NULL,

    replicaset_id BIGINT
        REFERENCES replica_sets(replicaset_id)
        ON DELETE SET NULL,

    node_id BIGINT
        REFERENCES nodes(node_id)
        ON DELETE SET NULL,

    pod_name VARCHAR(63) NOT NULL,

    image TEXT NOT NULL,

    phase pod_phase NOT NULL DEFAULT 'Pending',

    labels JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(labels) = 'object'),

    cpu_request_millicores INTEGER NOT NULL
        CHECK (cpu_request_millicores > 0),

    memory_request_mb INTEGER NOT NULL
        CHECK (memory_request_mb > 0),

    ready BOOLEAN NOT NULL DEFAULT FALSE,

    restart_count INTEGER NOT NULL DEFAULT 0
        CHECK (restart_count >= 0),

    revision INTEGER NOT NULL DEFAULT 1,

    creation_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    started_at TIMESTAMPTZ,

    UNIQUE(namespace_id, pod_name),

    CHECK (
        NOT ready OR phase = 'Running'
    )
);


CREATE INDEX idx_pods_node_phase
    ON pods(node_id, phase);


CREATE INDEX idx_pods_workload_phase
    ON pods(workload_id, phase);


CREATE INDEX idx_pods_labels
    ON pods USING GIN(labels);


CREATE INDEX idx_pods_ready
    ON pods(namespace_id, workload_id)
    WHERE phase = 'Running' AND ready = TRUE;


CREATE TABLE containers (
    container_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    pod_id BIGINT NOT NULL
        REFERENCES pods(pod_id)
        ON DELETE CASCADE,

    container_name VARCHAR(63) NOT NULL,

    image TEXT NOT NULL,

    status container_status NOT NULL DEFAULT 'Waiting',

    restart_count INTEGER NOT NULL DEFAULT 0
        CHECK (restart_count >= 0),

    started_at TIMESTAMPTZ,

    terminated_at TIMESTAMPTZ,

    UNIQUE(pod_id, container_name)
);


-- ============================================================
-- 7. NODE CONDITIONS
-- ============================================================

CREATE TABLE node_conditions (
    condition_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    node_id BIGINT NOT NULL
        REFERENCES nodes(node_id)
        ON DELETE CASCADE,

    condition_type VARCHAR(50) NOT NULL,

    status condition_status NOT NULL,

    reason VARCHAR(100),

    message TEXT,

    last_transition_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE INDEX idx_node_conditions_latest
    ON node_conditions(node_id, condition_type, last_transition_time DESC);


-- ============================================================
-- 8. SERVICES AND ENDPOINT DISCOVERY
-- ============================================================

CREATE TABLE services (
    service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    namespace_id BIGINT NOT NULL
        REFERENCES namespaces(namespace_id)
        ON DELETE CASCADE,

    service_name VARCHAR(63) NOT NULL,

    service_type VARCHAR(20) NOT NULL DEFAULT 'ClusterIP'
        CHECK (
            service_type IN (
                'ClusterIP',
                'NodePort',
                'LoadBalancer',
                'ExternalName'
            )
        ),

    selector JSONB NOT NULL
        CHECK (
            jsonb_typeof(selector) = 'object'
            AND selector <> '{}'::jsonb
        ),

    port INTEGER NOT NULL
        CHECK (port BETWEEN 1 AND 65535),

    target_port INTEGER NOT NULL
        CHECK (target_port BETWEEN 1 AND 65535),

    UNIQUE(namespace_id, service_name)
);


CREATE TABLE service_endpoints (
    endpoint_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_id BIGINT NOT NULL
        REFERENCES services(service_id)
        ON DELETE CASCADE,

    pod_id BIGINT NOT NULL
        REFERENCES pods(pod_id)
        ON DELETE CASCADE,

    ready BOOLEAN NOT NULL DEFAULT FALSE,

    last_updated TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(service_id, pod_id)
);


-- ============================================================
-- 9. SCHEDULING EVENTS AND CONTROL-PLANE AUDIT
-- ============================================================

CREATE TABLE cluster_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cluster_id BIGINT NOT NULL
        REFERENCES clusters(cluster_id)
        ON DELETE CASCADE,

    node_id BIGINT
        REFERENCES nodes(node_id)
        ON DELETE SET NULL,

    pod_id BIGINT
        REFERENCES pods(pod_id)
        ON DELETE SET NULL,

    workload_id BIGINT
        REFERENCES workloads(workload_id)
        ON DELETE SET NULL,

    event_type VARCHAR(100) NOT NULL,

    severity event_severity NOT NULL DEFAULT 'Normal',

    message TEXT NOT NULL,

    event_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE INDEX idx_events_cluster_time
    ON cluster_events(cluster_id, event_timestamp DESC);


CREATE INDEX idx_events_warning
    ON cluster_events(cluster_id, event_timestamp DESC)
    WHERE severity IN ('Warning', 'Error');


CREATE TABLE reconciliation_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    workload_id BIGINT NOT NULL
        REFERENCES workloads(workload_id)
        ON DELETE CASCADE,

    desired_replicas INTEGER NOT NULL,

    actual_replicas INTEGER NOT NULL,

    generation INTEGER NOT NULL,

    succeeded BOOLEAN NOT NULL,

    error_message TEXT,

    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    completed_at TIMESTAMPTZ,

    CHECK (actual_replicas >= 0),
    CHECK (desired_replicas >= 0)
);


-- ============================================================
-- 10. TRIGGERS AND INTEGRITY ENFORCEMENT
-- ============================================================

CREATE OR REPLACE FUNCTION update_modified_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


CREATE TRIGGER trg_workload_updated
BEFORE UPDATE ON workloads
FOR EACH ROW
EXECUTE FUNCTION update_modified_timestamp();


-- Prevent pods from being assigned to a node in another cluster.
CREATE OR REPLACE FUNCTION validate_pod_node_cluster()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_namespace_cluster BIGINT;
    v_node_cluster BIGINT;
BEGIN
    IF NEW.node_id IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT cluster_id
    INTO v_namespace_cluster
    FROM namespaces
    WHERE namespace_id = NEW.namespace_id;

    SELECT cluster_id
    INTO v_node_cluster
    FROM nodes
    WHERE node_id = NEW.node_id;

    IF v_namespace_cluster IS DISTINCT FROM v_node_cluster THEN
        RAISE EXCEPTION
            'Pod and node must belong to the same cluster';
    END IF;

    RETURN NEW;
END;
$$;


CREATE TRIGGER trg_validate_pod_node
BEFORE INSERT OR UPDATE OF namespace_id, node_id
ON pods
FOR EACH ROW
EXECUTE FUNCTION validate_pod_node_cluster();


-- Ensure a ready pod has a running phase.
CREATE OR REPLACE FUNCTION enforce_pod_readiness()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.ready AND NEW.phase <> 'Running' THEN
        RAISE EXCEPTION
            'Only Running pods can be Ready';
    END IF;

    RETURN NEW;
END;
$$;


CREATE TRIGGER trg_pod_readiness
BEFORE INSERT OR UPDATE ON pods
FOR EACH ROW
EXECUTE FUNCTION enforce_pod_readiness();


-- ============================================================
-- 11. RESOURCE ACCOUNTING VIEWS
-- ============================================================

CREATE OR REPLACE VIEW node_resource_utilization AS
SELECT
    n.node_id,
    n.cluster_id,
    n.node_name,
    n.status,
    n.cpu_allocatable_millicores,
    COALESCE(SUM(
        CASE
            WHEN p.phase IN ('Pending', 'Running')
            THEN p.cpu_request_millicores
            ELSE 0
        END
    ), 0)::BIGINT AS allocated_cpu_millicores,

    n.memory_allocatable_mb,

    COALESCE(SUM(
        CASE
            WHEN p.phase IN ('Pending', 'Running')
            THEN p.memory_request_mb
            ELSE 0
        END
    ), 0)::BIGINT AS allocated_memory_mb,

    ROUND(
        100.0 * COALESCE(SUM(
            CASE
                WHEN p.phase IN ('Pending', 'Running')
                THEN p.cpu_request_millicores
                ELSE 0
            END
        ), 0) / n.cpu_allocatable_millicores,
        2
    ) AS cpu_request_utilization_percent

FROM nodes n

LEFT JOIN pods p
    ON p.node_id = n.node_id

GROUP BY
    n.node_id,
    n.cluster_id,
    n.node_name,
    n.status,
    n.cpu_allocatable_millicores,
    n.memory_allocatable_mb;


CREATE OR REPLACE VIEW workload_health AS
SELECT
    w.workload_id,
    w.workload_name,
    w.workload_type,
    w.desired_replicas,

    COUNT(p.pod_id) FILTER (
        WHERE p.phase = 'Running'
    ) AS running_replicas,

    COUNT(p.pod_id) FILTER (
        WHERE p.phase = 'Running'
          AND p.ready = TRUE
    ) AS ready_replicas,

    COUNT(p.pod_id) FILTER (
        WHERE p.phase = 'Failed'
    ) AS failed_replicas,

    CASE
        WHEN COUNT(p.pod_id) FILTER (
            WHERE p.phase = 'Running'
              AND p.ready = TRUE
        ) = w.desired_replicas
        THEN 'Healthy'

        WHEN COUNT(p.pod_id) FILTER (
            WHERE p.phase = 'Running'
              AND p.ready = TRUE
        ) = 0
        AND w.desired_replicas > 0
        THEN 'Unavailable'

        ELSE 'Degraded'
    END AS health_status

FROM workloads w

LEFT JOIN pods p
    ON p.workload_id = w.workload_id

GROUP BY
    w.workload_id,
    w.workload_name,
    w.workload_type,
    w.desired_replicas;


-- ============================================================
-- 12. SERVICE ENDPOINT DISCOVERY VIEW
-- ============================================================

CREATE OR REPLACE VIEW ready_service_endpoints AS
SELECT
    s.service_id,
    s.service_name,
    ns.namespace_name,
    p.pod_id,
    p.pod_name,
    n.node_name,
    s.port,
    s.target_port

FROM services s

JOIN namespaces ns
    ON ns.namespace_id = s.namespace_id

JOIN pods p
    ON p.namespace_id = s.namespace_id
   AND p.phase = 'Running'
   AND p.ready = TRUE
   AND p.labels @> s.selector

JOIN nodes n
    ON n.node_id = p.node_id
   AND n.status = 'Ready';


-- ============================================================
-- 13. RECONCILIATION FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION record_reconciliation(
    p_workload_id BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_desired INTEGER;
    v_actual INTEGER;
    v_generation INTEGER;
    v_run_id BIGINT;
BEGIN
    SELECT desired_replicas, generation
    INTO v_desired, v_generation
    FROM workloads
    WHERE workload_id = p_workload_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workload not found: %', p_workload_id;
    END IF;

    SELECT COUNT(*)
    INTO v_actual
    FROM pods
    WHERE workload_id = p_workload_id
      AND phase = 'Running'
      AND ready = TRUE;

    INSERT INTO reconciliation_runs (
        workload_id,
        desired_replicas,
        actual_replicas,
        generation,
        succeeded,
        completed_at
    )
    VALUES (
        p_workload_id,
        v_desired,
        v_actual,
        v_generation,
        v_actual = v_desired,
        CURRENT_TIMESTAMP
    )
    RETURNING run_id INTO v_run_id;

    RETURN v_run_id;
END;
$$;


-- ============================================================
-- 14. SCHEDULING ELIGIBILITY FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION eligible_nodes(
    p_cluster_id BIGINT,
    p_cpu INTEGER,
    p_memory INTEGER
)
RETURNS TABLE (
    node_id BIGINT,
    node_name VARCHAR,
    available_cpu BIGINT,
    available_memory BIGINT
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        n.node_id,
        n.node_name,

        n.cpu_allocatable_millicores -
            COALESCE(SUM(
                CASE
                    WHEN p.phase IN ('Pending', 'Running')
                    THEN p.cpu_request_millicores
                    ELSE 0
                END
            ), 0)::BIGINT AS available_cpu,

        n.memory_allocatable_mb -
            COALESCE(SUM(
                CASE
                    WHEN p.phase IN ('Pending', 'Running')
                    THEN p.memory_request_mb
                    ELSE 0
                END
            ), 0)::BIGINT AS available_memory

    FROM nodes n

    LEFT JOIN pods p
        ON p.node_id = n.node_id

    WHERE n.cluster_id = p_cluster_id
      AND n.status = 'Ready'

    GROUP BY
        n.node_id,
        n.node_name,
        n.cpu_allocatable_millicores,
        n.memory_allocatable_mb

    HAVING
        n.cpu_allocatable_millicores -
            COALESCE(SUM(
                CASE
                    WHEN p.phase IN ('Pending', 'Running')
                    THEN p.cpu_request_millicores
                    ELSE 0
                END
            ), 0) >= p_cpu

        AND

        n.memory_allocatable_mb -
            COALESCE(SUM(
                CASE
                    WHEN p.phase IN ('Pending', 'Running')
                    THEN p.memory_request_mb
                    ELSE 0
                END
            ), 0) >= p_memory

    ORDER BY available_cpu ASC, available_memory ASC;
$$;


-- ============================================================
-- 15. SAMPLE CLUSTER DATA
-- ============================================================

INSERT INTO clusters (
    cluster_name,
    environment,
    kubernetes_version,
    control_plane_endpoint
)
VALUES
(
    'production-cluster',
    'production',
    '1.32.0',
    'https://api.production.internal:6443'
),
(
    'staging-cluster',
    'staging',
    '1.32.0',
    'https://api.staging.internal:6443'
);


INSERT INTO nodes (
    cluster_id,
    node_name,
    node_role,
    status,
    cpu_capacity_millicores,
    memory_capacity_mb,
    cpu_allocatable_millicores,
    memory_allocatable_mb,
    kubelet_version,
    last_heartbeat
)
SELECT
    cluster_id,
    data.node_name,
    'Worker',
    data.status::node_status,
    data.cpu,
    data.memory,
    data.cpu_allocatable,
    data.memory_allocatable,
    'v1.32.0',
    CURRENT_TIMESTAMP
FROM clusters
CROSS JOIN (
    VALUES
        ('worker-01', 'Ready', 4000, 8192, 3500, 7168),
        ('worker-02', 'Ready', 4000, 8192, 3500, 7168),
        ('worker-03', 'NotReady', 2000, 4096, 1800, 3584)
) AS data(
    node_name,
    status,
    cpu,
    memory,
    cpu_allocatable,
    memory_allocatable
)
WHERE clusters.cluster_name = 'production-cluster';


INSERT INTO namespaces (
    cluster_id,
    namespace_name,
    purpose
)
SELECT
    cluster_id,
    data.namespace_name,
    data.purpose
FROM clusters
CROSS JOIN (
    VALUES
        ('payments', 'Payment processing services'),
        ('monitoring', 'Cluster monitoring workloads'),
        ('development', 'Development workloads')
) AS data(namespace_name, purpose)
WHERE clusters.cluster_name = 'production-cluster';


INSERT INTO resource_quotas (
    namespace_id,
    quota_name,
    max_pods,
    max_cpu_millicores,
    max_memory_mb
)
SELECT
    namespace_id,
    'standard-quota',
    50,
    20000,
    32768
FROM namespaces
WHERE namespace_name = 'payments';


-- ============================================================
-- 16. SAMPLE WORKLOADS
-- ============================================================

INSERT INTO workloads (
    namespace_id,
    workload_name,
    workload_type,
    container_image,
    desired_replicas,
    selector,
    cpu_request_millicores,
    memory_request_mb,
    cpu_limit_millicores,
    memory_limit_mb,
    desired_image
)
SELECT
    namespace_id,
    'payment-api',
    'Deployment',
    'registry.example.com/payment:v1',
    3,
    '{"app":"payment-api","tier":"backend"}'::jsonb,
    500,
    512,
    1000,
    1024,
    'registry.example.com/payment:v1'
FROM namespaces
WHERE namespace_name = 'payments';


INSERT INTO workloads (
    namespace_id,
    workload_name,
    workload_type,
    container_image,
    desired_replicas,
    selector,
    cpu_request_millicores,
    memory_request_mb,
    desired_image
)
SELECT
    namespace_id,
    'payment-worker',
    'Deployment',
    'registry.example.com/worker:v1',
    2,
    '{"app":"payment-worker"}'::jsonb,
    1000,
    1024,
    'registry.example.com/worker:v1'
FROM namespaces
WHERE namespace_name = 'payments';


INSERT INTO workloads (
    namespace_id,
    workload_name,
    workload_type,
    container_image,
    desired_replicas,
    selector,
    cpu_request_millicores,
    memory_request_mb,
    desired_image
)
SELECT
    namespace_id,
    'resource-constrained-api',
    'Deployment',
    'registry.example.com/constrained:v1',
    1,
    '{"app":"constrained-api"}'::jsonb,
    5000,
    16384,
    'registry.example.com/constrained:v1'
FROM namespaces
WHERE namespace_name = 'payments';


-- ============================================================
-- 17. REPLICASET AND POD RECORDS
-- ============================================================

INSERT INTO replica_sets (
    workload_id,
    revision,
    image,
    desired_replicas
)
SELECT
    workload_id,
    1,
    container_image,
    desired_replicas
FROM workloads
WHERE workload_name IN (
    'payment-api',
    'payment-worker',
    'resource-constrained-api'
);


INSERT INTO pods (
    namespace_id,
    workload_id,
    replicaset_id,
    node_id,
    pod_name,
    image,
    phase,
    labels,
    cpu_request_millicores,
    memory_request_mb,
    ready,
    revision
)
SELECT
    w.namespace_id,
    w.workload_id,
    rs.replicaset_id,
    n.node_id,
    data.pod_name,
    w.container_image,
    data.phase::pod_phase,
    w.selector,
    w.cpu_request_millicores,
    w.memory_request_mb,
    data.ready,
    1
FROM workloads w

JOIN replica_sets rs
    ON rs.workload_id = w.workload_id

JOIN namespaces ns
    ON ns.namespace_id = w.namespace_id

JOIN clusters c
    ON c.cluster_id = ns.cluster_id

JOIN (
    VALUES
        ('payment-api', 'payment-api-1', 'worker-01', 'Running', TRUE),
        ('payment-api', 'payment-api-2', 'worker-01', 'Running', TRUE),
        ('payment-api', 'payment-api-3', 'worker-02', 'Running', TRUE),

        ('payment-worker', 'payment-worker-1', 'worker-02', 'Running', TRUE),
        ('payment-worker', 'payment-worker-2', 'worker-01', 'Pending', FALSE),

        ('resource-constrained-api', 'constrained-api-1', NULL, 'Pending', FALSE)
) AS data(
    workload_name,
    pod_name,
    node_name,
    phase,
    ready
)
    ON data.workload_name = w.workload_name

LEFT JOIN nodes n
    ON n.node_name = data.node_name
   AND n.cluster_id = c.cluster_id

WHERE rs.revision = 1;


-- ============================================================
-- 18. CONTAINER INSTANCES
-- ============================================================

INSERT INTO containers (
    pod_id,
    container_name,
    image,
    status
)
SELECT
    pod_id,
    'application',
    image,
    CASE
        WHEN phase = 'Running'
        THEN 'Running'::container_status
        ELSE 'Waiting'::container_status
    END
FROM pods
WHERE workload_id IS NOT NULL;


-- ============================================================
-- 19. SAMPLE SERVICES
-- ============================================================

INSERT INTO services (
    namespace_id,
    service_name,
    service_type,
    selector,
    port,
    target_port
)
SELECT
    namespace_id,
    'payment-service',
    'ClusterIP',
    '{"app":"payment-api"}'::jsonb,
    80,
    8080
FROM namespaces
WHERE namespace_name = 'payments';


-- ============================================================
-- 20. SERVICE ENDPOINT REGISTRATION
-- ============================================================

INSERT INTO service_endpoints (
    service_id,
    pod_id,
    ready
)
SELECT
    s.service_id,
    p.pod_id,
    p.ready
FROM services s

JOIN pods p
    ON p.namespace_id = s.namespace_id
   AND p.labels @> s.selector

WHERE p.phase = 'Running';


-- ============================================================
-- 21. NODE CONDITION RECORDS
-- ============================================================

INSERT INTO node_conditions (
    node_id,
    condition_type,
    status,
    reason,
    message
)
SELECT
    node_id,
    'Ready',
    CASE
        WHEN status = 'Ready'
        THEN 'True'::condition_status
        ELSE 'False'::condition_status
    END,
    CASE
        WHEN status = 'Ready'
        THEN 'KubeletReady'
        ELSE 'NodeUnreachable'
    END,
    'Sample node health condition'
FROM nodes;


-- ============================================================
-- 22. CLUSTER EVENTS
-- ============================================================

INSERT INTO cluster_events (
    cluster_id,
    event_type,
    severity,
    message
)
SELECT
    cluster_id,
    'ClusterInitialized',
    'Normal',
    'Production cluster initialized.'
FROM clusters
WHERE cluster_name = 'production-cluster';


INSERT INTO cluster_events (
    cluster_id,
    node_id,
    event_type,
    severity,
    message
)
SELECT
    n.cluster_id,
    n.node_id,
    'NodeNotReady',
    'Warning',
    'Worker node is unavailable.'
FROM nodes n
WHERE n.node_name = 'worker-03';


INSERT INTO cluster_events (
    cluster_id,
    workload_id,
    event_type,
    severity,
    message
)
SELECT
    ns.cluster_id,
    w.workload_id,
    'FailedScheduling',
    'Warning',
    'Insufficient CPU or memory capacity.'
FROM workloads w
JOIN namespaces ns
    ON ns.namespace_id = w.namespace_id
WHERE w.workload_name = 'resource-constrained-api';


-- ============================================================
-- 23. RETRIEVAL QUERIES
-- ============================================================

-- All production worker nodes and their current state.
SELECT
    c.cluster_name,
    n.node_name,
    n.status,
    n.cpu_allocatable_millicores,
    n.memory_allocatable_mb
FROM nodes n
JOIN clusters c USING (cluster_id)
WHERE c.environment = 'production'
ORDER BY n.node_name;


-- All pods in the payments namespace.
SELECT
    ns.namespace_name,
    p.pod_name,
    p.phase,
    p.ready,
    n.node_name,
    p.restart_count
FROM pods p
JOIN namespaces ns USING (namespace_id)
LEFT JOIN nodes n USING (node_id)
WHERE ns.namespace_name = 'payments'
ORDER BY p.pod_name;


-- ============================================================
-- 24. RESOURCE VALIDATION QUERIES
-- ============================================================

-- Nodes with insufficient requested-resource capacity.
SELECT *
FROM node_resource_utilization
WHERE allocated_cpu_millicores >
      cpu_allocatable_millicores

   OR allocated_memory_mb >
      memory_allocatable_mb;


-- Scheduling candidates for a 500m CPU / 512MB workload.
SELECT *
FROM eligible_nodes(
    (
        SELECT cluster_id
        FROM clusters
        WHERE cluster_name = 'production-cluster'
    ),
    500,
    512
);


-- ============================================================
-- 25. WORKLOAD HEALTH REPORTING
-- ============================================================

SELECT
    workload_name,
    desired_replicas,
    running_replicas,
    ready_replicas,
    failed_replicas,
    health_status
FROM workload_health
ORDER BY workload_name;


-- ============================================================
-- 26. SERVICE DISCOVERY
-- ============================================================

SELECT
    service_name,
    namespace_name,
    pod_name,
    node_name,
    port,
    target_port
FROM ready_service_endpoints
ORDER BY service_name, pod_name;


-- ============================================================
-- 27. EVENT ANALYSIS
-- ============================================================

SELECT
    event_type,
    severity,
    COUNT(*) AS event_count,
    MAX(event_timestamp) AS latest_event
FROM cluster_events
GROUP BY event_type, severity
ORDER BY severity, event_count DESC;


-- ============================================================
-- 28. RECONCILIATION HISTORY
-- ============================================================

SELECT
    w.workload_name,
    r.desired_replicas,
    r.actual_replicas,
    r.generation,
    r.succeeded,
    r.started_at
FROM reconciliation_runs r
JOIN workloads w USING (workload_id)
ORDER BY r.started_at DESC;


-- ============================================================
-- 29. RECONCILIATION EXECUTION
-- ============================================================

SELECT record_reconciliation(workload_id)
FROM workloads
WHERE workload_name = 'payment-api';


-- ============================================================
-- 30. RESOURCE QUOTA VALIDATION
-- ============================================================

WITH namespace_usage AS (
    SELECT
        ns.namespace_id,
        ns.namespace_name,
        COUNT(p.pod_id) FILTER (
            WHERE p.phase IN ('Pending', 'Running')
        ) AS current_pods,

        COALESCE(SUM(
            CASE
                WHEN p.phase IN ('Pending', 'Running')
                THEN p.cpu_request_millicores
                ELSE 0
            END
        ), 0) AS current_cpu,

        COALESCE(SUM(
            CASE
                WHEN p.phase IN ('Pending', 'Running')
                THEN p.memory_request_mb
                ELSE 0
            END
        ), 0) AS current_memory

    FROM namespaces ns

    LEFT JOIN pods p
        ON p.namespace_id = ns.namespace_id

    GROUP BY
        ns.namespace_id,
        ns.namespace_name
)
SELECT
    u.namespace_name,
    u.current_pods,
    q.max_pods,
    u.current_cpu,
    q.max_cpu_millicores,
    u.current_memory,
    q.max_memory_mb,

    (
        u.current_pods <= q.max_pods
        AND u.current_cpu <= q.max_cpu_millicores
        AND u.current_memory <= q.max_memory_mb
    ) AS within_quota

FROM namespace_usage u

JOIN resource_quotas q
    ON q.namespace_id = u.namespace_id;


-- ============================================================
-- 31. TRANSACTIONAL DECLARATIVE SCALING
-- ============================================================

-- Updating desired replicas changes the declared target.
-- It does not itself create or schedule physical pods.
BEGIN;

UPDATE workloads
SET
    desired_replicas = 4,
    generation = generation + 1
WHERE workload_name = 'payment-api'
  AND namespace_id = (
      SELECT namespace_id
      FROM namespaces
      WHERE namespace_name = 'payments'
  );

-- Verify the updated desired specification.
SELECT
    workload_name,
    desired_replicas,
    generation
FROM workloads
WHERE workload_name = 'payment-api';

COMMIT;


-- ============================================================
-- 32. MERGE-READY OPERATIONAL DASHBOARD
-- ============================================================

SELECT
    c.cluster_name,
    c.environment,
    c.status AS cluster_status,

    COUNT(DISTINCT n.node_id) AS total_nodes,

    COUNT(DISTINCT n.node_id) FILTER (
        WHERE n.status = 'Ready'
    ) AS ready_nodes,

    COUNT(DISTINCT p.pod_id) FILTER (
        WHERE p.phase = 'Running'
    ) AS running_pods,

    COUNT(DISTINCT p.pod_id) FILTER (
        WHERE p.phase = 'Pending'
    ) AS pending_pods,

    COUNT(DISTINCT p.pod_id) FILTER (
        WHERE p.phase = 'Failed'
    ) AS failed_pods

FROM clusters c

LEFT JOIN nodes n
    ON n.cluster_id = c.cluster_id

LEFT JOIN namespaces ns
    ON ns.cluster_id = c.cluster_id

LEFT JOIN pods p
    ON p.namespace_id = ns.namespace_id

GROUP BY
    c.cluster_id,
    c.cluster_name,
    c.environment,
    c.status;


-- ============================================================
-- 33. SCHEDULING FAILURE ANALYSIS
-- ============================================================

SELECT
    e.event_timestamp,
    c.cluster_name,
    e.event_type,
    e.severity,
    e.message,
    w.workload_name
FROM cluster_events e

JOIN clusters c
    ON c.cluster_id = e.cluster_id

LEFT JOIN workloads w
    ON w.workload_id = e.workload_id

WHERE e.event_type IN (
    'FailedScheduling',
    'NodeNotReady',
    'OOMKilled',
    'BackOff'
)

ORDER BY e.event_timestamp DESC;


-- ============================================================
-- 34. FINAL SCHEMA CHECK
-- ============================================================

SELECT
    table_schema,
    table_name
FROM information_schema.tables
WHERE table_schema = 'kube_lab'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;


COMMIT;
