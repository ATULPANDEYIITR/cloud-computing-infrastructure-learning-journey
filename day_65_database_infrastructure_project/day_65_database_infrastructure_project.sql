-- ============================================================
-- HIGHLY AVAILABLE DATABASE INFRASTRUCTURE
-- PostgreSQL 16+
--
-- Functional areas:
-- 1. Cluster and database node inventory
-- 2. Primary and replica topology
-- 3. Replication monitoring
-- 4. Backup catalog and integrity validation
-- 5. Recovery operations
-- 6. Cache performance monitoring
-- 7. Health checks and incidents
-- 8. Failover governance
-- 9. Operational reporting
--
-- Execution:
-- Run as a PostgreSQL role with permission to create schemas,
-- tables, functions, procedures, and triggers.
--
-- The metadata schema models infrastructure operations.
-- It does not configure PostgreSQL physical streaming
-- replication or create actual database backups.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS ha_infrastructure;

SET search_path TO ha_infrastructure, public;

-- ============================================================
-- 1. ENUM TYPES
-- ============================================================

CREATE TYPE node_role AS ENUM (
    'PRIMARY',
    'REPLICA',
    'WITNESS'
);

CREATE TYPE node_status AS ENUM (
    'HEALTHY',
    'DEGRADED',
    'DOWN',
    'RECOVERING',
    'MAINTENANCE'
);

CREATE TYPE replication_mode AS ENUM (
    'SYNCHRONOUS',
    'ASYNCHRONOUS'
);

CREATE TYPE backup_type AS ENUM (
    'FULL',
    'INCREMENTAL',
    'WAL'
);

CREATE TYPE backup_status AS ENUM (
    'RUNNING',
    'COMPLETED',
    'FAILED',
    'VERIFIED',
    'EXPIRED'
);

CREATE TYPE incident_severity AS ENUM (
    'INFO',
    'WARNING',
    'CRITICAL'
);

CREATE TYPE incident_status AS ENUM (
    'OPEN',
    'INVESTIGATING',
    'RESOLVED'
);

CREATE TYPE recovery_status AS ENUM (
    'REQUESTED',
    'APPROVED',
    'RUNNING',
    'COMPLETED',
    'FAILED'
);

-- ============================================================
-- 2. CLUSTER CONFIGURATION
-- ============================================================

CREATE TABLE clusters (
    cluster_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cluster_name VARCHAR(100) NOT NULL UNIQUE,

    environment VARCHAR(20) NOT NULL
        CHECK (
            environment IN (
                'DEVELOPMENT',
                'TESTING',
                'STAGING',
                'PRODUCTION'
            )
        ),

    replication_policy replication_mode NOT NULL,

    maximum_replication_lag_seconds INTEGER NOT NULL
        CHECK (maximum_replication_lag_seconds >= 0),

    required_replica_count INTEGER NOT NULL DEFAULT 1
        CHECK (required_replica_count >= 1),

    maximum_connections INTEGER NOT NULL DEFAULT 200
        CHECK (maximum_connections > 0),

    cache_ttl_seconds INTEGER NOT NULL DEFAULT 60
        CHECK (cache_ttl_seconds > 0),

    recovery_point_objective_seconds INTEGER NOT NULL
        CHECK (recovery_point_objective_seconds >= 0),

    recovery_time_objective_seconds INTEGER NOT NULL
        CHECK (recovery_time_objective_seconds > 0),

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 3. DATABASE NODES
-- ============================================================

CREATE TABLE database_nodes (
    node_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cluster_id BIGINT NOT NULL
        REFERENCES clusters(cluster_id)
        ON DELETE RESTRICT,

    node_name VARCHAR(100) NOT NULL,

    host_name VARCHAR(255) NOT NULL,

    port INTEGER NOT NULL DEFAULT 5432
        CHECK (port BETWEEN 1 AND 65535),

    role node_role NOT NULL,

    status node_status NOT NULL DEFAULT 'HEALTHY',

    replication_position BIGINT NOT NULL DEFAULT 0
        CHECK (replication_position >= 0),

    active_connections INTEGER NOT NULL DEFAULT 0
        CHECK (active_connections >= 0),

    maximum_connections INTEGER NOT NULL
        CHECK (maximum_connections > 0),

    last_heartbeat TIMESTAMPTZ,

    last_health_check TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (cluster_id, node_name),
    UNIQUE (host_name, port),

    CHECK (active_connections <= maximum_connections)
);

CREATE UNIQUE INDEX one_active_primary_per_cluster
ON database_nodes(cluster_id)
WHERE role = 'PRIMARY'
  AND status IN ('HEALTHY', 'DEGRADED');

CREATE INDEX idx_nodes_cluster_status
ON database_nodes(cluster_id, status);

CREATE INDEX idx_nodes_replication_position
ON database_nodes(cluster_id, replication_position DESC);

-- ============================================================
-- 4. REPLICATION MONITORING
-- ============================================================

CREATE TABLE replication_metrics (
    metric_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cluster_id BIGINT NOT NULL
        REFERENCES clusters(cluster_id),

    primary_node_id BIGINT NOT NULL
        REFERENCES database_nodes(node_id),

    replica_node_id BIGINT NOT NULL
        REFERENCES database_nodes(node_id),

    primary_position BIGINT NOT NULL
        CHECK (primary_position >= 0),

    replica_position BIGINT NOT NULL
        CHECK (replica_position >= 0),

    lag_bytes BIGINT NOT NULL DEFAULT 0
        CHECK (lag_bytes >= 0),

    lag_seconds NUMERIC(12, 3) NOT NULL DEFAULT 0
        CHECK (lag_seconds >= 0),

    sampled_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (primary_node_id <> replica_node_id)
);

CREATE INDEX idx_replication_latest
ON replication_metrics(
    cluster_id,
    replica_node_id,
    sampled_at DESC
);

-- ============================================================
-- 5. BACKUP CATALOG
-- ============================================================

CREATE TABLE backup_catalog (
    backup_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cluster_id BIGINT NOT NULL
        REFERENCES clusters(cluster_id),

    source_node_id BIGINT NOT NULL
        REFERENCES database_nodes(node_id),

    backup_name VARCHAR(200) NOT NULL,

    backup_kind backup_type NOT NULL,

    status backup_status NOT NULL DEFAULT 'RUNNING',

    storage_location TEXT NOT NULL,

    checksum_algorithm VARCHAR(20) NOT NULL DEFAULT 'SHA256',

    checksum VARCHAR(128),

    size_bytes BIGINT NOT NULL DEFAULT 0
        CHECK (size_bytes >= 0),

    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    completed_at TIMESTAMPTZ,

    expires_at TIMESTAMPTZ,

    recovery_position BIGINT NOT NULL DEFAULT 0
        CHECK (recovery_position >= 0),

    verified_at TIMESTAMPTZ,

    UNIQUE (cluster_id, backup_name),

    CHECK (
        completed_at IS NULL
        OR completed_at >= started_at
    ),

    CHECK (
        expires_at IS NULL
        OR expires_at > started_at
    ),

    CHECK (
        status NOT IN ('COMPLETED', 'VERIFIED')
        OR checksum IS NOT NULL
    )
);

CREATE INDEX idx_backup_recovery
ON backup_catalog(
    cluster_id,
    status,
    completed_at DESC
);

-- ============================================================
-- 6. BACKUP VALIDATION FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION validate_backup()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status = 'VERIFIED' THEN

        IF NEW.checksum IS NULL
           OR length(trim(NEW.checksum)) < 32 THEN

            RAISE EXCEPTION
                'Verified backup requires a valid checksum';
        END IF;

        IF NEW.completed_at IS NULL THEN
            RAISE EXCEPTION
                'Backup must be completed before verification';
        END IF;

        IF NEW.verified_at IS NULL THEN
            NEW.verified_at := now();
        END IF;
    END IF;

    IF NEW.status = 'FAILED'
       AND NEW.completed_at IS NULL THEN
        NEW.completed_at := now();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_backup
BEFORE INSERT OR UPDATE ON backup_catalog
FOR EACH ROW
EXECUTE FUNCTION validate_backup();

-- ============================================================
-- 7. RECOVERY OPERATIONS
-- ============================================================

CREATE TABLE recovery_operations (
    recovery_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cluster_id BIGINT NOT NULL
        REFERENCES clusters(cluster_id),

    backup_id BIGINT NOT NULL
        REFERENCES backup_catalog(backup_id),

    target_node_id BIGINT NOT NULL
        REFERENCES database_nodes(node_id),

    requested_by VARCHAR(100) NOT NULL,

    approved_by VARCHAR(100),

    status recovery_status NOT NULL DEFAULT 'REQUESTED',

    recovery_target TIMESTAMPTZ,

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (
        approved_by IS NULL
        OR approved_by <> requested_by
    ),

    CHECK (
        completed_at IS NULL
        OR started_at IS NOT NULL
    ),

    CHECK (
        completed_at IS NULL
        OR completed_at >= started_at
    )
);

CREATE INDEX idx_recovery_cluster_status
ON recovery_operations(cluster_id, status);

CREATE OR REPLACE FUNCTION enforce_recovery_policy()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    selected_backup backup_catalog%ROWTYPE;
BEGIN
    SELECT *
    INTO selected_backup
    FROM backup_catalog
    WHERE backup_id = NEW.backup_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Backup does not exist';
    END IF;

    IF selected_backup.cluster_id <> NEW.cluster_id THEN
        RAISE EXCEPTION
            'Backup and recovery cluster do not match';
    END IF;

    IF NEW.status IN ('APPROVED', 'RUNNING', 'COMPLETED') THEN

        IF NEW.approved_by IS NULL THEN
            RAISE EXCEPTION
                'Recovery requires independent approval';
        END IF;

        IF selected_backup.status <> 'VERIFIED' THEN
            RAISE EXCEPTION
                'Only verified backups can be restored';
        END IF;

        IF selected_backup.expires_at IS NOT NULL
           AND selected_backup.expires_at <= now() THEN

            RAISE EXCEPTION
                'Expired backup cannot be restored';
        END IF;
    END IF;

    IF NEW.status = 'RUNNING'
       AND NEW.started_at IS NULL THEN
        NEW.started_at := now();
    END IF;

    IF NEW.status IN ('COMPLETED', 'FAILED')
       AND NEW.completed_at IS NULL THEN
        NEW.completed_at := now();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_recovery_policy
BEFORE INSERT OR UPDATE ON recovery_operations
FOR EACH ROW
EXECUTE FUNCTION enforce_recovery_policy();

-- ============================================================
-- 8. CACHE PERFORMANCE
-- ============================================================

CREATE TABLE cache_metrics (
    cache_metric_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cluster_id BIGINT NOT NULL
        REFERENCES clusters(cluster_id),

    cache_name VARCHAR(100) NOT NULL,

    cache_hits BIGINT NOT NULL DEFAULT 0
        CHECK (cache_hits >= 0),

    cache_misses BIGINT NOT NULL DEFAULT 0
        CHECK (cache_misses >= 0),

    evictions BIGINT NOT NULL DEFAULT 0
        CHECK (evictions >= 0),

    invalidations BIGINT NOT NULL DEFAULT 0
        CHECK (invalidations >= 0),

    memory_used_bytes BIGINT NOT NULL DEFAULT 0
        CHECK (memory_used_bytes >= 0),

    sampled_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_cache_metrics_latest
ON cache_metrics(cluster_id, sampled_at DESC);

CREATE OR REPLACE VIEW cache_performance AS
SELECT
    cluster_id,
    cache_name,
    cache_hits,
    cache_misses,
    evictions,
    invalidations,
    memory_used_bytes,
    sampled_at,
    ROUND(
        100.0 * cache_hits /
        NULLIF(cache_hits + cache_misses, 0),
        2
    ) AS hit_ratio_percent
FROM cache_metrics;

-- ============================================================
-- 9. HEALTH CHECKS
-- ============================================================

CREATE TABLE health_checks (
    health_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    node_id BIGINT NOT NULL
        REFERENCES database_nodes(node_id),

    check_name VARCHAR(100) NOT NULL,

    is_healthy BOOLEAN NOT NULL,

    response_time_ms NUMERIC(12, 3)
        CHECK (response_time_ms >= 0),

    details JSONB NOT NULL DEFAULT '{}'::jsonb,

    checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_health_checks_node_time
ON health_checks(node_id, checked_at DESC);

CREATE INDEX idx_health_checks_failed
ON health_checks(checked_at DESC)
WHERE is_healthy = false;

-- ============================================================
-- 10. INCIDENT MANAGEMENT
-- ============================================================

CREATE TABLE infrastructure_incidents (
    incident_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cluster_id BIGINT NOT NULL
        REFERENCES clusters(cluster_id),

    node_id BIGINT
        REFERENCES database_nodes(node_id),

    severity incident_severity NOT NULL,

    status incident_status NOT NULL DEFAULT 'OPEN',

    incident_type VARCHAR(100) NOT NULL,

    description TEXT NOT NULL,

    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    resolved_at TIMESTAMPTZ,

    resolution_notes TEXT,

    CHECK (
        resolved_at IS NULL
        OR resolved_at >= opened_at
    )
);

CREATE INDEX idx_incidents_open
ON infrastructure_incidents(
    cluster_id,
    severity,
    opened_at DESC
)
WHERE status <> 'RESOLVED';

-- ============================================================
-- 11. FAILOVER HISTORY
-- ============================================================

CREATE TABLE failover_history (
    failover_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cluster_id BIGINT NOT NULL
        REFERENCES clusters(cluster_id),

    previous_primary_id BIGINT
        REFERENCES database_nodes(node_id),

    promoted_node_id BIGINT NOT NULL
        REFERENCES database_nodes(node_id),

    previous_position BIGINT NOT NULL,

    promoted_position BIGINT NOT NULL,

    data_loss_estimate BIGINT NOT NULL DEFAULT 0
        CHECK (data_loss_estimate >= 0),

    reason TEXT NOT NULL,

    initiated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    completed_at TIMESTAMPTZ,

    CHECK (promoted_node_id <> previous_primary_id)
);

CREATE INDEX idx_failover_history
ON failover_history(cluster_id, initiated_at DESC);

-- ============================================================
-- 12. SAMPLE CLUSTER
-- ============================================================

INSERT INTO clusters (
    cluster_name,
    environment,
    replication_policy,
    maximum_replication_lag_seconds,
    required_replica_count,
    maximum_connections,
    cache_ttl_seconds,
    recovery_point_objective_seconds,
    recovery_time_objective_seconds
)
VALUES (
    'production-commerce',
    'PRODUCTION',
    'ASYNCHRONOUS',
    5,
    2,
    300,
    60,
    60,
    300
);

INSERT INTO database_nodes (
    cluster_id,
    node_name,
    host_name,
    port,
    role,
    status,
    replication_position,
    maximum_connections,
    last_heartbeat
)
SELECT
    cluster_id,
    'postgres-primary',
    'db-primary.internal',
    5432,
    'PRIMARY',
    'HEALTHY',
    1200,
    300,
    now()
FROM clusters
WHERE cluster_name = 'production-commerce';

INSERT INTO database_nodes (
    cluster_id,
    node_name,
    host_name,
    port,
    role,
    status,
    replication_position,
    maximum_connections,
    last_heartbeat
)
SELECT
    cluster_id,
    'postgres-replica-1',
    'db-replica-1.internal',
    5432,
    'REPLICA',
    'HEALTHY',
    1198,
    200,
    now()
FROM clusters
WHERE cluster_name = 'production-commerce';

INSERT INTO database_nodes (
    cluster_id,
    node_name,
    host_name,
    port,
    role,
    status,
    replication_position,
    maximum_connections,
    last_heartbeat
)
SELECT
    cluster_id,
    'postgres-replica-2',
    'db-replica-2.internal',
    5432,
    'REPLICA',
    'DEGRADED',
    1170,
    200,
    now()
FROM clusters
WHERE cluster_name = 'production-commerce';

-- ============================================================
-- 13. REPLICATION SAMPLE METRICS
-- ============================================================

INSERT INTO replication_metrics (
    cluster_id,
    primary_node_id,
    replica_node_id,
    primary_position,
    replica_position,
    lag_bytes,
    lag_seconds
)
SELECT
    c.cluster_id,
    p.node_id,
    r.node_id,
    p.replication_position,
    r.replication_position,
    CASE
        WHEN p.replication_position >= r.replication_position
        THEN (p.replication_position - r.replication_position) * 8192
        ELSE 0
    END,
    CASE
        WHEN r.node_name = 'postgres-replica-1'
        THEN 0.5
        ELSE 8.5
    END
FROM clusters c
JOIN database_nodes p
    ON p.cluster_id = c.cluster_id
   AND p.role = 'PRIMARY'
JOIN database_nodes r
    ON r.cluster_id = c.cluster_id
   AND r.role = 'REPLICA'
WHERE c.cluster_name = 'production-commerce';

-- ============================================================
-- 14. BACKUP SAMPLE DATA
-- ============================================================

INSERT INTO backup_catalog (
    cluster_id,
    source_node_id,
    backup_name,
    backup_kind,
    status,
    storage_location,
    checksum,
    size_bytes,
    completed_at,
    expires_at,
    recovery_position
)
SELECT
    c.cluster_id,
    n.node_id,
    'production-full-backup-001',
    'FULL',
    'VERIFIED',
    's3://database-backups/production/full-001',
    repeat('a', 64),
    1073741824,
    now() - interval '1 hour',
    now() + interval '30 days',
    1200
FROM clusters c
JOIN database_nodes n
    ON n.cluster_id = c.cluster_id
   AND n.role = 'PRIMARY'
WHERE c.cluster_name = 'production-commerce';

-- ============================================================
-- 15. CACHE SAMPLE METRICS
-- ============================================================

INSERT INTO cache_metrics (
    cluster_id,
    cache_name,
    cache_hits,
    cache_misses,
    evictions,
    invalidations,
    memory_used_bytes
)
SELECT
    cluster_id,
    'redis-commerce-cache',
    95000,
    5000,
    120,
    250,
    536870912
FROM clusters
WHERE cluster_name = 'production-commerce';

-- ============================================================
-- 16. HEALTH CHECK SAMPLE DATA
-- ============================================================

INSERT INTO health_checks (
    node_id,
    check_name,
    is_healthy,
    response_time_ms,
    details
)
SELECT
    node_id,
    'database-connectivity',
    status = 'HEALTHY',
    CASE
        WHEN status = 'HEALTHY' THEN 4.2
        ELSE 350.0
    END,
    jsonb_build_object(
        'connection_test', status = 'HEALTHY',
        'role', role::text
    )
FROM database_nodes;

-- ============================================================
-- 17. INCIDENT SAMPLE
-- ============================================================

INSERT INTO infrastructure_incidents (
    cluster_id,
    node_id,
    severity,
    status,
    incident_type,
    description
)
SELECT
    c.cluster_id,
    n.node_id,
    'WARNING',
    'OPEN',
    'REPLICATION_LAG',
    'Replica replication delay exceeds configured threshold'
FROM clusters c
JOIN database_nodes n
    ON n.cluster_id = c.cluster_id
WHERE c.cluster_name = 'production-commerce'
  AND n.node_name = 'postgres-replica-2';

-- ============================================================
-- 18. INFRASTRUCTURE REPORTING VIEWS
-- ============================================================

CREATE OR REPLACE VIEW cluster_node_overview AS
SELECT
    c.cluster_name,
    c.environment,
    c.replication_policy,
    n.node_name,
    n.role,
    n.status,
    n.replication_position,
    n.active_connections,
    n.maximum_connections,
    n.last_heartbeat
FROM clusters c
JOIN database_nodes n
    ON n.cluster_id = c.cluster_id;

CREATE OR REPLACE VIEW replica_lag_report AS
SELECT
    c.cluster_name,
    p.node_name AS primary_node,
    r.node_name AS replica_node,
    m.primary_position,
    m.replica_position,
    m.lag_bytes,
    m.lag_seconds,
    c.maximum_replication_lag_seconds,
    CASE
        WHEN m.lag_seconds <=
            c.maximum_replication_lag_seconds
        THEN 'WITHIN_THRESHOLD'
        ELSE 'LAG_EXCEEDED'
    END AS lag_status,
    m.sampled_at
FROM replication_metrics m
JOIN clusters c
    ON c.cluster_id = m.cluster_id
JOIN database_nodes p
    ON p.node_id = m.primary_node_id
JOIN database_nodes r
    ON r.node_id = m.replica_node_id;

CREATE OR REPLACE VIEW backup_compliance AS
SELECT
    c.cluster_name,
    b.backup_name,
    b.backup_kind,
    b.status,
    b.completed_at,
    b.verified_at,
    b.size_bytes,
    b.checksum,
    b.expires_at,
    CASE
        WHEN b.status = 'VERIFIED'
         AND (
             b.expires_at IS NULL
             OR b.expires_at > now()
         )
        THEN true
        ELSE false
    END AS eligible_for_recovery
FROM backup_catalog b
JOIN clusters c
    ON c.cluster_id = b.cluster_id;

CREATE OR REPLACE VIEW cluster_capacity_report AS
SELECT
    c.cluster_name,
    n.node_name,
    n.active_connections,
    n.maximum_connections,
    ROUND(
        100.0 * n.active_connections /
        NULLIF(n.maximum_connections, 0),
        2
    ) AS connection_utilization_percent
FROM clusters c
JOIN database_nodes n
    ON n.cluster_id = c.cluster_id;

-- ============================================================
-- 19. ELIGIBLE FAILOVER CANDIDATES
-- ============================================================

CREATE OR REPLACE VIEW eligible_failover_candidates AS
WITH primary_position AS (
    SELECT
        cluster_id,
        replication_position AS primary_position
    FROM database_nodes
    WHERE role = 'PRIMARY'
)
SELECT
    c.cluster_name,
    n.node_id,
    n.node_name,
    n.replication_position,
    p.primary_position,
    p.primary_position - n.replication_position
        AS position_lag,
    n.status
FROM clusters c
JOIN database_nodes n
    ON n.cluster_id = c.cluster_id
JOIN primary_position p
    ON p.cluster_id = c.cluster_id
WHERE n.role = 'REPLICA'
  AND n.status = 'HEALTHY'
  AND n.replication_position <= p.primary_position
  AND (
      p.primary_position - n.replication_position
  ) <= c.maximum_replication_lag_seconds;

-- ============================================================
-- 20. REPLICATION METRIC RECORDING FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION record_replication_metric(
    p_cluster_id BIGINT,
    p_replica_id BIGINT,
    p_lag_bytes BIGINT,
    p_lag_seconds NUMERIC
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_primary_id BIGINT;
    v_primary_position BIGINT;
    v_replica_position BIGINT;
    v_metric_id BIGINT;
BEGIN
    IF p_lag_bytes < 0 OR p_lag_seconds < 0 THEN
        RAISE EXCEPTION 'Replication lag cannot be negative';
    END IF;

    SELECT node_id, replication_position
    INTO v_primary_id, v_primary_position
    FROM database_nodes
    WHERE cluster_id = p_cluster_id
      AND role = 'PRIMARY'
      AND status IN ('HEALTHY', 'DEGRADED')
    FOR SHARE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'No available primary node';
    END IF;

    SELECT replication_position
    INTO v_replica_position
    FROM database_nodes
    WHERE node_id = p_replica_id
      AND cluster_id = p_cluster_id
      AND role = 'REPLICA';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Replica does not belong to cluster';
    END IF;

    INSERT INTO replication_metrics (
        cluster_id,
        primary_node_id,
        replica_node_id,
        primary_position,
        replica_position,
        lag_bytes,
        lag_seconds
    )
    VALUES (
        p_cluster_id,
        v_primary_id,
        p_replica_id,
        v_primary_position,
        v_replica_position,
        p_lag_bytes,
        p_lag_seconds
    )
    RETURNING metric_id INTO v_metric_id;

    RETURN v_metric_id;
END;
$$;

-- ============================================================
-- 21. FAILOVER PROCEDURE
--
-- Advisory locking prevents simultaneous failover execution
-- for the same cluster within this PostgreSQL control database.
--
-- A production implementation must also fence the former
-- primary at the database/network layer.
-- ============================================================

CREATE OR REPLACE PROCEDURE promote_replica(
    p_cluster_id BIGINT,
    p_replica_id BIGINT,
    p_reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_old_primary BIGINT;
    v_old_position BIGINT;
    v_new_position BIGINT;
    v_replica_status node_status;
    v_new_role node_role;
    v_data_loss BIGINT;
BEGIN
    PERFORM pg_advisory_xact_lock(p_cluster_id);

    SELECT node_id, replication_position
    INTO v_old_primary, v_old_position
    FROM database_nodes
    WHERE cluster_id = p_cluster_id
      AND role = 'PRIMARY'
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Primary node not found';
    END IF;

    SELECT status, role, replication_position
    INTO v_replica_status, v_new_role, v_new_position
    FROM database_nodes
    WHERE node_id = p_replica_id
      AND cluster_id = p_cluster_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Promotion candidate not found';
    END IF;

    IF v_new_role <> 'REPLICA' THEN
        RAISE EXCEPTION 'Candidate is not a replica';
    END IF;

    IF v_replica_status <> 'HEALTHY' THEN
        RAISE EXCEPTION 'Candidate is not healthy';
    END IF;

    IF v_new_position > v_old_position THEN
        RAISE EXCEPTION
            'Replica position exceeds primary position';
    END IF;

    v_data_loss := v_old_position - v_new_position;

    -- Retire the old primary before promoting another node.
    UPDATE database_nodes
    SET role = 'REPLICA',
        status = 'DOWN'
    WHERE node_id = v_old_primary;

    UPDATE database_nodes
    SET role = 'PRIMARY',
        status = 'HEALTHY'
    WHERE node_id = p_replica_id;

    INSERT INTO failover_history (
        cluster_id,
        previous_primary_id,
        promoted_node_id,
        previous_position,
        promoted_position,
        data_loss_estimate,
        reason,
        completed_at
    )
    VALUES (
        p_cluster_id,
        v_old_primary,
        p_replica_id,
        v_old_position,
        v_new_position,
        v_data_loss,
        p_reason,
        now()
    );

    INSERT INTO infrastructure_incidents (
        cluster_id,
        node_id,
        severity,
        status,
        incident_type,
        description
    )
    VALUES (
        p_cluster_id,
        p_replica_id,
        'CRITICAL',
        'INVESTIGATING',
        'DATABASE_FAILOVER',
        p_reason
    );

END;
$$;

-- ============================================================
-- 22. BACKUP ELIGIBILITY FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION is_backup_recovery_eligible(
    p_backup_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM backup_catalog b
        JOIN clusters c
            ON c.cluster_id = b.cluster_id
        WHERE b.backup_id = p_backup_id
          AND b.status = 'VERIFIED'
          AND (
              b.expires_at IS NULL
              OR b.expires_at > now()
          )
    );
$$;

-- ============================================================
-- 23. OPERATIONAL ALERT GENERATION
-- ============================================================

CREATE OR REPLACE FUNCTION generate_replication_alerts()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_count INTEGER;
BEGIN
    INSERT INTO infrastructure_incidents (
        cluster_id,
        node_id,
        severity,
        status,
        incident_type,
        description
    )
    SELECT
        m.cluster_id,
        m.replica_node_id,
        'WARNING',
        'OPEN',
        'REPLICATION_LAG',
        'Replica lag exceeds cluster policy'
    FROM replication_metrics m
    JOIN clusters c
        ON c.cluster_id = m.cluster_id
    WHERE m.sampled_at >= now() - interval '5 minutes'
      AND m.lag_seconds >
          c.maximum_replication_lag_seconds
      AND NOT EXISTS (
          SELECT 1
          FROM infrastructure_incidents i
          WHERE i.cluster_id = m.cluster_id
            AND i.node_id = m.replica_node_id
            AND i.incident_type = 'REPLICATION_LAG'
            AND i.status <> 'RESOLVED'
      );

    GET DIAGNOSTICS v_count = ROW_COUNT;

    RETURN v_count;
END;
$$;

-- ============================================================
-- 24. VALIDATION AND REPORTING QUERIES
-- ============================================================

-- Query A: Complete cluster topology.
SELECT *
FROM cluster_node_overview
ORDER BY cluster_name, role, node_name;

-- Query B: Latest replication state.
WITH latest AS (
    SELECT DISTINCT ON (replica_node_id)
        *
    FROM replica_lag_report
    ORDER BY replica_node_id, sampled_at DESC
)
SELECT *
FROM latest
ORDER BY lag_seconds DESC;

-- Query C: Replication threshold violations.
SELECT *
FROM replica_lag_report
WHERE lag_status = 'LAG_EXCEEDED';

-- Query D: Backup recovery eligibility.
SELECT *
FROM backup_compliance
ORDER BY completed_at DESC;

-- Query E: Cache hit ratio.
SELECT *
FROM cache_performance
ORDER BY sampled_at DESC;

-- Query F: Connection utilization.
SELECT *
FROM cluster_capacity_report
ORDER BY connection_utilization_percent DESC;

-- Query G: Health check failures.
SELECT
    n.node_name,
    h.check_name,
    h.response_time_ms,
    h.details,
    h.checked_at
FROM health_checks h
JOIN database_nodes n
    ON n.node_id = h.node_id
WHERE h.is_healthy = false
ORDER BY h.checked_at DESC;

-- Query H: Active critical incidents.
SELECT
    c.cluster_name,
    i.incident_type,
    i.severity,
    i.description,
    i.opened_at
FROM infrastructure_incidents i
JOIN clusters c
    ON c.cluster_id = i.cluster_id
WHERE i.status <> 'RESOLVED'
ORDER BY i.opened_at DESC;

-- Query I: Backup age and RPO evaluation.
SELECT
    c.cluster_name,
    b.backup_name,
    EXTRACT(
        EPOCH FROM now() - b.completed_at
    ) AS backup_age_seconds,
    c.recovery_point_objective_seconds,
    CASE
        WHEN b.status = 'VERIFIED'
         AND EXTRACT(
             EPOCH FROM now() - b.completed_at
         ) <= c.recovery_point_objective_seconds
        THEN 'RPO_WITHIN_TARGET'
        ELSE 'RPO_TARGET_NOT_MET'
    END AS rpo_status
FROM backup_catalog b
JOIN clusters c
    ON c.cluster_id = b.cluster_id
WHERE b.completed_at IS NOT NULL;

-- Query J: Failover candidates.
SELECT *
FROM eligible_failover_candidates
ORDER BY position_lag ASC;

-- ============================================================
-- 25. WORKFLOW VALIDATION EXAMPLES
-- ============================================================

-- A backup cannot become VERIFIED without a completed backup
-- and a checksum.
--
-- A recovery operation requires a verified, unexpired backup
-- and independent approval.
--
-- The following transaction demonstrates an approved recovery
-- workflow using the sample backup.

DO $$
DECLARE
    v_cluster_id BIGINT;
    v_backup_id BIGINT;
    v_target_node_id BIGINT;
BEGIN
    SELECT cluster_id
    INTO v_cluster_id
    FROM clusters
    WHERE cluster_name = 'production-commerce';

    SELECT backup_id
    INTO v_backup_id
    FROM backup_catalog
    WHERE cluster_id = v_cluster_id
      AND backup_name = 'production-full-backup-001';

    SELECT node_id
    INTO v_target_node_id
    FROM database_nodes
    WHERE cluster_id = v_cluster_id
      AND role = 'REPLICA'
    ORDER BY replication_position DESC
    LIMIT 1;

    INSERT INTO recovery_operations (
        cluster_id,
        backup_id,
        target_node_id,
        requested_by,
        approved_by,
        status
    )
    VALUES (
        v_cluster_id,
        v_backup_id,
        v_target_node_id,
        'database-operator',
        'infrastructure-manager',
        'APPROVED'
    );
END;
$$;

-- ============================================================
-- 26. REPORTING: RECOVERY AND FAILOVER HISTORY
-- ============================================================

SELECT
    c.cluster_name,
    f.initiated_at,
    old_node.node_name AS previous_primary,
    new_node.node_name AS promoted_primary,
    f.previous_position,
    f.promoted_position,
    f.data_loss_estimate,
    f.reason
FROM failover_history f
JOIN clusters c
    ON c.cluster_id = f.cluster_id
LEFT JOIN database_nodes old_node
    ON old_node.node_id = f.previous_primary_id
JOIN database_nodes new_node
    ON new_node.node_id = f.promoted_node_id
ORDER BY f.initiated_at DESC;

SELECT
    r.recovery_id,
    c.cluster_name,
    b.backup_name,
    r.requested_by,
    r.approved_by,
    r.status,
    r.started_at,
    r.completed_at
FROM recovery_operations r
JOIN clusters c
    ON c.cluster_id = r.cluster_id
JOIN backup_catalog b
    ON b.backup_id = r.backup_id
ORDER BY r.created_at DESC;

-- ============================================================
-- 27. MAINTENANCE AND RETENTION
-- ============================================================

-- Expire old backup metadata.
-- Execute only after the corresponding storage objects have
-- been safely removed according to retention policy.

-- UPDATE backup_catalog
-- SET status = 'EXPIRED'
-- WHERE expires_at < now()
--   AND status = 'VERIFIED';

-- Remove historical metric records only after the monitoring
-- retention policy permits their removal.

-- DELETE FROM replication_metrics
-- WHERE sampled_at < now() - interval '90 days';

COMMIT;

-- ============================================================
-- 28. OPERATIONAL NOTES
-- ============================================================

-- Actual PostgreSQL high availability requires separate
-- database-level configuration:
--
-- - WAL archiving
-- - streaming replication
-- - synchronous_standby_names
-- - pg_basebackup
-- - recovery.signal
-- - restore_command
-- - replication slots
-- - primary fencing
-- - controlled promotion
--
-- The tables above store operational metadata and monitoring
-- observations. Updating a metadata row does not itself
-- configure the PostgreSQL replication engine.
--
-- Production deployments should also apply:
--
-- - TLS for database connections
-- - SCRAM-SHA-256 authentication
-- - least-privilege database roles
-- - encrypted backup storage
-- - off-site backup copies
-- - secret rotation
-- - connection pooling
-- - replication lag alerts
-- - tested point-in-time recovery
-- - audit logging
