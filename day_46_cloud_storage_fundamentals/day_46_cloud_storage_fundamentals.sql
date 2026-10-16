-- PostgreSQL 15+
-- Cloud storage model covering durability, availability, replication,
-- redundancy, storage classes, lifecycle policies, and recovery operations.
--
-- All rates and reliability figures are illustrative, not provider quotations.

BEGIN;

DROP SCHEMA IF EXISTS cloud_storage_lab CASCADE;
CREATE SCHEMA cloud_storage_lab;
SET search_path TO cloud_storage_lab, public;

CREATE TYPE storage_class AS ENUM (
    'STANDARD',
    'INFREQUENT_ACCESS',
    'ARCHIVE'
);

CREATE TYPE replication_mode AS ENUM (
    'SINGLE_REGION',
    'SYNCHRONOUS',
    'ASYNCHRONOUS'
);

CREATE TYPE replication_state AS ENUM (
    'PENDING',
    'COMPLETED',
    'RETRYABLE_FAILURE',
    'PERMANENT_FAILURE'
);

CREATE TYPE region_state AS ENUM (
    'AVAILABLE',
    'UNAVAILABLE',
    'DEGRADED'
);

CREATE TYPE lifecycle_state AS ENUM (
    'ACTIVE',
    'ARCHIVED',
    'DELETED'
);

CREATE TABLE storage_classes (
    class_name storage_class PRIMARY KEY,
    monthly_cost_per_gb NUMERIC(12, 8) NOT NULL
        CHECK (monthly_cost_per_gb >= 0),
    retrieval_cost_per_gb NUMERIC(12, 8) NOT NULL
        CHECK (retrieval_cost_per_gb >= 0),
    minimum_retention_days INTEGER NOT NULL
        CHECK (minimum_retention_days >= 0),
    retrieval_latency_seconds INTEGER NOT NULL
        CHECK (retrieval_latency_seconds >= 0),
    description TEXT NOT NULL
);

INSERT INTO storage_classes VALUES
    ('STANDARD', 0.02300000, 0.00000000, 0, 1,
     'Frequent reads and low-latency access'),
    ('INFREQUENT_ACCESS', 0.01250000, 0.01000000, 30, 2,
     'Lower storage cost with retrieval charges and a retention floor'),
    ('ARCHIVE', 0.00400000, 0.03000000, 90, 3600,
     'Low-cost long-term retention with delayed retrieval');

CREATE TABLE regions (
    region_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    region_code TEXT NOT NULL UNIQUE,
    geography TEXT NOT NULL,
    state region_state NOT NULL DEFAULT 'AVAILABLE',
    failure_domain TEXT NOT NULL,
    last_health_check TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO regions (region_code, geography, failure_domain, state) VALUES
    ('ap-south-1', 'India', 'south-region', 'AVAILABLE'),
    ('ap-southeast-1', 'Southeast Asia', 'southeast-region', 'AVAILABLE'),
    ('eu-west-1', 'Europe', 'europe-region', 'AVAILABLE');

CREATE TABLE storage_buckets (
    bucket_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bucket_name TEXT NOT NULL UNIQUE,
    primary_region_id BIGINT NOT NULL REFERENCES regions(region_id),
    replication_policy replication_mode NOT NULL,
    versioning_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(bucket_name)) > 0)
);

INSERT INTO storage_buckets (
    bucket_name, primary_region_id, replication_policy, versioning_enabled
)
SELECT
    'compliance-evidence',
    region_id,
    'ASYNCHRONOUS',
    TRUE
FROM regions
WHERE region_code = 'ap-south-1';

CREATE TABLE stored_objects (
    object_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bucket_id BIGINT NOT NULL REFERENCES storage_buckets(bucket_id),
    object_key TEXT NOT NULL CHECK (length(trim(object_key)) > 0),
    current_version BIGINT NOT NULL DEFAULT 1 CHECK (current_version > 0),
    size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
    checksum_sha256 TEXT NOT NULL
        CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    class_name storage_class NOT NULL REFERENCES storage_classes(class_name),
    lifecycle lifecycle_state NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TIMESTAMPTZ,
    UNIQUE (bucket_id, object_key)
);

CREATE TABLE object_versions (
    version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    object_id BIGINT NOT NULL REFERENCES stored_objects(object_id),
    version_number BIGINT NOT NULL CHECK (version_number > 0),
    size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
    checksum_sha256 TEXT NOT NULL
        CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    class_name storage_class NOT NULL REFERENCES storage_classes(class_name),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (object_id, version_number)
);

CREATE UNIQUE INDEX one_current_version_per_object
    ON object_versions(object_id)
    WHERE is_current;

CREATE TABLE object_replicas (
    replica_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    object_id BIGINT NOT NULL REFERENCES stored_objects(object_id),
    region_id BIGINT NOT NULL REFERENCES regions(region_id),
    version_number BIGINT NOT NULL CHECK (version_number > 0),
    checksum_sha256 TEXT NOT NULL
        CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (object_id, region_id)
);

CREATE TABLE replication_jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    object_id BIGINT NOT NULL REFERENCES stored_objects(object_id),
    source_region_id BIGINT NOT NULL REFERENCES regions(region_id),
    target_region_id BIGINT NOT NULL REFERENCES regions(region_id),
    version_number BIGINT NOT NULL CHECK (version_number > 0),
    state replication_state NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error TEXT,
    queued_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    CHECK (source_region_id <> target_region_id)
);

CREATE INDEX pending_replication_jobs
    ON replication_jobs(queued_at)
    WHERE state IN ('PENDING', 'RETRYABLE_FAILURE');

CREATE TABLE lifecycle_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    object_id BIGINT NOT NULL REFERENCES stored_objects(object_id),
    from_class storage_class NOT NULL REFERENCES storage_classes(class_name),
    to_class storage_class NOT NULL REFERENCES storage_classes(class_name),
    event_day DATE NOT NULL DEFAULT CURRENT_DATE,
    estimated_cost NUMERIC(14, 6) NOT NULL CHECK (estimated_cost >= 0),
    accepted BOOLEAN NOT NULL,
    rejection_reason TEXT,
    CHECK (
        (accepted AND rejection_reason IS NULL)
        OR (NOT accepted AND rejection_reason IS NOT NULL)
    )
);

CREATE TABLE access_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    object_id BIGINT NOT NULL REFERENCES stored_objects(object_id),
    region_id BIGINT REFERENCES regions(region_id),
    event_type TEXT NOT NULL
        CHECK (event_type IN ('READ', 'WRITE', 'RESTORE', 'CHECKSUM_FAILURE')),
    succeeded BOOLEAN NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    latency_ms INTEGER CHECK (latency_ms >= 0)
);

CREATE TABLE durability_assumptions (
    assumption_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label TEXT NOT NULL UNIQUE,
    independent_copy_loss_probability NUMERIC(18, 16) NOT NULL
        CHECK (
            independent_copy_loss_probability > 0
            AND independent_copy_loss_probability < 1
        ),
    target_object_loss_probability NUMERIC(18, 16) NOT NULL
        CHECK (
            target_object_loss_probability > 0
            AND target_object_loss_probability < 1
        )
);

INSERT INTO durability_assumptions (
    label, independent_copy_loss_probability, target_object_loss_probability
) VALUES (
    'illustrative-independent-copy-model', 0.0001000000000000, 0.0000000000010000
);

-- A trigger prevents an object version from claiming to be current when its
-- version number differs from the parent object's declared current version.
CREATE FUNCTION validate_current_object_version()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    expected_version BIGINT;
BEGIN
    SELECT current_version
    INTO expected_version
    FROM stored_objects
    WHERE object_id = NEW.object_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Object % does not exist', NEW.object_id;
    END IF;

    IF NEW.is_current AND NEW.version_number <> expected_version THEN
        RAISE EXCEPTION
            'Current version % does not match object version %',
            NEW.version_number, expected_version;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER enforce_current_object_version
BEFORE INSERT OR UPDATE OF is_current, version_number, object_id
ON object_versions
FOR EACH ROW
EXECUTE FUNCTION validate_current_object_version();

-- The trigger rejects a replica when its recorded region is not the configured
-- destination's region or when it is older than the stored object's version.
CREATE FUNCTION validate_replica_version()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    expected_version BIGINT;
BEGIN
    SELECT current_version
    INTO expected_version
    FROM stored_objects
    WHERE object_id = NEW.object_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Object % does not exist', NEW.object_id;
    END IF;

    IF NEW.version_number > expected_version THEN
        RAISE EXCEPTION 'Replica version cannot exceed the source version';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER enforce_replica_version
BEFORE INSERT OR UPDATE OF version_number, object_id
ON object_replicas
FOR EACH ROW
EXECUTE FUNCTION validate_replica_version();

-- Create an object and its initial version atomically.
DO $$
DECLARE
    v_bucket BIGINT;
    v_object BIGINT;
    v_primary BIGINT;
BEGIN
    SELECT bucket_id, primary_region_id
    INTO v_bucket, v_primary
    FROM storage_buckets
    WHERE bucket_name = 'compliance-evidence';

    INSERT INTO stored_objects (
        bucket_id, object_key, current_version, size_bytes,
        checksum_sha256, class_name
    ) VALUES (
        v_bucket,
        'plant-07/inspection-2026-10-16.json',
        1,
        4096,
        repeat('a', 64),
        'STANDARD'
    )
    RETURNING object_id INTO v_object;

    INSERT INTO object_versions (
        object_id, version_number, size_bytes, checksum_sha256,
        class_name, is_current
    ) VALUES (
        v_object, 1, 4096, repeat('a', 64), 'STANDARD', TRUE
    );

    INSERT INTO object_replicas (
        object_id, region_id, version_number, checksum_sha256, verified_at
    ) VALUES (
        v_object, v_primary, 1, repeat('a', 64), CURRENT_TIMESTAMP
    );
END;
$$;

-- Queue asynchronous replication only for available destinations.
INSERT INTO replication_jobs (
    object_id, source_region_id, target_region_id, version_number
)
SELECT
    object.object_id,
    bucket.primary_region_id,
    target.region_id,
    object.current_version
FROM stored_objects AS object
JOIN storage_buckets AS bucket
    ON bucket.bucket_id = object.bucket_id
JOIN regions AS target
    ON target.region_id <> bucket.primary_region_id
WHERE bucket.bucket_name = 'compliance-evidence'
  AND bucket.replication_policy = 'ASYNCHRONOUS'
  AND target.state = 'AVAILABLE';

-- Successful replication delivery is performed within a transaction so that
-- the replica and the job state cannot be committed independently.
DO $$
DECLARE
    job RECORD;
BEGIN
    FOR job IN
        SELECT
            j.job_id,
            j.object_id,
            j.target_region_id,
            j.version_number,
            o.checksum_sha256
        FROM replication_jobs AS j
        JOIN stored_objects AS o ON o.object_id = j.object_id
        JOIN regions AS r ON r.region_id = j.target_region_id
        WHERE j.state IN ('PENDING', 'RETRYABLE_FAILURE')
          AND r.state = 'AVAILABLE'
        FOR UPDATE OF j
    LOOP
        INSERT INTO object_replicas (
            object_id, region_id, version_number, checksum_sha256, verified_at
        ) VALUES (
            job.object_id,
            job.target_region_id,
            job.version_number,
            job.checksum_sha256,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT (object_id, region_id)
        DO UPDATE SET
            version_number = EXCLUDED.version_number,
            checksum_sha256 = EXCLUDED.checksum_sha256,
            verified_at = EXCLUDED.verified_at
        WHERE object_replicas.version_number <= EXCLUDED.version_number;

        UPDATE replication_jobs
        SET state = 'COMPLETED',
            completed_at = CURRENT_TIMESTAMP,
            attempts = attempts + 1,
            last_error = NULL
        WHERE job_id = job.job_id;
    END LOOP;
END;
$$;

-- A failed destination remains retryable. It is not counted as a completed copy.
UPDATE regions
SET state = 'UNAVAILABLE',
    last_health_check = CURRENT_TIMESTAMP
WHERE region_code = 'eu-west-1';

UPDATE replication_jobs AS job
SET state = 'RETRYABLE_FAILURE',
    attempts = attempts + 1,
    last_error = 'Destination region unavailable'
FROM regions AS region
WHERE job.target_region_id = region.region_id
  AND region.state = 'UNAVAILABLE'
  AND job.state IN ('PENDING', 'RETRYABLE_FAILURE');

-- Restore region health and allow a subsequent replication attempt.
UPDATE regions
SET state = 'AVAILABLE',
    last_health_check = CURRENT_TIMESTAMP
WHERE region_code = 'eu-west-1';

-- Record a permitted lifecycle transition. Retention is calculated from object
-- creation time; actual provider-specific early-deletion charges may differ.
INSERT INTO lifecycle_events (
    object_id, from_class, to_class, event_day, estimated_cost,
    accepted, rejection_reason
)
SELECT
    object.object_id,
    object.class_name,
    'ARCHIVE',
    CURRENT_DATE,
    (object.size_bytes::NUMERIC / 1000000000)
        * target.monthly_cost_per_gb,
    CURRENT_DATE - object.created_at::DATE
        >= current_policy.minimum_retention_days,
    CASE
        WHEN CURRENT_DATE - object.created_at::DATE
            < current_policy.minimum_retention_days
        THEN 'Minimum retention period has not elapsed'
        ELSE NULL
    END
FROM stored_objects AS object
JOIN storage_classes AS current_policy
    ON current_policy.class_name = object.class_name
JOIN storage_classes AS target
    ON target.class_name = 'ARCHIVE'
WHERE object.object_key = 'plant-07/inspection-2026-10-16.json';

-- Storage and retrieval costs must be evaluated together.
SELECT
    class.class_name,
    class.monthly_cost_per_gb,
    class.retrieval_cost_per_gb,
    class.minimum_retention_days,
    class.retrieval_latency_seconds,
    500 * class.monthly_cost_per_gb
        + 20 * class.retrieval_cost_per_gb AS estimated_monthly_cost
FROM storage_classes AS class
ORDER BY estimated_monthly_cost;

-- Regional availability is distinct from object durability. An available
-- region does not count as an object replica unless the object is present.
CREATE VIEW object_resilience AS
SELECT
    object.object_id,
    object.object_key,
    object.current_version,
    COUNT(replica.replica_id) FILTER (
        WHERE region.state = 'AVAILABLE'
          AND replica.version_number = object.current_version
          AND replica.checksum_sha256 = object.checksum_sha256
    ) AS verified_available_current_copies,
    COUNT(replica.replica_id) FILTER (
        WHERE region.state = 'UNAVAILABLE'
    ) AS copies_in_unavailable_regions,
    COUNT(DISTINCT region.failure_domain) FILTER (
        WHERE region.state = 'AVAILABLE'
          AND replica.version_number = object.current_version
          AND replica.checksum_sha256 = object.checksum_sha256
    ) AS independent_available_failure_domains
FROM stored_objects AS object
LEFT JOIN object_replicas AS replica
    ON replica.object_id = object.object_id
LEFT JOIN regions AS region
    ON region.region_id = replica.region_id
GROUP BY
    object.object_id,
    object.object_key,
    object.current_version,
    object.checksum_sha256;

SELECT * FROM object_resilience ORDER BY object_id;

-- Estimate read availability if any independently failing service path can
-- answer a request. This model does not capture correlated failures.
WITH parameters AS (
    SELECT 0.999::NUMERIC AS path_availability
),
copy_counts AS (
    SELECT
        object.object_id,
        COALESCE(
            COUNT(DISTINCT region.failure_domain) FILTER (
                WHERE region.state = 'AVAILABLE'
                  AND replica.version_number = object.current_version
            ), 0
        ) AS copies
    FROM stored_objects AS object
    LEFT JOIN object_replicas AS replica
        ON replica.object_id = object.object_id
    LEFT JOIN regions AS region
        ON region.region_id = replica.region_id
    GROUP BY object.object_id
)
SELECT
    copy_counts.object_id,
    copy_counts.copies,
    CASE
        WHEN copy_counts.copies = 0 THEN 0
        ELSE 1 - POWER(
            1 - parameters.path_availability,
            copy_counts.copies
        )
    END AS estimated_availability
FROM copy_counts
CROSS JOIN parameters;

-- Illustrative independent-copy durability calculation.
SELECT
    label,
    CEIL(
        LN(target_object_loss_probability)
        / LN(independent_copy_loss_probability)
    )::INTEGER AS estimated_minimum_independent_copies,
    POWER(
        independent_copy_loss_probability,
        CEIL(
            LN(target_object_loss_probability)
            / LN(independent_copy_loss_probability)
        )
    ) AS estimated_object_loss_probability
FROM durability_assumptions;

-- Identify replication lag, missing current copies, and failed integrity checks.
SELECT
    object.object_key,
    job.target_region_id,
    job.version_number AS queued_version,
    job.state,
    job.attempts,
    job.last_error
FROM replication_jobs AS job
JOIN stored_objects AS object ON object.object_id = job.object_id
WHERE job.state <> 'COMPLETED'
ORDER BY job.queued_at;

SELECT
    object.object_key,
    replica.region_id,
    replica.version_number,
    object.current_version,
    replica.checksum_sha256 = object.checksum_sha256 AS checksum_matches
FROM object_replicas AS replica
JOIN stored_objects AS object ON object.object_id = replica.object_id
WHERE replica.version_number <> object.current_version
   OR replica.checksum_sha256 <> object.checksum_sha256;

-- Constraints expose invalid records at the database boundary. For example,
-- an object with a negative size, a malformed digest, or a duplicate key is
-- rejected rather than silently accepted by the storage application.
--
-- Production systems should also enforce authorization, immutable audit logs,
-- tested restoration procedures, cross-account backups, and provider-specific
-- lifecycle and replication guarantees. Live replicas alone are not backups.

COMMIT;
