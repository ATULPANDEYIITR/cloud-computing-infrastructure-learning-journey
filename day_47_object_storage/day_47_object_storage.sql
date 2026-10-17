-- PostgreSQL 15+
-- Object storage governance model covering buckets, objects, metadata,
-- version history, lifecycle policies, access statements, and audit events.
--
-- Run against a disposable development database. The script recreates its
-- dedicated schema so that it can be executed repeatedly.

BEGIN;

DROP SCHEMA IF EXISTS object_storage_lab CASCADE;
CREATE SCHEMA object_storage_lab;
SET search_path TO object_storage_lab, public;

CREATE TYPE versioning_state AS ENUM ('DISABLED', 'ENABLED', 'SUSPENDED');
CREATE TYPE storage_class AS ENUM ('STANDARD', 'INFREQUENT_ACCESS', 'ARCHIVE');
CREATE TYPE policy_effect AS ENUM ('ALLOW', 'DENY');
CREATE TYPE audit_outcome AS ENUM ('ALLOWED', 'DENIED', 'FAILED');
CREATE TYPE lifecycle_action AS ENUM (
    'TRANSITION',
    'EXPIRE_CURRENT',
    'EXPIRE_NONCURRENT',
    'ABORT_INCOMPLETE_UPLOAD'
);

CREATE TABLE principals (
    principal_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    principal_name TEXT NOT NULL UNIQUE,
    authenticated BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (length(trim(principal_name)) > 0)
);

CREATE TABLE principal_roles (
    principal_id BIGINT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
    role_name TEXT NOT NULL,
    PRIMARY KEY (principal_id, role_name),
    CHECK (length(trim(role_name)) > 0)
);

CREATE TABLE buckets (
    bucket_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bucket_name TEXT NOT NULL UNIQUE,
    owner_principal_id BIGINT NOT NULL REFERENCES principals(principal_id),
    versioning versioning_state NOT NULL DEFAULT 'DISABLED',
    default_encryption TEXT NOT NULL DEFAULT 'AES256',
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (
        bucket_name ~ '^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$'
        AND bucket_name NOT LIKE '%..%'
        AND bucket_name NOT LIKE '%.-%'
        AND bucket_name NOT LIKE '%-.%'
    ),
    CHECK (length(default_encryption) > 0)
);

CREATE TABLE objects (
    object_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bucket_id BIGINT NOT NULL REFERENCES buckets(bucket_id) ON DELETE CASCADE,
    object_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (bucket_id, object_key),
    CHECK (length(object_key) > 0),
    CHECK (left(object_key, 1) <> '/'),
    CHECK (position(chr(0) IN object_key) = 0)
);

CREATE TABLE object_versions (
    object_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    object_id BIGINT NOT NULL REFERENCES objects(object_id) ON DELETE CASCADE,
    version_id TEXT NOT NULL,
    payload BYTEA NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    content_length BIGINT NOT NULL,
    etag TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    storage_class storage_class NOT NULL DEFAULT 'STANDARD',
    is_delete_marker BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    noncurrent_since TIMESTAMPTZ,
    retention_until TIMESTAMPTZ,
    UNIQUE (object_id, version_id),
    CHECK (content_length >= 0),
    CHECK (content_length = octet_length(payload)),
    CHECK (length(content_type) > 0),
    CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (NOT is_delete_marker OR content_length = 0),
    CHECK (retention_until IS NULL OR retention_until >= created_at)
);

CREATE TABLE object_metadata (
    object_version_id BIGINT NOT NULL REFERENCES object_versions(object_version_id) ON DELETE CASCADE,
    metadata_key TEXT NOT NULL,
    metadata_value TEXT NOT NULL,
    PRIMARY KEY (object_version_id, metadata_key),
    CHECK (metadata_key ~ '^[a-z0-9-]{1,64}$'),
    CHECK (octet_length(metadata_value) <= 2048)
);

CREATE TABLE bucket_policy_statements (
    statement_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bucket_id BIGINT NOT NULL REFERENCES buckets(bucket_id) ON DELETE CASCADE,
    statement_name TEXT NOT NULL,
    effect policy_effect NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (bucket_id, statement_name),
    CHECK (length(trim(statement_name)) > 0)
);

CREATE TABLE policy_actions (
    statement_id BIGINT NOT NULL REFERENCES bucket_policy_statements(statement_id) ON DELETE CASCADE,
    action_name TEXT NOT NULL,
    PRIMARY KEY (statement_id, action_name),
    CHECK (action_name IN (
        'bucket:ListObjects',
        'bucket:GetPolicy',
        'bucket:PutPolicy',
        'object:Get',
        'object:GetVersion',
        'object:Put',
        'object:Delete',
        'object:DeleteVersion',
        'object:ListVersions',
        'object:Restore',
        'object:ManageLifecycle'
    ))
);

CREATE TABLE policy_principals (
    statement_id BIGINT NOT NULL REFERENCES bucket_policy_statements(statement_id) ON DELETE CASCADE,
    principal_pattern TEXT NOT NULL,
    PRIMARY KEY (statement_id, principal_pattern),
    CHECK (length(principal_pattern) > 0)
);

CREATE TABLE policy_resources (
    statement_id BIGINT NOT NULL REFERENCES bucket_policy_statements(statement_id) ON DELETE CASCADE,
    resource_pattern TEXT NOT NULL,
    PRIMARY KEY (statement_id, resource_pattern),
    CHECK (length(resource_pattern) > 0)
);

CREATE TABLE policy_conditions (
    statement_id BIGINT NOT NULL REFERENCES bucket_policy_statements(statement_id) ON DELETE CASCADE,
    condition_key TEXT NOT NULL,
    expected_value TEXT NOT NULL,
    PRIMARY KEY (statement_id, condition_key)
);

CREATE TABLE lifecycle_rules (
    lifecycle_rule_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bucket_id BIGINT NOT NULL REFERENCES buckets(bucket_id) ON DELETE CASCADE,
    rule_name TEXT NOT NULL,
    object_prefix TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    transition_after_days INTEGER,
    target_storage_class storage_class,
    expire_current_after_days INTEGER,
    expire_noncurrent_after_days INTEGER,
    abort_upload_after_days INTEGER,
    UNIQUE (bucket_id, rule_name),
    CHECK (
        transition_after_days IS NOT NULL
        OR expire_current_after_days IS NOT NULL
        OR expire_noncurrent_after_days IS NOT NULL
        OR abort_upload_after_days IS NOT NULL
    ),
    CHECK (transition_after_days IS NULL OR transition_after_days >= 0),
    CHECK (expire_current_after_days IS NULL OR expire_current_after_days >= 0),
    CHECK (expire_noncurrent_after_days IS NULL OR expire_noncurrent_after_days >= 0),
    CHECK (abort_upload_after_days IS NULL OR abort_upload_after_days >= 0),
    CHECK (
        transition_after_days IS NULL
        OR target_storage_class IS NOT NULL
    )
);

CREATE TABLE incomplete_uploads (
    upload_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bucket_id BIGINT NOT NULL REFERENCES buckets(bucket_id) ON DELETE CASCADE,
    object_key TEXT NOT NULL,
    initiated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (length(object_key) > 0)
);

CREATE TABLE storage_audit_events (
    audit_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    principal_id BIGINT REFERENCES principals(principal_id) ON DELETE SET NULL,
    bucket_id BIGINT REFERENCES buckets(bucket_id) ON DELETE SET NULL,
    object_key TEXT,
    action_name TEXT NOT NULL,
    outcome audit_outcome NOT NULL,
    event_detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX object_versions_history_idx
    ON object_versions (object_id, created_at DESC, object_version_id DESC);

CREATE INDEX object_versions_noncurrent_cleanup_idx
    ON object_versions (noncurrent_since)
    WHERE noncurrent_since IS NOT NULL AND is_delete_marker = FALSE;

CREATE INDEX object_key_prefix_idx
    ON objects (bucket_id, object_key text_pattern_ops);

CREATE INDEX lifecycle_due_rules_idx
    ON lifecycle_rules (bucket_id, enabled, object_prefix);

CREATE INDEX storage_audit_recent_idx
    ON storage_audit_events (bucket_id, occurred_at DESC);

CREATE INDEX storage_audit_denied_idx
    ON storage_audit_events (occurred_at DESC)
    WHERE outcome = 'DENIED';

-- A partial unique index makes a single non-marker current version explicit.
-- A delete marker can be the logical current entry without being a payload.
CREATE UNIQUE INDEX one_current_payload_per_object
    ON object_versions (object_id)
    WHERE noncurrent_since IS NULL AND is_delete_marker = FALSE;

CREATE OR REPLACE FUNCTION validate_object_key()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.object_key ~ '(^/|(^|/)\.\.(/|$))' THEN
        RAISE EXCEPTION 'Object keys cannot be absolute or contain parent segments';
    END IF;

    IF octet_length(NEW.object_key) > 1024 THEN
        RAISE EXCEPTION 'Object key exceeds 1024 bytes';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER objects_validate_key
BEFORE INSERT OR UPDATE OF object_key ON objects
FOR EACH ROW EXECUTE FUNCTION validate_object_key();

CREATE OR REPLACE FUNCTION validate_object_version()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.content_length <> octet_length(NEW.payload) THEN
        RAISE EXCEPTION 'content_length must equal payload byte length';
    END IF;

    IF NEW.retention_until IS NOT NULL
       AND NEW.retention_until < NEW.created_at THEN
        RAISE EXCEPTION 'retention_until cannot precede created_at';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER object_versions_validate_payload
BEFORE INSERT OR UPDATE OF payload, content_length, retention_until, created_at
ON object_versions
FOR EACH ROW EXECUTE FUNCTION validate_object_version();

-- PostgreSQL pgcrypto is not required by this schema. The application supplies
-- SHA-256 values, and a production deployment should verify them using pgcrypto
-- or a trusted application service before committing a payload.

CREATE OR REPLACE FUNCTION evaluate_access(
    p_principal_id BIGINT,
    p_bucket_id BIGINT,
    p_action TEXT,
    p_object_key TEXT,
    p_context JSONB DEFAULT '{}'::jsonb
)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_owner_id BIGINT;
    v_principal_name TEXT;
    v_authenticated BOOLEAN;
    v_resource TEXT;
    v_has_allow BOOLEAN;
    v_has_deny BOOLEAN;
BEGIN
    SELECT owner_principal_id INTO v_owner_id
    FROM buckets
    WHERE bucket_id = p_bucket_id;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    SELECT principal_name, authenticated
    INTO v_principal_name, v_authenticated
    FROM principals
    WHERE principal_id = p_principal_id;

    IF NOT FOUND OR NOT v_authenticated THEN
        RETURN FALSE;
    END IF;

    IF p_principal_id = v_owner_id THEN
        RETURN TRUE;
    END IF;

    v_resource := 'arn:object:' ||
        (SELECT bucket_name FROM buckets WHERE bucket_id = p_bucket_id);

    IF p_object_key IS NOT NULL THEN
        v_resource := v_resource || '/' || p_object_key;
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM bucket_policy_statements s
        JOIN policy_actions a ON a.statement_id = s.statement_id
        JOIN policy_principals p ON p.statement_id = s.statement_id
        JOIN policy_resources r ON r.statement_id = s.statement_id
        WHERE s.bucket_id = p_bucket_id
          AND s.enabled
          AND s.effect = 'DENY'
          AND a.action_name IN (p_action, '*')
          AND (
              p.principal_pattern = '*'
              OR p.principal_pattern = v_principal_name
              OR EXISTS (
                  SELECT 1
                  FROM principal_roles pr
                  WHERE pr.principal_id = p_principal_id
                    AND pr.role_name = p.principal_pattern
              )
          )
          AND (
              r.resource_pattern = '*'
              OR (
                  right(r.resource_pattern, 1) = '*'
                  AND left(v_resource, length(r.resource_pattern) - 1)
                      = left(r.resource_pattern, length(r.resource_pattern) - 1)
              )
              OR r.resource_pattern = v_resource
          )
          AND NOT EXISTS (
              SELECT 1
              FROM policy_conditions c
              WHERE c.statement_id = s.statement_id
                AND p_context ->> c.condition_key IS DISTINCT FROM c.expected_value
          )
    ) INTO v_has_deny;

    IF v_has_deny THEN
        RETURN FALSE;
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM bucket_policy_statements s
        JOIN policy_actions a ON a.statement_id = s.statement_id
        JOIN policy_principals p ON p.statement_id = s.statement_id
        JOIN policy_resources r ON r.statement_id = s.statement_id
        WHERE s.bucket_id = p_bucket_id
          AND s.enabled
          AND s.effect = 'ALLOW'
          AND a.action_name IN (p_action, '*')
          AND (
              p.principal_pattern = '*'
              OR p.principal_pattern = v_principal_name
              OR EXISTS (
                  SELECT 1
                  FROM principal_roles pr
                  WHERE pr.principal_id = p_principal_id
                    AND pr.role_name = p.principal_pattern
              )
          )
          AND (
              r.resource_pattern = '*'
              OR (
                  right(r.resource_pattern, 1) = '*'
                  AND left(v_resource, length(r.resource_pattern) - 1)
                      = left(r.resource_pattern, length(r.resource_pattern) - 1)
              )
              OR r.resource_pattern = v_resource
          )
          AND NOT EXISTS (
              SELECT 1
              FROM policy_conditions c
              WHERE c.statement_id = s.statement_id
                AND p_context ->> c.condition_key IS DISTINCT FROM c.expected_value
          )
    ) INTO v_has_allow;

    RETURN v_has_allow;
END;
$$;

CREATE OR REPLACE FUNCTION current_object_inventory()
RETURNS TABLE (
    bucket_name TEXT,
    object_key TEXT,
    version_id TEXT,
    content_length BIGINT,
    storage_class storage_class,
    last_modified TIMESTAMPTZ
)
LANGUAGE sql
STABLE
AS $$
    SELECT b.bucket_name,
           o.object_key,
           v.version_id,
           v.content_length,
           v.storage_class,
           v.created_at
    FROM objects o
    JOIN buckets b ON b.bucket_id = o.bucket_id
    JOIN LATERAL (
        SELECT ov.*
        FROM object_versions ov
        WHERE ov.object_id = o.object_id
        ORDER BY ov.created_at DESC, ov.object_version_id DESC
        LIMIT 1
    ) v ON TRUE
    WHERE NOT v.is_delete_marker;
$$;

-- Demo principals and roles.
INSERT INTO principals (principal_name) VALUES
    ('storage-owner'),
    ('report-writer'),
    ('compliance-auditor'),
    ('anonymous-client');

INSERT INTO principals (principal_name, authenticated)
VALUES ('unauthenticated-session', FALSE);

INSERT INTO principal_roles (principal_id, role_name)
SELECT principal_id, 'storage-admin'
FROM principals WHERE principal_name = 'storage-owner';

INSERT INTO principal_roles (principal_id, role_name)
SELECT principal_id, 'report-writer'
FROM principals WHERE principal_name = 'report-writer';

INSERT INTO principal_roles (principal_id, role_name)
SELECT principal_id, 'audit'
FROM principals WHERE principal_name = 'compliance-auditor';

INSERT INTO buckets (bucket_name, owner_principal_id, versioning)
SELECT 'enterprise-records-prod', principal_id, 'ENABLED'
FROM principals WHERE principal_name = 'storage-owner';

INSERT INTO objects (bucket_id, object_key)
SELECT bucket_id, 'reports/monthly.json'
FROM buckets WHERE bucket_name = 'enterprise-records-prod';

INSERT INTO objects (bucket_id, object_key)
SELECT bucket_id, 'reports/archive/2026-08.csv'
FROM buckets WHERE bucket_name = 'enterprise-records-prod';

INSERT INTO objects (bucket_id, object_key)
SELECT bucket_id, 'legal/retention-register.csv'
FROM buckets WHERE bucket_name = 'enterprise-records-prod';

INSERT INTO object_versions (
    object_id, version_id, payload, content_type, content_length,
    etag, sha256, storage_class, created_at
)
SELECT o.object_id, 'v-2026-09-01',
       convert_to('{"month":"2026-09","incidents":18}', 'UTF8'),
       'application/json',
       octet_length(convert_to('{"month":"2026-09","incidents":18}', 'UTF8')),
       'etag-001',
       repeat('a', 64),
       'STANDARD',
       clock_timestamp() - interval '10 days'
FROM objects o
JOIN buckets b ON b.bucket_id = o.bucket_id
WHERE b.bucket_name = 'enterprise-records-prod'
  AND o.object_key = 'reports/monthly.json';

UPDATE object_versions
SET noncurrent_since = clock_timestamp() - interval '2 days'
WHERE version_id = 'v-2026-09-01';

INSERT INTO object_versions (
    object_id, version_id, payload, content_type, content_length,
    etag, sha256, storage_class
)
SELECT o.object_id, 'v-2026-09-02',
       convert_to('{"month":"2026-09","incidents":16}', 'UTF8'),
       'application/json',
       octet_length(convert_to('{"month":"2026-09","incidents":16}', 'UTF8')),
       'etag-002',
       repeat('b', 64),
       'STANDARD'
FROM objects o
JOIN buckets b ON b.bucket_id = o.bucket_id
WHERE b.bucket_name = 'enterprise-records-prod'
  AND o.object_key = 'reports/monthly.json';

INSERT INTO object_metadata (object_version_id, metadata_key, metadata_value)
SELECT object_version_id, 'department', 'operations'
FROM object_versions WHERE version_id = 'v-2026-09-02';

INSERT INTO object_metadata (object_version_id, metadata_key, metadata_value)
SELECT object_version_id, 'classification', 'internal'
FROM object_versions WHERE version_id = 'v-2026-09-02';

INSERT INTO object_versions (
    object_id, version_id, payload, content_type, content_length,
    etag, sha256, storage_class, created_at
)
SELECT o.object_id, 'archive-v1',
       convert_to('account,total' || E'\n' || 'A104,15300', 'UTF8'),
       'text/csv',
       octet_length(convert_to('account,total' || E'\n' || 'A104,15300', 'UTF8')),
       'archive-etag',
       repeat('c', 64),
       'STANDARD',
       clock_timestamp() - interval '45 days'
FROM objects o
JOIN buckets b ON b.bucket_id = o.bucket_id
WHERE b.bucket_name = 'enterprise-records-prod'
  AND o.object_key = 'reports/archive/2026-08.csv';

INSERT INTO object_versions (
    object_id, version_id, payload, content_type, content_length,
    etag, sha256, storage_class
)
SELECT o.object_id, 'legal-v1',
       convert_to('retention=7-years', 'UTF8'),
       'text/plain',
       octet_length(convert_to('retention=7-years', 'UTF8')),
       'legal-etag',
       repeat('d', 64),
       'STANDARD'
FROM objects o
JOIN buckets b ON b.bucket_id = o.bucket_id
WHERE b.bucket_name = 'enterprise-records-prod'
  AND o.object_key = 'legal/retention-register.csv';

INSERT INTO bucket_policy_statements (bucket_id, statement_name, effect)
SELECT bucket_id, 'auditor-read-reports', 'ALLOW'
FROM buckets WHERE bucket_name = 'enterprise-records-prod';

INSERT INTO policy_actions (statement_id, action_name)
SELECT statement_id, action_name
FROM bucket_policy_statements
CROSS JOIN (VALUES ('object:Get'), ('object:GetVersion')) AS actions(action_name)
WHERE statement_name = 'auditor-read-reports';

INSERT INTO policy_principals (statement_id, principal_pattern)
SELECT statement_id, 'audit'
FROM bucket_policy_statements WHERE statement_name = 'auditor-read-reports';

INSERT INTO policy_resources (statement_id, resource_pattern)
SELECT statement_id, 'arn:object:enterprise-records-prod/reports/*'
FROM bucket_policy_statements WHERE statement_name = 'auditor-read-reports';

INSERT INTO bucket_policy_statements (bucket_id, statement_name, effect)
SELECT bucket_id, 'writer-tls-reports', 'ALLOW'
FROM buckets WHERE bucket_name = 'enterprise-records-prod';

INSERT INTO policy_actions (statement_id, action_name)
SELECT statement_id, action_name
FROM bucket_policy_statements
CROSS JOIN (
    VALUES ('object:Get'), ('object:Put'), ('object:Delete')
) AS actions(action_name)
WHERE statement_name = 'writer-tls-reports';

INSERT INTO policy_principals (statement_id, principal_pattern)
SELECT statement_id, 'report-writer'
FROM bucket_policy_statements WHERE statement_name = 'writer-tls-reports';

INSERT INTO policy_resources (statement_id, resource_pattern)
SELECT statement_id, 'arn:object:enterprise-records-prod/reports/*'
FROM bucket_policy_statements WHERE statement_name = 'writer-tls-reports';

INSERT INTO policy_conditions (statement_id, condition_key, expected_value)
SELECT statement_id, 'transport', 'tls'
FROM bucket_policy_statements WHERE statement_name = 'writer-tls-reports';

INSERT INTO bucket_policy_statements (bucket_id, statement_name, effect)
SELECT bucket_id, 'deny-legal-deletion', 'DENY'
FROM buckets WHERE bucket_name = 'enterprise-records-prod';

INSERT INTO policy_actions (statement_id, action_name)
SELECT statement_id, action_name
FROM bucket_policy_statements
CROSS JOIN (
    VALUES ('object:Delete'), ('object:DeleteVersion')
) AS actions(action_name)
WHERE statement_name = 'deny-legal-deletion';

INSERT INTO policy_principals (statement_id, principal_pattern)
SELECT statement_id, '*'
FROM bucket_policy_statements WHERE statement_name = 'deny-legal-deletion';

INSERT INTO policy_resources (statement_id, resource_pattern)
SELECT statement_id, 'arn:object:enterprise-records-prod/legal/*'
FROM bucket_policy_statements WHERE statement_name = 'deny-legal-deletion';

INSERT INTO lifecycle_rules (
    bucket_id, rule_name, object_prefix, transition_after_days,
    target_storage_class, expire_noncurrent_after_days
)
SELECT bucket_id, 'archive-old-reports', 'reports/archive/', 30,
       'ARCHIVE', 180
FROM buckets WHERE bucket_name = 'enterprise-records-prod';

INSERT INTO lifecycle_rules (
    bucket_id, rule_name, object_prefix, expire_current_after_days,
    abort_upload_after_days
)
SELECT bucket_id, 'temporary-cleanup', 'tmp/', 7, 2
FROM buckets WHERE bucket_name = 'enterprise-records-prod';

-- Record policy decisions in audit data instead of treating a query result
-- as proof that a cloud provider has accepted a real API operation.
INSERT INTO storage_audit_events (
    principal_id, bucket_id, object_key, action_name, outcome, event_detail
)
SELECT p.principal_id, b.bucket_id, 'reports/monthly.json',
       'object:GetVersion', 'ALLOWED',
       jsonb_build_object('reason', 'auditor role and reports prefix matched')
FROM principals p CROSS JOIN buckets b
WHERE p.principal_name = 'compliance-auditor'
  AND b.bucket_name = 'enterprise-records-prod'
  AND evaluate_access(
      p.principal_id, b.bucket_id, 'object:GetVersion',
      'reports/monthly.json', '{}'::jsonb
  );

INSERT INTO storage_audit_events (
    principal_id, bucket_id, object_key, action_name, outcome, event_detail
)
SELECT p.principal_id, b.bucket_id, 'legal/retention-register.csv',
       'object:Delete', 'DENIED',
       jsonb_build_object('reason', 'explicit deny on legal prefix')
FROM principals p CROSS JOIN buckets b
WHERE p.principal_name = 'report-writer'
  AND b.bucket_name = 'enterprise-records-prod'
  AND NOT evaluate_access(
      p.principal_id, b.bucket_id, 'object:Delete',
      'legal/retention-register.csv', '{"transport":"tls"}'::jsonb
  );

-- Inspect all versions, including noncurrent records.
SELECT b.bucket_name, o.object_key, v.version_id, v.storage_class,
       v.content_length, v.created_at, v.noncurrent_since, v.is_delete_marker
FROM object_versions v
JOIN objects o ON o.object_id = v.object_id
JOIN buckets b ON b.bucket_id = o.bucket_id
ORDER BY o.object_key, v.created_at DESC;

-- Inspect the logical current inventory. A delete marker hides the key.
SELECT * FROM current_object_inventory()
ORDER BY bucket_name, object_key;

-- Inspect custom metadata for the current monthly report.
SELECT o.object_key, v.version_id, m.metadata_key, m.metadata_value
FROM objects o
JOIN buckets b ON b.bucket_id = o.bucket_id
JOIN object_versions v ON v.object_id = o.object_id
JOIN object_metadata m ON m.object_version_id = v.object_version_id
WHERE b.bucket_name = 'enterprise-records-prod'
  AND o.object_key = 'reports/monthly.json'
  AND v.version_id = 'v-2026-09-02'
ORDER BY m.metadata_key;

-- Check policy outcomes for an authenticated auditor and a writer without TLS.
SELECT
    p.principal_name,
    requested.action_name,
    requested.object_key,
    evaluate_access(
        p.principal_id,
        b.bucket_id,
        requested.action_name,
        requested.object_key,
        requested.context
    ) AS allowed
FROM principals p
CROSS JOIN buckets b
CROSS JOIN (
    VALUES
      ('object:GetVersion', 'reports/monthly.json', '{}'::jsonb),
      ('object:Put', 'reports/monthly.json', '{}'::jsonb),
      ('object:Delete', 'legal/retention-register.csv', '{"transport":"tls"}'::jsonb)
) AS requested(action_name, object_key, context)
WHERE b.bucket_name = 'enterprise-records-prod'
  AND p.principal_name IN ('compliance-auditor', 'report-writer')
ORDER BY p.principal_name, requested.action_name;

-- Calculate storage consumption by class using all payload versions.
SELECT b.bucket_name, v.storage_class,
       count(*) AS version_count,
       sum(v.content_length) AS stored_payload_bytes
FROM object_versions v
JOIN objects o ON o.object_id = v.object_id
JOIN buckets b ON b.bucket_id = o.bucket_id
WHERE NOT v.is_delete_marker
GROUP BY b.bucket_name, v.storage_class
ORDER BY v.storage_class;

-- Lifecycle evaluation identifies candidates. This query does not mutate data.
SELECT b.bucket_name, o.object_key, v.version_id,
       r.rule_name, r.transition_after_days, r.target_storage_class,
       r.expire_current_after_days, r.expire_noncurrent_after_days,
       CASE
           WHEN r.transition_after_days IS NOT NULL
                AND v.storage_class <> r.target_storage_class
                AND v.created_at <= clock_timestamp()
                    - make_interval(days => r.transition_after_days)
               THEN 'TRANSITION_CANDIDATE'
           WHEN r.expire_noncurrent_after_days IS NOT NULL
                AND v.noncurrent_since IS NOT NULL
                AND v.noncurrent_since <= clock_timestamp()
                    - make_interval(days => r.expire_noncurrent_after_days)
               THEN 'NONCURRENT_EXPIRATION_CANDIDATE'
           WHEN r.expire_current_after_days IS NOT NULL
                AND v.noncurrent_since IS NULL
                AND v.created_at <= clock_timestamp()
                    - make_interval(days => r.expire_current_after_days)
               THEN 'CURRENT_EXPIRATION_CANDIDATE'
           ELSE 'NO_ACTION_DUE'
       END AS lifecycle_decision
FROM object_versions v
JOIN objects o ON o.object_id = v.object_id
JOIN buckets b ON b.bucket_id = o.bucket_id
JOIN lifecycle_rules r ON r.bucket_id = b.bucket_id
WHERE r.enabled AND o.object_key LIKE replace(r.object_prefix, '%', '\%') || '%'
ORDER BY o.object_key, v.created_at;

-- Demonstrate transactional creation of a new version. The old current
-- payload becomes noncurrent before the new version is inserted.
BEGIN;

SELECT o.object_id, b.bucket_id
FROM objects o
JOIN buckets b ON b.bucket_id = o.bucket_id
WHERE b.bucket_name = 'enterprise-records-prod'
  AND o.object_key = 'reports/monthly.json'
FOR UPDATE OF o;

UPDATE object_versions
SET noncurrent_since = clock_timestamp()
WHERE object_id = (
    SELECT o.object_id
    FROM objects o
    JOIN buckets b ON b.bucket_id = o.bucket_id
    WHERE b.bucket_name = 'enterprise-records-prod'
      AND o.object_key = 'reports/monthly.json'
)
AND noncurrent_since IS NULL
AND NOT is_delete_marker;

INSERT INTO object_versions (
    object_id, version_id, payload, content_type, content_length,
    etag, sha256, storage_class
)
SELECT o.object_id, 'v-2026-09-03',
       convert_to('{"month":"2026-09","incidents":15}', 'UTF8'),
       'application/json',
       octet_length(convert_to('{"month":"2026-09","incidents":15}', 'UTF8')),
       'etag-003',
       repeat('e', 64),
       'STANDARD'
FROM objects o
JOIN buckets b ON b.bucket_id = o.bucket_id
WHERE b.bucket_name = 'enterprise-records-prod'
  AND o.object_key = 'reports/monthly.json';

COMMIT;

-- Database integrity rejects an incorrect content length. Execute this
-- block to observe the exception in a client that continues after errors.
-- The exception block rolls back its own subtransaction and allows the
-- remainder of the script to execute.
DO $$
DECLARE
    v_object_id BIGINT;
BEGIN
    SELECT o.object_id INTO v_object_id
    FROM objects o
    JOIN buckets b ON b.bucket_id = o.bucket_id
    WHERE b.bucket_name = 'enterprise-records-prod'
      AND o.object_key = 'reports/monthly.json';

    BEGIN
        INSERT INTO object_versions (
            object_id, version_id, payload, content_type, content_length,
            etag, sha256
        )
        VALUES (
            v_object_id, 'invalid-length-example',
            convert_to('abc', 'UTF8'), 'text/plain', 99,
            'invalid-etag', repeat('f', 64)
        );
    EXCEPTION WHEN check_violation OR raise_exception THEN
        RAISE NOTICE 'Invalid object rejected: %', SQLERRM;
    END;
END;
$$;

SELECT audit_event_id, principal_id, action_name, outcome, event_detail, occurred_at
FROM storage_audit_events
ORDER BY occurred_at DESC;

COMMIT;
