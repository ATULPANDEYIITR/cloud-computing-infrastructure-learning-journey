-- Containers vs Virtual Machines
-- PostgreSQL 16+ compatible relational model.
--
-- The schema represents an infrastructure inventory in which workloads can
-- run as containers or virtual machines. Constraints protect resource and
-- lifecycle invariants at the database layer.
--
-- The model focuses on:
--   isolation
--   performance
--   portability
--   resource utilization
--   workload comparison

DROP SCHEMA IF EXISTS virtualization_lab CASCADE;
CREATE SCHEMA virtualization_lab;

SET search_path TO virtualization_lab;

CREATE TYPE workload_type AS ENUM (
    'web_api',
    'database',
    'legacy_application',
    'batch',
    'multi_service'
);

CREATE TYPE runtime_type AS ENUM (
    'container',
    'virtual_machine'
);

CREATE TYPE workload_state AS ENUM (
    'planned',
    'running',
    'stopped',
    'failed'
);

CREATE TYPE deployment_state AS ENUM (
    'proposed',
    'deployed',
    'failed',
    'retired'
);

CREATE TABLE architecture (
    architecture_code TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

CREATE TABLE host (
    host_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    host_name TEXT NOT NULL UNIQUE,
    architecture_code TEXT NOT NULL
        REFERENCES architecture(architecture_code),
    cpu_cores NUMERIC(8,2) NOT NULL
        CHECK (cpu_cores > 0),
    memory_gb NUMERIC(10,2) NOT NULL
        CHECK (memory_gb > 0),
    storage_gb NUMERIC(12,2) NOT NULL
        CHECK (storage_gb > 0),
    container_runtime_supported BOOLEAN NOT NULL DEFAULT TRUE,
    hypervisor_supported BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE workload (
    workload_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workload_name TEXT NOT NULL UNIQUE,
    workload_type workload_type NOT NULL,
    requested_cpu NUMERIC(8,2) NOT NULL
        CHECK (requested_cpu > 0),
    requested_memory_gb NUMERIC(10,2) NOT NULL
        CHECK (requested_memory_gb > 0),
    requested_storage_gb NUMERIC(12,2) NOT NULL
        CHECK (requested_storage_gb >= 0),
    architecture_code TEXT NOT NULL
        REFERENCES architecture(architecture_code),
    requires_custom_kernel BOOLEAN NOT NULL DEFAULT FALSE,
    untrusted_code BOOLEAN NOT NULL DEFAULT FALSE,
    state workload_state NOT NULL DEFAULT 'planned'
);

CREATE TABLE runtime_profile (
    runtime_profile_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    runtime_type runtime_type NOT NULL UNIQUE,
    cpu_overhead NUMERIC(8,3) NOT NULL
        CHECK (cpu_overhead >= 0),
    memory_overhead_gb NUMERIC(8,3) NOT NULL
        CHECK (memory_overhead_gb >= 0),
    startup_seconds NUMERIC(10,2) NOT NULL
        CHECK (startup_seconds >= 0),
    isolation_score NUMERIC(4,3) NOT NULL
        CHECK (isolation_score BETWEEN 0 AND 1),
    portability_score NUMERIC(4,3) NOT NULL
        CHECK (portability_score BETWEEN 0 AND 1),
    kernel_boundary TEXT NOT NULL
);

CREATE TABLE deployment (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workload_id BIGINT NOT NULL
        REFERENCES workload(workload_id),
    host_id BIGINT NOT NULL
        REFERENCES host(host_id),
    runtime_profile_id BIGINT NOT NULL
        REFERENCES runtime_profile(runtime_profile_id),
    runtime_name TEXT NOT NULL,
    cpu_limit NUMERIC(8,2) NOT NULL
        CHECK (cpu_limit > 0),
    memory_limit_gb NUMERIC(10,2) NOT NULL
        CHECK (memory_limit_gb > 0),
    state deployment_state NOT NULL DEFAULT 'proposed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT deployment_runtime_name_unique
        UNIQUE (host_id, runtime_name)
);

CREATE INDEX idx_workload_type
    ON workload(workload_type);

CREATE INDEX idx_workload_state
    ON workload(state);

CREATE INDEX idx_deployment_host_state
    ON deployment(host_id, state);

CREATE INDEX idx_deployment_workload
    ON deployment(workload_id);

INSERT INTO architecture (
    architecture_code,
    description
) VALUES
    ('x86_64', '64-bit x86 architecture'),
    ('arm64', '64-bit ARM architecture');

INSERT INTO runtime_profile (
    runtime_type,
    cpu_overhead,
    memory_overhead_gb,
    startup_seconds,
    isolation_score,
    portability_score,
    kernel_boundary
) VALUES
    (
        'container',
        0.020,
        0.080,
        0.80,
        0.720,
        0.950,
        'Shared host kernel with process and namespace isolation'
    ),
    (
        'virtual_machine',
        0.200,
        0.650,
        22.00,
        0.960,
        0.820,
        'Independent guest kernel behind virtual hardware'
    );

INSERT INTO host (
    host_name,
    architecture_code,
    cpu_cores,
    memory_gb,
    storage_gb,
    container_runtime_supported,
    hypervisor_supported
) VALUES
    (
        'container-node-01',
        'x86_64',
        16,
        32,
        500,
        TRUE,
        TRUE
    ),
    (
        'legacy-vm-node-01',
        'x86_64',
        32,
        64,
        1000,
        TRUE,
        TRUE
    ),
    (
        'arm-edge-node-01',
        'arm64',
        8,
        16,
        250,
        TRUE,
        FALSE
    );

INSERT INTO workload (
    workload_name,
    workload_type,
    requested_cpu,
    requested_memory_gb,
    requested_storage_gb,
    architecture_code,
    requires_custom_kernel,
    untrusted_code,
    state
) VALUES
    (
        'customer-api',
        'web_api',
        1,
        1,
        5,
        'x86_64',
        FALSE,
        FALSE,
        'running'
    ),
    (
        'analytics-batch',
        'batch',
        4,
        8,
        25,
        'x86_64',
        FALSE,
        FALSE,
        'running'
    ),
    (
        'legacy-payment',
        'legacy_application',
        2,
        4,
        40,
        'x86_64',
        TRUE,
        FALSE,
        'running'
    ),
    (
        'orders-database',
        'database',
        4,
        12,
        200,
        'x86_64',
        FALSE,
        FALSE,
        'running'
    ),
    (
        'untrusted-code-job',
        'batch',
        1,
        2,
        5,
        'x86_64',
        FALSE,
        TRUE,
        'planned'
    );

-- The following view exposes the resource cost of each runtime model.
CREATE VIEW runtime_resource_profile AS
SELECT
    runtime_type,
    cpu_overhead,
    memory_overhead_gb,
    startup_seconds,
    isolation_score,
    portability_score,
    kernel_boundary
FROM runtime_profile;

-- A workload comparison query makes the isolation/performance trade-off
-- visible without pretending that one runtime is universally superior.
SELECT
    w.workload_name,
    w.workload_type,
    rp.runtime_type,
    w.requested_cpu,
    w.requested_memory_gb,
    rp.cpu_overhead,
    rp.memory_overhead_gb,
    rp.startup_seconds,
    rp.isolation_score,
    rp.portability_score
FROM workload AS w
CROSS JOIN runtime_profile AS rp
ORDER BY
    w.workload_name,
    rp.runtime_type;

-- Runtime selection based on workload requirements.
-- A custom kernel requirement is treated as a VM-specific requirement.
SELECT
    workload_name,
    workload_type,
    CASE
        WHEN requires_custom_kernel
            THEN 'virtual_machine'
        WHEN workload_type IN ('web_api', 'batch', 'multi_service')
            THEN 'container'
        WHEN workload_type = 'legacy_application'
            THEN 'virtual_machine'
        ELSE
            'requires_architectural_review'
    END AS initial_runtime_recommendation
FROM workload
ORDER BY workload_name;

-- Compare aggregate theoretical overhead by runtime type.
SELECT
    runtime_type,
    COUNT(*) AS modeled_workload_options,
    SUM(cpu_overhead) AS aggregate_cpu_overhead,
    SUM(memory_overhead_gb) AS aggregate_memory_overhead_gb,
    AVG(startup_seconds) AS average_startup_seconds,
    AVG(isolation_score) AS average_isolation_score,
    AVG(portability_score) AS average_portability_score
FROM runtime_profile
GROUP BY runtime_type
ORDER BY runtime_type;

-- Deploy workloads that satisfy the basic architecture and runtime
-- compatibility rules. The INSERT is deliberately limited to safe examples.
INSERT INTO deployment (
    workload_id,
    host_id,
    runtime_profile_id,
    runtime_name,
    cpu_limit,
    memory_limit_gb,
    state
)
SELECT
    w.workload_id,
    h.host_id,
    rp.runtime_profile_id,
    'customer-api-container',
    1,
    1,
    'deployed'
FROM workload AS w
JOIN host AS h
    ON h.host_name = 'container-node-01'
JOIN runtime_profile AS rp
    ON rp.runtime_type = 'container'
WHERE w.workload_name = 'customer-api'
  AND h.architecture_code = w.architecture_code
  AND h.container_runtime_supported = TRUE
  AND 1 >= w.requested_cpu
  AND 1 >= w.requested_memory_gb;

-- Deploy the legacy application into a VM because it requires kernel
-- independence.
INSERT INTO deployment (
    workload_id,
    host_id,
    runtime_profile_id,
    runtime_name,
    cpu_limit,
    memory_limit_gb,
    state
)
SELECT
    w.workload_id,
    h.host_id,
    rp.runtime_profile_id,
    'legacy-payment-vm',
    2,
    4,
    'deployed'
FROM workload AS w
JOIN host AS h
    ON h.host_name = 'legacy-vm-node-01'
JOIN runtime_profile AS rp
    ON rp.runtime_type = 'virtual_machine'
WHERE w.workload_name = 'legacy-payment'
  AND h.architecture_code = w.architecture_code
  AND h.hypervisor_supported = TRUE
  AND 2 >= w.requested_cpu
  AND 4 >= w.requested_memory_gb;

-- Detect deployments that violate the workload's requested resource floor.
SELECT
    d.deployment_id,
    d.runtime_name,
    w.workload_name,
    d.cpu_limit,
    w.requested_cpu,
    d.memory_limit_gb,
    w.requested_memory_gb
FROM deployment AS d
JOIN workload AS w
    ON w.workload_id = d.workload_id
WHERE d.cpu_limit < w.requested_cpu
   OR d.memory_limit_gb < w.requested_memory_gb;

-- Host-level resource accounting.
SELECT
    h.host_name,
    h.cpu_cores,
    COALESCE(SUM(d.cpu_limit)
        FILTER (WHERE d.state = 'deployed'), 0) AS allocated_cpu,
    h.memory_gb,
    COALESCE(SUM(d.memory_limit_gb)
        FILTER (WHERE d.state = 'deployed'), 0) AS allocated_memory_gb,
    h.storage_gb,
    COALESCE(SUM(w.requested_storage_gb)
        FILTER (WHERE d.state = 'deployed'), 0) AS allocated_storage_gb
FROM host AS h
LEFT JOIN deployment AS d
    ON d.host_id = h.host_id
LEFT JOIN workload AS w
    ON w.workload_id = d.workload_id
GROUP BY
    h.host_id,
    h.host_name,
    h.cpu_cores,
    h.memory_gb,
    h.storage_gb
ORDER BY h.host_name;

-- Identify workloads for which a VM offers a stronger isolation boundary
-- while a container offers lower startup overhead.
SELECT
    w.workload_name,
    c.startup_seconds AS container_startup_seconds,
    v.startup_seconds AS vm_startup_seconds,
    c.isolation_score AS container_isolation,
    v.isolation_score AS vm_isolation,
    v.isolation_score - c.isolation_score AS isolation_difference,
    c.startup_seconds - v.startup_seconds AS startup_difference
FROM workload AS w
CROSS JOIN runtime_profile AS c
CROSS JOIN runtime_profile AS v
WHERE c.runtime_type = 'container'
  AND v.runtime_type = 'virtual_machine'
ORDER BY w.workload_name;

-- Transactional example: a workload migration is represented as one
-- atomic database operation. If any statement fails, the old deployment
-- remains unchanged when the transaction is rolled back.
BEGIN;

UPDATE deployment
SET state = 'retired'
WHERE runtime_name = 'customer-api-container'
  AND state = 'deployed';

-- The new VM deployment is intentionally shown for the same workload to
-- demonstrate that runtime migration is a stateful infrastructure change.
INSERT INTO deployment (
    workload_id,
    host_id,
    runtime_profile_id,
    runtime_name,
    cpu_limit,
    memory_limit_gb,
    state
)
SELECT
    w.workload_id,
    h.host_id,
    rp.runtime_profile_id,
    'customer-api-migrated-vm',
    1,
    1,
    'deployed'
FROM workload AS w
JOIN host AS h
    ON h.host_name = 'legacy-vm-node-01'
JOIN runtime_profile AS rp
    ON rp.runtime_type = 'virtual_machine'
WHERE w.workload_name = 'customer-api'
  AND h.architecture_code = w.architecture_code
  AND h.hypervisor_supported = TRUE;

COMMIT;

-- Post-migration state.
SELECT
    w.workload_name,
    d.runtime_name,
    rp.runtime_type,
    d.state
FROM deployment AS d
JOIN workload AS w
    ON w.workload_id = d.workload_id
JOIN runtime_profile AS rp
    ON rp.runtime_profile_id = d.runtime_profile_id
WHERE w.workload_name = 'customer-api'
ORDER BY d.deployment_id;
