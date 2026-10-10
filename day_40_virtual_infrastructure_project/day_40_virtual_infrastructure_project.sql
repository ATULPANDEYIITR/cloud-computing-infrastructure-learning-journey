-- Virtual Infrastructure Project
-- PostgreSQL 15+
--
-- Relational control-plane model for multi-tenant virtual infrastructure.
-- Covers environments, users, role assignments, networks, IP allocations,
-- storage pools, volumes, virtual machines, lifecycle events, and auditing.
--
-- Execute in a dedicated database or schema where these object names are free.

BEGIN;

CREATE SCHEMA IF NOT EXISTS virtual_infrastructure;
SET search_path TO virtual_infrastructure, public;

CREATE TYPE environment_state AS ENUM (
    'active', 'suspended', 'deleted'
);

CREATE TYPE vm_state AS ENUM (
    'provisioning', 'stopped', 'running', 'suspended', 'terminated', 'failed'
);

CREATE TYPE user_role AS ENUM (
    'viewer', 'operator', 'admin'
);

CREATE TYPE volume_state AS ENUM (
    'available', 'attached', 'deleting'
);

CREATE TYPE infrastructure_event_type AS ENUM (
    'environment_created',
    'network_created',
    'storage_pool_created',
    'vm_created',
    'vm_started',
    'vm_stopped',
    'vm_suspended',
    'vm_terminated',
    'volume_created',
    'volume_attached',
    'volume_detached',
    'volume_deleted',
    'access_granted',
    'provisioning_failed'
);

CREATE TABLE infrastructure_users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    role user_role NOT NULL DEFAULT 'viewer',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT username_format CHECK (
        username ~ '^[A-Za-z][A-Za-z0-9_-]{1,62}$'
    )
);

CREATE TABLE environments (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    state environment_state NOT NULL DEFAULT 'active',
    max_vms INTEGER NOT NULL,
    max_vcpus INTEGER NOT NULL,
    max_memory_mib BIGINT NOT NULL,
    max_storage_gib BIGINT NOT NULL,
    created_by BIGINT NOT NULL REFERENCES infrastructure_users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT environment_key_format CHECK (
        environment_key ~ '^[A-Za-z][A-Za-z0-9_-]{1,62}$'
    ),
    CONSTRAINT environment_quota_valid CHECK (
        max_vms > 0
        AND max_vcpus > 0
        AND max_memory_mib >= 128
        AND max_storage_gib > 0
    )
);

CREATE TABLE environment_memberships (
    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id) ON DELETE RESTRICT,
    user_id BIGINT NOT NULL
        REFERENCES infrastructure_users(user_id) ON DELETE RESTRICT,
    granted_by BIGINT NOT NULL
        REFERENCES infrastructure_users(user_id) ON DELETE RESTRICT,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (environment_id, user_id)
);

CREATE TABLE virtual_networks (
    network_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id) ON DELETE RESTRICT,
    network_key TEXT NOT NULL UNIQUE,
    cidr CIDR NOT NULL,
    gateway INET NOT NULL,
    vlan_id INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT vlan_range CHECK (vlan_id BETWEEN 1 AND 4094),
    CONSTRAINT gateway_ipv4 CHECK (family(gateway) = 4),
    CONSTRAINT gateway_in_subnet CHECK (gateway <<= cidr),
    CONSTRAINT gateway_not_network_address CHECK (
        gateway <> network(cidr)
    ),
    CONSTRAINT gateway_not_broadcast_address CHECK (
        gateway <> broadcast(cidr)
    ),
    CONSTRAINT network_key_format CHECK (
        network_key ~ '^[A-Za-z][A-Za-z0-9_-]{1,62}$'
    ),
    UNIQUE (environment_id, network_key)
);

-- Exclusion constraints prevent overlapping managed subnets.
-- btree_gist is a standard PostgreSQL extension used to combine scalar
-- equality with range-like GiST operators.
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE virtual_networks
    ADD CONSTRAINT no_overlapping_environment_subnets
    EXCLUDE USING gist (
        cidr inet_ops WITH &&
    );

-- A separate table makes IP ownership explicit and allows the database
-- to reject duplicate address assignments within a network.
CREATE TABLE ip_allocations (
    allocation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    network_id BIGINT NOT NULL
        REFERENCES virtual_networks(network_id) ON DELETE RESTRICT,
    address INET NOT NULL,
    vm_id BIGINT,
    reserved_reason TEXT,
    allocated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ipv4_allocation CHECK (family(address) = 4),
    CONSTRAINT address_has_owner_or_reservation CHECK (
        vm_id IS NOT NULL OR reserved_reason IS NOT NULL
    ),
    UNIQUE (network_id, address)
);

CREATE TABLE storage_pools (
    pool_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id) ON DELETE RESTRICT,
    pool_key TEXT NOT NULL UNIQUE,
    capacity_gib BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT storage_pool_capacity CHECK (capacity_gib > 0),
    CONSTRAINT pool_key_format CHECK (
        pool_key ~ '^[A-Za-z][A-Za-z0-9_-]{1,62}$'
    ),
    UNIQUE (environment_id, pool_key)
);

CREATE TABLE virtual_machines (
    vm_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id) ON DELETE RESTRICT,
    network_id BIGINT NOT NULL
        REFERENCES virtual_networks(network_id) ON DELETE RESTRICT,
    vm_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    image_reference TEXT NOT NULL,
    vcpus INTEGER NOT NULL,
    memory_mib BIGINT NOT NULL,
    state vm_state NOT NULL DEFAULT 'provisioning',
    created_by BIGINT NOT NULL
        REFERENCES infrastructure_users(user_id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    terminated_at TIMESTAMPTZ,
    CONSTRAINT vm_resource_bounds CHECK (
        vcpus BETWEEN 1 AND 128
        AND memory_mib BETWEEN 128 AND 1048576
    ),
    CONSTRAINT vm_key_format CHECK (
        vm_key ~ '^[A-Za-z][A-Za-z0-9_-]{1,62}$'
    ),
    CONSTRAINT vm_image_nonempty CHECK (
        length(trim(image_reference)) > 0
    ),
    UNIQUE (environment_id, vm_key),
    UNIQUE (vm_id, network_id, environment_id)
);

-- The composite foreign key guarantees that a VM can use only a network
-- belonging to its own environment.
ALTER TABLE virtual_networks
    ADD CONSTRAINT network_id_environment_unique
    UNIQUE (network_id, environment_id);

ALTER TABLE virtual_machines
    ADD CONSTRAINT vm_network_environment_isolation
    FOREIGN KEY (network_id, environment_id)
    REFERENCES virtual_networks(network_id, environment_id)
    ON DELETE RESTRICT;

-- Complete the IP allocation relationship after the VM table exists.
ALTER TABLE ip_allocations
    ADD CONSTRAINT allocation_vm_network_environment
    FOREIGN KEY (vm_id, network_id, (
        SELECT environment_id
        FROM virtual_networks
        WHERE virtual_networks.network_id = ip_allocations.network_id
    ))
    REFERENCES virtual_machines(vm_id, network_id, environment_id);

-- PostgreSQL does not allow a subquery in a foreign-key column definition.
-- Replace the preceding illustrative relationship with direct ownership
-- references enforced through triggers.
ALTER TABLE ip_allocations
    DROP CONSTRAINT IF EXISTS allocation_vm_network_environment;

ALTER TABLE ip_allocations
    ADD CONSTRAINT allocation_vm_fk
    FOREIGN KEY (vm_id)
    REFERENCES virtual_machines(vm_id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX one_dynamic_ip_per_vm
    ON ip_allocations(vm_id)
    WHERE vm_id IS NOT NULL;

CREATE TABLE storage_volumes (
    volume_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id) ON DELETE RESTRICT,
    pool_id BIGINT NOT NULL
        REFERENCES storage_pools(pool_id) ON DELETE RESTRICT,
    volume_key TEXT NOT NULL UNIQUE,
    size_gib BIGINT NOT NULL,
    encrypted BOOLEAN NOT NULL DEFAULT TRUE,
    state volume_state NOT NULL DEFAULT 'available',
    created_by BIGINT NOT NULL
        REFERENCES infrastructure_users(user_id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT volume_size_valid CHECK (size_gib > 0),
    CONSTRAINT volume_key_format CHECK (
        volume_key ~ '^[A-Za-z][A-Za-z0-9_-]{1,62}$'
    ),
    UNIQUE (environment_id, volume_key),
    UNIQUE (volume_id, environment_id)
);

-- A pool must belong to the same environment as the volume.
ALTER TABLE storage_pools
    ADD CONSTRAINT pool_id_environment_unique
    UNIQUE (pool_id, environment_id);

ALTER TABLE storage_volumes
    ADD CONSTRAINT volume_pool_environment_isolation
    FOREIGN KEY (pool_id, environment_id)
    REFERENCES storage_pools(pool_id, environment_id)
    ON DELETE RESTRICT;

CREATE TABLE volume_attachments (
    volume_id BIGINT PRIMARY KEY
        REFERENCES storage_volumes(volume_id) ON DELETE RESTRICT,
    vm_id BIGINT NOT NULL
        REFERENCES virtual_machines(vm_id) ON DELETE RESTRICT,
    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id) ON DELETE RESTRICT,
    attached_by BIGINT NOT NULL
        REFERENCES infrastructure_users(user_id) ON DELETE RESTRICT,
    attached_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT one_attachment_per_volume UNIQUE (volume_id, vm_id)
);

-- Enforce the same-environment attachment rule at the relational layer.
ALTER TABLE virtual_machines
    ADD CONSTRAINT vm_id_environment_unique
    UNIQUE (vm_id, environment_id);

ALTER TABLE volume_attachments
    ADD CONSTRAINT attachment_vm_environment_isolation
    FOREIGN KEY (vm_id, environment_id)
    REFERENCES virtual_machines(vm_id, environment_id)
    ON DELETE RESTRICT;

ALTER TABLE volume_attachments
    ADD CONSTRAINT attachment_volume_environment_isolation
    FOREIGN KEY (volume_id, environment_id)
    REFERENCES storage_volumes(volume_id, environment_id)
    ON DELETE RESTRICT;

CREATE TABLE infrastructure_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_id BIGINT
        REFERENCES environments(environment_id) ON DELETE RESTRICT,
    actor_id BIGINT
        REFERENCES infrastructure_users(user_id) ON DELETE RESTRICT,
    event_type infrastructure_event_type NOT NULL,
    resource_type TEXT NOT NULL,
    resource_key TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (
        outcome IN ('success', 'failure', 'rejected')
    ),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE vm_status_checks (
    status_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id BIGINT NOT NULL
        REFERENCES virtual_machines(vm_id) ON DELETE RESTRICT,
    check_name TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX vm_environment_state_idx
    ON virtual_machines(environment_id, state);

CREATE INDEX vm_network_idx
    ON virtual_machines(network_id);

CREATE INDEX volume_environment_pool_idx
    ON storage_volumes(environment_id, pool_id);

CREATE INDEX event_environment_time_idx
    ON infrastructure_events(environment_id, occurred_at DESC);

CREATE INDEX status_check_latest_idx
    ON vm_status_checks(vm_id, checked_at DESC);

-- This trigger enforces basic state consistency and updated timestamps.
CREATE FUNCTION enforce_vm_state_consistency()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.state = 'terminated' AND NEW.state <> 'terminated' THEN
        RAISE EXCEPTION 'A terminated VM cannot return to an active state';
    END IF;

    IF NEW.state = 'terminated' AND NEW.terminated_at IS NULL THEN
        NEW.terminated_at := now();
    END IF;

    IF NEW.state <> 'terminated' THEN
        NEW.terminated_at := NULL;
    END IF;

    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER vm_state_consistency_trigger
BEFORE UPDATE OF state ON virtual_machines
FOR EACH ROW
EXECUTE FUNCTION enforce_vm_state_consistency();

-- The database validates that an assigned IP is inside its network and
-- that the network belongs to the VM's environment.
CREATE FUNCTION validate_ip_allocation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    network_cidr CIDR;
    network_environment BIGINT;
    vm_environment BIGINT;
BEGIN
    SELECT cidr, environment_id
      INTO network_cidr, network_environment
      FROM virtual_networks
     WHERE network_id = NEW.network_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Network % does not exist', NEW.network_id;
    END IF;

    IF NOT (NEW.address <<= network_cidr) THEN
        RAISE EXCEPTION 'IP address % is outside network %',
            NEW.address, network_cidr;
    END IF;

    IF NEW.address = network(network_cidr)
       OR NEW.address = broadcast(network_cidr) THEN
        RAISE EXCEPTION 'Network and broadcast addresses cannot be allocated';
    END IF;

    IF NEW.vm_id IS NOT NULL THEN
        SELECT environment_id
          INTO vm_environment
          FROM virtual_machines
         WHERE vm_id = NEW.vm_id
           AND network_id = NEW.network_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'VM must exist and use the allocated network';
        END IF;

        IF vm_environment <> network_environment THEN
            RAISE EXCEPTION 'Cross-environment IP assignment is prohibited';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER ip_allocation_validation_trigger
BEFORE INSERT OR UPDATE ON ip_allocations
FOR EACH ROW
EXECUTE FUNCTION validate_ip_allocation();

-- A trigger rejects attachments to terminated VMs and inconsistent volume
-- states. Composite foreign keys independently enforce environment isolation.
CREATE FUNCTION validate_volume_attachment()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    current_state vm_state;
BEGIN
    SELECT state
      INTO current_state
      FROM virtual_machines
     WHERE vm_id = NEW.vm_id
       AND environment_id = NEW.environment_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'VM is not available in the selected environment';
    END IF;

    IF current_state = 'terminated' THEN
        RAISE EXCEPTION 'Cannot attach a volume to a terminated VM';
    END IF;

    UPDATE storage_volumes
       SET state = 'attached'
     WHERE volume_id = NEW.volume_id
       AND environment_id = NEW.environment_id
       AND state = 'available';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Volume is not available for attachment';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER volume_attachment_validation_trigger
BEFORE INSERT ON volume_attachments
FOR EACH ROW
EXECUTE FUNCTION validate_volume_attachment();

CREATE FUNCTION restore_volume_state_after_detachment()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE storage_volumes
       SET state = 'available'
     WHERE volume_id = OLD.volume_id
       AND state = 'attached';

    INSERT INTO infrastructure_events (
        environment_id, actor_id, event_type,
        resource_type, resource_key, outcome, details
    )
    VALUES (
        OLD.environment_id, OLD.attached_by, 'volume_detached',
        'volume', OLD.volume_id::text, 'success',
        jsonb_build_object('vm_id', OLD.vm_id)
    );

    RETURN OLD;
END;
$$;

CREATE TRIGGER volume_detachment_state_trigger
AFTER DELETE ON volume_attachments
FOR EACH ROW
EXECUTE FUNCTION restore_volume_state_after_detachment();

-- The view reports aggregate allocations. Capacity enforcement that spans
-- multiple rows requires locking or serializable transactions in write paths.
CREATE VIEW environment_resource_inventory AS
SELECT
    e.environment_id,
    e.environment_key,
    e.name,
    e.state,
    e.max_vms,
    COUNT(vm.vm_id) FILTER (
        WHERE vm.state <> 'terminated'
    ) AS active_vms,
    COUNT(vm.vm_id) FILTER (
        WHERE vm.state = 'running'
    ) AS running_vms,
    COALESCE(SUM(vm.vcpus) FILTER (
        WHERE vm.state <> 'terminated'
    ), 0) AS allocated_vcpus,
    COALESCE(SUM(vm.memory_mib) FILTER (
        WHERE vm.state <> 'terminated'
    ), 0) AS allocated_memory_mib,
    e.max_storage_gib,
    COALESCE((
        SELECT SUM(sp.capacity_gib)
          FROM storage_pools sp
         WHERE sp.environment_id = e.environment_id
    ), 0) AS storage_pool_capacity_gib,
    COALESCE((
        SELECT SUM(sv.size_gib)
          FROM storage_volumes sv
         WHERE sv.environment_id = e.environment_id
    ), 0) AS provisioned_volume_gib
FROM environments e
LEFT JOIN virtual_machines vm
    ON vm.environment_id = e.environment_id
GROUP BY
    e.environment_id,
    e.environment_key,
    e.name,
    e.state,
    e.max_vms,
    e.max_storage_gib;

-- Sample infrastructure records.
INSERT INTO infrastructure_users (username, role)
VALUES
    ('cloud_admin', 'admin'),
    ('application_operator', 'operator'),
    ('security_auditor', 'viewer');

INSERT INTO environments (
    environment_key, name, max_vms, max_vcpus,
    max_memory_mib, max_storage_gib, created_by
)
SELECT
    'engineering',
    'Engineering Sandbox',
    8,
    24,
    32768,
    300,
    user_id
FROM infrastructure_users
WHERE username = 'cloud_admin';

INSERT INTO environment_memberships (
    environment_id, user_id, granted_by
)
SELECT
    e.environment_id,
    u.user_id,
    admin.user_id
FROM environments e
CROSS JOIN infrastructure_users u
CROSS JOIN infrastructure_users admin
WHERE e.environment_key = 'engineering'
  AND u.username IN ('application_operator', 'security_auditor')
  AND admin.username = 'cloud_admin';

INSERT INTO virtual_networks (
    environment_id, network_key, cidr, gateway, vlan_id
)
SELECT
    environment_id,
    'engineering_net',
    '10.90.1.0/24'::cidr,
    '10.90.1.1'::inet,
    190
FROM environments
WHERE environment_key = 'engineering';

INSERT INTO storage_pools (
    environment_id, pool_key, capacity_gib
)
SELECT environment_id, 'engineering_pool', 200
FROM environments
WHERE environment_key = 'engineering';

INSERT INTO virtual_machines (
    environment_id, network_id, vm_key, name,
    image_reference, vcpus, memory_mib, state, created_by
)
SELECT
    e.environment_id,
    n.network_id,
    'api_server',
    'API Service',
    'ubuntu-24.04',
    4,
    8192,
    'stopped',
    u.user_id
FROM environments e
JOIN virtual_networks n
  ON n.environment_id = e.environment_id
 AND n.network_key = 'engineering_net'
JOIN infrastructure_users u
  ON u.username = 'application_operator'
WHERE e.environment_key = 'engineering';

INSERT INTO ip_allocations (
    network_id, address, vm_id
)
SELECT
    n.network_id,
    '10.90.1.10'::inet,
    vm.vm_id
FROM virtual_networks n
JOIN virtual_machines vm
  ON vm.network_id = n.network_id
WHERE n.network_key = 'engineering_net'
  AND vm.vm_key = 'api_server';

INSERT INTO storage_volumes (
    environment_id, pool_id, volume_key,
    size_gib, encrypted, created_by
)
SELECT
    e.environment_id,
    p.pool_id,
    'api_data',
    40,
    TRUE,
    u.user_id
FROM environments e
JOIN storage_pools p
  ON p.environment_id = e.environment_id
 AND p.pool_key = 'engineering_pool'
JOIN infrastructure_users u
  ON u.username = 'application_operator'
WHERE e.environment_key = 'engineering';

-- Attach the data volume through the guarded attachment workflow.
INSERT INTO volume_attachments (
    volume_id, vm_id, environment_id, attached_by
)
SELECT
    v.volume_id,
    vm.vm_id,
    e.environment_id,
    u.user_id
FROM storage_volumes v
JOIN environments e
  ON e.environment_id = v.environment_id
JOIN virtual_machines vm
  ON vm.environment_id = e.environment_id
JOIN infrastructure_users u
  ON u.username = 'application_operator'
WHERE e.environment_key = 'engineering'
  AND v.volume_key = 'api_data'
  AND vm.vm_key = 'api_server';

UPDATE virtual_machines
SET state = 'running'
WHERE vm_key = 'api_server';

INSERT INTO infrastructure_events (
    environment_id, actor_id, event_type,
    resource_type, resource_key, outcome, details
)
SELECT
    e.environment_id,
    u.user_id,
    'vm_started',
    'vm',
    vm.vm_key,
    'success',
    jsonb_build_object(
        'state', vm.state,
        'vcpus', vm.vcpus,
        'memory_mib', vm.memory_mib
    )
FROM virtual_machines vm
JOIN environments e
  ON e.environment_id = vm.environment_id
JOIN infrastructure_users u
  ON u.username = 'application_operator'
WHERE vm.vm_key = 'api_server';

-- Operational queries.
SELECT *
FROM environment_resource_inventory
WHERE environment_key = 'engineering';

SELECT
    vm.vm_key,
    vm.state,
    vm.vcpus,
    vm.memory_mib,
    network.network_key,
    allocation.address,
    volume.volume_key,
    volume.size_gib,
    volume.encrypted
FROM virtual_machines vm
JOIN virtual_networks network
  ON network.network_id = vm.network_id
LEFT JOIN ip_allocations allocation
  ON allocation.vm_id = vm.vm_id
LEFT JOIN volume_attachments attachment
  ON attachment.vm_id = vm.vm_id
LEFT JOIN storage_volumes volume
  ON volume.volume_id = attachment.volume_id
WHERE vm.environment_id = (
    SELECT environment_id
    FROM environments
    WHERE environment_key = 'engineering'
)
ORDER BY vm.vm_key, volume.volume_key;

-- Identify environments whose compute quotas have been exceeded.
WITH compute_usage AS (
    SELECT
        e.environment_id,
        e.environment_key,
        e.max_vms,
        e.max_vcpus,
        e.max_memory_mib,
        COUNT(vm.vm_id) FILTER (
            WHERE vm.state <> 'terminated'
        ) AS active_vms,
        COALESCE(SUM(vm.vcpus) FILTER (
            WHERE vm.state <> 'terminated'
        ), 0) AS allocated_vcpus,
        COALESCE(SUM(vm.memory_mib) FILTER (
            WHERE vm.state <> 'terminated'
        ), 0) AS allocated_memory_mib
    FROM environments e
    LEFT JOIN virtual_machines vm
      ON vm.environment_id = e.environment_id
    GROUP BY
        e.environment_id,
        e.environment_key,
        e.max_vms,
        e.max_vcpus,
        e.max_memory_mib
)
SELECT *,
    active_vms > max_vms AS vm_quota_exceeded,
    allocated_vcpus > max_vcpus AS vcpu_quota_exceeded,
    allocated_memory_mib > max_memory_mib AS memory_quota_exceeded
FROM compute_usage;

-- Storage usage by pool.
SELECT
    pool.pool_key,
    pool.capacity_gib,
    COALESCE(SUM(volume.size_gib), 0) AS provisioned_gib,
    pool.capacity_gib - COALESCE(SUM(volume.size_gib), 0) AS remaining_gib
FROM storage_pools pool
LEFT JOIN storage_volumes volume
  ON volume.pool_id = pool.pool_id
GROUP BY pool.pool_id, pool.pool_key, pool.capacity_gib
ORDER BY pool.pool_key;

-- Demonstrate transaction rollback for an invalid capacity reservation.
-- This example uses a savepoint so the remainder of the script can continue.
SAVEPOINT before_invalid_volume;

DO $$
DECLARE
    selected_environment BIGINT;
    selected_pool BIGINT;
    selected_user BIGINT;
    available_gib BIGINT;
BEGIN
    SELECT environment_id
      INTO selected_environment
      FROM environments
     WHERE environment_key = 'engineering';

    SELECT pool_id, capacity_gib -
        COALESCE((
            SELECT SUM(size_gib)
            FROM storage_volumes
            WHERE storage_volumes.pool_id = storage_pools.pool_id
        ), 0)
      INTO selected_pool, available_gib
      FROM storage_pools
     WHERE environment_id = selected_environment
       AND pool_key = 'engineering_pool';

    SELECT user_id
      INTO selected_user
      FROM infrastructure_users
     WHERE username = 'application_operator';

    IF available_gib < 1000 THEN
        RAISE NOTICE
            'Rejected 1000 GiB reservation: only % GiB remain',
            available_gib;
    ELSE
        INSERT INTO storage_volumes (
            environment_id, pool_id, volume_key,
            size_gib, encrypted, created_by
        )
        VALUES (
            selected_environment, selected_pool, 'invalid_capacity_test',
            1000, TRUE, selected_user
        );
    END IF;
END;
$$;

RELEASE SAVEPOINT before_invalid_volume;

-- PostgreSQL transactional note:
-- Row-level CHECK constraints cannot enforce aggregate quotas across multiple
-- rows. Concurrent provisioning must lock the environment row, check aggregate
-- usage, insert the resource, and commit in the same transaction. A service
-- should use a consistent locking protocol or SERIALIZABLE isolation with
-- retry handling. The reporting view is diagnostic, not a concurrency guard.

COMMIT;
