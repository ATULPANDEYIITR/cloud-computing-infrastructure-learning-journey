-- ============================================================
-- DOCKER STORAGE AND VOLUMES
-- PostgreSQL 15+
--
-- Relational model for:
-- repositories of storage resources, named volumes,
-- containers, mount configurations, lifecycle events,
-- backups, retention policies, and storage reporting.
--
-- Run in a dedicated database or schema.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS docker_storage;

SET search_path TO docker_storage, public;

-- ------------------------------------------------------------
-- ENUMERATED DOMAIN TYPES
-- ------------------------------------------------------------

CREATE TYPE mount_type AS ENUM (
    'volume',
    'bind',
    'tmpfs'
);

CREATE TYPE volume_state AS ENUM (
    'available',
    'in_use',
    'removed'
);

CREATE TYPE container_state AS ENUM (
    'created',
    'running',
    'stopped',
    'removed'
);

CREATE TYPE storage_event_type AS ENUM (
    'created',
    'attached',
    'detached',
    'written',
    'backed_up',
    'restored',
    'removed',
    'pruned'
);

CREATE TYPE backup_state AS ENUM (
    'pending',
    'completed',
    'failed'
);

-- ------------------------------------------------------------
-- USERS AND STORAGE ENVIRONMENTS
-- ------------------------------------------------------------

CREATE TABLE storage_users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    role VARCHAR(30) NOT NULL CHECK (
        role IN ('administrator', 'operator', 'developer', 'auditor')
    ),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE storage_environments (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_name VARCHAR(80) NOT NULL UNIQUE,
    description TEXT,
    retention_days INTEGER NOT NULL DEFAULT 30 CHECK (
        retention_days BETWEEN 1 AND 3650
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- VOLUMES
-- ------------------------------------------------------------

CREATE TABLE volumes (
    volume_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    volume_name VARCHAR(64) NOT NULL UNIQUE,
    driver VARCHAR(100) NOT NULL DEFAULT 'local',
    environment_id BIGINT NOT NULL
        REFERENCES storage_environments(environment_id),
    owner_id BIGINT NOT NULL
        REFERENCES storage_users(user_id),
    state volume_state NOT NULL DEFAULT 'available',
    labels JSONB NOT NULL DEFAULT '{}'::JSONB,
    options JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    removed_at TIMESTAMPTZ,

    CONSTRAINT valid_volume_name CHECK (
        volume_name ~ '^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$'
    ),

    CONSTRAINT valid_labels CHECK (
        jsonb_typeof(labels) = 'object'
    ),

    CONSTRAINT valid_options CHECK (
        jsonb_typeof(options) = 'object'
    ),

    CONSTRAINT valid_removal_state CHECK (
        (state = 'removed' AND removed_at IS NOT NULL)
        OR
        (state <> 'removed' AND removed_at IS NULL)
    )
);

CREATE INDEX idx_volumes_environment_state
    ON volumes(environment_id, state);

CREATE INDEX idx_volumes_created
    ON volumes(created_at DESC);

CREATE INDEX idx_volumes_labels
    ON volumes USING GIN(labels);

-- ------------------------------------------------------------
-- CONTAINERS
-- ------------------------------------------------------------

CREATE TABLE containers (
    container_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    container_name VARCHAR(100) NOT NULL UNIQUE,
    image_name VARCHAR(255) NOT NULL,
    environment_id BIGINT NOT NULL
        REFERENCES storage_environments(environment_id),
    state container_state NOT NULL DEFAULT 'created',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ
);

CREATE INDEX idx_containers_environment_state
    ON containers(environment_id, state);

-- ------------------------------------------------------------
-- MOUNT CONFIGURATION
-- ------------------------------------------------------------

CREATE TABLE mounts (
    mount_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    container_id BIGINT NOT NULL
        REFERENCES containers(container_id),
    volume_id BIGINT
        REFERENCES volumes(volume_id),
    type mount_type NOT NULL,
    source TEXT NOT NULL,
    destination TEXT NOT NULL,
    read_only BOOLEAN NOT NULL DEFAULT FALSE,
    propagation VARCHAR(30) NOT NULL DEFAULT 'rprivate',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_container_destination
        UNIQUE(container_id, destination),

    CONSTRAINT valid_destination CHECK (
        destination LIKE '/%'
        AND destination NOT LIKE '%/../%'
        AND destination NOT LIKE '%/..'
    ),

    CONSTRAINT valid_mount_source CHECK (
        LENGTH(source) > 0
    ),

    CONSTRAINT valid_mount_reference CHECK (
        (type = 'volume' AND volume_id IS NOT NULL)
        OR
        (type IN ('bind', 'tmpfs') AND volume_id IS NULL)
    ),

    CONSTRAINT valid_bind_source CHECK (
        type <> 'bind' OR source LIKE '/%'
    ),

    CONSTRAINT valid_tmpfs_source CHECK (
        type <> 'tmpfs' OR source = 'tmpfs'
    )
);

CREATE INDEX idx_mounts_volume
    ON mounts(volume_id)
    WHERE volume_id IS NOT NULL;

CREATE INDEX idx_mounts_container
    ON mounts(container_id);

-- ------------------------------------------------------------
-- BACKUPS
-- ------------------------------------------------------------

CREATE TABLE volume_backups (
    backup_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    volume_id BIGINT NOT NULL REFERENCES volumes(volume_id),
    backup_name VARCHAR(255) NOT NULL,
    storage_location TEXT NOT NULL,
    checksum VARCHAR(128),
    backup_size_bytes BIGINT CHECK (
        backup_size_bytes IS NULL OR backup_size_bytes >= 0
    ),
    state backup_state NOT NULL DEFAULT 'pending',
    initiated_by BIGINT NOT NULL REFERENCES storage_users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    UNIQUE(volume_id, backup_name),

    CONSTRAINT valid_backup_completion CHECK (
        (state = 'completed' AND completed_at IS NOT NULL)
        OR
        (state <> 'completed' AND completed_at IS NULL)
    )
);

CREATE INDEX idx_backups_volume_date
    ON volume_backups(volume_id, created_at DESC);

-- ------------------------------------------------------------
-- STORAGE AUDIT EVENTS
-- ------------------------------------------------------------

CREATE TABLE storage_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    volume_id BIGINT REFERENCES volumes(volume_id),
    container_id BIGINT REFERENCES containers(container_id),
    actor_id BIGINT REFERENCES storage_users(user_id),
    event_type storage_event_type NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_volume_time
    ON storage_events(volume_id, occurred_at DESC);

CREATE INDEX idx_events_type_time
    ON storage_events(event_type, occurred_at DESC);

CREATE INDEX idx_events_details
    ON storage_events USING GIN(details);

-- ------------------------------------------------------------
-- AUTOMATIC MOUNT VALIDATION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_volume_mount()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    current_volume volumes%ROWTYPE;
BEGIN
    IF NEW.type = 'volume' THEN
        SELECT *
        INTO current_volume
        FROM volumes
        WHERE volume_id = NEW.volume_id
        FOR UPDATE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Referenced volume does not exist';
        END IF;

        IF current_volume.state = 'removed' THEN
            RAISE EXCEPTION 'Cannot mount a removed volume';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM containers c
            WHERE c.container_id = NEW.container_id
              AND c.environment_id = current_volume.environment_id
        ) THEN
            RAISE EXCEPTION
                'Container and volume environments do not match';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_volume_mount
BEFORE INSERT OR UPDATE ON mounts
FOR EACH ROW
EXECUTE FUNCTION validate_volume_mount();

-- ------------------------------------------------------------
-- AUTOMATIC VOLUME STATE MANAGEMENT
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION refresh_volume_state()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    affected_volume BIGINT;
BEGIN
    affected_volume := COALESCE(NEW.volume_id, OLD.volume_id);

    IF affected_volume IS NOT NULL THEN
        UPDATE volumes v
        SET state = CASE
            WHEN EXISTS (
                SELECT 1
                FROM mounts m
                JOIN containers c
                  ON c.container_id = m.container_id
                WHERE m.volume_id = affected_volume
                  AND m.type = 'volume'
                  AND c.state <> 'removed'
            )
            THEN 'in_use'::volume_state
            ELSE 'available'::volume_state
        END
        WHERE v.volume_id = affected_volume
          AND v.state <> 'removed';
    END IF;

    RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE TRIGGER trg_mount_volume_state
AFTER INSERT OR UPDATE OR DELETE ON mounts
FOR EACH ROW
EXECUTE FUNCTION refresh_volume_state();

-- ------------------------------------------------------------
-- CONTAINER STATE CHANGE VALIDATION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_container_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.state = 'removed' AND NEW.state <> 'removed' THEN
        RAISE EXCEPTION 'Removed containers cannot be restarted';
    END IF;

    IF NEW.state = 'running' AND NEW.started_at IS NULL THEN
        NEW.started_at := NOW();
    END IF;

    IF NEW.state IN ('stopped', 'removed') THEN
        NEW.stopped_at := NOW();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_container_transition
BEFORE UPDATE ON containers
FOR EACH ROW
EXECUTE FUNCTION validate_container_transition();

-- ------------------------------------------------------------
-- VOLUME DELETION GUARD
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION prevent_volume_removal_in_use()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = 'removed' AND OLD.state <> 'removed' THEN
        IF EXISTS (
            SELECT 1
            FROM mounts m
            JOIN containers c
              ON c.container_id = m.container_id
            WHERE m.volume_id = OLD.volume_id
              AND c.state <> 'removed'
        ) THEN
            RAISE EXCEPTION
                'Volume is referenced by an active container';
        END IF;

        NEW.removed_at := NOW();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_prevent_volume_removal
BEFORE UPDATE OF state ON volumes
FOR EACH ROW
EXECUTE FUNCTION prevent_volume_removal_in_use();

-- ------------------------------------------------------------
-- STORAGE REPORTING VIEW
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW volume_inventory AS
SELECT
    v.volume_id,
    v.volume_name,
    v.driver,
    e.environment_name,
    u.username AS owner,
    v.state,
    COUNT(DISTINCT m.container_id) FILTER (
        WHERE c.state <> 'removed'
    ) AS attached_containers,
    COUNT(DISTINCT b.backup_id) FILTER (
        WHERE b.state = 'completed'
    ) AS completed_backups,
    MAX(b.completed_at) AS last_backup,
    v.created_at
FROM volumes v
JOIN storage_environments e
    ON e.environment_id = v.environment_id
JOIN storage_users u
    ON u.user_id = v.owner_id
LEFT JOIN mounts m
    ON m.volume_id = v.volume_id
LEFT JOIN containers c
    ON c.container_id = m.container_id
LEFT JOIN volume_backups b
    ON b.volume_id = v.volume_id
GROUP BY
    v.volume_id,
    v.volume_name,
    v.driver,
    e.environment_name,
    u.username,
    v.state,
    v.created_at;

-- ------------------------------------------------------------
-- ELIGIBILITY FUNCTION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION volume_removal_eligible(
    requested_volume BIGINT
)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM volumes v
        WHERE v.volume_id = requested_volume
          AND v.state <> 'removed'
          AND NOT EXISTS (
              SELECT 1
              FROM mounts m
              JOIN containers c
                ON c.container_id = m.container_id
              WHERE m.volume_id = v.volume_id
                AND c.state <> 'removed'
          )
    );
$$;

-- ------------------------------------------------------------
-- TRANSACTIONAL BACKUP COMPLETION PROCEDURE
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE complete_backup(
    requested_backup BIGINT,
    requested_checksum VARCHAR(128),
    requested_size BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF requested_checksum IS NULL
       OR LENGTH(requested_checksum) < 16
       OR requested_size < 0 THEN
        RAISE EXCEPTION 'Invalid backup metadata';
    END IF;

    UPDATE volume_backups
    SET
        state = 'completed',
        checksum = requested_checksum,
        backup_size_bytes = requested_size,
        completed_at = NOW()
    WHERE backup_id = requested_backup
      AND state = 'pending';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Backup not found or is not pending';
    END IF;

    INSERT INTO storage_events (
        volume_id,
        event_type,
        details
    )
    SELECT
        volume_id,
        'backed_up',
        jsonb_build_object(
            'backup_id', backup_id,
            'checksum', requested_checksum,
            'size_bytes', requested_size
        )
    FROM volume_backups
    WHERE backup_id = requested_backup;
END;
$$;

-- ------------------------------------------------------------
-- SAMPLE USERS AND ENVIRONMENTS
-- ------------------------------------------------------------

INSERT INTO storage_users (username, role)
VALUES
    ('storage_admin', 'administrator'),
    ('database_operator', 'operator'),
    ('application_developer', 'developer'),
    ('security_auditor', 'auditor');

INSERT INTO storage_environments (
    environment_name,
    description,
    retention_days
)
VALUES
    ('production', 'Production persistent storage', 365),
    ('development', 'Development storage', 30),
    ('testing', 'Automated test storage', 7);

-- ------------------------------------------------------------
-- SAMPLE VOLUMES
-- ------------------------------------------------------------

INSERT INTO volumes (
    volume_name,
    driver,
    environment_id,
    owner_id,
    labels
)
SELECT
    'postgres_data',
    'local',
    e.environment_id,
    u.user_id,
    '{"service":"postgres","tier":"critical"}'::JSONB
FROM storage_environments e
CROSS JOIN storage_users u
WHERE e.environment_name = 'production'
  AND u.username = 'database_operator';

INSERT INTO volumes (
    volume_name,
    driver,
    environment_id,
    owner_id,
    labels
)
SELECT
    'application_data',
    'local',
    e.environment_id,
    u.user_id,
    '{"service":"inventory","tier":"standard"}'::JSONB
FROM storage_environments e
CROSS JOIN storage_users u
WHERE e.environment_name = 'development'
  AND u.username = 'application_developer';

INSERT INTO volumes (
    volume_name,
    driver,
    environment_id,
    owner_id,
    labels
)
SELECT
    'unused_test_volume',
    'local',
    e.environment_id,
    u.user_id,
    '{"service":"testing","cleanup":"eligible"}'::JSONB
FROM storage_environments e
CROSS JOIN storage_users u
WHERE e.environment_name = 'testing'
  AND u.username = 'application_developer';

-- ------------------------------------------------------------
-- SAMPLE CONTAINERS
-- ------------------------------------------------------------

INSERT INTO containers (
    container_name,
    image_name,
    environment_id,
    state
)
SELECT
    'postgres-primary',
    'postgres:17',
    environment_id,
    'running'
FROM storage_environments
WHERE environment_name = 'production';

INSERT INTO containers (
    container_name,
    image_name,
    environment_id,
    state
)
SELECT
    'inventory-api',
    'inventory-api:1.0',
    environment_id,
    'running'
FROM storage_environments
WHERE environment_name = 'development';

-- ------------------------------------------------------------
-- SAMPLE MOUNTS
-- ------------------------------------------------------------

INSERT INTO mounts (
    container_id,
    volume_id,
    type,
    source,
    destination,
    read_only
)
SELECT
    c.container_id,
    v.volume_id,
    'volume',
    'postgres_data',
    '/var/lib/postgresql/data',
    FALSE
FROM containers c
JOIN volumes v
    ON v.volume_name = 'postgres_data'
WHERE c.container_name = 'postgres-primary';

INSERT INTO mounts (
    container_id,
    volume_id,
    type,
    source,
    destination,
    read_only
)
SELECT
    c.container_id,
    v.volume_id,
    'volume',
    'application_data',
    '/app/data',
    FALSE
FROM containers c
JOIN volumes v
    ON v.volume_name = 'application_data'
WHERE c.container_name = 'inventory-api';

INSERT INTO mounts (
    container_id,
    type,
    source,
    destination,
    read_only
)
SELECT
    container_id,
    'tmpfs',
    'tmpfs',
    '/run/cache',
    TRUE
FROM containers
WHERE container_name = 'inventory-api';

-- ------------------------------------------------------------
-- SAMPLE BACKUPS
-- ------------------------------------------------------------

INSERT INTO volume_backups (
    volume_id,
    backup_name,
    storage_location,
    initiated_by,
    state
)
SELECT
    v.volume_id,
    'postgres-initial-backup',
    '/backups/postgres-initial.tar',
    u.user_id,
    'pending'
FROM volumes v
CROSS JOIN storage_users u
WHERE v.volume_name = 'postgres_data'
  AND u.username = 'storage_admin';

-- Complete the backup transactionally.
CALL complete_backup(
    (
        SELECT backup_id
        FROM volume_backups
        WHERE backup_name = 'postgres-initial-backup'
    ),
    'a1b2c3d4e5f607182930abcdef123456',
    10485760
);

-- ------------------------------------------------------------
-- SAMPLE AUDIT EVENTS
-- ------------------------------------------------------------

INSERT INTO storage_events (
    volume_id,
    container_id,
    actor_id,
    event_type,
    details
)
SELECT
    v.volume_id,
    c.container_id,
    u.user_id,
    'attached',
    '{"mount_destination":"/var/lib/postgresql/data"}'::JSONB
FROM volumes v
JOIN containers c
    ON c.container_name = 'postgres-primary'
JOIN storage_users u
    ON u.username = 'database_operator'
WHERE v.volume_name = 'postgres_data';

COMMIT;

-- ============================================================
-- OPERATIONAL QUERIES
-- ============================================================

-- 1. Retrieve all volumes and lifecycle information.

SELECT *
FROM volume_inventory
ORDER BY environment_name, volume_name;

-- 2. Find volumes currently used by multiple containers.

SELECT
    v.volume_name,
    COUNT(DISTINCT m.container_id) AS container_count
FROM volumes v
JOIN mounts m ON m.volume_id = v.volume_id
JOIN containers c ON c.container_id = m.container_id
WHERE c.state <> 'removed'
GROUP BY v.volume_id, v.volume_name
HAVING COUNT(DISTINCT m.container_id) > 1;

-- 3. Find containers with read-only mounts.

SELECT
    c.container_name,
    m.type,
    m.source,
    m.destination
FROM containers c
JOIN mounts m ON m.container_id = c.container_id
WHERE m.read_only = TRUE;

-- 4. Find volumes eligible for safe removal.

SELECT
    volume_id,
    volume_name,
    volume_removal_eligible(volume_id) AS eligible
FROM volumes
WHERE state <> 'removed';

-- 5. Identify volumes without completed backups.

SELECT
    v.volume_name,
    COUNT(b.backup_id) AS backup_attempts
FROM volumes v
LEFT JOIN volume_backups b
    ON b.volume_id = v.volume_id
   AND b.state = 'completed'
GROUP BY v.volume_id, v.volume_name
HAVING COUNT(b.backup_id) = 0;

-- 6. Calculate storage backup statistics.

SELECT
    v.volume_name,
    COUNT(b.backup_id) AS backup_count,
    COALESCE(SUM(b.backup_size_bytes), 0) AS total_backup_bytes,
    MAX(b.completed_at) AS latest_backup
FROM volumes v
LEFT JOIN volume_backups b
    ON b.volume_id = v.volume_id
GROUP BY v.volume_id, v.volume_name;

-- 7. Inspect recent storage events.

SELECT
    event_type,
    details,
    occurred_at
FROM storage_events
ORDER BY occurred_at DESC
LIMIT 50;

-- 8. Validate mount destinations and source types.

SELECT
    c.container_name,
    m.type,
    m.source,
    m.destination,
    CASE
        WHEN m.type = 'volume' AND m.volume_id IS NULL
            THEN 'INVALID_VOLUME_REFERENCE'
        WHEN m.type = 'bind' AND m.source NOT LIKE '/%'
            THEN 'INVALID_BIND_SOURCE'
        WHEN m.type = 'tmpfs' AND m.source <> 'tmpfs'
            THEN 'INVALID_TMPFS_SOURCE'
        ELSE 'VALID'
    END AS validation_result
FROM mounts m
JOIN containers c ON c.container_id = m.container_id;

-- 9. Environment-level storage aggregation using a CTE.

WITH environment_usage AS (
    SELECT
        e.environment_name,
        COUNT(DISTINCT v.volume_id) AS total_volumes,
        COUNT(DISTINCT c.container_id) AS total_containers,
        COUNT(DISTINCT m.mount_id) AS total_mounts
    FROM storage_environments e
    LEFT JOIN volumes v
        ON v.environment_id = e.environment_id
    LEFT JOIN containers c
        ON c.environment_id = e.environment_id
    LEFT JOIN mounts m
        ON m.container_id = c.container_id
    GROUP BY e.environment_id, e.environment_name
)
SELECT *
FROM environment_usage
ORDER BY environment_name;

-- 10. Find stale backups based on environment retention.

SELECT
    b.backup_id,
    b.backup_name,
    e.environment_name,
    b.completed_at,
    e.retention_days
FROM volume_backups b
JOIN volumes v ON v.volume_id = b.volume_id
JOIN storage_environments e
    ON e.environment_id = v.environment_id
WHERE b.state = 'completed'
  AND b.completed_at <
      NOW() - make_interval(days => e.retention_days);

-- 11. Transactional removal of an unused volume.
-- The eligibility check and update occur in one transaction.

BEGIN;

SELECT volume_id
FROM volumes
WHERE volume_name = 'unused_test_volume'
FOR UPDATE;

UPDATE volumes
SET
    state = 'removed',
    removed_at = NOW()
WHERE volume_name = 'unused_test_volume'
  AND volume_removal_eligible(volume_id);

COMMIT;

-- 12. Display current storage states.

SELECT
    state,
    COUNT(*) AS volume_count
FROM volumes
GROUP BY state
ORDER BY state;
