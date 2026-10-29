DROP SCHEMA IF EXISTS replication_lab CASCADE;
CREATE SCHEMA replication_lab;

SET search_path = replication_lab, public;

-- The relational model separates primary-side data, replication events,
-- replica state, and the policy used to decide whether a write is accepted.

CREATE TYPE node_role AS ENUM ('primary', 'replica');
CREATE TYPE node_state AS ENUM ('online', 'lagging', 'offline');
CREATE TYPE replication_mode AS ENUM ('synchronous', 'asynchronous');
CREATE TYPE transaction_state AS ENUM ('pending', 'committed', 'rejected');
CREATE TYPE review_state AS ENUM ('pending', 'passed', 'failed');

CREATE TABLE repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE database_nodes (
    node_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT REFERENCES repositories(repository_id),
    node_name TEXT NOT NULL UNIQUE,
    role node_role NOT NULL,
    state node_state NOT NULL DEFAULT 'online',
    replication_mode replication_mode NOT NULL,
    applied_sequence BIGINT NOT NULL DEFAULT 0,
    CHECK (applied_sequence >= 0)
);

CREATE TABLE replication_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    policy_name TEXT NOT NULL,
    replication_mode replication_mode NOT NULL,
    required_acknowledgements INTEGER NOT NULL DEFAULT 0,
    allow_stale_reads BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (required_acknowledgements >= 0),
    UNIQUE (repository_id, policy_name)
);

CREATE TABLE data_records (
    record_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    record_key TEXT NOT NULL,
    record_value TEXT,
    version BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (repository_id, record_key),
    CHECK (length(record_key) BETWEEN 1 AND 128),
    CHECK (version > 0)
);

CREATE TABLE replication_transactions (
    transaction_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    sequence_no BIGINT NOT NULL,
    record_key TEXT NOT NULL,
    new_value TEXT,
    checksum TEXT NOT NULL,
    state transaction_state NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    committed_at TIMESTAMPTZ,
    UNIQUE (repository_id, sequence_no),
    CHECK (sequence_no > 0)
);

CREATE TABLE replication_acknowledgements (
    transaction_id BIGINT NOT NULL
        REFERENCES replication_transactions(transaction_id)
        ON DELETE CASCADE,
    node_id BIGINT NOT NULL
        REFERENCES database_nodes(node_id)
        ON DELETE CASCADE,
    acknowledged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_sequence BIGINT NOT NULL,
    PRIMARY KEY (transaction_id, node_id)
);

CREATE TABLE status_checks (
    status_check_id BIGSERIAL PRIMARY KEY,
    transaction_id BIGINT NOT NULL
        REFERENCES replication_transactions(transaction_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    state review_state NOT NULL DEFAULT 'pending',
    completed_at TIMESTAMPTZ,
    UNIQUE (transaction_id, check_name)
);

CREATE INDEX idx_transactions_repository_sequence
    ON replication_transactions(repository_id, sequence_no DESC);

CREATE INDEX idx_acknowledgements_node
    ON replication_acknowledgements(node_id, acknowledged_at DESC);

CREATE INDEX idx_data_records_repository_key
    ON data_records(repository_id, record_key);

CREATE INDEX idx_nodes_repository_state
    ON database_nodes(repository_id, state);

CREATE OR REPLACE FUNCTION validate_replication_policy()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    replica_count INTEGER;
BEGIN
    SELECT count(*)
    INTO replica_count
    FROM database_nodes
    WHERE repository_id = NEW.repository_id
      AND role = 'replica';

    IF NEW.replication_mode = 'synchronous'
       AND NEW.required_acknowledgements < 1 THEN
        RAISE EXCEPTION
            'Synchronous policy requires at least one acknowledgement';
    END IF;

    IF NEW.required_acknowledgements > replica_count THEN
        RAISE EXCEPTION
            'Required acknowledgements (%) exceed configured replicas (%)',
            NEW.required_acknowledgements,
            replica_count;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_replication_policy
BEFORE INSERT OR UPDATE ON replication_policies
FOR EACH ROW
EXECUTE FUNCTION validate_replication_policy();

CREATE OR REPLACE FUNCTION update_record_from_transaction()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = 'committed' AND OLD.state <> 'committed' THEN
        INSERT INTO data_records (
            repository_id,
            record_key,
            record_value,
            version
        )
        VALUES (
            NEW.repository_id,
            NEW.record_key,
            NEW.new_value,
            NEW.sequence_no
        )
        ON CONFLICT (repository_id, record_key)
        DO UPDATE SET
            record_value = EXCLUDED.record_value,
            version = EXCLUDED.version,
            updated_at = now();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_transaction_commit
AFTER UPDATE OF state ON replication_transactions
FOR EACH ROW
EXECUTE FUNCTION update_record_from_transaction();

CREATE OR REPLACE FUNCTION create_replication_transaction(
    p_repository_id BIGINT,
    p_record_key TEXT,
    p_new_value TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    next_sequence BIGINT;
    transaction_id_result BIGINT;
    generated_checksum TEXT;
BEGIN
    IF length(p_record_key) NOT BETWEEN 1 AND 128 THEN
        RAISE EXCEPTION 'Record key must contain 1-128 characters';
    END IF;

    SELECT COALESCE(MAX(sequence_no), 0) + 1
    INTO next_sequence
    FROM replication_transactions
    WHERE repository_id = p_repository_id
    FOR UPDATE;

    generated_checksum := md5(
        p_repository_id::TEXT || '|' ||
        next_sequence::TEXT || '|' ||
        p_record_key || '|' ||
        COALESCE(p_new_value, 'NULL')
    );

    INSERT INTO replication_transactions (
        repository_id,
        sequence_no,
        record_key,
        new_value,
        checksum
    )
    VALUES (
        p_repository_id,
        next_sequence,
        p_record_key,
        p_new_value,
        generated_checksum
    )
    RETURNING transaction_id
    INTO transaction_id_result;

    RETURN transaction_id_result;
END;
$$;

CREATE OR REPLACE FUNCTION evaluate_merge_eligibility(
    p_transaction_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    acknowledgements INTEGER,
    required_acknowledgements INTEGER,
    pending_checks INTEGER,
    reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    tx RECORD;
    policy RECORD;
    acknowledgement_count INTEGER;
    pending_check_count INTEGER;
BEGIN
    SELECT *
    INTO tx
    FROM replication_transactions
    WHERE transaction_id = p_transaction_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown transaction %', p_transaction_id;
    END IF;

    SELECT *
    INTO policy
    FROM replication_policies
    WHERE repository_id = tx.repository_id
    ORDER BY policy_id
    LIMIT 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'No replication policy configured for repository %',
            tx.repository_id;
    END IF;

    SELECT count(*)
    INTO acknowledgement_count
    FROM replication_acknowledgements
    WHERE transaction_id = p_transaction_id;

    SELECT count(*)
    INTO pending_check_count
    FROM status_checks
    WHERE transaction_id = p_transaction_id
      AND state <> 'passed';

    IF policy.replication_mode = 'asynchronous' THEN
        eligible :=
            tx.state = 'committed'
            AND pending_check_count = 0;
    ELSE
        eligible :=
            tx.state = 'committed'
            AND acknowledgement_count >= policy.required_acknowledgements
            AND pending_check_count = 0;
    END IF;

    acknowledgements := acknowledgement_count;
    required_acknowledgements := policy.required_acknowledgements;
    pending_checks := pending_check_count;

    reason :=
        CASE
            WHEN tx.state <> 'committed'
                THEN 'transaction is not committed'
            WHEN pending_check_count > 0
                THEN 'required status checks are incomplete'
            WHEN policy.replication_mode = 'synchronous'
                 AND acknowledgement_count <
                     policy.required_acknowledgements
                THEN 'synchronous acknowledgement requirement not met'
            ELSE 'eligible'
        END;

    RETURN NEXT;
END;
$$;

CREATE VIEW replica_health AS
SELECT
    primary_node.repository_id,
    replica.node_id,
    replica.node_name,
    replica.state,
    primary_node.applied_sequence AS primary_sequence,
    replica.applied_sequence,
    primary_node.applied_sequence - replica.applied_sequence AS lag
FROM database_nodes primary_node
JOIN database_nodes replica
    ON replica.repository_id = primary_node.repository_id
WHERE primary_node.role = 'primary'
  AND replica.role = 'replica';

CREATE VIEW replication_report AS
SELECT
    r.repository_name,
    t.transaction_id,
    t.sequence_no,
    t.record_key,
    t.state,
    p.replication_mode,
    p.required_acknowledgements,
    count(a.node_id) AS acknowledgement_count,
    count(*) FILTER (
        WHERE sc.state <> 'passed'
    ) AS unresolved_checks
FROM repositories r
JOIN replication_transactions t
    ON t.repository_id = r.repository_id
JOIN replication_policies p
    ON p.repository_id = r.repository_id
LEFT JOIN replication_acknowledgements a
    ON a.transaction_id = t.transaction_id
LEFT JOIN status_checks sc
    ON sc.transaction_id = t.transaction_id
GROUP BY
    r.repository_name,
    t.transaction_id,
    t.sequence_no,
    t.record_key,
    t.state,
    p.replication_mode,
    p.required_acknowledgements;

INSERT INTO repositories (repository_name)
VALUES ('payments-production');

INSERT INTO database_nodes (
    repository_id,
    node_name,
    role,
    state,
    replication_mode,
    applied_sequence
)
VALUES
    (
        1,
        'db-primary',
        'primary',
        'online',
        'synchronous',
        3
    ),
    (
        1,
        'db-replica-1',
        'replica',
        'online',
        'synchronous',
        3
    ),
    (
        1,
        'db-replica-2',
        'replica',
        'lagging',
        'asynchronous',
        2
    ),
    (
        1,
        'db-replica-3',
        'replica',
        'offline',
        'asynchronous',
        1
    );

-- The policy requires two synchronous acknowledgements. The trigger verifies
-- that the configured replica count can satisfy the policy.
INSERT INTO replication_policies (
    repository_id,
    policy_name,
    replication_mode,
    required_acknowledgements,
    allow_stale_reads
)
VALUES (
    1,
    'payments-write-policy',
    'synchronous',
    2,
    FALSE
);

INSERT INTO replication_transactions (
    repository_id,
    sequence_no,
    record_key,
    new_value,
    checksum,
    state,
    committed_at
)
VALUES
    (
        1,
        1,
        'payment:1001',
        'SETTLED',
        md5('1|1|payment:1001|SETTLED'),
        'committed',
        now()
    ),
    (
        1,
        2,
        'payment:1002',
        'AUTHORIZED',
        md5('1|2|payment:1002|AUTHORIZED'),
        'committed',
        now()
    ),
    (
        1,
        3,
        'payment:1003',
        'SETTLED',
        md5('1|3|payment:1003|SETTLED'),
        'pending',
        NULL
    );

INSERT INTO replication_acknowledgements (
    transaction_id,
    node_id,
    applied_sequence
)
VALUES
    (1, 2, 1),
    (1, 3, 1),
    (2, 2, 2);

INSERT INTO status_checks (
    transaction_id,
    check_name,
    state,
    completed_at
)
VALUES
    (1, 'replica-integrity', 'passed', now()),
    (2, 'replica-integrity', 'passed', now()),
    (3, 'replica-integrity', 'pending', NULL);

-- The trigger updates the materialized record state when a transaction changes
-- from pending to committed.
UPDATE replication_transactions
SET state = 'committed',
    committed_at = now()
WHERE transaction_id = 3;

INSERT INTO status_checks (
    transaction_id,
    check_name,
    state,
    completed_at
)
VALUES
    (3, 'replica-integrity', 'failed', now());

-- Retrieval: current replicated records.
SELECT
    repository_id,
    record_key,
    record_value,
    version,
    updated_at
FROM data_records
ORDER BY record_key;

-- Monitoring: primary/replica lag.
SELECT *
FROM replica_health
ORDER BY repository_id, node_id;

-- Aggregation: acknowledgement coverage by transaction.
SELECT
    t.transaction_id,
    t.sequence_no,
    t.record_key,
    count(a.node_id) AS acknowledgements
FROM replication_transactions t
LEFT JOIN replication_acknowledgements a
    ON a.transaction_id = t.transaction_id
GROUP BY t.transaction_id, t.sequence_no, t.record_key
ORDER BY t.sequence_no;

-- Eligibility evaluation for a synchronous transaction.
SELECT *
FROM evaluate_merge_eligibility(1);

-- Eligibility evaluation for a transaction with an unresolved failed check.
SELECT *
FROM evaluate_merge_eligibility(3);

-- CTE-based lag analysis identifies replicas that may serve stale reads.
WITH lagged_replicas AS (
    SELECT
        repository_id,
        node_name,
        lag
    FROM replica_health
    WHERE lag > 0
)
SELECT
    repository_id,
    node_name,
    lag,
    CASE
        WHEN lag = 0 THEN 'current'
        WHEN lag <= 1 THEN 'slightly_lagging'
        ELSE 'stale'
    END AS read_consistency_class
FROM lagged_replicas
ORDER BY lag DESC;

-- Transactional example: an acknowledgement and state transition are committed
-- together. If either operation fails, PostgreSQL rolls back the transaction.
BEGIN;

INSERT INTO replication_acknowledgements (
    transaction_id,
    node_id,
    applied_sequence
)
VALUES (3, 2, 3)
ON CONFLICT (transaction_id, node_id)
DO UPDATE SET
    applied_sequence = EXCLUDED.applied_sequence,
    acknowledged_at = now();

UPDATE replication_transactions
SET state = 'committed',
    committed_at = now()
WHERE transaction_id = 3
  AND EXISTS (
      SELECT 1
      FROM replication_acknowledgements
      WHERE transaction_id = 3
        AND node_id = 2
  );

COMMIT;

-- Final operational report.
SELECT *
FROM replication_report
ORDER BY sequence_no;
