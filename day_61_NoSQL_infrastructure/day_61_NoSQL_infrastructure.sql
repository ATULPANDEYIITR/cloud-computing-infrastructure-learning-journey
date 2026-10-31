DROP SCHEMA IF EXISTS nosql_infrastructure CASCADE;
CREATE SCHEMA nosql_infrastructure;

SET search_path TO nosql_infrastructure;

-- A relational model is used here to represent the operational metadata
-- around NoSQL systems. The data structures preserve the semantics of
-- key-value, document, wide-column, graph, and replication workloads.

CREATE TYPE database_kind AS ENUM (
    'key_value',
    'document',
    'wide_column',
    'graph'
);

CREATE TYPE consistency_mode AS ENUM (
    'strong',
    'eventual'
);

CREATE TYPE node_kind AS ENUM (
    'service',
    'device',
    'user',
    'resource'
);

CREATE TYPE check_state AS ENUM (
    'pending',
    'passed',
    'failed'
);

CREATE TYPE replication_state AS ENUM (
    'queued',
    'applied',
    'rejected'
);

CREATE TABLE repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    owner_name TEXT NOT NULL,
    database_kind database_kind NOT NULL,
    consistency consistency_mode NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(trim(repository_name)) > 0),
    CHECK (length(trim(owner_name)) > 0)
);

CREATE TABLE branches (
    branch_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    branch_name TEXT NOT NULL,
    is_protected BOOLEAN NOT NULL DEFAULT false,
    head_version BIGINT NOT NULL DEFAULT 0,
    UNIQUE(repository_id, branch_name),
    CHECK (length(trim(branch_name)) > 0),
    CHECK (head_version >= 0)
);

CREATE TABLE commits (
    commit_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id)
        ON DELETE CASCADE,
    commit_hash TEXT NOT NULL,
    parent_hash TEXT,
    author_name TEXT NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(repository_id, commit_hash),
    CHECK (length(commit_hash) >= 7),
    CHECK (length(trim(author_name)) > 0)
);

CREATE TABLE document_records (
    document_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    external_key TEXT NOT NULL,
    document JSONB NOT NULL,
    version BIGINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(repository_id, external_key),
    CHECK (jsonb_typeof(document) = 'object'),
    CHECK (version > 0)
);

CREATE INDEX document_records_document_gin_idx
    ON document_records USING GIN(document);

CREATE TABLE wide_column_rows (
    row_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    partition_key TEXT NOT NULL,
    clustering_key TEXT NOT NULL,
    columns JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(repository_id, partition_key, clustering_key),
    CHECK (jsonb_typeof(columns) = 'object')
);

CREATE INDEX wide_column_partition_idx
    ON wide_column_rows(repository_id, partition_key, clustering_key);

CREATE TABLE graph_nodes (
    node_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    external_id TEXT NOT NULL,
    node_type node_kind NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(repository_id, external_id),
    CHECK (jsonb_typeof(properties) = 'object')
);

CREATE TABLE graph_edges (
    edge_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    source_node_id BIGINT NOT NULL
        REFERENCES graph_nodes(node_id)
        ON DELETE CASCADE,
    target_node_id BIGINT NOT NULL
        REFERENCES graph_nodes(node_id)
        ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (source_node_id <> target_node_id),
    CHECK (length(trim(relationship)) > 0),
    CHECK (jsonb_typeof(properties) = 'object')
);

CREATE INDEX graph_edges_source_idx
    ON graph_edges(repository_id, source_node_id);

CREATE INDEX graph_edges_target_idx
    ON graph_edges(repository_id, target_node_id);

CREATE TABLE replicas (
    replica_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    replica_name TEXT NOT NULL,
    region TEXT NOT NULL,
    applied_version BIGINT NOT NULL DEFAULT 0,
    UNIQUE(repository_id, replica_name),
    CHECK (applied_version >= 0),
    CHECK (length(trim(region)) > 0)
);

CREATE TABLE replication_events (
    replication_event_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    replica_id BIGINT NOT NULL
        REFERENCES replicas(replica_id)
        ON DELETE CASCADE,
    record_key TEXT NOT NULL,
    source_version BIGINT NOT NULL,
    state replication_state NOT NULL DEFAULT 'queued',
    queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_at TIMESTAMPTZ,
    CHECK (source_version > 0),
    CHECK (
        (state = 'applied' AND applied_at IS NOT NULL)
        OR state <> 'applied'
    )
);

CREATE INDEX replication_queue_idx
    ON replication_events(replica_id, state, queued_at);

CREATE TABLE users (
    user_id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT true,
    CHECK (length(trim(username)) > 0)
);

CREATE TABLE pull_requests (
    pull_request_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    source_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),
    target_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('draft', 'open', 'closed', 'merged')),
    source_head_version BIGINT NOT NULL,
    target_head_version BIGINT NOT NULL,
    created_by BIGINT NOT NULL
        REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ,
    CHECK (source_branch_id <> target_branch_id),
    CHECK (length(trim(title)) > 0),
    CHECK (source_head_version >= 0),
    CHECK (target_head_version >= 0)
);

CREATE TABLE reviews (
    review_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL
        REFERENCES users(user_id),
    state TEXT NOT NULL
        CHECK (state IN ('approved', 'changes_requested', 'commented', 'dismissed')),
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_source_version BIGINT NOT NULL,
    UNIQUE(pull_request_id, reviewer_id, reviewed_source_version)
);

CREATE INDEX reviews_pr_idx
    ON reviews(pull_request_id, state);

CREATE TABLE review_comments (
    comment_id BIGSERIAL PRIMARY KEY,
    review_id BIGINT NOT NULL
        REFERENCES reviews(review_id)
        ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    line_number INTEGER,
    body TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(trim(body)) > 0),
    CHECK (line_number IS NULL OR line_number > 0)
);

CREATE TABLE status_checks (
    status_check_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    state check_state NOT NULL DEFAULT 'pending',
    completed_at TIMESTAMPTZ,
    UNIQUE(pull_request_id, check_name)
);

CREATE TABLE branch_protection_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    branch_id BIGINT NOT NULL UNIQUE
        REFERENCES branches(branch_id)
        ON DELETE CASCADE,
    required_reviews INTEGER NOT NULL DEFAULT 0,
    require_conversation_resolution BOOLEAN NOT NULL DEFAULT true,
    require_linear_history BOOLEAN NOT NULL DEFAULT false,
    allow_force_push BOOLEAN NOT NULL DEFAULT false,
    allow_deletion BOOLEAN NOT NULL DEFAULT false,
    allow_direct_push BOOLEAN NOT NULL DEFAULT false,
    CHECK (required_reviews >= 0)
);

CREATE TABLE required_status_checks (
    policy_id BIGINT NOT NULL
        REFERENCES branch_protection_policies(policy_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    PRIMARY KEY(policy_id, check_name)
);

CREATE TABLE approval_requirements (
    requirement_id BIGSERIAL PRIMARY KEY,
    policy_id BIGINT NOT NULL
        REFERENCES branch_protection_policies(policy_id)
        ON DELETE CASCADE,
    reviewer_role TEXT NOT NULL,
    minimum_approvals INTEGER NOT NULL,
    UNIQUE(policy_id, reviewer_role),
    CHECK (minimum_approvals > 0),
    CHECK (length(trim(reviewer_role)) > 0)
);

CREATE OR REPLACE FUNCTION enforce_document_version()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.version <= OLD.version THEN
        RAISE EXCEPTION
            'Document version must increase: old %, new %',
            OLD.version,
            NEW.version;
    END IF;

    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER document_version_trigger
BEFORE UPDATE ON document_records
FOR EACH ROW
EXECUTE FUNCTION enforce_document_version();

CREATE OR REPLACE FUNCTION evaluate_pull_request(
    p_pull_request_id BIGINT
)
RETURNS TABLE (
    pull_request_id BIGINT,
    eligible BOOLEAN,
    approval_count BIGINT,
    failed_checks BIGINT,
    unresolved_comments BIGINT,
    reasons TEXT[]
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_target_branch BIGINT;
    v_required_reviews INTEGER;
    v_require_conversations BOOLEAN;
    v_required_checks INTEGER;
    v_failed_checks BIGINT;
    v_approvals BIGINT;
    v_unresolved BIGINT;
    v_reasons TEXT[] := ARRAY[]::TEXT[];
BEGIN
    SELECT
        pr.target_branch_id,
        COALESCE(bp.required_reviews, 0),
        COALESCE(bp.require_conversation_resolution, false)
    INTO
        v_target_branch,
        v_required_reviews,
        v_require_conversations
    FROM pull_requests pr
    LEFT JOIN branch_protection_policies bp
        ON bp.branch_id = pr.target_branch_id
    WHERE pr.pull_request_id = p_pull_request_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Pull Request % does not exist',
            p_pull_request_id;
    END IF;

    SELECT COUNT(*)
    INTO v_approvals
    FROM reviews r
    JOIN pull_requests pr
        ON pr.pull_request_id = r.pull_request_id
    WHERE r.pull_request_id = p_pull_request_id
      AND r.state = 'approved'
      AND r.reviewed_source_version = pr.source_head_version;

    SELECT COUNT(*)
    INTO v_failed_checks
    FROM status_checks sc
    WHERE sc.pull_request_id = p_pull_request_id
      AND sc.state <> 'passed';

    SELECT COUNT(*)
    INTO v_unresolved
    FROM review_comments rc
    JOIN reviews r
        ON r.review_id = rc.review_id
    WHERE r.pull_request_id = p_pull_request_id
      AND rc.resolved = false;

    SELECT COUNT(*)
    INTO v_required_checks
    FROM required_status_checks rsc
    JOIN branch_protection_policies bp
        ON bp.policy_id = rsc.policy_id
    WHERE bp.branch_id = v_target_branch;

    IF v_approvals < v_required_reviews THEN
        v_reasons := array_append(
            v_reasons,
            format(
                'Required approvals: %s, current approvals: %s',
                v_required_reviews,
                v_approvals
            )
        );
    END IF;

    IF v_failed_checks > 0 OR v_required_checks = 0 THEN
        IF v_failed_checks > 0 THEN
            v_reasons := array_append(
                v_reasons,
                'One or more required status checks are not passing'
            );
        END IF;
    END IF;

    IF v_require_conversations AND v_unresolved > 0 THEN
        v_reasons := array_append(
            v_reasons,
            'Unresolved review conversations remain'
        );
    END IF;

    RETURN QUERY
    SELECT
        p_pull_request_id,
        cardinality(v_reasons) = 0,
        v_approvals,
        v_failed_checks,
        v_unresolved,
        v_reasons;
END;
$$;

CREATE VIEW repository_replication_health AS
SELECT
    r.repository_id,
    r.repository_name,
    r.consistency,
    rp.replica_name,
    rp.region,
    rp.applied_version,
    COALESCE(
        MAX(re.source_version) FILTER (
            WHERE re.state = 'queued'
        ),
        rp.applied_version
    ) AS highest_queued_version,
    COUNT(*) FILTER (
        WHERE re.state = 'queued'
    ) AS queued_events
FROM repositories r
JOIN replicas rp
    ON rp.repository_id = r.repository_id
LEFT JOIN replication_events re
    ON re.replica_id = rp.replica_id
GROUP BY
    r.repository_id,
    r.repository_name,
    r.consistency,
    rp.replica_id,
    rp.replica_name,
    rp.region,
    rp.applied_version;

INSERT INTO repositories (
    repository_name,
    owner_name,
    database_kind,
    consistency
)
VALUES
    (
        'security-events',
        'security-team',
        'document',
        'eventual'
    ),
    (
        'session-store',
        'platform-team',
        'key_value',
        'strong'
    ),
    (
        'device-telemetry',
        'operations-team',
        'wide_column',
        'eventual'
    ),
    (
        'access-graph',
        'security-team',
        'graph',
        'strong'
    );

INSERT INTO branches (
    repository_id,
    branch_name,
    is_protected,
    head_version
)
SELECT
    repository_id,
    'main',
    true,
    12
FROM repositories;

INSERT INTO branches (
    repository_id,
    branch_name,
    is_protected,
    head_version
)
SELECT
    repository_id,
    'feature/nosql-policy',
    false,
    7
FROM repositories
WHERE repository_name = 'security-events';

INSERT INTO users (username)
VALUES
    ('anita'),
    ('ravi'),
    ('reviewer-security'),
    ('reviewer-platform');

INSERT INTO document_records (
    repository_id,
    external_key,
    document,
    version
)
SELECT
    repository_id,
    'incident-1001',
    '{
        "severity": "high",
        "source": "sensor-42",
        "status": "open",
        "tags": ["security", "network"]
    }'::jsonb,
    1
FROM repositories
WHERE repository_name = 'security-events';

INSERT INTO wide_column_rows (
    repository_id,
    partition_key,
    clustering_key,
    columns
)
SELECT
    repository_id,
    'device-42',
    '2026-10-31T11:00:00Z',
    '{"temperature": 31.2, "battery": 88}'::jsonb
FROM repositories
WHERE repository_name = 'device-telemetry';

INSERT INTO wide_column_rows (
    repository_id,
    partition_key,
    clustering_key,
    columns
)
SELECT
    repository_id,
    'device-42',
    '2026-10-31T11:01:00Z',
    '{"temperature": 31.4}'::jsonb
FROM repositories
WHERE repository_name = 'device-telemetry';

INSERT INTO graph_nodes (
    repository_id,
    external_id,
    node_type,
    properties
)
SELECT
    repository_id,
    node_data.external_id,
    node_data.node_type::node_kind,
    node_data.properties::jsonb
FROM repositories r
CROSS JOIN (
    VALUES
        (
            'alice',
            'user',
            '{"role":"analyst"}'
        ),
        (
            'service-orders',
            'service',
            '{"environment":"production"}'
        ),
        (
            'database-prod',
            'resource',
            '{"classification":"restricted"}'
        )
) AS node_data(external_id, node_type, properties)
WHERE r.repository_name = 'access-graph';

INSERT INTO graph_edges (
    repository_id,
    source_node_id,
    target_node_id,
    relationship
)
SELECT
    r.repository_id,
    source_node.node_id,
    service_node.node_id,
    'operates'
FROM repositories r
JOIN graph_nodes source_node
    ON source_node.repository_id = r.repository_id
   AND source_node.external_id = 'alice'
JOIN graph_nodes service_node
    ON service_node.repository_id = r.repository_id
   AND service_node.external_id = 'service-orders'
WHERE r.repository_name = 'access-graph';

INSERT INTO graph_edges (
    repository_id,
    source_node_id,
    target_node_id,
    relationship
)
SELECT
    r.repository_id,
    service_node.node_id,
    database_node.node_id,
    'accesses'
FROM repositories r
JOIN graph_nodes service_node
    ON service_node.repository_id = r.repository_id
   AND service_node.external_id = 'service-orders'
JOIN graph_nodes database_node
    ON database_node.repository_id = r.repository_id
   AND database_node.external_id = 'database-prod'
WHERE r.repository_name = 'access-graph';

INSERT INTO replicas (
    repository_id,
    replica_name,
    region,
    applied_version
)
SELECT
    repository_id,
    'replica-lucknow',
    'ap-south-1',
    3
FROM repositories
WHERE repository_name = 'security-events';

INSERT INTO replication_events (
    repository_id,
    replica_id,
    record_key,
    source_version,
    state
)
SELECT
    r.repository_id,
    rp.replica_id,
    'incident-1001',
    4,
    'queued'
FROM repositories r
JOIN replicas rp
    ON rp.repository_id = r.repository_id
WHERE r.repository_name = 'security-events';

INSERT INTO branch_protection_policies (
    branch_id,
    required_reviews,
    require_conversation_resolution,
    require_linear_history,
    allow_force_push,
    allow_deletion,
    allow_direct_push
)
SELECT
    branch_id,
    2,
    true,
    true,
    false,
    false,
    false
FROM branches b
JOIN repositories r
    ON r.repository_id = b.repository_id
WHERE r.repository_name = 'security-events'
  AND b.branch_name = 'main';

INSERT INTO required_status_checks (
    policy_id,
    check_name
)
SELECT
    policy_id,
    check_name
FROM branch_protection_policies bp
CROSS JOIN (
    VALUES
        ('unit-tests'),
        ('security-scan')
) AS checks(check_name)
JOIN branches b
    ON b.branch_id = bp.branch_id
JOIN repositories r
    ON r.repository_id = b.repository_id
WHERE r.repository_name = 'security-events';

INSERT INTO approval_requirements (
    policy_id,
    reviewer_role,
    minimum_approvals
)
SELECT
    policy_id,
    'security-reviewer',
    1
FROM branch_protection_policies;

INSERT INTO commits (
    repository_id,
    branch_id,
    commit_hash,
    parent_hash,
    author_name
)
SELECT
    r.repository_id,
    b.branch_id,
    'abc1234567890',
    NULL,
    'anita'
FROM repositories r
JOIN branches b
    ON b.repository_id = r.repository_id
WHERE r.repository_name = 'security-events'
  AND b.branch_name = 'feature/nosql-policy';

INSERT INTO commits (
    repository_id,
    branch_id,
    commit_hash,
    parent_hash,
    author_name
)
SELECT
    r.repository_id,
    b.branch_id,
    'def9876543210',
    'abc1234567890',
    'anita'
FROM repositories r
JOIN branches b
    ON b.repository_id = r.repository_id
WHERE r.repository_name = 'security-events'
  AND b.branch_name = 'feature/nosql-policy';

INSERT INTO pull_requests (
    repository_id,
    source_branch_id,
    target_branch_id,
    title,
    status,
    source_head_version,
    target_head_version,
    created_by
)
SELECT
    r.repository_id,
    source_branch.branch_id,
    target_branch.branch_id,
    'Add NoSQL consistency policy',
    'open',
    source_branch.head_version,
    target_branch.head_version,
    u.user_id
FROM repositories r
JOIN branches source_branch
    ON source_branch.repository_id = r.repository_id
   AND source_branch.branch_name = 'feature/nosql-policy'
JOIN branches target_branch
    ON target_branch.repository_id = r.repository_id
   AND target_branch.branch_name = 'main'
JOIN users u
    ON u.username = 'anita'
WHERE r.repository_name = 'security-events';

INSERT INTO reviews (
    pull_request_id,
    reviewer_id,
    state,
    reviewed_source_version
)
SELECT
    pr.pull_request_id,
    u.user_id,
    'approved',
    pr.source_head_version
FROM pull_requests pr
JOIN users u
    ON u.username = 'reviewer-security'
WHERE pr.title = 'Add NoSQL consistency policy';

INSERT INTO reviews (
    pull_request_id,
    reviewer_id,
    state,
    reviewed_source_version
)
SELECT
    pr.pull_request_id,
    u.user_id,
    'approved',
    pr.source_head_version
FROM pull_requests pr
JOIN users u
    ON u.username = 'reviewer-platform'
WHERE pr.title = 'Add NoSQL consistency policy';

INSERT INTO status_checks (
    pull_request_id,
    check_name,
    state,
    completed_at
)
SELECT
    pull_request_id,
    'unit-tests',
    'passed',
    now()
FROM pull_requests
WHERE title = 'Add NoSQL consistency policy';

INSERT INTO status_checks (
    pull_request_id,
    check_name,
    state,
    completed_at
)
SELECT
    pull_request_id,
    'security-scan',
    'passed',
    now()
FROM pull_requests
WHERE title = 'Add NoSQL consistency policy';

INSERT INTO review_comments (
    review_id,
    file_path,
    line_number,
    body,
    resolved
)
SELECT
    review_id,
    'policy.json',
    17,
    'Replica reads should document their staleness semantics.',
    true
FROM reviews
LIMIT 1;

-- Retrieval: document-oriented querying.
SELECT
    external_key,
    document ->> 'severity' AS severity,
    document ->> 'status' AS status
FROM document_records
WHERE document @> '{"tags":["security"]}'::jsonb;

-- Wide-column access pattern: retrieve one partition in clustering order.
SELECT
    partition_key,
    clustering_key,
    columns
FROM wide_column_rows
WHERE repository_id = (
    SELECT repository_id
    FROM repositories
    WHERE repository_name = 'device-telemetry'
)
AND partition_key = 'device-42'
ORDER BY clustering_key;

-- Graph relationship retrieval.
SELECT
    source.external_id AS source_node,
    ge.relationship,
    target.external_id AS target_node
FROM graph_edges ge
JOIN graph_nodes source
    ON source.node_id = ge.source_node_id
JOIN graph_nodes target
    ON target.node_id = ge.target_node_id
WHERE ge.relationship = 'accesses';

-- Replication health exposes lag without pretending that eventual
-- consistency means all replicas contain the newest version.
SELECT *
FROM repository_replication_health
ORDER BY repository_name, replica_name;

-- Pull Request merge eligibility combines approvals, status checks,
-- and unresolved conversations without confusing those mechanisms.
SELECT *
FROM evaluate_pull_request(
    (
        SELECT pull_request_id
        FROM pull_requests
        WHERE title = 'Add NoSQL consistency policy'
    )
);

-- Transactional update of a replication event.
BEGIN;

UPDATE replication_events
SET state = 'applied',
    applied_at = now()
WHERE replication_event_id = (
    SELECT replication_event_id
    FROM replication_events
    WHERE state = 'queued'
    ORDER BY queued_at
    LIMIT 1
)
RETURNING replication_event_id, state, applied_at;

UPDATE replicas
SET applied_version = GREATEST(
    applied_version,
    (
        SELECT MAX(source_version)
        FROM replication_events
        WHERE replication_event_id = (
            SELECT MAX(replication_event_id)
            FROM replication_events
        )
    )
)
WHERE replica_name = 'replica-lucknow';

COMMIT;

-- Validation query: stale approvals can be identified when the reviewed
-- source version differs from the Pull Request's current source version.
SELECT
    pr.pull_request_id,
    u.username AS reviewer,
    r.reviewed_source_version,
    pr.source_head_version,
    CASE
        WHEN r.reviewed_source_version = pr.source_head_version
            THEN 'current'
        ELSE 'stale'
    END AS approval_status
FROM reviews r
JOIN pull_requests pr
    ON pr.pull_request_id = r.pull_request_id
JOIN users u
    ON u.user_id = r.reviewer_id
WHERE r.state = 'approved';

-- Aggregation: operational distribution by database model.
SELECT
    database_kind,
    consistency,
    COUNT(*) AS repository_count
FROM repositories
GROUP BY database_kind, consistency
ORDER BY database_kind, consistency;
