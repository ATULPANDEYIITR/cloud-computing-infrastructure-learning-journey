-- Serverless Computing: PostgreSQL operational model
--
-- Models deployed functions, triggers, events, invocation attempts,
-- execution environments, scaling policies, and dead-letter outcomes.
--
-- Compatible with PostgreSQL 15+.
-- The script is designed to run in a dedicated database or schema.
-- It uses database constraints and transactions to preserve operational
-- integrity. Actual cloud execution remains the responsibility of a runtime.

BEGIN;

CREATE SCHEMA IF NOT EXISTS serverless_lab;
SET LOCAL search_path TO serverless_lab, public;

CREATE TABLE IF NOT EXISTS function_definitions (
    function_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    function_name TEXT NOT NULL UNIQUE,
    handler_name TEXT NOT NULL,
    runtime_name TEXT NOT NULL,
    memory_mb INTEGER NOT NULL CHECK (memory_mb >= 128),
    timeout_ms INTEGER NOT NULL CHECK (timeout_ms > 0),
    initialization_estimate_ms INTEGER NOT NULL DEFAULT 0
        CHECK (initialization_estimate_ms >= 0),
    max_concurrency INTEGER NOT NULL DEFAULT 10
        CHECK (max_concurrency > 0),
    max_retries INTEGER NOT NULL DEFAULT 0
        CHECK (max_retries >= 0),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS event_triggers (
    trigger_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trigger_name TEXT NOT NULL UNIQUE,
    trigger_type TEXT NOT NULL CHECK (
        trigger_type IN (
            'http',
            'queue',
            'object_created',
            'schedule',
            'database_event'
        )
    ),
    event_pattern TEXT NOT NULL,
    source_name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS trigger_subscriptions (
    trigger_id BIGINT NOT NULL REFERENCES event_triggers(trigger_id),
    function_id BIGINT NOT NULL REFERENCES function_definitions(function_id),
    subscription_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (trigger_id, function_id)
);

CREATE TABLE IF NOT EXISTS execution_environments (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    function_id BIGINT NOT NULL
        REFERENCES function_definitions(function_id),
    provider_environment_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ NOT NULL,
    invocation_count BIGINT NOT NULL DEFAULT 0
        CHECK (invocation_count >= 0),
    lifecycle_state TEXT NOT NULL DEFAULT 'ready'
        CHECK (
            lifecycle_state IN ('ready', 'busy', 'expired', 'terminated')
        ),
    UNIQUE (function_id, provider_environment_key),
    CHECK (last_used_at >= created_at)
);

CREATE TABLE IF NOT EXISTS serverless_events (
    event_id UUID PRIMARY KEY,
    trigger_id BIGINT REFERENCES event_triggers(trigger_id),
    event_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(payload) = 'object'),
    idempotency_key TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivery_state TEXT NOT NULL DEFAULT 'received'
        CHECK (
            delivery_state IN (
                'received',
                'processing',
                'succeeded',
                'failed',
                'dead_lettered'
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_serverless_events_type_received
    ON serverless_events (event_type, received_at DESC);

CREATE INDEX IF NOT EXISTS idx_serverless_events_pending
    ON serverless_events (received_at)
    WHERE delivery_state IN ('received', 'failed');

CREATE TABLE IF NOT EXISTS invocation_records (
    invocation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES serverless_events(event_id),
    function_id BIGINT NOT NULL
        REFERENCES function_definitions(function_id),
    environment_id BIGINT
        REFERENCES execution_environments(environment_id),
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    invocation_status TEXT NOT NULL
        CHECK (
            invocation_status IN (
                'accepted',
                'succeeded',
                'failed',
                'timed_out',
                'throttled'
            )
        ),
    cold_start BOOLEAN NOT NULL DEFAULT FALSE,
    initialization_ms INTEGER NOT NULL DEFAULT 0
        CHECK (initialization_ms >= 0),
    handler_duration_ms INTEGER NOT NULL DEFAULT 0
        CHECK (handler_duration_ms >= 0),
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    CHECK (
        completed_at IS NULL OR completed_at >= started_at
    ),
    UNIQUE (event_id, function_id, attempt_number)
);

CREATE INDEX IF NOT EXISTS idx_invocations_function_started
    ON invocation_records (function_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_invocations_failures
    ON invocation_records (started_at DESC)
    WHERE invocation_status IN ('failed', 'timed_out', 'throttled');

CREATE TABLE IF NOT EXISTS idempotency_records (
    function_id BIGINT NOT NULL
        REFERENCES function_definitions(function_id),
    idempotency_key TEXT NOT NULL,
    event_id UUID NOT NULL REFERENCES serverless_events(event_id),
    operation_state TEXT NOT NULL
        CHECK (operation_state IN ('in_progress', 'succeeded', 'failed')),
    result_payload JSONB,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (function_id, idempotency_key),
    CHECK (
        operation_state <> 'succeeded'
        OR result_payload IS NOT NULL
    )
);

CREATE TABLE IF NOT EXISTS dead_letter_events (
    dead_letter_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES serverless_events(event_id),
    function_id BIGINT REFERENCES function_definitions(function_id),
    final_attempt_number INTEGER NOT NULL CHECK (final_attempt_number >= 0),
    failure_reason TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    replayed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_dead_letter_unreplayed
    ON dead_letter_events (recorded_at)
    WHERE replayed_at IS NULL;

-- Sample functions represent separate execution and scaling profiles.
INSERT INTO function_definitions (
    function_name,
    handler_name,
    runtime_name,
    memory_mb,
    timeout_ms,
    initialization_estimate_ms,
    max_concurrency,
    max_retries
)
VALUES
    (
        'order-validator',
        'validate_order',
        'python3.13',
        256,
        1500,
        120,
        20,
        2
    ),
    (
        'image-thumbnailer',
        'create_thumbnail',
        'nodejs22.x',
        512,
        5000,
        240,
        8,
        1
    ),
    (
        'scheduled-report',
        'generate_report',
        'java21',
        1024,
        15000,
        900,
        4,
        0
    )
ON CONFLICT (function_name) DO UPDATE
SET handler_name = EXCLUDED.handler_name,
    runtime_name = EXCLUDED.runtime_name,
    memory_mb = EXCLUDED.memory_mb,
    timeout_ms = EXCLUDED.timeout_ms,
    initialization_estimate_ms = EXCLUDED.initialization_estimate_ms,
    max_concurrency = EXCLUDED.max_concurrency,
    max_retries = EXCLUDED.max_retries;

INSERT INTO event_triggers (
    trigger_name,
    trigger_type,
    event_pattern,
    source_name
)
VALUES
    (
        'checkout-order-created',
        'queue',
        'order.created',
        'checkout-service'
    ),
    (
        'product-image-uploaded',
        'object_created',
        'uploads/*',
        'product-image-bucket'
    ),
    (
        'nightly-report-schedule',
        'schedule',
        '0 2 * * *',
        'report-scheduler'
    )
ON CONFLICT (trigger_name) DO UPDATE
SET trigger_type = EXCLUDED.trigger_type,
    event_pattern = EXCLUDED.event_pattern,
    source_name = EXCLUDED.source_name;

INSERT INTO trigger_subscriptions (trigger_id, function_id)
SELECT t.trigger_id, f.function_id
FROM event_triggers AS t
JOIN function_definitions AS f
    ON (
        (t.trigger_name = 'checkout-order-created'
            AND f.function_name = 'order-validator')
        OR
        (t.trigger_name = 'product-image-uploaded'
            AND f.function_name = 'image-thumbnailer')
        OR
        (t.trigger_name = 'nightly-report-schedule'
            AND f.function_name = 'scheduled-report')
    )
ON CONFLICT (trigger_id, function_id) DO NOTHING;

INSERT INTO serverless_events (
    event_id,
    trigger_id,
    event_type,
    source_name,
    payload,
    idempotency_key,
    occurred_at,
    delivery_state
)
SELECT
    v.event_id::UUID,
    t.trigger_id,
    v.event_type,
    v.source_name,
    v.payload::JSONB,
    v.idempotency_key,
    v.occurred_at::TIMESTAMPTZ,
    v.delivery_state
FROM (
    VALUES
        (
            '10000000-0000-4000-8000-000000000001',
            'checkout-order-created',
            'order.created',
            'checkout-service',
            '{"order_id":"ORD-1001","amount":1250.50}' ,
            'order:ORD-1001',
            '2026-10-15 08:00:00+05:30',
            'succeeded'
        ),
        (
            '10000000-0000-4000-8000-000000000002',
            'checkout-order-created',
            'order.created',
            'checkout-service',
            '{"order_id":"ORD-1002","amount":0}' ,
            'order:ORD-1002',
            '2026-10-15 08:01:00+05:30',
            'failed'
        ),
        (
            '10000000-0000-4000-8000-000000000003',
            'product-image-uploaded',
            'object.created',
            'product-image-bucket',
            '{"object_key":"uploads/item-88.jpg","width":640}' ,
            NULL,
            '2026-10-15 08:02:00+05:30',
            'received'
        ),
        (
            '10000000-0000-4000-8000-000000000004',
            'nightly-report-schedule',
            'report.generate',
            'report-scheduler',
            '{"report_date":"2026-10-15"}',
            NULL,
            '2026-10-15 02:00:00+05:30',
            'dead_lettered'
        )
) AS v(
    event_id,
    trigger_name,
    event_type,
    source_name,
    payload,
    idempotency_key,
    occurred_at,
    delivery_state
)
JOIN event_triggers AS t
    ON t.trigger_name = v.trigger_name
ON CONFLICT (event_id) DO NOTHING;

INSERT INTO execution_environments (
    function_id,
    provider_environment_key,
    created_at,
    last_used_at,
    invocation_count,
    lifecycle_state
)
SELECT
    f.function_id,
    v.environment_key,
    v.created_at::TIMESTAMPTZ,
    v.last_used_at::TIMESTAMPTZ,
    v.invocation_count,
    v.lifecycle_state
FROM (
    VALUES
        (
            'order-validator',
            'worker-order-01',
            '2026-10-15 07:50:00+05:30',
            '2026-10-15 08:00:00+05:30',
            8,
            'ready'
        ),
        (
            'image-thumbnailer',
            'worker-image-01',
            '2026-10-15 08:02:00+05:30',
            '2026-10-15 08:02:00+05:30',
            1,
            'ready'
        ),
        (
            'scheduled-report',
            'worker-report-01',
            '2026-10-15 02:00:00+05:30',
            '2026-10-15 02:00:00+05:30',
            1,
            'expired'
        )
) AS v(
    function_name,
    environment_key,
    created_at,
    last_used_at,
    invocation_count,
    lifecycle_state
)
JOIN function_definitions AS f
    ON f.function_name = v.function_name
ON CONFLICT (function_id, provider_environment_key) DO UPDATE
SET last_used_at = EXCLUDED.last_used_at,
    invocation_count = EXCLUDED.invocation_count,
    lifecycle_state = EXCLUDED.lifecycle_state;

INSERT INTO invocation_records (
    event_id,
    function_id,
    environment_id,
    attempt_number,
    invocation_status,
    cold_start,
    initialization_ms,
    handler_duration_ms,
    error_message,
    started_at,
    completed_at
)
SELECT
    e.event_id,
    f.function_id,
    env.environment_id,
    v.attempt_number,
    v.invocation_status,
    v.cold_start,
    v.initialization_ms,
    v.handler_duration_ms,
    v.error_message,
    v.started_at::TIMESTAMPTZ,
    v.completed_at::TIMESTAMPTZ
FROM (
    VALUES
        (
            '10000000-0000-4000-8000-000000000001',
            'order-validator',
            'worker-order-01',
            1,
            'succeeded',
            FALSE,
            0,
            35,
            NULL::TEXT,
            '2026-10-15 08:00:00+05:30',
            '2026-10-15 08:00:00.035+05:30'
        ),
        (
            '10000000-0000-4000-8000-000000000002',
            'order-validator',
            'worker-order-01',
            1,
            'failed',
            FALSE,
            0,
            4,
            'amount must be positive',
            '2026-10-15 08:01:00+05:30',
            '2026-10-15 08:01:00.004+05:30'
        ),
        (
            '10000000-0000-4000-8000-000000000003',
            'image-thumbnailer',
            'worker-image-01',
            1,
            'succeeded',
            TRUE,
            240,
            110,
            NULL::TEXT,
            '2026-10-15 08:02:00+05:30',
            '2026-10-15 08:02:00.350+05:30'
        ),
        (
            '10000000-0000-4000-8000-000000000004',
            'scheduled-report',
            'worker-report-01',
            1,
            'timed_out',
            TRUE,
            900,
            15000,
            'Execution exceeded configured timeout',
            '2026-10-15 02:00:00+05:30',
            '2026-10-15 02:00:15+05:30'
        )
) AS v(
    event_id,
    function_name,
    environment_key,
    attempt_number,
    invocation_status,
    cold_start,
    initialization_ms,
    handler_duration_ms,
    error_message,
    started_at,
    completed_at
)
JOIN serverless_events AS e
    ON e.event_id = v.event_id::UUID
JOIN function_definitions AS f
    ON f.function_name = v.function_name
JOIN execution_environments AS env
    ON env.function_id = f.function_id
    AND env.provider_environment_key = v.environment_key
ON CONFLICT (event_id, function_id, attempt_number) DO NOTHING;

INSERT INTO idempotency_records (
    function_id,
    idempotency_key,
    event_id,
    operation_state,
    result_payload,
    completed_at
)
SELECT
    f.function_id,
    e.idempotency_key,
    e.event_id,
    CASE
        WHEN e.delivery_state = 'succeeded' THEN 'succeeded'
        WHEN e.delivery_state = 'failed' THEN 'failed'
        ELSE 'in_progress'
    END,
    CASE
        WHEN e.delivery_state = 'succeeded'
            THEN jsonb_build_object(
                'order_id', e.payload ->> 'order_id',
                'accepted', TRUE
            )
        ELSE NULL
    END,
    CASE
        WHEN e.delivery_state IN ('succeeded', 'failed')
            THEN e.received_at
        ELSE NULL
    END
FROM serverless_events AS e
JOIN function_definitions AS f
    ON f.function_name = 'order-validator'
WHERE e.idempotency_key IS NOT NULL
ON CONFLICT (function_id, idempotency_key) DO NOTHING;

INSERT INTO dead_letter_events (
    event_id,
    function_id,
    final_attempt_number,
    failure_reason
)
SELECT
    e.event_id,
    f.function_id,
    COALESCE(
        (
            SELECT MAX(i.attempt_number)
            FROM invocation_records AS i
            WHERE i.event_id = e.event_id
              AND i.function_id = f.function_id
        ),
        0
    ),
    CASE
        WHEN e.event_type = 'report.generate'
            THEN 'Execution exceeded configured timeout'
        ELSE 'Event delivery failed'
    END
FROM serverless_events AS e
JOIN function_definitions AS f
    ON (
        (e.event_type = 'report.generate'
            AND f.function_name = 'scheduled-report')
        OR
        (e.event_type = 'order.created'
            AND e.delivery_state = 'failed'
            AND f.function_name = 'order-validator')
    )
WHERE e.delivery_state IN ('failed', 'dead_lettered')
ON CONFLICT DO NOTHING;

COMMIT;

-- Event-routing inspection: one trigger can be associated with one or
-- multiple functions, while each subscription is independently enabled.
SELECT
    t.trigger_name,
    t.trigger_type,
    t.event_pattern,
    f.function_name,
    s.subscription_enabled
FROM event_triggers AS t
JOIN trigger_subscriptions AS s
    ON s.trigger_id = t.trigger_id
JOIN function_definitions AS f
    ON f.function_id = s.function_id
ORDER BY t.trigger_name, f.function_name;

-- Cold-start impact separates initialization overhead from handler time.
SELECT
    f.function_name,
    COUNT(*) AS invocation_count,
    COUNT(*) FILTER (WHERE i.cold_start) AS cold_start_count,
    ROUND(
        AVG(i.initialization_ms)::NUMERIC,
        2
    ) AS average_initialization_ms,
    ROUND(
        AVG(i.handler_duration_ms)::NUMERIC,
        2
    ) AS average_handler_duration_ms,
    ROUND(
        AVG(
            i.initialization_ms + i.handler_duration_ms
        )::NUMERIC,
        2
    ) AS average_recorded_execution_ms
FROM invocation_records AS i
JOIN function_definitions AS f
    ON f.function_id = i.function_id
GROUP BY f.function_name
ORDER BY f.function_name;

-- Failure analysis distinguishes application errors, timeouts, and
-- throttling. These conditions require different operational responses.
SELECT
    f.function_name,
    i.invocation_status,
    COUNT(*) AS occurrence_count,
    MAX(i.started_at) AS latest_occurrence
FROM invocation_records AS i
JOIN function_definitions AS f
    ON f.function_id = i.function_id
WHERE i.invocation_status IN ('failed', 'timed_out', 'throttled')
GROUP BY f.function_name, i.invocation_status
ORDER BY f.function_name, i.invocation_status;

-- JSONB payload extraction enables event-specific operational inspection.
SELECT
    event_id,
    event_type,
    payload ->> 'order_id' AS order_id,
    CASE
        WHEN payload ? 'amount'
            THEN (payload ->> 'amount')::NUMERIC
        ELSE NULL
    END AS amount,
    delivery_state
FROM serverless_events
WHERE event_type = 'order.created'
ORDER BY received_at;

-- Idempotency records distinguish completed operations from work still
-- in progress. The unique key prevents duplicate claims per function.
SELECT
    f.function_name,
    r.idempotency_key,
    r.operation_state,
    r.event_id,
    r.first_seen_at,
    r.completed_at
FROM idempotency_records AS r
JOIN function_definitions AS f
    ON f.function_id = r.function_id
ORDER BY r.first_seen_at;

-- Dead-letter events remain available for diagnosis and controlled replay.
SELECT
    d.dead_letter_id,
    d.event_id,
    f.function_name,
    d.final_attempt_number,
    d.failure_reason,
    d.recorded_at
FROM dead_letter_events AS d
LEFT JOIN function_definitions AS f
    ON f.function_id = d.function_id
WHERE d.replayed_at IS NULL
ORDER BY d.recorded_at;

-- PostgreSQL transaction example: mark an event as being processed only
-- if it is currently eligible. The conditional update prevents two
-- competing workers from both claiming the same received event.
BEGIN;

WITH claimed AS (
    UPDATE serverless_events
    SET delivery_state = 'processing'
    WHERE event_id = '10000000-0000-4000-8000-000000000003'::UUID
      AND delivery_state = 'received'
    RETURNING event_id, event_type, received_at
)
SELECT * FROM claimed;

COMMIT;

-- Validate event data without aborting the reporting query. Invalid
-- application payloads are visible as data-quality findings.
SELECT
    event_id,
    payload,
    CASE
        WHEN event_type = 'order.created'
             AND (
                 NULLIF(payload ->> 'order_id', '') IS NULL
                 OR CASE
                     WHEN jsonb_typeof(payload -> 'amount') = 'number'
                         THEN (payload ->> 'amount')::NUMERIC <= 0
                     ELSE TRUE
                 END
             )
            THEN 'invalid_order_payload'
        WHEN event_type = 'object.created'
             AND COALESCE(payload ->> 'object_key', '') NOT LIKE 'uploads/%'
            THEN 'invalid_object_key'
        ELSE 'payload_passes_basic_checks'
    END AS validation_result
FROM serverless_events
ORDER BY received_at;

-- Capacity planning compares configured concurrency with observed
-- invocation activity. It does not imply that historical counts equal
-- simultaneous executions.
SELECT
    f.function_name,
    f.max_concurrency,
    COUNT(i.invocation_id) AS recorded_invocations,
    COUNT(*) FILTER (
        WHERE i.invocation_status = 'throttled'
    ) AS throttled_invocations,
    COUNT(*) FILTER (
        WHERE i.cold_start
    ) AS cold_starts
FROM function_definitions AS f
LEFT JOIN invocation_records AS i
    ON i.function_id = f.function_id
GROUP BY f.function_id, f.function_name, f.max_concurrency
ORDER BY throttled_invocations DESC, f.function_name;
