-- ================================================================
-- DOCKER CONTAINER MANAGEMENT DATABASE
-- PostgreSQL 15+
--
-- Models:
--   Container inventory
--   Container lifecycle
--   Image references
--   Environment variables
--   Commands and execution records
--   Logs
--   Restart policies
--   Resource limits
--   Inspection snapshots
--   Operational eligibility
--
-- This database records and governs container operations.
-- It does not communicate with the Docker Engine.
-- ================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS docker_management;

SET search_path TO docker_management, public;

-- ================================================================
-- 1. ENUM TYPES
-- ================================================================

CREATE TYPE container_state AS ENUM (
    'created',
    'running',
    'paused',
    'restarting',
    'stopped',
    'exited',
    'removing',
    'removed'
);

CREATE TYPE restart_policy AS ENUM (
    'no',
    'always',
    'on-failure',
    'unless-stopped'
);

CREATE TYPE log_level AS ENUM (
    'DEBUG',
    'INFO',
    'WARN',
    'ERROR',
    'FATAL'
);

CREATE TYPE operation_type AS ENUM (
    'create',
    'start',
    'pause',
    'unpause',
    'stop',
    'restart',
    'remove',
    'execute',
    'inspect'
);

CREATE TYPE operation_status AS ENUM (
    'pending',
    'success',
    'failed'
);

-- ================================================================
-- 2. USERS AND HOSTS
-- ================================================================

CREATE TABLE operators (
    operator_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    role VARCHAR(30) NOT NULL
        CHECK (role IN ('administrator', 'operator', 'viewer')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE docker_hosts (
    host_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    host_name VARCHAR(120) NOT NULL UNIQUE,
    engine_version VARCHAR(40) NOT NULL,
    operating_system VARCHAR(80) NOT NULL,
    architecture VARCHAR(40) NOT NULL,
    total_memory_mb INTEGER NOT NULL
        CHECK (total_memory_mb > 0),
    total_cpu NUMERIC(8,2) NOT NULL
        CHECK (total_cpu > 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ================================================================
-- 3. IMAGE REGISTRY
-- ================================================================

CREATE TABLE container_images (
    image_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository VARCHAR(255) NOT NULL,
    tag VARCHAR(128) NOT NULL DEFAULT 'latest',
    digest VARCHAR(128),
    registry VARCHAR(255) NOT NULL DEFAULT 'docker.io',
    size_bytes BIGINT NOT NULL DEFAULT 0
        CHECK (size_bytes >= 0),
    trusted BOOLEAN NOT NULL DEFAULT FALSE,
    scanned BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_image_reference
        UNIQUE (registry, repository, tag)
);

CREATE INDEX idx_images_repository
    ON container_images(repository);

-- ================================================================
-- 4. CONTAINERS
-- ================================================================

CREATE TABLE containers (
    container_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    docker_id VARCHAR(64) NOT NULL UNIQUE,
    container_name VARCHAR(128) NOT NULL UNIQUE,

    image_id BIGINT NOT NULL
        REFERENCES container_images(image_id),

    host_id BIGINT NOT NULL
        REFERENCES docker_hosts(host_id),

    state container_state NOT NULL DEFAULT 'created',

    restart_policy restart_policy NOT NULL DEFAULT 'no',

    memory_limit_mb INTEGER NOT NULL DEFAULT 512
        CHECK (memory_limit_mb >= 16),

    cpu_limit NUMERIC(8,2) NOT NULL DEFAULT 1.0
        CHECK (cpu_limit BETWEEN 0.1 AND 64),

    restart_count INTEGER NOT NULL DEFAULT 0
        CHECK (restart_count >= 0),

    exit_code INTEGER
        CHECK (exit_code BETWEEN 0 AND 255),

    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,

    manually_stopped BOOLEAN NOT NULL DEFAULT FALSE,

    created_by BIGINT NOT NULL
        REFERENCES operators(operator_id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_container_timestamps
        CHECK (
            finished_at IS NULL
            OR started_at IS NULL
            OR finished_at >= started_at
        )
);

CREATE INDEX idx_containers_state
    ON containers(state);

CREATE INDEX idx_containers_host_state
    ON containers(host_id, state);

CREATE INDEX idx_containers_created
    ON containers(created_at DESC);

CREATE INDEX idx_containers_restart
    ON containers(restart_policy, state);

-- ================================================================
-- 5. ENVIRONMENT VARIABLES
-- ================================================================

CREATE TABLE container_environment (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    container_id BIGINT NOT NULL
        REFERENCES containers(container_id)
        ON DELETE CASCADE,

    variable_name VARCHAR(128) NOT NULL
        CHECK (
            variable_name ~ '^[A-Za-z_][A-Za-z0-9_]*$'
        ),

    variable_value TEXT NOT NULL,

    is_secret BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_container_environment
        UNIQUE (container_id, variable_name)
);

CREATE INDEX idx_environment_container
    ON container_environment(container_id);

-- Secret values should be stored in a dedicated secrets manager
-- in production. The flag does not encrypt the value.

-- ================================================================
-- 6. COMMAND DEFINITIONS
-- ================================================================

CREATE TABLE allowed_commands (
    command_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    executable VARCHAR(100) NOT NULL UNIQUE,

    description TEXT NOT NULL,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO allowed_commands (executable, description)
VALUES
    ('echo', 'Display supplied text'),
    ('printenv', 'Display environment variables'),
    ('hostname', 'Display container hostname'),
    ('date', 'Display current date and time'),
    ('uname', 'Display operating system information');

CREATE TABLE container_commands (
    execution_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    container_id BIGINT NOT NULL
        REFERENCES containers(container_id),

    operator_id BIGINT NOT NULL
        REFERENCES operators(operator_id),

    executable VARCHAR(100) NOT NULL,

    arguments JSONB NOT NULL DEFAULT '[]'::JSONB
        CHECK (jsonb_typeof(arguments) = 'array'),

    output TEXT,

    exit_code INTEGER
        CHECK (exit_code BETWEEN 0 AND 255),

    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    successful BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_commands_container_time
    ON container_commands(container_id, executed_at DESC);

-- ================================================================
-- 7. LOGS
-- ================================================================

CREATE TABLE container_logs (
    log_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    container_id BIGINT NOT NULL
        REFERENCES containers(container_id)
        ON DELETE CASCADE,

    level log_level NOT NULL DEFAULT 'INFO',

    message TEXT NOT NULL,

    source VARCHAR(100) NOT NULL DEFAULT 'container',

    logged_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_logs_container_time
    ON container_logs(container_id, logged_at DESC);

CREATE INDEX idx_logs_error_time
    ON container_logs(logged_at DESC)
    WHERE level IN ('ERROR', 'FATAL');

-- ================================================================
-- 8. OPERATION AUDIT
-- ================================================================

CREATE TABLE container_operations (
    operation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    container_id BIGINT
        REFERENCES containers(container_id)
        ON DELETE SET NULL,

    operator_id BIGINT NOT NULL
        REFERENCES operators(operator_id),

    operation operation_type NOT NULL,

    status operation_status NOT NULL DEFAULT 'pending',

    previous_state container_state,

    resulting_state container_state,

    error_message TEXT,

    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_operations_container
    ON container_operations(container_id, requested_at DESC);

CREATE INDEX idx_operations_failed
    ON container_operations(requested_at DESC)
    WHERE status = 'failed';

-- ================================================================
-- 9. INSPECTION SNAPSHOTS
-- ================================================================

CREATE TABLE container_inspections (
    inspection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    container_id BIGINT NOT NULL
        REFERENCES containers(container_id)
        ON DELETE CASCADE,

    inspected_by BIGINT NOT NULL
        REFERENCES operators(operator_id),

    inspection_data JSONB NOT NULL
        CHECK (jsonb_typeof(inspection_data) = 'object'),

    inspected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_inspections_container
    ON container_inspections(container_id, inspected_at DESC);

CREATE INDEX idx_inspections_json
    ON container_inspections
    USING GIN(inspection_data);

-- ================================================================
-- 10. RESOURCE VALIDATION FUNCTION
-- ================================================================

CREATE OR REPLACE FUNCTION validate_container_resources()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    available_memory INTEGER;
    available_cpu NUMERIC(8,2);
    allocated_memory BIGINT;
    allocated_cpu NUMERIC(12,2);
BEGIN
    SELECT total_memory_mb, total_cpu
    INTO available_memory, available_cpu
    FROM docker_hosts
    WHERE host_id = NEW.host_id
      AND active = TRUE
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Docker host is unavailable.';
    END IF;

    SELECT
        COALESCE(SUM(memory_limit_mb), 0),
        COALESCE(SUM(cpu_limit), 0)
    INTO allocated_memory, allocated_cpu
    FROM containers
    WHERE host_id = NEW.host_id
      AND state IN ('created', 'running', 'paused', 'restarting')
      AND container_id <> COALESCE(NEW.container_id, -1);

    IF allocated_memory + NEW.memory_limit_mb > available_memory THEN
        RAISE EXCEPTION
            'Insufficient host memory: requested %, available %',
            NEW.memory_limit_mb,
            available_memory - allocated_memory;
    END IF;

    IF allocated_cpu + NEW.cpu_limit > available_cpu THEN
        RAISE EXCEPTION
            'Insufficient host CPU capacity.';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_container_resources
BEFORE INSERT OR UPDATE OF host_id, memory_limit_mb, cpu_limit
ON containers
FOR EACH ROW
EXECUTE FUNCTION validate_container_resources();

-- ================================================================
-- 11. STATE TRANSITION VALIDATION
-- ================================================================

CREATE OR REPLACE FUNCTION enforce_container_state_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = OLD.state THEN
        RETURN NEW;
    END IF;

    IF NOT (
        (OLD.state = 'created'
            AND NEW.state IN ('running', 'removing'))
        OR
        (OLD.state = 'running'
            AND NEW.state IN (
                'paused', 'stopped', 'exited', 'restarting', 'removing'
            ))
        OR
        (OLD.state = 'paused'
            AND NEW.state IN (
                'running', 'stopped', 'removing'
            ))
        OR
        (OLD.state = 'restarting'
            AND NEW.state IN ('running', 'exited', 'stopped'))
        OR
        (OLD.state = 'stopped'
            AND NEW.state IN ('running', 'removing'))
        OR
        (OLD.state = 'exited'
            AND NEW.state IN ('running', 'removing'))
        OR
        (OLD.state = 'removing'
            AND NEW.state = 'removed')
    ) THEN
        RAISE EXCEPTION
            'Invalid container state transition: % -> %',
            OLD.state,
            NEW.state;
    END IF;

    NEW.updated_at = NOW();

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_container_state_transition
BEFORE UPDATE OF state
ON containers
FOR EACH ROW
EXECUTE FUNCTION enforce_container_state_transition();

-- ================================================================
-- 12. UPDATED TIMESTAMP
-- ================================================================

CREATE OR REPLACE FUNCTION update_container_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_container_updated_at
BEFORE UPDATE
ON containers
FOR EACH ROW
EXECUTE FUNCTION update_container_timestamp();

-- ================================================================
-- 13. RESTART POLICY EVALUATION
-- ================================================================

CREATE OR REPLACE FUNCTION restart_eligible(
    p_container_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    selected_policy restart_policy;
    selected_state container_state;
    selected_exit_code INTEGER;
    selected_manual_stop BOOLEAN;
BEGIN
    SELECT
        restart_policy,
        state,
        exit_code,
        manually_stopped
    INTO
        selected_policy,
        selected_state,
        selected_exit_code,
        selected_manual_stop
    FROM containers
    WHERE container_id = p_container_id;

    IF NOT FOUND OR selected_state <> 'exited' THEN
        RETURN FALSE;
    END IF;

    RETURN CASE selected_policy
        WHEN 'no' THEN FALSE
        WHEN 'always' THEN TRUE
        WHEN 'unless-stopped' THEN NOT selected_manual_stop
        WHEN 'on-failure' THEN
            COALESCE(selected_exit_code, 0) <> 0
    END;
END;
$$;

-- ================================================================
-- 14. CONTAINER LIFECYCLE PROCEDURE
-- ================================================================

CREATE OR REPLACE PROCEDURE change_container_state(
    p_container_id BIGINT,
    p_operator_id BIGINT,
    p_operation operation_type,
    p_exit_code INTEGER DEFAULT 0
)
LANGUAGE plpgsql
AS $$
DECLARE
    current_state container_state;
    next_state container_state;
    current_code INTEGER;
    operation_id_value BIGINT;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM operators
        WHERE operator_id = p_operator_id
          AND active = TRUE
          AND role IN ('administrator', 'operator')
    ) THEN
        RAISE EXCEPTION 'Operator is not authorized.';
    END IF;

    SELECT state
    INTO current_state
    FROM containers
    WHERE container_id = p_container_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Container does not exist.';
    END IF;

    INSERT INTO container_operations (
        container_id,
        operator_id,
        operation,
        status,
        previous_state
    )
    VALUES (
        p_container_id,
        p_operator_id,
        p_operation,
        'pending',
        current_state
    )
    RETURNING operation_id INTO operation_id_value;

    CASE p_operation
        WHEN 'start' THEN
            IF current_state NOT IN ('created', 'stopped', 'exited') THEN
                RAISE EXCEPTION 'Container cannot be started from %',
                    current_state;
            END IF;

            next_state := 'running';

            UPDATE containers
            SET
                state = next_state,
                started_at = NOW(),
                finished_at = NULL,
                exit_code = NULL,
                manually_stopped = FALSE
            WHERE container_id = p_container_id;

        WHEN 'pause' THEN
            IF current_state <> 'running' THEN
                RAISE EXCEPTION 'Only running containers can be paused.';
            END IF;

            next_state := 'paused';

            UPDATE containers
            SET state = next_state
            WHERE container_id = p_container_id;

        WHEN 'unpause' THEN
            IF current_state <> 'paused' THEN
                RAISE EXCEPTION 'Container is not paused.';
            END IF;

            next_state := 'running';

            UPDATE containers
            SET state = next_state
            WHERE container_id = p_container_id;

        WHEN 'stop' THEN
            IF current_state NOT IN ('running', 'paused') THEN
                RAISE EXCEPTION 'Container cannot be stopped.';
            END IF;

            IF p_exit_code NOT BETWEEN 0 AND 255 THEN
                RAISE EXCEPTION 'Invalid exit code.';
            END IF;

            next_state := 'stopped';

            UPDATE containers
            SET
                state = next_state,
                exit_code = p_exit_code,
                finished_at = NOW(),
                manually_stopped = TRUE
            WHERE container_id = p_container_id;

        WHEN 'restart' THEN
            IF current_state NOT IN (
                'running', 'paused', 'stopped', 'exited'
            ) THEN
                RAISE EXCEPTION 'Container cannot be restarted.';
            END IF;

            next_state := 'running';

            UPDATE containers
            SET
                state = next_state,
                started_at = NOW(),
                finished_at = NULL,
                exit_code = NULL,
                restart_count = restart_count + 1,
                manually_stopped = FALSE
            WHERE container_id = p_container_id;

        WHEN 'remove' THEN
            IF current_state IN ('running', 'paused') THEN
                RAISE EXCEPTION 'Stop container before removal.';
            END IF;

            next_state := 'removed';

            UPDATE containers
            SET state = 'removing'
            WHERE container_id = p_container_id;

            UPDATE containers
            SET state = 'removed'
            WHERE container_id = p_container_id;

        ELSE
            RAISE EXCEPTION
                'Unsupported lifecycle operation: %',
                p_operation;
    END CASE;

    UPDATE container_operations
    SET
        status = 'success',
        resulting_state = next_state,
        completed_at = NOW()
    WHERE operation_id = operation_id_value;

    INSERT INTO container_logs (
        container_id,
        level,
        message,
        source
    )
    VALUES (
        p_container_id,
        'INFO',
        'Operation completed: ' || p_operation,
        'management-service'
    );

EXCEPTION
    WHEN OTHERS THEN
        UPDATE container_operations
        SET
            status = 'failed',
            error_message = SQLERRM,
            completed_at = NOW()
        WHERE operation_id = operation_id_value;

        RAISE;
END;
$$;

-- ================================================================
-- 15. ENVIRONMENT VARIABLE UPSERT PROCEDURE
-- ================================================================

CREATE OR REPLACE PROCEDURE set_environment_variable(
    p_container_id BIGINT,
    p_name VARCHAR(128),
    p_value TEXT,
    p_is_secret BOOLEAN DEFAULT FALSE
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_name !~ '^[A-Za-z_][A-Za-z0-9_]*$' THEN
        RAISE EXCEPTION 'Invalid environment variable name.';
    END IF;

    IF p_value IS NULL THEN
        RAISE EXCEPTION 'Environment value cannot be NULL.';
    END IF;

    INSERT INTO container_environment (
        container_id,
        variable_name,
        variable_value,
        is_secret
    )
    VALUES (
        p_container_id,
        p_name,
        p_value,
        p_is_secret
    )
    ON CONFLICT (container_id, variable_name)
    DO UPDATE SET
        variable_value = EXCLUDED.variable_value,
        is_secret = EXCLUDED.is_secret;
END;
$$;

-- ================================================================
-- 16. ELIGIBILITY VIEW
-- ================================================================

CREATE OR REPLACE VIEW container_operational_eligibility AS
SELECT
    c.container_id,
    c.container_name,
    c.state,
    c.restart_policy,
    c.memory_limit_mb,
    c.cpu_limit,

    CASE
        WHEN c.state = 'running'
            THEN TRUE
        ELSE FALSE
    END AS accepts_execution,

    CASE
        WHEN c.state = 'exited'
             AND restart_eligible(c.container_id)
            THEN TRUE
        ELSE FALSE
    END AS restart_eligible,

    CASE
        WHEN c.state = 'running'
            THEN 'running'
        WHEN c.state = 'exited'
             AND restart_eligible(c.container_id)
            THEN 'restart_candidate'
        WHEN c.state = 'exited'
            THEN 'restart_not_required'
        ELSE 'not_running'
    END AS operational_status

FROM containers c;

-- ================================================================
-- 17. SAMPLE DATA
-- ================================================================

INSERT INTO operators (username, role)
VALUES
    ('platform_admin', 'administrator'),
    ('deployment_operator', 'operator'),
    ('audit_viewer', 'viewer');

INSERT INTO docker_hosts (
    host_name,
    engine_version,
    operating_system,
    architecture,
    total_memory_mb,
    total_cpu
)
VALUES
    (
        'docker-host-01',
        '28.0.0',
        'Ubuntu 24.04',
        'x86_64',
        16384,
        16
    ),
    (
        'docker-host-02',
        '28.0.0',
        'Debian 12',
        'x86_64',
        8192,
        8
    );

INSERT INTO container_images (
    repository,
    tag,
    digest,
    registry,
    size_bytes,
    trusted,
    scanned
)
VALUES
    (
        'nginx',
        '1.27-alpine',
        'sha256:nginx127',
        'docker.io',
        45000000,
        TRUE,
        TRUE
    ),
    (
        'postgres',
        '18-alpine',
        'sha256:postgres18',
        'docker.io',
        110000000,
        TRUE,
        TRUE
    ),
    (
        'node',
        '22-alpine',
        'sha256:node22',
        'docker.io',
        65000000,
        TRUE,
        TRUE
    ),
    (
        'unverified-application',
        'latest',
        NULL,
        'registry.internal',
        30000000,
        FALSE,
        FALSE
    );

INSERT INTO containers (
    docker_id,
    container_name,
    image_id,
    host_id,
    state,
    restart_policy,
    memory_limit_mb,
    cpu_limit,
    created_by
)
VALUES
    (
        'aabbcc001122',
        'web-api',
        1,
        1,
        'created',
        'on-failure',
        1024,
        2,
        1
    ),
    (
        'aabbcc003344',
        'orders-db',
        2,
        1,
        'created',
        'always',
        2048,
        2,
        1
    ),
    (
        'aabbcc005566',
        'worker',
        3,
        2,
        'created',
        'unless-stopped',
        1024,
        1,
        2
    ),
    (
        'aabbcc007788',
        'unverified-app',
        4,
        2,
        'created',
        'no',
        512,
        1,
        2
    );

CALL set_environment_variable(
    1, 'APP_ENV', 'production', FALSE
);

CALL set_environment_variable(
    1, 'PORT', '8000', FALSE
);

CALL set_environment_variable(
    1, 'API_SECRET', 'sample-secret-value', TRUE
);

CALL set_environment_variable(
    2, 'POSTGRES_DB', 'orders', FALSE
);

CALL set_environment_variable(
    2, 'POSTGRES_USER', 'application', FALSE
);

INSERT INTO container_logs (
    container_id,
    level,
    message,
    source
)
VALUES
    (1, 'INFO', 'Container created.', 'docker'),
    (1, 'INFO', 'Application configuration loaded.', 'application'),
    (1, 'WARN', 'Connection pool approaching capacity.', 'application'),
    (2, 'INFO', 'Database initialization completed.', 'application'),
    (3, 'ERROR', 'Worker process terminated unexpectedly.', 'application');

-- ================================================================
-- 18. TRANSACTIONAL LIFECYCLE DEMONSTRATION
-- ================================================================

DO $$
BEGIN
    CALL change_container_state(
        1,
        1,
        'start'
    );

    CALL change_container_state(
        1,
        1,
        'pause'
    );

    CALL change_container_state(
        1,
        1,
        'unpause'
    );
END;
$$;

-- Simulate an application failure.
UPDATE containers
SET
    state = 'exited',
    exit_code = 1,
    finished_at = NOW()
WHERE container_id = 1;

-- Restart eligibility is calculated from policy and exit state.
SELECT
    container_name,
    state,
    restart_policy,
    restart_eligible(container_id) AS should_restart
FROM containers
ORDER BY container_id;

-- Restart an eligible container transactionally.
DO $$
DECLARE
    selected_id BIGINT;
BEGIN
    SELECT container_id
    INTO selected_id
    FROM containers
    WHERE container_name = 'web-api'
      AND restart_eligible(container_id);

    IF selected_id IS NOT NULL THEN
        CALL change_container_state(
            selected_id,
            1,
            'restart'
        );
    END IF;
END;
$$;

-- ================================================================
-- 19. RETRIEVAL QUERIES
-- ================================================================

-- Container inventory with image and host details.

SELECT
    c.container_id,
    c.container_name,
    i.repository,
    i.tag,
    h.host_name,
    c.state,
    c.memory_limit_mb,
    c.cpu_limit
FROM containers c
JOIN container_images i
    ON i.image_id = c.image_id
JOIN docker_hosts h
    ON h.host_id = c.host_id
ORDER BY c.container_name;

-- Environment configuration.
-- Secret values are deliberately masked.

SELECT
    c.container_name,
    e.variable_name,
    CASE
        WHEN e.is_secret THEN '********'
        ELSE e.variable_value
    END AS displayed_value,
    e.is_secret
FROM container_environment e
JOIN containers c
    ON c.container_id = e.container_id
ORDER BY c.container_name, e.variable_name;

-- ================================================================
-- 20. VALIDATION QUERIES
-- ================================================================

-- Containers using untrusted or unscanned images.

SELECT
    c.container_name,
    i.repository,
    i.tag,
    i.trusted,
    i.scanned
FROM containers c
JOIN container_images i
    ON i.image_id = c.image_id
WHERE NOT i.trusted
   OR NOT i.scanned;

-- Containers exceeding 50 percent of host memory.

SELECT
    c.container_name,
    h.host_name,
    c.memory_limit_mb,
    h.total_memory_mb,
    ROUND(
        100.0 * c.memory_limit_mb / h.total_memory_mb,
        2
    ) AS memory_percentage
FROM containers c
JOIN docker_hosts h
    ON h.host_id = c.host_id
WHERE c.memory_limit_mb > h.total_memory_mb * 0.5;

-- ================================================================
-- 21. AGGREGATION AND RESOURCE REPORTING
-- ================================================================

SELECT
    h.host_name,
    COUNT(c.container_id) AS total_containers,

    COUNT(*) FILTER (
        WHERE c.state = 'running'
    ) AS running_containers,

    COUNT(*) FILTER (
        WHERE c.state = 'paused'
    ) AS paused_containers,

    COUNT(*) FILTER (
        WHERE c.state = 'exited'
    ) AS exited_containers,

    COALESCE(SUM(c.memory_limit_mb), 0)
        AS allocated_memory_mb,

    COALESCE(SUM(c.cpu_limit), 0)
        AS allocated_cpu

FROM docker_hosts h
LEFT JOIN containers c
    ON c.host_id = h.host_id
GROUP BY h.host_id, h.host_name
ORDER BY h.host_name;

-- ================================================================
-- 22. LOG REPORTING
-- ================================================================

SELECT
    c.container_name,
    l.level,
    COUNT(*) AS event_count
FROM container_logs l
JOIN containers c
    ON c.container_id = l.container_id
GROUP BY c.container_name, l.level
ORDER BY c.container_name, l.level;

-- Recent errors.

SELECT
    c.container_name,
    l.logged_at,
    l.message
FROM container_logs l
JOIN containers c
    ON c.container_id = l.container_id
WHERE l.level IN ('ERROR', 'FATAL')
ORDER BY l.logged_at DESC
LIMIT 20;

-- ================================================================
-- 23. WORKFLOW AND AUDIT REPORTING
-- ================================================================

SELECT
    o.operation_id,
    c.container_name,
    op.username,
    o.operation,
    o.status,
    o.previous_state,
    o.resulting_state,
    o.error_message,
    o.requested_at,
    o.completed_at
FROM container_operations o
LEFT JOIN containers c
    ON c.container_id = o.container_id
JOIN operators op
    ON op.operator_id = o.operator_id
ORDER BY o.requested_at DESC;

-- ================================================================
-- 24. INSPECTION SNAPSHOT
-- ================================================================

INSERT INTO container_inspections (
    container_id,
    inspected_by,
    inspection_data
)
SELECT
    c.container_id,
    1,
    jsonb_build_object(
        'name', c.container_name,
        'state', c.state,
        'image', i.repository || ':' || i.tag,
        'memory_limit_mb', c.memory_limit_mb,
        'cpu_limit', c.cpu_limit,
        'restart_policy', c.restart_policy,
        'restart_count', c.restart_count,
        'environment_count', (
            SELECT COUNT(*)
            FROM container_environment e
            WHERE e.container_id = c.container_id
        )
    )
FROM containers c
JOIN container_images i
    ON i.image_id = c.image_id
WHERE c.container_name = 'web-api';

SELECT
    c.container_name,
    s.inspected_at,
    s.inspection_data
FROM container_inspections s
JOIN containers c
    ON c.container_id = s.container_id
ORDER BY s.inspected_at DESC;

-- ================================================================
-- 25. OPERATIONAL ELIGIBILITY
-- ================================================================

SELECT *
FROM container_operational_eligibility
ORDER BY container_name;

-- ================================================================
-- 26. NEGATIVE TESTS
-- ================================================================

-- Each invalid operation is isolated inside a subtransaction.
-- The outer transaction remains usable.

DO $$
BEGIN
    BEGIN
        CALL change_container_state(
            1,
            3,
            'stop'
        );
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Expected authorization rejection: %',
                SQLERRM;
    END;

    BEGIN
        CALL change_container_state(
            1,
            1,
            'pause'
        );
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Expected invalid transition: %',
                SQLERRM;
    END;

    BEGIN
        INSERT INTO container_environment (
            container_id,
            variable_name,
            variable_value
        )
        VALUES (
            1,
            'INVALID-KEY',
            'value'
        );
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Expected environment validation error: %',
                SQLERRM;
    END;
END;
$$;

-- ================================================================
-- 27. FINAL DATABASE INVENTORY
-- ================================================================

SELECT
    c.container_name,
    c.state,
    c.restart_policy,
    c.restart_count,
    c.exit_code,
    h.host_name
FROM containers c
JOIN docker_hosts h
    ON h.host_id = c.host_id
ORDER BY c.container_name;

COMMIT;
