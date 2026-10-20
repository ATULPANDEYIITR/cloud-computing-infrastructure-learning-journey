DROP SCHEMA IF EXISTS storage_optimization CASCADE;
CREATE SCHEMA storage_optimization;
SET search_path TO storage_optimization;

-- Storage tiers separate physical performance characteristics from workloads.
CREATE TABLE storage_tiers (
    tier_id              BIGSERIAL PRIMARY KEY,
    tier_name            TEXT NOT NULL UNIQUE,
    max_iops             NUMERIC(14,2) NOT NULL CHECK (max_iops > 0),
    max_throughput_mbps  NUMERIC(14,2) NOT NULL CHECK (max_throughput_mbps > 0),
    latency_ms           NUMERIC(12,4) NOT NULL CHECK (latency_ms > 0),
    monthly_cost_per_gb  NUMERIC(12,5) NOT NULL CHECK (monthly_cost_per_gb >= 0)
);

INSERT INTO storage_tiers
    (tier_name, max_iops, max_throughput_mbps, latency_ms, monthly_cost_per_gb)
VALUES
    ('HDD',       180,     220,  8.0000, 0.02000),
    ('SATA SSD',  75000,   550,  0.1000, 0.08000),
    ('NVMe SSD',  800000, 7000,  0.0250, 0.15000);

CREATE TABLE storage_workloads (
    workload_id             BIGSERIAL PRIMARY KEY,
    workload_name           TEXT NOT NULL UNIQUE,
    required_iops            NUMERIC(14,2) NOT NULL CHECK (required_iops >= 0),
    required_throughput_mbps NUMERIC(14,2) NOT NULL CHECK (required_throughput_mbps >= 0),
    capacity_gb              NUMERIC(14,2) NOT NULL CHECK (capacity_gb > 0),
    max_monthly_cost         NUMERIC(14,2) CHECK (max_monthly_cost >= 0),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO storage_workloads
    (workload_name, required_iops, required_throughput_mbps, capacity_gb, max_monthly_cost)
VALUES
    ('Transactional customer database', 120000, 1500, 2000, 1000),
    ('Media archive', 300, 400, 10000, 500),
    ('Analytics scratch workload', 400000, 5000, 3000, 1000);

CREATE TABLE storage_devices (
    device_id       BIGSERIAL PRIMARY KEY,
    device_name     TEXT NOT NULL UNIQUE,
    tier_id         BIGINT NOT NULL REFERENCES storage_tiers(tier_id),
    capacity_gb     NUMERIC(14,2) NOT NULL CHECK (capacity_gb > 0),
    active          BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO storage_devices (device_name, tier_id, capacity_gb)
SELECT
    'nvme-primary',
    tier_id,
    2000
FROM storage_tiers
WHERE tier_name = 'NVMe SSD';

INSERT INTO storage_devices (device_name, tier_id, capacity_gb)
SELECT
    'archive-hdd',
    tier_id,
    10000
FROM storage_tiers
WHERE tier_name = 'HDD';

CREATE TABLE io_operations (
    operation_id    BIGSERIAL PRIMARY KEY,
    device_id       BIGINT NOT NULL REFERENCES storage_devices(device_id),
    operation_type  TEXT NOT NULL CHECK (operation_type IN ('READ', 'WRITE')),
    object_key      TEXT NOT NULL,
    size_kb         INTEGER NOT NULL CHECK (size_kb > 0 AND size_kb <= 1048576),
    cache_hit       BOOLEAN,
    latency_ms      NUMERIC(14,4) CHECK (latency_ms >= 0),
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_io_device_time
    ON io_operations (device_id, occurred_at);

CREATE INDEX idx_io_object_key
    ON io_operations (object_key);

CREATE TABLE cache_events (
    cache_event_id BIGSERIAL PRIMARY KEY,
    object_key     TEXT NOT NULL,
    event_type     TEXT NOT NULL CHECK (
        event_type IN ('HIT', 'MISS', 'EVICTION', 'WRITE_THROUGH')
    ),
    event_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE benchmark_runs (
    benchmark_id       BIGSERIAL PRIMARY KEY,
    device_id          BIGINT NOT NULL REFERENCES storage_devices(device_id),
    workload_id        BIGINT REFERENCES storage_workloads(workload_id),
    request_count      BIGINT NOT NULL CHECK (request_count > 0),
    average_latency_ms NUMERIC(14,4) CHECK (average_latency_ms >= 0),
    measured_iops      NUMERIC(14,2) CHECK (measured_iops >= 0),
    measured_mbps      NUMERIC(14,2) CHECK (measured_mbps >= 0),
    cache_hit_ratio    NUMERIC(7,6) CHECK (cache_hit_ratio BETWEEN 0 AND 1),
    measured_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Trigger derives latency from the selected tier and request size.
CREATE OR REPLACE FUNCTION calculate_io_latency()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    tier_record storage_tiers%ROWTYPE;
    transfer_ms NUMERIC;
BEGIN
    SELECT t.*
    INTO tier_record
    FROM storage_devices d
    JOIN storage_tiers t ON t.tier_id = d.tier_id
    WHERE d.device_id = NEW.device_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Device % has no valid storage tier', NEW.device_id;
    END IF;

    IF NEW.operation_type = 'READ' AND NEW.cache_hit IS TRUE THEN
        NEW.latency_ms :=
            GREATEST(0.05, tier_record.latency_ms * 0.10);
    ELSE
        transfer_ms :=
            (NEW.size_kb / 1024.0)
            / tier_record.max_throughput_mbps
            * 1000.0;

        NEW.latency_ms :=
            tier_record.latency_ms + transfer_ms;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_calculate_io_latency
BEFORE INSERT ON io_operations
FOR EACH ROW
EXECUTE FUNCTION calculate_io_latency();

-- Choose the cheapest tier satisfying both performance and cost constraints.
CREATE OR REPLACE FUNCTION recommend_storage_tier(
    p_required_iops NUMERIC,
    p_required_mbps NUMERIC,
    p_capacity_gb NUMERIC,
    p_max_monthly_cost NUMERIC DEFAULT NULL
)
RETURNS TABLE (
    tier_id BIGINT,
    tier_name TEXT,
    estimated_monthly_cost NUMERIC,
    max_iops NUMERIC,
    max_throughput_mbps NUMERIC,
    latency_ms NUMERIC
)
LANGUAGE sql
AS $$
    SELECT
        t.tier_id,
        t.tier_name,
        ROUND(t.monthly_cost_per_gb * p_capacity_gb, 2),
        t.max_iops,
        t.max_throughput_mbps,
        t.latency_ms
    FROM storage_tiers t
    WHERE t.max_iops >= p_required_iops
      AND t.max_throughput_mbps >= p_required_mbps
      AND (
          p_max_monthly_cost IS NULL
          OR t.monthly_cost_per_gb * p_capacity_gb <= p_max_monthly_cost
      )
    ORDER BY t.monthly_cost_per_gb
    LIMIT 1;
$$;

-- Demonstrate normal I/O operations and cache effects.
INSERT INTO io_operations
    (device_id, operation_type, object_key, size_kb, cache_hit)
SELECT
    device_id, 'READ', 'customer:1001', 8, FALSE
FROM storage_devices
WHERE device_name = 'nvme-primary';

INSERT INTO io_operations
    (device_id, operation_type, object_key, size_kb, cache_hit)
SELECT
    device_id, 'READ', 'customer:1001', 8, TRUE
FROM storage_devices
WHERE device_name = 'nvme-primary';

INSERT INTO io_operations
    (device_id, operation_type, object_key, size_kb, cache_hit)
SELECT
    device_id, 'WRITE', 'customer:1001', 64, FALSE
FROM storage_devices
WHERE device_name = 'nvme-primary';

INSERT INTO cache_events (object_key, event_type)
VALUES
    ('customer:1001', 'MISS'),
    ('customer:1001', 'HIT'),
    ('customer:1001', 'WRITE_THROUGH');

-- Store representative benchmark observations.
INSERT INTO benchmark_runs
    (device_id, workload_id, request_count, average_latency_ms,
     measured_iops, measured_mbps, cache_hit_ratio)
SELECT
    d.device_id,
    w.workload_id,
    100000,
    0.18,
    118000,
    1420,
    0.82
FROM storage_devices d
CROSS JOIN storage_workloads w
WHERE d.device_name = 'nvme-primary'
  AND w.workload_name = 'Transactional customer database';

-- Cheapest tier satisfying the transactional workload.
SELECT *
FROM recommend_storage_tier(
    120000,
    1500,
    2000,
    1000
);

-- Compare all tiers against one workload.
SELECT
    w.workload_name,
    t.tier_name,
    ROUND(t.monthly_cost_per_gb * w.capacity_gb, 2)
        AS estimated_monthly_cost,
    t.max_iops >= w.required_iops
        AS meets_iops,
    t.max_throughput_mbps >= w.required_throughput_mbps
        AS meets_throughput,
    CASE
        WHEN t.max_iops >= w.required_iops
         AND t.max_throughput_mbps >= w.required_throughput_mbps
         AND (
             w.max_monthly_cost IS NULL
             OR t.monthly_cost_per_gb * w.capacity_gb
                <= w.max_monthly_cost
         )
        THEN TRUE
        ELSE FALSE
    END AS eligible
FROM storage_workloads w
CROSS JOIN storage_tiers t
WHERE w.workload_name = 'Transactional customer database'
ORDER BY estimated_monthly_cost;

-- Aggregate actual modeled operations by device.
SELECT
    d.device_name,
    COUNT(*) AS operations,
    COUNT(*) FILTER (
        WHERE o.operation_type = 'READ'
    ) AS reads,
    COUNT(*) FILTER (
        WHERE o.operation_type = 'WRITE'
    ) AS writes,
    ROUND(
        AVG(o.latency_ms),
        4
    ) AS average_latency_ms,
    ROUND(
        SUM(o.size_kb) / 1024.0,
        2
    ) AS total_mb
FROM io_operations o
JOIN storage_devices d
    ON d.device_id = o.device_id
GROUP BY d.device_name
ORDER BY average_latency_ms;

-- Cache effectiveness is evaluated independently from device capacity.
SELECT
    COUNT(*) FILTER (WHERE event_type = 'HIT') AS hits,
    COUNT(*) FILTER (WHERE event_type = 'MISS') AS misses,
    ROUND(
        COUNT(*) FILTER (WHERE event_type = 'HIT')::NUMERIC
        / NULLIF(
            COUNT(*) FILTER (
                WHERE event_type IN ('HIT', 'MISS')
            ),
            0
        ),
        4
    ) AS cache_hit_ratio
FROM cache_events;

-- Request-size sensitivity:
-- IOPS limited by either the device IOPS ceiling or throughput ceiling.
WITH request_sizes(size_kb) AS (
    VALUES (4), (64), (256)
)
SELECT
    t.tier_name,
    r.size_kb,
    LEAST(
        t.max_iops,
        t.max_throughput_mbps * 1024 / r.size_kb
    ) AS sustainable_iops
FROM storage_tiers t
CROSS JOIN request_sizes r
ORDER BY t.tier_id, r.size_kb;

-- Transaction demonstrates atomic insertion of a benchmark and its operations.
BEGIN;

WITH target AS (
    SELECT device_id
    FROM storage_devices
    WHERE device_name = 'nvme-primary'
)
INSERT INTO benchmark_runs
    (device_id, request_count, average_latency_ms,
     measured_iops, measured_mbps, cache_hit_ratio)
SELECT
    device_id,
    50000,
    0.21,
    105000,
    1280,
    0.79
FROM target;

INSERT INTO io_operations
    (device_id, operation_type, object_key, size_kb, cache_hit)
SELECT
    device_id,
    'READ',
    'transaction:9001',
    16,
    FALSE
FROM storage_devices
WHERE device_name = 'nvme-primary';

COMMIT;

-- A reporting view keeps workload selection logic separate from raw data.
CREATE OR REPLACE VIEW storage_capacity_report AS
SELECT
    w.workload_name,
    t.tier_name,
    w.capacity_gb,
    ROUND(t.monthly_cost_per_gb * w.capacity_gb, 2)
        AS monthly_cost,
    t.max_iops,
    t.max_throughput_mbps,
    t.latency_ms,
    CASE
        WHEN t.max_iops >= w.required_iops
         AND t.max_throughput_mbps >= w.required_throughput_mbps
         AND (
             w.max_monthly_cost IS NULL
             OR t.monthly_cost_per_gb * w.capacity_gb
                <= w.max_monthly_cost
         )
        THEN 'ELIGIBLE'
        ELSE 'REJECTED'
    END AS decision
FROM storage_workloads w
CROSS JOIN storage_tiers t;

SELECT *
FROM storage_capacity_report
ORDER BY workload_name, monthly_cost;
