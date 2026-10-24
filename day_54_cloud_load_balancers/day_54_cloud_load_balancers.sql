CREATE SCHEMA IF NOT EXISTS cloud_lb;

SET search_path TO cloud_lb, public;

DROP VIEW IF EXISTS merge_eligibility;
DROP VIEW IF EXISTS target_health_report;
DROP VIEW IF EXISTS request_distribution;
DROP FUNCTION IF EXISTS evaluate_merge_eligibility(bigint);
DROP FUNCTION IF EXISTS validate_target_port();
DROP FUNCTION IF EXISTS prevent_invalid_health_check();
DROP TABLE IF EXISTS routing_events CASCADE;
DROP TABLE IF EXISTS status_checks CASCADE;
DROP TABLE IF EXISTS review_comments CASCADE;
DROP TABLE IF EXISTS reviews CASCADE;
DROP TABLE IF EXISTS pull_requests CASCADE;
DROP TABLE IF EXISTS commits CASCADE;
DROP TABLE IF EXISTS targets CASCADE;
DROP TABLE IF EXISTS health_checks CASCADE;
DROP TABLE IF EXISTS target_groups CASCADE;
DROP TABLE IF EXISTS listeners CASCADE;
DROP TABLE IF EXISTS branch_protection_policies CASCADE;
DROP TABLE IF EXISTS branches CASCADE;
DROP TABLE IF EXISTS repositories CASCADE;
DROP TABLE IF EXISTS users CASCADE;

CREATE TYPE load_balancer_type AS ENUM (
    'application',
    'network'
);

CREATE TYPE protocol_type AS ENUM (
    'HTTP',
    'HTTPS',
    'TCP',
    'TLS'
);

CREATE TYPE target_state AS ENUM (
    'healthy',
    'unhealthy',
    'draining'
);

CREATE TYPE health_result AS ENUM (
    'pass',
    'fail'
);

CREATE TYPE check_state AS ENUM (
    'passing',
    'failing',
    'unknown'
);

CREATE TYPE merge_status AS ENUM (
    'open',
    'merged',
    'closed'
);

CREATE TYPE review_state AS ENUM (
    'pending',
    'approved',
    'changes_requested',
    'commented',
    'dismissed'
);

CREATE TABLE repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    load_balancer_type load_balancer_type NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(name)) > 0)
);

CREATE TABLE users (
    user_id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(username)) > 0)
);

CREATE TABLE branches (
    branch_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id),
    name TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_protected BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (repository_id, name),
    CHECK (length(trim(name)) > 0)
);

CREATE TABLE branch_protection_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    branch_id BIGINT NOT NULL UNIQUE REFERENCES branches(branch_id)
        ON DELETE CASCADE,
    require_tls BOOLEAN NOT NULL DEFAULT TRUE,
    require_healthy_targets BOOLEAN NOT NULL DEFAULT TRUE,
    minimum_healthy_targets INTEGER NOT NULL DEFAULT 1,
    require_successful_health_check BOOLEAN NOT NULL DEFAULT TRUE,
    allow_direct_changes BOOLEAN NOT NULL DEFAULT FALSE,
    allow_force_operations BOOLEAN NOT NULL DEFAULT FALSE,
    allow_deletion BOOLEAN NOT NULL DEFAULT FALSE,
    require_connection_draining_for_replacement BOOLEAN NOT NULL DEFAULT TRUE,
    require_application_protocol BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (minimum_healthy_targets >= 0)
);

CREATE TABLE listeners (
    listener_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    protocol protocol_type NOT NULL,
    port INTEGER NOT NULL,
    target_group_name TEXT NOT NULL,
    UNIQUE (repository_id, protocol, port),
    CHECK (port BETWEEN 1 AND 65535)
);

CREATE TABLE target_groups (
    target_group_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    name TEXT NOT NULL,
    protocol protocol_type NOT NULL,
    port INTEGER NOT NULL,
    algorithm TEXT NOT NULL,
    UNIQUE (repository_id, name),
    CHECK (port BETWEEN 1 AND 65535),
    CHECK (
        algorithm IN (
            'round_robin',
            'flow_hash',
            'least_connections'
        )
    ),
    CHECK (
        (
            protocol IN ('HTTP', 'HTTPS')
            AND algorithm IN ('round_robin', 'least_connections')
        )
        OR
        (
            protocol IN ('TCP', 'TLS')
            AND algorithm IN ('flow_hash', 'least_connections')
        )
    )
);

CREATE TABLE health_checks (
    health_check_id BIGSERIAL PRIMARY KEY,
    target_group_id BIGINT NOT NULL UNIQUE
        REFERENCES target_groups(target_group_id)
        ON DELETE CASCADE,
    protocol protocol_type NOT NULL,
    port INTEGER NOT NULL,
    path TEXT,
    interval_seconds INTEGER NOT NULL DEFAULT 10,
    timeout_seconds INTEGER NOT NULL DEFAULT 3,
    healthy_threshold INTEGER NOT NULL DEFAULT 2,
    unhealthy_threshold INTEGER NOT NULL DEFAULT 3,
    last_result health_result,
    CHECK (port BETWEEN 1 AND 65535),
    CHECK (interval_seconds > 0),
    CHECK (timeout_seconds > 0),
    CHECK (timeout_seconds < interval_seconds),
    CHECK (healthy_threshold > 0),
    CHECK (unhealthy_threshold > 0),
    CHECK (
        protocol IN ('TCP', 'TLS')
        OR length(trim(path)) > 0
    )
);

CREATE TABLE targets (
    target_id BIGSERIAL PRIMARY KEY,
    target_group_id BIGINT NOT NULL
        REFERENCES target_groups(target_group_id)
        ON DELETE CASCADE,
    target_name TEXT NOT NULL,
    address INET NOT NULL,
    port INTEGER NOT NULL,
    availability_zone TEXT NOT NULL,
    state target_state NOT NULL DEFAULT 'healthy',
    active_connections INTEGER NOT NULL DEFAULT 0,
    last_health_result health_result,
    UNIQUE (target_group_id, target_name),
    CHECK (port BETWEEN 1 AND 65535),
    CHECK (active_connections >= 0),
    CHECK (length(trim(availability_zone)) > 0)
);

CREATE TABLE commits (
    commit_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id),
    branch_id BIGINT NOT NULL REFERENCES branches(branch_id),
    sha CHAR(40) NOT NULL UNIQUE,
    parent_sha CHAR(40),
    committed_by BIGINT NOT NULL REFERENCES users(user_id),
    committed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (sha ~ '^[0-9a-f]{40}$')
);

CREATE TABLE pull_requests (
    pull_request_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id),
    source_branch_id BIGINT NOT NULL REFERENCES branches(branch_id),
    target_branch_id BIGINT NOT NULL REFERENCES branches(branch_id),
    author_id BIGINT NOT NULL REFERENCES users(user_id),
    title TEXT NOT NULL,
    status merge_status NOT NULL DEFAULT 'open',
    draft BOOLEAN NOT NULL DEFAULT FALSE,
    head_commit_id BIGINT REFERENCES commits(commit_id),
    base_commit_id BIGINT REFERENCES commits(commit_id),
    mergeable BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    merged_at TIMESTAMPTZ,
    CHECK (source_branch_id <> target_branch_id),
    CHECK (length(trim(title)) > 0)
);

CREATE TABLE reviews (
    review_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL REFERENCES users(user_id),
    state review_state NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dismissed_at TIMESTAMPTZ,
    UNIQUE (pull_request_id, reviewer_id, submitted_at)
);

CREATE TABLE review_comments (
    comment_id BIGSERIAL PRIMARY KEY,
    review_id BIGINT NOT NULL REFERENCES reviews(review_id)
        ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    body TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (line_number > 0),
    CHECK (length(trim(body)) > 0)
);

CREATE TABLE status_checks (
    status_check_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    state check_state NOT NULL DEFAULT 'unknown',
    completed_at TIMESTAMPTZ,
    UNIQUE (pull_request_id, check_name)
);

CREATE TABLE routing_events (
    event_id BIGSERIAL PRIMARY KEY,
    target_id BIGINT NOT NULL REFERENCES targets(target_id),
    source_address INET,
    protocol protocol_type NOT NULL,
    source_port INTEGER,
    selected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        source_port IS NULL
        OR source_port BETWEEN 1 AND 65535
    )
);

CREATE INDEX idx_branches_repository
    ON branches(repository_id);

CREATE INDEX idx_targets_group_state
    ON targets(target_group_id, state);

CREATE INDEX idx_health_checks_result
    ON targets(target_group_id, last_health_result);

CREATE INDEX idx_status_checks_pr_state
    ON status_checks(pull_request_id, state);

CREATE INDEX idx_reviews_pr_state
    ON reviews(pull_request_id, state);

CREATE INDEX idx_routing_events_target_time
    ON routing_events(target_id, selected_at DESC);

-- Database-level protection against a target being registered on
-- a different port from its target group.
CREATE OR REPLACE FUNCTION validate_target_port()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    expected_port INTEGER;
BEGIN
    SELECT port
    INTO expected_port
    FROM target_groups
    WHERE target_group_id = NEW.target_group_id;

    IF expected_port IS NULL THEN
        RAISE EXCEPTION 'Target group % does not exist',
            NEW.target_group_id;
    END IF;

    IF NEW.port <> expected_port THEN
        RAISE EXCEPTION
            'Target port % does not match target-group port %',
            NEW.port,
            expected_port;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_target_port
BEFORE INSERT OR UPDATE ON targets
FOR EACH ROW
EXECUTE FUNCTION validate_target_port();

CREATE OR REPLACE FUNCTION prevent_invalid_health_check()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.protocol IN ('HTTP', 'HTTPS')
       AND (NEW.path IS NULL OR length(trim(NEW.path)) = 0) THEN
        RAISE EXCEPTION
            'HTTP/HTTPS health checks require a path';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_health_check
BEFORE INSERT OR UPDATE ON health_checks
FOR EACH ROW
EXECUTE FUNCTION prevent_invalid_health_check();

CREATE OR REPLACE FUNCTION evaluate_merge_eligibility(
    p_pull_request_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    healthy_target_count BIGINT,
    required_healthy_targets INTEGER,
    failing_checks BIGINT,
    required_reviews INTEGER,
    approvals BIGINT,
    unresolved_comments BIGINT,
    reason TEXT
)
LANGUAGE sql
AS $$
WITH pr AS (
    SELECT
        p.*,
        bp.require_healthy_targets,
        bp.minimum_healthy_targets,
        bp.require_successful_health_check,
        bp.require_application_protocol,
        bp.branch_id AS protected_branch_id
    FROM pull_requests p
    JOIN branch_protection_policies bp
      ON bp.branch_id = p.target_branch_id
    WHERE p.pull_request_id = p_pull_request_id
),
health AS (
    SELECT
        pr.pull_request_id,
        COUNT(t.target_id) FILTER (
            WHERE t.state = 'healthy'
        ) AS healthy_count
    FROM pr
    LEFT JOIN target_groups tg
      ON tg.repository_id = pr.repository_id
    LEFT JOIN targets t
      ON t.target_group_id = tg.target_group_id
    GROUP BY pr.pull_request_id
),
checks AS (
    SELECT
        p_pull_request_id AS pull_request_id,
        COUNT(*) FILTER (
            WHERE state = 'failing'
        ) AS failing
    FROM status_checks
    WHERE pull_request_id = p_pull_request_id
),
review_data AS (
    SELECT
        p_pull_request_id AS pull_request_id,
        COUNT(*) FILTER (
            WHERE state = 'approved'
              AND dismissed_at IS NULL
        ) AS approved_count
    FROM reviews
    WHERE pull_request_id = p_pull_request_id
),
comments AS (
    SELECT
        r.pull_request_id,
        COUNT(c.comment_id) FILTER (
            WHERE c.resolved = FALSE
        ) AS unresolved
    FROM reviews r
    LEFT JOIN review_comments c
      ON c.review_id = r.review_id
    WHERE r.pull_request_id = p_pull_request_id
    GROUP BY r.pull_request_id
)
SELECT
    (
        pr.status = 'open'
        AND NOT pr.draft
        AND pr.mergeable
        AND (
            NOT pr.require_healthy_targets
            OR health.healthy_count >= pr.minimum_healthy_targets
        )
        AND (
            NOT pr.require_successful_health_check
            OR checks.failing = 0
        )
        AND (
            NOT pr.require_application_protocol
            OR EXISTS (
                SELECT 1
                FROM target_groups tg
                WHERE tg.repository_id = pr.repository_id
                  AND tg.protocol IN ('HTTP', 'HTTPS')
            )
        )
        AND review_data.approved_count >= 2
        AND COALESCE(comments.unresolved, 0) = 0
    ) AS eligible,
    health.healthy_count,
    pr.minimum_healthy_targets,
    checks.failing,
    2 AS required_reviews,
    review_data.approved_count,
    COALESCE(comments.unresolved, 0),
    CASE
        WHEN pr.status <> 'open'
            THEN 'Pull Request is not open'
        WHEN pr.draft
            THEN 'Pull Request is still a draft'
        WHEN NOT pr.mergeable
            THEN 'Branch state reports conflicts or non-mergeable changes'
        WHEN pr.require_healthy_targets
             AND health.healthy_count < pr.minimum_healthy_targets
            THEN 'Insufficient healthy targets'
        WHEN pr.require_successful_health_check
             AND checks.failing > 0
            THEN 'One or more required health checks are failing'
        WHEN review_data.approved_count < 2
            THEN 'Required approvals are missing'
        WHEN COALESCE(comments.unresolved, 0) > 0
            THEN 'Review discussions remain unresolved'
        ELSE 'All configured merge conditions are satisfied'
    END AS reason
FROM pr
JOIN health
  ON health.pull_request_id = pr.pull_request_id
CROSS JOIN checks
CROSS JOIN review_data
LEFT JOIN comments
  ON comments.pull_request_id = pr.pull_request_id;
$$;

INSERT INTO repositories (name, load_balancer_type)
VALUES
    ('checkout-platform', 'application'),
    ('payment-gateway', 'network');

INSERT INTO users (username, email)
VALUES
    ('atul', 'atul@example.com'),
    ('maya', 'maya@example.com'),
    ('rohan', 'rohan@example.com'),
    ('neha', 'neha@example.com'),
    ('ops-bot', 'ops-bot@example.com');

INSERT INTO branches (
    repository_id,
    name,
    is_default,
    is_protected
)
SELECT
    repository_id,
    'main',
    TRUE,
    TRUE
FROM repositories
WHERE name IN ('checkout-platform', 'payment-gateway');

INSERT INTO branches (
    repository_id,
    name,
    is_default,
    is_protected
)
SELECT
    repository_id,
    'feature/load-balancer-health',
    FALSE,
    FALSE
FROM repositories
WHERE name = 'checkout-platform';

INSERT INTO branches (
    repository_id,
    name,
    is_default,
    is_protected
)
SELECT
    repository_id,
    'feature/tcp-draining',
    FALSE,
    FALSE
FROM repositories
WHERE name = 'payment-gateway';

INSERT INTO branch_protection_policies (
    branch_id,
    require_tls,
    require_healthy_targets,
    minimum_healthy_targets,
    require_successful_health_check,
    allow_direct_changes,
    allow_force_operations,
    allow_deletion,
    require_connection_draining_for_replacement,
    require_application_protocol
)
SELECT
    b.branch_id,
    TRUE,
    TRUE,
    2,
    TRUE,
    FALSE,
    FALSE,
    FALSE,
    TRUE,
    TRUE
FROM branches b
JOIN repositories r
  ON r.repository_id = b.repository_id
WHERE r.name = 'checkout-platform'
  AND b.name = 'main';

INSERT INTO branch_protection_policies (
    branch_id,
    require_tls,
    require_healthy_targets,
    minimum_healthy_targets,
    require_successful_health_check,
    allow_direct_changes,
    allow_force_operations,
    allow_deletion,
    require_connection_draining_for_replacement,
    require_application_protocol
)
SELECT
    b.branch_id,
    TRUE,
    TRUE,
    1,
    TRUE,
    FALSE,
    FALSE,
    FALSE,
    TRUE,
    FALSE
FROM branches b
JOIN repositories r
  ON r.repository_id = b.repository_id
WHERE r.name = 'payment-gateway'
  AND b.name = 'main';

INSERT INTO target_groups (
    repository_id,
    name,
    protocol,
    port,
    algorithm
)
SELECT
    repository_id,
    'checkout-web',
    'HTTP',
    8080,
    'round_robin'
FROM repositories
WHERE name = 'checkout-platform';

INSERT INTO target_groups (
    repository_id,
    name,
    protocol,
    port,
    algorithm
)
SELECT
    repository_id,
    'payment-tcp',
    'TCP',
    9000,
    'flow_hash'
FROM repositories
WHERE name = 'payment-gateway';

INSERT INTO listeners (
    repository_id,
    protocol,
    port,
    target_group_name
)
SELECT
    repository_id,
    'HTTPS',
    443,
    'checkout-web'
FROM repositories
WHERE name = 'checkout-platform';

INSERT INTO listeners (
    repository_id,
    protocol,
    port,
    target_group_name
)
SELECT
    repository_id,
    'TCP',
    443,
    'payment-tcp'
FROM repositories
WHERE name = 'payment-gateway';

INSERT INTO health_checks (
    target_group_id,
    protocol,
    port,
    path,
    interval_seconds,
    timeout_seconds,
    healthy_threshold,
    unhealthy_threshold,
    last_result
)
SELECT
    target_group_id,
    'HTTP',
    8080,
    '/health',
    10,
    3,
    2,
    3,
    'pass'
FROM target_groups
WHERE name = 'checkout-web';

INSERT INTO health_checks (
    target_group_id,
    protocol,
    port,
    interval_seconds,
    timeout_seconds,
    healthy_threshold,
    unhealthy_threshold,
    last_result
)
SELECT
    target_group_id,
    'TCP',
    9000,
    10,
    3,
    2,
    3,
    'pass'
FROM target_groups
WHERE name = 'payment-tcp';

INSERT INTO targets (
    target_group_id,
    target_name,
    address,
    port,
    availability_zone,
    state,
    active_connections,
    last_health_result
)
SELECT
    target_group_id,
    'checkout-a',
    '10.10.1.10',
    8080,
    'zone-a',
    'healthy',
    3,
    'pass'
FROM target_groups
WHERE name = 'checkout-web';

INSERT INTO targets (
    target_group_id,
    target_name,
    address,
    port,
    availability_zone,
    state,
    active_connections,
    last_health_result
)
SELECT
    target_group_id,
    'checkout-b',
    '10.10.2.10',
    8080,
    'zone-b',
    'healthy',
    2,
    'pass'
FROM target_groups
WHERE name = 'checkout-web';

INSERT INTO targets (
    target_group_id,
    target_name,
    address,
    port,
    availability_zone,
    state,
    active_connections,
    last_health_result
)
SELECT
    target_group_id,
    'checkout-c',
    '10.10.3.10',
    8080,
    'zone-c',
    'unhealthy',
    0,
    'fail'
FROM target_groups
WHERE name = 'checkout-web';

INSERT INTO targets (
    target_group_id,
    target_name,
    address,
    port,
    availability_zone,
    state,
    active_connections,
    last_health_result
)
SELECT
    target_group_id,
    'payment-a',
    '10.20.1.10',
    9000,
    'zone-a',
    'healthy',
    4,
    'pass'
FROM target_groups
WHERE name = 'payment-tcp';

INSERT INTO targets (
    target_group_id,
    target_name,
    address,
    port,
    availability_zone,
    state,
    active_connections,
    last_health_result
)
SELECT
    target_group_id,
    'payment-b',
    '10.20.2.10',
    9000,
    'zone-b',
    'draining',
    7,
    'pass'
FROM target_groups
WHERE name = 'payment-tcp';

INSERT INTO commits (
    repository_id,
    branch_id,
    sha,
    parent_sha,
    committed_by
)
SELECT
    r.repository_id,
    b.branch_id,
    '1111111111111111111111111111111111111111',
    NULL,
    u.user_id
FROM repositories r
JOIN branches b
  ON b.repository_id = r.repository_id
 AND b.name = 'main'
JOIN users u
  ON u.username = 'atul'
WHERE r.name = 'checkout-platform';

INSERT INTO commits (
    repository_id,
    branch_id,
    sha,
    parent_sha,
    committed_by
)
SELECT
    r.repository_id,
    b.branch_id,
    '2222222222222222222222222222222222222222',
    '1111111111111111111111111111111111111111',
    u.user_id
FROM repositories r
JOIN branches b
  ON b.repository_id = r.repository_id
 AND b.name = 'feature/load-balancer-health'
JOIN users u
  ON u.username = 'atul'
WHERE r.name = 'checkout-platform';

INSERT INTO pull_requests (
    repository_id,
    source_branch_id,
    target_branch_id,
    author_id,
    title,
    status,
    draft,
    head_commit_id,
    base_commit_id,
    mergeable
)
SELECT
    r.repository_id,
    source.branch_id,
    target.branch_id,
    author.user_id,
    'Improve target health routing',
    'open',
    FALSE,
    head.commit_id,
    base.commit_id,
    TRUE
FROM repositories r
JOIN branches source
  ON source.repository_id = r.repository_id
 AND source.name = 'feature/load-balancer-health'
JOIN branches target
  ON target.repository_id = r.repository_id
 AND target.name = 'main'
JOIN users author
  ON author.username = 'atul'
JOIN commits head
  ON head.sha = '2222222222222222222222222222222222222222'
JOIN commits base
  ON base.sha = '1111111111111111111111111111111111111111'
WHERE r.name = 'checkout-platform';

INSERT INTO reviews (
    pull_request_id,
    reviewer_id,
    state
)
SELECT
    pr.pull_request_id,
    u.user_id,
    'approved'
FROM pull_requests pr
JOIN users u
  ON u.username IN ('maya', 'rohan')
WHERE pr.title = 'Improve target health routing';

INSERT INTO review_comments (
    review_id,
    file_path,
    line_number,
    body,
    resolved
)
SELECT
    review_id,
    'health-check-policy.txt',
    42,
    'Health-check timeout must remain below the interval.',
    TRUE
FROM reviews
WHERE state = 'approved';

INSERT INTO status_checks (
    pull_request_id,
    check_name,
    state,
    completed_at
)
SELECT
    pull_request_id,
    'health-check-integration',
    'passing',
    CURRENT_TIMESTAMP
FROM pull_requests
WHERE title = 'Improve target health routing';

INSERT INTO status_checks (
    pull_request_id,
    check_name,
    state,
    completed_at
)
SELECT
    pull_request_id,
    'target-capacity',
    'passing',
    CURRENT_TIMESTAMP
FROM pull_requests
WHERE title = 'Improve target health routing';

CREATE OR REPLACE VIEW target_health_report AS
SELECT
    r.name AS repository,
    tg.name AS target_group,
    tg.protocol,
    tg.port,
    COUNT(t.target_id) AS total_targets,
    COUNT(t.target_id) FILTER (
        WHERE t.state = 'healthy'
    ) AS healthy_targets,
    COUNT(t.target_id) FILTER (
        WHERE t.state = 'unhealthy'
    ) AS unhealthy_targets,
    COUNT(t.target_id) FILTER (
        WHERE t.state = 'draining'
    ) AS draining_targets
FROM repositories r
JOIN target_groups tg
  ON tg.repository_id = r.repository_id
LEFT JOIN targets t
  ON t.target_group_id = tg.target_group_id
GROUP BY
    r.name,
    tg.name,
    tg.protocol,
    tg.port;

CREATE OR REPLACE VIEW request_distribution AS
SELECT
    r.name AS repository,
    tg.name AS target_group,
    t.target_name,
    t.state,
    COUNT(re.event_id) AS routing_events
FROM repositories r
JOIN target_groups tg
  ON tg.repository_id = r.repository_id
JOIN targets t
  ON t.target_group_id = tg.target_group_id
LEFT JOIN routing_events re
  ON re.target_id = t.target_id
GROUP BY
    r.name,
    tg.name,
    t.target_name,
    t.state;

CREATE OR REPLACE VIEW merge_eligibility AS
SELECT
    pr.pull_request_id,
    r.name AS repository,
    pr.title,
    result.eligible,
    result.healthy_target_count,
    result.required_healthy_targets,
    result.failing_checks,
    result.required_reviews,
    result.approvals,
    result.unresolved_comments,
    result.reason
FROM pull_requests pr
JOIN repositories r
  ON r.repository_id = pr.repository_id
CROSS JOIN LATERAL evaluate_merge_eligibility(
    pr.pull_request_id
) AS result;

-- Record representative routing activity for reporting.
INSERT INTO routing_events (
    target_id,
    source_address,
    protocol,
    source_port
)
SELECT
    target_id,
    '192.0.2.10',
    'HTTPS',
    51001
FROM targets
WHERE target_name = 'checkout-a';

INSERT INTO routing_events (
    target_id,
    source_address,
    protocol,
    source_port
)
SELECT
    target_id,
    '192.0.2.11',
    'HTTPS',
    51002
FROM targets
WHERE target_name = 'checkout-b';

INSERT INTO routing_events (
    target_id,
    source_address,
    protocol,
    source_port
)
SELECT
    target_id,
    '198.51.100.10',
    'TCP',
    52001
FROM targets
WHERE target_name = 'payment-a';

-- Transactional demonstration:
-- mark an unhealthy target unavailable for new traffic while retaining
-- existing connections. The row remains present for operational visibility.
BEGIN;

UPDATE targets
SET state = 'draining'
WHERE target_name = 'checkout-c'
  AND state = 'unhealthy';

COMMIT;

-- 1. Target health by group.
SELECT *
FROM target_health_report
ORDER BY repository, target_group;

-- 2. Targets eligible for new connections.
SELECT
    tg.name AS target_group,
    t.target_name,
    t.address,
    t.port,
    t.availability_zone
FROM target_groups tg
JOIN targets t
  ON t.target_group_id = tg.target_group_id
WHERE t.state = 'healthy'
ORDER BY tg.name, t.target_name;

-- 3. Health-check failure investigation.
SELECT
    r.name AS repository,
    tg.name AS target_group,
    t.target_name,
    t.last_health_result,
    t.state,
    hc.interval_seconds,
    hc.timeout_seconds,
    hc.unhealthy_threshold
FROM repositories r
JOIN target_groups tg
  ON tg.repository_id = r.repository_id
JOIN targets t
  ON t.target_group_id = tg.target_group_id
JOIN health_checks hc
  ON hc.target_group_id = tg.target_group_id
WHERE t.state <> 'healthy'
ORDER BY r.name, tg.name, t.target_name;

-- 4. Routing distribution.
SELECT *
FROM request_distribution
ORDER BY repository, target_group, target_name;

-- 5. Pull Request merge eligibility and the governing reason.
SELECT *
FROM merge_eligibility
ORDER BY repository, pull_request_id;

-- 6. Aggregate active connections by availability zone.
SELECT
    tg.name AS target_group,
    t.availability_zone,
    SUM(t.active_connections) AS active_connections
FROM target_groups tg
JOIN targets t
  ON t.target_group_id = tg.target_group_id
GROUP BY tg.name, t.availability_zone
ORDER BY tg.name, t.availability_zone;

-- 7. Verify protected branch controls.
SELECT
    r.name AS repository,
    b.name AS branch,
    b.is_protected,
    p.require_tls,
    p.require_healthy_targets,
    p.minimum_healthy_targets,
    p.require_successful_health_check,
    p.allow_direct_changes,
    p.allow_force_operations,
    p.allow_deletion,
    p.require_connection_draining_for_replacement
FROM repositories r
JOIN branches b
  ON b.repository_id = r.repository_id
JOIN branch_protection_policies p
  ON p.branch_id = b.branch_id
WHERE b.is_protected
ORDER BY r.name;
