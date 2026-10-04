-- PostgreSQL 15+ compatible Storage Virtualization Laboratory
--
-- The model represents:
--
-- physical devices
--      -> storage pools
--          -> logical volumes
--              -> virtual disks
--                  -> logical blocks
--
-- Governance and integrity rules are enforced at the database layer where
-- relational constraints can express them reliably.

DROP SCHEMA IF EXISTS storage_virtualization CASCADE;

CREATE SCHEMA storage_virtualization;

SET search_path TO storage_virtualization;

CREATE TYPE device_state AS ENUM (
    'online',
    'degraded',
    'failed'
);

CREATE TYPE volume_mode AS ENUM (
    'thick',
    'thin'
);

CREATE TYPE volume_state AS ENUM (
    'online',
    'read_only',
    'offline'
);

CREATE TABLE storage_pool (
    pool_id          BIGSERIAL PRIMARY KEY,
    pool_name        TEXT NOT NULL UNIQUE,
    extent_size_gb   INTEGER NOT NULL CHECK (extent_size_gb > 0),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE physical_device (
    device_id        BIGSERIAL PRIMARY KEY,
    pool_id          BIGINT NOT NULL
        REFERENCES storage_pool(pool_id)
        ON DELETE RESTRICT,
    device_name      TEXT NOT NULL,
    capacity_gb      INTEGER NOT NULL CHECK (capacity_gb > 0),
    used_gb          INTEGER NOT NULL DEFAULT 0
        CHECK (used_gb >= 0 AND used_gb <= capacity_gb),
    state            device_state NOT NULL DEFAULT 'online',
    read_iops        INTEGER NOT NULL CHECK (read_iops > 0),
    write_iops       INTEGER NOT NULL CHECK (write_iops > 0),
    UNIQUE (pool_id, device_name)
);

CREATE TABLE logical_volume (
    volume_id             BIGSERIAL PRIMARY KEY,
    pool_id               BIGINT NOT NULL
        REFERENCES storage_pool(pool_id)
        ON DELETE RESTRICT,
    volume_name            TEXT NOT NULL,
    virtual_capacity_gb    INTEGER NOT NULL
        CHECK (virtual_capacity_gb > 0),
    mode                   volume_mode NOT NULL,
    state                  volume_state NOT NULL DEFAULT 'online',
    created_at             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (pool_id, volume_name)
);

CREATE TABLE virtual_disk (
    virtual_disk_id BIGSERIAL PRIMARY KEY,
    volume_id       BIGINT NOT NULL
        REFERENCES logical_volume(volume_id)
        ON DELETE RESTRICT,
    disk_name       TEXT NOT NULL UNIQUE,
    sector_size     INTEGER NOT NULL DEFAULT 4096
        CHECK (sector_size IN (512, 4096)),
    attached_to     TEXT
);

CREATE TABLE storage_extent (
    extent_id       BIGSERIAL PRIMARY KEY,
    pool_id         BIGINT NOT NULL
        REFERENCES storage_pool(pool_id)
        ON DELETE RESTRICT,
    volume_id       BIGINT NOT NULL
        REFERENCES logical_volume(volume_id)
        ON DELETE RESTRICT,
    device_id       BIGINT NOT NULL
        REFERENCES physical_device(device_id)
        ON DELETE RESTRICT,
    start_gb        INTEGER NOT NULL CHECK (start_gb >= 0),
    size_gb         INTEGER NOT NULL CHECK (size_gb > 0),
    UNIQUE (device_id, start_gb)
);

CREATE TABLE logical_block (
    block_id        BIGSERIAL PRIMARY KEY,
    volume_id       BIGINT NOT NULL
        REFERENCES logical_volume(volume_id)
        ON DELETE CASCADE,
    logical_block   BIGINT NOT NULL CHECK (logical_block >= 0),
    payload         TEXT NOT NULL,
    generation      BIGINT NOT NULL CHECK (generation > 0),
    checksum        TEXT NOT NULL,
    UNIQUE (volume_id, logical_block)
);

CREATE TABLE storage_snapshot (
    snapshot_id     BIGSERIAL PRIMARY KEY,
    volume_id       BIGINT NOT NULL
        REFERENCES logical_volume(volume_id)
        ON DELETE RESTRICT,
    snapshot_name   TEXT NOT NULL,
    generation      BIGINT NOT NULL CHECK (generation >= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (volume_id, snapshot_name)
);

CREATE TABLE snapshot_block (
    snapshot_id     BIGINT NOT NULL
        REFERENCES storage_snapshot(snapshot_id)
        ON DELETE CASCADE,
    logical_block   BIGINT NOT NULL CHECK (logical_block >= 0),
    checksum        TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, logical_block)
);

CREATE INDEX idx_device_pool_state
    ON physical_device(pool_id, state);

CREATE INDEX idx_volume_pool_mode
    ON logical_volume(pool_id, mode);

CREATE INDEX idx_extent_device
    ON storage_extent(device_id);

CREATE INDEX idx_extent_volume
    ON storage_extent(volume_id);

CREATE INDEX idx_logical_block_volume_block
    ON logical_block(volume_id, logical_block);

CREATE INDEX idx_snapshot_volume
    ON storage_snapshot(volume_id);

CREATE VIEW pool_capacity AS
SELECT
    p.pool_id,
    p.pool_name,
    COALESCE(SUM(d.capacity_gb), 0) AS physical_capacity_gb,
    COALESCE(SUM(d.used_gb), 0) AS physical_used_gb,
    COALESCE(SUM(d.capacity_gb - d.used_gb), 0)
        AS physical_free_gb
FROM storage_pool p
LEFT JOIN physical_device d
    ON d.pool_id = p.pool_id
GROUP BY p.pool_id, p.pool_name;

CREATE VIEW volume_capacity AS
SELECT
    v.volume_id,
    v.volume_name,
    v.virtual_capacity_gb,
    v.mode,
    v.state,
    COALESCE(SUM(e.size_gb), 0) AS physically_allocated_gb
FROM logical_volume v
LEFT JOIN storage_extent e
    ON e.volume_id = v.volume_id
GROUP BY
    v.volume_id,
    v.volume_name,
    v.virtual_capacity_gb,
    v.mode,
    v.state;

CREATE OR REPLACE FUNCTION prevent_failed_device_allocation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM physical_device
        WHERE device_id = NEW.device_id
          AND state = 'failed'
    ) THEN
        RAISE EXCEPTION
            'Cannot allocate extent on failed device %',
            NEW.device_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_prevent_failed_device_allocation
BEFORE INSERT OR UPDATE ON storage_extent
FOR EACH ROW
EXECUTE FUNCTION prevent_failed_device_allocation();

CREATE OR REPLACE FUNCTION synchronize_device_usage()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    delta INTEGER;
BEGIN
    IF TG_OP = 'INSERT' THEN
        delta := NEW.size_gb;

        UPDATE physical_device
        SET used_gb = used_gb + delta
        WHERE device_id = NEW.device_id;

        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        UPDATE physical_device
        SET used_gb = used_gb - OLD.size_gb
        WHERE device_id = OLD.device_id;

        RETURN OLD;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF NEW.device_id = OLD.device_id THEN
            UPDATE physical_device
            SET used_gb = used_gb - OLD.size_gb + NEW.size_gb
            WHERE device_id = NEW.device_id;
        ELSE
            UPDATE physical_device
            SET used_gb = used_gb - OLD.size_gb
            WHERE device_id = OLD.device_id;

            UPDATE physical_device
            SET used_gb = used_gb + NEW.size_gb
            WHERE device_id = NEW.device_id;
        END IF;

        RETURN NEW;
    END IF;

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_synchronize_device_usage
AFTER INSERT OR UPDATE OR DELETE ON storage_extent
FOR EACH ROW
EXECUTE FUNCTION synchronize_device_usage();

INSERT INTO storage_pool (
    pool_name,
    extent_size_gb
)
VALUES
    ('production-pool', 1),
    ('archive-pool', 2);

INSERT INTO physical_device (
    pool_id,
    device_name,
    capacity_gb,
    read_iops,
    write_iops
)
SELECT
    p.pool_id,
    x.device_name,
    x.capacity_gb,
    x.read_iops,
    x.write_iops
FROM storage_pool p
JOIN (
    VALUES
        ('production-pool', 'nvme-01', 12, 90000, 70000),
        ('production-pool', 'nvme-02', 16, 85000, 65000),
        ('production-pool', 'ssd-archive', 24, 40000, 30000),
        ('archive-pool', 'archive-01', 40, 20000, 15000)
) AS x(
    pool_name,
    device_name,
    capacity_gb,
    read_iops,
    write_iops
)
ON x.pool_name = p.pool_name;

INSERT INTO logical_volume (
    pool_id,
    volume_name,
    virtual_capacity_gb,
    mode
)
SELECT
    pool_id,
    'production-db',
    8,
    'thick'
FROM storage_pool
WHERE pool_name = 'production-pool';

INSERT INTO logical_volume (
    pool_id,
    volume_name,
    virtual_capacity_gb,
    mode
)
SELECT
    pool_id,
    'event-stream',
    20,
    'thin'
FROM storage_pool
WHERE pool_name = 'production-pool';

INSERT INTO logical_volume (
    pool_id,
    volume_name,
    virtual_capacity_gb,
    mode
)
SELECT
    pool_id,
    'long-term-data',
    30,
    'thin'
FROM storage_pool
WHERE pool_name = 'archive-pool';

INSERT INTO virtual_disk (
    volume_id,
    disk_name,
    sector_size,
    attached_to
)
SELECT
    volume_id,
    'vdisk-db-01',
    4096,
    'database-vm-01'
FROM logical_volume
WHERE volume_name = 'production-db';

INSERT INTO virtual_disk (
    volume_id,
    disk_name,
    sector_size,
    attached_to
)
SELECT
    volume_id,
    'vdisk-events-01',
    4096,
    'streaming-vm-01'
FROM logical_volume
WHERE volume_name = 'event-stream';

-- Thick provisioning consumes physical extents immediately.
INSERT INTO storage_extent (
    pool_id,
    volume_id,
    device_id,
    start_gb,
    size_gb
)
SELECT
    v.pool_id,
    v.volume_id,
    d.device_id,
    COALESCE(
        (
            SELECT MAX(e.start_gb + e.size_gb)
            FROM storage_extent e
            WHERE e.device_id = d.device_id
        ),
        0
    ),
    1
FROM logical_volume v
JOIN physical_device d
    ON d.pool_id = v.pool_id
WHERE v.volume_name = 'production-db'
  AND d.device_name IN ('nvme-01', 'nvme-02')
  AND (
      SELECT COUNT(*)
      FROM storage_extent e
      WHERE e.volume_id = v.volume_id
  ) < 8
LIMIT 8;

-- Thin provisioning allocates only the extents needed by actual writes.
INSERT INTO storage_extent (
    pool_id,
    volume_id,
    device_id,
    start_gb,
    size_gb
)
SELECT
    v.pool_id,
    v.volume_id,
    d.device_id,
    COALESCE(
        (
            SELECT MAX(e.start_gb + e.size_gb)
            FROM storage_extent e
            WHERE e.device_id = d.device_id
        ),
        0
    ),
    1
FROM logical_volume v
JOIN physical_device d
    ON d.pool_id = v.pool_id
WHERE v.volume_name = 'event-stream'
  AND d.device_name = 'ssd-archive'
LIMIT 2;

INSERT INTO logical_block (
    volume_id,
    logical_block,
    payload,
    generation,
    checksum
)
SELECT
    v.volume_id,
    x.logical_block,
    x.payload,
    x.generation,
    md5(x.payload)
FROM logical_volume v
JOIN (
    VALUES
        (0::BIGINT, 'database-superblock', 1::BIGINT),
        (1::BIGINT, 'database-catalog', 2::BIGINT),
        (2::BIGINT, 'transaction-log-header', 3::BIGINT)
) AS x(logical_block, payload, generation)
ON TRUE
WHERE v.volume_name = 'production-db';

INSERT INTO logical_block (
    volume_id,
    logical_block,
    payload,
    generation,
    checksum
)
SELECT
    v.volume_id,
    x.logical_block,
    x.payload,
    x.generation,
    md5(x.payload)
FROM logical_volume v
JOIN (
    VALUES
        (64::BIGINT, 'event-2026-10-05', 4::BIGINT),
        (65::BIGINT, 'event-2026-10-05-follow-up', 5::BIGINT)
) AS x(logical_block, payload, generation)
ON TRUE
WHERE v.volume_name = 'event-stream';

INSERT INTO storage_snapshot (
    volume_id,
    snapshot_name,
    generation
)
SELECT
    volume_id,
    'production-db-before-upgrade',
    3
FROM logical_volume
WHERE volume_name = 'production-db';

INSERT INTO snapshot_block (
    snapshot_id,
    logical_block,
    checksum
)
SELECT
    s.snapshot_id,
    b.logical_block,
    b.checksum
FROM storage_snapshot s
JOIN logical_block b
    ON b.volume_id = s.volume_id
WHERE s.snapshot_name = 'production-db-before-upgrade'
  AND b.generation <= s.generation;

-- Virtual capacity can exceed current physical allocation for thin volumes.
SELECT
    volume_name,
    virtual_capacity_gb,
    physically_allocated_gb,
    mode,
    ROUND(
        physically_allocated_gb::numeric
        / virtual_capacity_gb * 100,
        2
    ) AS physical_consumption_percent
FROM volume_capacity
ORDER BY volume_name;

-- Physical pool utilization shows the actual storage consumption.
SELECT
    pool_name,
    physical_capacity_gb,
    physical_used_gb,
    physical_free_gb,
    ROUND(
        physical_used_gb::numeric
        / NULLIF(physical_capacity_gb, 0) * 100,
        2
    ) AS utilization_percent
FROM pool_capacity
ORDER BY pool_name;

-- The logical-to-physical mapping is the central abstraction boundary.
SELECT
    v.volume_name,
    b.logical_block,
    e.extent_id,
    e.device_id,
    e.start_gb,
    e.size_gb,
    b.payload
FROM logical_block b
JOIN logical_volume v
    ON v.volume_id = b.volume_id
JOIN storage_extent e
    ON e.volume_id = v.volume_id
ORDER BY
    v.volume_name,
    b.logical_block,
    e.extent_id;

-- Integrity verification compares snapshot checksums with current blocks.
SELECT
    s.snapshot_name,
    sb.logical_block,
    sb.checksum AS snapshot_checksum,
    b.checksum AS current_checksum,
    sb.checksum = b.checksum AS unchanged
FROM snapshot_block sb
JOIN storage_snapshot s
    ON s.snapshot_id = sb.snapshot_id
JOIN logical_block b
    ON b.volume_id = s.volume_id
   AND b.logical_block = sb.logical_block
WHERE s.snapshot_name = 'production-db-before-upgrade';

-- Demonstrate a transaction that moves an extent while preserving usage
-- accounting. PostgreSQL rolls the whole operation back if any constraint
-- or business rule fails.
BEGIN;

WITH selected_extent AS (
    SELECT
        e.extent_id,
        e.device_id,
        e.size_gb
    FROM storage_extent e
    JOIN logical_volume v
        ON v.volume_id = e.volume_id
    WHERE v.volume_name = 'production-db'
    ORDER BY e.extent_id
    LIMIT 1
),
target_device AS (
    SELECT d.device_id
    FROM physical_device d
    JOIN storage_pool p
        ON p.pool_id = d.pool_id
    JOIN logical_volume v
        ON v.pool_id = p.pool_id
    WHERE v.volume_name = 'production-db'
      AND d.state = 'online'
      AND d.device_id <> (
          SELECT device_id
          FROM selected_extent
      )
      AND d.capacity_gb - d.used_gb >= (
          SELECT size_gb
          FROM selected_extent
      )
    ORDER BY
        (d.used_gb::numeric / d.capacity_gb),
        d.device_id
    LIMIT 1
)
UPDATE storage_extent e
SET
    device_id = t.device_id,
    start_gb = COALESCE(
        (
            SELECT MAX(existing.start_gb + existing.size_gb)
            FROM storage_extent existing
            WHERE existing.device_id = t.device_id
              AND existing.extent_id <> e.extent_id
        ),
        0
    )
FROM target_device t
WHERE e.extent_id = (
    SELECT extent_id
    FROM selected_extent
);

COMMIT;

-- Failure state is represented separately from the logical volume identity.
UPDATE physical_device
SET state = 'failed'
WHERE device_name = 'nvme-01';

-- Volumes containing extents on the failed device become read-only in this
-- demonstration. The UPDATE is deliberately data-driven.
UPDATE logical_volume v
SET state = 'read_only'
WHERE EXISTS (
    SELECT 1
    FROM storage_extent e
    JOIN physical_device d
        ON d.device_id = e.device_id
    WHERE e.volume_id = v.volume_id
      AND d.state = 'failed'
);

SELECT
    v.volume_name,
    v.mode,
    v.state,
    COUNT(e.extent_id) AS extent_count,
    COUNT(DISTINCT e.device_id) AS physical_device_count
FROM logical_volume v
LEFT JOIN storage_extent e
    ON e.volume_id = v.volume_id
GROUP BY
    v.volume_name,
    v.mode,
    v.state
ORDER BY v.volume_name;

-- Invalid state demonstration.
-- This statement is intentionally commented out because it would violate
-- the trigger that prevents allocations on failed physical devices.
--
-- INSERT INTO storage_extent (
--     pool_id,
--     volume_id,
--     device_id,
--     start_gb,
--     size_gb
-- )
-- SELECT
--     p.pool_id,
--     v.volume_id,
--     d.device_id,
--     99,
--     1
-- FROM storage_pool p
-- JOIN logical_volume v ON v.pool_id = p.pool_id
-- JOIN physical_device d ON d.pool_id = p.pool_id
-- WHERE d.state = 'failed'
--   AND v.volume_name = 'production-db';

-- Final inventory exposes both the virtual and physical perspectives.
SELECT
    p.pool_name,
    p.physical_capacity_gb,
    p.physical_used_gb,
    p.physical_free_gb,
    COUNT(v.volume_id) AS logical_volume_count,
    COALESCE(
        SUM(v.virtual_capacity_gb),
        0
    ) AS total_virtual_capacity_gb
FROM pool_capacity p
LEFT JOIN logical_volume v
    ON v.pool_id = p.pool_id
GROUP BY
    p.pool_name,
    p.physical_capacity_gb,
    p.physical_used_gb,
    p.physical_free_gb
ORDER BY p.pool_name;
