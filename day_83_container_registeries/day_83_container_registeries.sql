/*
 * Container Registry Management and Image Distribution
 *
 * PostgreSQL 15+
 *
 * Models:
 * - Registries and image repositories
 * - Private repository access
 * - Users, roles, and permissions
 * - OCI-style manifests and image layers
 * - Content-addressed image artifacts
 * - Tags, semantic versions, and immutable releases
 * - Image publishing and distribution
 * - Quarantine and lifecycle states
 * - Audit events
 * - Garbage collection
 * - Repository policy evaluation
 *
 * Run as a database role with permission to create schemas,
 * tables, functions, triggers, and procedures.
 */

BEGIN;

CREATE SCHEMA IF NOT EXISTS container_registry;

SET search_path TO container_registry, public;

-- ============================================================
-- 1. DOMAIN TYPES
-- ============================================================

CREATE TYPE access_role AS ENUM (
    'reader',
    'writer',
    'admin'
);

CREATE TYPE image_state AS ENUM (
    'available',
    'quarantined',
    'deleted'
);

CREATE TYPE registry_operation AS ENUM (
    'push',
    'pull',
    'delete',
    'admin'
);

CREATE TYPE audit_outcome AS ENUM (
    'success',
    'failure'
);

-- ============================================================
-- 2. REGISTRIES AND USERS
-- ============================================================

CREATE TABLE registries (
    registry_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    registry_name VARCHAR(120) NOT NULL UNIQUE,
    endpoint TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_registry_name
        CHECK (
            registry_name ~ '^[a-z0-9][a-z0-9.-]*$'
        ),

    CONSTRAINT valid_registry_endpoint
        CHECK (endpoint ~ '^https://')
);

CREATE TABLE registry_users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    credential_hash TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_username
        CHECK (username ~ '^[a-zA-Z0-9_.-]{3,100}$'),

    CONSTRAINT valid_credential_hash
        CHECK (length(credential_hash) >= 32)
);

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    registry_id BIGINT NOT NULL
        REFERENCES registries(registry_id)
        ON DELETE CASCADE,

    repository_name VARCHAR(255) NOT NULL,
    is_private BOOLEAN NOT NULL DEFAULT TRUE,
    immutable_tags BOOLEAN NOT NULL DEFAULT FALSE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_repository
        UNIQUE (registry_id, repository_name),

    CONSTRAINT valid_repository_name
        CHECK (
            repository_name ~
            '^[a-z0-9]+([._/-][a-z0-9]+)*$'
        )
);

CREATE TABLE repository_permissions (
    permission_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,

    user_id BIGINT NOT NULL
        REFERENCES registry_users(user_id)
        ON DELETE CASCADE,

    role access_role NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    granted_by BIGINT REFERENCES registry_users(user_id),

    CONSTRAINT unique_repository_user
        UNIQUE (repository_id, user_id)
);

-- ============================================================
-- 3. IMAGE MANIFESTS AND LAYERS
-- ============================================================

CREATE TABLE image_artifacts (
    artifact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,

    manifest_digest VARCHAR(71) NOT NULL,
    config_digest VARCHAR(71) NOT NULL,
    media_type TEXT NOT NULL,
    architecture VARCHAR(30) NOT NULL,
    operating_system VARCHAR(30) NOT NULL DEFAULT 'linux',

    state image_state NOT NULL DEFAULT 'available',

    manifest_size_bytes BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pushed_by BIGINT REFERENCES registry_users(user_id),

    CONSTRAINT unique_repository_manifest
        UNIQUE (repository_id, manifest_digest),

    CONSTRAINT valid_manifest_digest
        CHECK (
            manifest_digest ~ '^sha256:[a-f0-9]{64}$'
        ),

    CONSTRAINT valid_config_digest
        CHECK (
            config_digest ~ '^sha256:[a-f0-9]{64}$'
        ),

    CONSTRAINT valid_manifest_size
        CHECK (manifest_size_bytes >= 0),

    CONSTRAINT valid_architecture
        CHECK (
            architecture IN ('amd64', 'arm64', 'arm', '386')
        ),

    CONSTRAINT valid_media_type
        CHECK (length(media_type) > 0)
);

CREATE TABLE image_layers (
    layer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    artifact_id BIGINT NOT NULL
        REFERENCES image_artifacts(artifact_id)
        ON DELETE CASCADE,

    layer_digest VARCHAR(71) NOT NULL,
    layer_size_bytes BIGINT NOT NULL,

    layer_order INTEGER NOT NULL,

    CONSTRAINT valid_layer_digest
        CHECK (
            layer_digest ~ '^sha256:[a-f0-9]{64}$'
        ),

    CONSTRAINT positive_layer_size
        CHECK (layer_size_bytes > 0),

    CONSTRAINT nonnegative_layer_order
        CHECK (layer_order >= 0),

    CONSTRAINT unique_layer_position
        UNIQUE (artifact_id, layer_order)
);

-- ============================================================
-- 4. IMAGE TAGS AND VERSIONING
-- ============================================================

CREATE TABLE image_tags (
    tag_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,

    artifact_id BIGINT NOT NULL
        REFERENCES image_artifacts(artifact_id)
        ON DELETE RESTRICT,

    tag_name VARCHAR(128) NOT NULL,
    semantic_version VARCHAR(64),
    is_protected BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_repository_tag
        UNIQUE (repository_id, tag_name),

    CONSTRAINT valid_tag_name
        CHECK (
            tag_name ~ '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$'
        ),

    CONSTRAINT valid_semantic_version
        CHECK (
            semantic_version IS NULL OR
            semantic_version ~
            '^[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?(\+[A-Za-z0-9.-]+)?$'
        )
);

-- ============================================================
-- 5. AUDIT AND DISTRIBUTION METRICS
-- ============================================================

CREATE TABLE registry_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    registry_id BIGINT NOT NULL
        REFERENCES registries(registry_id),

    repository_id BIGINT
        REFERENCES repositories(repository_id)
        ON DELETE SET NULL,

    user_id BIGINT
        REFERENCES registry_users(user_id)
        ON DELETE SET NULL,

    operation registry_operation NOT NULL,
    reference TEXT,
    outcome audit_outcome NOT NULL,
    failure_reason TEXT,
    source_ip INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE image_distribution_events (
    distribution_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    artifact_id BIGINT NOT NULL
        REFERENCES image_artifacts(artifact_id),

    user_id BIGINT REFERENCES registry_users(user_id),

    event_type VARCHAR(30) NOT NULL,
    bytes_transferred BIGINT NOT NULL DEFAULT 0,
    source_region VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_distribution_event
        CHECK (
            event_type IN (
                'pull_started',
                'pull_completed',
                'pull_failed',
                'push_completed'
            )
        ),

    CONSTRAINT nonnegative_transfer
        CHECK (bytes_transferred >= 0)
);

-- ============================================================
-- 6. PERFORMANCE INDEXES
-- ============================================================

CREATE INDEX idx_repositories_registry
    ON repositories(registry_id, repository_name);

CREATE INDEX idx_artifacts_repository_state
    ON image_artifacts(repository_id, state);

CREATE INDEX idx_artifacts_digest
    ON image_artifacts(manifest_digest);

CREATE INDEX idx_tags_repository_name
    ON image_tags(repository_id, tag_name);

CREATE INDEX idx_tags_artifact
    ON image_tags(artifact_id);

CREATE INDEX idx_permissions_user
    ON repository_permissions(user_id, repository_id);

CREATE INDEX idx_audit_repository_time
    ON registry_audit(repository_id, created_at DESC);

CREATE INDEX idx_audit_user_time
    ON registry_audit(user_id, created_at DESC);

CREATE INDEX idx_distribution_artifact_time
    ON image_distribution_events(artifact_id, created_at DESC);

-- ============================================================
-- 7. INTEGRITY TRIGGERS
-- ============================================================

CREATE OR REPLACE FUNCTION validate_tag_repository()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    artifact_repository BIGINT;
BEGIN
    SELECT repository_id
    INTO artifact_repository
    FROM image_artifacts
    WHERE artifact_id = NEW.artifact_id;

    IF artifact_repository IS NULL THEN
        RAISE EXCEPTION 'Image artifact does not exist';
    END IF;

    IF artifact_repository <> NEW.repository_id THEN
        RAISE EXCEPTION
            'Tag and artifact must belong to the same repository';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_tag_repository
BEFORE INSERT OR UPDATE OF repository_id, artifact_id
ON image_tags
FOR EACH ROW
EXECUTE FUNCTION validate_tag_repository();


CREATE OR REPLACE FUNCTION enforce_tag_immutability()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    repository_immutable BOOLEAN;
BEGIN
    SELECT immutable_tags
    INTO repository_immutable
    FROM repositories
    WHERE repository_id = OLD.repository_id;

    IF repository_immutable AND
       NEW.artifact_id <> OLD.artifact_id THEN
        RAISE EXCEPTION
            'Repository uses immutable tags';
    END IF;

    IF OLD.is_protected AND
       NEW.artifact_id <> OLD.artifact_id THEN
        RAISE EXCEPTION
            'Protected tags cannot be reassigned';
    END IF;

    IF OLD.is_protected AND NOT NEW.is_protected THEN
        RAISE EXCEPTION
            'Protected tag status cannot be removed through tag update';
    END IF;

    NEW.updated_at = NOW();

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_enforce_tag_immutability
BEFORE UPDATE ON image_tags
FOR EACH ROW
EXECUTE FUNCTION enforce_tag_immutability();


CREATE OR REPLACE FUNCTION prevent_protected_tag_deletion()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.is_protected THEN
        RAISE EXCEPTION
            'Protected image tag cannot be deleted';
    END IF;

    RETURN OLD;
END;
$$;

CREATE TRIGGER trg_prevent_protected_tag_deletion
BEFORE DELETE ON image_tags
FOR EACH ROW
EXECUTE FUNCTION prevent_protected_tag_deletion();


CREATE OR REPLACE FUNCTION validate_image_layer_state()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    current_state image_state;
BEGIN
    SELECT state
    INTO current_state
    FROM image_artifacts
    WHERE artifact_id = NEW.artifact_id;

    IF current_state <> 'available' THEN
        RAISE EXCEPTION
            'Layers cannot be added to unavailable artifacts';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_image_layer_state
BEFORE INSERT ON image_layers
FOR EACH ROW
EXECUTE FUNCTION validate_image_layer_state();

-- ============================================================
-- 8. ACCESS-CONTROL FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION check_repository_access(
    p_user_id BIGINT,
    p_repository_id BIGINT,
    p_operation registry_operation
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    repository_private BOOLEAN;
    repository_enabled BOOLEAN;
    registry_enabled BOOLEAN;
    user_active BOOLEAN;
    assigned_role access_role;
BEGIN
    SELECT
        r.is_private,
        r.enabled,
        g.enabled
    INTO
        repository_private,
        repository_enabled,
        registry_enabled
    FROM repositories r
    JOIN registries g
        ON g.registry_id = r.registry_id
    WHERE r.repository_id = p_repository_id;

    IF repository_private IS NULL THEN
        RETURN FALSE;
    END IF;

    SELECT active
    INTO user_active
    FROM registry_users
    WHERE user_id = p_user_id;

    IF NOT COALESCE(user_active, FALSE) THEN
        RETURN FALSE;
    END IF;

    IF NOT repository_enabled OR NOT registry_enabled THEN
        RETURN FALSE;
    END IF;

    SELECT role
    INTO assigned_role
    FROM repository_permissions
    WHERE user_id = p_user_id
      AND repository_id = p_repository_id;

    IF p_operation = 'pull' AND NOT repository_private THEN
        RETURN TRUE;
    END IF;

    RETURN CASE p_operation
        WHEN 'pull' THEN
            assigned_role IN ('reader', 'writer', 'admin')
        WHEN 'push' THEN
            assigned_role IN ('writer', 'admin')
        WHEN 'delete' THEN
            assigned_role = 'admin'
        WHEN 'admin' THEN
            assigned_role = 'admin'
        ELSE FALSE
    END;
END;
$$;

-- ============================================================
-- 9. IMAGE PUBLISHING FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION publish_image(
    p_user_id BIGINT,
    p_repository_id BIGINT,
    p_digest VARCHAR(71),
    p_config_digest VARCHAR(71),
    p_architecture VARCHAR(30),
    p_media_type TEXT,
    p_tag VARCHAR(128),
    p_verified BOOLEAN DEFAULT TRUE
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    new_artifact_id BIGINT;
    existing_tag RECORD;
    immutable_policy BOOLEAN;
BEGIN
    -- Serialize publication within the target repository.
    PERFORM 1
    FROM repositories
    WHERE repository_id = p_repository_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Repository not found';
    END IF;

    IF NOT check_repository_access(
        p_user_id,
        p_repository_id,
        'push'
    ) THEN
        RAISE EXCEPTION 'Push authorization denied';
    END IF;

    IF NOT p_verified THEN
        RAISE EXCEPTION 'Image verification required';
    END IF;

    IF p_digest !~ '^sha256:[a-f0-9]{64}$' OR
       p_config_digest !~ '^sha256:[a-f0-9]{64}$' THEN
        RAISE EXCEPTION 'Invalid SHA-256 digest';
    END IF;

    IF p_architecture NOT IN ('amd64', 'arm64', 'arm', '386') THEN
        RAISE EXCEPTION 'Unsupported architecture';
    END IF;

    IF p_tag !~ '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$' THEN
        RAISE EXCEPTION 'Invalid tag';
    END IF;

    SELECT immutable_tags
    INTO immutable_policy
    FROM repositories
    WHERE repository_id = p_repository_id;

    SELECT *
    INTO existing_tag
    FROM image_tags
    WHERE repository_id = p_repository_id
      AND tag_name = p_tag
    FOR UPDATE;

    IF FOUND THEN
        IF immutable_policy AND
           existing_tag.artifact_id IS DISTINCT FROM
           (
               SELECT artifact_id
               FROM image_artifacts
               WHERE repository_id = p_repository_id
                 AND manifest_digest = p_digest
           ) THEN
            RAISE EXCEPTION 'Immutable tag cannot be reassigned';
        END IF;

        IF existing_tag.is_protected THEN
            RAISE EXCEPTION 'Protected tag cannot be reassigned';
        END IF;
    END IF;

    INSERT INTO image_artifacts (
        repository_id,
        manifest_digest,
        config_digest,
        media_type,
        architecture,
        pushed_by
    )
    VALUES (
        p_repository_id,
        p_digest,
        p_config_digest,
        p_media_type,
        p_architecture,
        p_user_id
    )
    ON CONFLICT (repository_id, manifest_digest)
    DO NOTHING;

    SELECT artifact_id
    INTO new_artifact_id
    FROM image_artifacts
    WHERE repository_id = p_repository_id
      AND manifest_digest = p_digest;

    IF existing_tag.tag_id IS NOT NULL THEN
        UPDATE image_tags
        SET artifact_id = new_artifact_id
        WHERE tag_id = existing_tag.tag_id;
    ELSE
        INSERT INTO image_tags (
            repository_id,
            artifact_id,
            tag_name
        )
        VALUES (
            p_repository_id,
            new_artifact_id,
            p_tag
        );
    END IF;

    INSERT INTO registry_audit (
        registry_id,
        repository_id,
        user_id,
        operation,
        reference,
        outcome
    )
    SELECT
        registry_id,
        p_repository_id,
        p_user_id,
        'push',
        p_tag,
        'success'
    FROM repositories
    WHERE repository_id = p_repository_id;

    RETURN new_artifact_id;
END;
$$;

-- ============================================================
-- 10. IMAGE PULL FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION pull_image(
    p_user_id BIGINT,
    p_repository_id BIGINT,
    p_reference TEXT
)
RETURNS TABLE (
    artifact_id BIGINT,
    manifest_digest VARCHAR(71),
    architecture VARCHAR(30),
    total_size_bytes BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    resolved_artifact BIGINT;
    resolved_digest VARCHAR(71);
BEGIN
    IF NOT check_repository_access(
        p_user_id,
        p_repository_id,
        'pull'
    ) THEN
        RAISE EXCEPTION 'Pull authorization denied';
    END IF;

    SELECT
        a.artifact_id,
        a.manifest_digest
    INTO
        resolved_artifact,
        resolved_digest
    FROM image_artifacts a
    LEFT JOIN image_tags t
        ON t.artifact_id = a.artifact_id
    WHERE a.repository_id = p_repository_id
      AND (
          a.manifest_digest = p_reference OR
          t.tag_name = p_reference
      )
      AND a.state = 'available'
    ORDER BY a.artifact_id
    LIMIT 1;

    IF resolved_artifact IS NULL THEN
        RAISE EXCEPTION 'Image reference not found or unavailable';
    END IF;

    RETURN QUERY
    SELECT
        a.artifact_id,
        a.manifest_digest,
        a.architecture,
        COALESCE(
            SUM(l.layer_size_bytes),
            0
        )::BIGINT
    FROM image_artifacts a
    LEFT JOIN image_layers l
        ON l.artifact_id = a.artifact_id
    WHERE a.artifact_id = resolved_artifact
    GROUP BY
        a.artifact_id,
        a.manifest_digest,
        a.architecture;

    INSERT INTO image_distribution_events (
        artifact_id,
        user_id,
        event_type
    )
    VALUES (
        resolved_artifact,
        p_user_id,
        'pull_completed'
    );

    INSERT INTO registry_audit (
        registry_id,
        repository_id,
        user_id,
        operation,
        reference,
        outcome
    )
    SELECT
        registry_id,
        p_repository_id,
        p_user_id,
        'pull',
        p_reference,
        'success'
    FROM repositories
    WHERE repository_id = p_repository_id;
END;
$$;

-- ============================================================
-- 11. QUARANTINE FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION quarantine_image(
    p_user_id BIGINT,
    p_repository_id BIGINT,
    p_digest VARCHAR(71)
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT check_repository_access(
        p_user_id,
        p_repository_id,
        'admin'
    ) THEN
        RAISE EXCEPTION 'Administrative permission required';
    END IF;

    UPDATE image_artifacts
    SET state = 'quarantined'
    WHERE repository_id = p_repository_id
      AND manifest_digest = p_digest
      AND state = 'available';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Available artifact not found';
    END IF;

    RETURN TRUE;
END;
$$;

-- ============================================================
-- 12. GARBAGE COLLECTION PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE garbage_collect_repository(
    p_user_id BIGINT,
    p_repository_id BIGINT,
    INOUT p_removed_count INTEGER DEFAULT 0
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT check_repository_access(
        p_user_id,
        p_repository_id,
        'admin'
    ) THEN
        RAISE EXCEPTION 'Administrative permission required';
    END IF;

    WITH unreferenced AS (
        SELECT a.artifact_id
        FROM image_artifacts a
        WHERE a.repository_id = p_repository_id
          AND NOT EXISTS (
              SELECT 1
              FROM image_tags t
              WHERE t.artifact_id = a.artifact_id
          )
          AND a.state <> 'quarantined'
    ),
    removed AS (
        DELETE FROM image_artifacts a
        USING unreferenced u
        WHERE a.artifact_id = u.artifact_id
        RETURNING a.artifact_id
    )
    SELECT COUNT(*)::INTEGER
    INTO p_removed_count
    FROM removed;
END;
$$;

-- ============================================================
-- 13. REPORTING VIEWS
-- ============================================================

CREATE VIEW repository_inventory AS
SELECT
    r.repository_id,
    g.registry_name,
    r.repository_name,
    r.is_private,
    r.immutable_tags,
    COUNT(DISTINCT a.artifact_id) AS artifact_count,
    COUNT(DISTINCT t.tag_id) AS tag_count,
    COALESCE(SUM(DISTINCT a.manifest_size_bytes), 0)
        AS manifest_storage_bytes
FROM repositories r
JOIN registries g
    ON g.registry_id = r.registry_id
LEFT JOIN image_artifacts a
    ON a.repository_id = r.repository_id
LEFT JOIN image_tags t
    ON t.repository_id = r.repository_id
GROUP BY
    r.repository_id,
    g.registry_name,
    r.repository_name,
    r.is_private,
    r.immutable_tags;


CREATE VIEW image_distribution_report AS
SELECT
    a.artifact_id,
    r.repository_name,
    a.manifest_digest,
    a.architecture,
    a.state,
    COUNT(d.distribution_id) AS distribution_events,
    COALESCE(
        SUM(d.bytes_transferred),
        0
    ) AS bytes_transferred
FROM image_artifacts a
JOIN repositories r
    ON r.repository_id = a.repository_id
LEFT JOIN image_distribution_events d
    ON d.artifact_id = a.artifact_id
GROUP BY
    a.artifact_id,
    r.repository_name,
    a.manifest_digest,
    a.architecture,
    a.state;

-- ============================================================
-- 14. SAMPLE DATA
-- ============================================================

INSERT INTO registries (
    registry_name,
    endpoint
)
VALUES (
    'production-registry',
    'https://registry.example.internal'
);

INSERT INTO registry_users (
    username,
    credential_hash
)
VALUES
    (
        'registry_admin',
        repeat('a', 64)
    ),
    (
        'image_builder',
        repeat('b', 64)
    ),
    (
        'deployment_service',
        repeat('c', 64)
    ),
    (
        'external_user',
        repeat('d', 64)
    );

INSERT INTO repositories (
    registry_id,
    repository_name,
    is_private,
    immutable_tags
)
SELECT
    registry_id,
    'finance/payment-api',
    TRUE,
    FALSE
FROM registries
WHERE registry_name = 'production-registry';

INSERT INTO repositories (
    registry_id,
    repository_name,
    is_private,
    immutable_tags
)
SELECT
    registry_id,
    'public/base-images',
    FALSE,
    TRUE
FROM registries
WHERE registry_name = 'production-registry';

INSERT INTO repository_permissions (
    repository_id,
    user_id,
    role,
    granted_by
)
SELECT
    r.repository_id,
    u.user_id,
    CASE u.username
        WHEN 'registry_admin' THEN 'admin'::access_role
        WHEN 'image_builder' THEN 'writer'::access_role
        WHEN 'deployment_service' THEN 'reader'::access_role
    END,
    (
        SELECT user_id
        FROM registry_users
        WHERE username = 'registry_admin'
    )
FROM repositories r
CROSS JOIN registry_users u
WHERE r.repository_name = 'finance/payment-api'
  AND u.username IN (
      'registry_admin',
      'image_builder',
      'deployment_service'
  );

INSERT INTO repository_permissions (
    repository_id,
    user_id,
    role
)
SELECT
    r.repository_id,
    u.user_id,
    'admin'
FROM repositories r
CROSS JOIN registry_users u
WHERE r.repository_name = 'public/base-images'
  AND u.username = 'registry_admin';

-- ============================================================
-- 15. SAMPLE IMAGE PUBLICATION
-- ============================================================

SELECT publish_image(
    (
        SELECT user_id
        FROM registry_users
        WHERE username = 'image_builder'
    ),
    (
        SELECT repository_id
        FROM repositories
        WHERE repository_name = 'finance/payment-api'
    ),
    'sha256:' || repeat('1', 64),
    'sha256:' || repeat('2', 64),
    'amd64',
    'application/vnd.oci.image.manifest.v1+json',
    '1.0.0',
    TRUE
) AS published_artifact_id;

SELECT publish_image(
    (
        SELECT user_id
        FROM registry_users
        WHERE username = 'image_builder'
    ),
    (
        SELECT repository_id
        FROM repositories
        WHERE repository_name = 'finance/payment-api'
    ),
    'sha256:' || repeat('1', 64),
    'sha256:' || repeat('2', 64),
    'amd64',
    'application/vnd.oci.image.manifest.v1+json',
    'latest',
    TRUE
) AS latest_artifact_id;

-- Attach image layers to the published artifact.
INSERT INTO image_layers (
    artifact_id,
    layer_digest,
    layer_size_bytes,
    layer_order
)
SELECT
    artifact_id,
    'sha256:' || repeat('3', 64),
    10485760,
    0
FROM image_artifacts
WHERE manifest_digest = 'sha256:' || repeat('1', 64);

INSERT INTO image_layers (
    artifact_id,
    layer_digest,
    layer_size_bytes,
    layer_order
)
SELECT
    artifact_id,
    'sha256:' || repeat('4', 64),
    5242880,
    1
FROM image_artifacts
WHERE manifest_digest = 'sha256:' || repeat('1', 64);

-- Add semantic version metadata.
UPDATE image_tags
SET semantic_version = '1.0.0'
WHERE tag_name = '1.0.0';

-- Protect production deployment reference.
UPDATE image_tags
SET is_protected = TRUE
WHERE tag_name = 'latest'
  AND repository_id = (
      SELECT repository_id
      FROM repositories
      WHERE repository_name = 'finance/payment-api'
  );

-- ============================================================
-- 16. TRANSACTIONAL IMAGE DISTRIBUTION
-- ============================================================

SAVEPOINT before_deployment;

SELECT *
FROM pull_image(
    (
        SELECT user_id
        FROM registry_users
        WHERE username = 'deployment_service'
    ),
    (
        SELECT repository_id
        FROM repositories
        WHERE repository_name = 'finance/payment-api'
    ),
    'latest'
);

-- The successful pull and its audit records remain part of
-- the current transaction.

-- ============================================================
-- 17. VALIDATION AND ELIGIBILITY QUERIES
-- ============================================================

-- Repository inventory.
SELECT *
FROM repository_inventory
ORDER BY registry_name, repository_name;

-- Images available for deployment.
SELECT
    r.repository_name,
    t.tag_name,
    a.manifest_digest,
    a.architecture,
    a.state
FROM image_tags t
JOIN repositories r
    ON r.repository_id = t.repository_id
JOIN image_artifacts a
    ON a.artifact_id = t.artifact_id
WHERE a.state = 'available'
  AND r.enabled = TRUE
ORDER BY r.repository_name, t.tag_name;

-- Detect tags whose artifact is quarantined or unavailable.
SELECT
    r.repository_name,
    t.tag_name,
    a.manifest_digest,
    a.state
FROM image_tags t
JOIN repositories r
    ON r.repository_id = t.repository_id
JOIN image_artifacts a
    ON a.artifact_id = t.artifact_id
WHERE a.state <> 'available';

-- Validate that every available image has at least one layer.
SELECT
    a.artifact_id,
    a.manifest_digest,
    COUNT(l.layer_id) AS layer_count
FROM image_artifacts a
LEFT JOIN image_layers l
    ON l.artifact_id = a.artifact_id
WHERE a.state = 'available'
GROUP BY a.artifact_id, a.manifest_digest
HAVING COUNT(l.layer_id) = 0;

-- Evaluate user access to private and public repositories.
SELECT
    u.username,
    r.repository_name,
    r.is_private,
    check_repository_access(
        u.user_id,
        r.repository_id,
        'pull'
    ) AS can_pull,
    check_repository_access(
        u.user_id,
        r.repository_id,
        'push'
    ) AS can_push,
    check_repository_access(
        u.user_id,
        r.repository_id,
        'delete'
    ) AS can_delete
FROM registry_users u
CROSS JOIN repositories r
ORDER BY u.username, r.repository_name;

-- Image storage and layer analysis.
SELECT
    r.repository_name,
    COUNT(DISTINCT a.artifact_id) AS image_count,
    COUNT(l.layer_id) AS layer_count,
    COALESCE(SUM(l.layer_size_bytes), 0) AS total_layer_bytes
FROM repositories r
LEFT JOIN image_artifacts a
    ON a.repository_id = r.repository_id
LEFT JOIN image_layers l
    ON l.artifact_id = a.artifact_id
GROUP BY r.repository_name;

-- Distribution activity by image.
SELECT *
FROM image_distribution_report
ORDER BY distribution_events DESC;

-- Audit activity.
SELECT
    u.username,
    a.operation,
    a.reference,
    a.outcome,
    a.failure_reason,
    a.created_at
FROM registry_audit a
LEFT JOIN registry_users u
    ON u.user_id = a.user_id
ORDER BY a.created_at DESC;

-- ============================================================
-- 18. FAILURE-CASE DEMONSTRATION
-- ============================================================

-- A reader cannot publish images.
DO $$
DECLARE
    result BIGINT;
BEGIN
    BEGIN
        result := publish_image(
            (
                SELECT user_id
                FROM registry_users
                WHERE username = 'deployment_service'
            ),
            (
                SELECT repository_id
                FROM repositories
                WHERE repository_name = 'finance/payment-api'
            ),
            'sha256:' || repeat('5', 64),
            'sha256:' || repeat('6', 64),
            'amd64',
            'application/vnd.oci.image.manifest.v1+json',
            'unauthorized',
            TRUE
        );

    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'Expected publication rejection: %', SQLERRM;
    END;
END;
$$;

-- An unverified image cannot be published.
DO $$
DECLARE
    result BIGINT;
BEGIN
    BEGIN
        result := publish_image(
            (
                SELECT user_id
                FROM registry_users
                WHERE username = 'image_builder'
            ),
            (
                SELECT repository_id
                FROM repositories
                WHERE repository_name = 'finance/payment-api'
            ),
            'sha256:' || repeat('7', 64),
            'sha256:' || repeat('8', 64),
            'amd64',
            'application/vnd.oci.image.manifest.v1+json',
            'unverified',
            FALSE
        );

    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'Expected verification rejection: %', SQLERRM;
    END;
END;
$$;

-- Protected tags cannot be deleted.
DO $$
BEGIN
    BEGIN
        DELETE FROM image_tags
        WHERE tag_name = 'latest'
          AND repository_id = (
              SELECT repository_id
              FROM repositories
              WHERE repository_name = 'finance/payment-api'
          );

    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'Expected protected-tag rejection: %', SQLERRM;
    END;
END;
$$;

-- ============================================================
-- 19. GARBAGE COLLECTION
-- ============================================================

-- Garbage collection is restricted to repository administrators.
-- It deletes artifacts that are not referenced by any tag and are
-- not quarantined.

-- The initial sample has no unreferenced artifact.
-- Execute after removing an unprotected tag to test collection.

COMMIT;

-- ============================================================
-- 20. OPERATIONAL QUERIES
-- ============================================================

-- Run independently when maintenance is required:
--
-- CALL garbage_collect_repository(
--     (SELECT user_id FROM registry_users
--      WHERE username = 'registry_admin'),
--     (SELECT repository_id FROM repositories
--      WHERE repository_name = 'finance/payment-api'),
--     0
-- );
--
-- Repository inventory:
--
-- SELECT * FROM repository_inventory;
--
-- Distribution metrics:
--
-- SELECT * FROM image_distribution_report;
--
-- Registry activity:
--
-- SELECT operation, outcome, COUNT(*)
-- FROM registry_audit
-- GROUP BY operation, outcome
-- ORDER BY operation, outcome;
