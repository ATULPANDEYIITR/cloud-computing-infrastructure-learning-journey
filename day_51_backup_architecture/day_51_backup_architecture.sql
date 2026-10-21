DROP SCHEMA IF EXISTS backup_architecture CASCADE;
CREATE SCHEMA backup_architecture;
SET search_path TO backup_architecture;

-- A repository identifies the protected workload. A backup repository is
-- modeled separately because operational source data and recovery storage
-- have different failure domains.
CREATE TABLE repositories (
    repository_id      BIGSERIAL PRIMARY KEY,
    repository_name    TEXT NOT NULL UNIQUE,
    source_uri         TEXT NOT NULL,
    backup_storage_uri TEXT NOT NULL,
    enabled            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE branches (
    branch_id       BIGSERIAL PRIMARY KEY,
    repository_id   BIGINT NOT NULL REFERENCES repositories(repository_id)
                    ON DELETE CASCADE,
    branch_name     TEXT NOT NULL,
    protected       BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (repository_id, branch_name)
);

CREATE TABLE backup_policies (
    policy_id                  BIGSERIAL PRIMARY KEY,
    repository_id              BIGINT NOT NULL
                               REFERENCES repositories(repository_id)
                               ON DELETE CASCADE,
    full_frequency_hours       INTEGER NOT NULL
                               CHECK (full_frequency_hours > 0),
    incremental_frequency_hours INTEGER NOT NULL
                               CHECK (incremental_frequency_hours > 0),
    snapshot_frequency_hours   INTEGER NOT NULL
                               CHECK (snapshot_frequency_hours > 0),
    retention_days             INTEGER NOT NULL
                               CHECK (retention_days > 0),
    minimum_full_backups       INTEGER NOT NULL DEFAULT 2
                               CHECK (minimum_full_backups >= 1),
    verify_after_backup        BOOLEAN NOT NULL DEFAULT TRUE,
    enabled                    BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (repository_id)
);

CREATE TYPE backup_type AS ENUM (
    'full',
    'incremental',
    'snapshot'
);

CREATE TYPE backup_status AS ENUM (
    'running',
    'completed',
    'failed',
    'expired'
);

CREATE TABLE backups (
    backup_id          BIGSERIAL PRIMARY KEY,
    repository_id      BIGINT NOT NULL
                       REFERENCES repositories(repository_id)
                       ON DELETE CASCADE,
    parent_backup_id   BIGINT REFERENCES backups(backup_id),
    backup_type        backup_type NOT NULL,
    status             backup_status NOT NULL DEFAULT 'running',
    started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at       TIMESTAMPTZ,
    source_bytes       BIGINT NOT NULL DEFAULT 0
                       CHECK (source_bytes >= 0),
    stored_bytes       BIGINT NOT NULL DEFAULT 0
                       CHECK (stored_bytes >= 0),
    object_count       INTEGER NOT NULL DEFAULT 0
                       CHECK (object_count >= 0),
    checksum_algorithm TEXT NOT NULL DEFAULT 'sha256',
    storage_uri        TEXT NOT NULL,
    failure_reason     TEXT,

    CHECK (
        backup_type = 'full'
        OR parent_backup_id IS NOT NULL
        OR status IN ('running', 'failed')
    ),

    CHECK (
        status <> 'completed'
        OR completed_at IS NOT NULL
    ),

    CHECK (
        status <> 'failed'
        OR failure_reason IS NOT NULL
    )
);

CREATE INDEX idx_backups_repository_time
    ON backups (repository_id, started_at DESC);

CREATE INDEX idx_backups_parent
    ON backups (parent_backup_id);

CREATE INDEX idx_backups_completed
    ON backups (repository_id, completed_at DESC)
    WHERE status = 'completed';

CREATE TABLE backup_files (
    backup_file_id BIGSERIAL PRIMARY KEY,
    backup_id      BIGINT NOT NULL REFERENCES backups(backup_id)
                   ON DELETE CASCADE,
    relative_path  TEXT NOT NULL,
    file_size      BIGINT NOT NULL CHECK (file_size >= 0),
    checksum       TEXT NOT NULL,
    modified_at    TIMESTAMPTZ NOT NULL,
    UNIQUE (backup_id, relative_path)
);

CREATE TABLE backup_verifications (
    verification_id BIGSERIAL PRIMARY KEY,
    backup_id       BIGINT NOT NULL REFERENCES backups(backup_id)
                    ON DELETE CASCADE,
    verified_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    passed          BOOLEAN NOT NULL,
    checked_files   INTEGER NOT NULL DEFAULT 0
                    CHECK (checked_files >= 0),
    failure_count   INTEGER NOT NULL DEFAULT 0
                    CHECK (failure_count >= 0),
    details         JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TYPE schedule_type AS ENUM (
    'full',
    'incremental',
    'snapshot'
);

CREATE TABLE backup_schedule (
    schedule_id       BIGSERIAL PRIMARY KEY,
    repository_id     BIGINT NOT NULL
                      REFERENCES repositories(repository_id)
                      ON DELETE CASCADE,
    schedule_type     schedule_type NOT NULL,
    interval_minutes  INTEGER NOT NULL
                      CHECK (interval_minutes > 0),
    next_run_at       TIMESTAMPTZ NOT NULL,
    enabled            BOOLEAN NOT NULL DEFAULT TRUE
);

-- The trigger prevents an incremental backup from referencing a backup
-- belonging to a different repository.
CREATE OR REPLACE FUNCTION validate_backup_parent()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    parent_repository BIGINT;
    parent_type backup_type;
BEGIN
    IF NEW.parent_backup_id IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT repository_id, backup_type
    INTO parent_repository, parent_type
    FROM backups
    WHERE backup_id = NEW.parent_backup_id;

    IF parent_repository IS NULL THEN
        RAISE EXCEPTION
            'Parent backup % does not exist',
            NEW.parent_backup_id;
    END IF;

    IF parent_repository <> NEW.repository_id THEN
        RAISE EXCEPTION
            'Parent backup belongs to another repository';
    END IF;

    IF NEW.backup_type = 'incremental'
       AND parent_type NOT IN ('full', 'incremental') THEN
        RAISE EXCEPTION
            'Incremental backup cannot use snapshot as parent';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_backup_parent
BEFORE INSERT OR UPDATE ON backups
FOR EACH ROW
EXECUTE FUNCTION validate_backup_parent();

-- A completed backup must contain a completion timestamp and an actual
-- stored object count. This complements the table-level constraints.
CREATE OR REPLACE FUNCTION validate_completed_backup()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    actual_count INTEGER;
BEGIN
    IF NEW.status = 'completed' THEN
        SELECT count(*)
        INTO actual_count
        FROM backup_files
        WHERE backup_id = NEW.backup_id;

        IF actual_count = 0 THEN
            RAISE EXCEPTION
                'Completed backup % contains no files',
                NEW.backup_id;
        END IF;

        IF NEW.completed_at IS NULL THEN
            RAISE EXCEPTION
                'Completed backup % requires completed_at',
                NEW.backup_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_completed_backup
BEFORE INSERT OR UPDATE ON backups
FOR EACH ROW
EXECUTE FUNCTION validate_completed_backup();

CREATE OR REPLACE VIEW successful_backups AS
SELECT
    b.backup_id,
    r.repository_name,
    b.backup_type,
    b.status,
    b.started_at,
    b.completed_at,
    b.source_bytes,
    b.stored_bytes,
    b.object_count,
    round(
        100.0 * b.stored_bytes
        / NULLIF(b.source_bytes, 0),
        2
    ) AS storage_ratio
FROM backups b
JOIN repositories r
    ON r.repository_id = b.repository_id
WHERE b.status = 'completed';

CREATE OR REPLACE VIEW backup_health AS
SELECT
    r.repository_name,
    count(b.backup_id)
        FILTER (WHERE b.status = 'completed')
        AS completed_backups,
    count(b.backup_id)
        FILTER (WHERE b.status = 'failed')
        AS failed_backups,
    max(b.completed_at)
        FILTER (WHERE b.status = 'completed')
        AS latest_completed_backup,
    max(v.verified_at)
        FILTER (WHERE v.passed)
        AS latest_successful_verification
FROM repositories r
LEFT JOIN backups b
    ON b.repository_id = r.repository_id
LEFT JOIN backup_verifications v
    ON v.backup_id = b.backup_id
GROUP BY r.repository_id, r.repository_name;

CREATE OR REPLACE FUNCTION mark_backup_completed(
    p_backup_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    file_count INTEGER;
    stored_total BIGINT;
BEGIN
    SELECT count(*), COALESCE(sum(file_size), 0)
    INTO file_count, stored_total
    FROM backup_files
    WHERE backup_id = p_backup_id;

    IF file_count = 0 THEN
        RAISE EXCEPTION
            'Cannot complete backup % without files',
            p_backup_id;
    END IF;

    UPDATE backups
    SET status = 'completed',
        completed_at = now(),
        object_count = file_count,
        stored_bytes = stored_total
    WHERE backup_id = p_backup_id
      AND status = 'running';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Backup % is not in running state',
            p_backup_id;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION eligible_restore_points(
    p_repository_id BIGINT
)
RETURNS TABLE (
    backup_id BIGINT,
    backup_type backup_type,
    completed_at TIMESTAMPTZ,
    chain_depth INTEGER
)
LANGUAGE sql
AS $$
    WITH RECURSIVE chain AS (
        SELECT
            b.backup_id,
            b.backup_type,
            b.completed_at,
            b.parent_backup_id,
            0 AS chain_depth
        FROM backups b
        WHERE b.repository_id = p_repository_id
          AND b.status = 'completed'
          AND b.backup_type = 'full'

        UNION ALL

        SELECT
            child.backup_id,
            child.backup_type,
            child.completed_at,
            child.parent_backup_id,
            parent.chain_depth + 1
        FROM backups child
        JOIN chain parent
            ON child.parent_backup_id = parent.backup_id
        WHERE child.status = 'completed'
    )
    SELECT
        backup_id,
        backup_type,
        completed_at,
        chain_depth
    FROM chain
    ORDER BY completed_at DESC;
$$;

INSERT INTO repositories (
    repository_name,
    source_uri,
    backup_storage_uri
)
VALUES (
    'payments-production',
    'postgresql://payments-primary',
    's3://company-backups/payments-production/'
);

INSERT INTO branches (
    repository_id,
    branch_name,
    protected
)
SELECT
    repository_id,
    branch_name,
    protected
FROM repositories
CROSS JOIN (
    VALUES
        ('main', TRUE),
        ('release', TRUE),
        ('feature/backup-policy', FALSE)
) AS branch_data(branch_name, protected)
WHERE repository_name = 'payments-production';

INSERT INTO backup_policies (
    repository_id,
    full_frequency_hours,
    incremental_frequency_hours,
    snapshot_frequency_hours,
    retention_days,
    minimum_full_backups
)
SELECT
    repository_id,
    24,
    1,
    6,
    30,
    2
FROM repositories
WHERE repository_name = 'payments-production';

INSERT INTO backup_schedule (
    repository_id,
    schedule_type,
    interval_minutes,
    next_run_at
)
SELECT
    repository_id,
    'full',
    1440,
    now() + interval '1 day'
FROM repositories
WHERE repository_name = 'payments-production';

INSERT INTO backup_schedule (
    repository_id,
    schedule_type,
    interval_minutes,
    next_run_at
)
SELECT
    repository_id,
    'incremental',
    60,
    now() + interval '1 hour'
FROM repositories
WHERE repository_name = 'payments-production';

INSERT INTO backup_schedule (
    repository_id,
    schedule_type,
    interval_minutes,
    next_run_at
)
SELECT
    repository_id,
    'snapshot',
    360,
    now() + interval '6 hours'
FROM repositories
WHERE repository_name = 'payments-production';

BEGIN;

INSERT INTO backups (
    repository_id,
    backup_type,
    status,
    source_bytes,
    stored_bytes,
    object_count,
    storage_uri,
    completed_at
)
SELECT
    repository_id,
    'full',
    'completed',
    1200000000,
    1200000000,
    3,
    's3://company-backups/payments-production/full-001/',
    now() - interval '12 hours'
FROM repositories
WHERE repository_name = 'payments-production';

COMMIT;

INSERT INTO backup_files (
    backup_id,
    relative_path,
    file_size,
    checksum,
    modified_at
)
SELECT
    backup_id,
    file_data.relative_path,
    file_data.file_size,
    file_data.checksum,
    now() - interval '1 day'
FROM backups
CROSS JOIN (
    VALUES
        ('database/payments.dump', 800000000, repeat('a', 64)),
        ('database/customers.dump', 350000000, repeat('b', 64)),
        ('application/config.json', 5000, repeat('c', 64))
) AS file_data(relative_path, file_size, checksum)
WHERE backup_type = 'full'
  AND status = 'completed'
  AND backup_id = (
      SELECT min(backup_id)
      FROM backups
      WHERE backup_type = 'full'
        AND status = 'completed'
  );

-- An incremental backup stores only changes after the full backup.
BEGIN;

INSERT INTO backups (
    repository_id,
    parent_backup_id,
    backup_type,
    status,
    source_bytes,
    storage_uri
)
SELECT
    repository_id,
    backup_id,
    'incremental',
    'running',
    1250000000,
    's3://company-backups/payments-production/incremental-001/'
FROM backups
WHERE backup_type = 'full'
  AND status = 'completed'
  AND backup_id = (
      SELECT min(backup_id)
      FROM backups
      WHERE backup_type = 'full'
        AND status = 'completed'
  );

INSERT INTO backup_files (
    backup_id,
    relative_path,
    file_size,
    checksum,
    modified_at
)
SELECT
    max(backup_id),
    'database/payments.dump',
    50000000,
    repeat('d', 64),
    now()
FROM backups
WHERE backup_type = 'incremental'
  AND status = 'running';

INSERT INTO backup_files (
    backup_id,
    relative_path,
    file_size,
    checksum,
    modified_at
)
SELECT
    max(backup_id),
    'database/audit.dump',
    15000000,
    repeat('e', 64),
    now()
FROM backups
WHERE backup_type = 'incremental'
  AND status = 'running';

SELECT mark_backup_completed(
    (
        SELECT max(backup_id)
        FROM backups
        WHERE backup_type = 'incremental'
          AND status = 'running'
    )
);

COMMIT;

INSERT INTO backup_verifications (
    backup_id,
    passed,
    checked_files,
    failure_count,
    details
)
SELECT
    backup_id,
    TRUE,
    object_count,
    0,
    jsonb_build_object(
        'checksum_algorithm', checksum_algorithm,
        'verified_at', now()
    )
FROM backups
WHERE status = 'completed';

-- Simulate a failed backup. The failure reason is mandatory at database level.
INSERT INTO backups (
    repository_id,
    backup_type,
    status,
    source_bytes,
    stored_bytes,
    object_count,
    storage_uri,
    failure_reason
)
SELECT
    repository_id,
    'snapshot',
    'failed',
    1250000000,
    0,
    0,
    's3://company-backups/payments-production/snapshot-failed/',
    'Storage endpoint unavailable'
FROM repositories
WHERE repository_name = 'payments-production';

-- Retrieve recent successful restore points.
SELECT *
FROM successful_backups
ORDER BY completed_at DESC;

-- Show repository-level operational health.
SELECT *
FROM backup_health;

-- Reconstruct an incremental chain using a recursive CTE.
SELECT *
FROM eligible_restore_points(
    (
        SELECT repository_id
        FROM repositories
        WHERE repository_name = 'payments-production'
    )
);

-- Find backups that have completed but lack a successful verification.
SELECT
    b.backup_id,
    b.backup_type,
    b.completed_at
FROM backups b
WHERE b.status = 'completed'
  AND NOT EXISTS (
      SELECT 1
      FROM backup_verifications v
      WHERE v.backup_id = b.backup_id
        AND v.passed = TRUE
  );

-- Estimate storage consumed by each backup type.
SELECT
    backup_type,
    count(*) AS backup_count,
    sum(stored_bytes) AS stored_bytes,
    avg(stored_bytes) AS average_stored_bytes
FROM backups
WHERE status = 'completed'
GROUP BY backup_type
ORDER BY backup_type;

-- Identify repositories whose newest completed backup is older than policy allows.
SELECT
    r.repository_name,
    max(b.completed_at) AS latest_backup,
    p.retention_days,
    now() - max(b.completed_at) AS backup_age
FROM repositories r
JOIN backup_policies p
    ON p.repository_id = r.repository_id
LEFT JOIN backups b
    ON b.repository_id = r.repository_id
   AND b.status = 'completed'
GROUP BY
    r.repository_id,
    r.repository_name,
    p.retention_days
HAVING max(b.completed_at)
       < now() - make_interval(days => p.retention_days);
