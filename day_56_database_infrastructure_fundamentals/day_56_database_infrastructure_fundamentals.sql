-- Database Infrastructure Fundamentals
-- PostgreSQL 14+ / 15+ / 16+ / 17 / 18 compatible design.
--
-- The schema separates:
--   physical/logical infrastructure metadata
--   transactional state
--   replication state
--   availability policy
--   operational workflow
--
-- The SQL models database infrastructure rather than pretending that
-- PostgreSQL storage internals can be replaced by ordinary application tables.

DROP SCHEMA IF EXISTS db_infra CASCADE;
CREATE SCHEMA db_infra;

SET search_path = db_infra, public;

CREATE TYPE node_role AS ENUM ('primary', 'replica');
CREATE TYPE node_state AS ENUM ('online', 'degraded', 'offline');
CREATE TYPE transaction_state AS ENUM ('active', 'committed', 'rolled_back');
CREATE TYPE transaction_isolation AS ENUM (
    'read_committed',
    'repeatable_read',
    'serializable'
);
CREATE TYPE replication_mode AS ENUM ('synchronous', 'asynchronous');
CREATE TYPE wal_operation AS ENUM ('insert', 'update', 'delete');
CREATE TYPE check_state AS ENUM ('pending', 'passed', 'failed');
CREATE TYPE failover_state AS ENUM ('none', 'candidate', 'promoted', 'rejected');

CREATE TABLE database_cluster (
    cluster_id BIGSERIAL PRIMARY KEY,
    cluster_name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE database_node (
    node_id BIGSERIAL PRIMARY KEY,
    cluster_id BIGINT NOT NULL
        REFERENCES database_cluster(cluster_id)
        ON DELETE CASCADE,
    node_name TEXT NOT NULL,
    role node_role NOT NULL,
    state node_state NOT NULL DEFAULT 'online',
    replication_mode replication_mode NOT NULL DEFAULT 'asynchronous',
    applied_lsn BIGINT NOT NULL DEFAULT 0 CHECK (applied_lsn >= 0),
    last_heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (cluster_id, node_name)
);

CREATE UNIQUE INDEX ux_one_primary_per_cluster
    ON database_node(cluster_id)
    WHERE role = 'primary';

CREATE TABLE application_account (
    account_id BIGSERIAL PRIMARY KEY,
    account_code TEXT NOT NULL UNIQUE,
    owner_name TEXT NOT NULL,
    balance NUMERIC(18, 2) NOT NULL DEFAULT 0
        CHECK (balance >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE database_transaction (
    transaction_id UUID PRIMARY KEY,
    cluster_id BIGINT NOT NULL
        REFERENCES database_cluster(cluster_id),
    isolation_level transaction_isolation NOT NULL,
    state transaction_state NOT NULL DEFAULT 'active',
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    committed_at TIMESTAMPTZ,
    CHECK (
        (state = 'committed' AND committed_at IS NOT NULL)
        OR
        (state <> 'committed')
    )
);

CREATE TABLE transaction_operation (
    operation_id BIGSERIAL PRIMARY KEY,
    transaction_id UUID NOT NULL
        REFERENCES database_transaction(transaction_id)
        ON DELETE CASCADE,
    operation_number INTEGER NOT NULL CHECK (operation_number > 0),
    operation wal_operation NOT NULL,
    account_id BIGINT
        REFERENCES application_account(account_id),
    amount NUMERIC(18, 2)
        CHECK (amount IS NULL OR amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (transaction_id, operation_number)
);

CREATE TABLE write_ahead_log (
    lsn BIGSERIAL PRIMARY KEY,
    node_id BIGINT NOT NULL
        REFERENCES database_node(node_id),
    transaction_id UUID NOT NULL
        REFERENCES database_transaction(transaction_id),
    operation wal_operation NOT NULL,
    account_id BIGINT
        REFERENCES application_account(account_id),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX ix_wal_transaction_lsn
    ON write_ahead_log(transaction_id, lsn);

CREATE INDEX ix_wal_node_lsn
    ON write_ahead_log(node_id, lsn);

CREATE TABLE replication_status (
    source_node_id BIGINT NOT NULL
        REFERENCES database_node(node_id)
        ON DELETE CASCADE,
    replica_node_id BIGINT NOT NULL
        REFERENCES database_node(node_id)
        ON DELETE CASCADE,
    received_lsn BIGINT NOT NULL DEFAULT 0 CHECK (received_lsn >= 0),
    replayed_lsn BIGINT NOT NULL DEFAULT 0 CHECK (replayed_lsn >= 0),
    last_replay_at TIMESTAMPTZ,
    state node_state NOT NULL DEFAULT 'online',
    PRIMARY KEY (source_node_id, replica_node_id),
    CHECK (replayed_lsn <= received_lsn)
);

CREATE TABLE availability_policy (
    policy_id BIGSERIAL PRIMARY KEY,
    cluster_id BIGINT NOT NULL
        REFERENCES database_cluster(cluster_id)
        ON DELETE CASCADE,
    minimum_online_nodes INTEGER NOT NULL CHECK (minimum_online_nodes > 0),
    require_replica_lag_below BIGINT NOT NULL DEFAULT 100
        CHECK (require_replica_lag_below >= 0),
    allow_failover BOOLEAN NOT NULL DEFAULT TRUE,
    require_synchronous_replica BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (cluster_id)
);

CREATE TABLE health_check (
    health_check_id BIGSERIAL PRIMARY KEY,
    node_id BIGINT NOT NULL
        REFERENCES database_node(node_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    state check_state NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    latency_ms NUMERIC(12, 3)
        CHECK (latency_ms IS NULL OR latency_ms >= 0),
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE failover_event (
    failover_id BIGSERIAL PRIMARY KEY,
    cluster_id BIGINT NOT NULL
        REFERENCES database_cluster(cluster_id)
        ON DELETE CASCADE,
    failed_node_id BIGINT
        REFERENCES database_node(node_id),
    candidate_node_id BIGINT
        REFERENCES database_node(node_id),
    resulting_state failover_state NOT NULL,
    reason TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION prevent_invalid_replication_status()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.source_node_id = NEW.replica_node_id THEN
        RAISE EXCEPTION 'A node cannot replicate from itself';
    END IF;

    IF NEW.replayed_lsn > NEW.received_lsn THEN
        RAISE EXCEPTION
            'Replayed LSN % cannot exceed received LSN %',
            NEW.replayed_lsn,
            NEW.received_lsn;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_replication_status_validation
BEFORE INSERT OR UPDATE ON replication_status
FOR EACH ROW
EXECUTE FUNCTION prevent_invalid_replication_status();

CREATE OR REPLACE FUNCTION enforce_transaction_state()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.state <> 'active' AND NEW.state <> OLD.state THEN
        RAISE EXCEPTION
            'Transaction % cannot transition from % to %',
            OLD.transaction_id,
            OLD.state,
            NEW.state;
    END IF;

    IF NEW.state = 'committed' AND NEW.committed_at IS NULL THEN
        NEW.committed_at := clock_timestamp();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_transaction_state
BEFORE UPDATE ON database_transaction
FOR EACH ROW
EXECUTE FUNCTION enforce_transaction_state();

CREATE OR REPLACE FUNCTION create_transfer(
    p_transaction_id UUID,
    p_source BIGINT,
    p_target BIGINT,
    p_amount NUMERIC(18, 2)
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    source_balance NUMERIC(18, 2);
BEGIN
    IF p_source = p_target THEN
        RAISE EXCEPTION 'Source and target accounts must differ';
    END IF;

    IF p_amount <= 0 THEN
        RAISE EXCEPTION 'Transfer amount must be positive';
    END IF;

    SELECT balance
      INTO source_balance
      FROM application_account
     WHERE account_id = p_source
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Source account % does not exist', p_source;
    END IF;

    PERFORM 1
      FROM application_account
     WHERE account_id = p_target
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Target account % does not exist', p_target;
    END IF;

    IF source_balance < p_amount THEN
        RAISE EXCEPTION
            'Insufficient funds: balance %, requested %',
            source_balance,
            p_amount;
    END IF;

    UPDATE application_account
       SET balance = balance - p_amount
     WHERE account_id = p_source;

    UPDATE application_account
       SET balance = balance + p_amount
     WHERE account_id = p_target;

    INSERT INTO transaction_operation (
        transaction_id,
        operation_number,
        operation,
        account_id,
        amount
    )
    SELECT
        p_transaction_id,
        COALESCE(MAX(operation_number), 0) + 1,
        'update',
        p_source,
        p_amount
    FROM transaction_operation
    WHERE transaction_id = p_transaction_id;

    INSERT INTO transaction_operation (
        transaction_id,
        operation_number,
        operation,
        account_id,
        amount
    )
    SELECT
        p_transaction_id,
        COALESCE(MAX(operation_number), 0) + 1,
        'update',
        p_target,
        p_amount
    FROM transaction_operation
    WHERE transaction_id = p_transaction_id;
END;
$$;

CREATE OR REPLACE VIEW cluster_health AS
SELECT
    c.cluster_name,
    n.node_name,
    n.role,
    n.state,
    n.applied_lsn,
    n.last_heartbeat_at,
    CASE
        WHEN n.state = 'online'
         AND n.last_heartbeat_at >= clock_timestamp() - INTERVAL '30 seconds'
        THEN 'healthy'
        WHEN n.state = 'degraded'
        THEN 'degraded'
        ELSE 'unhealthy'
    END AS health
FROM database_cluster c
JOIN database_node n
  ON n.cluster_id = c.cluster_id;

CREATE OR REPLACE VIEW replication_lag AS
SELECT
    source.node_name AS source_node,
    replica.node_name AS replica_node,
    rs.received_lsn,
    rs.replayed_lsn,
    rs.received_lsn - rs.replayed_lsn AS lag,
    rs.state
FROM replication_status rs
JOIN database_node source
  ON source.node_id = rs.source_node_id
JOIN database_node replica
  ON replica.node_id = rs.replica_node_id;

CREATE OR REPLACE VIEW merge_like_availability_decision AS
SELECT
    c.cluster_id,
    c.cluster_name,
    COUNT(*) FILTER (WHERE n.state = 'online') AS online_nodes,
    p.minimum_online_nodes,
    p.allow_failover,
    p.require_synchronous_replica,
    (
        COUNT(*) FILTER (WHERE n.state = 'online')
        >= p.minimum_online_nodes
    ) AS enough_online_nodes,
    (
        NOT p.require_synchronous_replica
        OR EXISTS (
            SELECT 1
            FROM database_node replica
            WHERE replica.cluster_id = c.cluster_id
              AND replica.role = 'replica'
              AND replica.state = 'online'
              AND replica.replication_mode = 'synchronous'
        )
    ) AS replication_requirement_met
FROM database_cluster c
JOIN availability_policy p
  ON p.cluster_id = c.cluster_id
JOIN database_node n
  ON n.cluster_id = c.cluster_id
GROUP BY
    c.cluster_id,
    c.cluster_name,
    p.minimum_online_nodes,
    p.allow_failover,
    p.require_synchronous_replica;

INSERT INTO database_cluster (cluster_name)
VALUES ('orders-production');

INSERT INTO database_node (
    cluster_id,
    node_name,
    role,
    state,
    replication_mode,
    applied_lsn
)
VALUES
(
    1,
    'orders-primary-01',
    'primary',
    'online',
    'synchronous',
    1050
),
(
    1,
    'orders-replica-01',
    'replica',
    'online',
    'synchronous',
    1048
),
(
    1,
    'orders-replica-02',
    'replica',
    'degraded',
    'asynchronous',
    1001
);

INSERT INTO availability_policy (
    cluster_id,
    minimum_online_nodes,
    require_replica_lag_below,
    allow_failover,
    require_synchronous_replica
)
VALUES (1, 2, 10, TRUE, TRUE);

INSERT INTO application_account (
    account_code,
    owner_name,
    balance
)
VALUES
    ('OPS-100', 'Operations', 1000.00),
    ('ANL-200', 'Analytics', 250.00),
    ('SUP-300', 'Support', 500.00);

INSERT INTO database_transaction (
    transaction_id,
    cluster_id,
    isolation_level,
    state,
    committed_at
)
VALUES
(
    '11111111-1111-1111-1111-111111111111',
    1,
    'serializable',
    'committed',
    clock_timestamp()
),
(
    '22222222-2222-2222-2222-222222222222',
    1,
    'read_committed',
    'rolled_back',
    NULL
);

INSERT INTO transaction_operation (
    transaction_id,
    operation_number,
    operation,
    account_id,
    amount
)
VALUES
(
    '11111111-1111-1111-1111-111111111111',
    1,
    'update',
    1,
    125.00
),
(
    '11111111-1111-1111-1111-111111111111',
    2,
    'update',
    2,
    125.00
),
(
    '22222222-2222-2222-2222-222222222222',
    1,
    'update',
    1,
    5000.00
);

INSERT INTO write_ahead_log (
    node_id,
    transaction_id,
    operation,
    account_id,
    payload
)
VALUES
(
    1,
    '11111111-1111-1111-1111-111111111111',
    'update',
    1,
    '{"operation":"debit","amount":125.00}'
),
(
    1,
    '11111111-1111-1111-1111-111111111111',
    'update',
    2,
    '{"operation":"credit","amount":125.00}'
);

INSERT INTO replication_status (
    source_node_id,
    replica_node_id,
    received_lsn,
    replayed_lsn,
    last_replay_at,
    state
)
VALUES
(
    1,
    2,
    1050,
    1048,
    clock_timestamp(),
    'online'
),
(
    1,
    3,
    1050,
    1001,
    clock_timestamp(),
    'degraded'
);

INSERT INTO health_check (
    node_id,
    check_name,
    state,
    latency_ms,
    details
)
VALUES
(
    1,
    'database-connectivity',
    'passed',
    2.10,
    '{"connections":42,"max_connections":200}'
),
(
    2,
    'replication-replay',
    'passed',
    4.80,
    '{"replayed_lsn":1048}'
),
(
    3,
    'replication-replay',
    'failed',
    80.20,
    '{"reason":"replication lag above operational threshold"}'
);

INSERT INTO failover_event (
    cluster_id,
    failed_node_id,
    candidate_node_id,
    resulting_state,
    reason
)
VALUES (
    1,
    1,
    2,
    'candidate',
    'Primary failure simulation with replica 01 as the most current healthy candidate'
);

-- Retrieval: infrastructure topology and current health.
SELECT *
FROM cluster_health
ORDER BY cluster_name, node_name;

-- Replication evaluation: lag is derived from received and replayed LSN.
SELECT
    source_node,
    replica_node,
    lag,
    state,
    CASE
        WHEN state = 'online' AND lag <= 10
        THEN 'within-policy'
        ELSE 'outside-policy'
    END AS replication_decision
FROM replication_lag
ORDER BY lag DESC;

-- Aggregation: WAL activity by node.
SELECT
    n.node_name,
    COUNT(w.lsn) AS wal_records,
    COALESCE(MAX(w.lsn), 0) AS latest_lsn
FROM database_node n
LEFT JOIN write_ahead_log w
  ON w.node_id = n.node_id
GROUP BY n.node_name
ORDER BY latest_lsn DESC;

-- Transaction reporting.
SELECT
    t.transaction_id,
    t.isolation_level,
    t.state,
    COUNT(o.operation_id) AS operations,
    t.started_at,
    t.committed_at
FROM database_transaction t
LEFT JOIN transaction_operation o
  ON o.transaction_id = t.transaction_id
GROUP BY
    t.transaction_id,
    t.isolation_level,
    t.state,
    t.started_at,
    t.committed_at
ORDER BY t.started_at;

-- Eligibility evaluation combines availability and replication policy.
SELECT
    cluster_name,
    online_nodes,
    minimum_online_nodes,
    enough_online_nodes,
    replication_requirement_met,
    (
        enough_online_nodes
        AND replication_requirement_met
    ) AS failover_eligible
FROM merge_like_availability_decision;

-- CTE reporting identifies replicas whose lag requires operational attention.
WITH replica_lag AS (
    SELECT
        replica.node_name,
        rs.received_lsn,
        rs.replayed_lsn,
        rs.received_lsn - rs.replayed_lsn AS lag
    FROM replication_status rs
    JOIN database_node replica
      ON replica.node_id = rs.replica_node_id
)
SELECT
    node_name,
    lag,
    CASE
        WHEN lag = 0 THEN 'synchronized'
        WHEN lag <= 10 THEN 'acceptable'
        ELSE 'investigate'
    END AS operational_state
FROM replica_lag
ORDER BY lag DESC;

-- Transactional workflow example.
-- The row locks prevent concurrent transfers from observing the same
-- spendable balance.
BEGIN;

UPDATE application_account
SET balance = balance - 25.00
WHERE account_id = 1
  AND balance >= 25.00;

DO $$
BEGIN
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Debit rejected: insufficient funds';
    END IF;
END;
$$;

UPDATE application_account
SET balance = balance + 25.00
WHERE account_id = 2;

COMMIT;

-- Validation of the final account state.
SELECT
    account_code,
    owner_name,
    balance
FROM application_account
ORDER BY account_id;
