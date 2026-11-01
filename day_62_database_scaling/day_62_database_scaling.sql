DROP SCHEMA IF EXISTS database_scaling CASCADE;
CREATE SCHEMA database_scaling;

SET search_path = database_scaling, public;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- Database Scaling Reference Model
--
-- Vertical scaling:
--   represented by node capacity metadata.
--
-- Horizontal scaling:
--   represented by multiple database nodes.
--
-- Partitioning:
--   implemented as PostgreSQL range partitions.
--
-- Sharding:
--   represented by shard metadata and deterministic routing.
--
-- Read replicas:
--   represented by primary/replica node roles and routing policy.
-- ============================================================

CREATE TYPE node_role AS ENUM (
    'primary',
    'read_replica',
    'shard_primary',
    'shard_replica'
);

CREATE TYPE node_status AS ENUM (
    'healthy',
    'degraded',
    'offline'
);

CREATE TYPE scaling_strategy AS ENUM (
    'vertical',
    'horizontal',
    'partitioning',
    'sharding',
    'read_replica'
);

CREATE TABLE database_nodes (
    node_id              BIGSERIAL PRIMARY KEY,
    node_name            TEXT NOT NULL UNIQUE,
    region               TEXT NOT NULL,
    role                 node_role NOT NULL,
    status               node_status NOT NULL DEFAULT 'healthy',
    cpu_cores            INTEGER NOT NULL CHECK (cpu_cores > 0),
    memory_gb            INTEGER NOT NULL CHECK (memory_gb > 0),
    max_ops_per_second   INTEGER NOT NULL CHECK (max_ops_per_second > 0),
    active_connections   INTEGER NOT NULL DEFAULT 0
                         CHECK (active_connections >= 0),
    replication_lag_ms   INTEGER NOT NULL DEFAULT 0
                         CHECK (replication_lag_ms >= 0),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE repositories_for_scaling_demo (
    repository_id        BIGSERIAL PRIMARY KEY,
    repository_name      TEXT NOT NULL UNIQUE,
    owner_name           TEXT NOT NULL,
    scaling_strategy     scaling_strategy NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE customers (
    customer_id          BIGINT NOT NULL,
    customer_name        TEXT NOT NULL,
    region               TEXT NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id)
) PARTITION BY RANGE (customer_id);

CREATE TABLE customers_p0_999
    PARTITION OF customers
    FOR VALUES FROM (0) TO (1000);

CREATE TABLE customers_p1000_1999
    PARTITION OF customers
    FOR VALUES FROM (1000) TO (2000);

CREATE TABLE customers_p2000_2999
    PARTITION OF customers
    FOR VALUES FROM (2000) TO (3000);

CREATE TABLE customers_p3000_3999
    PARTITION OF customers
    FOR VALUES FROM (3000) TO (4000);

CREATE TABLE orders (
    order_id             BIGINT GENERATED ALWAYS AS IDENTITY,
    customer_id          BIGINT NOT NULL,
    order_total          NUMERIC(12,2) NOT NULL CHECK (order_total >= 0),
    order_status         TEXT NOT NULL
                         CHECK (
                             order_status IN
                             ('pending', 'paid', 'shipped', 'cancelled')
                         ),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE orders_2026_q4
    PARTITION OF orders
    FOR VALUES FROM ('2026-10-01 00:00:00+00')
                 TO ('2027-01-01 00:00:00+00');

CREATE TABLE orders_2027_q1
    PARTITION OF orders
    FOR VALUES FROM ('2027-01-01 00:00:00+00')
                 TO ('2027-04-01 00:00:00+00');

ALTER TABLE orders
    ADD CONSTRAINT orders_customer_fk
    FOREIGN KEY (customer_id)
    REFERENCES customers(customer_id);

CREATE TABLE shards (
    shard_id             SERIAL PRIMARY KEY,
    shard_name           TEXT NOT NULL UNIQUE,
    region               TEXT NOT NULL,
    primary_node_id      BIGINT NOT NULL REFERENCES database_nodes(node_id),
    minimum_customer_id  BIGINT NOT NULL,
    maximum_customer_id  BIGINT NOT NULL,
    CHECK (minimum_customer_id <= maximum_customer_id),
    UNIQUE (
        minimum_customer_id,
        maximum_customer_id
    )
);

CREATE TABLE shard_replicas (
    shard_replica_id     BIGSERIAL PRIMARY KEY,
    shard_id             INTEGER NOT NULL REFERENCES shards(shard_id)
                         ON DELETE CASCADE,
    node_id              BIGINT NOT NULL REFERENCES database_nodes(node_id),
    replica_priority     INTEGER NOT NULL CHECK (replica_priority > 0),
    enabled              BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (shard_id, node_id),
    UNIQUE (shard_id, replica_priority)
);

CREATE TABLE scaling_events (
    scaling_event_id     BIGSERIAL PRIMARY KEY,
    node_id              BIGINT REFERENCES database_nodes(node_id),
    strategy             scaling_strategy NOT NULL,
    observed_ops         INTEGER NOT NULL CHECK (observed_ops >= 0),
    capacity_ops         INTEGER NOT NULL CHECK (capacity_ops > 0),
    write_ratio          NUMERIC(5,4) NOT NULL
                         CHECK (write_ratio BETWEEN 0 AND 1),
    row_count            BIGINT NOT NULL CHECK (row_count >= 0),
    reason               TEXT NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_database_nodes_region_status
    ON database_nodes(region, status);

CREATE INDEX idx_database_nodes_role_status
    ON database_nodes(role, status);

CREATE INDEX idx_orders_customer
    ON orders(customer_id);

CREATE INDEX idx_orders_created_at
    ON orders(created_at);

CREATE INDEX idx_shard_replicas_enabled
    ON shard_replicas(shard_id, enabled);

-- Prevent overlapping shard ranges.
CREATE OR REPLACE FUNCTION prevent_overlapping_shards()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM shards s
        WHERE s.shard_id <> COALESCE(NEW.shard_id, -1)
          AND int8range(
                s.minimum_customer_id,
                s.maximum_customer_id + 1,
                '[)'
              ) &&
              int8range(
                NEW.minimum_customer_id,
                NEW.maximum_customer_id + 1,
                '[)'
              )
    ) THEN
        RAISE EXCEPTION
            'Shard range %-% overlaps an existing shard',
            NEW.minimum_customer_id,
            NEW.maximum_customer_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_prevent_overlapping_shards
BEFORE INSERT OR UPDATE ON shards
FOR EACH ROW
EXECUTE FUNCTION prevent_overlapping_shards();

-- Basic node safety: replicas cannot report negative lag or
-- exceed their configured connection capacity.
CREATE OR REPLACE FUNCTION validate_database_node()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.active_connections > NEW.max_ops_per_second THEN
        RAISE EXCEPTION
            'Active connections cannot exceed configured capacity';
    END IF;

    IF NEW.role = 'read_replica'
       AND NEW.replication_lag_ms > 30000
       AND NEW.status = 'healthy' THEN
        NEW.status := 'degraded';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_database_node
BEFORE INSERT OR UPDATE ON database_nodes
FOR EACH ROW
EXECUTE FUNCTION validate_database_node();

-- ============================================================
-- Sample database nodes
-- ============================================================

INSERT INTO database_nodes (
    node_name,
    region,
    role,
    cpu_cores,
    memory_gb,
    max_ops_per_second
)
VALUES
    ('primary-ap-south', 'ap-south', 'primary', 16, 64, 5000),
    ('replica-ap-south-1', 'ap-south', 'read_replica', 8, 32, 3000),
    ('replica-ap-southeast-1', 'ap-southeast', 'read_replica', 8, 32, 3000),
    ('shard-a-primary', 'ap-south', 'shard_primary', 16, 64, 4500),
    ('shard-b-primary', 'ap-south', 'shard_primary', 16, 64, 4500),
    ('shard-c-primary', 'ap-southeast', 'shard_primary', 16, 64, 4500);

INSERT INTO repositories_for_scaling_demo (
    repository_name,
    owner_name,
    scaling_strategy
)
VALUES
    ('commerce-orders', 'platform-team', 'partitioning'),
    ('customer-profile', 'platform-team', 'read_replica'),
    ('global-events', 'platform-team', 'sharding'),
    ('analytics-api', 'platform-team', 'horizontal');

-- ============================================================
-- Partitioned customer data
-- ============================================================

INSERT INTO customers (
    customer_id,
    customer_name,
    region
)
VALUES
    (101, 'Customer 101', 'north'),
    (102, 'Customer 102', 'south'),
    (103, 'Customer 103', 'east'),
    (104, 'Customer 104', 'west'),
    (1500, 'Customer 1500', 'south'),
    (1501, 'Customer 1501', 'south'),
    (2100, 'Customer 2100', 'east'),
    (2101, 'Customer 2101', 'east'),
    (3200, 'Customer 3200', 'west');

INSERT INTO orders (
    customer_id,
    order_total,
    order_status,
    created_at
)
VALUES
    (101, 250.00, 'paid', '2026-10-05 10:00:00+00'),
    (102, 125.00, 'shipped', '2026-10-10 11:00:00+00'),
    (1500, 400.00, 'paid', '2026-10-15 12:00:00+00'),
    (1501, 800.00, 'pending', '2026-10-20 13:00:00+00'),
    (2100, 950.00, 'shipped', '2026-10-21 14:00:00+00'),
    (2101, 300.00, 'cancelled', '2026-10-22 15:00:00+00'),
    (3200, 500.00, 'paid', '2026-10-25 16:00:00+00');

-- ============================================================
-- Shard metadata
-- ============================================================

INSERT INTO shards (
    shard_name,
    region,
    primary_node_id,
    minimum_customer_id,
    maximum_customer_id
)
SELECT
    'shard-a',
    'ap-south',
    node_id,
    0,
    999
FROM database_nodes
WHERE node_name = 'shard-a-primary';

INSERT INTO shards (
    shard_name,
    region,
    primary_node_id,
    minimum_customer_id,
    maximum_customer_id
)
SELECT
    'shard-b',
    'ap-south',
    node_id,
    1000,
    1999
FROM database_nodes
WHERE node_name = 'shard-b-primary';

INSERT INTO shards (
    shard_name,
    region,
    primary_node_id,
    minimum_customer_id,
    maximum_customer_id
)
SELECT
    'shard-c',
    'ap-southeast',
    node_id,
    2000,
    3999
FROM database_nodes
WHERE node_name = 'shard-c-primary';

INSERT INTO shard_replicas (
    shard_id,
    node_id,
    replica_priority
)
SELECT
    s.shard_id,
    n.node_id,
    1
FROM shards s
JOIN database_nodes n
  ON n.node_name = 'replica-ap-south-1'
WHERE s.shard_name = 'shard-a';

INSERT INTO shard_replicas (
    shard_id,
    node_id,
    replica_priority
)
SELECT
    s.shard_id,
    n.node_id,
    1
FROM shards s
JOIN database_nodes n
  ON n.node_name = 'replica-ap-southeast-1'
WHERE s.shard_name = 'shard-c';

-- ============================================================
-- Scaling decision function
-- ============================================================

CREATE OR REPLACE FUNCTION recommend_scaling_strategy(
    p_observed_ops INTEGER,
    p_capacity_ops INTEGER,
    p_write_ratio NUMERIC,
    p_row_count BIGINT
)
RETURNS scaling_strategy
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_observed_ops <= 0 OR p_capacity_ops <= 0 THEN
        RAISE EXCEPTION
            'Observed operations and capacity must be positive';
    END IF;

    IF p_write_ratio < 0 OR p_write_ratio > 1 THEN
        RAISE EXCEPTION
            'Write ratio must be between 0 and 1';
    END IF;

    IF p_observed_ops::NUMERIC / p_capacity_ops <= 0.70 THEN
        RETURN 'vertical';
    END IF;

    IF p_write_ratio < 0.30 THEN
        RETURN 'read_replica';
    END IF;

    IF p_row_count > 10000000 THEN
        RETURN 'partitioning';
    END IF;

    RETURN 'horizontal';
END;
$$;

-- ============================================================
-- Deterministic shard routing function
-- ============================================================

CREATE OR REPLACE FUNCTION route_customer_to_shard(
    p_customer_id BIGINT
)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    selected_shard TEXT;
BEGIN
    SELECT shard_name
    INTO selected_shard
    FROM shards
    WHERE p_customer_id BETWEEN
          minimum_customer_id AND maximum_customer_id
    ORDER BY minimum_customer_id
    LIMIT 1;

    IF selected_shard IS NULL THEN
        RAISE EXCEPTION
            'No shard owns customer %',
            p_customer_id;
    END IF;

    RETURN selected_shard;
END;
$$;

-- ============================================================
-- Read-routing view
-- ============================================================

CREATE VIEW healthy_read_targets AS
SELECT
    node_id,
    node_name,
    region,
    max_ops_per_second,
    replication_lag_ms,
    CASE
        WHEN replication_lag_ms <= 1000
             THEN 'preferred'
        WHEN replication_lag_ms <= 30000
             THEN 'acceptable'
        ELSE 'lagging'
    END AS routing_state
FROM database_nodes
WHERE role = 'read_replica'
  AND status IN ('healthy', 'degraded')
ORDER BY
    replication_lag_ms,
    active_connections;

-- ============================================================
-- Partition distribution report
-- ============================================================

CREATE VIEW customer_partition_distribution AS
SELECT
    tableoid::regclass AS physical_partition,
    COUNT(*) AS customer_count,
    MIN(customer_id) AS minimum_customer_id,
    MAX(customer_id) AS maximum_customer_id
FROM customers
GROUP BY tableoid
ORDER BY physical_partition::TEXT;

-- ============================================================
-- Scaling workload examples
-- ============================================================

INSERT INTO scaling_events (
    node_id,
    strategy,
    observed_ops,
    capacity_ops,
    write_ratio,
    row_count,
    reason
)
SELECT
    node_id,
    recommend_scaling_strategy(900, 1000, 0.10, 500000),
    900,
    1000,
    0.10,
    500000,
    'Read-heavy workload exceeds preferred node utilization'
FROM database_nodes
WHERE node_name = 'primary-ap-south';

INSERT INTO scaling_events (
    node_id,
    strategy,
    observed_ops,
    capacity_ops,
    write_ratio,
    row_count,
    reason
)
SELECT
    node_id,
    recommend_scaling_strategy(900, 1000, 0.80, 20000000),
    900,
    1000,
    0.80,
    20000000,
    'Large write workload requires data distribution'
FROM database_nodes
WHERE node_name = 'primary-ap-south';

-- ============================================================
-- Transactional routing example
-- ============================================================

BEGIN;

SELECT route_customer_to_shard(1500);

UPDATE database_nodes
SET active_connections = active_connections + 1
WHERE node_name = 'primary-ap-south'
  AND active_connections < max_ops_per_second;

COMMIT;

-- ============================================================
-- Validation and reporting queries
-- ============================================================

-- Partition pruning can be observed with EXPLAIN.
EXPLAIN
SELECT *
FROM customers
WHERE customer_id = 1500;

-- Query only the required partition range.
SELECT
    customer_id,
    customer_name,
    region
FROM customers
WHERE customer_id BETWEEN 1000 AND 1999
ORDER BY customer_id;

-- Order aggregation.
SELECT
    c.region,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.order_total), 0) AS revenue
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
GROUP BY c.region
ORDER BY revenue DESC;

-- Scaling recommendations across observed workloads.
WITH workloads AS (
    SELECT *
    FROM (
        VALUES
            (500, 1000, 0.50::NUMERIC, 100000::BIGINT),
            (900, 1000, 0.10::NUMERIC, 500000::BIGINT),
            (900, 1000, 0.80::NUMERIC, 20000000::BIGINT),
            (950, 1000, 0.50::NUMERIC, 2000000::BIGINT)
    ) AS x(
        observed_ops,
        capacity_ops,
        write_ratio,
        row_count
    )
)
SELECT
    observed_ops,
    capacity_ops,
    write_ratio,
    row_count,
    recommend_scaling_strategy(
        observed_ops,
        capacity_ops,
        write_ratio,
        row_count
    ) AS recommended_strategy
FROM workloads;

-- Healthy read targets.
SELECT *
FROM healthy_read_targets;

-- Partition distribution.
SELECT *
FROM customer_partition_distribution;

-- Shard ownership.
SELECT
    s.shard_name,
    s.region,
    s.minimum_customer_id,
    s.maximum_customer_id,
    n.node_name AS primary_node
FROM shards s
JOIN database_nodes n
    ON n.node_id = s.primary_node_id
ORDER BY s.minimum_customer_id;

-- Replication health.
SELECT
    node_name,
    region,
    replication_lag_ms,
    active_connections,
    max_ops_per_second,
    ROUND(
        active_connections::NUMERIC /
        NULLIF(max_ops_per_second, 0) * 100,
        2
    ) AS capacity_utilization_percent
FROM database_nodes
WHERE role IN ('primary', 'read_replica')
ORDER BY capacity_utilization_percent DESC;

-- Failure-condition query: replicas with excessive lag.
SELECT
    node_name,
    region,
    replication_lag_ms,
    status
FROM database_nodes
WHERE role = 'read_replica'
  AND replication_lag_ms > 30000;

-- CTE for customer-to-shard placement.
WITH customer_targets AS (
    SELECT
        customer_id,
        route_customer_to_shard(customer_id) AS shard_name
    FROM customers
)
SELECT
    shard_name,
    COUNT(*) AS customers
FROM customer_targets
GROUP BY shard_name
ORDER BY shard_name;

-- Example of a read-routing decision that prefers the least-lagged replica.
SELECT
    node_name,
    region,
    replication_lag_ms,
    active_connections
FROM database_nodes
WHERE role = 'read_replica'
  AND status = 'healthy'
ORDER BY
    replication_lag_ms ASC,
    active_connections ASC
LIMIT 1;
