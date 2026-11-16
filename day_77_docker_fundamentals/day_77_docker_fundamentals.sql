-- ============================================================
-- DOCKER FUNDAMENTALS
-- Docker architecture, daemon, client, images, containers
-- and registries.
--
-- PostgreSQL 15+
--
-- The schema represents a simplified container platform
-- inventory and operational control system.
--
-- It is a management and simulation database, not a replacement
-- for the actual Docker Engine API or container runtime.
-- ============================================================

BEGIN;

DROP SCHEMA IF EXISTS docker_lab CASCADE;

CREATE SCHEMA docker_lab;

SET search_path TO docker_lab, public;

-- ============================================================
-- 1. ENUM TYPES
-- ============================================================

CREATE TYPE daemon_status AS ENUM (
    'available',
    'unavailable',
    'maintenance'
);

CREATE TYPE image_status AS ENUM (
    'building',
    'available',
    'failed',
    'deleted'
);

CREATE TYPE container_status AS ENUM (
    'created',
    'running',
    'stopped',
    'paused',
    'exited',
    'removed'
);

CREATE TYPE registry_type AS ENUM (
    'public',
    'private',
    'internal'
);

CREATE TYPE operation_status AS ENUM (
    'pending',
    'running',
    'succeeded',
    'failed'
);

CREATE TYPE event_type AS ENUM (
    'image_build',
    'image_tag',
    'image_push',
    'image_pull',
    'container_create',
    'container_start',
    'container_stop',
    'container_remove',
    'daemon_failure'
);

-- ============================================================
-- 2. HOSTS AND DOCKER DAEMONS
-- ============================================================

CREATE TABLE docker_hosts (
    host_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    hostname VARCHAR(120) NOT NULL UNIQUE,

    operating_system VARCHAR(100) NOT NULL,

    architecture VARCHAR(30) NOT NULL
        CHECK (
            architecture IN (
                'amd64',
                'arm64',
                'arm/v7',
                'other'
            )
        ),

    total_memory_mb INTEGER NOT NULL
        CHECK (total_memory_mb > 0),

    total_cpu NUMERIC(8,2) NOT NULL
        CHECK (total_cpu > 0),

    storage_capacity_mb BIGINT NOT NULL
        CHECK (storage_capacity_mb > 0),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE docker_daemons (
    daemon_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    host_id BIGINT NOT NULL UNIQUE
        REFERENCES docker_hosts(host_id),

    daemon_version VARCHAR(30) NOT NULL,

    api_version VARCHAR(30) NOT NULL,

    status daemon_status NOT NULL DEFAULT 'available',

    started_at TIMESTAMPTZ,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 3. REGISTRIES
-- ============================================================

CREATE TABLE registries (
    registry_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    registry_name VARCHAR(150) NOT NULL UNIQUE,

    registry_url TEXT NOT NULL UNIQUE,

    registry_category registry_type NOT NULL,

    requires_authentication BOOLEAN NOT NULL DEFAULT TRUE,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (registry_url ~ '^https?://')
);


CREATE TABLE registry_accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    registry_id BIGINT NOT NULL
        REFERENCES registries(registry_id),

    username VARCHAR(100) NOT NULL,

    credential_reference TEXT NOT NULL,

    can_pull BOOLEAN NOT NULL DEFAULT TRUE,

    can_push BOOLEAN NOT NULL DEFAULT FALSE,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (registry_id, username)
);

-- credential_reference stores a secret-manager reference,
-- never a plaintext registry password or access token.

-- ============================================================
-- 4. IMAGE REPOSITORIES AND IMAGES
-- ============================================================

CREATE TABLE image_repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    registry_id BIGINT
        REFERENCES registries(registry_id),

    repository_name VARCHAR(200) NOT NULL,

    owner_team VARCHAR(100) NOT NULL,

    is_private BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (registry_id, repository_name)
);


CREATE TABLE images (
    image_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES image_repositories(repository_id),

    image_digest VARCHAR(80) NOT NULL UNIQUE,

    image_tag VARCHAR(100) NOT NULL,

    architecture VARCHAR(30) NOT NULL,

    operating_system VARCHAR(30) NOT NULL DEFAULT 'linux',

    size_mb NUMERIC(14,2) NOT NULL
        CHECK (size_mb >= 0),

    image_state image_status NOT NULL DEFAULT 'building',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    created_by VARCHAR(100) NOT NULL,

    UNIQUE (repository_id, image_tag),

    CHECK (image_digest ~ '^sha256:[0-9a-f]{64}$')
);


CREATE TABLE image_layers (
    layer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    image_id BIGINT NOT NULL
        REFERENCES images(image_id) ON DELETE CASCADE,

    layer_order INTEGER NOT NULL
        CHECK (layer_order >= 0),

    layer_digest VARCHAR(80) NOT NULL,

    instruction TEXT NOT NULL,

    size_mb NUMERIC(14,2) NOT NULL
        CHECK (size_mb >= 0),

    UNIQUE (image_id, layer_order),

    CHECK (layer_digest ~ '^sha256:[0-9a-f]{64}$')
);


CREATE TABLE image_tags (
    tag_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    image_id BIGINT NOT NULL
        REFERENCES images(image_id),

    tag_name VARCHAR(100) NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (image_id, tag_name)
);


CREATE TABLE image_transfers (
    transfer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    image_id BIGINT NOT NULL
        REFERENCES images(image_id),

    registry_id BIGINT NOT NULL
        REFERENCES registries(registry_id),

    transfer_direction VARCHAR(10) NOT NULL
        CHECK (
            transfer_direction IN ('pull', 'push')
        ),

    status operation_status NOT NULL DEFAULT 'pending',

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    completed_at TIMESTAMPTZ,

    error_message TEXT,

    CHECK (
        completed_at IS NULL OR completed_at >= started_at
    )
);

-- ============================================================
-- 5. CONTAINERS
-- ============================================================

CREATE TABLE containers (
    container_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    daemon_id BIGINT NOT NULL
        REFERENCES docker_daemons(daemon_id),

    image_id BIGINT NOT NULL
        REFERENCES images(image_id),

    container_name VARCHAR(120) NOT NULL,

    container_runtime_id VARCHAR(100) NOT NULL UNIQUE,

    status container_status NOT NULL DEFAULT 'created',

    memory_limit_mb INTEGER NOT NULL DEFAULT 512
        CHECK (memory_limit_mb > 0),

    cpu_limit NUMERIC(8,2) NOT NULL DEFAULT 1.0
        CHECK (cpu_limit > 0),

    restart_policy VARCHAR(30) NOT NULL DEFAULT 'no'
        CHECK (
            restart_policy IN (
                'no',
                'always',
                'unless-stopped',
                'on-failure'
            )
        ),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    started_at TIMESTAMPTZ,

    stopped_at TIMESTAMPTZ,

    UNIQUE (daemon_id, container_name)
);


CREATE TABLE container_ports (
    port_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    container_id BIGINT NOT NULL
        REFERENCES containers(container_id) ON DELETE CASCADE,

    host_port INTEGER NOT NULL
        CHECK (host_port BETWEEN 1 AND 65535),

    container_port INTEGER NOT NULL
        CHECK (container_port BETWEEN 1 AND 65535),

    protocol VARCHAR(10) NOT NULL DEFAULT 'tcp'
        CHECK (protocol IN ('tcp', 'udp')),

    UNIQUE (container_id, host_port, protocol)
);


CREATE TABLE container_environment (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    container_id BIGINT NOT NULL
        REFERENCES containers(container_id) ON DELETE CASCADE,

    variable_name VARCHAR(200) NOT NULL,

    variable_value TEXT NOT NULL,

    is_sensitive BOOLEAN NOT NULL DEFAULT FALSE,

    UNIQUE (container_id, variable_name)
);


CREATE TABLE container_logs (
    log_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    container_id BIGINT NOT NULL
        REFERENCES containers(container_id) ON DELETE CASCADE,

    log_level VARCHAR(15) NOT NULL DEFAULT 'INFO',

    log_message TEXT NOT NULL,

    logged_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================
-- 6. RESOURCE MANAGEMENT
-- ============================================================

CREATE TABLE resource_allocations (
    allocation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    container_id BIGINT NOT NULL UNIQUE
        REFERENCES containers(container_id),

    memory_mb INTEGER NOT NULL CHECK (memory_mb > 0),

    cpu_cores NUMERIC(8,2) NOT NULL CHECK (cpu_cores > 0),

    allocated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    released_at TIMESTAMPTZ
);

-- ============================================================
-- 7. DOCKER EVENT AUDIT
-- ============================================================

CREATE TABLE docker_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    daemon_id BIGINT NOT NULL
        REFERENCES docker_daemons(daemon_id),

    container_id BIGINT
        REFERENCES containers(container_id),

    image_id BIGINT
        REFERENCES images(image_id),

    event event_type NOT NULL,

    description TEXT,

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- ============================================================
-- 8. INDEXES
-- ============================================================

CREATE INDEX idx_daemons_status
    ON docker_daemons(status);

CREATE INDEX idx_images_repository
    ON images(repository_id, image_state);

CREATE INDEX idx_images_created
    ON images(created_at DESC);

CREATE INDEX idx_image_layers
    ON image_layers(image_id, layer_order);

CREATE INDEX idx_container_daemon_status
    ON containers(daemon_id, status);

CREATE INDEX idx_container_image
    ON containers(image_id);

CREATE INDEX idx_container_logs_time
    ON container_logs(container_id, logged_at DESC);

CREATE INDEX idx_events_daemon_time
    ON docker_events(daemon_id, occurred_at DESC);

CREATE INDEX idx_transfers_status
    ON image_transfers(status, started_at DESC);

CREATE INDEX idx_events_metadata
    ON docker_events USING GIN(metadata);

CREATE UNIQUE INDEX idx_active_host_port
    ON container_ports(host_port, protocol)
    WHERE EXISTS (
        SELECT 1
        FROM containers c
        WHERE c.container_id = container_ports.container_id
          AND c.status = 'running'
    );

-- The partial index above is not supported by PostgreSQL because
-- partial-index predicates cannot reference another table.
-- Active port enforcement is therefore implemented by triggers.
-- Remove the attempted index before executing the trigger design.

DROP INDEX IF EXISTS idx_active_host_port;

-- ============================================================
-- 9. CONTAINER NAME AND PORT VALIDATION
-- ============================================================

CREATE OR REPLACE FUNCTION validate_container_insert()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM docker_daemons d
        WHERE d.daemon_id = NEW.daemon_id
          AND d.status = 'available'
    ) THEN
        RAISE EXCEPTION
            'Cannot create container: daemon is unavailable';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM images i
        WHERE i.image_id = NEW.image_id
          AND i.image_state = 'available'
    ) THEN
        RAISE EXCEPTION
            'Container image is not available';
    END IF;

    RETURN NEW;
END;
$$;


CREATE TRIGGER trg_validate_container_insert
BEFORE INSERT ON containers
FOR EACH ROW
EXECUTE FUNCTION validate_container_insert();


CREATE OR REPLACE FUNCTION validate_container_port()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM container_ports cp
        JOIN containers c
            ON c.container_id = cp.container_id
        JOIN containers new_container
            ON new_container.container_id = NEW.container_id
        WHERE cp.host_port = NEW.host_port
          AND cp.protocol = NEW.protocol
          AND c.status = 'running'
          AND c.daemon_id = new_container.daemon_id
          AND cp.container_id <> NEW.container_id
    ) THEN
        RAISE EXCEPTION
            'Host port % is already allocated on this daemon',
            NEW.host_port;
    END IF;

    RETURN NEW;
END;
$$;


CREATE TRIGGER trg_validate_container_port
BEFORE INSERT OR UPDATE ON container_ports
FOR EACH ROW
EXECUTE FUNCTION validate_container_port();


-- ============================================================
-- 10. RESOURCE ALLOCATION VALIDATION
-- ============================================================

CREATE OR REPLACE FUNCTION validate_resource_allocation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_daemon BIGINT;
    v_total_memory BIGINT;
    v_total_cpu NUMERIC;
    v_memory_capacity INTEGER;
    v_cpu_capacity NUMERIC;
BEGIN
    SELECT
        c.daemon_id,
        h.total_memory_mb,
        h.total_cpu
    INTO
        v_daemon,
        v_memory_capacity,
        v_cpu_capacity
    FROM containers c
    JOIN docker_daemons d
        ON d.daemon_id = c.daemon_id
    JOIN docker_hosts h
        ON h.host_id = d.host_id
    WHERE c.container_id = NEW.container_id
    FOR UPDATE OF d;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Container or daemon not found';
    END IF;

    SELECT
        COALESCE(SUM(ra.memory_mb), 0),
        COALESCE(SUM(ra.cpu_cores), 0)
    INTO
        v_total_memory,
        v_total_cpu
    FROM resource_allocations ra
    JOIN containers c
        ON c.container_id = ra.container_id
    WHERE c.daemon_id = v_daemon
      AND (
          TG_OP = 'INSERT'
          OR ra.allocation_id <> NEW.allocation_id
      )
      AND ra.released_at IS NULL;

    IF v_total_memory + NEW.memory_mb > v_memory_capacity THEN
        RAISE EXCEPTION
            'Insufficient memory capacity on daemon %',
            v_daemon;
    END IF;

    IF v_total_cpu + NEW.cpu_cores > v_cpu_capacity THEN
        RAISE EXCEPTION
            'Insufficient CPU capacity on daemon %',
            v_daemon;
    END IF;

    RETURN NEW;
END;
$$;


CREATE TRIGGER trg_validate_resource_allocation
BEFORE INSERT OR UPDATE ON resource_allocations
FOR EACH ROW
EXECUTE FUNCTION validate_resource_allocation();


-- ============================================================
-- 11. CONTAINER LIFECYCLE FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION change_container_state(
    p_container_id BIGINT,
    p_new_status container_status
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_old_status container_status;
    v_daemon_id BIGINT;
    v_image_id BIGINT;
BEGIN
    SELECT status, daemon_id, image_id
    INTO v_old_status, v_daemon_id, v_image_id
    FROM containers
    WHERE container_id = p_container_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Container % does not exist',
            p_container_id;
    END IF;

    IF v_old_status = p_new_status THEN
        RAISE EXCEPTION 'Container already has status %',
            p_new_status;
    END IF;

    IF NOT (
        (v_old_status = 'created' AND
            p_new_status IN ('running', 'removed'))
        OR
        (v_old_status = 'running' AND
            p_new_status IN ('stopped', 'exited', 'paused'))
        OR
        (v_old_status = 'paused' AND
            p_new_status IN ('running', 'stopped'))
        OR
        (v_old_status = 'stopped' AND
            p_new_status IN ('running', 'removed'))
        OR
        (v_old_status = 'exited' AND
            p_new_status IN ('running', 'removed'))
    ) THEN
        RAISE EXCEPTION
            'Invalid lifecycle transition: % -> %',
            v_old_status,
            p_new_status;
    END IF;

    IF p_new_status = 'running' THEN

        IF NOT EXISTS (
            SELECT 1
            FROM docker_daemons
            WHERE daemon_id = v_daemon_id
              AND status = 'available'
        ) THEN
            RAISE EXCEPTION 'Docker daemon is unavailable';
        END IF;

        IF EXISTS (
            SELECT 1
            FROM container_ports cp
            JOIN containers c
                ON c.container_id = cp.container_id
            WHERE cp.container_id = p_container_id
              AND EXISTS (
                  SELECT 1
                  FROM container_ports other_port
                  JOIN containers other_container
                    ON other_container.container_id =
                       other_port.container_id
                  WHERE other_port.host_port = cp.host_port
                    AND other_port.protocol = cp.protocol
                    AND other_container.daemon_id = v_daemon_id
                    AND other_container.status = 'running'
                    AND other_container.container_id <> p_container_id
              )
        ) THEN
            RAISE EXCEPTION 'Port conflict detected';
        END IF;

    END IF;

    UPDATE containers
    SET status = p_new_status,
        started_at = CASE
            WHEN p_new_status = 'running'
                THEN NOW()
            ELSE started_at
        END,
        stopped_at = CASE
            WHEN p_new_status IN ('stopped', 'exited')
                THEN NOW()
            ELSE stopped_at
        END
    WHERE container_id = p_container_id;

    IF p_new_status = 'running' THEN
        INSERT INTO resource_allocations (
            container_id,
            memory_mb,
            cpu_cores
        )
        SELECT
            container_id,
            memory_limit_mb,
            cpu_limit
        FROM containers
        WHERE container_id = p_container_id
        ON CONFLICT (container_id)
        DO UPDATE SET
            released_at = NULL,
            memory_mb = EXCLUDED.memory_mb,
            cpu_cores = EXCLUDED.cpu_cores;

    ELSIF p_new_status IN ('stopped', 'exited', 'removed') THEN

        UPDATE resource_allocations
        SET released_at = NOW()
        WHERE container_id = p_container_id
          AND released_at IS NULL;

    END IF;

    INSERT INTO docker_events (
        daemon_id,
        container_id,
        image_id,
        event,
        description
    )
    VALUES (
        v_daemon_id,
        p_container_id,
        v_image_id,
        CASE p_new_status
            WHEN 'running' THEN 'container_start'
            WHEN 'stopped' THEN 'container_stop'
            WHEN 'removed' THEN 'container_remove'
            ELSE 'container_stop'
        END,
        'Container transitioned from ' ||
            v_old_status || ' to ' || p_new_status
    );

END;
$$;


-- ============================================================
-- 12. IMAGE REGISTRY TRANSFER PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE register_image_transfer(
    p_image_id BIGINT,
    p_registry_id BIGINT,
    p_direction VARCHAR(10)
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_transfer_id BIGINT;
BEGIN
    IF p_direction NOT IN ('push', 'pull') THEN
        RAISE EXCEPTION 'Invalid transfer direction';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM images
        WHERE image_id = p_image_id
          AND image_state = 'available'
    ) THEN
        RAISE EXCEPTION 'Image is not available';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM registries
        WHERE registry_id = p_registry_id
          AND enabled = TRUE
    ) THEN
        RAISE EXCEPTION 'Registry is unavailable';
    END IF;

    INSERT INTO image_transfers (
        image_id,
        registry_id,
        transfer_direction,
        status
    )
    VALUES (
        p_image_id,
        p_registry_id,
        p_direction,
        'running'
    )
    RETURNING transfer_id INTO v_transfer_id;

    UPDATE image_transfers
    SET status = 'succeeded',
        completed_at = NOW()
    WHERE transfer_id = v_transfer_id;

    INSERT INTO docker_events (
        daemon_id,
        image_id,
        event,
        description
    )
    SELECT
        d.daemon_id,
        p_image_id,
        CASE p_direction
            WHEN 'push' THEN 'image_push'::event_type
            ELSE 'image_pull'::event_type
        END,
        'Registry transfer completed'
    FROM docker_daemons d
    WHERE d.status = 'available'
    ORDER BY d.daemon_id
    LIMIT 1;

END;
$$;


-- ============================================================
-- 13. OPERATIONAL VIEWS
-- ============================================================

CREATE VIEW v_container_inventory AS
SELECT
    c.container_id,
    c.container_name,
    c.container_runtime_id,
    c.status,
    c.memory_limit_mb,
    c.cpu_limit,
    h.hostname,
    d.daemon_version,
    r.repository_name,
    i.image_tag,
    i.image_digest,
    c.created_at,
    c.started_at,
    c.stopped_at
FROM containers c
JOIN docker_daemons d
    ON d.daemon_id = c.daemon_id
JOIN docker_hosts h
    ON h.host_id = d.host_id
JOIN images i
    ON i.image_id = c.image_id
JOIN image_repositories r
    ON r.repository_id = i.repository_id;


CREATE VIEW v_daemon_resource_usage AS
SELECT
    d.daemon_id,
    h.hostname,
    h.total_memory_mb,
    h.total_cpu,
    COALESCE(SUM(
        CASE
            WHEN ra.released_at IS NULL
            THEN ra.memory_mb
            ELSE 0
        END
    ), 0) AS allocated_memory_mb,
    COALESCE(SUM(
        CASE
            WHEN ra.released_at IS NULL
            THEN ra.cpu_cores
            ELSE 0
        END
    ), 0) AS allocated_cpu,
    COUNT(DISTINCT CASE
        WHEN c.status = 'running'
        THEN c.container_id
    END) AS running_containers
FROM docker_daemons d
JOIN docker_hosts h
    ON h.host_id = d.host_id
LEFT JOIN containers c
    ON c.daemon_id = d.daemon_id
LEFT JOIN resource_allocations ra
    ON ra.container_id = c.container_id
GROUP BY
    d.daemon_id,
    h.hostname,
    h.total_memory_mb,
    h.total_cpu;


CREATE VIEW v_registry_image_inventory AS
SELECT
    rg.registry_name,
    rg.registry_url,
    rg.registry_category,
    repo.repository_name,
    i.image_tag,
    i.image_digest,
    i.image_state,
    i.size_mb,
    i.created_at
FROM registries rg
JOIN image_repositories repo
    ON repo.registry_id = rg.registry_id
JOIN images i
    ON i.repository_id = repo.repository_id;


-- ============================================================
-- 14. SAMPLE INFRASTRUCTURE
-- ============================================================

INSERT INTO docker_hosts (
    hostname,
    operating_system,
    architecture,
    total_memory_mb,
    total_cpu,
    storage_capacity_mb
)
VALUES
(
    'docker-host-01',
    'Ubuntu 24.04',
    'amd64',
    16384,
    8,
    200000
),
(
    'docker-host-02',
    'Ubuntu 24.04',
    'arm64',
    8192,
    4,
    100000
);


INSERT INTO docker_daemons (
    host_id,
    daemon_version,
    api_version,
    status,
    started_at
)
VALUES
(
    1,
    '27.5.1',
    '1.47',
    'available',
    NOW() - INTERVAL '2 days'
),
(
    2,
    '27.5.1',
    '1.47',
    'available',
    NOW() - INTERVAL '1 day'
);


INSERT INTO registries (
    registry_name,
    registry_url,
    registry_category,
    requires_authentication
)
VALUES
(
    'Docker Hub',
    'https://registry-1.docker.io',
    'public',
    FALSE
),
(
    'Company Registry',
    'https://registry.example.com',
    'private',
    TRUE
),
(
    'Internal Registry',
    'https://internal.example.com',
    'internal',
    TRUE
);


INSERT INTO registry_accounts (
    registry_id,
    username,
    credential_reference,
    can_pull,
    can_push
)
VALUES
(
    2,
    'developer',
    'secret-manager://docker/developer',
    TRUE,
    TRUE
),
(
    2,
    'deployment-service',
    'secret-manager://docker/deployment',
    TRUE,
    FALSE
);


INSERT INTO image_repositories (
    registry_id,
    repository_name,
    owner_team,
    is_private
)
VALUES
(
    2,
    'company/web-service',
    'platform-team',
    TRUE
),
(
    2,
    'company/worker',
    'operations-team',
    TRUE
),
(
    1,
    'library/nginx',
    'platform-team',
    FALSE
);


INSERT INTO images (
    repository_id,
    image_digest,
    image_tag,
    architecture,
    size_mb,
    image_state,
    created_by
)
VALUES
(
    1,
    'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    '1.0',
    'amd64',
    180.50,
    'available',
    'developer'
),
(
    1,
    'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    '2.0',
    'amd64',
    195.00,
    'available',
    'developer'
),
(
    2,
    'sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
    '1.0',
    'amd64',
    220.00,
    'available',
    'operations'
),
(
    3,
    'sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
    'stable',
    'amd64',
    45.00,
    'available',
    'platform-team'
),
(
    1,
    'sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
    'broken',
    'amd64',
    0,
    'failed',
    'developer'
);


INSERT INTO image_layers (
    image_id,
    layer_order,
    layer_digest,
    instruction,
    size_mb
)
VALUES
(
    1,
    0,
    'sha256:1111111111111111111111111111111111111111111111111111111111111111',
    'FROM python:3.13-slim',
    80
),
(
    1,
    1,
    'sha256:2222222222222222222222222222222222222222222222222222222222222222',
    'WORKDIR /app',
    0.1
),
(
    1,
    2,
    'sha256:3333333333333333333333333333333333333333333333333333333333333333',
    'COPY application.py /app',
    2
),
(
    1,
    3,
    'sha256:4444444444444444444444444444444444444444444444444444444444444444',
    'RUN pip install -r requirements.txt',
    98.4
);


INSERT INTO image_tags (
    image_id,
    tag_name
)
VALUES
(1, 'latest'),
(1, 'stable'),
(2, 'latest'),
(3, 'latest'),
(4, 'stable');


-- ============================================================
-- 15. CONTAINER SAMPLE RECORDS
-- ============================================================

INSERT INTO containers (
    daemon_id,
    image_id,
    container_name,
    container_runtime_id,
    status,
    memory_limit_mb,
    cpu_limit
)
VALUES
(
    1,
    1,
    'web-production',
    'a1b2c3d4e5f6',
    'running',
    1024,
    2.0
),
(
    1,
    3,
    'worker-production',
    'b1c2d3e4f5a6',
    'running',
    2048,
    2.0
),
(
    2,
    4,
    'nginx-proxy',
    'c1d2e3f4a5b6',
    'stopped',
    512,
    1.0
),
(
    1,
    2,
    'web-staging',
    'd1e2f3a4b5c6',
    'created',
    512,
    1.0
);


INSERT INTO container_ports (
    container_id,
    host_port,
    container_port,
    protocol
)
VALUES
(1, 8080, 8000, 'tcp'),
(2, 9090, 9090, 'tcp'),
(3, 8081, 80, 'tcp'),
(4, 8082, 8000, 'tcp');


INSERT INTO container_environment (
    container_id,
    variable_name,
    variable_value,
    is_sensitive
)
VALUES
(1, 'APP_ENV', 'production', FALSE),
(1, 'DATABASE_URL', 'secret-manager://database/web', TRUE),
(2, 'WORKER_MODE', 'background', FALSE),
(3, 'NGINX_MODE', 'reverse-proxy', FALSE);


INSERT INTO container_logs (
    container_id,
    log_level,
    log_message
)
VALUES
(1, 'INFO', 'Application started on port 8000'),
(1, 'INFO', 'Database connection established'),
(2, 'INFO', 'Worker queue initialized'),
(3, 'WARNING', 'Container stopped for maintenance');


INSERT INTO resource_allocations (
    container_id,
    memory_mb,
    cpu_cores
)
VALUES
(1, 1024, 2.0),
(2, 2048, 2.0);


INSERT INTO docker_events (
    daemon_id,
    container_id,
    image_id,
    event,
    description
)
VALUES
(1, 1, 1, 'container_start', 'Production web service started'),
(1, 2, 3, 'container_start', 'Background worker started'),
(2, 3, 4, 'container_stop', 'Proxy stopped for maintenance'),
(1, NULL, 2, 'image_build', 'Staging image built');


INSERT INTO image_transfers (
    image_id,
    registry_id,
    transfer_direction,
    status,
    completed_at
)
VALUES
(1, 2, 'push', 'succeeded', NOW()),
(2, 2, 'push', 'succeeded', NOW()),
(3, 2, 'pull', 'succeeded', NOW()),
(4, 1, 'pull', 'failed', NOW());


-- ============================================================
-- 16. BASIC RETRIEVAL QUERIES
-- ============================================================

-- All registered Docker hosts and daemon versions.

SELECT
    h.hostname,
    h.architecture,
    d.daemon_version,
    d.status
FROM docker_hosts h
JOIN docker_daemons d
    ON d.host_id = h.host_id
ORDER BY h.hostname;


-- Available images and their layer counts.

SELECT
    i.image_id,
    r.repository_name,
    i.image_tag,
    i.image_digest,
    i.size_mb,
    COUNT(l.layer_id) AS layer_count
FROM images i
JOIN image_repositories r
    ON r.repository_id = i.repository_id
LEFT JOIN image_layers l
    ON l.image_id = i.image_id
WHERE i.image_state = 'available'
GROUP BY
    i.image_id,
    r.repository_name,
    i.image_tag,
    i.image_digest,
    i.size_mb
ORDER BY i.created_at DESC;


-- Running containers.

SELECT *
FROM v_container_inventory
WHERE status = 'running'
ORDER BY hostname, container_name;


-- ============================================================
-- 17. VALIDATION QUERIES
-- ============================================================

-- Detect containers whose image is not available.

SELECT
    c.container_name,
    i.image_state
FROM containers c
JOIN images i
    ON i.image_id = c.image_id
WHERE i.image_state <> 'available';


-- Detect resource allocation exceeding host capacity.

SELECT *
FROM v_daemon_resource_usage
WHERE allocated_memory_mb > total_memory_mb
   OR allocated_cpu > total_cpu;


-- Detect duplicate active host-port assignments.

SELECT
    c.daemon_id,
    cp.host_port,
    cp.protocol,
    COUNT(*) AS allocation_count
FROM container_ports cp
JOIN containers c
    ON c.container_id = cp.container_id
WHERE c.status = 'running'
GROUP BY
    c.daemon_id,
    cp.host_port,
    cp.protocol
HAVING COUNT(*) > 1;


-- ============================================================
-- 18. AGGREGATION AND REPORTING
-- ============================================================

-- Container distribution by state.

SELECT
    status,
    COUNT(*) AS total_containers
FROM containers
GROUP BY status
ORDER BY total_containers DESC;


-- Image storage consumption by repository.

SELECT
    r.repository_name,
    COUNT(i.image_id) AS total_images,
    COALESCE(SUM(i.size_mb), 0) AS total_storage_mb,
    ROUND(AVG(i.size_mb), 2) AS average_image_size_mb
FROM image_repositories r
LEFT JOIN images i
    ON i.repository_id = r.repository_id
GROUP BY r.repository_id, r.repository_name
ORDER BY total_storage_mb DESC;


-- Registry transfer reliability.

SELECT
    rg.registry_name,
    COUNT(t.transfer_id) AS total_transfers,
    COUNT(*) FILTER (
        WHERE t.status = 'succeeded'
    ) AS successful_transfers,
    COUNT(*) FILTER (
        WHERE t.status = 'failed'
    ) AS failed_transfers,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE t.status = 'succeeded'
        ) / NULLIF(COUNT(t.transfer_id), 0),
        2
    ) AS success_percentage
FROM registries rg
LEFT JOIN image_transfers t
    ON t.registry_id = rg.registry_id
GROUP BY rg.registry_id, rg.registry_name;


-- ============================================================
-- 19. CTE: RESOURCE UTILIZATION
-- ============================================================

WITH host_usage AS (
    SELECT
        d.daemon_id,
        h.hostname,
        h.total_memory_mb,
        h.total_cpu,
        COALESCE(SUM(
            CASE
                WHEN ra.released_at IS NULL
                THEN ra.memory_mb
                ELSE 0
            END
        ), 0) AS allocated_memory
    FROM docker_daemons d
    JOIN docker_hosts h
        ON h.host_id = d.host_id
    LEFT JOIN containers c
        ON c.daemon_id = d.daemon_id
    LEFT JOIN resource_allocations ra
        ON ra.container_id = c.container_id
    GROUP BY
        d.daemon_id,
        h.hostname,
        h.total_memory_mb,
        h.total_cpu
)
SELECT
    hostname,
    allocated_memory,
    total_memory_mb,
    ROUND(
        100.0 * allocated_memory /
        NULLIF(total_memory_mb, 0),
        2
    ) AS memory_utilization_percentage
FROM host_usage
ORDER BY memory_utilization_percentage DESC;


-- ============================================================
-- 20. ELIGIBILITY DETERMINATION
-- ============================================================

CREATE OR REPLACE FUNCTION is_container_eligible(
    p_container_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_eligible BOOLEAN;
BEGIN
    SELECT
        c.status IN ('created', 'stopped')
        AND i.image_state = 'available'
        AND d.status = 'available'
        AND c.memory_limit_mb <= h.total_memory_mb
        AND c.cpu_limit <= h.total_cpu
    INTO v_eligible
    FROM containers c
    JOIN images i
        ON i.image_id = c.image_id
    JOIN docker_daemons d
        ON d.daemon_id = c.daemon_id
    JOIN docker_hosts h
        ON h.host_id = d.host_id
    WHERE c.container_id = p_container_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Container not found';
    END IF;

    RETURN v_eligible;
END;
$$;


SELECT
    container_id,
    container_name,
    is_container_eligible(container_id) AS eligible_for_start
FROM containers
ORDER BY container_id;


-- ============================================================
-- 21. TRANSACTIONAL CONTAINER START
-- ============================================================

-- Resource allocation and lifecycle state change are performed
-- in one transaction. A failed operation rolls back both.

DO $$
BEGIN
    BEGIN
        PERFORM change_container_state(
            4,
            'running'
        );

        RAISE NOTICE 'Container started successfully';

    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Container start rejected: %',
                SQLERRM;
    END;
END;
$$;


-- ============================================================
-- 22. IMAGE TAGGING
-- ============================================================

INSERT INTO image_tags (
    image_id,
    tag_name
)
VALUES (
    1,
    'release-2026'
)
ON CONFLICT (image_id, tag_name)
DO NOTHING;


-- ============================================================
-- 23. REGISTRY TRANSFER
-- ============================================================

CALL register_image_transfer(
    1,
    2,
    'push'
);


-- ============================================================
-- 24. FAILURE INVESTIGATION
-- ============================================================

-- Failed image builds.

SELECT
    image_id,
    image_tag,
    image_digest,
    created_by,
    created_at
FROM images
WHERE image_state = 'failed';


-- Failed registry transfers.

SELECT
    transfer_id,
    transfer_direction,
    status,
    error_message,
    started_at
FROM image_transfers
WHERE status = 'failed';


-- Container operational logs.

SELECT
    c.container_name,
    l.log_level,
    l.log_message,
    l.logged_at
FROM container_logs l
JOIN containers c
    ON c.container_id = l.container_id
ORDER BY l.logged_at DESC;


-- ============================================================
-- 25. JSONB EVENT REPORT
-- ============================================================

SELECT
    event_id,
    event,
    description,
    metadata,
    occurred_at
FROM docker_events
WHERE metadata @> '{}'::jsonb
ORDER BY occurred_at DESC;


COMMIT;

-- ============================================================
-- 26. OPERATIONAL REFERENCE QUERIES
-- ============================================================

-- Current daemon inventory.

SELECT *
FROM docker_daemons
ORDER BY daemon_id;


-- Current container inventory.

SELECT *
FROM v_container_inventory
ORDER BY hostname, container_name;


-- Current resource consumption.

SELECT *
FROM v_daemon_resource_usage
ORDER BY hostname;


-- Registry inventory.

SELECT *
FROM v_registry_image_inventory
ORDER BY registry_name, repository_name;


-- Latest Docker events.

SELECT
    event,
    description,
    occurred_at
FROM docker_events
ORDER BY occurred_at DESC
LIMIT 20;
