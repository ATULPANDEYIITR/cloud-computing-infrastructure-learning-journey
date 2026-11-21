/*
    DOCKER COMPOSE RELATIONAL DEPLOYMENT MANAGEMENT

    PostgreSQL 14+

    Models:
    - Applications and repositories
    - Compose projects
    - Service definitions
    - Networks
    - Persistent and temporary volumes
    - Environment configuration
    - Service dependencies
    - Deployment executions
    - Container runtime states
    - Health checks
    - Resource allocation
    - Deployment eligibility
    - Audit events

    The schema represents deployment management metadata.
    It does not replace the Docker Engine or Compose CLI.
*/

BEGIN;

CREATE SCHEMA IF NOT EXISTS compose_ops;

SET search_path TO compose_ops, public;

-- =========================================================
-- 1. ENUM TYPES
-- =========================================================

CREATE TYPE service_state AS ENUM (
    'created',
    'starting',
    'running',
    'healthy',
    'unhealthy',
    'failed',
    'stopped'
);

CREATE TYPE dependency_condition AS ENUM (
    'service_started',
    'service_healthy',
    'service_completed_successfully'
);

CREATE TYPE restart_policy AS ENUM (
    'no',
    'always',
    'unless_stopped',
    'on_failure'
);

CREATE TYPE volume_type AS ENUM (
    'persistent',
    'temporary'
);

CREATE TYPE deployment_state AS ENUM (
    'pending',
    'validating',
    'deploying',
    'running',
    'failed',
    'stopped',
    'rolled_back'
);

CREATE TYPE check_state AS ENUM (
    'pending',
    'passed',
    'failed',
    'unknown'
);

-- =========================================================
-- 2. APPLICATIONS AND COMPOSE PROJECTS
-- =========================================================

CREATE TABLE applications (
    application_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    application_name VARCHAR(120) NOT NULL UNIQUE,

    description TEXT,

    owner VARCHAR(120) NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (length(trim(application_name)) > 0)
);

CREATE TABLE compose_projects (
    project_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    application_id BIGINT NOT NULL
        REFERENCES applications(application_id),

    project_name VARCHAR(120) NOT NULL,

    compose_version VARCHAR(30),

    environment_name VARCHAR(30) NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        application_id,
        project_name,
        environment_name
    )
);

-- =========================================================
-- 3. NETWORK DEFINITIONS
-- =========================================================

CREATE TABLE networks (
    network_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    project_id BIGINT NOT NULL
        REFERENCES compose_projects(project_id)
        ON DELETE CASCADE,

    network_name VARCHAR(100) NOT NULL,

    driver VARCHAR(40) NOT NULL DEFAULT 'bridge',

    internal BOOLEAN NOT NULL DEFAULT FALSE,

    attachable BOOLEAN NOT NULL DEFAULT FALSE,

    UNIQUE (project_id, network_name),

    CHECK (driver IN ('bridge', 'overlay', 'host', 'macvlan'))
);

-- =========================================================
-- 4. VOLUME DEFINITIONS
-- =========================================================

CREATE TABLE volumes (
    volume_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    project_id BIGINT NOT NULL
        REFERENCES compose_projects(project_id)
        ON DELETE CASCADE,

    volume_name VARCHAR(100) NOT NULL,

    volume_kind volume_type NOT NULL,

    driver VARCHAR(50) NOT NULL DEFAULT 'local',

    external_volume BOOLEAN NOT NULL DEFAULT FALSE,

    UNIQUE (project_id, volume_name)
);

-- =========================================================
-- 5. SERVICE DEFINITIONS
-- =========================================================

CREATE TABLE services (
    service_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    project_id BIGINT NOT NULL
        REFERENCES compose_projects(project_id)
        ON DELETE CASCADE,

    service_name VARCHAR(100) NOT NULL,

    image_reference VARCHAR(255) NOT NULL,

    memory_limit_mb INTEGER NOT NULL DEFAULT 256,

    cpu_limit NUMERIC(8, 3) NOT NULL DEFAULT 1.0,

    restart_policy restart_policy NOT NULL DEFAULT 'no',

    healthcheck_enabled BOOLEAN NOT NULL DEFAULT FALSE,

    privileged BOOLEAN NOT NULL DEFAULT FALSE,

    read_only_root_filesystem BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (project_id, service_name),

    CHECK (memory_limit_mb > 0),

    CHECK (cpu_limit > 0 AND cpu_limit <= 128),

    CHECK (length(trim(image_reference)) > 0)
);

CREATE INDEX idx_services_project
    ON services(project_id);

-- =========================================================
-- 6. SERVICE NETWORK MEMBERSHIPS
-- =========================================================

CREATE TABLE service_networks (
    service_id BIGINT NOT NULL
        REFERENCES services(service_id)
        ON DELETE CASCADE,

    network_id BIGINT NOT NULL
        REFERENCES networks(network_id)
        ON DELETE CASCADE,

    ipv4_address INET,

    PRIMARY KEY (service_id, network_id)
);

CREATE INDEX idx_service_networks_network
    ON service_networks(network_id);

-- =========================================================
-- 7. SERVICE VOLUME MOUNTS
-- =========================================================

CREATE TABLE service_volumes (
    service_id BIGINT NOT NULL
        REFERENCES services(service_id)
        ON DELETE CASCADE,

    volume_id BIGINT NOT NULL
        REFERENCES volumes(volume_id)
        ON DELETE CASCADE,

    container_path VARCHAR(255) NOT NULL,

    read_only BOOLEAN NOT NULL DEFAULT FALSE,

    PRIMARY KEY (
        service_id,
        volume_id,
        container_path
    ),

    CHECK (container_path LIKE '/%')
);

-- =========================================================
-- 8. PORT MAPPINGS
-- =========================================================

CREATE TABLE port_mappings (
    mapping_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    service_id BIGINT NOT NULL
        REFERENCES services(service_id)
        ON DELETE CASCADE,

    host_port INTEGER NOT NULL,

    container_port INTEGER NOT NULL,

    protocol VARCHAR(10) NOT NULL DEFAULT 'tcp',

    UNIQUE (service_id, container_port, protocol),

    CHECK (host_port BETWEEN 1 AND 65535),

    CHECK (container_port BETWEEN 1 AND 65535),

    CHECK (protocol IN ('tcp', 'udp'))
);

CREATE INDEX idx_port_mappings_host
    ON port_mappings(host_port);

-- =========================================================
-- 9. ENVIRONMENT CONFIGURATION
-- =========================================================

CREATE TABLE environment_variables (
    variable_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    service_id BIGINT NOT NULL
        REFERENCES services(service_id)
        ON DELETE CASCADE,

    variable_name VARCHAR(128) NOT NULL,

    variable_value TEXT,

    is_secret BOOLEAN NOT NULL DEFAULT FALSE,

    required BOOLEAN NOT NULL DEFAULT FALSE,

    UNIQUE (service_id, variable_name),

    CHECK (
        variable_name ~ '^[A-Za-z_][A-Za-z0-9_]*$'
    )
);

CREATE INDEX idx_environment_service
    ON environment_variables(service_id);

-- =========================================================
-- 10. SERVICE DEPENDENCIES
-- =========================================================

CREATE TABLE service_dependencies (
    service_id BIGINT NOT NULL
        REFERENCES services(service_id)
        ON DELETE CASCADE,

    depends_on_service_id BIGINT NOT NULL
        REFERENCES services(service_id)
        ON DELETE CASCADE,

    condition dependency_condition NOT NULL
        DEFAULT 'service_started',

    PRIMARY KEY (
        service_id,
        depends_on_service_id
    ),

    CHECK (service_id <> depends_on_service_id)
);

CREATE INDEX idx_dependencies_target
    ON service_dependencies(depends_on_service_id);

-- =========================================================
-- 11. DEPLOYMENT EXECUTIONS
-- =========================================================

CREATE TABLE deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    project_id BIGINT NOT NULL
        REFERENCES compose_projects(project_id),

    deployment_number INTEGER NOT NULL,

    state deployment_state NOT NULL DEFAULT 'pending',

    requested_by VARCHAR(120) NOT NULL,

    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    error_message TEXT,

    UNIQUE (project_id, deployment_number)
);

CREATE INDEX idx_deployments_project_date
    ON deployments(project_id, requested_at DESC);

CREATE INDEX idx_deployments_state
    ON deployments(state);

-- =========================================================
-- 12. CONTAINER RUNTIME INSTANCES
-- =========================================================

CREATE TABLE container_instances (
    instance_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id)
        ON DELETE CASCADE,

    service_id BIGINT NOT NULL
        REFERENCES services(service_id),

    container_identifier VARCHAR(128),

    state service_state NOT NULL DEFAULT 'created',

    started_at TIMESTAMPTZ,

    stopped_at TIMESTAMPTZ,

    restart_count INTEGER NOT NULL DEFAULT 0,

    UNIQUE (deployment_id, service_id),

    CHECK (restart_count >= 0)
);

CREATE INDEX idx_instances_deployment_state
    ON container_instances(deployment_id, state);

-- =========================================================
-- 13. HEALTH CHECK RESULTS
-- =========================================================

CREATE TABLE health_checks (
    health_check_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    instance_id BIGINT NOT NULL
        REFERENCES container_instances(instance_id)
        ON DELETE CASCADE,

    check_state check_state NOT NULL,

    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    response_time_ms INTEGER,

    failure_reason TEXT,

    CHECK (
        response_time_ms IS NULL OR response_time_ms >= 0
    )
);

CREATE INDEX idx_health_instance_date
    ON health_checks(instance_id, checked_at DESC);

-- =========================================================
-- 14. DEPLOYMENT AUDIT
-- =========================================================

CREATE TABLE deployment_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id)
        ON DELETE CASCADE,

    service_id BIGINT
        REFERENCES services(service_id),

    event_type VARCHAR(80) NOT NULL,

    event_details JSONB NOT NULL DEFAULT '{}'::JSONB,

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_deployment_date
    ON deployment_events(deployment_id, occurred_at);

CREATE INDEX idx_events_details
    ON deployment_events USING GIN(event_details);

-- =========================================================
-- 15. RESOURCE CAPACITY
-- =========================================================

CREATE TABLE deployment_hosts (
    host_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    host_name VARCHAR(120) NOT NULL UNIQUE,

    available_memory_mb INTEGER NOT NULL,

    available_cpu NUMERIC(8, 3) NOT NULL,

    CHECK (available_memory_mb > 0),

    CHECK (available_cpu > 0)
);

-- =========================================================
-- 16. INTEGRITY TRIGGERS
-- =========================================================

-- Dependencies must connect services belonging to the same project.

CREATE OR REPLACE FUNCTION validate_dependency_project()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    source_project BIGINT;
    target_project BIGINT;
BEGIN
    SELECT project_id
    INTO source_project
    FROM services
    WHERE service_id = NEW.service_id;

    SELECT project_id
    INTO target_project
    FROM services
    WHERE service_id = NEW.depends_on_service_id;

    IF source_project IS DISTINCT FROM target_project THEN
        RAISE EXCEPTION
            'Service dependencies cannot cross Compose projects';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_dependency_project
BEFORE INSERT OR UPDATE
ON service_dependencies
FOR EACH ROW
EXECUTE FUNCTION validate_dependency_project();


-- Network membership must belong to the same project.

CREATE OR REPLACE FUNCTION validate_network_project()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    service_project BIGINT;
    network_project BIGINT;
BEGIN
    SELECT project_id
    INTO service_project
    FROM services
    WHERE service_id = NEW.service_id;

    SELECT project_id
    INTO network_project
    FROM networks
    WHERE network_id = NEW.network_id;

    IF service_project IS DISTINCT FROM network_project THEN
        RAISE EXCEPTION
            'Service and network must belong to the same project';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_network_project
BEFORE INSERT OR UPDATE
ON service_networks
FOR EACH ROW
EXECUTE FUNCTION validate_network_project();


-- Volumes must belong to the same project as the service.

CREATE OR REPLACE FUNCTION validate_volume_project()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    service_project BIGINT;
    volume_project BIGINT;
BEGIN
    SELECT project_id
    INTO service_project
    FROM services
    WHERE service_id = NEW.service_id;

    SELECT project_id
    INTO volume_project
    FROM volumes
    WHERE volume_id = NEW.volume_id;

    IF service_project IS DISTINCT FROM volume_project THEN
        RAISE EXCEPTION
            'Service and volume must belong to the same project';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_volume_project
BEFORE INSERT OR UPDATE
ON service_volumes
FOR EACH ROW
EXECUTE FUNCTION validate_volume_project();


-- Environment variables cannot be changed to null when required.

CREATE OR REPLACE FUNCTION validate_required_environment()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.required AND (
        NEW.variable_value IS NULL OR
        length(trim(NEW.variable_value)) = 0
    ) THEN
        RAISE EXCEPTION
            'Required environment variable % is empty',
            NEW.variable_name;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_required_environment
BEFORE INSERT OR UPDATE
ON environment_variables
FOR EACH ROW
EXECUTE FUNCTION validate_required_environment();


-- =========================================================
-- 17. CONFIGURATION VALIDATION FUNCTION
-- =========================================================

CREATE OR REPLACE FUNCTION validate_compose_project(
    p_project_id BIGINT
)
RETURNS TABLE (
    check_name TEXT,
    passed BOOLEAN,
    details TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM compose_projects
        WHERE project_id = p_project_id
    ) THEN
        RAISE EXCEPTION
            'Unknown project: %', p_project_id;
    END IF;

    RETURN QUERY
    SELECT
        'service_exists'::TEXT,
        COUNT(*) > 0,
        'At least one service must exist'::TEXT
    FROM services
    WHERE project_id = p_project_id;

    RETURN QUERY
    SELECT
        'environment_complete'::TEXT,
        COUNT(*) = 0,
        'All required environment variables must be populated'::TEXT
    FROM environment_variables e
    JOIN services s
        ON s.service_id = e.service_id
    WHERE s.project_id = p_project_id
      AND e.required
      AND (
          e.variable_value IS NULL
          OR length(trim(e.variable_value)) = 0
      );

    RETURN QUERY
    SELECT
        'network_configured'::TEXT,
        COUNT(*) = 0,
        'Each service must have a network membership'::TEXT
    FROM services s
    WHERE s.project_id = p_project_id
      AND NOT EXISTS (
          SELECT 1
          FROM service_networks sn
          WHERE sn.service_id = s.service_id
      );

    RETURN QUERY
    SELECT
        'dependency_valid'::TEXT,
        COUNT(*) = 0,
        'All dependencies must belong to the project'::TEXT
    FROM service_dependencies d
    JOIN services source_service
        ON source_service.service_id = d.service_id
    JOIN services target_service
        ON target_service.service_id = d.depends_on_service_id
    WHERE source_service.project_id = p_project_id
      AND source_service.project_id <>
          target_service.project_id;

    RETURN QUERY
    SELECT
        'privileged_configuration'::TEXT,
        COUNT(*) = 0,
        'Privileged containers require explicit security review'::TEXT
    FROM services
    WHERE project_id = p_project_id
      AND privileged;
END;
$$;

-- =========================================================
-- 18. RESOURCE ELIGIBILITY VIEW
-- =========================================================

CREATE OR REPLACE VIEW project_resource_requirements AS
SELECT
    p.project_id,
    p.project_name,

    COALESCE(SUM(s.memory_limit_mb), 0)
        AS required_memory_mb,

    COALESCE(SUM(s.cpu_limit), 0)
        AS required_cpu,

    COUNT(s.service_id)
        AS service_count

FROM compose_projects p

LEFT JOIN services s
    ON s.project_id = p.project_id

GROUP BY
    p.project_id,
    p.project_name;

-- =========================================================
-- 19. DEPLOYMENT ELIGIBILITY FUNCTION
-- =========================================================

CREATE OR REPLACE FUNCTION check_deployment_eligibility(
    p_project_id BIGINT,
    p_host_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    required_memory_mb BIGINT,
    available_memory_mb INTEGER,
    required_cpu NUMERIC,
    available_cpu NUMERIC,
    failure_reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    requirements RECORD;
    host RECORD;
    reason TEXT := '';
BEGIN
    SELECT *
    INTO requirements
    FROM project_resource_requirements
    WHERE project_id = p_project_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Unknown project: %', p_project_id;
    END IF;

    SELECT *
    INTO host
    FROM deployment_hosts
    WHERE host_id = p_host_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Unknown deployment host: %', p_host_id;
    END IF;

    IF requirements.service_count = 0 THEN
        reason := reason || 'No services configured; ';
    END IF;

    IF requirements.required_memory_mb >
       host.available_memory_mb THEN
        reason := reason || 'Insufficient memory; ';
    END IF;

    IF requirements.required_cpu >
       host.available_cpu THEN
        reason := reason || 'Insufficient CPU; ';
    END IF;

    RETURN QUERY
    SELECT
        reason = '',
        requirements.required_memory_mb::BIGINT,
        host.available_memory_mb,
        requirements.required_cpu,
        host.available_cpu,
        NULLIF(reason, '');
END;
$$;

-- =========================================================
-- 20. DEPLOYMENT CREATION PROCEDURE
-- =========================================================

CREATE OR REPLACE PROCEDURE create_deployment(
    p_project_id BIGINT,
    p_deployment_number INTEGER,
    p_requested_by VARCHAR(120),
    p_host_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    new_deployment_id BIGINT;
    eligibility RECORD;
    validation_failure BOOLEAN;
BEGIN
    IF p_deployment_number <= 0 THEN
        RAISE EXCEPTION
            'Deployment number must be positive';
    END IF;

    IF p_requested_by IS NULL OR
       length(trim(p_requested_by)) = 0 THEN
        RAISE EXCEPTION
            'Requested by is required';
    END IF;

    SELECT *
    INTO eligibility
    FROM check_deployment_eligibility(
        p_project_id,
        p_host_id
    );

    IF NOT eligibility.eligible THEN
        RAISE EXCEPTION
            'Deployment rejected: %',
            eligibility.failure_reason;
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM validate_compose_project(p_project_id)
        WHERE NOT passed
    )
    INTO validation_failure;

    IF validation_failure THEN
        RAISE EXCEPTION
            'Compose project configuration validation failed';
    END IF;

    INSERT INTO deployments (
        project_id,
        deployment_number,
        state,
        requested_by
    )
    VALUES (
        p_project_id,
        p_deployment_number,
        'validating',
        p_requested_by
    )
    RETURNING deployment_id
    INTO new_deployment_id;

    UPDATE deployments
    SET
        state = 'deploying',
        started_at = NOW()
    WHERE deployment_id = new_deployment_id;

    INSERT INTO container_instances (
        deployment_id,
        service_id,
        state
    )
    SELECT
        new_deployment_id,
        service_id,
        'created'
    FROM services
    WHERE project_id = p_project_id;

    INSERT INTO deployment_events (
        deployment_id,
        event_type,
        event_details
    )
    VALUES (
        new_deployment_id,
        'DEPLOYMENT_CREATED',
        jsonb_build_object(
            'requested_by', p_requested_by,
            'host_id', p_host_id
        )
    );

    RAISE NOTICE
        'Deployment % created',
        new_deployment_id;
END;
$$;

-- =========================================================
-- 21. SAMPLE APPLICATION AND PROJECT
-- =========================================================

INSERT INTO applications (
    application_name,
    description,
    owner
)
VALUES (
    'Inventory Platform',
    'Multi-container inventory management application',
    'Platform Engineering'
);

INSERT INTO compose_projects (
    application_id,
    project_name,
    compose_version,
    environment_name
)
SELECT
    application_id,
    'inventory-stack',
    '2.30',
    'development'
FROM applications
WHERE application_name = 'Inventory Platform';

-- =========================================================
-- 22. SAMPLE NETWORKS
-- =========================================================

INSERT INTO networks (
    project_id,
    network_name,
    driver,
    internal
)
SELECT
    project_id,
    'frontend',
    'bridge',
    FALSE
FROM compose_projects
WHERE project_name = 'inventory-stack';

INSERT INTO networks (
    project_id,
    network_name,
    driver,
    internal
)
SELECT
    project_id,
    'backend',
    'bridge',
    TRUE
FROM compose_projects
WHERE project_name = 'inventory-stack';

-- =========================================================
-- 23. SAMPLE VOLUMES
-- =========================================================

INSERT INTO volumes (
    project_id,
    volume_name,
    volume_kind
)
SELECT
    project_id,
    'postgres_data',
    'persistent'
FROM compose_projects
WHERE project_name = 'inventory-stack';

INSERT INTO volumes (
    project_id,
    volume_name,
    volume_kind
)
SELECT
    project_id,
    'redis_data',
    'persistent'
FROM compose_projects
WHERE project_name = 'inventory-stack';

-- =========================================================
-- 24. SAMPLE SERVICES
-- =========================================================

INSERT INTO services (
    project_id,
    service_name,
    image_reference,
    memory_limit_mb,
    cpu_limit,
    restart_policy,
    healthcheck_enabled,
    privileged,
    read_only_root_filesystem
)
SELECT
    project_id,
    'database',
    'postgres:18',
    1024,
    2.0,
    'unless-stopped',
    TRUE,
    FALSE,
    FALSE
FROM compose_projects
WHERE project_name = 'inventory-stack';

INSERT INTO services (
    project_id,
    service_name,
    image_reference,
    memory_limit_mb,
    cpu_limit,
    restart_policy,
    healthcheck_enabled
)
SELECT
    project_id,
    'cache',
    'redis:7-alpine',
    256,
    0.5,
    'unless-stopped',
    TRUE
FROM compose_projects
WHERE project_name = 'inventory-stack';

INSERT INTO services (
    project_id,
    service_name,
    image_reference,
    memory_limit_mb,
    cpu_limit,
    restart_policy,
    healthcheck_enabled,
    read_only_root_filesystem
)
SELECT
    project_id,
    'api',
    'example/inventory-api:1.0',
    512,
    1.5,
    'on_failure',
    TRUE,
    TRUE
FROM compose_projects
WHERE project_name = 'inventory-stack';

INSERT INTO services (
    project_id,
    service_name,
    image_reference,
    memory_limit_mb,
    cpu_limit,
    restart_policy
)
SELECT
    project_id,
    'web',
    'example/inventory-web:1.0',
    256,
    1.0,
    'unless-stopped'
FROM compose_projects
WHERE project_name = 'inventory-stack';

-- =========================================================
-- 25. NETWORK MEMBERSHIPS
-- =========================================================

INSERT INTO service_networks (
    service_id,
    network_id
)
SELECT
    s.service_id,
    n.network_id
FROM services s
JOIN networks n
    ON n.project_id = s.project_id
WHERE s.project_id = (
    SELECT project_id
    FROM compose_projects
    WHERE project_name = 'inventory-stack'
)
AND (
    (s.service_name = 'database' AND n.network_name = 'backend')
    OR
    (s.service_name = 'cache' AND n.network_name = 'backend')
    OR
    (s.service_name = 'api' AND n.network_name IN (
        'frontend', 'backend'
    ))
    OR
    (s.service_name = 'web' AND n.network_name = 'frontend')
);

-- =========================================================
-- 26. VOLUME MOUNTS
-- =========================================================

INSERT INTO service_volumes (
    service_id,
    volume_id,
    container_path,
    read_only
)
SELECT
    s.service_id,
    v.volume_id,
    '/var/lib/postgresql/data',
    FALSE
FROM services s
JOIN volumes v
    ON v.project_id = s.project_id
WHERE s.service_name = 'database'
  AND v.volume_name = 'postgres_data';

INSERT INTO service_volumes (
    service_id,
    volume_id,
    container_path,
    read_only
)
SELECT
    s.service_id,
    v.volume_id,
    '/data',
    FALSE
FROM services s
JOIN volumes v
    ON v.project_id = s.project_id
WHERE s.service_name = 'cache'
  AND v.volume_name = 'redis_data';

-- =========================================================
-- 27. PORT MAPPINGS
-- =========================================================

INSERT INTO port_mappings (
    service_id,
    host_port,
    container_port
)
SELECT service_id, 8080, 8080
FROM services
WHERE service_name = 'api';

INSERT INTO port_mappings (
    service_id,
    host_port,
    container_port
)
SELECT service_id, 3000, 3000
FROM services
WHERE service_name = 'web';

-- =========================================================
-- 28. ENVIRONMENT VARIABLES
-- =========================================================

INSERT INTO environment_variables (
    service_id,
    variable_name,
    variable_value,
    required,
    is_secret
)
SELECT
    service_id,
    'POSTGRES_DB',
    'inventory',
    TRUE,
    FALSE
FROM services
WHERE service_name = 'database';

INSERT INTO environment_variables (
    service_id,
    variable_name,
    variable_value,
    required,
    is_secret
)
SELECT
    service_id,
    'POSTGRES_USER',
    'inventory_user',
    TRUE,
    FALSE
FROM services
WHERE service_name = 'database';

INSERT INTO environment_variables (
    service_id,
    variable_name,
    variable_value,
    required,
    is_secret
)
SELECT
    service_id,
    'POSTGRES_PASSWORD',
    'development-only-secret',
    TRUE,
    TRUE
FROM services
WHERE service_name = 'database';

INSERT INTO environment_variables (
    service_id,
    variable_name,
    variable_value,
    required
)
SELECT
    service_id,
    'DATABASE_HOST',
    'database',
    TRUE
FROM services
WHERE service_name = 'api';

INSERT INTO environment_variables (
    service_id,
    variable_name,
    variable_value,
    required
)
SELECT
    service_id,
    'CACHE_HOST',
    'cache',
    TRUE
FROM services
WHERE service_name = 'api';

INSERT INTO environment_variables (
    service_id,
    variable_name,
    variable_value,
    required
)
SELECT
    service_id,
    'API_BASE_URL',
    'http://api:8080',
    TRUE
FROM services
WHERE service_name = 'web';

-- =========================================================
-- 29. DEPENDENCY RELATIONSHIPS
-- =========================================================

INSERT INTO service_dependencies (
    service_id,
    depends_on_service_id,
    condition
)
SELECT
    api.service_id,
    db.service_id,
    'service_healthy'
FROM services api
JOIN services db
    ON db.project_id = api.project_id
WHERE api.service_name = 'api'
  AND db.service_name = 'database';

INSERT INTO service_dependencies (
    service_id,
    depends_on_service_id,
    condition
)
SELECT
    api.service_id,
    cache.service_id,
    'service_started'
FROM services api
JOIN services cache
    ON cache.project_id = api.project_id
WHERE api.service_name = 'api'
  AND cache.service_name = 'cache';

INSERT INTO service_dependencies (
    service_id,
    depends_on_service_id,
    condition
)
SELECT
    web.service_id,
    api.service_id,
    'service_healthy'
FROM services web
JOIN services api
    ON api.project_id = web.project_id
WHERE web.service_name = 'web'
  AND api.service_name = 'api';

-- =========================================================
-- 30. DEPLOYMENT HOST
-- =========================================================

INSERT INTO deployment_hosts (
    host_name,
    available_memory_mb,
    available_cpu
)
VALUES (
    'development-host-01',
    8192,
    8.0
);

-- =========================================================
-- 31. CONFIGURATION VALIDATION REPORT
-- =========================================================

SELECT *
FROM validate_compose_project(
    (
        SELECT project_id
        FROM compose_projects
        WHERE project_name = 'inventory-stack'
    )
);

-- =========================================================
-- 32. RESOURCE AGGREGATION
-- =========================================================

SELECT
    project_name,
    service_count,
    required_memory_mb,
    required_cpu
FROM project_resource_requirements
WHERE project_name = 'inventory-stack';

-- =========================================================
-- 33. NETWORK CONNECTIVITY REPORT
-- =========================================================

SELECT
    s.service_name,
    n.network_name,
    n.internal
FROM service_networks sn
JOIN services s
    ON s.service_id = sn.service_id
JOIN networks n
    ON n.network_id = sn.network_id
ORDER BY s.service_name, n.network_name;

-- =========================================================
-- 34. DEPENDENCY REPORT
-- =========================================================

SELECT
    source.service_name AS service,
    target.service_name AS dependency,
    d.condition
FROM service_dependencies d
JOIN services source
    ON source.service_id = d.service_id
JOIN services target
    ON target.service_id = d.depends_on_service_id
ORDER BY source.service_name;

-- =========================================================
-- 35. SECRET CONFIGURATION REPORT
-- =========================================================

SELECT
    s.service_name,
    e.variable_name,
    e.is_secret,
    CASE
        WHEN e.is_secret THEN '[REDACTED]'
        ELSE e.variable_value
    END AS displayed_value
FROM environment_variables e
JOIN services s
    ON s.service_id = e.service_id
ORDER BY s.service_name, e.variable_name;

-- =========================================================
-- 36. DEPLOYMENT ELIGIBILITY
-- =========================================================

SELECT *
FROM check_deployment_eligibility(
    (
        SELECT project_id
        FROM compose_projects
        WHERE project_name = 'inventory-stack'
    ),
    (
        SELECT host_id
        FROM deployment_hosts
        WHERE host_name = 'development-host-01'
    )
);

-- =========================================================
-- 37. CREATE DEPLOYMENT TRANSACTION
-- =========================================================

CALL create_deployment(
    (
        SELECT project_id
        FROM compose_projects
        WHERE project_name = 'inventory-stack'
    ),
    1,
    'platform-engineer',
    (
        SELECT host_id
        FROM deployment_hosts
        WHERE host_name = 'development-host-01'
    )
);

-- =========================================================
-- 38. SIMULATED CONTAINER STARTUP
-- =========================================================

UPDATE container_instances ci
SET
    state = 'running',
    started_at = NOW()
FROM services s
WHERE ci.service_id = s.service_id
  AND ci.deployment_id = (
      SELECT MAX(deployment_id)
      FROM deployments
  )
  AND s.service_name IN ('database', 'cache');

-- Record database health result.

INSERT INTO health_checks (
    instance_id,
    check_state,
    response_time_ms
)
SELECT
    ci.instance_id,
    'passed',
    12
FROM container_instances ci
JOIN services s
    ON s.service_id = ci.service_id
WHERE ci.deployment_id = (
    SELECT MAX(deployment_id)
    FROM deployments
)
AND s.service_name = 'database';

UPDATE container_instances ci
SET state = 'healthy'
FROM services s
WHERE ci.service_id = s.service_id
  AND ci.deployment_id = (
      SELECT MAX(deployment_id)
      FROM deployments
  )
  AND s.service_name = 'database';

UPDATE container_instances ci
SET
    state = 'running',
    started_at = NOW()
FROM services s
WHERE ci.service_id = s.service_id
  AND ci.deployment_id = (
      SELECT MAX(deployment_id)
      FROM deployments
  )
  AND s.service_name = 'api';

UPDATE container_instances ci
SET state = 'healthy'
FROM services s
WHERE ci.service_id = s.service_id
  AND ci.deployment_id = (
      SELECT MAX(deployment_id)
      FROM deployments
  )
  AND s.service_name = 'api';

UPDATE container_instances ci
SET
    state = 'running',
    started_at = NOW()
FROM services s
WHERE ci.service_id = s.service_id
  AND ci.deployment_id = (
      SELECT MAX(deployment_id)
      FROM deployments
  )
  AND s.service_name = 'web';

-- =========================================================
-- 39. DEPLOYMENT STATUS
-- =========================================================

UPDATE deployments
SET
    state = 'running'
WHERE deployment_id = (
    SELECT MAX(deployment_id)
    FROM deployments
);

INSERT INTO deployment_events (
    deployment_id,
    event_type,
    event_details
)
SELECT
    deployment_id,
    'DEPLOYMENT_RUNNING',
    jsonb_build_object(
        'service_count',
        (
            SELECT COUNT(*)
            FROM container_instances ci
            WHERE ci.deployment_id = deployments.deployment_id
        )
    )
FROM deployments
WHERE deployment_id = (
    SELECT MAX(deployment_id)
    FROM deployments
);

-- =========================================================
-- 40. FAILURE DETECTION
-- =========================================================

SELECT
    s.service_name,
    ci.state,
    ci.restart_count
FROM container_instances ci
JOIN services s
    ON s.service_id = ci.service_id
WHERE ci.deployment_id = (
    SELECT MAX(deployment_id)
    FROM deployments
)
AND ci.state IN ('failed', 'unhealthy');

-- =========================================================
-- 41. DEPLOYMENT REPORTING
-- =========================================================

SELECT
    d.deployment_id,
    cp.project_name,
    d.deployment_number,
    d.state,
    d.requested_by,
    d.requested_at,
    COUNT(ci.instance_id) AS container_count,

    COUNT(*) FILTER (
        WHERE ci.state = 'healthy'
    ) AS healthy_containers,

    COUNT(*) FILTER (
        WHERE ci.state = 'failed'
    ) AS failed_containers

FROM deployments d

JOIN compose_projects cp
    ON cp.project_id = d.project_id

LEFT JOIN container_instances ci
    ON ci.deployment_id = d.deployment_id

GROUP BY
    d.deployment_id,
    cp.project_name,
    d.deployment_number,
    d.state,
    d.requested_by,
    d.requested_at;

-- =========================================================
-- 42. HEALTH HISTORY
-- =========================================================

SELECT
    s.service_name,
    h.check_state,
    h.response_time_ms,
    h.checked_at
FROM health_checks h
JOIN container_instances ci
    ON ci.instance_id = h.instance_id
JOIN services s
    ON s.service_id = ci.service_id
ORDER BY h.checked_at DESC;

-- =========================================================
-- 43. SERVICE STARTUP ORDER REPORT
-- =========================================================

WITH RECURSIVE dependency_tree AS (
    SELECT
        service_id,
        depends_on_service_id,
        1 AS depth,
        ARRAY[service_id, depends_on_service_id] AS path
    FROM service_dependencies

    UNION ALL

    SELECT
        d.service_id,
        d.depends_on_service_id,
        tree.depth + 1,
        tree.path || d.depends_on_service_id
    FROM dependency_tree tree
    JOIN service_dependencies d
        ON d.service_id = tree.depends_on_service_id
    WHERE NOT d.depends_on_service_id = ANY(tree.path)
)
SELECT
    source.service_name,
    target.service_name AS dependency,
    MAX(tree.depth) AS dependency_depth
FROM dependency_tree tree
JOIN services source
    ON source.service_id = tree.service_id
JOIN services target
    ON target.service_id = tree.depends_on_service_id
GROUP BY
    source.service_name,
    target.service_name
ORDER BY
    dependency_depth DESC,
    source.service_name;

-- =========================================================
-- 44. PERSISTENT DATA PROTECTION REPORT
-- =========================================================

SELECT
    s.service_name,
    v.volume_name,
    v.volume_kind,
    sv.container_path,
    sv.read_only,
    CASE
        WHEN v.volume_kind = 'persistent'
            THEN 'DATA RETAINED ACROSS CONTAINER RECREATION'
        ELSE 'TEMPORARY DATA'
    END AS persistence_behavior
FROM service_volumes sv
JOIN services s
    ON s.service_id = sv.service_id
JOIN volumes v
    ON v.volume_id = sv.volume_id;

-- =========================================================
-- 45. SHUTDOWN TRANSACTION
-- =========================================================

BEGIN;

UPDATE container_instances
SET
    state = 'stopped',
    stopped_at = NOW()
WHERE deployment_id = (
    SELECT MAX(deployment_id)
    FROM deployments
)
AND state NOT IN ('stopped');

UPDATE deployments
SET
    state = 'stopped',
    completed_at = NOW()
WHERE deployment_id = (
    SELECT MAX(deployment_id)
    FROM deployments
);

INSERT INTO deployment_events (
    deployment_id,
    event_type,
    event_details
)
SELECT
    deployment_id,
    'DEPLOYMENT_STOPPED',
    jsonb_build_object(
        'persistent_volumes_preserved',
        TRUE
    )
FROM deployments
WHERE deployment_id = (
    SELECT MAX(deployment_id)
    FROM deployments
);

COMMIT;

-- Persistent volume records remain available.
-- Container shutdown does not imply volume deletion.

COMMIT;
