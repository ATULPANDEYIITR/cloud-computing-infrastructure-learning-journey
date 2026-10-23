DROP SCHEMA IF EXISTS cdn_lab CASCADE;
CREATE SCHEMA cdn_lab;
SET search_path = cdn_lab, public;

-- The origin remains authoritative. Edge objects are deliberately modeled
-- separately so that cache state cannot silently replace source content.

CREATE TYPE content_class AS ENUM (
    'PUBLIC_STATIC',
    'PUBLIC_DYNAMIC',
    'PRIVATE'
);

CREATE TYPE cache_state AS ENUM (
    'FRESH',
    'STALE',
    'INVALIDATED'
);

CREATE TYPE deployment_state AS ENUM (
    'ACTIVE',
    'SUPERSEDED'
);

CREATE TABLE regions (
    region_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE
);

CREATE TABLE edge_locations (
    edge_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE,
    region_id bigint NOT NULL REFERENCES regions(region_id),
    capacity_objects integer NOT NULL CHECK (capacity_objects > 0),
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE origins (
    origin_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE,
    region_id bigint NOT NULL REFERENCES regions(region_id),
    base_url text NOT NULL UNIQUE
);

CREATE TABLE content_objects (
    content_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    origin_id bigint NOT NULL REFERENCES origins(origin_id),
    path text NOT NULL,
    content_class content_class NOT NULL,
    content_type text NOT NULL,
    body text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    etag text NOT NULL,
    state deployment_state NOT NULL DEFAULT 'ACTIVE',
    published_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (origin_id, path, version),
    UNIQUE (origin_id, path, etag),
    CHECK (path LIKE '/%'),
    CHECK (length(body) > 0)
);

CREATE UNIQUE INDEX one_active_content_per_path
ON content_objects(origin_id, path)
WHERE state = 'ACTIVE';

CREATE TABLE cache_entries (
    cache_entry_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    edge_id bigint NOT NULL REFERENCES edge_locations(edge_id),
    content_id bigint NOT NULL REFERENCES content_objects(content_id),
    path text NOT NULL,
    etag text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    state cache_state NOT NULL DEFAULT 'FRESH',
    cached_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL,
    last_accessed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    hit_count bigint NOT NULL DEFAULT 0 CHECK (hit_count >= 0),
    UNIQUE (edge_id, path)
);

CREATE INDEX cache_entries_expiry_idx
ON cache_entries(edge_id, expires_at);

CREATE INDEX cache_entries_content_idx
ON cache_entries(content_id);

CREATE TABLE requests (
    request_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    path text NOT NULL CHECK (path LIKE '/%'),
    client_region_id bigint NOT NULL REFERENCES regions(region_id),
    edge_id bigint REFERENCES edge_locations(edge_id),
    cache_status cache_state,
    source text NOT NULL CHECK (
        source IN ('EDGE', 'ORIGIN', 'BYPASS', 'NOT_FOUND')
    ),
    requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    latency_ms numeric(10,2) NOT NULL CHECK (latency_ms >= 0)
);

CREATE INDEX requests_path_time_idx
ON requests(path, requested_at DESC);

CREATE TABLE cache_invalidations (
    invalidation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    path_pattern text NOT NULL,
    edge_id bigint REFERENCES edge_locations(edge_id),
    reason text NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    affected_entries integer NOT NULL DEFAULT 0
        CHECK (affected_entries >= 0)
);

CREATE TABLE cache_policies (
    policy_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content_class content_class NOT NULL UNIQUE,
    cacheable boolean NOT NULL,
    ttl_seconds integer NOT NULL CHECK (ttl_seconds >= 0),
    stale_if_error_seconds integer NOT NULL DEFAULT 0
        CHECK (stale_if_error_seconds >= 0),
    require_versioned_path boolean NOT NULL DEFAULT false
);

INSERT INTO regions (name)
VALUES
    ('India'),
    ('Europe'),
    ('North America');

INSERT INTO edge_locations (
    name,
    region_id,
    capacity_objects
)
SELECT
    v.name,
    r.region_id,
    v.capacity
FROM (
    VALUES
        ('delhi-1', 'India', 1000),
        ('frankfurt-1', 'Europe', 1000),
        ('virginia-1', 'North America', 1000)
) AS v(name, region_name, capacity)
JOIN regions r ON r.name = v.region_name;

INSERT INTO origins (name, region_id, base_url)
SELECT
    'primary-origin',
    region_id,
    'https://origin.example.internal'
FROM regions
WHERE name = 'Europe';

INSERT INTO cache_policies (
    content_class,
    cacheable,
    ttl_seconds,
    stale_if_error_seconds,
    require_versioned_path
)
VALUES
    ('PUBLIC_STATIC', true, 3600, 300, true),
    ('PUBLIC_DYNAMIC', true, 30, 0, false),
    ('PRIVATE', false, 0, 0, false);

-- Publishing a new version automatically supersedes the previous active
-- version. The partial unique index guarantees one authoritative active
-- object for a path.
CREATE OR REPLACE FUNCTION publish_content(
    p_origin_id bigint,
    p_path text,
    p_body text,
    p_content_type text,
    p_content_class content_class
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    next_version integer;
    new_id bigint;
    new_etag text;
BEGIN
    IF p_path IS NULL OR p_path NOT LIKE '/%' THEN
        RAISE EXCEPTION 'Content path must begin with /';
    END IF;

    IF p_body IS NULL OR length(p_body) = 0 THEN
        RAISE EXCEPTION 'Content body cannot be empty';
    END IF;

    SELECT COALESCE(MAX(version), 0) + 1
    INTO next_version
    FROM content_objects
    WHERE origin_id = p_origin_id
      AND path = p_path;

    UPDATE content_objects
    SET state = 'SUPERSEDED'
    WHERE origin_id = p_origin_id
      AND path = p_path
      AND state = 'ACTIVE';

    new_etag :=
        '"' ||
        md5(
            p_path ||
            ':' ||
            next_version::text ||
            ':' ||
            p_body
        ) ||
        '"';

    INSERT INTO content_objects (
        origin_id,
        path,
        content_class,
        content_type,
        body,
        version,
        etag
    )
    VALUES (
        p_origin_id,
        p_path,
        p_content_class,
        p_content_type,
        p_body,
        next_version,
        new_etag
    )
    RETURNING content_id INTO new_id;

    RETURN new_id;
END;
$$;

-- A cache hit updates access metadata. A stale object is never treated as
-- fresh merely because the row still exists.
CREATE OR REPLACE FUNCTION cache_lookup(
    p_edge_id bigint,
    p_path text
)
RETURNS TABLE (
    result_status cache_state,
    result_etag text,
    result_version integer,
    result_content_id bigint
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        CASE
            WHEN ce.state = 'INVALIDATED'
                THEN 'INVALIDATED'::cache_state
            WHEN ce.expires_at <= clock_timestamp()
                THEN 'STALE'::cache_state
            ELSE 'FRESH'::cache_state
        END,
        ce.etag,
        ce.version,
        ce.content_id
    FROM cache_entries ce
    WHERE ce.edge_id = p_edge_id
      AND ce.path = p_path;

    UPDATE cache_entries
    SET
        hit_count = hit_count + 1,
        last_accessed_at = clock_timestamp()
    WHERE edge_id = p_edge_id
      AND path = p_path
      AND state = 'FRESH'
      AND expires_at > clock_timestamp();
END;
$$;

-- Invalidation is represented as an explicit transaction so all edge copies
-- can be removed consistently.
CREATE OR REPLACE FUNCTION invalidate_path(
    p_path text,
    p_reason text
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    affected integer;
BEGIN
    IF p_path IS NULL OR p_path NOT LIKE '/%' THEN
        RAISE EXCEPTION 'Invalid invalidation path';
    END IF;

    UPDATE cache_entries
    SET state = 'INVALIDATED'
    WHERE path = p_path
      AND state <> 'INVALIDATED';

    GET DIAGNOSTICS affected = ROW_COUNT;

    INSERT INTO cache_invalidations (
        path_pattern,
        reason,
        affected_entries
    )
    VALUES (
        p_path,
        p_reason,
        affected
    );

    RETURN affected;
END;
$$;

CREATE OR REPLACE FUNCTION invalidate_prefix(
    p_prefix text,
    p_reason text
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    affected integer;
BEGIN
    IF p_prefix IS NULL OR p_prefix NOT LIKE '/%' THEN
        RAISE EXCEPTION 'Invalid invalidation prefix';
    END IF;

    UPDATE cache_entries
    SET state = 'INVALIDATED'
    WHERE path LIKE p_prefix || '%'
      AND state <> 'INVALIDATED';

    GET DIAGNOSTICS affected = ROW_COUNT;

    INSERT INTO cache_invalidations (
        path_pattern,
        reason,
        affected_entries
    )
    VALUES (
        p_prefix || '%',
        p_reason,
        affected
    );

    RETURN affected;
END;
$$;

CREATE VIEW active_origin_content AS
SELECT
    c.content_id,
    c.path,
    c.content_class,
    c.content_type,
    c.body,
    c.version,
    c.etag,
    c.published_at,
    o.name AS origin_name,
    r.name AS origin_region
FROM content_objects c
JOIN origins o
    ON o.origin_id = c.origin_id
JOIN regions r
    ON r.region_id = o.region_id
WHERE c.state = 'ACTIVE';

CREATE VIEW cache_health AS
SELECT
    e.name AS edge_name,
    r.name AS region,
    COUNT(ce.cache_entry_id) AS entries,
    COUNT(*) FILTER (
        WHERE ce.state = 'FRESH'
          AND ce.expires_at > clock_timestamp()
    ) AS fresh_entries,
    COUNT(*) FILTER (
        WHERE ce.state = 'STALE'
           OR ce.expires_at <= clock_timestamp()
    ) AS stale_entries,
    COUNT(*) FILTER (
        WHERE ce.state = 'INVALIDATED'
    ) AS invalidated_entries,
    COALESCE(SUM(ce.hit_count), 0) AS cache_hits
FROM edge_locations e
JOIN regions r
    ON r.region_id = e.region_id
LEFT JOIN cache_entries ce
    ON ce.edge_id = e.edge_id
GROUP BY e.name, r.name;

-- Publish realistic public assets.
SELECT publish_content(
    (SELECT origin_id FROM origins WHERE name = 'primary-origin'),
    '/assets/app.a91f42d7.js',
    'release-1',
    'application/javascript',
    'PUBLIC_STATIC'
);

SELECT publish_content(
    (SELECT origin_id FROM origins WHERE name = 'primary-origin'),
    '/images/logo.52ab11ef.svg',
    '<svg><title>CDN</title></svg>',
    'image/svg+xml',
    'PUBLIC_STATIC'
);

SELECT publish_content(
    (SELECT origin_id FROM origins WHERE name = 'primary-origin'),
    '/api/config',
    '{"release":"2026.10","region":"global"}',
    'application/json',
    'PUBLIC_DYNAMIC'
);

-- Seed edge copies to represent normal cache fill after origin requests.
INSERT INTO cache_entries (
    edge_id,
    content_id,
    path,
    etag,
    version,
    expires_at
)
SELECT
    e.edge_id,
    c.content_id,
    c.path,
    c.etag,
    c.version,
    clock_timestamp() +
        CASE
            WHEN c.content_class = 'PUBLIC_STATIC'
                THEN interval '1 hour'
            ELSE interval '30 seconds'
        END
FROM edge_locations e
CROSS JOIN active_origin_content c
WHERE c.path IN (
    '/assets/app.a91f42d7.js',
    '/images/logo.52ab11ef.svg'
);

-- Simulate edge requests from multiple geographic regions.
INSERT INTO requests (
    path,
    client_region_id,
    edge_id,
    cache_status,
    source,
    latency_ms
)
VALUES
(
    '/assets/app.a91f42d7.js',
    (SELECT region_id FROM regions WHERE name = 'India'),
    (SELECT edge_id FROM edge_locations WHERE name = 'delhi-1'),
    'FRESH',
    'EDGE',
    20
),
(
    '/assets/app.a91f42d7.js',
    (SELECT region_id FROM regions WHERE name = 'Europe'),
    (SELECT edge_id FROM edge_locations WHERE name = 'frankfurt-1'),
    'FRESH',
    'EDGE',
    25
),
(
    '/images/logo.52ab11ef.svg',
    (SELECT region_id FROM regions WHERE name = 'North America'),
    (SELECT edge_id FROM edge_locations WHERE name = 'virginia-1'),
    'FRESH',
    'EDGE',
    25
),
(
    '/api/config',
    (SELECT region_id FROM regions WHERE name = 'India'),
    (SELECT edge_id FROM edge_locations WHERE name = 'delhi-1'),
    'STALE',
    'ORIGIN',
    100
);

-- Publish a new application version. Existing edge copies intentionally still
-- reference the previous content version until TTL expiration or invalidation.
BEGIN;

SELECT publish_content(
    (SELECT origin_id FROM origins WHERE name = 'primary-origin'),
    '/assets/app.a91f42d7.js',
    'release-2',
    'application/javascript',
    'PUBLIC_STATIC'
);

SELECT invalidate_path(
    '/assets/app.a91f42d7.js',
    'application deployment'
);

COMMIT;

-- Conditional validation can use the ETag without transferring a full body.
SELECT
    c.path,
    c.version,
    c.etag,
    CASE
        WHEN c.etag = '"invalid-client-etag"'
            THEN 'MODIFIED'
        ELSE 'NOT_MODIFIED'
    END AS validator_result
FROM active_origin_content c
WHERE c.path = '/assets/app.a91f42d7.js';

-- Prefix invalidation is useful after a deployment that changes a complete
-- asset namespace, but broad invalidation can create an origin traffic spike.
BEGIN;

SELECT invalidate_prefix(
    '/images/',
    'image deployment'
);

COMMIT;

-- Cache health by edge.
SELECT *
FROM cache_health
ORDER BY region, edge_name;

-- Origin content currently authoritative for each path.
SELECT
    path,
    content_class,
    version,
    etag,
    origin_region,
    published_at
FROM active_origin_content
ORDER BY path;

-- Hit-rate reporting by edge.
SELECT
    e.name AS edge_name,
    COUNT(r.request_id) AS requests,
    COUNT(*) FILTER (WHERE r.source = 'EDGE') AS edge_hits,
    COUNT(*) FILTER (WHERE r.source = 'ORIGIN') AS origin_requests,
    ROUND(
        100.0 *
        COUNT(*) FILTER (WHERE r.source = 'EDGE') /
        NULLIF(COUNT(r.request_id), 0),
        2
    ) AS hit_rate_percent,
    ROUND(AVG(r.latency_ms), 2) AS average_latency_ms
FROM edge_locations e
LEFT JOIN requests r
    ON r.edge_id = e.edge_id
GROUP BY e.name
ORDER BY e.name;

-- Identify cache entries whose stored version no longer matches the active
-- origin version. These are candidates for invalidation or natural expiry.
SELECT
    ce.edge_id,
    e.name AS edge_name,
    ce.path,
    ce.version AS cached_version,
    active.version AS origin_version,
    ce.state,
    ce.expires_at
FROM cache_entries ce
JOIN edge_locations e
    ON e.edge_id = ce.edge_id
JOIN active_origin_content active
    ON active.path = ce.path
WHERE ce.version <> active.version;

-- Show invalidation impact.
SELECT
    invalidation_id,
    path_pattern,
    reason,
    affected_entries,
    requested_at
FROM cache_invalidations
ORDER BY requested_at DESC;
