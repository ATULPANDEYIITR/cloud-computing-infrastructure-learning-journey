DROP SCHEMA IF EXISTS storage_demo CASCADE;
CREATE SCHEMA storage_demo;
SET search_path TO storage_demo;

-- The model separates the logical file namespace from physical storage
-- locations. This distinction becomes important when one file has multiple
-- distributed replicas.

CREATE TYPE storage_kind AS ENUM (
    'LOCAL_FILE',
    'NETWORK_FILE_SYSTEM',
    'DISTRIBUTED_FILE_SYSTEM'
);

CREATE TYPE node_status AS ENUM (
    'ONLINE',
    'FAILED',
    'MAINTENANCE'
);

CREATE TYPE file_status AS ENUM (
    'ACTIVE',
    'DELETED',
    'UNAVAILABLE'
);

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    storage_kind storage_kind NOT NULL,
    quota_bytes BIGINT NOT NULL CHECK (quota_bytes > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE storage_nodes (
    node_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    node_name TEXT NOT NULL,
    status node_status NOT NULL DEFAULT 'ONLINE',
    capacity_bytes BIGINT NOT NULL CHECK (capacity_bytes > 0),
    used_bytes BIGINT NOT NULL DEFAULT 0
        CHECK (used_bytes >= 0 AND used_bytes <= capacity_bytes),
    UNIQUE (repository_id, node_name)
);

CREATE TABLE files (
    file_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    logical_path TEXT NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    checksum_sha256 CHAR(64) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    status file_status NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (repository_id, logical_path)
);

CREATE TABLE file_chunks (
    chunk_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_id BIGINT NOT NULL
        REFERENCES files(file_id)
        ON DELETE CASCADE,
    chunk_number INTEGER NOT NULL CHECK (chunk_number >= 0),
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    checksum_sha256 CHAR(64) NOT NULL,
    UNIQUE (file_id, chunk_number)
);

CREATE TABLE chunk_replicas (
    chunk_id BIGINT NOT NULL
        REFERENCES file_chunks(chunk_id)
        ON DELETE CASCADE,
    node_id BIGINT NOT NULL
        REFERENCES storage_nodes(node_id)
        ON DELETE RESTRICT,
    replica_state TEXT NOT NULL DEFAULT 'AVAILABLE'
        CHECK (replica_state IN ('AVAILABLE', 'CORRUPTED', 'MISSING')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (chunk_id, node_id)
);

CREATE TABLE file_access_log (
    access_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_id BIGINT NOT NULL
        REFERENCES files(file_id)
        ON DELETE CASCADE,
    client_name TEXT NOT NULL,
    operation TEXT NOT NULL
        CHECK (operation IN ('READ', 'WRITE', 'DELETE')),
    success BOOLEAN NOT NULL,
    failure_reason TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        success = TRUE
        OR failure_reason IS NOT NULL
    )
);

CREATE INDEX idx_files_repository_path
    ON files(repository_id, logical_path);

CREATE INDEX idx_file_chunks_file
    ON file_chunks(file_id, chunk_number);

CREATE INDEX idx_chunk_replicas_node
    ON chunk_replicas(node_id);

CREATE INDEX idx_access_log_file_time
    ON file_access_log(file_id, occurred_at DESC);

-- A distributed repository must not accept a physical node with a capacity
-- below zero or a used amount above its capacity. The table constraints
-- enforce the local invariant regardless of application behavior.

CREATE OR REPLACE FUNCTION record_node_usage(
    p_node_id BIGINT,
    p_delta BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    current_used BIGINT;
    node_capacity BIGINT;
BEGIN
    SELECT used_bytes, capacity_bytes
    INTO current_used, node_capacity
    FROM storage_nodes
    WHERE node_id = p_node_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Storage node % does not exist', p_node_id;
    END IF;

    IF current_used + p_delta < 0 THEN
        RAISE EXCEPTION 'Node usage cannot become negative';
    END IF;

    IF current_used + p_delta > node_capacity THEN
        RAISE EXCEPTION 'Node capacity exceeded';
    END IF;

    UPDATE storage_nodes
    SET used_bytes = current_used + p_delta
    WHERE node_id = p_node_id;
END;
$$;

CREATE VIEW file_replica_health AS
SELECT
    f.file_id,
    f.logical_path,
    fc.chunk_number,
    COUNT(cr.node_id)
        FILTER (
            WHERE sn.status = 'ONLINE'
              AND cr.replica_state = 'AVAILABLE'
        ) AS healthy_replicas,
    COUNT(cr.node_id) AS configured_replicas
FROM files f
JOIN file_chunks fc
    ON fc.file_id = f.file_id
LEFT JOIN chunk_replicas cr
    ON cr.chunk_id = fc.chunk_id
LEFT JOIN storage_nodes sn
    ON sn.node_id = cr.node_id
GROUP BY
    f.file_id,
    f.logical_path,
    fc.chunk_number;

CREATE OR REPLACE FUNCTION validate_file_readable(
    p_file_id BIGINT,
    p_required_replicas INTEGER DEFAULT 1
)
RETURNS BOOLEAN
LANGUAGE sql
AS $$
    SELECT NOT EXISTS (
        SELECT 1
        FROM file_chunks fc
        WHERE fc.file_id = p_file_id
          AND (
              SELECT COUNT(*)
              FROM chunk_replicas cr
              JOIN storage_nodes sn
                ON sn.node_id = cr.node_id
              WHERE cr.chunk_id = fc.chunk_id
                AND cr.replica_state = 'AVAILABLE'
                AND sn.status = 'ONLINE'
          ) < p_required_replicas
    );
$$;

INSERT INTO repositories (
    repository_name,
    storage_kind,
    quota_bytes
)
VALUES
    ('engineering-share', 'NETWORK_FILE_SYSTEM', 500000),
    ('analytics-distributed', 'DISTRIBUTED_FILE_SYSTEM', 5000000);

INSERT INTO storage_nodes (
    repository_id,
    node_name,
    capacity_bytes
)
SELECT
    r.repository_id,
    v.node_name,
    v.capacity_bytes
FROM repositories r
JOIN (
    VALUES
        ('engineering-share', 'file-server-01', 500000),
        ('analytics-distributed', 'storage-a', 2000000),
        ('analytics-distributed', 'storage-b', 2000000),
        ('analytics-distributed', 'storage-c', 2000000)
) AS v(repository_name, node_name, capacity_bytes)
ON v.repository_name = r.repository_name;

INSERT INTO files (
    repository_id,
    logical_path,
    size_bytes,
    checksum_sha256,
    version
)
SELECT
    repository_id,
    '/research/experiment.txt',
    120,
    repeat('a', 64),
    1
FROM repositories
WHERE repository_name = 'engineering-share';

INSERT INTO files (
    repository_id,
    logical_path,
    size_bytes,
    checksum_sha256,
    version
)
SELECT
    repository_id,
    '/datasets/events.bin',
    250,
    repeat('b', 64),
    3
FROM repositories
WHERE repository_name = 'analytics-distributed';

INSERT INTO file_chunks (
    file_id,
    chunk_number,
    size_bytes,
    checksum_sha256
)
SELECT file_id, 0, 120, repeat('c', 64)
FROM files
WHERE logical_path = '/research/experiment.txt';

INSERT INTO file_chunks (
    file_id,
    chunk_number,
    size_bytes,
    checksum_sha256
)
SELECT file_id, chunk_number, size_bytes, repeat('d', 64)
FROM files
CROSS JOIN (
    VALUES
        (0, 128),
        (1, 122)
) AS chunks(chunk_number, size_bytes)
WHERE logical_path = '/datasets/events.bin';

INSERT INTO chunk_replicas (
    chunk_id,
    node_id,
    replica_state
)
SELECT
    fc.chunk_id,
    sn.node_id,
    'AVAILABLE'
FROM file_chunks fc
JOIN files f
    ON f.file_id = fc.file_id
JOIN repositories r
    ON r.repository_id = f.repository_id
JOIN storage_nodes sn
    ON sn.repository_id = r.repository_id
WHERE f.logical_path = '/research/experiment.txt'
  AND sn.node_name = 'file-server-01';

INSERT INTO chunk_replicas (
    chunk_id,
    node_id,
    replica_state
)
SELECT
    fc.chunk_id,
    sn.node_id,
    'AVAILABLE'
FROM file_chunks fc
JOIN files f
    ON f.file_id = fc.file_id
JOIN storage_nodes sn
    ON sn.repository_id = f.repository_id
WHERE f.logical_path = '/datasets/events.bin'
  AND sn.node_name IN ('storage-a', 'storage-b');

INSERT INTO file_access_log (
    file_id,
    client_name,
    operation,
    success,
    failure_reason
)
SELECT
    file_id,
    'analytics-worker-01',
    'READ',
    TRUE,
    NULL
FROM files
WHERE logical_path = '/datasets/events.bin';

-- Simulate a failed storage node. The distributed file remains readable when
-- another replica for every chunk remains healthy.
UPDATE storage_nodes
SET status = 'FAILED'
WHERE node_name = 'storage-a';

SELECT
    logical_path,
    chunk_number,
    healthy_replicas,
    configured_replicas,
    CASE
        WHEN healthy_replicas >= 1 THEN 'READABLE'
        ELSE 'UNAVAILABLE'
    END AS availability
FROM file_replica_health
ORDER BY logical_path, chunk_number;

SELECT
    f.logical_path,
    validate_file_readable(f.file_id, 1) AS readable_with_one_replica,
    validate_file_readable(f.file_id, 2) AS readable_with_two_replicas
FROM files f;

-- This transaction demonstrates a metadata update that is only committed
-- after the database verifies the new node usage.
BEGIN;

SELECT record_node_usage(
    (
        SELECT node_id
        FROM storage_nodes
        WHERE node_name = 'storage-c'
    ),
    250
);

UPDATE files
SET version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE logical_path = '/datasets/events.bin';

COMMIT;

-- Query the physical placement of every chunk. A logical file can have
-- several physical locations without changing its logical pathname.
SELECT
    f.logical_path,
    fc.chunk_number,
    sn.node_name,
    sn.status,
    cr.replica_state
FROM files f
JOIN file_chunks fc
    ON fc.file_id = f.file_id
JOIN chunk_replicas cr
    ON cr.chunk_id = fc.chunk_id
JOIN storage_nodes sn
    ON sn.node_id = cr.node_id
ORDER BY
    f.logical_path,
    fc.chunk_number,
    sn.node_name;

-- Identify chunks whose configured replication has degraded.
SELECT
    logical_path,
    chunk_number,
    configured_replicas,
    healthy_replicas
FROM file_replica_health
WHERE healthy_replicas < configured_replicas
ORDER BY logical_path, chunk_number;

-- Database-level validation exposes the remaining availability boundary:
-- after both replicas for a chunk are failed, the file becomes unreadable.
UPDATE storage_nodes
SET status = 'FAILED'
WHERE node_name = 'storage-b';

SELECT
    logical_path,
    validate_file_readable(file_id, 1) AS readable_after_second_failure
FROM files
WHERE logical_path = '/datasets/events.bin';
