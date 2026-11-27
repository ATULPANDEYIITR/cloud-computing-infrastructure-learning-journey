-- ============================================================
-- KUBERNETES PODS
-- Pod architecture, lifecycle, manifests and multi-container Pods
-- PostgreSQL 15+
--
-- Includes:
-- 1. Cluster and namespace management
-- 2. Worker nodes and resource accounting
-- 3. Pod specifications and manifests
-- 4. Application and init containers
-- 5. Shared volumes and container mounts
-- 6. Pod lifecycle and conditions
-- 7. Container states and restart policies
-- 8. Scheduling and resource allocation
-- 9. Events, probes and status checks
-- 10. Termination and operational reporting
--
-- Resource quantities:
-- CPU is represented in millicores.
-- Memory is represented in MiB.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS kubernetes_lab;

SET search_path TO kubernetes_lab, public;

-- ------------------------------------------------------------
-- ENUMERATED DOMAIN STATES
-- ------------------------------------------------------------

CREATE TYPE pod_phase AS ENUM (
    'Pending',
    'Running',
    'Succeeded',
    'Failed',
    'Unknown'
);

CREATE TYPE container_state AS ENUM (
    'Waiting',
    'Running',
    'Terminated'
);

CREATE TYPE restart_policy AS ENUM (
    'Always',
    'OnFailure',
    'Never'
);

CREATE TYPE container_role AS ENUM (
    'Application',
    'Init',
    'Sidecar',
    'Adapter',
    'Ambassador'
);

CREATE TYPE condition_status AS ENUM (
    'True',
    'False',
    'Unknown'
);

CREATE TYPE event_type AS ENUM (
    'Normal',
    'Warning'
);

-- ------------------------------------------------------------
-- CLUSTER AND NAMESPACE
-- ------------------------------------------------------------

CREATE TABLE clusters (
    cluster_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_name VARCHAR(100) NOT NULL UNIQUE,
    kubernetes_version VARCHAR(30) NOT NULL,
    region VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (length(trim(cluster_name)) > 0)
);

CREATE TABLE namespaces (
    namespace_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_id BIGINT NOT NULL REFERENCES clusters(cluster_id),
    namespace_name VARCHAR(63) NOT NULL,
    environment VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (cluster_id, namespace_name)
);

CREATE INDEX idx_namespaces_environment
    ON namespaces(environment);

-- ------------------------------------------------------------
-- WORKER NODES
-- ------------------------------------------------------------

CREATE TABLE worker_nodes (
    node_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_id BIGINT NOT NULL REFERENCES clusters(cluster_id),
    node_name VARCHAR(100) NOT NULL,
    cpu_capacity_millicores INTEGER NOT NULL,
    memory_capacity_mib INTEGER NOT NULL,
    allocated_cpu_millicores INTEGER NOT NULL DEFAULT 0,
    allocated_memory_mib INTEGER NOT NULL DEFAULT 0,
    schedulable BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (cluster_id, node_name),

    CHECK (cpu_capacity_millicores > 0),
    CHECK (memory_capacity_mib > 0),
    CHECK (allocated_cpu_millicores >= 0),
    CHECK (allocated_memory_mib >= 0),
    CHECK (
        allocated_cpu_millicores <= cpu_capacity_millicores
    ),
    CHECK (
        allocated_memory_mib <= memory_capacity_mib
    )
);

CREATE INDEX idx_nodes_schedulable
    ON worker_nodes(cluster_id, schedulable);

-- ------------------------------------------------------------
-- SERVICE ACCOUNTS
-- ------------------------------------------------------------

CREATE TABLE service_accounts (
    service_account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    namespace_id BIGINT NOT NULL REFERENCES namespaces(namespace_id),
    account_name VARCHAR(100) NOT NULL,
    automount_token BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (namespace_id, account_name)
);

-- ------------------------------------------------------------
-- POD SPECIFICATIONS
-- ------------------------------------------------------------

CREATE TABLE pods (
    pod_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    namespace_id BIGINT NOT NULL REFERENCES namespaces(namespace_id),
    node_id BIGINT REFERENCES worker_nodes(node_id),
    service_account_id BIGINT REFERENCES service_accounts(service_account_id),

    pod_name VARCHAR(253) NOT NULL,
    uid UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),

    phase pod_phase NOT NULL DEFAULT 'Pending',
    restart_policy restart_policy NOT NULL DEFAULT 'Always',

    termination_grace_period_seconds INTEGER NOT NULL DEFAULT 30,

    labels JSONB NOT NULL DEFAULT '{}'::jsonb,
    annotations JSONB NOT NULL DEFAULT '{}'::jsonb,

    desired_cpu_millicores INTEGER NOT NULL DEFAULT 100,
    desired_memory_mib INTEGER NOT NULL DEFAULT 128,

    scheduled_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    deletion_timestamp TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (namespace_id, pod_name),

    CHECK (pod_name ~ '^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'),
    CHECK (termination_grace_period_seconds >= 0),
    CHECK (desired_cpu_millicores > 0),
    CHECK (desired_memory_mib > 0),
    CHECK (jsonb_typeof(labels) = 'object'),
    CHECK (jsonb_typeof(annotations) = 'object')
);

CREATE INDEX idx_pods_namespace_phase
    ON pods(namespace_id, phase);

CREATE INDEX idx_pods_node
    ON pods(node_id)
    WHERE node_id IS NOT NULL;

CREATE INDEX idx_pods_labels
    ON pods USING GIN(labels);

CREATE INDEX idx_pods_created
    ON pods(created_at DESC);

-- ------------------------------------------------------------
-- CONTAINER SPECIFICATIONS
-- ------------------------------------------------------------

CREATE TABLE containers (
    container_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pod_id BIGINT NOT NULL REFERENCES pods(pod_id) ON DELETE CASCADE,

    container_name VARCHAR(63) NOT NULL,
    image VARCHAR(253) NOT NULL,
    role container_role NOT NULL DEFAULT 'Application',

    cpu_request_millicores INTEGER NOT NULL DEFAULT 100,
    memory_request_mib INTEGER NOT NULL DEFAULT 128,

    cpu_limit_millicores INTEGER,
    memory_limit_mib INTEGER,

    container_port INTEGER,

    command JSONB NOT NULL DEFAULT '[]'::jsonb,
    args JSONB NOT NULL DEFAULT '[]'::jsonb,
    environment JSONB NOT NULL DEFAULT '{}'::jsonb,

    essential BOOLEAN NOT NULL DEFAULT TRUE,
    privileged BOOLEAN NOT NULL DEFAULT FALSE,
    read_only_root_filesystem BOOLEAN NOT NULL DEFAULT TRUE,

    state container_state NOT NULL DEFAULT 'Waiting',
    ready BOOLEAN NOT NULL DEFAULT FALSE,
    restart_count INTEGER NOT NULL DEFAULT 0,
    last_exit_code INTEGER,

    started_at TIMESTAMPTZ,
    terminated_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (pod_id, container_name),

    CHECK (container_name ~ '^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'),
    CHECK (length(trim(image)) > 0),
    CHECK (cpu_request_millicores > 0),
    CHECK (memory_request_mib > 0),
    CHECK (
        cpu_limit_millicores IS NULL
        OR cpu_limit_millicores >= cpu_request_millicores
    ),
    CHECK (
        memory_limit_mib IS NULL
        OR memory_limit_mib >= memory_request_mib
    ),
    CHECK (
        container_port IS NULL
        OR container_port BETWEEN 1 AND 65535
    ),
    CHECK (restart_count >= 0),
    CHECK (
        last_exit_code IS NULL
        OR last_exit_code >= 0
    ),
    CHECK (jsonb_typeof(command) = 'array'),
    CHECK (jsonb_typeof(args) = 'array'),
    CHECK (jsonb_typeof(environment) = 'object')
);

CREATE INDEX idx_containers_pod_state
    ON containers(pod_id, state);

CREATE INDEX idx_containers_ready
    ON containers(pod_id, ready);

CREATE INDEX idx_containers_image
    ON containers(image);

-- ------------------------------------------------------------
-- POD VOLUMES
-- ------------------------------------------------------------

CREATE TABLE pod_volumes (
    volume_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pod_id BIGINT NOT NULL REFERENCES pods(pod_id) ON DELETE CASCADE,
    volume_name VARCHAR(100) NOT NULL,
    volume_type VARCHAR(40) NOT NULL,
    source_configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (pod_id, volume_name),

    CHECK (jsonb_typeof(source_configuration) = 'object')
);

CREATE TABLE volume_mounts (
    mount_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    container_id BIGINT NOT NULL REFERENCES containers(container_id)
        ON DELETE CASCADE,
    volume_id BIGINT NOT NULL REFERENCES pod_volumes(volume_id)
        ON DELETE CASCADE,
    mount_path VARCHAR(500) NOT NULL,
    read_only BOOLEAN NOT NULL DEFAULT FALSE,

    UNIQUE (container_id, mount_path),

    CHECK (mount_path LIKE '/%')
);

CREATE INDEX idx_volume_mounts_volume
    ON volume_mounts(volume_id);

-- ------------------------------------------------------------
-- CONTAINER PORTS
-- ------------------------------------------------------------

CREATE TABLE container_ports (
    port_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    container_id BIGINT NOT NULL REFERENCES containers(container_id)
        ON DELETE CASCADE,
    container_port INTEGER NOT NULL,
    protocol VARCHAR(10) NOT NULL DEFAULT 'TCP',
    port_name VARCHAR(63),

    UNIQUE (container_id, container_port, protocol),

    CHECK (container_port BETWEEN 1 AND 65535),
    CHECK (protocol IN ('TCP', 'UDP', 'SCTP'))
);

-- ------------------------------------------------------------
-- POD CONDITIONS
-- ------------------------------------------------------------

CREATE TABLE pod_conditions (
    condition_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pod_id BIGINT NOT NULL REFERENCES pods(pod_id) ON DELETE CASCADE,
    condition_type VARCHAR(50) NOT NULL,
    status condition_status NOT NULL,
    reason VARCHAR(100),
    message TEXT,
    last_transition_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (pod_id, condition_type)
);

CREATE INDEX idx_pod_conditions_status
    ON pod_conditions(pod_id, status);

-- ------------------------------------------------------------
-- POD EVENTS
-- ------------------------------------------------------------

CREATE TABLE pod_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pod_id BIGINT REFERENCES pods(pod_id) ON DELETE SET NULL,
    event_type event_type NOT NULL DEFAULT 'Normal',
    reason VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    first_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (occurrence_count > 0)
);

CREATE INDEX idx_pod_events_recent
    ON pod_events(pod_id, last_timestamp DESC);

-- ------------------------------------------------------------
-- HEALTH PROBES
-- ------------------------------------------------------------

CREATE TABLE container_probes (
    probe_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    container_id BIGINT NOT NULL REFERENCES containers(container_id)
        ON DELETE CASCADE,

    probe_type VARCHAR(20) NOT NULL,
    probe_method VARCHAR(20) NOT NULL,
    probe_configuration JSONB NOT NULL DEFAULT '{}'::jsonb,

    initial_delay_seconds INTEGER NOT NULL DEFAULT 0,
    period_seconds INTEGER NOT NULL DEFAULT 10,
    timeout_seconds INTEGER NOT NULL DEFAULT 1,
    failure_threshold INTEGER NOT NULL DEFAULT 3,
    success_threshold INTEGER NOT NULL DEFAULT 1,

    last_result BOOLEAN,
    last_checked_at TIMESTAMPTZ,

    CHECK (probe_type IN ('Liveness', 'Readiness', 'Startup')),
    CHECK (
        probe_method IN ('HTTP', 'TCP', 'Exec', 'GRPC')
    ),
    CHECK (initial_delay_seconds >= 0),
    CHECK (period_seconds > 0),
    CHECK (timeout_seconds > 0),
    CHECK (failure_threshold > 0),
    CHECK (success_threshold > 0),
    CHECK (jsonb_typeof(probe_configuration) = 'object'),

    UNIQUE (container_id, probe_type)
);

-- ------------------------------------------------------------
-- RESOURCE ALLOCATION HISTORY
-- ------------------------------------------------------------

CREATE TABLE resource_allocations (
    allocation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pod_id BIGINT NOT NULL REFERENCES pods(pod_id),
    node_id BIGINT NOT NULL REFERENCES worker_nodes(node_id),

    cpu_millicores INTEGER NOT NULL,
    memory_mib INTEGER NOT NULL,

    allocated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    released_at TIMESTAMPTZ,

    CHECK (cpu_millicores > 0),
    CHECK (memory_mib > 0),
    CHECK (released_at IS NULL OR released_at >= allocated_at)
);

CREATE UNIQUE INDEX idx_active_pod_allocation
    ON resource_allocations(pod_id)
    WHERE released_at IS NULL;

CREATE INDEX idx_allocations_node
    ON resource_allocations(node_id, allocated_at DESC);

-- ------------------------------------------------------------
-- UPDATED_AT TRIGGER
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_pods_updated
BEFORE UPDATE ON pods
FOR EACH ROW
EXECUTE FUNCTION update_timestamp();

-- ------------------------------------------------------------
-- CONTAINER STATE INTEGRITY
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION enforce_container_state()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.ready AND NEW.state <> 'Running' THEN
        RAISE EXCEPTION
            'A container can only be ready while Running';
    END IF;

    IF NEW.state = 'Terminated' THEN
        NEW.ready = FALSE;

        IF NEW.terminated_at IS NULL THEN
            NEW.terminated_at = CURRENT_TIMESTAMP;
        END IF;
    END IF;

    IF NEW.state = 'Running' THEN
        NEW.terminated_at = NULL;
        NEW.last_exit_code = NULL;

        IF NEW.started_at IS NULL THEN
            NEW.started_at = CURRENT_TIMESTAMP;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_container_state
BEFORE INSERT OR UPDATE ON containers
FOR EACH ROW
EXECUTE FUNCTION enforce_container_state();

-- ------------------------------------------------------------
-- EVENT INSERTION FUNCTION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION record_pod_event(
    p_pod_id BIGINT,
    p_type event_type,
    p_reason VARCHAR,
    p_message TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    result_id BIGINT;
BEGIN
    INSERT INTO pod_events (
        pod_id,
        event_type,
        reason,
        message
    )
    VALUES (
        p_pod_id,
        p_type,
        p_reason,
        p_message
    )
    RETURNING event_id INTO result_id;

    RETURN result_id;
END;
$$;

-- ------------------------------------------------------------
-- POD READINESS EVALUATION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION calculate_pod_readiness(
    p_pod_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    total_count INTEGER;
    ready_count INTEGER;
    current_phase pod_phase;
BEGIN
    SELECT phase
    INTO current_phase
    FROM pods
    WHERE pod_id = p_pod_id;

    IF NOT FOUND OR current_phase <> 'Running' THEN
        RETURN FALSE;
    END IF;

    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE state = 'Running' AND ready = TRUE
        )
    INTO total_count, ready_count
    FROM containers
    WHERE pod_id = p_pod_id
      AND role <> 'Init';

    RETURN total_count > 0 AND total_count = ready_count;
END;
$$;

-- ------------------------------------------------------------
-- NODE RESOURCE SCHEDULING
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION schedule_pod(
    p_pod_id BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    target_node BIGINT;
    target_cpu INTEGER;
    target_memory INTEGER;
    app_cpu INTEGER;
    app_memory INTEGER;
    init_cpu INTEGER;
    init_memory INTEGER;
    allocation_cpu INTEGER;
    allocation_memory INTEGER;
    pod_status pod_phase;
    existing_allocation BOOLEAN;
BEGIN
    -- Lock Pod to prevent concurrent scheduling.
    SELECT phase
    INTO pod_status
    FROM pods
    WHERE pod_id = p_pod_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pod % does not exist', p_pod_id;
    END IF;

    IF pod_status <> 'Pending' THEN
        RAISE EXCEPTION 'Only Pending Pods can be scheduled';
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM resource_allocations
        WHERE pod_id = p_pod_id
          AND released_at IS NULL
    )
    INTO existing_allocation;

    IF existing_allocation THEN
        RAISE EXCEPTION 'Pod already has an active allocation';
    END IF;

    -- Regular application containers contribute additive requests.
    SELECT
        COALESCE(SUM(cpu_request_millicores), 0),
        COALESCE(SUM(memory_request_mib), 0)
    INTO app_cpu, app_memory
    FROM containers
    WHERE pod_id = p_pod_id
      AND role <> 'Init';

    -- Ordinary init containers run sequentially.
    SELECT
        COALESCE(MAX(cpu_request_millicores), 0),
        COALESCE(MAX(memory_request_mib), 0)
    INTO init_cpu, init_memory
    FROM containers
    WHERE pod_id = p_pod_id
      AND role = 'Init';

    allocation_cpu := GREATEST(app_cpu, init_cpu);
    allocation_memory := GREATEST(app_memory, init_memory);

    IF allocation_cpu <= 0 OR allocation_memory <= 0 THEN
        RAISE EXCEPTION 'Invalid Pod resource requirements';
    END IF;

    -- Row locking prevents concurrent allocation beyond node capacity.
    SELECT node_id
    INTO target_node
    FROM worker_nodes
    WHERE cluster_id = (
        SELECT n.cluster_id
        FROM namespaces ns
        JOIN clusters n ON n.cluster_id = ns.cluster_id
        JOIN pods p ON p.namespace_id = ns.namespace_id
        WHERE p.pod_id = p_pod_id
    )
      AND schedulable = TRUE
      AND allocated_cpu_millicores + allocation_cpu
            <= cpu_capacity_millicores
      AND allocated_memory_mib + allocation_memory
            <= memory_capacity_mib
    ORDER BY
        allocated_cpu_millicores,
        allocated_memory_mib,
        node_id
    LIMIT 1
    FOR UPDATE;

    IF target_node IS NULL THEN
        PERFORM record_pod_event(
            p_pod_id,
            'Warning',
            'FailedScheduling',
            'No worker node has sufficient available resources'
        );

        RETURN NULL;
    END IF;

    UPDATE worker_nodes
    SET
        allocated_cpu_millicores =
            allocated_cpu_millicores + allocation_cpu,
        allocated_memory_mib =
            allocated_memory_mib + allocation_memory
    WHERE node_id = target_node;

    INSERT INTO resource_allocations (
        pod_id,
        node_id,
        cpu_millicores,
        memory_mib
    )
    VALUES (
        p_pod_id,
        target_node,
        allocation_cpu,
        allocation_memory
    );

    UPDATE pods
    SET
        node_id = target_node,
        scheduled_at = CURRENT_TIMESTAMP
    WHERE pod_id = p_pod_id;

    INSERT INTO pod_conditions (
        pod_id,
        condition_type,
        status,
        reason,
        message
    )
    VALUES (
        p_pod_id,
        'PodScheduled',
        'True',
        'Scheduled',
        'Pod assigned to a worker node'
    )
    ON CONFLICT (pod_id, condition_type)
    DO UPDATE SET
        status = 'True',
        reason = 'Scheduled',
        last_transition_time = CURRENT_TIMESTAMP;

    PERFORM record_pod_event(
        p_pod_id,
        'Normal',
        'Scheduled',
        'Pod successfully assigned to node ' || target_node
    );

    RETURN target_node;
END;
$$;

-- ------------------------------------------------------------
-- INIT CONTAINER EXECUTION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION complete_init_container(
    p_container_id BIGINT,
    p_exit_code INTEGER
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    current_pod BIGINT;
    current_role container_role;
    current_state container_state;
BEGIN
    SELECT pod_id, role, state
    INTO current_pod, current_role, current_state
    FROM containers
    WHERE container_id = p_container_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Container does not exist';
    END IF;

    IF current_role <> 'Init' THEN
        RAISE EXCEPTION 'Container is not an init container';
    END IF;

    IF current_state <> 'Running' THEN
        RAISE EXCEPTION 'Init container must be Running';
    END IF;

    IF p_exit_code < 0 THEN
        RAISE EXCEPTION 'Invalid exit code';
    END IF;

    UPDATE containers
    SET
        state = 'Terminated',
        ready = FALSE,
        last_exit_code = p_exit_code,
        terminated_at = CURRENT_TIMESTAMP
    WHERE container_id = p_container_id;

    IF p_exit_code <> 0 THEN
        UPDATE pods
        SET phase = 'Pending'
        WHERE pod_id = current_pod;

        PERFORM record_pod_event(
            current_pod,
            'Warning',
            'InitContainerFailed',
            'Init container exited unsuccessfully'
        );

        RETURN;
    END IF;

    PERFORM record_pod_event(
        current_pod,
        'Normal',
        'InitContainerCompleted',
        'Init container completed successfully'
    );
END;
$$;

-- ------------------------------------------------------------
-- POD START FUNCTION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION start_pod(
    p_pod_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    current_phase pod_phase;
    assigned_node BIGINT;
    init_total INTEGER;
    init_success INTEGER;
BEGIN
    SELECT phase, node_id
    INTO current_phase, assigned_node
    FROM pods
    WHERE pod_id = p_pod_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pod does not exist';
    END IF;

    IF current_phase <> 'Pending' OR assigned_node IS NULL THEN
        RAISE EXCEPTION 'Pod must be scheduled and Pending';
    END IF;

    SELECT COUNT(*)
    INTO init_total
    FROM containers
    WHERE pod_id = p_pod_id
      AND role = 'Init';

    SELECT COUNT(*)
    INTO init_success
    FROM containers
    WHERE pod_id = p_pod_id
      AND role = 'Init'
      AND state = 'Terminated'
      AND last_exit_code = 0;

    IF init_total <> init_success THEN
        RAISE EXCEPTION
            'All init containers must complete successfully';
    END IF;

    UPDATE containers
    SET
        state = 'Running',
        ready = FALSE,
        started_at = CURRENT_TIMESTAMP
    WHERE pod_id = p_pod_id
      AND role <> 'Init';

    UPDATE pods
    SET
        phase = 'Running',
        started_at = CURRENT_TIMESTAMP
    WHERE pod_id = p_pod_id;

    INSERT INTO pod_conditions (
        pod_id,
        condition_type,
        status,
        reason,
        message
    )
    VALUES
        (
            p_pod_id,
            'Initialized',
            'True',
            'InitContainersCompleted',
            'All init containers completed'
        ),
        (
            p_pod_id,
            'Ready',
            'False',
            'ContainersStarting',
            'Application containers are starting'
        )
    ON CONFLICT (pod_id, condition_type)
    DO UPDATE SET
        status = EXCLUDED.status,
        reason = EXCLUDED.reason,
        message = EXCLUDED.message,
        last_transition_time = CURRENT_TIMESTAMP;

    PERFORM record_pod_event(
        p_pod_id,
        'Normal',
        'Started',
        'Application containers started'
    );
END;
$$;

-- ------------------------------------------------------------
-- CONTAINER READINESS UPDATE
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION update_container_readiness(
    p_container_id BIGINT,
    p_ready BOOLEAN
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    current_pod BIGINT;
    current_state container_state;
BEGIN
    SELECT pod_id, state
    INTO current_pod, current_state
    FROM containers
    WHERE container_id = p_container_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Container does not exist';
    END IF;

    IF current_state <> 'Running' THEN
        RAISE EXCEPTION 'Only running containers can become ready';
    END IF;

    UPDATE containers
    SET ready = p_ready
    WHERE container_id = p_container_id;

    INSERT INTO pod_conditions (
        pod_id,
        condition_type,
        status,
        reason,
        message
    )
    VALUES (
        current_pod,
        'Ready',
        CASE
            WHEN calculate_pod_readiness(current_pod)
                THEN 'True'::condition_status
            ELSE 'False'::condition_status
        END,
        'ReadinessEvaluation',
        'Pod readiness evaluated from application containers'
    )
    ON CONFLICT (pod_id, condition_type)
    DO UPDATE SET
        status = EXCLUDED.status,
        reason = EXCLUDED.reason,
        message = EXCLUDED.message,
        last_transition_time = CURRENT_TIMESTAMP;

    PERFORM record_pod_event(
        current_pod,
        'Normal',
        'ReadinessChanged',
        'Container readiness changed to ' || p_ready
    );
END;
$$;

-- ------------------------------------------------------------
-- CONTAINER TERMINATION AND RESTART
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION terminate_container(
    p_container_id BIGINT,
    p_exit_code INTEGER
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    current_pod BIGINT;
    current_policy restart_policy;
    current_state container_state;
    current_essential BOOLEAN;
    should_restart BOOLEAN;
    all_terminated BOOLEAN;
BEGIN
    IF p_exit_code < 0 THEN
        RAISE EXCEPTION 'Exit code cannot be negative';
    END IF;

    SELECT
        c.pod_id,
        c.state,
        c.essential,
        p.restart_policy
    INTO
        current_pod,
        current_state,
        current_essential,
        current_policy
    FROM containers c
    JOIN pods p ON p.pod_id = c.pod_id
    WHERE c.container_id = p_container_id
    FOR UPDATE OF c, p;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Container does not exist';
    END IF;

    IF current_state <> 'Running' THEN
        RAISE EXCEPTION 'Container is not Running';
    END IF;

    should_restart :=
        current_policy = 'Always'
        OR (
            current_policy = 'OnFailure'
            AND p_exit_code <> 0
        );

    UPDATE containers
    SET
        state = 'Terminated',
        ready = FALSE,
        last_exit_code = p_exit_code,
        terminated_at = CURRENT_TIMESTAMP
    WHERE container_id = p_container_id;

    IF should_restart THEN
        UPDATE containers
        SET
            restart_count = restart_count + 1,
            state = 'Running',
            ready = FALSE,
            started_at = CURRENT_TIMESTAMP,
            terminated_at = NULL,
            last_exit_code = NULL
        WHERE container_id = p_container_id;

        PERFORM record_pod_event(
            current_pod,
            'Warning',
            'BackOff',
            'Container restarted according to Pod restart policy'
        );

        RETURN TRUE;
    END IF;

    IF p_exit_code <> 0 AND current_essential THEN
        UPDATE pods
        SET phase = 'Failed'
        WHERE pod_id = current_pod;

        PERFORM record_pod_event(
            current_pod,
            'Warning',
            'ContainerFailed',
            'Essential application container failed'
        );

        RETURN FALSE;
    END IF;

    SELECT NOT EXISTS (
        SELECT 1
        FROM containers
        WHERE pod_id = current_pod
          AND role <> 'Init'
          AND state <> 'Terminated'
    )
    INTO all_terminated;

    IF all_terminated THEN
        UPDATE pods
        SET phase = 'Succeeded'
        WHERE pod_id = current_pod;
    END IF;

    RETURN FALSE;
END;
$$;

-- ------------------------------------------------------------
-- RELEASE NODE RESOURCES
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION release_pod_resources(
    p_pod_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    allocation RECORD;
BEGIN
    SELECT *
    INTO allocation
    FROM resource_allocations
    WHERE pod_id = p_pod_id
      AND released_at IS NULL
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    UPDATE worker_nodes
    SET
        allocated_cpu_millicores =
            allocated_cpu_millicores - allocation.cpu_millicores,
        allocated_memory_mib =
            allocated_memory_mib - allocation.memory_mib
    WHERE node_id = allocation.node_id;

    UPDATE resource_allocations
    SET released_at = CURRENT_TIMESTAMP
    WHERE allocation_id = allocation.allocation_id;

    UPDATE pods
    SET node_id = NULL
    WHERE pod_id = p_pod_id;

    PERFORM record_pod_event(
        p_pod_id,
        'Normal',
        'ResourcesReleased',
        'Worker node resource allocation released'
    );
END;
$$;

-- ------------------------------------------------------------
-- POD TERMINATION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION terminate_pod(
    p_pod_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    current_phase pod_phase;
BEGIN
    SELECT phase
    INTO current_phase
    FROM pods
    WHERE pod_id = p_pod_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pod does not exist';
    END IF;

    IF current_phase IN ('Succeeded', 'Failed') THEN
        PERFORM release_pod_resources(p_pod_id);
        RETURN;
    END IF;

    UPDATE pods
    SET
        deletion_timestamp = CURRENT_TIMESTAMP,
        phase = 'Succeeded'
    WHERE pod_id = p_pod_id;

    UPDATE containers
    SET
        state = 'Terminated',
        ready = FALSE,
        last_exit_code = 143,
        terminated_at = CURRENT_TIMESTAMP
    WHERE pod_id = p_pod_id
      AND state = 'Running';

    UPDATE pod_conditions
    SET
        status = 'False',
        reason = 'Terminating',
        message = 'Pod is terminating'
    WHERE pod_id = p_pod_id
      AND condition_type = 'Ready';

    PERFORM release_pod_resources(p_pod_id);

    PERFORM record_pod_event(
        p_pod_id,
        'Normal',
        'Killing',
        'Pod termination completed'
    );
END;
$$;

-- ------------------------------------------------------------
-- MULTI-CONTAINER POD SHARING VALIDATION
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW pod_container_architecture AS
SELECT
    p.pod_id,
    p.pod_name,
    ns.namespace_name,
    c.container_id,
    c.container_name,
    c.role,
    c.image,
    c.state,
    c.ready,
    c.restart_count,
    c.cpu_request_millicores,
    c.memory_request_mib
FROM pods p
JOIN namespaces ns ON ns.namespace_id = p.namespace_id
JOIN containers c ON c.pod_id = p.pod_id;

CREATE OR REPLACE VIEW pod_volume_sharing AS
SELECT
    p.pod_name,
    pv.volume_name,
    c.container_name,
    vm.mount_path,
    vm.read_only
FROM pod_volumes pv
JOIN pods p ON p.pod_id = pv.pod_id
JOIN volume_mounts vm ON vm.volume_id = pv.volume_id
JOIN containers c ON c.container_id = vm.container_id;

-- ------------------------------------------------------------
-- POD OPERATIONAL REPORT
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW pod_operational_report AS
SELECT
    p.pod_id,
    ns.namespace_name,
    p.pod_name,
    p.phase,
    p.restart_policy,
    wn.node_name,

    COUNT(c.container_id) FILTER (
        WHERE c.role <> 'Init'
    ) AS application_container_count,

    COUNT(c.container_id) FILTER (
        WHERE c.role = 'Init'
    ) AS init_container_count,

    COUNT(c.container_id) FILTER (
        WHERE c.role <> 'Init'
          AND c.ready = TRUE
          AND c.state = 'Running'
    ) AS ready_container_count,

    COALESCE(SUM(c.restart_count), 0) AS total_restart_count,

    p.desired_cpu_millicores,
    p.desired_memory_mib,

    calculate_pod_readiness(p.pod_id) AS pod_ready,

    p.created_at,
    p.started_at

FROM pods p
JOIN namespaces ns ON ns.namespace_id = p.namespace_id
LEFT JOIN worker_nodes wn ON wn.node_id = p.node_id
LEFT JOIN containers c ON c.pod_id = p.pod_id
GROUP BY
    p.pod_id,
    ns.namespace_name,
    wn.node_name;

-- ------------------------------------------------------------
-- SAMPLE CLUSTER
-- ------------------------------------------------------------

INSERT INTO clusters (
    cluster_name,
    kubernetes_version,
    region
)
VALUES
    ('production-cluster', '1.31', 'ap-south-1'),
    ('development-cluster', '1.31', 'ap-south-1');

INSERT INTO namespaces (
    cluster_id,
    namespace_name,
    environment
)
SELECT cluster_id, 'production', 'production'
FROM clusters
WHERE cluster_name = 'production-cluster';

INSERT INTO namespaces (
    cluster_id,
    namespace_name,
    environment
)
SELECT cluster_id, 'development', 'development'
FROM clusters
WHERE cluster_name = 'development-cluster';

INSERT INTO worker_nodes (
    cluster_id,
    node_name,
    cpu_capacity_millicores,
    memory_capacity_mib
)
SELECT
    cluster_id,
    'worker-01',
    4000,
    8192
FROM clusters
WHERE cluster_name = 'production-cluster';

INSERT INTO worker_nodes (
    cluster_id,
    node_name,
    cpu_capacity_millicores,
    memory_capacity_mib
)
SELECT
    cluster_id,
    'worker-02',
    2000,
    4096
FROM clusters
WHERE cluster_name = 'production-cluster';

INSERT INTO service_accounts (
    namespace_id,
    account_name,
    automount_token
)
SELECT
    namespace_id,
    'orders-service',
    FALSE
FROM namespaces
WHERE namespace_name = 'production';

-- ------------------------------------------------------------
-- APPLICATION POD
-- ------------------------------------------------------------

INSERT INTO pods (
    namespace_id,
    service_account_id,
    pod_name,
    restart_policy,
    termination_grace_period_seconds,
    labels,
    annotations
)
SELECT
    ns.namespace_id,
    sa.service_account_id,
    'orders-api',
    'Always',
    30,
    '{"app":"orders","tier":"backend","environment":"production"}',
    '{"owner":"platform-team","purpose":"order processing"}'
FROM namespaces ns
JOIN service_accounts sa
    ON sa.namespace_id = ns.namespace_id
WHERE ns.namespace_name = 'production'
  AND sa.account_name = 'orders-service';

-- ------------------------------------------------------------
-- CONTAINER DEFINITIONS
-- ------------------------------------------------------------

INSERT INTO containers (
    pod_id,
    container_name,
    image,
    role,
    cpu_request_millicores,
    memory_request_mib,
    cpu_limit_millicores,
    memory_limit_mib,
    container_port,
    essential,
    read_only_root_filesystem
)
SELECT
    pod_id,
    'api',
    'nginx:1.27',
    'Application',
    300,
    256,
    1000,
    512,
    8080,
    TRUE,
    TRUE
FROM pods
WHERE pod_name = 'orders-api';

INSERT INTO containers (
    pod_id,
    container_name,
    image,
    role,
    cpu_request_millicores,
    memory_request_mib,
    essential
)
SELECT
    pod_id,
    'log-agent',
    'fluent-bit:3.1',
    'Sidecar',
    100,
    128,
    TRUE
FROM pods
WHERE pod_name = 'orders-api';

INSERT INTO containers (
    pod_id,
    container_name,
    image,
    role,
    cpu_request_millicores,
    memory_request_mib,
    essential
)
SELECT
    pod_id,
    'config-init',
    'busybox:1.36',
    'Init',
    50,
    64,
    TRUE
FROM pods
WHERE pod_name = 'orders-api';

-- ------------------------------------------------------------
-- PORTS AND PROBES
-- ------------------------------------------------------------

INSERT INTO container_ports (
    container_id,
    container_port,
    protocol,
    port_name
)
SELECT
    container_id,
    8080,
    'TCP',
    'http'
FROM containers
WHERE container_name = 'api';

INSERT INTO container_probes (
    container_id,
    probe_type,
    probe_method,
    probe_configuration,
    initial_delay_seconds,
    period_seconds,
    timeout_seconds,
    failure_threshold
)
SELECT
    container_id,
    'Readiness',
    'HTTP',
    '{"path":"/health/ready","port":8080}',
    5,
    10,
    2,
    3
FROM containers
WHERE container_name = 'api';

INSERT INTO container_probes (
    container_id,
    probe_type,
    probe_method,
    probe_configuration,
    initial_delay_seconds,
    period_seconds,
    failure_threshold
)
SELECT
    container_id,
    'Liveness',
    'HTTP',
    '{"path":"/health/live","port":8080}',
    10,
    15,
    3
FROM containers
WHERE container_name = 'api';

-- ------------------------------------------------------------
-- SHARED VOLUME
-- ------------------------------------------------------------

INSERT INTO pod_volumes (
    pod_id,
    volume_name,
    volume_type,
    source_configuration
)
SELECT
    pod_id,
    'shared-logs',
    'emptyDir',
    '{"medium":"","sizeLimit":"1Gi"}'
FROM pods
WHERE pod_name = 'orders-api';

INSERT INTO volume_mounts (
    container_id,
    volume_id,
    mount_path,
    read_only
)
SELECT
    c.container_id,
    v.volume_id,
    '/var/log/application',
    FALSE
FROM containers c
JOIN pod_volumes v ON v.pod_id = c.pod_id
WHERE c.container_name IN ('api', 'log-agent')
  AND v.volume_name = 'shared-logs';

-- ------------------------------------------------------------
-- SECOND POD: BATCH WORKLOAD
-- ------------------------------------------------------------

INSERT INTO pods (
    namespace_id,
    pod_name,
    restart_policy,
    desired_cpu_millicores,
    desired_memory_mib
)
SELECT
    namespace_id,
    'nightly-report',
    'Never',
    200,
    256
FROM namespaces
WHERE namespace_name = 'production';

INSERT INTO containers (
    pod_id,
    container_name,
    image,
    role,
    cpu_request_millicores,
    memory_request_mib
)
SELECT
    pod_id,
    'processor',
    'python:3.13-slim',
    'Application',
    200,
    256
FROM pods
WHERE pod_name = 'nightly-report';

-- ------------------------------------------------------------
-- INVALID CASES ARE TESTED IN ROLLED-BACK TRANSACTIONS
-- ------------------------------------------------------------

DO $$
BEGIN
    BEGIN
        INSERT INTO pods (
            namespace_id,
            pod_name,
            desired_cpu_millicores
        )
        SELECT namespace_id, 'invalid-pod', 0
        FROM namespaces
        WHERE namespace_name = 'production';

        RAISE EXCEPTION 'Expected invalid resource request to fail';

    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'Correctly rejected invalid CPU request';
    END;

    BEGIN
        INSERT INTO containers (
            pod_id,
            container_name,
            image,
            cpu_request_millicores,
            memory_request_mib
        )
        SELECT
            pod_id,
            'invalid-container',
            'nginx:latest',
            100,
            128
        FROM pods
        WHERE pod_name = 'orders-api';

        UPDATE containers
        SET ready = TRUE
        WHERE container_name = 'invalid-container';

        RAISE EXCEPTION 'Expected invalid state to fail';

    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Invalid container state rejected';
    END;
END;
$$;

COMMIT;

-- ------------------------------------------------------------
-- TRANSACTIONAL WORKFLOW EXECUTION
-- ------------------------------------------------------------

-- Schedule the application Pod.
BEGIN;

SELECT schedule_pod(pod_id)
FROM pods
WHERE pod_name = 'orders-api';

COMMIT;

-- Start init container.
UPDATE containers
SET state = 'Running',
    started_at = CURRENT_TIMESTAMP
WHERE container_name = 'config-init'
  AND pod_id = (
      SELECT pod_id FROM pods WHERE pod_name = 'orders-api'
  );

-- Complete init container.
SELECT complete_init_container(
    container_id,
    0
)
FROM containers
WHERE container_name = 'config-init';

-- Start application containers.
SELECT start_pod(pod_id)
FROM pods
WHERE pod_name = 'orders-api';

-- Update application and sidecar readiness.
UPDATE containers
SET ready = TRUE
WHERE pod_id = (
    SELECT pod_id FROM pods WHERE pod_name = 'orders-api'
)
AND container_name = 'api';

SELECT update_container_readiness(
    container_id,
    TRUE
)
FROM containers
WHERE container_name = 'api';

UPDATE containers
SET ready = TRUE
WHERE pod_id = (
    SELECT pod_id FROM pods WHERE pod_name = 'orders-api'
)
AND container_name = 'log-agent';

SELECT update_container_readiness(
    container_id,
    TRUE
)
FROM containers
WHERE container_name = 'log-agent';

-- Schedule the batch workload.
SELECT schedule_pod(pod_id)
FROM pods
WHERE pod_name = 'nightly-report';

-- Start batch workload.
SELECT start_pod(pod_id)
FROM pods
WHERE pod_name = 'nightly-report';

-- ------------------------------------------------------------
-- RETRIEVAL QUERIES
-- ------------------------------------------------------------

SELECT
    pod_name,
    namespace_name,
    phase,
    node_name,
    pod_ready,
    application_container_count,
    init_container_count
FROM pod_operational_report
ORDER BY pod_name;

SELECT
    pod_name,
    container_name,
    role,
    image,
    state,
    ready,
    restart_count
FROM pod_container_architecture
ORDER BY pod_name, role, container_name;

-- ------------------------------------------------------------
-- SHARED VOLUME RETRIEVAL
-- ------------------------------------------------------------

SELECT *
FROM pod_volume_sharing
ORDER BY pod_name, volume_name, container_name;

-- ------------------------------------------------------------
-- VALIDATION QUERIES
-- ------------------------------------------------------------

-- Identify Pods without a worker assignment.
SELECT
    pod_id,
    pod_name,
    phase
FROM pods
WHERE phase IN ('Running', 'Pending')
  AND node_id IS NULL;

-- Identify application containers that are not ready.
SELECT
    p.pod_name,
    c.container_name,
    c.state,
    c.ready
FROM pods p
JOIN containers c ON c.pod_id = p.pod_id
WHERE c.role <> 'Init'
  AND (
      c.state <> 'Running'
      OR c.ready = FALSE
  );

-- Identify resource allocation inconsistencies.
SELECT
    n.node_name,
    n.allocated_cpu_millicores,
    COALESCE(SUM(
        CASE
            WHEN ra.released_at IS NULL
            THEN ra.cpu_millicores
            ELSE 0
        END
    ), 0) AS calculated_cpu
FROM worker_nodes n
LEFT JOIN resource_allocations ra ON ra.node_id = n.node_id
GROUP BY
    n.node_id,
    n.node_name,
    n.allocated_cpu_millicores
HAVING n.allocated_cpu_millicores <> COALESCE(SUM(
    CASE
        WHEN ra.released_at IS NULL
        THEN ra.cpu_millicores
        ELSE 0
    END
), 0);

-- ------------------------------------------------------------
-- AGGREGATION AND RESOURCE UTILIZATION
-- ------------------------------------------------------------

SELECT
    n.node_name,
    n.cpu_capacity_millicores,
    n.allocated_cpu_millicores,
    ROUND(
        100.0 * n.allocated_cpu_millicores
        / n.cpu_capacity_millicores,
        2
    ) AS cpu_utilization_percent,
    n.memory_capacity_mib,
    n.allocated_memory_mib,
    ROUND(
        100.0 * n.allocated_memory_mib
        / n.memory_capacity_mib,
        2
    ) AS memory_utilization_percent
FROM worker_nodes n
ORDER BY n.node_name;

-- ------------------------------------------------------------
-- RESTART ANALYSIS
-- ------------------------------------------------------------

SELECT
    p.pod_name,
    c.container_name,
    c.restart_count,
    c.last_exit_code,
    c.state
FROM pods p
JOIN containers c ON c.pod_id = p.pod_id
WHERE c.restart_count > 0
ORDER BY c.restart_count DESC;

-- ------------------------------------------------------------
-- EVENT REPORTING
-- ------------------------------------------------------------

SELECT
    p.pod_name,
    e.event_type,
    e.reason,
    e.message,
    e.last_timestamp
FROM pod_events e
LEFT JOIN pods p ON p.pod_id = e.pod_id
ORDER BY e.last_timestamp DESC;

-- ------------------------------------------------------------
-- ELIGIBILITY AND STARTUP VALIDATION
-- ------------------------------------------------------------

SELECT
    p.pod_name,
    p.phase,
    p.node_id IS NOT NULL AS scheduled,
    COUNT(c.container_id) FILTER (
        WHERE c.role = 'Init'
          AND c.state = 'Terminated'
          AND c.last_exit_code = 0
    ) AS completed_init_containers,
    COUNT(c.container_id) FILTER (
        WHERE c.role = 'Init'
    ) AS required_init_containers,
    (
        p.phase = 'Pending'
        AND p.node_id IS NOT NULL
        AND COUNT(c.container_id) FILTER (
            WHERE c.role = 'Init'
              AND c.state = 'Terminated'
              AND c.last_exit_code = 0
        ) = COUNT(c.container_id) FILTER (
            WHERE c.role = 'Init'
        )
    ) AS eligible_to_start
FROM pods p
LEFT JOIN containers c ON c.pod_id = p.pod_id
GROUP BY p.pod_id;

-- ------------------------------------------------------------
-- CTE: NODE CAPACITY AND POD PLACEMENT
-- ------------------------------------------------------------

WITH node_capacity AS (
    SELECT
        node_id,
        node_name,
        cpu_capacity_millicores,
        allocated_cpu_millicores,
        memory_capacity_mib,
        allocated_memory_mib,
        cpu_capacity_millicores - allocated_cpu_millicores
            AS free_cpu,
        memory_capacity_mib - allocated_memory_mib
            AS free_memory
    FROM worker_nodes
    WHERE schedulable = TRUE
)
SELECT
    node_name,
    free_cpu,
    free_memory,
    CASE
        WHEN free_cpu >= 500 AND free_memory >= 1024
            THEN 'High Capacity'
        WHEN free_cpu >= 100 AND free_memory >= 256
            THEN 'Moderate Capacity'
        ELSE 'Low Capacity'
    END AS capacity_category
FROM node_capacity
ORDER BY free_cpu DESC;

-- ------------------------------------------------------------
-- EXPLICIT TRANSACTIONAL POD TERMINATION
-- ------------------------------------------------------------

BEGIN;

SELECT terminate_pod(pod_id)
FROM pods
WHERE pod_name = 'nightly-report';

COMMIT;

-- ------------------------------------------------------------
-- FINAL OPERATIONAL REPORT
-- ------------------------------------------------------------

SELECT
    p.pod_name,
    p.phase,
    ns.namespace_name,
    p.restart_policy,
    wn.node_name,
    p.created_at,
    p.started_at,
    p.deletion_timestamp
FROM pods p
JOIN namespaces ns ON ns.namespace_id = p.namespace_id
LEFT JOIN worker_nodes wn ON wn.node_id = p.node_id
ORDER BY p.created_at DESC;

-- ------------------------------------------------------------
-- IMPORTANT OPERATIONAL NOTES
-- ------------------------------------------------------------

-- This relational model simulates Kubernetes control-plane operations.
-- It does not replace the Kubernetes API server, scheduler, kubelet,
-- container runtime, or distributed consensus mechanisms.
--
-- Production implementation considerations:
-- 1. Run workflow operations with restricted database roles.
-- 2. Use transactions and row locks for resource accounting.
-- 3. Apply admission policies before accepting Pod specifications.
-- 4. Never store plaintext credentials in environment JSON.
-- 5. Use external secret management for sensitive configuration.
-- 6. Model actual Kubernetes resource quantities and QoS rules
--    when implementing a production scheduler.
-- 7. Use separate control-plane and observability permissions.
