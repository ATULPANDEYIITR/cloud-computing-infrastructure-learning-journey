DROP SCHEMA IF EXISTS cache_infrastructure CASCADE;
CREATE SCHEMA cache_infrastructure;

SET search_path TO cache_infrastructure, public;

CREATE TYPE cache_strategy AS ENUM (
    'cache_aside',
    'write_through'
);

CREATE TYPE cache_layer AS ENUM (
    'local',
    'distributed'
);

CREATE TYPE cache_event_type AS ENUM (
    'populate',
    'hit',
    'miss',
    'invalidate',
    'stale_rejected',
    'write'
);

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    owner_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE branches (
    branch_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    branch_name TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (repository_id, branch_name)
);

CREATE TABLE products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_name TEXT NOT NULL,
    price NUMERIC(14,2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    version BIGINT NOT NULL DEFAULT 1 CHECK (version > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cache_nodes (
    cache_node_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_name TEXT NOT NULL UNIQUE,
    cache_layer cache_layer NOT NULL,
    available BOOLEAN NOT NULL DEFAULT TRUE,
    capacity_entries INTEGER NOT NULL
        CHECK (capacity_entries > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cache_entries (
    cache_entry_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cache_node_id BIGINT NOT NULL
        REFERENCES cache_nodes(cache_node_id)
        ON DELETE CASCADE,
    product_id BIGINT NOT NULL
        REFERENCES products(product_id)
        ON DELETE CASCADE,
    cache_key TEXT NOT NULL,
    cached_version BIGINT NOT NULL CHECK (cached_version > 0),
    cached_price NUMERIC(14,2) NOT NULL CHECK (cached_price >= 0),
    cached_stock INTEGER NOT NULL CHECK (cached_stock >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ,
    UNIQUE (cache_node_id, cache_key),
    CHECK (expires_at IS NULL OR expires_at > created_at)
);

CREATE TABLE cache_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cache_node_id BIGINT
        REFERENCES cache_nodes(cache_node_id)
        ON DELETE SET NULL,
    product_id BIGINT
        REFERENCES products(product_id)
        ON DELETE SET NULL,
    cache_key TEXT NOT NULL,
    event_type cache_event_type NOT NULL,
    event_version BIGINT,
    event_detail TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cache_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    policy_name TEXT NOT NULL UNIQUE,
    strategy cache_strategy NOT NULL,
    local_ttl_seconds INTEGER NOT NULL
        CHECK (local_ttl_seconds > 0),
    distributed_ttl_seconds INTEGER NOT NULL
        CHECK (distributed_ttl_seconds >= local_ttl_seconds),
    reject_stale_versions BOOLEAN NOT NULL DEFAULT TRUE,
    invalidate_on_update BOOLEAN NOT NULL DEFAULT TRUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_cache_entries_product
    ON cache_entries(product_id);

CREATE INDEX idx_cache_entries_expiry
    ON cache_entries(expires_at);

CREATE INDEX idx_cache_events_product_time
    ON cache_events(product_id, occurred_at DESC);

CREATE INDEX idx_cache_events_type_time
    ON cache_events(event_type, occurred_at DESC);

CREATE OR REPLACE FUNCTION set_product_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    NEW.version := OLD.version + 1;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_product_version
BEFORE UPDATE ON products
FOR EACH ROW
EXECUTE FUNCTION set_product_updated_at();

CREATE OR REPLACE FUNCTION reject_stale_cache_entry()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    authoritative_version BIGINT;
BEGIN
    SELECT version
    INTO authoritative_version
    FROM products
    WHERE product_id = NEW.product_id;

    IF authoritative_version IS NULL THEN
        RAISE EXCEPTION
            'Cannot cache missing product %',
            NEW.product_id;
    END IF;

    IF NEW.cached_version < authoritative_version THEN
        RAISE EXCEPTION
            'Stale cache entry: product %, cache version %, authoritative version %',
            NEW.product_id,
            NEW.cached_version,
            authoritative_version;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_reject_stale_cache_entry
BEFORE INSERT OR UPDATE ON cache_entries
FOR EACH ROW
EXECUTE FUNCTION reject_stale_cache_entry();

CREATE OR REPLACE FUNCTION cache_key_for_product(p_product_id BIGINT)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT 'product:' || p_product_id::TEXT;
$$;

CREATE OR REPLACE FUNCTION invalidate_product_cache(
    p_product_id BIGINT
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM cache_entries
    WHERE product_id = p_product_id;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    INSERT INTO cache_events (
        product_id,
        cache_key,
        event_type,
        event_detail
    )
    VALUES (
        p_product_id,
        cache_key_for_product(p_product_id),
        'invalidate',
        'All cache layers invalidated after authoritative update'
    );

    RETURN deleted_count;
END;
$$;

CREATE OR REPLACE FUNCTION cache_aside_update_product(
    p_product_id BIGINT,
    p_price NUMERIC,
    p_stock INTEGER
)
RETURNS products
LANGUAGE plpgsql
AS $$
DECLARE
    updated_product products;
BEGIN
    IF p_price < 0 THEN
        RAISE EXCEPTION 'price cannot be negative';
    END IF;

    IF p_stock < 0 THEN
        RAISE EXCEPTION 'stock cannot be negative';
    END IF;

    UPDATE products
    SET price = p_price,
        stock = p_stock
    WHERE product_id = p_product_id
    RETURNING * INTO updated_product;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Product % does not exist',
            p_product_id;
    END IF;

    PERFORM invalidate_product_cache(p_product_id);

    INSERT INTO cache_events (
        product_id,
        cache_key,
        event_type,
        event_version,
        event_detail
    )
    VALUES (
        p_product_id,
        cache_key_for_product(p_product_id),
        'write',
        updated_product.version,
        'Cache-aside database update followed by invalidation'
    );

    RETURN updated_product;
END;
$$;

CREATE OR REPLACE PROCEDURE write_through_product(
    p_product_id BIGINT,
    p_price NUMERIC,
    p_stock INTEGER,
    p_local_node BIGINT,
    p_distributed_node BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    updated_product products;
    local_ttl INTEGER;
    distributed_ttl INTEGER;
    cache_key TEXT;
BEGIN
    SELECT local_ttl_seconds, distributed_ttl_seconds
    INTO local_ttl, distributed_ttl
    FROM cache_policies
    WHERE strategy = 'write_through'
      AND enabled = TRUE
    ORDER BY policy_id
    LIMIT 1;

    IF local_ttl IS NULL THEN
        RAISE EXCEPTION
            'No enabled write-through policy exists';
    END IF;

    IF p_price < 0 OR p_stock < 0 THEN
        RAISE EXCEPTION
            'Invalid product values';
    END IF;

    UPDATE products
    SET price = p_price,
        stock = p_stock
    WHERE product_id = p_product_id
    RETURNING * INTO updated_product;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Product % does not exist',
            p_product_id;
    END IF;

    cache_key := cache_key_for_product(p_product_id);

    INSERT INTO cache_entries (
        cache_node_id,
        product_id,
        cache_key,
        cached_version,
        cached_price,
        cached_stock,
        expires_at
    )
    VALUES (
        p_local_node,
        p_product_id,
        cache_key,
        updated_product.version,
        updated_product.price,
        updated_product.stock,
        CURRENT_TIMESTAMP
            + make_interval(secs => local_ttl)
    )
    ON CONFLICT (cache_node_id, cache_key)
    DO UPDATE SET
        product_id = EXCLUDED.product_id,
        cached_version = EXCLUDED.cached_version,
        cached_price = EXCLUDED.cached_price,
        cached_stock = EXCLUDED.cached_stock,
        created_at = CURRENT_TIMESTAMP,
        expires_at = EXCLUDED.expires_at;

    INSERT INTO cache_entries (
        cache_node_id,
        product_id,
        cache_key,
        cached_version,
        cached_price,
        cached_stock,
        expires_at
    )
    VALUES (
        p_distributed_node,
        p_product_id,
        cache_key,
        updated_product.version,
        updated_product.price,
        updated_product.stock,
        CURRENT_TIMESTAMP
            + make_interval(secs => distributed_ttl)
    )
    ON CONFLICT (cache_node_id, cache_key)
    DO UPDATE SET
        product_id = EXCLUDED.product_id,
        cached_version = EXCLUDED.cached_version,
        cached_price = EXCLUDED.cached_price,
        cached_stock = EXCLUDED.cached_stock,
        created_at = CURRENT_TIMESTAMP,
        expires_at = EXCLUDED.expires_at;

    INSERT INTO cache_events (
        product_id,
        cache_key,
        event_type,
        event_version,
        event_detail
    )
    VALUES (
        p_product_id,
        cache_key,
        'write',
        updated_product.version,
        'Write-through update refreshed both cache layers'
    );
END;
$$;

CREATE OR REPLACE VIEW active_cache_entries AS
SELECT
    ce.cache_entry_id,
    cn.node_name,
    cn.cache_layer,
    p.product_id,
    p.product_name,
    ce.cached_version,
    p.version AS authoritative_version,
    ce.cached_price,
    ce.cached_stock,
    ce.expires_at,
    ce.expires_at > CURRENT_TIMESTAMP AS is_fresh
FROM cache_entries ce
JOIN cache_nodes cn
    ON cn.cache_node_id = ce.cache_node_id
JOIN products p
    ON p.product_id = ce.product_id
WHERE cn.available = TRUE;

CREATE OR REPLACE VIEW cache_health_report AS
SELECT
    cn.node_name,
    cn.cache_layer,
    cn.available,
    COUNT(ce.cache_entry_id) AS entries,
    COUNT(*) FILTER (
        WHERE ce.expires_at <= CURRENT_TIMESTAMP
    ) AS expired_entries,
    COUNT(*) FILTER (
        WHERE ce.cached_version < p.version
    ) AS stale_entries
FROM cache_nodes cn
LEFT JOIN cache_entries ce
    ON ce.cache_node_id = cn.cache_node_id
LEFT JOIN products p
    ON p.product_id = ce.product_id
GROUP BY
    cn.node_name,
    cn.cache_layer,
    cn.available;

INSERT INTO repositories (
    repository_name,
    owner_name
)
VALUES (
    'enterprise-cache-platform',
    'platform-engineering'
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
WHERE repository_name = 'enterprise-cache-platform';

INSERT INTO branches (
    repository_id,
    branch_name,
    is_default,
    protected
)
SELECT
    repository_id,
    'feature/cache-versioning',
    FALSE,
    FALSE
FROM repositories
WHERE repository_name = 'enterprise-cache-platform';

INSERT INTO products (
    product_name,
    price,
    stock
)
VALUES
    ('API Gateway', 75000.00, 10),
    ('Distributed Session Store', 115000.00, 6),
    ('Event Processing Cluster', 160000.00, 4);

INSERT INTO cache_nodes (
    node_name,
    cache_layer,
    capacity_entries
)
VALUES
    ('application-node-01', 'local', 500),
    ('redis-cluster-primary', 'distributed', 50000);

INSERT INTO cache_policies (
    policy_name,
    strategy,
    local_ttl_seconds,
    distributed_ttl_seconds,
    reject_stale_versions,
    invalidate_on_update
)
VALUES
    (
        'product-cache-aside',
        'cache_aside',
        30,
        120,
        TRUE,
        TRUE
    ),
    (
        'product-write-through',
        'write_through',
        30,
        120,
        TRUE,
        TRUE
    );

INSERT INTO cache_entries (
    cache_node_id,
    product_id,
    cache_key,
    cached_version,
    cached_price,
    cached_stock,
    expires_at
)
SELECT
    cn.cache_node_id,
    p.product_id,
    cache_key_for_product(p.product_id),
    p.version,
    p.price,
    p.stock,
    CURRENT_TIMESTAMP + INTERVAL '30 seconds'
FROM cache_nodes cn
CROSS JOIN products p
WHERE cn.node_name = 'application-node-01'
  AND p.product_name = 'API Gateway';

INSERT INTO cache_events (
    cache_node_id,
    product_id,
    cache_key,
    event_type,
    event_version,
    event_detail
)
SELECT
    cn.cache_node_id,
    p.product_id,
    cache_key_for_product(p.product_id),
    'populate',
    p.version,
    'Initial local cache population'
FROM cache_nodes cn
CROSS JOIN products p
WHERE cn.node_name = 'application-node-01'
  AND p.product_name = 'API Gateway';

BEGIN;

SELECT cache_aside_update_product(
    (
        SELECT product_id
        FROM products
        WHERE product_name = 'API Gateway'
    ),
    73500.00,
    12
);

COMMIT;

BEGIN;

CALL write_through_product(
    (
        SELECT product_id
        FROM products
        WHERE product_name = 'Distributed Session Store'
    ),
    112500.00,
    5,
    (
        SELECT cache_node_id
        FROM cache_nodes
        WHERE node_name = 'application-node-01'
    ),
    (
        SELECT cache_node_id
        FROM cache_nodes
        WHERE node_name = 'redis-cluster-primary'
    )
);

COMMIT;

-- Retrieval: authoritative state and cached state.
SELECT
    p.product_id,
    p.product_name,
    p.price,
    p.stock,
    p.version
FROM products p
ORDER BY p.product_id;

SELECT *
FROM active_cache_entries
ORDER BY product_id, cache_layer;

-- Validation: cached versions must not be behind authoritative versions.
SELECT
    product_id,
    COUNT(*) AS stale_entry_count
FROM active_cache_entries
WHERE cached_version < authoritative_version
GROUP BY product_id;

-- Aggregation: cache activity by event type.
SELECT
    event_type,
    COUNT(*) AS event_count,
    MAX(occurred_at) AS last_event
FROM cache_events
GROUP BY event_type
ORDER BY event_count DESC;

-- Evaluation: determine which cached records are currently eligible.
WITH candidates AS (
    SELECT
        cache_entry_id,
        node_name,
        product_id,
        cached_version,
        authoritative_version,
        expires_at,
        is_fresh
    FROM active_cache_entries
)
SELECT
    cache_entry_id,
    node_name,
    product_id,
    CASE
        WHEN NOT is_fresh THEN 'EXPIRED'
        WHEN cached_version < authoritative_version THEN 'STALE'
        WHEN cached_version = authoritative_version THEN 'ELIGIBLE'
        ELSE 'FUTURE_VERSION'
    END AS eligibility
FROM candidates
ORDER BY product_id, node_name;

-- Workflow state: cache nodes and operational availability.
SELECT
    node_name,
    cache_layer,
    available,
    entries,
    expired_entries,
    stale_entries
FROM cache_health_report
ORDER BY cache_layer, node_name;

-- Policy comparison.
SELECT
    policy_name,
    strategy,
    local_ttl_seconds,
    distributed_ttl_seconds,
    reject_stale_versions,
    invalidate_on_update,
    enabled
FROM cache_policies
ORDER BY policy_id;

-- Failure-oriented query: cache misses and stale rejections.
SELECT
    event_type,
    COUNT(*) AS occurrences
FROM cache_events
WHERE event_type IN ('miss', 'stale_rejected')
GROUP BY event_type
ORDER BY event_type;

-- Transactional rollback demonstration. The update is intentionally invalid,
-- so no durable state change is retained.
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM products
        WHERE product_id = 1
    ) THEN
        UPDATE products
        SET stock = -1
        WHERE product_id = 1;
    END IF;
EXCEPTION
    WHEN check_violation THEN
        RAISE NOTICE
            'Invalid stock update rejected by database constraint';
END;
$$;

ROLLBACK;
