DROP SCHEMA IF EXISTS block_storage_lab CASCADE;
CREATE SCHEMA block_storage_lab;
SET search_path TO block_storage_lab;

-- PostgreSQL model for block storage operations.
-- Capacity, IOPS, throughput, attachment state, snapshots, and governance
-- are stored separately because they represent different operational facts.

CREATE TYPE volume_type AS ENUM ('gp3', 'io2');
CREATE TYPE volume_state AS ENUM ('available', 'attached', 'detaching');
CREATE TYPE snapshot_state AS ENUM ('creating', 'completed', 'failed');
CREATE TYPE review_result AS ENUM ('pending', 'passed', 'failed');

CREATE TABLE storage_instances (
    instance_id BIGSERIAL PRIMARY KEY,
    instance_name TEXT NOT NULL UNIQUE,
    availability_zone TEXT NOT NULL,
    environment TEXT NOT NULL
        CHECK (environment IN ('development', 'staging', 'production'))
);

CREATE TABLE volumes (
    volume_id BIGSERIAL PRIMARY KEY,
    volume_name TEXT NOT NULL UNIQUE,
    size_gib INTEGER NOT NULL CHECK (size_gib > 0),
    volume_type volume_type NOT NULL,
    provisioned_iops INTEGER NOT NULL CHECK (provisioned_iops > 0),
    throughput_mib_s INTEGER NOT NULL CHECK (throughput_mib_s > 0),
    encrypted BOOLEAN NOT NULL DEFAULT TRUE,
    state volume_state NOT NULL DEFAULT 'available',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (volume_type = 'gp3'
         AND provisioned_iops BETWEEN 3000 AND 16000
         AND throughput_mib_s BETWEEN 125 AND 1000)
        OR
        (volume_type = 'io2'
         AND provisioned_iops BETWEEN 100 AND 64000)
    )
);

CREATE TABLE volume_attachments (
    attachment_id BIGSERIAL PRIMARY KEY,
    volume_id BIGINT NOT NULL REFERENCES volumes(volume_id),
    instance_id BIGINT NOT NULL REFERENCES storage_instances(instance_id),
    device_name TEXT NOT NULL,
    attached_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    detached_at TIMESTAMPTZ,
    CHECK (device_name LIKE '/dev/%'),
    CHECK (
        detached_at IS NULL
        OR detached_at >= attached_at
    )
);

-- A volume can have only one active attachment in this model.
CREATE UNIQUE INDEX one_active_attachment_per_volume
ON volume_attachments(volume_id)
WHERE detached_at IS NULL;

CREATE INDEX volume_attachments_instance_idx
ON volume_attachments(instance_id)
WHERE detached_at IS NULL;

CREATE TABLE snapshots (
    snapshot_id BIGSERIAL PRIMARY KEY,
    snapshot_name TEXT NOT NULL UNIQUE,
    source_volume_id BIGINT NOT NULL REFERENCES volumes(volume_id),
    parent_snapshot_id BIGINT REFERENCES snapshots(snapshot_id),
    state snapshot_state NOT NULL DEFAULT 'creating',
    progress_percent INTEGER NOT NULL DEFAULT 0
        CHECK (progress_percent BETWEEN 0 AND 100),
    source_size_gib INTEGER NOT NULL CHECK (source_size_gib > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ
);

CREATE INDEX snapshots_source_volume_idx
ON snapshots(source_volume_id);

CREATE INDEX snapshots_parent_idx
ON snapshots(parent_snapshot_id);

CREATE TABLE storage_workloads (
    workload_id BIGSERIAL PRIMARY KEY,
    workload_name TEXT NOT NULL UNIQUE,
    volume_id BIGINT NOT NULL REFERENCES volumes(volume_id),
    requests_per_second BIGINT NOT NULL CHECK (requests_per_second >= 0),
    average_io_kib INTEGER NOT NULL CHECK (average_io_kib > 0),
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds > 0)
);

CREATE TABLE storage_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    policy_name TEXT NOT NULL UNIQUE,
    minimum_iops INTEGER NOT NULL CHECK (minimum_iops > 0),
    minimum_throughput_mib_s INTEGER NOT NULL CHECK (minimum_throughput_mib_s > 0),
    maximum_latency_ms NUMERIC(12, 3) NOT NULL
        CHECK (maximum_latency_ms > 0),
    require_encryption BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE policy_evaluations (
    evaluation_id BIGSERIAL PRIMARY KEY,
    policy_id BIGINT NOT NULL REFERENCES storage_policies(policy_id),
    volume_id BIGINT NOT NULL REFERENCES volumes(volume_id),
    workload_id BIGINT NOT NULL REFERENCES storage_workloads(workload_id),
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    passed BOOLEAN NOT NULL,
    failure_reason TEXT
);

CREATE INDEX policy_evaluations_volume_idx
ON policy_evaluations(volume_id, evaluated_at DESC);

-- The trigger keeps the volume lifecycle consistent with active attachments.
CREATE OR REPLACE FUNCTION enforce_volume_attachment_state()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF EXISTS (
            SELECT 1
            FROM volume_attachments
            WHERE volume_id = NEW.volume_id
              AND detached_at IS NULL
        ) THEN
            RAISE EXCEPTION
                'Volume % already has an active attachment',
                NEW.volume_id;
        END IF;

        UPDATE volumes
        SET state = 'attached'
        WHERE volume_id = NEW.volume_id;

        RETURN NEW;
    END IF;

    IF TG_OP = 'UPDATE' AND OLD.detached_at IS NULL
       AND NEW.detached_at IS NOT NULL THEN

        UPDATE volumes
        SET state = 'available'
        WHERE volume_id = NEW.volume_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER volume_attachment_state_trigger
AFTER INSERT OR UPDATE OF detached_at
ON volume_attachments
FOR EACH ROW
EXECUTE FUNCTION enforce_volume_attachment_state();

-- Snapshot completion is enforced by the database rather than trusting
-- application code to keep state and progress synchronized.
CREATE OR REPLACE FUNCTION validate_snapshot_state()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = 'completed' AND NEW.progress_percent <> 100 THEN
        RAISE EXCEPTION
            'Completed snapshot % must have 100 percent progress',
            NEW.snapshot_id;
    END IF;

    IF NEW.state <> 'completed' AND NEW.completed_at IS NOT NULL THEN
        RAISE EXCEPTION
            'Only completed snapshots may have completed_at';
    END IF;

    IF NEW.state = 'completed' AND NEW.completed_at IS NULL THEN
        NEW.completed_at := CURRENT_TIMESTAMP;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER snapshot_state_validation_trigger
BEFORE INSERT OR UPDATE
ON snapshots
FOR EACH ROW
EXECUTE FUNCTION validate_snapshot_state();

INSERT INTO storage_instances (
    instance_name,
    availability_zone,
    environment
)
VALUES
    ('db-production-01', 'ap-south-1a', 'production'),
    ('analytics-production-01', 'ap-south-1b', 'production'),
    ('app-staging-01', 'ap-south-1a', 'staging');

INSERT INTO volumes (
    volume_name,
    size_gib,
    volume_type,
    provisioned_iops,
    throughput_mib_s,
    encrypted
)
VALUES
    ('orders-db-data', 1024, 'gp3', 12000, 500, TRUE),
    ('orders-db-log', 256, 'gp3', 16000, 500, TRUE),
    ('analytics-data', 2048, 'io2', 16000, 500, TRUE),
    ('legacy-unencrypted-test', 100, 'gp3', 3000, 125, FALSE);

INSERT INTO volume_attachments (
    volume_id,
    instance_id,
    device_name
)
SELECT
    v.volume_id,
    i.instance_id,
    '/dev/sdf'
FROM volumes v
JOIN storage_instances i
    ON i.instance_name = 'db-production-01'
WHERE v.volume_name = 'orders-db-data';

INSERT INTO volume_attachments (
    volume_id,
    instance_id,
    device_name
)
SELECT
    v.volume_id,
    i.instance_id,
    '/dev/sdg'
FROM volumes v
JOIN storage_instances i
    ON i.instance_name = 'analytics-production-01'
WHERE v.volume_name = 'analytics-data';

INSERT INTO snapshots (
    snapshot_name,
    source_volume_id,
    parent_snapshot_id,
    state,
    progress_percent
)
SELECT
    'orders-db-data-baseline',
    volume_id,
    NULL,
    'completed',
    100
FROM volumes
WHERE volume_name = 'orders-db-data';

INSERT INTO snapshots (
    snapshot_name,
    source_volume_id,
    parent_snapshot_id,
    state,
    progress_percent
)
SELECT
    'orders-db-data-after-index-maintenance',
    v.volume_id,
    s.snapshot_id,
    'completed',
    100
FROM volumes v
JOIN snapshots s
    ON s.snapshot_name = 'orders-db-data-baseline'
WHERE v.volume_name = 'orders-db-data';

INSERT INTO storage_workloads (
    workload_name,
    volume_id,
    requests_per_second,
    average_io_kib,
    duration_seconds
)
SELECT
    'orders-api-random-read-write',
    volume_id,
    18000,
    16,
    60
FROM volumes
WHERE volume_name = 'orders-db-data';

INSERT INTO storage_workloads (
    workload_name,
    volume_id,
    requests_per_second,
    average_io_kib,
    duration_seconds
)
SELECT
    'analytics-large-read',
    volume_id,
    1000,
    512,
    300
FROM volumes
WHERE volume_name = 'analytics-data';

INSERT INTO storage_policies (
    policy_name,
    minimum_iops,
    minimum_throughput_mib_s,
    maximum_latency_ms,
    require_encryption
)
VALUES
    ('production-database', 8000, 250, 10.0, TRUE),
    ('analytics-throughput', 3000, 500, 15.0, TRUE);

-- Requested throughput is derived from IOPS multiplied by average I/O size.
-- This exposes whether a workload is approaching an IOPS or throughput limit.
CREATE VIEW workload_capacity_analysis AS
SELECT
    w.workload_name,
    v.volume_name,
    v.provisioned_iops,
    v.throughput_mib_s,
    w.requests_per_second,
    w.average_io_kib,
    ROUND(
        (w.requests_per_second * w.average_io_kib / 1024.0)::numeric,
        2
    ) AS requested_mib_s,
    ROUND(
        (w.requests_per_second::numeric / v.provisioned_iops),
        3
    ) AS iops_pressure,
    ROUND(
        (
            w.requests_per_second
            * w.average_io_kib
            / 1024.0
            / v.throughput_mib_s
        )::numeric,
        3
    ) AS throughput_pressure
FROM storage_workloads w
JOIN volumes v
    ON v.volume_id = w.volume_id;

SELECT *
FROM workload_capacity_analysis
ORDER BY workload_name;

-- Policy evaluation uses current volume characteristics and workload demand.
-- The query is intentionally explicit so each failed condition is visible.
WITH policy_input AS (
    SELECT
        p.policy_id,
        p.policy_name,
        p.minimum_iops,
        p.minimum_throughput_mib_s,
        p.maximum_latency_ms,
        p.require_encryption,
        v.volume_id,
        v.volume_name,
        v.provisioned_iops,
        v.throughput_mib_s,
        v.encrypted,
        w.workload_id,
        w.workload_name,
        w.requests_per_second,
        w.average_io_kib,
        GREATEST(
            w.requests_per_second::numeric / v.provisioned_iops,
            (
                w.requests_per_second
                * w.average_io_kib
                / 1024.0
                / v.throughput_mib_s
            )
        ) AS pressure
    FROM storage_policies p
    CROSS JOIN volumes v
    JOIN storage_workloads w
        ON w.volume_id = v.volume_id
    WHERE
        (
            p.policy_name = 'production-database'
            AND v.volume_name = 'orders-db-data'
        )
        OR
        (
            p.policy_name = 'analytics-throughput'
            AND v.volume_name = 'analytics-data'
        )
)
SELECT
    policy_name,
    volume_name,
    workload_name,
    provisioned_iops,
    throughput_mib_s,
    encrypted,
    ROUND(pressure, 3) AS bottleneck_pressure,
    (
        provisioned_iops >= minimum_iops
        AND throughput_mib_s >= minimum_throughput_mib_s
        AND (
            NOT require_encryption
            OR encrypted
        )
    ) AS capacity_and_security_requirements_met
FROM policy_input;

-- Snapshot lineage uses a recursive CTE. This is useful for audit trails,
-- backup relationships, and identifying the ancestry of a restored volume.
WITH RECURSIVE snapshot_lineage AS (
    SELECT
        s.snapshot_id,
        s.snapshot_name,
        s.parent_snapshot_id,
        0 AS depth
    FROM snapshots s
    WHERE s.snapshot_name = 'orders-db-data-after-index-maintenance'

    UNION ALL

    SELECT
        parent.snapshot_id,
        parent.snapshot_name,
        parent.parent_snapshot_id,
        child.depth + 1
    FROM snapshots parent
    JOIN snapshot_lineage child
        ON parent.snapshot_id = child.parent_snapshot_id
)
SELECT
    depth,
    snapshot_id,
    snapshot_name
FROM snapshot_lineage
ORDER BY depth;

-- A transaction demonstrates a safe performance change. The CHECK constraint
-- protects the database if an invalid configuration is attempted.
BEGIN;

UPDATE volumes
SET
    provisioned_iops = 16000,
    throughput_mib_s = 750
WHERE volume_name = 'orders-db-data';

SELECT
    volume_name,
    provisioned_iops,
    throughput_mib_s
FROM volumes
WHERE volume_name = 'orders-db-data';

COMMIT;

-- This statement is intentionally invalid and should fail because gp3 IOPS
-- cannot be below its configured minimum.
-- UPDATE volumes
-- SET provisioned_iops = 1000
-- WHERE volume_name = 'orders-db-data';

-- Demonstrate current attachment state.
SELECT
    v.volume_name,
    v.state,
    i.instance_name,
    a.device_name,
    a.attached_at
FROM volumes v
LEFT JOIN volume_attachments a
    ON a.volume_id = v.volume_id
   AND a.detached_at IS NULL
LEFT JOIN storage_instances i
    ON i.instance_id = a.instance_id
ORDER BY v.volume_name;

-- Demonstrate snapshot inventory and storage lineage metadata.
SELECT
    s.snapshot_name,
    v.volume_name AS source_volume,
    s.state,
    s.progress_percent,
    parent.snapshot_name AS parent_snapshot
FROM snapshots s
JOIN volumes v
    ON v.volume_id = s.source_volume_id
LEFT JOIN snapshots parent
    ON parent.snapshot_id = s.parent_snapshot_id
ORDER BY s.created_at;
