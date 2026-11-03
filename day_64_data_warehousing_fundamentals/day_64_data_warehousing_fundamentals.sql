DROP SCHEMA IF EXISTS warehouse_demo CASCADE;

CREATE SCHEMA warehouse_demo;

SET search_path TO warehouse_demo;

CREATE TYPE load_strategy AS ENUM ('ETL', 'ELT');
CREATE TYPE pipeline_state AS ENUM (
    'CREATED',
    'EXTRACTED',
    'VALIDATED',
    'TRANSFORMED',
    'LOADED',
    'FAILED'
);

CREATE TABLE source_customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name TEXT NOT NULL,
    segment TEXT NOT NULL
        CHECK (segment IN ('Consumer', 'Business', 'Enterprise')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE source_products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit_price NUMERIC(12,2) NOT NULL
        CHECK (unit_price >= 0),
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE source_orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES source_customers(customer_id),
    product_id BIGINT NOT NULL
        REFERENCES source_products(product_id),
    order_date DATE NOT NULL,
    region TEXT NOT NULL
        CHECK (btrim(region) <> ''),
    quantity INTEGER NOT NULL
        CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL
        CHECK (unit_price >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_source_orders_date
    ON source_orders (order_date);

CREATE INDEX idx_source_orders_customer
    ON source_orders (customer_id);

CREATE INDEX idx_source_orders_product
    ON source_orders (product_id);

CREATE INDEX idx_source_orders_region_date
    ON source_orders (region, order_date);

CREATE TABLE pipeline_runs (
    pipeline_run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    strategy load_strategy NOT NULL,
    state pipeline_state NOT NULL DEFAULT 'CREATED',
    extracted_rows INTEGER NOT NULL DEFAULT 0
        CHECK (extracted_rows >= 0),
    rejected_rows INTEGER NOT NULL DEFAULT 0
        CHECK (rejected_rows >= 0),
    loaded_rows INTEGER NOT NULL DEFAULT 0
        CHECK (loaded_rows >= 0),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ
);

CREATE TABLE pipeline_rejections (
    rejection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_run_id BIGINT NOT NULL
        REFERENCES pipeline_runs(pipeline_run_id),
    order_id BIGINT,
    rejection_reason TEXT NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,
    calendar_date DATE NOT NULL UNIQUE,
    calendar_year INTEGER NOT NULL,
    calendar_month INTEGER NOT NULL
        CHECK (calendar_month BETWEEN 1 AND 12),
    calendar_quarter INTEGER NOT NULL
        CHECK (calendar_quarter BETWEEN 1 AND 4)
);

CREATE TABLE dim_customer (
    customer_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_customer_id BIGINT NOT NULL UNIQUE,
    customer_name TEXT NOT NULL,
    segment TEXT NOT NULL
);

CREATE TABLE dim_product (
    product_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_product_id BIGINT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL
);

CREATE TABLE fact_sales (
    sales_fact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL UNIQUE,
    date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    customer_key BIGINT NOT NULL
        REFERENCES dim_customer(customer_key),
    product_key BIGINT NOT NULL
        REFERENCES dim_product(product_key),
    region TEXT NOT NULL,
    quantity INTEGER NOT NULL
        CHECK (quantity > 0),
    revenue NUMERIC(14,2) NOT NULL
        CHECK (revenue >= 0),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_fact_sales_date
    ON fact_sales (date_key);

CREATE INDEX idx_fact_sales_customer
    ON fact_sales (customer_key);

CREATE INDEX idx_fact_sales_product
    ON fact_sales (product_key);

CREATE INDEX idx_fact_sales_region_date
    ON fact_sales (region, date_key);

CREATE OR REPLACE FUNCTION populate_date_dimension()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO dim_date (
        date_key,
        calendar_date,
        calendar_year,
        calendar_month,
        calendar_quarter
    )
    VALUES (
        TO_CHAR(NEW.order_date, 'YYYYMMDD')::INTEGER,
        NEW.order_date,
        EXTRACT(YEAR FROM NEW.order_date)::INTEGER,
        EXTRACT(MONTH FROM NEW.order_date)::INTEGER,
        EXTRACT(QUARTER FROM NEW.order_date)::INTEGER
    )
    ON CONFLICT (date_key) DO NOTHING;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_source_order_date_dimension
AFTER INSERT ON source_orders
FOR EACH ROW
EXECUTE FUNCTION populate_date_dimension();

CREATE OR REPLACE FUNCTION normalize_region()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.region := INITCAP(REGEXP_REPLACE(BTRIM(NEW.region), '\s+', ' ', 'g'));

    IF NEW.region = '' THEN
        RAISE EXCEPTION 'Region cannot be empty';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_normalize_region
BEFORE INSERT OR UPDATE ON source_orders
FOR EACH ROW
EXECUTE FUNCTION normalize_region();

INSERT INTO source_customers (customer_name, segment)
VALUES
    ('Alpha Retail', 'Business'),
    ('Beta Manufacturing', 'Enterprise'),
    ('Gamma Services', 'Business'),
    ('Delta Stores', 'Consumer');

INSERT INTO source_products (product_name, category, unit_price)
VALUES
    ('Analytics Server', 'Infrastructure', 450.00),
    ('Storage Node', 'Infrastructure', 250.00),
    ('ETL Connector', 'Software', 120.00),
    ('BI License', 'Software', 300.00);

INSERT INTO source_orders (
    customer_id,
    product_id,
    order_date,
    region,
    quantity,
    unit_price
)
VALUES
    (1, 3, DATE '2026-01-10', 'north', 5, 120.00),
    (2, 2, DATE '2026-01-15', 'South', 3, 250.00),
    (1, 3, DATE '2026-02-03', 'north', 7, 120.00),
    (3, 1, DATE '2026-02-19', 'West', 2, 450.00),
    (4, 2, DATE '2026-03-04', 'east', 4, 250.00);

INSERT INTO pipeline_runs (
    strategy,
    state,
    extracted_rows,
    rejected_rows,
    loaded_rows,
    completed_at
)
VALUES (
    'ETL',
    'LOADED',
    5,
    0,
    5,
    CURRENT_TIMESTAMP
);

INSERT INTO dim_customer (
    source_customer_id,
    customer_name,
    segment
)
SELECT
    customer_id,
    customer_name,
    segment
FROM source_customers
ON CONFLICT (source_customer_id)
DO UPDATE SET
    customer_name = EXCLUDED.customer_name,
    segment = EXCLUDED.segment;

INSERT INTO dim_product (
    source_product_id,
    product_name,
    category
)
SELECT
    product_id,
    product_name,
    category
FROM source_products
ON CONFLICT (source_product_id)
DO UPDATE SET
    product_name = EXCLUDED.product_name,
    category = EXCLUDED.category;

INSERT INTO fact_sales (
    order_id,
    date_key,
    customer_key,
    product_key,
    region,
    quantity,
    revenue
)
SELECT
    o.order_id,
    TO_CHAR(o.order_date, 'YYYYMMDD')::INTEGER,
    c.customer_key,
    p.product_key,
    o.region,
    o.quantity,
    ROUND(o.quantity * o.unit_price, 2)
FROM source_orders o
JOIN dim_customer c
    ON c.source_customer_id = o.customer_id
JOIN dim_product p
    ON p.source_product_id = o.product_id
ON CONFLICT (order_id) DO NOTHING;

CREATE OR REPLACE VIEW sales_analytics AS
SELECT
    f.sales_fact_id,
    f.order_id,
    d.calendar_date,
    d.calendar_year,
    d.calendar_month,
    d.calendar_quarter,
    c.customer_name,
    c.segment,
    p.product_name,
    p.category,
    f.region,
    f.quantity,
    f.revenue
FROM fact_sales f
JOIN dim_date d
    ON d.date_key = f.date_key
JOIN dim_customer c
    ON c.customer_key = f.customer_key
JOIN dim_product p
    ON p.product_key = f.product_key;

CREATE OR REPLACE FUNCTION region_revenue()
RETURNS TABLE (
    region TEXT,
    order_count BIGINT,
    total_quantity BIGINT,
    revenue NUMERIC
)
LANGUAGE sql
AS $$
    SELECT
        region,
        COUNT(*) AS order_count,
        SUM(quantity) AS total_quantity,
        ROUND(SUM(revenue), 2) AS revenue
    FROM fact_sales
    GROUP BY region
    ORDER BY revenue DESC;
$$;

CREATE OR REPLACE FUNCTION monthly_revenue()
RETURNS TABLE (
    month_start DATE,
    order_count BIGINT,
    revenue NUMERIC
)
LANGUAGE sql
AS $$
    SELECT
        DATE_TRUNC('month', d.calendar_date)::DATE AS month_start,
        COUNT(*) AS order_count,
        ROUND(SUM(f.revenue), 2) AS revenue
    FROM fact_sales f
    JOIN dim_date d
        ON d.date_key = f.date_key
    GROUP BY DATE_TRUNC('month', d.calendar_date)
    ORDER BY month_start;
$$;

CREATE OR REPLACE PROCEDURE load_new_facts(
    IN p_pipeline_run_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    inserted_count INTEGER;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pipeline_runs
        WHERE pipeline_run_id = p_pipeline_run_id
          AND state IN ('CREATED', 'EXTRACTED', 'VALIDATED', 'TRANSFORMED')
    ) THEN
        RAISE EXCEPTION
            'Pipeline run % is not eligible for loading',
            p_pipeline_run_id;
    END IF;

    INSERT INTO fact_sales (
        order_id,
        date_key,
        customer_key,
        product_key,
        region,
        quantity,
        revenue
    )
    SELECT
        o.order_id,
        TO_CHAR(o.order_date, 'YYYYMMDD')::INTEGER,
        c.customer_key,
        p.product_key,
        o.region,
        o.quantity,
        ROUND(o.quantity * o.unit_price, 2)
    FROM source_orders o
    JOIN dim_customer c
        ON c.source_customer_id = o.customer_id
    JOIN dim_product p
        ON p.source_product_id = o.product_id
    WHERE NOT EXISTS (
        SELECT 1
        FROM fact_sales f
        WHERE f.order_id = o.order_id
    );

    GET DIAGNOSTICS inserted_count = ROW_COUNT;

    UPDATE pipeline_runs
    SET
        state = 'LOADED',
        loaded_rows = inserted_count,
        completed_at = CURRENT_TIMESTAMP
    WHERE pipeline_run_id = p_pipeline_run_id;
END;
$$;

CREATE OR REPLACE FUNCTION validate_source_order(
    p_customer_id BIGINT,
    p_product_id BIGINT,
    p_quantity INTEGER,
    p_unit_price NUMERIC
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM source_customers
        WHERE customer_id = p_customer_id
    ) THEN
        RETURN FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM source_products
        WHERE product_id = p_product_id
          AND active
    ) THEN
        RETURN FALSE;
    END IF;

    IF p_quantity <= 0 OR p_unit_price < 0 THEN
        RETURN FALSE;
    END IF;

    RETURN TRUE;
END;
$$;

-- Retrieval.
SELECT *
FROM sales_analytics
ORDER BY calendar_date, order_id;

-- Validation.
SELECT
    validate_source_order(1, 3, 5, 120.00) AS valid_case,
    validate_source_order(999, 3, 5, 120.00) AS invalid_customer_case,
    validate_source_order(1, 3, 0, 120.00) AS invalid_quantity_case;

-- Aggregation.
SELECT *
FROM region_revenue();

SELECT *
FROM monthly_revenue();

-- Reporting with dimensional attributes.
SELECT
    category,
    region,
    SUM(quantity) AS units,
    ROUND(SUM(revenue), 2) AS revenue
FROM sales_analytics
GROUP BY ROLLUP (category, region)
ORDER BY category NULLS LAST, region NULLS LAST;

-- CTE for customer performance.
WITH customer_sales AS (
    SELECT
        customer_name,
        segment,
        SUM(revenue) AS revenue
    FROM sales_analytics
    GROUP BY customer_name, segment
),
ranked AS (
    SELECT
        customer_name,
        segment,
        ROUND(revenue, 2) AS revenue,
        DENSE_RANK() OVER (ORDER BY revenue DESC) AS revenue_rank
    FROM customer_sales
)
SELECT *
FROM ranked
ORDER BY revenue_rank, customer_name;

-- Eligibility determination for a hypothetical analytical promotion.
WITH customer_metrics AS (
    SELECT
        customer_key,
        SUM(revenue) AS total_revenue,
        COUNT(*) AS order_count
    FROM fact_sales
    GROUP BY customer_key
)
SELECT
    c.customer_name,
    c.segment,
    ROUND(m.total_revenue, 2) AS total_revenue,
    m.order_count,
    CASE
        WHEN m.total_revenue >= 1000
             AND m.order_count >= 2
        THEN 'ELIGIBLE'
        ELSE 'NOT_ELIGIBLE'
    END AS eligibility
FROM customer_metrics m
JOIN dim_customer c
    ON c.customer_key = m.customer_key
ORDER BY total_revenue DESC;

-- Performance-oriented analytical access path.
EXPLAIN
SELECT
    region,
    SUM(revenue)
FROM fact_sales
WHERE date_key BETWEEN 20260101 AND 20260331
GROUP BY region;

-- Transaction demonstrating controlled workflow processing.
BEGIN;

INSERT INTO pipeline_runs (
    strategy,
    state,
    extracted_rows
)
VALUES (
    'ELT',
    'EXTRACTED',
    (SELECT COUNT(*) FROM source_orders)
)
RETURNING pipeline_run_id;

COMMIT;

-- The procedure can be invoked for a previously created eligible run:
-- CALL load_new_facts(<pipeline_run_id>);
