-- Docker Multi-Service Application
-- PostgreSQL database initialization and operational management.
-- Compatible with PostgreSQL 15+.

CREATE SCHEMA IF NOT EXISTS task_management;

SET search_path TO task_management, public;

-- ============================================================
-- ENUMERATIONS
-- ============================================================

CREATE TYPE task_status AS ENUM (
    'pending',
    'in_progress',
    'completed'
);

CREATE TYPE deployment_status AS ENUM (
    'created',
    'starting',
    'healthy',
    'unhealthy',
    'failed',
    'stopped'
);

CREATE TYPE service_type AS ENUM (
    'frontend',
    'backend',
    'database'
);

-- ============================================================
-- APPLICATION USERS
-- ============================================================

CREATE TABLE application_users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TASKS
-- ============================================================

CREATE TABLE tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES application_users(user_id)
        ON DELETE SET NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status task_status NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_task_title
        CHECK (LENGTH(BTRIM(title)) BETWEEN 1 AND 200),

    CONSTRAINT valid_description
        CHECK (LENGTH(description) <= 5000)
);

CREATE INDEX idx_tasks_status
    ON tasks(status);

CREATE INDEX idx_tasks_created_at
    ON tasks(created_at DESC);

CREATE INDEX idx_tasks_user_status
    ON tasks(user_id, status);

-- ============================================================
-- DOCKER SERVICE REGISTRY
-- ============================================================

CREATE TABLE docker_services (
    service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_name VARCHAR(100) NOT NULL UNIQUE,
    service_type service_type NOT NULL,
    image_name VARCHAR(255) NOT NULL,
    image_tag VARCHAR(100) NOT NULL,
    internal_port INTEGER NOT NULL,
    public_exposure BOOLEAN NOT NULL DEFAULT FALSE,
    persistent_storage BOOLEAN NOT NULL DEFAULT FALSE,
    restart_policy VARCHAR(30) NOT NULL DEFAULT 'unless-stopped',
    deployment_state deployment_status NOT NULL DEFAULT 'created',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_internal_port
        CHECK (internal_port BETWEEN 1 AND 65535),

    CONSTRAINT valid_restart_policy
        CHECK (restart_policy IN (
            'no',
            'always',
            'unless-stopped',
            'on-failure'
        )),

    CONSTRAINT database_persistence
        CHECK (
            service_type <> 'database'
            OR persistent_storage = TRUE
        ),

    CONSTRAINT database_not_public
        CHECK (
            service_type <> 'database'
            OR public_exposure = FALSE
        )
);

CREATE TABLE service_dependencies (
    service_id BIGINT NOT NULL REFERENCES docker_services(service_id)
        ON DELETE CASCADE,

    dependency_id BIGINT NOT NULL REFERENCES docker_services(service_id)
        ON DELETE CASCADE,

    PRIMARY KEY (service_id, dependency_id),

    CHECK (service_id <> dependency_id)
);

CREATE TABLE docker_networks (
    network_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    network_name VARCHAR(100) NOT NULL UNIQUE,
    internal_only BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE service_network_memberships (
    service_id BIGINT NOT NULL REFERENCES docker_services(service_id)
        ON DELETE CASCADE,

    network_id BIGINT NOT NULL REFERENCES docker_networks(network_id)
        ON DELETE CASCADE,

    PRIMARY KEY (service_id, network_id)
);

CREATE TABLE service_health_checks (
    healthcheck_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_id BIGINT NOT NULL REFERENCES docker_services(service_id)
        ON DELETE CASCADE,

    check_status BOOLEAN NOT NULL,
    response_time_ms INTEGER CHECK (response_time_ms >= 0),
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    error_message TEXT
);

CREATE INDEX idx_health_service_time
    ON service_health_checks(service_id, checked_at DESC);

-- ============================================================
-- UPDATED_AT TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION update_modified_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_tasks_updated_at
BEFORE UPDATE ON tasks
FOR EACH ROW
EXECUTE FUNCTION update_modified_timestamp();

-- ============================================================
-- SERVICE REGISTRATION
-- ============================================================

INSERT INTO docker_services (
    service_name,
    service_type,
    image_name,
    image_tag,
    internal_port,
    public_exposure,
    persistent_storage,
    restart_policy
)
VALUES
(
    'db',
    'database',
    'postgres',
    '17-alpine',
    5432,
    FALSE,
    TRUE,
    'unless-stopped'
),
(
    'backend',
    'backend',
    'python',
    '3.13-slim',
    8000,
    FALSE,
    FALSE,
    'unless-stopped'
),
(
    'frontend',
    'frontend',
    'node',
    '22-alpine',
    3000,
    TRUE,
    FALSE,
    'unless-stopped'
)
ON CONFLICT (service_name) DO NOTHING;

INSERT INTO docker_networks (network_name, internal_only)
VALUES
    ('backend_network', TRUE),
    ('frontend_network', FALSE)
ON CONFLICT (network_name) DO NOTHING;

-- Backend communicates with database and frontend.
INSERT INTO service_dependencies (
    service_id,
    dependency_id
)
SELECT child.service_id, parent.service_id
FROM (
    VALUES
        ('backend', 'db'),
        ('frontend', 'backend')
) AS dependency(child_name, parent_name)
JOIN docker_services child
    ON child.service_name = dependency.child_name
JOIN docker_services parent
    ON parent.service_name = dependency.parent_name
ON CONFLICT DO NOTHING;

-- Network membership.
INSERT INTO service_network_memberships (
    service_id,
    network_id
)
SELECT service.service_id, network.network_id
FROM (
    VALUES
        ('db', 'backend_network'),
        ('backend', 'backend_network'),
        ('backend', 'frontend_network'),
        ('frontend', 'frontend_network')
) AS membership(service_name, network_name)
JOIN docker_services service
    ON service.service_name = membership.service_name
JOIN docker_networks network
    ON network.network_name = membership.network_name
ON CONFLICT DO NOTHING;

-- ============================================================
-- TASK DATA
-- ============================================================

INSERT INTO application_users (
    username,
    email
)
VALUES
    ('admin', 'admin@example.local'),
    ('developer', 'developer@example.local')
ON CONFLICT DO NOTHING;

INSERT INTO tasks (
    user_id,
    title,
    description,
    status
)
SELECT
    user_id,
    'Configure Docker network',
    'Connect frontend and backend services.',
    'completed'
FROM application_users
WHERE username = 'admin'
AND NOT EXISTS (
    SELECT 1 FROM tasks WHERE title = 'Configure Docker network'
);

INSERT INTO tasks (
    user_id,
    title,
    description,
    status
)
SELECT
    user_id,
    'Implement backend API',
    'Create task management endpoints.',
    'in_progress'
FROM application_users
WHERE username = 'developer'
AND NOT EXISTS (
    SELECT 1 FROM tasks WHERE title = 'Implement backend API'
);

INSERT INTO tasks (
    title,
    description,
    status
)
SELECT
    'Configure PostgreSQL persistence',
    'Verify named volume configuration.',
    'pending'
WHERE NOT EXISTS (
    SELECT 1 FROM tasks
    WHERE title = 'Configure PostgreSQL persistence'
);

-- ============================================================
-- HEALTH CHECK HISTORY
-- ============================================================

INSERT INTO service_health_checks (
    service_id,
    check_status,
    response_time_ms,
    error_message
)
SELECT
    service_id,
    TRUE,
    12,
    NULL
FROM docker_services
WHERE service_name = 'db';

INSERT INTO service_health_checks (
    service_id,
    check_status,
    response_time_ms,
    error_message
)
SELECT
    service_id,
    TRUE,
    35,
    NULL
FROM docker_services
WHERE service_name = 'backend';

INSERT INTO service_health_checks (
    service_id,
    check_status,
    response_time_ms,
    error_message
)
SELECT
    service_id,
    FALSE,
    NULL,
    'Simulated frontend startup failure'
FROM docker_services
WHERE service_name = 'frontend';

-- ============================================================
-- LATEST HEALTH STATUS VIEW
-- ============================================================

CREATE OR REPLACE VIEW latest_service_health AS
SELECT DISTINCT ON (service_id)
    service_id,
    check_status,
    response_time_ms,
    checked_at,
    error_message
FROM service_health_checks
ORDER BY service_id, checked_at DESC, healthcheck_id DESC;

-- ============================================================
-- SERVICE READINESS VIEW
-- ============================================================

CREATE OR REPLACE VIEW service_readiness AS
SELECT
    service.service_name,
    service.service_type,
    service.deployment_state,
    service.public_exposure,
    service.persistent_storage,
    health.check_status,
    health.response_time_ms,
    CASE
        WHEN health.check_status IS TRUE
            THEN 'HEALTHY'
        WHEN health.check_status IS FALSE
            THEN 'UNHEALTHY'
        ELSE 'UNKNOWN'
    END AS health_state
FROM docker_services service
LEFT JOIN latest_service_health health
    ON health.service_id = service.service_id;

-- ============================================================
-- DEPENDENCY VALIDATION
-- ============================================================

CREATE OR REPLACE FUNCTION validate_service_dependencies()
RETURNS TABLE (
    service_name VARCHAR,
    dependency_name VARCHAR,
    valid BOOLEAN
)
LANGUAGE sql
AS $$
    SELECT
        child.service_name,
        parent.service_name,
        parent.deployment_state = 'healthy'
    FROM service_dependencies dependency
    JOIN docker_services child
        ON child.service_id = dependency.service_id
    JOIN docker_services parent
        ON parent.service_id = dependency.dependency_id;
$$;

-- ============================================================
-- MERGE-LIKE DEPLOYMENT ELIGIBILITY
-- ============================================================

CREATE OR REPLACE FUNCTION deployment_is_ready()
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT
        COUNT(*) = 3
        AND BOOL_AND(
            service.deployment_state = 'healthy'
            AND COALESCE(health.check_status, FALSE)
        )
        AND BOOL_AND(
            service.service_type <> 'database'
            OR service.persistent_storage
        )
        AND BOOL_AND(
            service.service_type <> 'database'
            OR NOT service.public_exposure
        )
    FROM docker_services service
    LEFT JOIN latest_service_health health
        ON health.service_id = service.service_id;
$$;

-- ============================================================
-- TASK REPORTING
-- ============================================================

CREATE OR REPLACE VIEW task_status_report AS
SELECT
    status,
    COUNT(*) AS task_count,
    MIN(created_at) AS first_created,
    MAX(updated_at) AS last_updated
FROM tasks
GROUP BY status;

-- ============================================================
-- OPERATIONAL QUERIES
-- ============================================================

-- 1. Retrieve application tasks.
SELECT *
FROM tasks
ORDER BY created_at DESC;

-- 2. Retrieve tasks and their assigned users.
SELECT
    task.title,
    task.status,
    users.username
FROM tasks task
LEFT JOIN application_users users
    ON users.user_id = task.user_id;

-- 3. Aggregate task status.
SELECT *
FROM task_status_report
ORDER BY task_count DESC;

-- 4. Inspect container service health.
SELECT *
FROM service_readiness
ORDER BY service_name;

-- 5. Validate dependency health.
SELECT *
FROM validate_service_dependencies();

-- 6. Check application deployment eligibility.
SELECT deployment_is_ready() AS deployment_ready;

-- 7. Retrieve services sharing a network.
SELECT
    network.network_name,
    ARRAY_AGG(service.service_name ORDER BY service.service_name)
        AS services
FROM service_network_memberships membership
JOIN docker_services service
    ON service.service_id = membership.service_id
JOIN docker_networks network
    ON network.network_id = membership.network_id
GROUP BY network.network_name;

-- 8. Dependency traversal using a recursive CTE.
WITH RECURSIVE dependency_tree AS (
    SELECT
        service_id,
        dependency_id,
        1 AS depth,
        ARRAY[service_id, dependency_id] AS visited
    FROM service_dependencies

    UNION ALL

    SELECT
        tree.service_id,
        dependency.dependency_id,
        tree.depth + 1,
        tree.visited || dependency.dependency_id
    FROM dependency_tree tree
    JOIN service_dependencies dependency
        ON dependency.service_id = tree.dependency_id
    WHERE NOT dependency.dependency_id = ANY(tree.visited)
)
SELECT
    root.service_name,
    dependency.service_name AS required_service,
    tree.depth
FROM dependency_tree tree
JOIN docker_services root
    ON root.service_id = tree.service_id
JOIN docker_services dependency
    ON dependency.service_id = tree.dependency_id
ORDER BY root.service_name, tree.depth;

-- ============================================================
-- TRANSACTIONAL TASK UPDATE
-- ============================================================

BEGIN;

UPDATE tasks
SET status = 'completed'
WHERE title = 'Configure Docker network'
AND status <> 'completed';

COMMIT;

-- ============================================================
-- DEPLOYMENT STATE UPDATE
-- ============================================================

-- This transaction represents a successful deployment report.
-- Health records and deployment state are separate data sources.

BEGIN;

UPDATE docker_services service
SET deployment_state = 'healthy'
WHERE service.service_name IN ('db', 'backend', 'frontend')
AND EXISTS (
    SELECT 1
    FROM latest_service_health health
    WHERE health.service_id = service.service_id
      AND health.check_status = TRUE
);

COMMIT;

-- ============================================================
-- FINAL DATABASE INSPECTION
-- ============================================================

SELECT
    service_name,
    service_type,
    deployment_state,
    persistent_storage,
    public_exposure
FROM docker_services
ORDER BY service_id;

SELECT
    status,
    COUNT(*) AS total
FROM tasks
GROUP BY status
ORDER BY status;
