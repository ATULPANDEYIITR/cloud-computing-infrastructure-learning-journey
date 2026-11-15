/*
 * CONTAINERIZATION AND RUNTIME MANAGEMENT
 * PostgreSQL 15+
 *
 * Models:
 * - Container registries
 * - Image repositories and immutable image versions
 * - Image layers
 * - Container hosts
 * - Host resource capacity
 * - Runtime instances
 * - Environment configuration
 * - Isolation namespaces
 * - Container lifecycle events
 * - Resource measurements
 * - Health checks
 * - Restart policies
 * - Deployment eligibility
 *
 * The database represents the control plane.
 * It does not execute containers or enforce Linux namespaces.
 */

BEGIN;

CREATE SCHEMA IF NOT EXISTS container_platform;

SET search_path TO container_platform, public;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE container_state AS ENUM (
    'created',
    'running',
    'paused',
    'stopped',
    'failed',
    'removed'
);

CREATE TYPE restart_policy AS ENUM (
    'never',
    'on-failure',
    'always'
);

CREATE TYPE isolation_type AS ENUM (
    'pid',
    'network',
    'mount',
    'user',
    'ipc',
    'uts',
    'cgroup'
);

CREATE TYPE health_status AS ENUM (
    'unknown',
    'healthy',
    'unhealthy'
);

CREATE TYPE deployment_status AS ENUM (
    'pending',
    'accepted',
    'rejected',
    'completed',
    'failed'
);

-- Registry ownership and endpoint configuration.

CREATE TABLE registries (
    registry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    registry_name VARCHAR(120) NOT NULL UNIQUE,
    endpoint TEXT NOT NULL,
    is_trusted BOOLEAN NOT NULL DEFAULT FALSE,
    requires_authentication BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT registry_name_valid
        CHECK (registry_name ~ '^[a-zA-Z0-9][a-zA-Z0-9._-]{0,119}$'),

    CONSTRAINT endpoint_not_empty
        CHECK (LENGTH(TRIM(endpoint)) > 0)
);

CREATE TABLE image_repositories (
    repository_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    registry_id UUID NOT NULL
        REFERENCES registries(registry_id),

    repository_name VARCHAR(200) NOT NULL,

    owner_name VARCHAR(120) NOT NULL,

    visibility VARCHAR(20) NOT NULL DEFAULT 'private'
        CHECK (visibility IN ('private', 'public', 'internal')),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (registry_id, repository_name)
);

-- Image versions are identified by cryptographic digests.
-- A mutable tag is a human-readable reference, not an immutable identity.

CREATE TABLE images (
    image_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    repository_id UUID NOT NULL
        REFERENCES image_repositories(repository_id),

    image_tag VARCHAR(128) NOT NULL,

    digest VARCHAR(64) NOT NULL UNIQUE,

    architecture VARCHAR(30) NOT NULL,

    operating_system VARCHAR(30) NOT NULL DEFAULT 'linux',

    entrypoint TEXT NOT NULL,

    image_size_mb INTEGER NOT NULL,

    is_signed BOOLEAN NOT NULL DEFAULT FALSE,

    scan_status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (
            scan_status IN (
                'pending',
                'passed',
                'failed',
                'not-scanned'
            )
        ),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (repository_id, image_tag),

    CONSTRAINT image_digest_valid
        CHECK (digest ~ '^[a-f0-9]{64}$'),

    CONSTRAINT image_size_valid
        CHECK (image_size_mb > 0),

    CONSTRAINT entrypoint_valid
        CHECK (LENGTH(TRIM(entrypoint)) > 0)
);

CREATE TABLE image_layers (
    layer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    image_id UUID NOT NULL
        REFERENCES images(image_id)
        ON DELETE CASCADE,

    layer_order INTEGER NOT NULL,

    layer_digest VARCHAR(64) NOT NULL,

    compressed_size_mb INTEGER NOT NULL,

    layer_description TEXT,

    UNIQUE (image_id, layer_order),

    CONSTRAINT layer_order_valid
        CHECK (layer_order >= 0),

    CONSTRAINT layer_size_valid
        CHECK (compressed_size_mb > 0),

    CONSTRAINT layer_digest_valid
        CHECK (layer_digest ~ '^[a-f0-9]{64}$')
);

-- Hosts provide the capacity against which deployment requests
-- are admitted.

CREATE TABLE container_hosts (
    host_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    hostname VARCHAR(120) NOT NULL UNIQUE,

    operating_system VARCHAR(40) NOT NULL,

    architecture VARCHAR(30) NOT NULL,

    runtime_name VARCHAR(80) NOT NULL,

    runtime_version VARCHAR(40) NOT NULL,

    total_cpu_cores NUMERIC(8,2) NOT NULL,

    total_memory_mb BIGINT NOT NULL,

    total_disk_mb BIGINT NOT NULL,

    reserved_cpu_cores NUMERIC(8,2) NOT NULL DEFAULT 0,

    reserved_memory_mb BIGINT NOT NULL DEFAULT 0,

    reserved_disk_mb BIGINT NOT NULL DEFAULT 0,

    is_available BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT host_cpu_valid
        CHECK (
            total_cpu_cores > 0
            AND reserved_cpu_cores >= 0
            AND reserved_cpu_cores <= total_cpu_cores
        ),

    CONSTRAINT host_memory_valid
        CHECK (
            total_memory_mb > 0
            AND reserved_memory_mb >= 0
            AND reserved_memory_mb <= total_memory_mb
        ),

    CONSTRAINT host_disk_valid
        CHECK (
            total_disk_mb > 0
            AND reserved_disk_mb >= 0
            AND reserved_disk_mb <= total_disk_mb
        )
);

-- Deployment requests preserve the requested configuration separately
-- from the actual runtime instance.

CREATE TABLE deployment_requests (
    deployment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    image_id UUID NOT NULL
        REFERENCES images(image_id),

    requested_host_id UUID
        REFERENCES container_hosts(host_id),

    container_name VARCHAR(63) NOT NULL,

    requested_cpu_cores NUMERIC(8,2) NOT NULL,

    requested_memory_mb BIGINT NOT NULL,

    requested_disk_mb BIGINT NOT NULL,

    requested_process_limit INTEGER NOT NULL DEFAULT 64,

    restart_policy restart_policy NOT NULL DEFAULT 'never',

    status deployment_status NOT NULL DEFAULT 'pending',

    requested_by VARCHAR(120) NOT NULL,

    rejection_reason TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    processed_at TIMESTAMPTZ,

    CONSTRAINT deployment_name_valid
        CHECK (
            container_name ~ '^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$'
        ),

    CONSTRAINT requested_resources_valid
        CHECK (
            requested_cpu_cores > 0
            AND requested_memory_mb >= 16
            AND requested_disk_mb >= 16
            AND requested_process_limit > 0
        )
);

-- Runtime instances represent containers actually assigned to hosts.

CREATE TABLE containers (
    container_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    deployment_id UUID NOT NULL UNIQUE
        REFERENCES deployment_requests(deployment_id),

    image_id UUID NOT NULL
        REFERENCES images(image_id),

    host_id UUID NOT NULL
        REFERENCES container_hosts(host_id),

    container_name VARCHAR(63) NOT NULL,

    state container_state NOT NULL DEFAULT 'created',

    health health_status NOT NULL DEFAULT 'unknown',

    restart_policy restart_policy NOT NULL DEFAULT 'never',

    restart_count INTEGER NOT NULL DEFAULT 0,

    exit_code INTEGER,

    cpu_limit_cores NUMERIC(8,2) NOT NULL,

    memory_limit_mb BIGINT NOT NULL,

    disk_limit_mb BIGINT NOT NULL,

    process_limit INTEGER NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    started_at TIMESTAMPTZ,

    stopped_at TIMESTAMPTZ,

    UNIQUE (host_id, container_name),

    CONSTRAINT restart_count_valid
        CHECK (restart_count >= 0),

    CONSTRAINT container_resource_valid
        CHECK (
            cpu_limit_cores > 0
            AND memory_limit_mb >= 16
            AND disk_limit_mb >= 16
            AND process_limit > 0
        )
);

CREATE TABLE container_environment (
    environment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    container_id UUID NOT NULL
        REFERENCES containers(container_id)
        ON DELETE CASCADE,

    variable_name VARCHAR(64) NOT NULL,

    variable_value TEXT NOT NULL,

    UNIQUE (container_id, variable_name),

    CONSTRAINT environment_name_valid
        CHECK (
            variable_name ~ '^[A-Z_][A-Z0-9_]{0,63}$'
        ),

    CONSTRAINT environment_value_valid
        CHECK (LENGTH(variable_value) <= 4096)
);

CREATE TABLE container_isolation (
    container_id UUID NOT NULL
        REFERENCES containers(container_id)
        ON DELETE CASCADE,

    isolation isolation_type NOT NULL,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    PRIMARY KEY (container_id, isolation)
);

CREATE TABLE container_ports (
    port_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    container_id UUID NOT NULL
        REFERENCES containers(container_id)
        ON DELETE CASCADE,

    host_port INTEGER NOT NULL,

    container_port INTEGER NOT NULL,

    protocol VARCHAR(10) NOT NULL DEFAULT 'tcp'
        CHECK (protocol IN ('tcp', 'udp')),

    UNIQUE (host_port, protocol),

    CONSTRAINT host_port_valid
        CHECK (host_port BETWEEN 1 AND 65535),

    CONSTRAINT container_port_valid
        CHECK (container_port BETWEEN 1 AND 65535)
);

CREATE TABLE container_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    container_id UUID NOT NULL
        REFERENCES containers(container_id),

    previous_state container_state,

    new_state container_state NOT NULL,

    event_type VARCHAR(60) NOT NULL,

    message TEXT,

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE resource_metrics (
    metric_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    container_id UUID NOT NULL
        REFERENCES containers(container_id)
        ON DELETE CASCADE,

    cpu_used_cores NUMERIC(8,2) NOT NULL,

    memory_used_mb BIGINT NOT NULL,

    disk_used_mb BIGINT NOT NULL,

    process_count INTEGER NOT NULL,

    measured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT metrics_nonnegative
        CHECK (
            cpu_used_cores >= 0
            AND memory_used_mb >= 0
            AND disk_used_mb >= 0
            AND process_count >= 0
        )
);

CREATE TABLE health_checks (
    health_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    container_id UUID NOT NULL
        REFERENCES containers(container_id)
        ON DELETE CASCADE,

    status health_status NOT NULL,

    check_type VARCHAR(40) NOT NULL,

    response_time_ms INTEGER,

    details TEXT,

    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT health_response_valid
        CHECK (response_time_ms IS NULL OR response_time_ms >= 0)
);

-- Indexes support common control-plane queries.

CREATE INDEX idx_images_repository
    ON images(repository_id, created_at DESC);

CREATE INDEX idx_images_scan_status
    ON images(scan_status, is_signed);

CREATE INDEX idx_containers_host_state
    ON containers(host_id, state);

CREATE INDEX idx_containers_image
    ON containers(image_id);

CREATE INDEX idx_deployments_status
    ON deployment_requests(status, created_at);

CREATE INDEX idx_events_container_time
    ON container_events(container_id, occurred_at DESC);

CREATE INDEX idx_metrics_container_time
    ON resource_metrics(container_id, measured_at DESC);

CREATE INDEX idx_health_container_time
    ON health_checks(container_id, checked_at DESC);

-- Prevent an unsafe image from being deployed through this control plane.

CREATE FUNCTION validate_deployment_image()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    image_scan_status TEXT;
    image_signature BOOLEAN;
BEGIN
    SELECT scan_status, is_signed
    INTO image_scan_status, image_signature
    FROM images
    WHERE image_id = NEW.image_id
    FOR SHARE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Image does not exist';
    END IF;

    IF image_scan_status <> 'passed' THEN
        RAISE EXCEPTION 'Image has not passed security scanning';
    END IF;

    IF image_signature IS NOT TRUE THEN
        RAISE EXCEPTION 'Unsigned images are not eligible for deployment';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_deployment_image
BEFORE INSERT ON deployment_requests
FOR EACH ROW
EXECUTE FUNCTION validate_deployment_image();

-- Validate resource measurements against container configuration.

CREATE FUNCTION validate_resource_metrics()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    limits RECORD;
BEGIN
    SELECT cpu_limit_cores,
           memory_limit_mb,
           disk_limit_mb,
           process_limit
    INTO limits
    FROM containers
    WHERE container_id = NEW.container_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Container not found';
    END IF;

    IF NEW.cpu_used_cores > limits.cpu_limit_cores THEN
        RAISE EXCEPTION 'CPU resource limit exceeded';
    END IF;

    IF NEW.memory_used_mb > limits.memory_limit_mb THEN
        RAISE EXCEPTION 'Memory resource limit exceeded';
    END IF;

    IF NEW.disk_used_mb > limits.disk_limit_mb THEN
        RAISE EXCEPTION 'Disk resource limit exceeded';
    END IF;

    IF NEW.process_count > limits.process_limit THEN
        RAISE EXCEPTION 'Process limit exceeded';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_resource_metrics
BEFORE INSERT ON resource_metrics
FOR EACH ROW
EXECUTE FUNCTION validate_resource_metrics();

-- Preserve lifecycle transitions in an auditable event table.

CREATE FUNCTION record_container_state_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.state IS DISTINCT FROM NEW.state THEN
        INSERT INTO container_events (
            container_id,
            previous_state,
            new_state,
            event_type,
            message
        )
        VALUES (
            NEW.container_id,
            OLD.state,
            NEW.state,
            'STATE_CHANGE',
            'Container lifecycle state changed'
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_container_state_audit
AFTER UPDATE OF state ON containers
FOR EACH ROW
EXECUTE FUNCTION record_container_state_change();

-- Host admission checks and reservation.
-- Row locking prevents concurrent deployments from oversubscribing
-- the same host through this procedure.

CREATE PROCEDURE process_deployment(
    IN p_deployment_id UUID
)
LANGUAGE plpgsql
AS $$
DECLARE
    request_row RECORD;
    host_row RECORD;
    new_container_id UUID;
BEGIN
    SELECT *
    INTO request_row
    FROM deployment_requests
    WHERE deployment_id = p_deployment_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Deployment request not found';
    END IF;

    IF request_row.status <> 'pending' THEN
        RAISE EXCEPTION 'Deployment is not pending';
    END IF;

    IF request_row.requested_host_id IS NULL THEN
        RAISE EXCEPTION 'A target host is required';
    END IF;

    SELECT *
    INTO host_row
    FROM container_hosts
    WHERE host_id = request_row.requested_host_id
    FOR UPDATE;

    IF NOT FOUND OR host_row.is_available IS NOT TRUE THEN
        UPDATE deployment_requests
        SET status = 'rejected',
            rejection_reason = 'Host unavailable',
            processed_at = NOW()
        WHERE deployment_id = p_deployment_id;

        RETURN;
    END IF;

    IF host_row.operating_system <> 'linux' THEN
        UPDATE deployment_requests
        SET status = 'rejected',
            rejection_reason = 'Unsupported operating system',
            processed_at = NOW()
        WHERE deployment_id = p_deployment_id;

        RETURN;
    END IF;

    IF (
        SELECT architecture
        FROM images
        WHERE image_id = request_row.image_id
    ) <> host_row.architecture THEN

        UPDATE deployment_requests
        SET status = 'rejected',
            rejection_reason = 'Image architecture mismatch',
            processed_at = NOW()
        WHERE deployment_id = p_deployment_id;

        RETURN;
    END IF;

    IF host_row.reserved_cpu_cores +
       request_row.requested_cpu_cores >
       host_row.total_cpu_cores THEN

        UPDATE deployment_requests
        SET status = 'rejected',
            rejection_reason = 'Insufficient CPU capacity',
            processed_at = NOW()
        WHERE deployment_id = p_deployment_id;

        RETURN;
    END IF;

    IF host_row.reserved_memory_mb +
       request_row.requested_memory_mb >
       host_row.total_memory_mb THEN

        UPDATE deployment_requests
        SET status = 'rejected',
            rejection_reason = 'Insufficient memory capacity',
            processed_at = NOW()
        WHERE deployment_id = p_deployment_id;

        RETURN;
    END IF;

    IF host_row.reserved_disk_mb +
       request_row.requested_disk_mb >
       host_row.total_disk_mb THEN

        UPDATE deployment_requests
        SET status = 'rejected',
            rejection_reason = 'Insufficient disk capacity',
            processed_at = NOW()
        WHERE deployment_id = p_deployment_id;

        RETURN;
    END IF;

    UPDATE container_hosts
    SET reserved_cpu_cores =
            reserved_cpu_cores + request_row.requested_cpu_cores,
        reserved_memory_mb =
            reserved_memory_mb + request_row.requested_memory_mb,
        reserved_disk_mb =
            reserved_disk_mb + request_row.requested_disk_mb
    WHERE host_id = host_row.host_id;

    INSERT INTO containers (
        deployment_id,
        image_id,
        host_id,
        container_name,
        restart_policy,
        cpu_limit_cores,
        memory_limit_mb,
        disk_limit_mb,
        process_limit
    )
    VALUES (
        p_deployment_id,
        request_row.image_id,
        host_row.host_id,
        request_row.container_name,
        request_row.restart_policy,
        request_row.requested_cpu_cores,
        request_row.requested_memory_mb,
        request_row.requested_disk_mb,
        request_row.requested_process_limit
    )
    RETURNING container_id INTO new_container_id;

    INSERT INTO container_isolation (
        container_id,
        isolation
    )
    SELECT new_container_id, isolation
    FROM unnest(enum_range(NULL::isolation_type)) AS isolation;

    UPDATE deployment_requests
    SET status = 'accepted',
        processed_at = NOW()
    WHERE deployment_id = p_deployment_id;

EXCEPTION
    WHEN OTHERS THEN
        RAISE;
END;
$$;

-- Release reservations when a container is removed.

CREATE FUNCTION release_container_resources()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = 'removed' AND OLD.state <> 'removed' THEN

        UPDATE container_hosts
        SET reserved_cpu_cores =
                reserved_cpu_cores - OLD.cpu_limit_cores,
            reserved_memory_mb =
                reserved_memory_mb - OLD.memory_limit_mb,
            reserved_disk_mb =
                reserved_disk_mb - OLD.disk_limit_mb
        WHERE host_id = OLD.host_id;

    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_release_container_resources
AFTER UPDATE OF state ON containers
FOR EACH ROW
EXECUTE FUNCTION release_container_resources();

-- Runtime state transition procedure.

CREATE PROCEDURE transition_container(
    IN p_container_id UUID,
    IN p_new_state container_state,
    IN p_exit_code INTEGER DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    current_state container_state;
BEGIN
    SELECT state
    INTO current_state
    FROM containers
    WHERE container_id = p_container_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Container not found';
    END IF;

    IF current_state = 'created'
       AND p_new_state IN ('running', 'removed') THEN
        NULL;

    ELSIF current_state = 'running'
       AND p_new_state IN ('paused', 'stopped', 'failed') THEN
        NULL;

    ELSIF current_state = 'paused'
       AND p_new_state IN ('running', 'stopped', 'failed') THEN
        NULL;

    ELSIF current_state = 'stopped'
       AND p_new_state IN ('running', 'removed') THEN
        NULL;

    ELSIF current_state = 'failed'
       AND p_new_state IN ('running', 'stopped', 'removed') THEN
        NULL;

    ELSE
        RAISE EXCEPTION
            'Invalid transition from % to %',
            current_state,
            p_new_state;
    END IF;

    UPDATE containers
    SET state = p_new_state,
        exit_code = COALESCE(p_exit_code, exit_code),
        started_at = CASE
            WHEN p_new_state = 'running' THEN NOW()
            ELSE started_at
        END,
        stopped_at = CASE
            WHEN p_new_state IN ('stopped', 'failed', 'removed')
            THEN NOW()
            ELSE stopped_at
        END,
        health = CASE
            WHEN p_new_state = 'running' THEN 'unknown'
            WHEN p_new_state IN ('failed', 'removed') THEN 'unhealthy'
            ELSE health
        END
    WHERE container_id = p_container_id;
END;
$$;

-- Read model for runtime monitoring.

CREATE VIEW v_container_inventory AS
SELECT
    c.container_id,
    c.container_name,
    i.image_tag,
    i.digest,
    h.hostname,
    h.runtime_name,
    c.state,
    c.health,
    c.restart_policy,
    c.restart_count,
    c.cpu_limit_cores,
    c.memory_limit_mb,
    c.disk_limit_mb,
    c.created_at,
    c.started_at
FROM containers c
JOIN images i ON i.image_id = c.image_id
JOIN container_hosts h ON h.host_id = c.host_id;

CREATE VIEW v_host_capacity AS
SELECT
    host_id,
    hostname,
    total_cpu_cores,
    reserved_cpu_cores,
    total_cpu_cores - reserved_cpu_cores AS available_cpu_cores,
    total_memory_mb,
    reserved_memory_mb,
    total_memory_mb - reserved_memory_mb AS available_memory_mb,
    total_disk_mb,
    reserved_disk_mb,
    total_disk_mb - reserved_disk_mb AS available_disk_mb,
    is_available
FROM container_hosts;

CREATE VIEW v_container_latest_metrics AS
SELECT DISTINCT ON (container_id)
    container_id,
    cpu_used_cores,
    memory_used_mb,
    disk_used_mb,
    process_count,
    measured_at
FROM resource_metrics
ORDER BY container_id, measured_at DESC;

-- Evaluation function for host deployment capacity.

CREATE FUNCTION deployment_eligible(
    p_deployment_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    request_row RECORD;
    host_row RECORD;
BEGIN
    SELECT *
    INTO request_row
    FROM deployment_requests
    WHERE deployment_id = p_deployment_id;

    IF NOT FOUND OR request_row.status <> 'pending' THEN
        RETURN FALSE;
    END IF;

    SELECT *
    INTO host_row
    FROM container_hosts
    WHERE host_id = request_row.requested_host_id;

    IF NOT FOUND OR NOT host_row.is_available THEN
        RETURN FALSE;
    END IF;

    RETURN
        host_row.reserved_cpu_cores +
            request_row.requested_cpu_cores <= host_row.total_cpu_cores
        AND
        host_row.reserved_memory_mb +
            request_row.requested_memory_mb <= host_row.total_memory_mb
        AND
        host_row.reserved_disk_mb +
            request_row.requested_disk_mb <= host_row.total_disk_mb;
END;
$$;

-- Sample registry, image and host.

INSERT INTO registries (
    registry_name,
    endpoint,
    is_trusted,
    requires_authentication
)
VALUES (
    'enterprise-registry',
    'https://registry.example.internal',
    TRUE,
    TRUE
);

INSERT INTO image_repositories (
    registry_id,
    repository_name,
    owner_name,
    visibility
)
SELECT
    registry_id,
    'inventory-api',
    'operations-team',
    'private'
FROM registries
WHERE registry_name = 'enterprise-registry';

INSERT INTO images (
    repository_id,
    image_tag,
    digest,
    architecture,
    operating_system,
    entrypoint,
    image_size_mb,
    is_signed,
    scan_status
)
SELECT
    repository_id,
    '2.0.0',
    encode(digest('inventory-api-image-2.0.0', 'sha256'), 'hex'),
    'amd64',
    'linux',
    'java -jar inventory.jar',
    320,
    TRUE,
    'passed'
FROM image_repositories
WHERE repository_name = 'inventory-api';

INSERT INTO image_layers (
    image_id,
    layer_order,
    layer_digest,
    compressed_size_mb,
    layer_description
)
SELECT
    image_id,
    0,
    encode(digest('linux-base-layer', 'sha256'), 'hex'),
    90,
    'Minimal Linux base filesystem'
FROM images
WHERE image_tag = '2.0.0';

INSERT INTO image_layers (
    image_id,
    layer_order,
    layer_digest,
    compressed_size_mb,
    layer_description
)
SELECT
    image_id,
    1,
    encode(digest('java-runtime-layer', 'sha256'), 'hex'),
    120,
    'Java runtime'
FROM images
WHERE image_tag = '2.0.0';

INSERT INTO container_hosts (
    hostname,
    operating_system,
    architecture,
    runtime_name,
    runtime_version,
    total_cpu_cores,
    total_memory_mb,
    total_disk_mb
)
VALUES
(
    'worker-01',
    'linux',
    'amd64',
    'containerd',
    '2.x',
    16,
    32768,
    500000
),
(
    'worker-02',
    'linux',
    'arm64',
    'containerd',
    '2.x',
    8,
    16384,
    200000
);

-- Deployment request.

INSERT INTO deployment_requests (
    image_id,
    requested_host_id,
    container_name,
    requested_cpu_cores,
    requested_memory_mb,
    requested_disk_mb,
    requested_process_limit,
    restart_policy,
    requested_by
)
SELECT
    i.image_id,
    h.host_id,
    'inventory-api',
    2,
    1024,
    2048,
    100,
    'on-failure',
    'operations-admin'
FROM images i
CROSS JOIN container_hosts h
WHERE i.image_tag = '2.0.0'
  AND h.hostname = 'worker-01';

-- Deliberately rejected deployment:
-- the image architecture does not match the target host.

INSERT INTO deployment_requests (
    image_id,
    requested_host_id,
    container_name,
    requested_cpu_cores,
    requested_memory_mb,
    requested_disk_mb,
    requested_process_limit,
    restart_policy,
    requested_by
)
SELECT
    i.image_id,
    h.host_id,
    'inventory-arm-mismatch',
    1,
    512,
    1024,
    50,
    'never',
    'operations-admin'
FROM images i
CROSS JOIN container_hosts h
WHERE i.image_tag = '2.0.0'
  AND h.hostname = 'worker-02';

-- Process valid and invalid requests independently.
-- A rejected request does not abort other deployments.

DO $$
DECLARE
    deployment RECORD;
BEGIN
    FOR deployment IN
        SELECT deployment_id
        FROM deployment_requests
        WHERE status = 'pending'
        ORDER BY created_at
    LOOP
        CALL process_deployment(deployment.deployment_id);
    END LOOP;
END;
$$;

-- Configure environment variables for accepted containers.

INSERT INTO container_environment (
    container_id,
    variable_name,
    variable_value
)
SELECT
    container_id,
    'APP_ENV',
    'production'
FROM containers;

INSERT INTO container_environment (
    container_id,
    variable_name,
    variable_value
)
SELECT
    container_id,
    'LOG_LEVEL',
    'INFO'
FROM containers;

-- Start accepted containers.

DO $$
DECLARE
    runtime_container RECORD;
BEGIN
    FOR runtime_container IN
        SELECT container_id
        FROM containers
        WHERE state = 'created'
    LOOP
        CALL transition_container(
            runtime_container.container_id,
            'running'
        );
    END LOOP;
END;
$$;

-- Record resource measurements for a running instance.

INSERT INTO resource_metrics (
    container_id,
    cpu_used_cores,
    memory_used_mb,
    disk_used_mb,
    process_count
)
SELECT
    container_id,
    0.75,
    320,
    500,
    12
FROM containers
WHERE container_name = 'inventory-api';

INSERT INTO health_checks (
    container_id,
    status,
    check_type,
    response_time_ms,
    details
)
SELECT
    container_id,
    'healthy',
    'http',
    35,
    'Application health endpoint returned success'
FROM containers
WHERE container_name = 'inventory-api';

UPDATE containers
SET health = 'healthy'
WHERE container_name = 'inventory-api';

-- Retrieval: active container inventory.

SELECT *
FROM v_container_inventory
ORDER BY hostname, container_name;

-- Retrieval: host capacity.

SELECT *
FROM v_host_capacity
ORDER BY hostname;

-- Aggregation: running containers by host.

SELECT
    h.hostname,
    COUNT(c.container_id) AS total_containers,
    COUNT(*) FILTER (
        WHERE c.state = 'running'
    ) AS running_containers,
    COUNT(*) FILTER (
        WHERE c.health = 'unhealthy'
    ) AS unhealthy_containers
FROM container_hosts h
LEFT JOIN containers c ON c.host_id = h.host_id
GROUP BY h.host_id, h.hostname
ORDER BY h.hostname;

-- Latest resource utilization.

SELECT
    c.container_name,
    m.cpu_used_cores,
    c.cpu_limit_cores,
    ROUND(
        100 * m.cpu_used_cores / NULLIF(c.cpu_limit_cores, 0),
        2
    ) AS cpu_utilization_percent,
    m.memory_used_mb,
    c.memory_limit_mb,
    ROUND(
        100.0 * m.memory_used_mb / NULLIF(c.memory_limit_mb, 0),
        2
    ) AS memory_utilization_percent
FROM v_container_latest_metrics m
JOIN containers c ON c.container_id = m.container_id;

-- CTE: identify containers approaching memory limits.

WITH latest_metrics AS (
    SELECT DISTINCT ON (container_id)
        container_id,
        memory_used_mb
    FROM resource_metrics
    ORDER BY container_id, measured_at DESC
)
SELECT
    c.container_name,
    m.memory_used_mb,
    c.memory_limit_mb,
    ROUND(
        100.0 * m.memory_used_mb / c.memory_limit_mb,
        2
    ) AS memory_percentage
FROM latest_metrics m
JOIN containers c ON c.container_id = m.container_id
WHERE m.memory_used_mb >= c.memory_limit_mb * 0.80
ORDER BY memory_percentage DESC;

-- Evaluation: deployment eligibility.

SELECT
    deployment_id,
    container_name,
    deployment_eligible(deployment_id) AS eligible,
    status,
    rejection_reason
FROM deployment_requests
ORDER BY created_at;

-- Evaluation: image security posture.

SELECT
    r.repository_name,
    i.image_tag,
    i.digest,
    i.is_signed,
    i.scan_status,
    CASE
        WHEN i.is_signed AND i.scan_status = 'passed'
        THEN 'ELIGIBLE'
        ELSE 'BLOCKED'
    END AS security_decision
FROM images i
JOIN image_repositories r
    ON r.repository_id = i.repository_id;

-- Workflow report: lifecycle event history.

SELECT
    c.container_name,
    e.previous_state,
    e.new_state,
    e.event_type,
    e.occurred_at
FROM container_events e
JOIN containers c ON c.container_id = e.container_id
ORDER BY e.occurred_at;

-- Restart behavior.
-- A failed container with an on-failure policy can be restarted.

DO $$
DECLARE
    target_id UUID;
BEGIN
    SELECT container_id
    INTO target_id
    FROM containers
    WHERE container_name = 'inventory-api';

    IF target_id IS NOT NULL THEN
        UPDATE containers
        SET state = 'failed',
            health = 'unhealthy',
            exit_code = 137
        WHERE container_id = target_id
          AND state = 'running';

        UPDATE containers
        SET restart_count = restart_count + 1,
            state = 'running',
            health = 'unknown',
            started_at = NOW(),
            exit_code = NULL
        WHERE container_id = target_id
          AND state = 'failed'
          AND restart_policy IN ('on-failure', 'always')
          AND restart_count < 3;
    END IF;
END;
$$;

-- Demonstrate transaction-safe removal and capacity release.

DO $$
DECLARE
    target_id UUID;
BEGIN
    SELECT container_id
    INTO target_id
    FROM containers
    WHERE container_name = 'inventory-api';

    IF target_id IS NOT NULL THEN
        CALL transition_container(target_id, 'stopped');
        CALL transition_container(target_id, 'removed');
    END IF;
END;
$$;

-- Verify that host resource reservations were released.

SELECT *
FROM v_host_capacity
ORDER BY hostname;

-- Final deployment and runtime report.

SELECT
    d.container_name,
    d.status,
    d.rejection_reason,
    c.state,
    c.health,
    c.restart_count,
    h.hostname
FROM deployment_requests d
LEFT JOIN containers c
    ON c.deployment_id = d.deployment_id
LEFT JOIN container_hosts h
    ON h.host_id = d.requested_host_id
ORDER BY d.created_at;

COMMIT;
