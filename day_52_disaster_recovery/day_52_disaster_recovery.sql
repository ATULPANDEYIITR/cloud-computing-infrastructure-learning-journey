-- PostgreSQL Disaster Recovery model
-- Represents RPO/RTO policies, backups, restores, recovery architectures,
-- infrastructure nodes, incidents, validation checks, and recovery decisions.
--
-- The script is self-contained and can be executed in a fresh PostgreSQL
-- database. Objects are recreated so repeated execution remains deterministic.

DROP VIEW IF EXISTS recovery_eligibility_report CASCADE;
DROP VIEW IF EXISTS latest_recovery_points CASCADE;

DROP FUNCTION IF EXISTS evaluate_recovery(uuid, timestamptz) CASCADE;
DROP FUNCTION IF EXISTS validate_backup_checksum() CASCADE;
DROP FUNCTION IF EXISTS set_updated_at() CASCADE;

DROP TABLE IF EXISTS recovery_validation_checks CASCADE;
DROP TABLE IF EXISTS recovery_attempts CASCADE;
DROP TABLE IF EXISTS incidents CASCADE;
DROP TABLE IF EXISTS infrastructure_nodes CASCADE;
DROP TABLE IF EXISTS backups CASCADE;
DROP TABLE IF EXISTS recovery_policies CASCADE;
DROP TABLE IF EXISTS repositories CASCADE;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE repositories (
    repository_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_name text NOT NULL UNIQUE,
    production_region text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (length(trim(repository_name)) >= 3),
    CHECK (length(trim(production_region)) >= 2)
);

CREATE TABLE recovery_policies (
    policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id uuid NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    service_name text NOT NULL,
    rpo_minutes integer NOT NULL,
    rto_minutes integer NOT NULL,
    architecture text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now(),

    UNIQUE (repository_id, service_name),

    CHECK (rpo_minutes >= 0),
    CHECK (rto_minutes > 0),
    CHECK (
        architecture IN (
            'PILOT_LIGHT',
            'WARM_STANDBY',
            'ACTIVE_ACTIVE'
        )
    )
);

CREATE TABLE backups (
    backup_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id uuid NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    backup_key text NOT NULL UNIQUE,
    backup_type text NOT NULL,
    created_at timestamptz NOT NULL,
    source_version bigint NOT NULL,
    size_mb bigint NOT NULL,
    checksum text NOT NULL,
    immutable boolean NOT NULL DEFAULT true,
    encrypted boolean NOT NULL DEFAULT true,

    CHECK (backup_type IN ('FULL', 'INCREMENTAL')),
    CHECK (source_version > 0),
    CHECK (size_mb > 0),
    CHECK (checksum ~ '^sha256:[0-9a-fA-F]{8,}$')
);

CREATE TABLE infrastructure_nodes (
    node_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id uuid NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    node_name text NOT NULL,
    region text NOT NULL,
    architecture text NOT NULL,
    node_state text NOT NULL DEFAULT 'HEALTHY',
    serving_traffic boolean NOT NULL DEFAULT false,
    last_synchronized_at timestamptz,

    UNIQUE (repository_id, node_name),

    CHECK (
        architecture IN (
            'PILOT_LIGHT',
            'WARM_STANDBY',
            'ACTIVE_ACTIVE'
        )
    ),
    CHECK (
        node_state IN (
            'HEALTHY',
            'FAILED',
            'RECOVERING'
        )
    )
);

CREATE TABLE incidents (
    incident_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id uuid NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    failure_started_at timestamptz NOT NULL,
    failure_type text NOT NULL,
    severity text NOT NULL,
    incident_state text NOT NULL DEFAULT 'OPEN',
    detected_at timestamptz NOT NULL,

    CHECK (
        severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
    ),
    CHECK (
        incident_state IN (
            'OPEN',
            'RECOVERING',
            'RECOVERED',
            'FAILED'
        )
    ),
    CHECK (detected_at >= failure_started_at)
);

CREATE TABLE recovery_attempts (
    attempt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id uuid NOT NULL REFERENCES incidents(incident_id)
        ON DELETE CASCADE,
    backup_id uuid REFERENCES backups(backup_id)
        ON DELETE SET NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    restored_version bigint,
    recovery_status text NOT NULL DEFAULT 'STARTED',
    restore_message text,

    CHECK (
        recovery_status IN (
            'STARTED',
            'SUCCESS',
            'FAILED'
        )
    ),
    CHECK (
        completed_at IS NULL
        OR completed_at >= started_at
    )
);

CREATE TABLE recovery_validation_checks (
    check_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id uuid NOT NULL REFERENCES recovery_attempts(attempt_id)
        ON DELETE CASCADE,
    check_name text NOT NULL,
    passed boolean NOT NULL,
    checked_at timestamptz NOT NULL DEFAULT now(),
    details text,

    UNIQUE (attempt_id, check_name)
);

CREATE INDEX idx_backups_repository_created
    ON backups (repository_id, created_at DESC);

CREATE INDEX idx_incidents_repository_failure
    ON incidents (repository_id, failure_started_at DESC);

CREATE INDEX idx_attempts_incident_status
    ON recovery_attempts (incident_id, recovery_status);

CREATE INDEX idx_nodes_repository_state
    ON infrastructure_nodes (repository_id, node_state);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_recovery_policy_updated
BEFORE UPDATE ON recovery_policies
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE FUNCTION validate_backup_checksum()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.checksum !~ '^sha256:[0-9a-fA-F]{8,}$' THEN
        RAISE EXCEPTION
            'Backup % has invalid SHA-256 checksum format',
            NEW.backup_key;
    END IF;

    IF NOT NEW.immutable THEN
        RAISE EXCEPTION
            'Backup % must be immutable for disaster recovery',
            NEW.backup_key;
    END IF;

    IF NOT NEW.encrypted THEN
        RAISE EXCEPTION
            'Backup % must be encrypted',
            NEW.backup_key;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_backup
BEFORE INSERT OR UPDATE ON backups
FOR EACH ROW
EXECUTE FUNCTION validate_backup_checksum();

INSERT INTO repositories (
    repository_name,
    production_region
)
VALUES
    ('payments-platform', 'ap-south-1'),
    ('order-processing', 'eu-west-1');

INSERT INTO recovery_policies (
    repository_id,
    service_name,
    rpo_minutes,
    rto_minutes,
    architecture
)
SELECT
    repository_id,
    'Payments API',
    30,
    60,
    'PILOT_LIGHT'
FROM repositories
WHERE repository_name = 'payments-platform';

INSERT INTO recovery_policies (
    repository_id,
    service_name,
    rpo_minutes,
    rto_minutes,
    architecture
)
SELECT
    repository_id,
    'Order API',
    5,
    5,
    'ACTIVE_ACTIVE'
FROM repositories
WHERE repository_name = 'order-processing';

INSERT INTO backups (
    repository_id,
    backup_key,
    backup_type,
    created_at,
    source_version,
    size_mb,
    checksum
)
SELECT
    repository_id,
    'payments-full-001',
    'FULL',
    '2026-10-22 00:00:00+00',
    1000,
    8000,
    'sha256:11111111'
FROM repositories
WHERE repository_name = 'payments-platform';

INSERT INTO backups (
    repository_id,
    backup_key,
    backup_type,
    created_at,
    source_version,
    size_mb,
    checksum
)
SELECT
    repository_id,
    'payments-inc-002',
    'INCREMENTAL',
    '2026-10-22 00:30:00+00',
    1001,
    650,
    'sha256:22222222'
FROM repositories
WHERE repository_name = 'payments-platform';

INSERT INTO backups (
    repository_id,
    backup_key,
    backup_type,
    created_at,
    source_version,
    size_mb,
    checksum
)
SELECT
    repository_id,
    'payments-inc-003',
    'INCREMENTAL',
    '2026-10-22 01:00:00+00',
    1002,
    700,
    'sha256:33333333'
FROM repositories
WHERE repository_name = 'payments-platform';

INSERT INTO backups (
    repository_id,
    backup_key,
    backup_type,
    created_at,
    source_version,
    size_mb,
    checksum
)
SELECT
    repository_id,
    'orders-full-001',
    'FULL',
    '2026-10-22 00:00:00+00',
    2000,
    10000,
    'sha256:44444444'
FROM repositories
WHERE repository_name = 'order-processing';

INSERT INTO backups (
    repository_id,
    backup_key,
    backup_type,
    created_at,
    source_version,
    size_mb,
    checksum
)
SELECT
    repository_id,
    'orders-inc-002',
    'INCREMENTAL',
    '2026-10-22 01:30:00+00',
    2001,
    800,
    'sha256:55555555'
FROM repositories
WHERE repository_name = 'order-processing';

INSERT INTO infrastructure_nodes (
    repository_id,
    node_name,
    region,
    architecture,
    node_state,
    serving_traffic,
    last_synchronized_at
)
SELECT
    repository_id,
    'payments-primary',
    'ap-south-1',
    'PILOT_LIGHT',
    'HEALTHY',
    true,
    '2026-10-22 01:30:00+00'
FROM repositories
WHERE repository_name = 'payments-platform';

INSERT INTO infrastructure_nodes (
    repository_id,
    node_name,
    region,
    architecture,
    node_state,
    serving_traffic,
    last_synchronized_at
)
SELECT
    repository_id,
    'payments-dr',
    'ap-southeast-1',
    'PILOT_LIGHT',
    'HEALTHY',
    false,
    '2026-10-22 01:30:00+00'
FROM repositories
WHERE repository_name = 'payments-platform';

INSERT INTO infrastructure_nodes (
    repository_id,
    node_name,
    region,
    architecture,
    node_state,
    serving_traffic,
    last_synchronized_at
)
SELECT
    repository_id,
    'orders-region-a',
    'eu-west-1',
    'ACTIVE_ACTIVE',
    'HEALTHY',
    true,
    '2026-10-22 01:40:00+00'
FROM repositories
WHERE repository_name = 'order-processing';

INSERT INTO infrastructure_nodes (
    repository_id,
    node_name,
    region,
    architecture,
    node_state,
    serving_traffic,
    last_synchronized_at
)
SELECT
    repository_id,
    'orders-region-b',
    'eu-central-1',
    'ACTIVE_ACTIVE',
    'HEALTHY',
    true,
    '2026-10-22 01:40:00+00'
FROM repositories
WHERE repository_name = 'order-processing';

INSERT INTO incidents (
    repository_id,
    failure_started_at,
    failure_type,
    severity,
    detected_at
)
SELECT
    repository_id,
    '2026-10-22 01:45:00+00',
    'REGION_OUTAGE',
    'CRITICAL',
    '2026-10-22 01:47:00+00'
FROM repositories
WHERE repository_name = 'payments-platform';

INSERT INTO incidents (
    repository_id,
    failure_started_at,
    failure_type,
    severity,
    detected_at
)
SELECT
    repository_id,
    '2026-10-22 01:45:00+00',
    'REGION_OUTAGE',
    'CRITICAL',
    '2026-10-22 01:46:00+00'
FROM repositories
WHERE repository_name = 'order-processing';

CREATE OR REPLACE FUNCTION evaluate_recovery(
    p_incident_id uuid,
    p_recovery_completed_at timestamptz
)
RETURNS TABLE (
    service_name text,
    architecture text,
    rpo_target_minutes integer,
    observed_rpo_minutes bigint,
    rpo_satisfied boolean,
    rto_target_minutes integer,
    observed_rto_minutes bigint,
    rto_satisfied boolean,
    recovery_eligible boolean,
    selected_backup text
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH incident_data AS (
        SELECT
            i.incident_id,
            i.repository_id,
            i.failure_started_at
        FROM incidents i
        WHERE i.incident_id = p_incident_id
    ),
    selected_backup AS (
        SELECT DISTINCT ON (b.repository_id)
            b.repository_id,
            b.backup_key,
            b.created_at
        FROM backups b
        JOIN incident_data i
            ON i.repository_id = b.repository_id
        WHERE b.created_at <= i.failure_started_at
          AND b.immutable = true
          AND b.encrypted = true
        ORDER BY
            b.repository_id,
            b.created_at DESC
    )
    SELECT
        rp.service_name,
        rp.architecture,
        rp.rpo_minutes,
        EXTRACT(
            EPOCH FROM (
                i.failure_started_at - sb.created_at
            )
        )::bigint / 60 AS observed_rpo_minutes,
        (
            EXTRACT(
                EPOCH FROM (
                    i.failure_started_at - sb.created_at
                )
            )::bigint / 60 <= rp.rpo_minutes
        ) AS rpo_satisfied,
        rp.rto_minutes,
        EXTRACT(
            EPOCH FROM (
                p_recovery_completed_at - i.failure_started_at
            )
        )::bigint / 60 AS observed_rto_minutes,
        (
            EXTRACT(
                EPOCH FROM (
                    p_recovery_completed_at - i.failure_started_at
                )
            )::bigint / 60 <= rp.rto_minutes
        ) AS rto_satisfied,
        (
            EXTRACT(
                EPOCH FROM (
                    i.failure_started_at - sb.created_at
                )
            )::bigint / 60 <= rp.rpo_minutes
            AND
            EXTRACT(
                EPOCH FROM (
                    p_recovery_completed_at - i.failure_started_at
                )
            )::bigint / 60 <= rp.rto_minutes
        ) AS recovery_eligible,
        sb.backup_key
    FROM incident_data i
    JOIN recovery_policies rp
        ON rp.repository_id = i.repository_id
       AND rp.active = true
    JOIN selected_backup sb
        ON sb.repository_id = i.repository_id;
END;
$$;

CREATE OR REPLACE VIEW latest_recovery_points AS
SELECT DISTINCT ON (b.repository_id)
    b.repository_id,
    r.repository_name,
    b.backup_id,
    b.backup_key,
    b.backup_type,
    b.created_at,
    b.source_version,
    b.immutable,
    b.encrypted
FROM backups b
JOIN repositories r
    ON r.repository_id = b.repository_id
WHERE b.immutable = true
  AND b.encrypted = true
ORDER BY
    b.repository_id,
    b.created_at DESC;

CREATE OR REPLACE VIEW recovery_eligibility_report AS
WITH incident_backup AS (
    SELECT
        i.incident_id,
        i.repository_id,
        i.failure_started_at,
        b.backup_id,
        b.backup_key,
        b.created_at AS recovery_point,
        ROW_NUMBER() OVER (
            PARTITION BY i.incident_id
            ORDER BY b.created_at DESC
        ) AS recovery_rank
    FROM incidents i
    JOIN backups b
        ON b.repository_id = i.repository_id
       AND b.created_at <= i.failure_started_at
       AND b.immutable
       AND b.encrypted
)
SELECT
    i.incident_id,
    r.repository_name,
    rp.service_name,
    rp.architecture,
    rp.rpo_minutes AS target_rpo_minutes,
    EXTRACT(
        EPOCH FROM (
            i.failure_started_at - ib.recovery_point
        )
    )::bigint / 60 AS observed_rpo_minutes,
    rp.rto_minutes AS target_rto_minutes,
    i.incident_state,
    ib.backup_key AS selected_recovery_point
FROM incidents i
JOIN repositories r
    ON r.repository_id = i.repository_id
JOIN recovery_policies rp
    ON rp.repository_id = i.repository_id
JOIN incident_backup ib
    ON ib.incident_id = i.incident_id
   AND ib.recovery_rank = 1;

-- Query the latest recovery points.
SELECT *
FROM latest_recovery_points
ORDER BY repository_name;

-- Query policy, selected recovery point, and observed RPO.
SELECT *
FROM recovery_eligibility_report
ORDER BY repository_name;

-- Demonstrate a CTE that ranks backups for every incident.
WITH ranked_backups AS (
    SELECT
        i.incident_id,
        r.repository_name,
        b.backup_key,
        b.created_at,
        b.source_version,
        ROW_NUMBER() OVER (
            PARTITION BY i.incident_id
            ORDER BY b.created_at DESC
        ) AS recovery_rank
    FROM incidents i
    JOIN repositories r
        ON r.repository_id = i.repository_id
    JOIN backups b
        ON b.repository_id = i.repository_id
       AND b.created_at <= i.failure_started_at
)
SELECT
    incident_id,
    repository_name,
    backup_key,
    created_at,
    source_version
FROM ranked_backups
WHERE recovery_rank = 1
ORDER BY repository_name;

-- Transactional recovery attempt:
-- The incident is moved into RECOVERING, a restore is recorded, validation
-- checks are recorded, and the incident becomes RECOVERED only when the
-- recovery operation succeeds.
BEGIN;

WITH target_incident AS (
    SELECT incident_id
    FROM incidents
    WHERE failure_type = 'REGION_OUTAGE'
      AND incident_state = 'OPEN'
    ORDER BY failure_started_at
    LIMIT 1
)
UPDATE incidents i
SET incident_state = 'RECOVERING'
FROM target_incident t
WHERE i.incident_id = t.incident_id;

INSERT INTO recovery_attempts (
    incident_id,
    backup_id,
    started_at,
    completed_at,
    restored_version,
    recovery_status,
    restore_message
)
SELECT
    i.incident_id,
    b.backup_id,
    '2026-10-22 01:48:00+00',
    '2026-10-22 02:05:00+00',
    b.source_version,
    'SUCCESS',
    'Restore completed and integrity validation passed.'
FROM incidents i
JOIN LATERAL (
    SELECT *
    FROM backups b
    WHERE b.repository_id = i.repository_id
      AND b.created_at <= i.failure_started_at
      AND b.immutable
      AND b.encrypted
    ORDER BY b.created_at DESC
    LIMIT 1
) b ON true
WHERE i.incident_state = 'RECOVERING'
  AND i.failure_type = 'REGION_OUTAGE';

INSERT INTO recovery_validation_checks (
    attempt_id,
    check_name,
    passed,
    details
)
SELECT
    ra.attempt_id,
    validation.check_name,
    validation.passed,
    validation.details
FROM recovery_attempts ra
CROSS JOIN (
    VALUES
        (
            'backup-integrity',
            true,
            'Checksum and immutable encrypted backup requirements satisfied.'
        ),
        (
            'database-consistency',
            true,
            'Restored transaction log sequence is consistent.'
        ),
        (
            'application-health',
            true,
            'Application health endpoint returned a successful state.'
        )
    ) AS validation(check_name, passed, details)
WHERE ra.recovery_status = 'SUCCESS'
  AND ra.completed_at = '2026-10-22 02:05:00+00';

UPDATE incidents i
SET incident_state = 'RECOVERED'
WHERE i.incident_state = 'RECOVERING'
  AND EXISTS (
      SELECT 1
      FROM recovery_attempts ra
      JOIN recovery_validation_checks rvc
          ON rvc.attempt_id = ra.attempt_id
      WHERE ra.incident_id = i.incident_id
        AND ra.recovery_status = 'SUCCESS'
      GROUP BY ra.attempt_id
      HAVING bool_and(rvc.passed)
  );

COMMIT;

-- Demonstrate recovery validation reporting after the transaction.
SELECT
    r.repository_name,
    i.incident_id,
    i.incident_state,
    ra.recovery_status,
    ra.restored_version,
    COUNT(rvc.check_id) AS validation_count,
    COUNT(*) FILTER (WHERE rvc.passed) AS passed_checks
FROM repositories r
JOIN incidents i
    ON i.repository_id = r.repository_id
LEFT JOIN recovery_attempts ra
    ON ra.incident_id = i.incident_id
LEFT JOIN recovery_validation_checks rvc
    ON rvc.attempt_id = ra.attempt_id
GROUP BY
    r.repository_name,
    i.incident_id,
    i.incident_state,
    ra.recovery_status,
    ra.restored_version
ORDER BY r.repository_name;

-- Active-active capacity query.
-- A production active-active deployment should retain sufficient healthy
-- serving capacity after loss of one region.
SELECT
    r.repository_name,
    COUNT(*) FILTER (
        WHERE n.node_state = 'HEALTHY'
          AND n.serving_traffic
    ) AS healthy_serving_nodes,
    COUNT(*) AS total_nodes,
    (
        COUNT(*) FILTER (
            WHERE n.node_state = 'HEALTHY'
              AND n.serving_traffic
        ) >= 2
    ) AS active_active_capacity_available
FROM repositories r
JOIN infrastructure_nodes n
    ON n.repository_id = r.repository_id
GROUP BY r.repository_name
ORDER BY r.repository_name;

-- Identify backups that would violate minimum recovery-storage controls.
SELECT
    repository_name,
    backup_key,
    immutable,
    encrypted
FROM repositories r
JOIN backups b
    ON b.repository_id = r.repository_id
WHERE NOT immutable
   OR NOT encrypted;
