DROP SCHEMA IF EXISTS managed_cloud CASCADE;
CREATE SCHEMA managed_cloud;

SET search_path TO managed_cloud, public;

CREATE TYPE database_state AS ENUM (
    'available',
    'maintenance',
    'degraded',
    'failed',
    'restoring'
);

CREATE TYPE node_role AS ENUM (
    'primary',
    'read_replica'
);

CREATE TYPE backup_type AS ENUM (
    'full',
    'snapshot'
);

CREATE TYPE backup_status AS ENUM (
    'available',
    'expired',
    'failed'
);

CREATE TYPE maintenance_status AS ENUM (
    'scheduled',
    'running',
    'completed',
    'failed'
);

CREATE TYPE check_status AS ENUM (
    'passing',
    'failing'
);

CREATE TABLE cloud_databases (
    database_id BIGSERIAL PRIMARY KEY,
    database_name TEXT NOT NULL UNIQUE,
    engine TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    region TEXT NOT NULL,
    storage_gb INTEGER NOT NULL CHECK (storage_gb >= 10),
    backup_retention_days INTEGER NOT NULL
        CHECK (backup_retention_days BETWEEN 1 AND 35),
    state database_state NOT NULL DEFAULT 'available',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE database_nodes (
    node_id BIGSERIAL PRIMARY KEY,
    database_id BIGINT NOT NULL
        REFERENCES cloud_databases(database_id)
        ON DELETE CASCADE,
    node_name TEXT NOT NULL,
    zone TEXT NOT NULL,
    role node_role NOT NULL,
    engine_version TEXT NOT NULL,
    state database_state NOT NULL DEFAULT 'available',
    cpu_percent NUMERIC(5,2) NOT NULL DEFAULT 0
        CHECK (cpu_percent BETWEEN 0 AND 100),
    storage_percent NUMERIC(5,2) NOT NULL DEFAULT 0
        CHECK (storage_percent BETWEEN 0 AND 100),
    replication_lag_seconds NUMERIC(12,3) NOT NULL DEFAULT 0
        CHECK (replication_lag_seconds >= 0),
    active_connections INTEGER NOT NULL DEFAULT 0
        CHECK (active_connections >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (database_id, node_name)
);

CREATE UNIQUE INDEX one_primary_per_database
ON database_nodes(database_id)
WHERE role = 'primary';

CREATE INDEX database_nodes_database_role_idx
ON database_nodes(database_id, role);

CREATE TABLE backups (
    backup_id BIGSERIAL PRIMARY KEY,
    database_id BIGINT NOT NULL
        REFERENCES cloud_databases(database_id)
        ON DELETE CASCADE,
    backup_type backup_type NOT NULL,
    status backup_status NOT NULL DEFAULT 'available',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    size_gb NUMERIC(12,2) NOT NULL CHECK (size_gb > 0),
    checksum TEXT NOT NULL,
    CHECK (expires_at > created_at)
);

CREATE INDEX backups_database_created_idx
ON backups(database_id, created_at DESC);

CREATE TABLE maintenance_events (
    maintenance_id BIGSERIAL PRIMARY KEY,
    database_id BIGINT NOT NULL
        REFERENCES cloud_databases(database_id)
        ON DELETE CASCADE,
    source_version TEXT NOT NULL,
    target_version TEXT NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    status maintenance_status NOT NULL DEFAULT 'scheduled',
    failure_reason TEXT,
    CHECK (source_version <> target_version)
);

CREATE INDEX maintenance_database_schedule_idx
ON maintenance_events(database_id, scheduled_at);

CREATE TABLE status_checks (
    status_check_id BIGSERIAL PRIMARY KEY,
    database_id BIGINT NOT NULL
        REFERENCES cloud_databases(database_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    status check_status NOT NULL,
    details TEXT NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (database_id, check_name)
);

CREATE TABLE backup_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    database_id BIGINT NOT NULL UNIQUE
        REFERENCES cloud_databases(database_id)
        ON DELETE CASCADE,
    minimum_retention_days INTEGER NOT NULL
        CHECK (minimum_retention_days BETWEEN 1 AND 35),
    automated_backup_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    point_in_time_recovery_enabled BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE audit_events (
    audit_id BIGSERIAL PRIMARY KEY,
    database_id BIGINT
        REFERENCES cloud_databases(database_id)
        ON DELETE SET NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    result TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER cloud_databases_updated_at
BEFORE UPDATE ON cloud_databases
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE FUNCTION validate_node_version()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    expected_version TEXT;
BEGIN
    SELECT engine_version
    INTO expected_version
    FROM cloud_databases
    WHERE database_id = NEW.database_id;

    IF expected_version IS NULL THEN
        RAISE EXCEPTION 'Database % does not exist', NEW.database_id;
    END IF;

    IF NEW.engine_version <> expected_version THEN
        RAISE EXCEPTION
            'Node version % does not match database version %',
            NEW.engine_version,
            expected_version;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER validate_node_version_trigger
BEFORE INSERT OR UPDATE ON database_nodes
FOR EACH ROW
EXECUTE FUNCTION validate_node_version();

CREATE OR REPLACE FUNCTION validate_backup_retention()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    retention_days INTEGER;
BEGIN
    SELECT backup_retention_days
    INTO retention_days
    FROM cloud_databases
    WHERE database_id = NEW.database_id;

    IF NEW.expires_at >
       NEW.created_at + make_interval(days => retention_days) THEN
        RAISE EXCEPTION
            'Backup % exceeds configured retention period',
            NEW.backup_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER validate_backup_retention_trigger
BEFORE INSERT OR UPDATE ON backups
FOR EACH ROW
EXECUTE FUNCTION validate_backup_retention();

CREATE OR REPLACE FUNCTION create_backup(
    p_database_id BIGINT,
    p_type backup_type DEFAULT 'snapshot'
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_backup_id BIGINT;
    v_retention INTEGER;
    v_storage INTEGER;
    v_primary_count INTEGER;
    v_checksum TEXT;
BEGIN
    SELECT backup_retention_days, storage_gb
    INTO v_retention, v_storage
    FROM cloud_databases
    WHERE database_id = p_database_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Database % does not exist', p_database_id;
    END IF;

    SELECT count(*)
    INTO v_primary_count
    FROM database_nodes
    WHERE database_id = p_database_id
      AND role = 'primary'
      AND state = 'available';

    IF v_primary_count <> 1 THEN
        RAISE EXCEPTION
            'Database % must have one available primary',
            p_database_id;
    END IF;

    v_checksum := encode(
        digest(
            p_database_id::TEXT || ':' ||
            clock_timestamp()::TEXT,
            'sha256'
        ),
        'hex'
    );

    INSERT INTO backups (
        database_id,
        backup_type,
        status,
        created_at,
        expires_at,
        size_gb,
        checksum
    )
    VALUES (
        p_database_id,
        p_type,
        'available',
        now(),
        now() + make_interval(days => v_retention),
        GREATEST(1, v_storage / 5),
        v_checksum
    )
    RETURNING backup_id INTO v_backup_id;

    INSERT INTO audit_events (
        database_id,
        action,
        actor,
        result,
        details
    )
    VALUES (
        p_database_id,
        'create_backup',
        'backup-service',
        'success',
        'Backup created: ' || v_backup_id
    );

    RETURN v_backup_id;
END;
$$;

CREATE OR REPLACE FUNCTION evaluate_database(
    p_database_id BIGINT
)
RETURNS TABLE (
    check_name TEXT,
    status check_status,
    details TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_primary_count INTEGER;
    v_zone_count INTEGER;
    v_replica_count INTEGER;
    v_retention INTEGER;
    v_version TEXT;
    v_version_mismatch INTEGER;
BEGIN
    SELECT backup_retention_days, engine_version
    INTO v_retention, v_version
    FROM cloud_databases
    WHERE database_id = p_database_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Database % does not exist', p_database_id;
    END IF;

    SELECT count(*)
    INTO v_primary_count
    FROM database_nodes
    WHERE database_id = p_database_id
      AND role = 'primary';

    SELECT count(DISTINCT zone)
    INTO v_zone_count
    FROM database_nodes
    WHERE database_id = p_database_id;

    SELECT count(*)
    INTO v_replica_count
    FROM database_nodes
    WHERE database_id = p_database_id
      AND role = 'read_replica'
      AND state = 'available'
      AND replication_lag_seconds < 30;

    SELECT count(*)
    INTO v_version_mismatch
    FROM database_nodes
    WHERE database_id = p_database_id
      AND engine_version <> v_version;

    RETURN QUERY
    SELECT
        'single-primary',
        CASE
            WHEN v_primary_count = 1
            THEN 'passing'::check_status
            ELSE 'failing'::check_status
        END,
        'Exactly one primary is required.';

    RETURN QUERY
    SELECT
        'backup-retention',
        CASE
            WHEN v_retention >= 7
            THEN 'passing'::check_status
            ELSE 'failing'::check_status
        END,
        'Production retention should be at least seven days.';

    RETURN QUERY
    SELECT
        'multi-zone',
        CASE
            WHEN v_zone_count >= 2
            THEN 'passing'::check_status
            ELSE 'failing'::check_status
        END,
        'Database nodes should span multiple zones.';

    RETURN QUERY
    SELECT
        'healthy-replica',
        CASE
            WHEN v_replica_count >= 1
            THEN 'passing'::check_status
            ELSE 'failing'::check_status
        END,
        'At least one healthy replica is required for failover.';

    RETURN QUERY
    SELECT
        'version-consistency',
        CASE
            WHEN v_version_mismatch = 0
            THEN 'passing'::check_status
            ELSE 'failing'::check_status
        END,
        'All nodes must use the database engine version.';
END;
$$;

CREATE OR REPLACE VIEW database_operational_summary AS
SELECT
    d.database_id,
    d.database_name,
    d.engine,
    d.engine_version,
    d.region,
    d.storage_gb,
    d.backup_retention_days,
    d.state,
    count(n.node_id) AS node_count,
    count(n.node_id) FILTER (
        WHERE n.role = 'primary'
    ) AS primary_count,
    count(n.node_id) FILTER (
        WHERE n.role = 'read_replica'
    ) AS replica_count,
    count(b.backup_id) FILTER (
        WHERE b.status = 'available'
          AND b.expires_at > now()
    ) AS active_backups
FROM cloud_databases d
LEFT JOIN database_nodes n
    ON n.database_id = d.database_id
LEFT JOIN backups b
    ON b.database_id = d.database_id
GROUP BY
    d.database_id,
    d.database_name,
    d.engine,
    d.engine_version,
    d.region,
    d.storage_gb,
    d.backup_retention_days,
    d.state;

INSERT INTO cloud_databases (
    database_name,
    engine,
    engine_version,
    region,
    storage_gb,
    backup_retention_days
)
VALUES (
    'orders-prod',
    'PostgreSQL',
    '16.4',
    'ap-south-1',
    250,
    14
);

INSERT INTO database_nodes (
    database_id,
    node_name,
    zone,
    role,
    engine_version,
    cpu_percent,
    storage_percent,
    replication_lag_seconds,
    active_connections
)
VALUES
(
    1,
    'orders-primary-a',
    'zone-a',
    'primary',
    '16.4',
    42.0,
    55.0,
    0,
    85
),
(
    1,
    'orders-replica-b',
    'zone-b',
    'read_replica',
    '16.4',
    34.0,
    52.0,
    4.2,
    45
),
(
    1,
    'orders-replica-c',
    'zone-c',
    'read_replica',
    '16.4',
    38.0,
    57.0,
    6.8,
    51
);

INSERT INTO backup_policies (
    database_id,
    minimum_retention_days
)
VALUES (
    1,
    7
);

INSERT INTO maintenance_events (
    database_id,
    source_version,
    target_version,
    scheduled_at,
    status
)
VALUES (
    1,
    '16.4',
    '16.5',
    now() + interval '2 hours',
    'scheduled'
);

INSERT INTO audit_events (
    database_id,
    action,
    actor,
    result,
    details
)
VALUES (
    1,
    'initial-provisioning',
    'platform-admin',
    'success',
    'Production database provisioned across three zones.'
);

DO $$
DECLARE
    v_backup BIGINT;
BEGIN
    v_backup := create_backup(1, 'full');

    RAISE NOTICE 'Created backup %', v_backup;
END;
$$;

INSERT INTO status_checks (
    database_id,
    check_name,
    status,
    details
)
SELECT
    1,
    check_name,
    status,
    details
FROM evaluate_database(1)
ON CONFLICT (database_id, check_name)
DO UPDATE SET
    status = EXCLUDED.status,
    details = EXCLUDED.details,
    checked_at = now();

SELECT *
FROM database_operational_summary;

SELECT *
FROM evaluate_database(1);

SELECT
    database_name,
    region,
    engine_version,
    node_count,
    primary_count,
    replica_count,
    active_backups
FROM database_operational_summary
WHERE state = 'available';

SELECT
    database_id,
    backup_id,
    backup_type,
    created_at,
    expires_at,
    status
FROM backups
WHERE expires_at > now()
ORDER BY created_at DESC;

SELECT
    maintenance_id,
    database_id,
    source_version,
    target_version,
    scheduled_at,
    status
FROM maintenance_events
WHERE status = 'scheduled'
ORDER BY scheduled_at;

SELECT
    d.database_name,
    n.node_name,
    n.zone,
    n.role,
    n.state,
    n.cpu_percent,
    n.storage_percent,
    n.replication_lag_seconds
FROM cloud_databases d
JOIN database_nodes n
    ON n.database_id = d.database_id
WHERE n.state <> 'available'
ORDER BY d.database_name, n.node_name;

-- Transactional maintenance state transition.
BEGIN;

SELECT database_id
FROM cloud_databases
WHERE database_id = 1
FOR UPDATE;

UPDATE cloud_databases
SET state = 'maintenance'
WHERE database_id = 1
  AND state = 'available';

UPDATE maintenance_events
SET
    status = 'running',
    started_at = now()
WHERE maintenance_id = (
    SELECT maintenance_id
    FROM maintenance_events
    WHERE database_id = 1
      AND status = 'scheduled'
    ORDER BY scheduled_at
    LIMIT 1
)
RETURNING maintenance_id;

INSERT INTO audit_events (
    database_id,
    action,
    actor,
    result,
    details
)
VALUES (
    1,
    'maintenance-start',
    'maintenance-service',
    'success',
    'Database entered controlled maintenance state.'
);

COMMIT;

-- Restore the service state after the example transaction.
BEGIN;

UPDATE cloud_databases
SET state = 'available'
WHERE database_id = 1
  AND state = 'maintenance';

UPDATE maintenance_events
SET
    status = 'completed',
    completed_at = now()
WHERE database_id = 1
  AND status = 'running';

INSERT INTO audit_events (
    database_id,
    action,
    actor,
    result,
    details
)
VALUES (
    1,
    'maintenance-complete',
    'maintenance-service',
    'success',
    'Maintenance workflow completed.'
);

COMMIT;

-- Retention cleanup.
UPDATE backups
SET status = 'expired'
WHERE expires_at <= now()
  AND status = 'available';

SELECT
    database_name,
    state,
    backup_retention_days
FROM cloud_databases
WHERE backup_retention_days < 7;

SELECT
    d.database_name,
    count(*) AS failing_checks
FROM status_checks s
JOIN cloud_databases d
    ON d.database_id = s.database_id
WHERE s.status = 'failing'
GROUP BY d.database_name
ORDER BY failing_checks DESC;
