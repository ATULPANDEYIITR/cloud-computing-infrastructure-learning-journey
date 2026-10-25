DROP SCHEMA IF EXISTS compute_storage_project CASCADE;

CREATE SCHEMA compute_storage_project;

SET search_path TO compute_storage_project, public;

-- ============================================================
-- Core infrastructure model
-- ============================================================

CREATE TYPE instance_state AS ENUM (
    'running',
    'unhealthy',
    'stopped'
);

CREATE TYPE object_state AS ENUM (
    'available',
    'deleted'
);

CREATE TYPE backup_state AS ENUM (
    'available',
    'restoring',
    'failed',
    'expired'
);

CREATE TYPE pull_request_state AS ENUM (
    'open',
    'merged',
    'closed'
);

-- Repositories represent deployable applications.
CREATE TABLE repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    environment TEXT NOT NULL CHECK (
        environment IN ('development', 'staging', 'production')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE compute_instances (
    instance_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    instance_name TEXT NOT NULL,
    state instance_state NOT NULL DEFAULT 'running',
    capacity_requests INTEGER NOT NULL CHECK (capacity_requests > 0),
    active_requests INTEGER NOT NULL DEFAULT 0 CHECK (
        active_requests >= 0
        AND active_requests <= capacity_requests
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(repository_id, instance_name)
);

CREATE INDEX idx_compute_repository_state
    ON compute_instances(repository_id, state);

CREATE TABLE branches (
    branch_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    branch_name TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(repository_id, branch_name)
);

CREATE UNIQUE INDEX uq_one_default_branch
    ON branches(repository_id)
    WHERE is_default = TRUE;

CREATE TABLE commits (
    commit_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    branch_id BIGINT
        REFERENCES branches(branch_id)
        ON DELETE SET NULL,
    commit_hash TEXT NOT NULL,
    parent_hash TEXT,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(repository_id, commit_hash)
);

CREATE INDEX idx_commits_branch_created
    ON commits(branch_id, created_at DESC);

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
    description TEXT,
    state pull_request_state NOT NULL DEFAULT 'open',
    head_commit_id BIGINT
        REFERENCES commits(commit_id),
    base_commit_id BIGINT
        REFERENCES commits(commit_id),
    draft BOOLEAN NOT NULL DEFAULT FALSE,
    mergeable BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    merged_at TIMESTAMPTZ,
    CHECK (source_branch_id <> target_branch_id),
    CHECK (
        (state = 'merged' AND merged_at IS NOT NULL)
        OR state <> 'merged'
    )
);

CREATE INDEX idx_pull_requests_repository_state
    ON pull_requests(repository_id, state);

CREATE INDEX idx_pull_requests_target_state
    ON pull_requests(target_branch_id, state);

-- ============================================================
-- Object storage
-- ============================================================

CREATE TABLE storage_objects (
    object_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    object_key TEXT NOT NULL,
    object_size_bytes BIGINT NOT NULL CHECK (object_size_bytes >= 0),
    checksum_sha256 TEXT NOT NULL,
    state object_state NOT NULL DEFAULT 'available',
    version_number INTEGER NOT NULL DEFAULT 1 CHECK (version_number > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(repository_id, object_key, version_number)
);

CREATE INDEX idx_storage_objects_repository_key
    ON storage_objects(repository_id, object_key);

CREATE TABLE backups (
    backup_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    backup_name TEXT NOT NULL,
    state backup_state NOT NULL DEFAULT 'available',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > created_at),
    UNIQUE(repository_id, backup_name)
);

CREATE INDEX idx_backups_repository_state
    ON backups(repository_id, state, created_at DESC);

CREATE TABLE backup_objects (
    backup_id BIGINT NOT NULL
        REFERENCES backups(backup_id)
        ON DELETE CASCADE,
    object_id BIGINT NOT NULL
        REFERENCES storage_objects(object_id)
        ON DELETE RESTRICT,
    object_size_bytes BIGINT NOT NULL CHECK (object_size_bytes >= 0),
    checksum_sha256 TEXT NOT NULL,
    PRIMARY KEY (backup_id, object_id)
);

-- ============================================================
-- Health and load-balancing state
-- ============================================================

CREATE TABLE health_checks (
    health_check_id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL
        REFERENCES compute_instances(instance_id)
        ON DELETE CASCADE,
    healthy BOOLEAN NOT NULL,
    response_ms INTEGER CHECK (response_ms >= 0),
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_health_checks_instance_time
    ON health_checks(instance_id, checked_at DESC);

CREATE TABLE request_samples (
    request_sample_id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL
        REFERENCES compute_instances(instance_id)
        ON DELETE CASCADE,
    request_count INTEGER NOT NULL CHECK (request_count > 0),
    sampled_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- Branch protection and deployment governance
-- ============================================================

CREATE TABLE branch_protection_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    branch_id BIGINT NOT NULL UNIQUE
        REFERENCES branches(branch_id)
        ON DELETE CASCADE,
    require_pull_request BOOLEAN NOT NULL DEFAULT TRUE,
    required_approvals INTEGER NOT NULL DEFAULT 1 CHECK (
        required_approvals >= 0
    ),
    require_status_checks BOOLEAN NOT NULL DEFAULT TRUE,
    require_conversation_resolution BOOLEAN NOT NULL DEFAULT TRUE,
    prohibit_direct_push BOOLEAN NOT NULL DEFAULT TRUE,
    prohibit_force_push BOOLEAN NOT NULL DEFAULT TRUE,
    prohibit_deletion BOOLEAN NOT NULL DEFAULT TRUE,
    require_linear_history BOOLEAN NOT NULL DEFAULT FALSE,
    allow_admin_bypass BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE deployment_requirements (
    requirement_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    minimum_healthy_instances INTEGER NOT NULL CHECK (
        minimum_healthy_instances > 0
    ),
    minimum_capacity_requests INTEGER NOT NULL CHECK (
        minimum_capacity_requests > 0
    ),
    backup_required BOOLEAN NOT NULL DEFAULT TRUE,
    backup_max_age INTERVAL NOT NULL DEFAULT INTERVAL '24 hours',
    UNIQUE(repository_id)
);

-- ============================================================
-- Code review and approval model
-- ============================================================

CREATE TABLE reviewers (
    reviewer_id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    role_name TEXT NOT NULL CHECK (
        role_name IN ('developer', 'maintainer', 'owner', 'administrator')
    )
);

CREATE TABLE reviews (
    review_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL
        REFERENCES reviewers(reviewer_id),
    review_state TEXT NOT NULL CHECK (
        review_state IN (
            'commented',
            'approved',
            'changes_requested',
            'dismissed'
        )
    ),
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(pull_request_id, reviewer_id, submitted_at)
);

CREATE INDEX idx_reviews_pr_state
    ON reviews(pull_request_id, review_state);

CREATE TABLE review_comments (
    comment_id BIGSERIAL PRIMARY KEY,
    review_id BIGINT NOT NULL
        REFERENCES reviews(review_id)
        ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    line_number INTEGER CHECK (line_number > 0),
    comment_text TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_review_comments_review_resolution
    ON review_comments(review_id, resolved);

CREATE TABLE status_checks (
    status_check_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'passed', 'failed')
    ),
    completed_at TIMESTAMPTZ,
    UNIQUE(pull_request_id, check_name)
);

CREATE TABLE conversations (
    conversation_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    subject TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_conversations_pr_resolution
    ON conversations(pull_request_id, resolved);

-- ============================================================
-- Trigger: protect active request accounting
-- ============================================================

CREATE OR REPLACE FUNCTION validate_instance_request_count()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.active_requests < 0
       OR NEW.active_requests > NEW.capacity_requests THEN
        RAISE EXCEPTION
            'active_requests must be between 0 and capacity_requests';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_instance_requests
BEFORE INSERT OR UPDATE OF active_requests, capacity_requests
ON compute_instances
FOR EACH ROW
EXECUTE FUNCTION validate_instance_request_count();

-- ============================================================
-- Trigger: merged PR must have a merge timestamp
-- ============================================================

CREATE OR REPLACE FUNCTION validate_pull_request_merge_state()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = 'merged' AND NEW.merged_at IS NULL THEN
        NEW.merged_at := now();
    END IF;

    IF NEW.state <> 'merged' THEN
        NEW.merged_at := NULL;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_pr_merge_state
BEFORE INSERT OR UPDATE OF state, merged_at
ON pull_requests
FOR EACH ROW
EXECUTE FUNCTION validate_pull_request_merge_state();

-- ============================================================
-- Sample repository
-- ============================================================

INSERT INTO repositories (
    name,
    environment
)
VALUES (
    'scalable-commerce-platform',
    'production'
);

INSERT INTO branches (
    repository_id,
    branch_name,
    is_default,
    protected
)
SELECT
    repository_id,
    'main',
    TRUE,
    TRUE
FROM repositories
WHERE name = 'scalable-commerce-platform';

INSERT INTO branches (
    repository_id,
    branch_name
)
SELECT
    repository_id,
    'feature/storage-cache'
FROM repositories
WHERE name = 'scalable-commerce-platform';

INSERT INTO branches (
    repository_id,
    branch_name
)
SELECT
    repository_id,
    'feature/load-balancer'
FROM repositories
WHERE name = 'scalable-commerce-platform';

-- ============================================================
-- Compute fleet
-- ============================================================

INSERT INTO compute_instances (
    repository_id,
    instance_name,
    state,
    capacity_requests,
    active_requests
)
SELECT
    repository_id,
    instance_name,
    'running',
    capacity,
    0
FROM repositories
CROSS JOIN (
    VALUES
        ('app-01', 100),
        ('app-02', 100),
        ('app-03', 100)
) AS fleet(instance_name, capacity)
WHERE repositories.name = 'scalable-commerce-platform';

-- ============================================================
-- Storage objects
-- ============================================================

INSERT INTO storage_objects (
    repository_id,
    object_key,
    object_size_bytes,
    checksum_sha256
)
SELECT
    repository_id,
    object_key,
    object_size_bytes,
    checksum
FROM repositories
CROSS JOIN (
    VALUES
        (
            'releases/v1/config.json',
            256,
            '8a5e7b9c7f2d4e1b'
        ),
        (
            'releases/v1/index.html',
            4096,
            '4f5c8d7e1a2b3c4d'
        )
) AS objects(
    object_key,
    object_size_bytes,
    checksum
)
WHERE repositories.name = 'scalable-commerce-platform';

-- ============================================================
-- Backup and backup membership
-- ============================================================

INSERT INTO backups (
    repository_id,
    backup_name,
    state,
    created_at,
    expires_at
)
SELECT
    repository_id,
    'production-2026-10-25-1200',
    'available',
    now() - INTERVAL '1 hour',
    now() + INTERVAL '6 days'
FROM repositories
WHERE name = 'scalable-commerce-platform';

INSERT INTO backup_objects (
    backup_id,
    object_id,
    object_size_bytes,
    checksum_sha256
)
SELECT
    b.backup_id,
    o.object_id,
    o.object_size_bytes,
    o.checksum_sha256
FROM backups b
JOIN storage_objects o
    ON o.repository_id = b.repository_id
WHERE b.backup_name = 'production-2026-10-25-1200'
  AND o.state = 'available';

-- ============================================================
-- Branch protection
-- ============================================================

INSERT INTO branch_protection_policies (
    branch_id,
    require_pull_request,
    required_approvals,
    require_status_checks,
    require_conversation_resolution,
    prohibit_direct_push,
    prohibit_force_push,
    prohibit_deletion,
    require_linear_history,
    allow_admin_bypass
)
SELECT
    branch_id,
    TRUE,
    2,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    FALSE
FROM branches
WHERE branch_name = 'main';

INSERT INTO deployment_requirements (
    repository_id,
    minimum_healthy_instances,
    minimum_capacity_requests,
    backup_required,
    backup_max_age
)
SELECT
    repository_id,
    2,
    200,
    TRUE,
    INTERVAL '24 hours'
FROM repositories
WHERE name = 'scalable-commerce-platform';

-- ============================================================
-- Reviewers
-- ============================================================

INSERT INTO reviewers (
    username,
    active,
    role_name
)
VALUES
    ('platform-owner', TRUE, 'owner'),
    ('senior-engineer', TRUE, 'maintainer'),
    ('application-engineer', TRUE, 'developer');

-- ============================================================
-- Commits
-- ============================================================

INSERT INTO commits (
    repository_id,
    branch_id,
    commit_hash,
    parent_hash,
    message
)
SELECT
    r.repository_id,
    b.branch_id,
    'abc123def456',
    NULL,
    'Add scalable storage configuration'
FROM repositories r
JOIN branches b
    ON b.repository_id = r.repository_id
WHERE r.name = 'scalable-commerce-platform'
  AND b.branch_name = 'feature/storage-cache';

INSERT INTO commits (
    repository_id,
    branch_id,
    commit_hash,
    parent_hash,
    message
)
SELECT
    r.repository_id,
    b.branch_id,
    'main001base',
    NULL,
    'Production baseline'
FROM repositories r
JOIN branches b
    ON b.repository_id = r.repository_id
WHERE r.name = 'scalable-commerce-platform'
  AND b.branch_name = 'main';

-- ============================================================
-- Pull Request
-- ============================================================

INSERT INTO pull_requests (
    repository_id,
    source_branch_id,
    target_branch_id,
    title,
    description,
    state,
    head_commit_id,
    base_commit_id,
    draft,
    mergeable
)
SELECT
    r.repository_id,
    source.branch_id,
    target.branch_id,
    'Scale application storage and compute',
    'Adds scalable storage handling and load-balancer configuration.',
    'open',
    head.commit_id,
    base.commit_id,
    FALSE,
    TRUE
FROM repositories r
JOIN branches source
    ON source.repository_id = r.repository_id
   AND source.branch_name = 'feature/storage-cache'
JOIN branches target
    ON target.repository_id = r.repository_id
   AND target.branch_name = 'main'
JOIN commits head
    ON head.commit_hash = 'abc123def456'
JOIN commits base
    ON base.commit_hash = 'main001base'
WHERE r.name = 'scalable-commerce-platform';

-- ============================================================
-- Reviews and comments
-- ============================================================

INSERT INTO reviews (
    pull_request_id,
    reviewer_id,
    review_state
)
SELECT
    pr.pull_request_id,
    r.reviewer_id,
    'approved'
FROM pull_requests pr
JOIN reviewers r
    ON r.username = 'platform-owner'
WHERE pr.title = 'Scale application storage and compute';

INSERT INTO reviews (
    pull_request_id,
    reviewer_id,
    review_state
)
SELECT
    pr.pull_request_id,
    r.reviewer_id,
    'approved'
FROM pull_requests pr
JOIN reviewers r
    ON r.username = 'senior-engineer'
WHERE pr.title = 'Scale application storage and compute';

INSERT INTO review_comments (
    review_id,
    file_path,
    line_number,
    comment_text,
    resolved
)
SELECT
    review_id,
    'infrastructure/storage.conf',
    42,
    'Checksum validation is required before accepting restored data.',
    TRUE
FROM reviews
WHERE review_state = 'approved'
ORDER BY review_id
LIMIT 1;

-- ============================================================
-- Conversations
-- ============================================================

INSERT INTO conversations (
    pull_request_id,
    subject,
    resolved
)
SELECT
    pull_request_id,
    'Confirm backup retention policy',
    TRUE
FROM pull_requests
WHERE title = 'Scale application storage and compute';

-- ============================================================
-- Automated status checks
-- ============================================================

INSERT INTO status_checks (
    pull_request_id,
    check_name,
    status,
    completed_at
)
SELECT
    pull_request_id,
    check_name,
    'passed',
    now()
FROM pull_requests
CROSS JOIN (
    VALUES
        ('unit-tests'),
        ('integration-tests'),
        ('security-scan'),
        ('capacity-validation')
) AS checks(check_name)
WHERE title = 'Scale application storage and compute';

-- ============================================================
-- Health checks
-- ============================================================

INSERT INTO health_checks (
    instance_id,
    healthy,
    response_ms
)
SELECT
    instance_id,
    TRUE,
    response_ms
FROM compute_instances
CROSS JOIN (
    VALUES
        (18),
        (21),
        (19)
) AS responses(response_ms)
WHERE instance_name IN ('app-01', 'app-02', 'app-03');

-- ============================================================
-- Views
-- ============================================================

CREATE OR REPLACE VIEW healthy_capacity AS
SELECT
    repository_id,
    COUNT(*) AS healthy_instances,
    SUM(capacity_requests) AS total_capacity,
    SUM(active_requests) AS active_requests,
    ROUND(
        SUM(active_requests)::NUMERIC /
        NULLIF(SUM(capacity_requests), 0),
        4
    ) AS utilization
FROM compute_instances
WHERE state = 'running'
GROUP BY repository_id;

CREATE OR REPLACE VIEW pull_request_review_summary AS
SELECT
    pr.pull_request_id,
    pr.title,
    pr.state,
    COUNT(*) FILTER (
        WHERE rv.review_state = 'approved'
    ) AS approvals,
    COUNT(*) FILTER (
        WHERE rv.review_state = 'changes_requested'
    ) AS change_requests,
    COUNT(*) FILTER (
        WHERE rv.review_state = 'dismissed'
    ) AS dismissed_reviews,
    COUNT(*) FILTER (
        WHERE rv.review_state = 'commented'
    ) AS comments
FROM pull_requests pr
LEFT JOIN reviews rv
    ON rv.pull_request_id = pr.pull_request_id
GROUP BY
    pr.pull_request_id,
    pr.title,
    pr.state;

-- ============================================================
-- Merge eligibility function
-- ============================================================

CREATE OR REPLACE FUNCTION evaluate_merge_eligibility(
    p_pull_request_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_repository_id BIGINT;
    v_target_branch_id BIGINT;
    v_required_approvals INTEGER;
    v_approvals INTEGER;
    v_change_requests INTEGER;
    v_failed_checks INTEGER;
    v_pending_checks INTEGER;
    v_unresolved_conversations INTEGER;
    v_healthy_instances INTEGER;
    v_capacity INTEGER;
    v_backup_count INTEGER;
    v_recent_backup_count INTEGER;
    v_draft BOOLEAN;
    v_pr_state pull_request_state;
BEGIN
    SELECT
        pr.repository_id,
        pr.target_branch_id,
        pr.draft,
        pr.state
    INTO
        v_repository_id,
        v_target_branch_id,
        v_draft,
        v_pr_state
    FROM pull_requests pr
    WHERE pr.pull_request_id = p_pull_request_id;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT FALSE, 'Pull Request does not exist';
        RETURN;
    END IF;

    IF v_pr_state <> 'open' THEN
        RETURN QUERY
        SELECT FALSE, 'Pull Request is not open';
        RETURN;
    END IF;

    IF v_draft THEN
        RETURN QUERY
        SELECT FALSE, 'Draft Pull Request cannot be merged';
        RETURN;
    END IF;

    SELECT required_approvals
    INTO v_required_approvals
    FROM branch_protection_policies
    WHERE branch_id = v_target_branch_id;

    IF v_required_approvals IS NULL THEN
        v_required_approvals := 0;
    END IF;

    SELECT COUNT(*)
    INTO v_approvals
    FROM reviews
    WHERE pull_request_id = p_pull_request_id
      AND review_state = 'approved';

    SELECT COUNT(*)
    INTO v_change_requests
    FROM reviews
    WHERE pull_request_id = p_pull_request_id
      AND review_state = 'changes_requested';

    IF v_approvals < v_required_approvals THEN
        RETURN QUERY
        SELECT FALSE,
            format(
                'Required approvals not met: %s of %s',
                v_approvals,
                v_required_approvals
            );
        RETURN;
    END IF;

    IF v_change_requests > 0 THEN
        RETURN QUERY
        SELECT FALSE, 'At least one active change request exists';
        RETURN;
    END IF;

    SELECT
        COUNT(*) FILTER (WHERE status = 'failed'),
        COUNT(*) FILTER (WHERE status = 'pending')
    INTO
        v_failed_checks,
        v_pending_checks
    FROM status_checks
    WHERE pull_request_id = p_pull_request_id;

    IF v_failed_checks > 0 THEN
        RETURN QUERY
        SELECT FALSE, 'One or more required status checks failed';
        RETURN;
    END IF;

    IF v_pending_checks > 0 THEN
        RETURN QUERY
        SELECT FALSE, 'One or more status checks are pending';
        RETURN;
    END IF;

    SELECT COUNT(*)
    INTO v_unresolved_conversations
    FROM conversations
    WHERE pull_request_id = p_pull_request_id
      AND NOT resolved;

    IF v_unresolved_conversations > 0 THEN
        RETURN QUERY
        SELECT FALSE, 'Unresolved review conversations exist';
        RETURN;
    END IF;

    SELECT
        COUNT(*),
        COALESCE(SUM(capacity_requests), 0)
    INTO
        v_healthy_instances,
        v_capacity
    FROM compute_instances
    WHERE repository_id = v_repository_id
      AND state = 'running';

    IF EXISTS (
        SELECT 1
        FROM deployment_requirements
        WHERE repository_id = v_repository_id
          AND (
              v_healthy_instances < minimum_healthy_instances
              OR v_capacity < minimum_capacity_requests
          )
    ) THEN
        RETURN QUERY
        SELECT FALSE,
            'Healthy compute capacity does not satisfy deployment requirements';
        RETURN;
    END IF;

    SELECT COUNT(*)
    INTO v_backup_count
    FROM backups
    WHERE repository_id = v_repository_id
      AND state = 'available';

    SELECT COUNT(*)
    INTO v_recent_backup_count
    FROM backups b
    JOIN deployment_requirements dr
      ON dr.repository_id = b.repository_id
    WHERE b.repository_id = v_repository_id
      AND b.state = 'available'
      AND b.created_at >= now() - dr.backup_max_age
      AND b.expires_at > now();

    IF EXISTS (
        SELECT 1
        FROM deployment_requirements
        WHERE repository_id = v_repository_id
          AND backup_required
          AND (
              v_backup_count = 0
              OR v_recent_backup_count = 0
          )
    ) THEN
        RETURN QUERY
        SELECT FALSE, 'A current valid backup is required';
        RETURN;
    END IF;

    RETURN QUERY
    SELECT TRUE, 'All merge and deployment requirements are satisfied';
END;
$$;

-- ============================================================
-- Transactional merge workflow
-- ============================================================

BEGIN;

SELECT *
FROM evaluate_merge_eligibility(
    (
        SELECT pull_request_id
        FROM pull_requests
        WHERE title = 'Scale application storage and compute'
    )
);

-- The sample data satisfies the merge policy.
UPDATE pull_requests
SET state = 'merged'
WHERE title = 'Scale application storage and compute'
  AND EXISTS (
      SELECT 1
      FROM evaluate_merge_eligibility(pull_request_id)
      WHERE eligible
  );

COMMIT;

-- ============================================================
-- Reporting and evaluation queries
-- ============================================================

-- 1. Current compute capacity and utilization.
SELECT
    r.name AS repository,
    hc.healthy_instances,
    hc.total_capacity,
    hc.active_requests,
    hc.utilization
FROM repositories r
JOIN healthy_capacity hc
    ON hc.repository_id = r.repository_id;

-- 2. Storage inventory and checksums.
SELECT
    r.name AS repository,
    so.object_key,
    so.object_size_bytes,
    so.checksum_sha256,
    so.state,
    so.version_number
FROM storage_objects so
JOIN repositories r
    ON r.repository_id = so.repository_id
ORDER BY so.object_key;

-- 3. Backup health.
SELECT
    r.name AS repository,
    b.backup_name,
    b.state,
    b.created_at,
    b.expires_at,
    b.expires_at > now() AS currently_valid
FROM backups b
JOIN repositories r
    ON r.repository_id = b.repository_id
ORDER BY b.created_at DESC;

-- 4. Review and approval status.
SELECT
    *
FROM pull_request_review_summary;

-- 5. Status-check evaluation.
SELECT
    pr.pull_request_id,
    pr.title,
    sc.check_name,
    sc.status
FROM pull_requests pr
JOIN status_checks sc
    ON sc.pull_request_id = pr.pull_request_id
ORDER BY pr.pull_request_id, sc.check_name;

-- 6. Latest health state for each instance.
WITH ranked_health AS (
    SELECT
        hc.*,
        ROW_NUMBER() OVER (
            PARTITION BY hc.instance_id
            ORDER BY hc.checked_at DESC
        ) AS row_number
    FROM health_checks hc
)
SELECT
    ci.instance_name,
    rh.healthy,
    rh.response_ms,
    rh.checked_at
FROM ranked_health rh
JOIN compute_instances ci
    ON ci.instance_id = rh.instance_id
WHERE rh.row_number = 1
ORDER BY ci.instance_name;

-- 7. Final merge eligibility report.
SELECT
    pr.pull_request_id,
    pr.title,
    eligibility.eligible,
    eligibility.reason
FROM pull_requests pr
CROSS JOIN LATERAL evaluate_merge_eligibility(
    pr.pull_request_id
) AS eligibility;

-- 8. CTE-based capacity planning.
WITH fleet AS (
    SELECT
        repository_id,
        COUNT(*) FILTER (
            WHERE state = 'running'
        ) AS healthy_instances,
        COALESCE(
            SUM(capacity_requests)
            FILTER (WHERE state = 'running'),
            0
        ) AS healthy_capacity
    FROM compute_instances
    GROUP BY repository_id
)
SELECT
    r.name,
    fleet.healthy_instances,
    fleet.healthy_capacity,
    dr.minimum_healthy_instances,
    dr.minimum_capacity_requests,
    fleet.healthy_instances >= dr.minimum_healthy_instances
        AS instance_requirement_met,
    fleet.healthy_capacity >= dr.minimum_capacity_requests
        AS capacity_requirement_met
FROM repositories r
JOIN fleet
    ON fleet.repository_id = r.repository_id
JOIN deployment_requirements dr
    ON dr.repository_id = r.repository_id;

-- 9. Identify backups that should be expired.
SELECT
    backup_id,
    backup_name,
    expires_at
FROM backups
WHERE expires_at <= now()
  AND state = 'available';

-- 10. Transactionally expire obsolete backups.
BEGIN;

UPDATE backups
SET state = 'expired'
WHERE expires_at <= now()
  AND state = 'available';

COMMIT;
