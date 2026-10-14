-- PostgreSQL 15+
-- Auto scaling control plane for a production web service.
--
-- This schema separates:
--   * Observed metrics from scaling decisions.
--   * Desired capacity from actual instance state.
--   * Target-tracking, step, and scheduled policies.
--   * Health events from policy-driven capacity changes.
--
-- Run the script in a dedicated development database.
-- The transaction makes the example schema and sample data reproducible.

BEGIN;

DROP SCHEMA IF EXISTS autoscaling_lab CASCADE;
CREATE SCHEMA autoscaling_lab;
SET search_path TO autoscaling_lab, public;

CREATE TYPE instance_status AS ENUM (
    'warming',
    'healthy',
    'unhealthy',
    'terminating'
);

CREATE TYPE scaling_policy_type AS ENUM (
    'target_tracking',
    'step_scaling',
    'scheduled'
);

CREATE TYPE scaling_direction AS ENUM (
    'scale_out',
    'scale_in',
    'no_change',
    'health_replacement',
    'scheduled_change'
);

CREATE TABLE scaling_groups (
    group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_name TEXT NOT NULL UNIQUE,
    minimum_capacity INTEGER NOT NULL DEFAULT 1,
    maximum_capacity INTEGER NOT NULL,
    desired_capacity INTEGER NOT NULL,
    instance_warmup_seconds INTEGER NOT NULL DEFAULT 60,
    health_check_grace_seconds INTEGER NOT NULL DEFAULT 120,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT valid_capacity_bounds CHECK (
        minimum_capacity >= 0
        AND maximum_capacity >= minimum_capacity
        AND desired_capacity BETWEEN minimum_capacity AND maximum_capacity
    ),
    CONSTRAINT valid_warmup CHECK (
        instance_warmup_seconds >= 0
        AND health_check_grace_seconds >= 0
    )
);

CREATE TABLE scaling_instances (
    instance_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_id BIGINT NOT NULL REFERENCES scaling_groups(group_id),
    provider_instance_key TEXT NOT NULL UNIQUE,
    status instance_status NOT NULL DEFAULT 'warming',
    launched_at TIMESTAMPTZ NOT NULL,
    ready_at TIMESTAMPTZ NOT NULL,
    last_health_check_at TIMESTAMPTZ,
    protected_from_scale_in BOOLEAN NOT NULL DEFAULT FALSE,
    failure_reason TEXT,
    terminated_at TIMESTAMPTZ,
    CONSTRAINT valid_readiness_window CHECK (ready_at >= launched_at),
    CONSTRAINT valid_termination_state CHECK (
        (status = 'terminating' AND terminated_at IS NOT NULL)
        OR
        (status <> 'terminating' AND terminated_at IS NULL)
    )
);

CREATE INDEX scaling_instances_group_status_idx
    ON scaling_instances(group_id, status);

CREATE INDEX scaling_instances_scale_in_candidates_idx
    ON scaling_instances(group_id, launched_at)
    WHERE protected_from_scale_in = FALSE
      AND status IN ('warming', 'healthy');

CREATE TABLE scaling_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_id BIGINT NOT NULL REFERENCES scaling_groups(group_id),
    policy_name TEXT NOT NULL,
    policy_type scaling_policy_type NOT NULL,
    metric_name TEXT NOT NULL CHECK (
        metric_name IN (
            'cpu_percent',
            'requests_per_second',
            'p95_latency_ms',
            'error_rate_percent'
        )
    ),
    target_value NUMERIC(12, 4) NOT NULL CHECK (target_value > 0),
    scale_out_ratio NUMERIC(8, 4) NOT NULL DEFAULT 1.10,
    scale_in_ratio NUMERIC(8, 4) NOT NULL DEFAULT 0.75,
    scale_out_step INTEGER NOT NULL DEFAULT 2,
    scale_in_step INTEGER NOT NULL DEFAULT 1,
    scale_out_cooldown_seconds INTEGER NOT NULL DEFAULT 120,
    scale_in_cooldown_seconds INTEGER NOT NULL DEFAULT 180,
    evaluation_periods INTEGER NOT NULL DEFAULT 2,
    metric_window_size INTEGER NOT NULL DEFAULT 3,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT unique_policy_name UNIQUE(group_id, policy_name),
    CONSTRAINT valid_policy_thresholds CHECK (
        scale_out_ratio > 1
        AND scale_in_ratio > 0
        AND scale_in_ratio < 1
    ),
    CONSTRAINT valid_policy_steps CHECK (
        scale_out_step >= 1
        AND scale_in_step >= 1
        AND scale_out_cooldown_seconds >= 0
        AND scale_in_cooldown_seconds >= 0
        AND evaluation_periods >= 1
        AND metric_window_size >= 1
    )
);

CREATE INDEX enabled_group_policies_idx
    ON scaling_policies(group_id, policy_type)
    WHERE enabled = TRUE;

CREATE TABLE metric_samples (
    sample_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_id BIGINT NOT NULL REFERENCES scaling_groups(group_id),
    observed_at TIMESTAMPTZ NOT NULL,
    cpu_percent NUMERIC(6, 3) NOT NULL CHECK (
        cpu_percent BETWEEN 0 AND 100
    ),
    requests_per_second NUMERIC(14, 3) NOT NULL CHECK (
        requests_per_second >= 0
    ),
    p95_latency_ms NUMERIC(14, 3) NOT NULL CHECK (
        p95_latency_ms >= 0
    ),
    error_rate_percent NUMERIC(6, 3) NOT NULL CHECK (
        error_rate_percent BETWEEN 0 AND 100
    ),
    UNIQUE(group_id, observed_at)
);

CREATE INDEX metric_samples_recent_idx
    ON metric_samples(group_id, observed_at DESC);

CREATE TABLE scaling_evaluations (
    evaluation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_id BIGINT NOT NULL REFERENCES scaling_groups(group_id),
    policy_id BIGINT REFERENCES scaling_policies(policy_id),
    evaluated_at TIMESTAMPTZ NOT NULL,
    metric_name TEXT NOT NULL,
    observed_value NUMERIC(14, 4) NOT NULL CHECK (observed_value >= 0),
    target_value NUMERIC(14, 4) NOT NULL CHECK (target_value > 0),
    ratio NUMERIC(14, 6) NOT NULL CHECK (ratio >= 0),
    decision TEXT NOT NULL CHECK (
        decision IN (
            'scale_out',
            'scale_in',
            'hold',
            'cooldown',
            'at_limit',
            'insufficient_data',
            'scheduled_change',
            'health_replacement'
        )
    ),
    reason TEXT NOT NULL,
    desired_before INTEGER NOT NULL CHECK (desired_before >= 0),
    desired_after INTEGER NOT NULL CHECK (desired_after >= 0)
);

CREATE INDEX evaluations_group_recent_idx
    ON scaling_evaluations(group_id, evaluated_at DESC);

CREATE TABLE scheduled_scaling_actions (
    scheduled_action_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_id BIGINT NOT NULL REFERENCES scaling_groups(group_id),
    action_name TEXT NOT NULL,
    execute_at TIMESTAMPTZ NOT NULL,
    desired_capacity INTEGER NOT NULL CHECK (desired_capacity >= 0),
    executed_at TIMESTAMPTZ,
    execution_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        execution_status IN ('pending', 'executed', 'rejected', 'failed')
    ),
    UNIQUE(group_id, action_name),
    CONSTRAINT execution_state_consistent CHECK (
        (execution_status = 'executed' AND executed_at IS NOT NULL)
        OR
        (execution_status <> 'executed' AND executed_at IS NULL)
    )
);

CREATE INDEX due_scheduled_actions_idx
    ON scheduled_scaling_actions(execute_at)
    WHERE execution_status = 'pending';

CREATE TABLE scaling_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_id BIGINT NOT NULL REFERENCES scaling_groups(group_id),
    policy_id BIGINT REFERENCES scaling_policies(policy_id),
    instance_id BIGINT REFERENCES scaling_instances(instance_id),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    direction scaling_direction NOT NULL,
    old_desired_capacity INTEGER NOT NULL CHECK (old_desired_capacity >= 0),
    new_desired_capacity INTEGER NOT NULL CHECK (new_desired_capacity >= 0),
    reason TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX scaling_events_group_recent_idx
    ON scaling_events(group_id, occurred_at DESC);

-- Sample production-like group and distinct scaling policies.
INSERT INTO scaling_groups (
    group_name,
    minimum_capacity,
    maximum_capacity,
    desired_capacity,
    instance_warmup_seconds,
    health_check_grace_seconds
)
VALUES
    ('checkout-api', 2, 12, 4, 90, 120),
    ('reporting-api', 1, 6, 2, 180, 240);

INSERT INTO scaling_policies (
    group_id,
    policy_name,
    policy_type,
    metric_name,
    target_value,
    scale_out_ratio,
    scale_in_ratio,
    scale_out_step,
    scale_in_step,
    evaluation_periods,
    metric_window_size
)
SELECT
    group_id,
    'cpu-target',
    'target_tracking',
    'cpu_percent',
    55,
    1.10,
    0.75,
    2,
    1,
    2,
    3
FROM scaling_groups
WHERE group_name = 'checkout-api';

INSERT INTO scaling_policies (
    group_id,
    policy_name,
    policy_type,
    metric_name,
    target_value,
    scale_out_ratio,
    scale_in_ratio,
    scale_out_step,
    scale_in_step,
    evaluation_periods,
    metric_window_size
)
SELECT
    group_id,
    'latency-step-policy',
    'step_scaling',
    'p95_latency_ms',
    250,
    1.20,
    0.60,
    3,
    1,
    2,
    3
FROM scaling_groups
WHERE group_name = 'checkout-api';

INSERT INTO scaling_instances (
    group_id,
    provider_instance_key,
    status,
    launched_at,
    ready_at,
    last_health_check_at,
    protected_from_scale_in
)
SELECT
    g.group_id,
    instance_data.provider_key,
    instance_data.status::instance_status,
    now() - instance_data.age,
    now() - instance_data.age + interval '90 seconds',
    now(),
    instance_data.protected
FROM scaling_groups AS g
CROSS JOIN (
    VALUES
        ('checkout-node-a', 'healthy', interval '20 minutes', FALSE),
        ('checkout-node-b', 'healthy', interval '15 minutes', FALSE),
        ('checkout-node-c', 'healthy', interval '10 minutes', FALSE),
        ('checkout-node-d', 'warming', interval '30 seconds', FALSE)
) AS instance_data(provider_key, status, age, protected)
WHERE g.group_name = 'checkout-api';

INSERT INTO metric_samples (
    group_id,
    observed_at,
    cpu_percent,
    requests_per_second,
    p95_latency_ms,
    error_rate_percent
)
SELECT
    g.group_id,
    metric_data.observed_at,
    metric_data.cpu,
    metric_data.request_rate,
    metric_data.latency,
    metric_data.errors
FROM scaling_groups AS g
CROSS JOIN (
    VALUES
        (now() - interval '4 minutes', 42.0, 150.0, 140.0, 0.2),
        (now() - interval '3 minutes', 61.0, 230.0, 220.0, 0.3),
        (now() - interval '2 minutes', 74.0, 300.0, 315.0, 0.5),
        (now() - interval '1 minute', 82.0, 365.0, 405.0, 1.2),
        (now(), 78.0, 350.0, 390.0, 1.0)
) AS metric_data(observed_at, cpu, request_rate, latency, errors)
WHERE g.group_name = 'checkout-api';

INSERT INTO scheduled_scaling_actions (
    group_id,
    action_name,
    execute_at,
    desired_capacity
)
SELECT
    group_id,
    'weekday-traffic-preparation',
    now() + interval '30 minutes',
    6
FROM scaling_groups
WHERE group_name = 'checkout-api';

-- Metric trend query: moving averages make short-lived spikes easier to identify.
SELECT
    group_name,
    observed_at,
    ROUND(cpu_percent, 2) AS cpu_percent,
    ROUND(
        AVG(cpu_percent) OVER (
            PARTITION BY group_id
            ORDER BY observed_at
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS cpu_moving_average,
    ROUND(p95_latency_ms, 2) AS p95_latency_ms,
    ROUND(
        AVG(p95_latency_ms) OVER (
            PARTITION BY group_id
            ORDER BY observed_at
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS latency_moving_average
FROM metric_samples
JOIN scaling_groups USING (group_id)
ORDER BY group_name, observed_at;

-- Evaluate the latest rolling CPU average against the enabled target policy.
WITH latest_policy AS (
    SELECT DISTINCT ON (group_id)
        group_id,
        policy_id,
        metric_name,
        target_value,
        scale_out_ratio,
        scale_in_ratio
    FROM scaling_policies
    WHERE enabled
      AND policy_type = 'target_tracking'
    ORDER BY group_id, created_at DESC
),
latest_metrics AS (
    SELECT
        m.group_id,
        AVG(m.cpu_percent) AS average_cpu,
        MAX(m.observed_at) AS latest_observation
    FROM (
        SELECT
            group_id,
            observed_at,
            cpu_percent
        FROM metric_samples
        ORDER BY group_id, observed_at DESC
    ) AS m
    GROUP BY m.group_id
)
SELECT
    g.group_name,
    p.policy_id,
    lm.latest_observation,
    ROUND(lm.average_cpu, 2) AS average_cpu,
    p.target_value,
    ROUND(lm.average_cpu / p.target_value, 3) AS utilization_ratio,
    CASE
        WHEN lm.average_cpu / p.target_value >= p.scale_out_ratio
            THEN 'scale_out_candidate'
        WHEN lm.average_cpu / p.target_value <= p.scale_in_ratio
            THEN 'scale_in_candidate'
        ELSE 'hold'
    END AS metric_decision
FROM scaling_groups AS g
JOIN latest_policy AS p USING (group_id)
JOIN latest_metrics AS lm USING (group_id)
ORDER BY g.group_name;

-- Compare desired capacity with observed instance states.
CREATE VIEW scaling_capacity_status AS
SELECT
    g.group_id,
    g.group_name,
    g.minimum_capacity,
    g.desired_capacity,
    g.maximum_capacity,
    COUNT(i.instance_id) FILTER (
        WHERE i.status <> 'terminating'
    ) AS actual_capacity,
    COUNT(i.instance_id) FILTER (
        WHERE i.status = 'healthy'
    ) AS healthy_capacity,
    COUNT(i.instance_id) FILTER (
        WHERE i.status = 'warming'
    ) AS warming_capacity,
    COUNT(i.instance_id) FILTER (
        WHERE i.status = 'unhealthy'
    ) AS unhealthy_capacity
FROM scaling_groups AS g
LEFT JOIN scaling_instances AS i USING (group_id)
GROUP BY
    g.group_id,
    g.group_name,
    g.minimum_capacity,
    g.desired_capacity,
    g.maximum_capacity;

SELECT *
FROM scaling_capacity_status
ORDER BY group_name;

-- Transactional capacity adjustment:
-- lock the group row, validate limits, update desired capacity, and record
-- the decision together. Concurrent controllers must use a consistent locking
-- protocol to prevent lost updates.
CREATE OR REPLACE FUNCTION request_capacity_change(
    p_group_id BIGINT,
    p_delta INTEGER,
    p_reason TEXT,
    p_policy_id BIGINT DEFAULT NULL
)
RETURNS TABLE (
    old_capacity INTEGER,
    new_capacity INTEGER,
    change_result TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_group scaling_groups%ROWTYPE;
    v_new_capacity INTEGER;
    v_direction scaling_direction;
BEGIN
    IF p_delta = 0 THEN
        RAISE EXCEPTION 'Capacity delta must not be zero';
    END IF;

    IF p_reason IS NULL OR length(trim(p_reason)) = 0 THEN
        RAISE EXCEPTION 'A reason is required for capacity changes';
    END IF;

    SELECT *
    INTO v_group
    FROM scaling_groups
    WHERE group_id = p_group_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Scaling group % does not exist', p_group_id;
    END IF;

    v_new_capacity := LEAST(
        v_group.maximum_capacity,
        GREATEST(
            v_group.minimum_capacity,
            v_group.desired_capacity + p_delta
        )
    );

    old_capacity := v_group.desired_capacity;
    new_capacity := v_new_capacity;

    IF v_new_capacity = v_group.desired_capacity THEN
        change_result := 'capacity_limit';
        INSERT INTO scaling_events (
            group_id,
            policy_id,
            direction,
            old_desired_capacity,
            new_desired_capacity,
            reason
        )
        VALUES (
            p_group_id,
            p_policy_id,
            'no_change',
            old_capacity,
            new_capacity,
            p_reason
        );
        RETURN NEXT;
        RETURN;
    END IF;

    v_direction := CASE
        WHEN v_new_capacity > v_group.desired_capacity THEN 'scale_out'
        ELSE 'scale_in'
    END;

    UPDATE scaling_groups
    SET desired_capacity = v_new_capacity
    WHERE group_id = p_group_id;

    INSERT INTO scaling_events (
        group_id,
        policy_id,
        direction,
        old_desired_capacity,
        new_desired_capacity,
        reason,
        metadata
    )
    VALUES (
        p_group_id,
        p_policy_id,
        v_direction,
        old_capacity,
        new_capacity,
        p_reason,
        jsonb_build_object(
            'requested_delta', p_delta,
            'bounded_delta', v_new_capacity - old_capacity
        )
    );

    change_result := v_direction::TEXT;
    RETURN NEXT;
END;
$$;

-- Demonstrate a policy-driven capacity change.
SELECT *
FROM request_capacity_change(
    (
        SELECT group_id
        FROM scaling_groups
        WHERE group_name = 'checkout-api'
    ),
    2,
    'Sustained CPU utilization above target',
    (
        SELECT policy_id
        FROM scaling_policies
        WHERE policy_name = 'cpu-target'
        AND group_id = (
            SELECT group_id
            FROM scaling_groups
            WHERE group_name = 'checkout-api'
        )
    )
);

-- Demonstrate a bounded scale-in request. Desired capacity cannot fall below
-- the minimum even when a controller requests a larger reduction.
SELECT *
FROM request_capacity_change(
    (
        SELECT group_id
        FROM scaling_groups
        WHERE group_name = 'checkout-api'
    ),
    -100,
    'Traffic reduction after sustained low utilization'
);

-- Process a due scheduled action once. FOR UPDATE SKIP LOCKED lets competing
-- workers claim separate rows without executing the same action concurrently.
WITH due_action AS (
    SELECT scheduled_action_id
    FROM scheduled_scaling_actions
    WHERE execution_status = 'pending'
      AND execute_at <= now()
    ORDER BY execute_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE scheduled_scaling_actions AS s
SET
    execution_status = 'executed',
    executed_at = now()
FROM due_action
WHERE s.scheduled_action_id = due_action.scheduled_action_id
RETURNING s.*;

-- Inspect decisions, including capacity changes rejected at group boundaries.
SELECT
    g.group_name,
    e.occurred_at,
    e.direction,
    e.old_desired_capacity,
    e.new_desired_capacity,
    e.reason,
    e.metadata
FROM scaling_events AS e
JOIN scaling_groups AS g USING (group_id)
ORDER BY e.occurred_at, e.event_id;

-- Integrity enforcement example:
-- the CHECK constraint rejects desired capacity outside the configured range.
-- Uncomment to observe the error:
-- UPDATE scaling_groups
-- SET desired_capacity = maximum_capacity + 1
-- WHERE group_name = 'checkout-api';

COMMIT;
