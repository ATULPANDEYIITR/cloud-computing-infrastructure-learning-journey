DROP SCHEMA IF EXISTS relational_architecture CASCADE;

CREATE SCHEMA relational_architecture;

SET search_path TO relational_architecture, public;

-- Users are stored independently from accounts.
-- This prevents repeated user attributes and demonstrates normalization.
CREATE TABLE app_user (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username TEXT NOT NULL,
    email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT app_user_username_ck CHECK (length(btrim(username)) >= 3),
    CONSTRAINT app_user_email_ck CHECK (position('@' IN email) > 1)
);

CREATE UNIQUE INDEX app_user_username_uq
    ON app_user (lower(username));

CREATE UNIQUE INDEX app_user_email_uq
    ON app_user (lower(email));

CREATE TABLE repository (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES app_user(user_id),
    repository_name TEXT NOT NULL,
    visibility TEXT NOT NULL DEFAULT 'private',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT repository_visibility_ck
        CHECK (visibility IN ('private', 'internal', 'public')),
    CONSTRAINT repository_name_ck
        CHECK (length(btrim(repository_name)) >= 1),
    CONSTRAINT repository_owner_name_uq
        UNIQUE (owner_id, repository_name)
);

CREATE TABLE branch (
    branch_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repository(repository_id)
        ON DELETE CASCADE,
    branch_name TEXT NOT NULL,
    head_commit_hash TEXT,
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT branch_repository_name_uq
        UNIQUE (repository_id, branch_name)
);

CREATE INDEX branch_repository_idx
    ON branch (repository_id);

CREATE TABLE commit_record (
    commit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repository(repository_id)
        ON DELETE CASCADE,
    commit_hash TEXT NOT NULL,
    author_id BIGINT NOT NULL REFERENCES app_user(user_id),
    parent_commit_id BIGINT REFERENCES commit_record(commit_id),
    message TEXT NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT commit_hash_uq UNIQUE (repository_id, commit_hash),
    CONSTRAINT commit_message_ck CHECK (length(btrim(message)) > 0)
);

CREATE INDEX commit_repository_time_idx
    ON commit_record (repository_id, committed_at DESC);

CREATE TABLE pull_request (
    pull_request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repository(repository_id)
        ON DELETE CASCADE,
    source_branch_id BIGINT NOT NULL REFERENCES branch(branch_id),
    target_branch_id BIGINT NOT NULL REFERENCES branch(branch_id),
    author_id BIGINT NOT NULL REFERENCES app_user(user_id),
    title TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'open',
    draft BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMPTZ,
    CONSTRAINT pull_request_state_ck
        CHECK (state IN ('open', 'closed', 'merged')),
    CONSTRAINT pull_request_title_ck
        CHECK (length(btrim(title)) > 0),
    CONSTRAINT pull_request_distinct_branches_ck
        CHECK (source_branch_id <> target_branch_id)
);

CREATE INDEX pull_request_repository_state_idx
    ON pull_request (repository_id, state);

CREATE TABLE pull_request_commit (
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_request(pull_request_id)
        ON DELETE CASCADE,
    commit_id BIGINT NOT NULL
        REFERENCES commit_record(commit_id)
        ON DELETE RESTRICT,
    sequence_no INTEGER NOT NULL,
    PRIMARY KEY (pull_request_id, commit_id),
    CONSTRAINT pull_request_commit_sequence_ck
        CHECK (sequence_no > 0),
    CONSTRAINT pull_request_commit_sequence_uq
        UNIQUE (pull_request_id, sequence_no)
);

CREATE TABLE review (
    review_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_request(pull_request_id)
        ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL REFERENCES app_user(user_id),
    review_state TEXT NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    commit_id BIGINT REFERENCES commit_record(commit_id),
    dismissed BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT review_state_ck
        CHECK (
            review_state IN (
                'approved',
                'changes_requested',
                'commented'
            )
        )
);

CREATE INDEX review_pr_reviewer_idx
    ON review (pull_request_id, reviewer_id, submitted_at DESC);

CREATE TABLE review_comment (
    comment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    review_id BIGINT NOT NULL REFERENCES review(review_id)
        ON DELETE CASCADE,
    author_id BIGINT NOT NULL REFERENCES app_user(user_id),
    file_path TEXT,
    line_number INTEGER,
    body TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT review_comment_body_ck CHECK (length(btrim(body)) > 0),
    CONSTRAINT review_comment_line_ck
        CHECK (line_number IS NULL OR line_number > 0)
);

CREATE INDEX review_comment_unresolved_idx
    ON review_comment (review_id)
    WHERE resolved = FALSE;

CREATE TABLE conversation (
    conversation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_request(pull_request_id)
        ON DELETE CASCADE,
    opened_by BIGINT NOT NULL REFERENCES app_user(user_id),
    subject TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ,
    CONSTRAINT conversation_subject_ck
        CHECK (length(btrim(subject)) > 0)
);

CREATE INDEX conversation_pr_state_idx
    ON conversation (pull_request_id, resolved);

CREATE TABLE status_check (
    status_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_request(pull_request_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    status TEXT NOT NULL,
    completed_at TIMESTAMPTZ,
    CONSTRAINT status_check_status_ck
        CHECK (status IN ('pending', 'passed', 'failed')),
    CONSTRAINT status_check_name_uq
        UNIQUE (pull_request_id, check_name)
);

CREATE INDEX status_check_pr_status_idx
    ON status_check (pull_request_id, status);

CREATE TABLE branch_protection_policy (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    branch_id BIGINT NOT NULL UNIQUE
        REFERENCES branch(branch_id)
        ON DELETE CASCADE,
    required_approvals INTEGER NOT NULL DEFAULT 0,
    require_passing_checks BOOLEAN NOT NULL DEFAULT TRUE,
    require_resolved_conversations BOOLEAN NOT NULL DEFAULT TRUE,
    allow_direct_push BOOLEAN NOT NULL DEFAULT FALSE,
    allow_force_push BOOLEAN NOT NULL DEFAULT FALSE,
    allow_branch_deletion BOOLEAN NOT NULL DEFAULT FALSE,
    require_linear_history BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT required_approvals_ck
        CHECK (required_approvals >= 0)
);

CREATE TABLE approval_requirement (
    requirement_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    policy_id BIGINT NOT NULL
        REFERENCES branch_protection_policy(policy_id)
        ON DELETE CASCADE,
    role_name TEXT NOT NULL,
    minimum_count INTEGER NOT NULL,
    CONSTRAINT approval_requirement_count_ck
        CHECK (minimum_count > 0),
    CONSTRAINT approval_requirement_role_uq
        UNIQUE (policy_id, role_name)
);

CREATE TABLE merge_record (
    merge_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pull_request_id BIGINT NOT NULL UNIQUE
        REFERENCES pull_request(pull_request_id)
        ON DELETE RESTRICT,
    merged_by BIGINT NOT NULL REFERENCES app_user(user_id),
    merge_strategy TEXT NOT NULL,
    merge_commit_hash TEXT NOT NULL,
    merged_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT merge_strategy_ck
        CHECK (
            merge_strategy IN (
                'merge_commit',
                'squash',
                'rebase'
            )
        ),
    CONSTRAINT merge_hash_uq UNIQUE (merge_commit_hash)
);

CREATE TABLE audit_event (
    audit_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    event_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE FUNCTION enforce_protected_branch_direct_push()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    protected_branch BOOLEAN;
    direct_push_allowed BOOLEAN;
BEGIN
    SELECT b.protected, COALESCE(bp.allow_direct_push, FALSE)
    INTO protected_branch, direct_push_allowed
    FROM branch b
    LEFT JOIN branch_protection_policy bp
        ON bp.branch_id = b.branch_id
    WHERE b.branch_id = NEW.target_branch_id;

    IF protected_branch AND NOT direct_push_allowed THEN
        IF NEW.source_branch_id = NEW.target_branch_id THEN
            RAISE EXCEPTION
                'Direct updates to protected branches are prohibited';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER pull_request_protected_branch_guard
BEFORE INSERT OR UPDATE ON pull_request
FOR EACH ROW
EXECUTE FUNCTION enforce_protected_branch_direct_push();

CREATE OR REPLACE FUNCTION validate_merge_state()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    pr_state TEXT;
    target_branch BIGINT;
BEGIN
    SELECT state, target_branch_id
    INTO pr_state, target_branch
    FROM pull_request
    WHERE pull_request_id = NEW.pull_request_id;

    IF pr_state <> 'open' THEN
        RAISE EXCEPTION
            'Only open pull requests can be merged';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM branch_protection_policy bp
        JOIN status_check sc
          ON sc.pull_request_id = NEW.pull_request_id
        WHERE bp.branch_id = target_branch
          AND bp.require_passing_checks
          AND sc.status <> 'passed'
    ) THEN
        RAISE EXCEPTION
            'Required status checks have not passed';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER merge_state_guard
BEFORE INSERT ON merge_record
FOR EACH ROW
EXECUTE FUNCTION validate_merge_state();

CREATE OR REPLACE VIEW merge_eligibility AS
WITH approval_counts AS (
    SELECT
        r.pull_request_id,
        COUNT(*) FILTER (
            WHERE r.review_state = 'approved'
              AND NOT r.dismissed
        ) AS approvals
    FROM review r
    GROUP BY r.pull_request_id
),
check_state AS (
    SELECT
        sc.pull_request_id,
        BOOL_AND(sc.status = 'passed') AS all_checks_passed
    FROM status_check sc
    GROUP BY sc.pull_request_id
),
conversation_state AS (
    SELECT
        c.pull_request_id,
        COUNT(*) FILTER (WHERE NOT c.resolved) AS unresolved_count
    FROM conversation c
    GROUP BY c.pull_request_id
)
SELECT
    pr.pull_request_id,
    pr.title,
    pr.state,
    b.branch_name AS target_branch,
    COALESCE(ac.approvals, 0) AS approvals,
    COALESCE(bp.required_approvals, 0) AS required_approvals,
    COALESCE(cs.all_checks_passed, TRUE) AS checks_passed,
    COALESCE(cvs.unresolved_count, 0) AS unresolved_conversations,
    (
        pr.state = 'open'
        AND COALESCE(ac.approvals, 0) >= COALESCE(bp.required_approvals, 0)
        AND (
            NOT COALESCE(bp.require_passing_checks, FALSE)
            OR COALESCE(cs.all_checks_passed, TRUE)
        )
        AND (
            NOT COALESCE(bp.require_resolved_conversations, FALSE)
            OR COALESCE(cvs.unresolved_count, 0) = 0
        )
    ) AS merge_eligible
FROM pull_request pr
JOIN branch b
    ON b.branch_id = pr.target_branch_id
LEFT JOIN branch_protection_policy bp
    ON bp.branch_id = pr.target_branch_id
LEFT JOIN approval_counts ac
    ON ac.pull_request_id = pr.pull_request_id
LEFT JOIN check_state cs
    ON cs.pull_request_id = pr.pull_request_id
LEFT JOIN conversation_state cvs
    ON cvs.pull_request_id = pr.pull_request_id;

INSERT INTO app_user (username, email)
VALUES
    ('alice', 'alice@example.org'),
    ('bob', 'bob@example.org'),
    ('carol', 'carol@example.org'),
    ('dave', 'dave@example.org');

INSERT INTO repository (owner_id, repository_name, visibility)
VALUES
    (1, 'payment-platform', 'private');

INSERT INTO branch (
    repository_id,
    branch_name,
    head_commit_hash,
    protected
)
VALUES
    (1, 'main', 'c001', TRUE),
    (1, 'feature/indexes', 'c003', FALSE);

INSERT INTO commit_record (
    repository_id,
    commit_hash,
    author_id,
    message
)
VALUES
    (1, 'c001', 1, 'Initial database schema'),
    (1, 'c002', 1, 'Add normalized account tables'),
    (1, 'c003', 2, 'Add indexes and transaction workflow');

INSERT INTO pull_request (
    repository_id,
    source_branch_id,
    target_branch_id,
    author_id,
    title,
    state,
    draft
)
VALUES (
    1,
    2,
    1,
    2,
    'Improve relational database architecture',
    'open',
    FALSE
);

INSERT INTO pull_request_commit (
    pull_request_id,
    commit_id,
    sequence_no
)
VALUES
    (1, 2, 1),
    (1, 3, 2);

INSERT INTO review (
    pull_request_id,
    reviewer_id,
    review_state,
    commit_id
)
VALUES
    (1, 1, 'approved', 3),
    (1, 3, 'approved', 3);

INSERT INTO review_comment (
    review_id,
    author_id,
    file_path,
    line_number,
    body,
    resolved
)
VALUES
    (1, 1, 'schema.sql', 42, 'Constraint is appropriate.', TRUE),
    (2, 3, 'schema.sql', 81, 'Index supports the reporting query.', TRUE);

INSERT INTO conversation (
    pull_request_id,
    opened_by,
    subject,
    resolved,
    resolved_at
)
VALUES
    (1, 1, 'Confirm transaction isolation requirement', TRUE, CURRENT_TIMESTAMP);

INSERT INTO status_check (
    pull_request_id,
    check_name,
    status,
    completed_at
)
VALUES
    (1, 'unit-tests', 'passed', CURRENT_TIMESTAMP),
    (1, 'integration-tests', 'passed', CURRENT_TIMESTAMP),
    (1, 'schema-validation', 'passed', CURRENT_TIMESTAMP);

INSERT INTO branch_protection_policy (
    branch_id,
    required_approvals,
    require_passing_checks,
    require_resolved_conversations,
    allow_direct_push,
    allow_force_push,
    allow_branch_deletion,
    require_linear_history
)
VALUES (
    1,
    2,
    TRUE,
    TRUE,
    FALSE,
    FALSE,
    FALSE,
    TRUE
);

INSERT INTO approval_requirement (
    policy_id,
    role_name,
    minimum_count
)
VALUES
    (1, 'maintainer', 1),
    (1, 'database-reviewer', 1);

-- Retrieval.
SELECT
    r.repository_name,
    b.branch_name,
    b.protected
FROM repository r
JOIN branch b
    ON b.repository_id = r.repository_id
ORDER BY r.repository_name, b.branch_name;

-- Review and approval evaluation.
SELECT
    pr.pull_request_id,
    pr.title,
    u.username AS author,
    COUNT(rv.review_id) AS total_reviews,
    COUNT(*) FILTER (
        WHERE rv.review_state = 'approved'
          AND NOT rv.dismissed
    ) AS active_approvals
FROM pull_request pr
JOIN app_user u
    ON u.user_id = pr.author_id
LEFT JOIN review rv
    ON rv.pull_request_id = pr.pull_request_id
GROUP BY pr.pull_request_id, pr.title, u.username;

-- Status-check reporting.
SELECT
    pull_request_id,
    COUNT(*) AS checks,
    COUNT(*) FILTER (WHERE status = 'passed') AS passed,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending
FROM status_check
GROUP BY pull_request_id;

-- Unresolved review conversations.
SELECT
    pr.pull_request_id,
    pr.title,
    COUNT(c.conversation_id) AS unresolved_conversations
FROM pull_request pr
LEFT JOIN conversation c
    ON c.pull_request_id = pr.pull_request_id
   AND NOT c.resolved
GROUP BY pr.pull_request_id, pr.title;

-- Final merge-eligibility decision.
SELECT *
FROM merge_eligibility
ORDER BY pull_request_id;

-- Demonstrate transactional integrity.
BEGIN;

UPDATE branch
SET head_commit_hash = 'c003'
WHERE branch_id = 2;

INSERT INTO audit_event (
    entity_type,
    entity_id,
    event_type,
    event_details
)
VALUES (
    'branch',
    2,
    'head_update',
    '{"reason":"transactional branch update"}'::jsonb
);

COMMIT;

-- ACID-oriented consistency check:
-- every account-related entity in this example is protected by
-- primary keys, foreign keys, CHECK constraints, and transactional writes.

CREATE TABLE account (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES app_user(user_id),
    balance_cents BIGINT NOT NULL DEFAULT 0,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT account_balance_ck CHECK (balance_cents >= 0),
    CONSTRAINT account_version_ck CHECK (version >= 0)
);

CREATE INDEX account_owner_idx
    ON account (owner_id);

INSERT INTO account (owner_id, balance_cents)
VALUES
    (1, 10000),
    (2, 2500);

-- Atomic transfer demonstrating row-level locking.
BEGIN;

SELECT account_id, balance_cents
FROM account
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE;

UPDATE account
SET balance_cents = balance_cents - 3000,
    version = version + 1
WHERE account_id = 1
  AND balance_cents >= 3000;

UPDATE account
SET balance_cents = balance_cents + 3000,
    version = version + 1
WHERE account_id = 2;

INSERT INTO audit_event (
    entity_type,
    entity_id,
    event_type,
    event_details
)
VALUES (
    'account',
    1,
    'transfer',
    '{"destination_account":2,"amount_cents":3000}'::jsonb
);

COMMIT;

-- Aggregate validation of the accounting invariant.
SELECT
    COUNT(*) AS accounts,
    SUM(balance_cents) AS total_balance_cents,
    MIN(balance_cents) AS minimum_balance_cents
FROM account;

-- Normalization relationship:
-- app_user stores user attributes once.
-- repository references app_user.
-- branch references repository.
-- pull_request references branches and users.
-- reviews reference pull requests and reviewers.
-- branch protection references branches.
-- This reduces update, insertion, and deletion anomalies.
SELECT
    u.username,
    r.repository_name,
    b.branch_name,
    b.protected
FROM app_user u
JOIN repository r
    ON r.owner_id = u.user_id
JOIN branch b
    ON b.repository_id = r.repository_id
ORDER BY u.username, r.repository_name, b.branch_name;
