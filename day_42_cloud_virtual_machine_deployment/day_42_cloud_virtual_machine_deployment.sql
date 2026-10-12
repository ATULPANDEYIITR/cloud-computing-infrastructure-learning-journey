-- PostgreSQL 15+
-- Relational cloud VM deployment, image governance, network access controls,
-- SSH public-key registration, lifecycle history, and cost reporting.
-- The database models infrastructure metadata only; it creates no real VMs.

BEGIN;

CREATE SCHEMA IF NOT EXISTS cloud_ops;
SET LOCAL search_path TO cloud_ops, public;

CREATE TYPE image_status AS ENUM ('available', 'deprecated', 'disabled');
CREATE TYPE machine_architecture AS ENUM ('x86_64', 'arm64');
CREATE TYPE instance_state AS ENUM (
    'pending', 'running', 'stopped', 'failed', 'terminated'
);
CREATE TYPE network_protocol AS ENUM ('tcp', 'udp');

CREATE TABLE cloud_regions (
    region_code TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (region_code ~ '^[a-z]{2}-[a-z]+-[0-9]+$')
);

CREATE TABLE machine_types (
    machine_type_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    architecture machine_architecture NOT NULL,
    vcpus INTEGER NOT NULL CHECK (vcpus > 0),
    memory_gib INTEGER NOT NULL CHECK (memory_gib > 0),
    hourly_compute_cost NUMERIC(12, 6) NOT NULL
        CHECK (hourly_compute_cost >= 0),
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE images (
    image_id TEXT PRIMARY KEY,
    publisher TEXT NOT NULL,
    image_name TEXT NOT NULL,
    image_version TEXT NOT NULL,
    architecture machine_architecture NOT NULL,
    status image_status NOT NULL DEFAULT 'available',
    minimum_disk_gib INTEGER NOT NULL CHECK (minimum_disk_gib > 0),
    trusted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (publisher, image_name, image_version)
);

CREATE TABLE ssh_keys (
    ssh_key_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key_name TEXT NOT NULL UNIQUE,
    public_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    key_algorithm TEXT NOT NULL
        CHECK (key_algorithm IN ('ssh-ed25519', 'ssh-rsa', 'ecdsa-sha2-nistp256')),
    owner_name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(public_key) >= 32),
    CHECK (length(fingerprint) >= 16)
);

CREATE TABLE security_groups (
    security_group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    outbound_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE security_group_rules (
    rule_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    security_group_id BIGINT NOT NULL
        REFERENCES security_groups(security_group_id) ON DELETE RESTRICT,
    direction TEXT NOT NULL CHECK (direction IN ('ingress', 'egress')),
    protocol network_protocol NOT NULL,
    from_port INTEGER NOT NULL CHECK (from_port BETWEEN 1 AND 65535),
    to_port INTEGER NOT NULL CHECK (to_port BETWEEN from_port AND 65535),
    source_cidr CIDR NOT NULL,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(trim(description)) > 0),
    UNIQUE (
        security_group_id, direction, protocol,
        from_port, to_port, source_cidr
    )
);

CREATE TABLE deployment_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    policy_name TEXT NOT NULL UNIQUE,
    minimum_disk_gib INTEGER NOT NULL CHECK (minimum_disk_gib > 0),
    maximum_hourly_cost NUMERIC(12, 6) NOT NULL
        CHECK (maximum_hourly_cost >= 0),
    require_encrypted_disk BOOLEAN NOT NULL DEFAULT TRUE,
    require_trusted_image BOOLEAN NOT NULL DEFAULT TRUE,
    require_restricted_ssh BOOLEAN NOT NULL DEFAULT TRUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE virtual_machines (
    instance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_name TEXT NOT NULL,
    region_code TEXT NOT NULL
        REFERENCES cloud_regions(region_code) ON DELETE RESTRICT,
    image_id TEXT NOT NULL
        REFERENCES images(image_id) ON DELETE RESTRICT,
    machine_type_id BIGINT NOT NULL
        REFERENCES machine_types(machine_type_id) ON DELETE RESTRICT,
    ssh_key_id BIGINT NOT NULL
        REFERENCES ssh_keys(ssh_key_id) ON DELETE RESTRICT,
    security_group_id BIGINT NOT NULL
        REFERENCES security_groups(security_group_id) ON DELETE RESTRICT,
    policy_id BIGINT NOT NULL
        REFERENCES deployment_policies(policy_id) ON DELETE RESTRICT,
    root_disk_gib INTEGER NOT NULL CHECK (root_disk_gib > 0),
    encrypted BOOLEAN NOT NULL DEFAULT TRUE,
    public_ip INET,
    state instance_state NOT NULL DEFAULT 'pending',
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    state_changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    terminated_at TIMESTAMPTZ,
    tags JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (jsonb_typeof(tags) = 'object'),
    CHECK (
        (state = 'terminated' AND terminated_at IS NOT NULL)
        OR (state <> 'terminated' AND terminated_at IS NULL)
    )
);

-- Permit name reuse after termination, while preventing duplicate active names.
CREATE UNIQUE INDEX one_active_instance_per_name
    ON virtual_machines (region_code, instance_name)
    WHERE state <> 'terminated';

CREATE INDEX virtual_machines_state_region_idx
    ON virtual_machines (state, region_code);

CREATE INDEX virtual_machines_tags_idx
    ON virtual_machines USING GIN (tags);

CREATE TABLE instance_state_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instance_id UUID NOT NULL
        REFERENCES virtual_machines(instance_id) ON DELETE RESTRICT,
    previous_state instance_state,
    current_state instance_state NOT NULL,
    action TEXT NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(detail) = 'object')
);

CREATE INDEX instance_events_instance_time_idx
    ON instance_state_events (instance_id, occurred_at DESC);

CREATE TABLE instance_status_checks (
    status_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instance_id UUID NOT NULL
        REFERENCES virtual_machines(instance_id) ON DELETE RESTRICT,
    check_name TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('pending', 'passed', 'failed')),
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (instance_id, check_name, checked_at)
);

CREATE INDEX status_checks_instance_result_idx
    ON instance_status_checks (instance_id, result);

-- Restrict illegal lifecycle transitions at the database boundary.
CREATE FUNCTION enforce_instance_lifecycle()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = OLD.state THEN
        RETURN NEW;
    END IF;

    IF NOT (
        (OLD.state = 'pending' AND NEW.state IN ('running', 'failed', 'terminated'))
        OR (OLD.state = 'running' AND NEW.state IN ('stopped', 'failed', 'terminated'))
        OR (OLD.state = 'stopped' AND NEW.state IN ('running', 'terminated'))
        OR (OLD.state = 'failed' AND NEW.state = 'terminated')
    ) THEN
        RAISE EXCEPTION 'Illegal VM lifecycle transition: % -> %',
            OLD.state, NEW.state;
    END IF;

    NEW.state_changed_at := now();

    IF NEW.state = 'terminated' THEN
        NEW.terminated_at := now();
        NEW.public_ip := NULL;
    ELSIF OLD.state = 'terminated' THEN
        RAISE EXCEPTION 'Terminated instances cannot be restarted';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER virtual_machine_lifecycle_guard
BEFORE UPDATE OF state ON virtual_machines
FOR EACH ROW
EXECUTE FUNCTION enforce_instance_lifecycle();

CREATE FUNCTION audit_instance_state()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO instance_state_events (
            instance_id, previous_state, current_state, action, detail
        ) VALUES (
            NEW.instance_id, NULL, NEW.state, 'creation_requested',
            jsonb_build_object('region', NEW.region_code, 'creator', NEW.created_by)
        );
    ELSIF NEW.state IS DISTINCT FROM OLD.state THEN
        INSERT INTO instance_state_events (
            instance_id, previous_state, current_state, action, detail
        ) VALUES (
            NEW.instance_id, OLD.state, NEW.state, 'state_changed',
            jsonb_build_object('name', NEW.instance_name)
        );
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER virtual_machine_state_audit
AFTER INSERT OR UPDATE OF state ON virtual_machines
FOR EACH ROW
EXECUTE FUNCTION audit_instance_state();

-- PostgreSQL CIDR operators let the policy evaluate actual address membership.
CREATE FUNCTION security_group_allows(
    p_group_id BIGINT,
    p_protocol network_protocol,
    p_port INTEGER,
    p_source INET
)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM security_group_rules AS r
        WHERE r.security_group_id = p_group_id
          AND r.direction = 'ingress'
          AND r.protocol = p_protocol
          AND p_port BETWEEN r.from_port AND r.to_port
          AND p_source <<= r.source_cidr
    );
$$;

-- Deployment is performed through a database function to centralize checks.
CREATE FUNCTION deploy_virtual_machine(
    p_name TEXT,
    p_region TEXT,
    p_image TEXT,
    p_machine_type BIGINT,
    p_ssh_key BIGINT,
    p_security_group BIGINT,
    p_policy BIGINT,
    p_disk_gib INTEGER,
    p_encrypted BOOLEAN,
    p_creator TEXT,
    p_tags JSONB DEFAULT '{}'::jsonb
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    selected_image images%ROWTYPE;
    selected_machine machine_types%ROWTYPE;
    selected_key ssh_keys%ROWTYPE;
    selected_group security_groups%ROWTYPE;
    selected_policy deployment_policies%ROWTYPE;
    new_instance_id UUID;
BEGIN
    IF p_name !~ '^[A-Za-z][A-Za-z0-9-]{0,39}$' THEN
        RAISE EXCEPTION 'Invalid instance name';
    END IF;
    IF p_disk_gib IS NULL OR p_disk_gib < 1 THEN
        RAISE EXCEPTION 'Root disk must be positive';
    END IF;
    IF p_tags IS NULL OR jsonb_typeof(p_tags) <> 'object' THEN
        RAISE EXCEPTION 'Tags must be a JSON object';
    END IF;

    SELECT * INTO selected_image
    FROM images WHERE image_id = p_image FOR SHARE;
    IF NOT FOUND OR selected_image.status <> 'available'
       OR NOT selected_image.trusted THEN
        RAISE EXCEPTION 'Image is unavailable or untrusted';
    END IF;

    SELECT * INTO selected_machine
    FROM machine_types WHERE machine_type_id = p_machine_type AND active;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Machine type is unavailable';
    END IF;

    SELECT * INTO selected_key
    FROM ssh_keys WHERE ssh_key_id = p_ssh_key AND enabled;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SSH key is unavailable';
    END IF;

    SELECT * INTO selected_group
    FROM security_groups WHERE security_group_id = p_security_group;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Security group not found';
    END IF;

    SELECT * INTO selected_policy
    FROM deployment_policies WHERE policy_id = p_policy AND enabled;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Deployment policy is unavailable';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM cloud_regions
        WHERE region_code = p_region AND enabled
    ) THEN
        RAISE EXCEPTION 'Region is unavailable';
    END IF;

    IF selected_image.architecture <> selected_machine.architecture THEN
        RAISE EXCEPTION 'Image and machine architectures differ';
    END IF;

    IF p_disk_gib < GREATEST(
        selected_image.minimum_disk_gib,
        selected_policy.minimum_disk_gib
    ) THEN
        RAISE EXCEPTION 'Root disk violates minimum size policy';
    END IF;

    IF selected_machine.hourly_compute_cost > selected_policy.maximum_hourly_cost THEN
        RAISE EXCEPTION 'Machine exceeds the hourly cost limit';
    END IF;

    IF selected_policy.require_encrypted_disk AND NOT p_encrypted THEN
        RAISE EXCEPTION 'Encrypted root disk is required';
    END IF;

    IF selected_policy.require_restricted_ssh AND EXISTS (
        SELECT 1 FROM security_group_rules r
        WHERE r.security_group_id = p_security_group
          AND r.direction = 'ingress'
          AND r.protocol = 'tcp'
          AND 22 BETWEEN r.from_port AND r.to_port
          AND r.source_cidr <<= '0.0.0.0/0'::cidr
          AND r.source_cidr = '0.0.0.0/0'::cidr
    ) THEN
        RAISE EXCEPTION 'SSH cannot be exposed to all IPv4 addresses';
    END IF;

    INSERT INTO virtual_machines (
        instance_name, region_code, image_id, machine_type_id,
        ssh_key_id, security_group_id, policy_id, root_disk_gib,
        encrypted, state, created_by, tags
    ) VALUES (
        p_name, p_region, p_image, p_machine_type,
        p_ssh_key, p_security_group, p_policy, p_disk_gib,
        p_encrypted, 'pending', p_creator, p_tags
    )
    RETURNING instance_id INTO new_instance_id;

    RETURN new_instance_id;
END;
$$;

INSERT INTO cloud_regions (region_code, display_name) VALUES
    ('us-east-1', 'US East'),
    ('ap-south-1', 'Asia Pacific South');

INSERT INTO machine_types (
    name, architecture, vcpus, memory_gib, hourly_compute_cost
) VALUES
    ('general.small', 'x86_64', 2, 4, 0.041600),
    ('compute.arm', 'arm64', 4, 8, 0.080000);

INSERT INTO images (
    image_id, publisher, image_name, image_version,
    architecture, status, minimum_disk_gib, trusted
) VALUES
    ('ubuntu-2404', 'verified-publisher', 'Ubuntu Server', '24.04',
     'x86_64', 'available', 8, TRUE),
    ('ubuntu-arm', 'verified-publisher', 'Ubuntu Server ARM', '24.04',
     'arm64', 'available', 8, TRUE),
    ('legacy-image', 'verified-publisher', 'Legacy Linux', '18.04',
     'x86_64', 'deprecated', 8, TRUE),
    ('unknown-image', 'unverified-publisher', 'Unknown OS', '1.0',
     'x86_64', 'available', 8, FALSE);

INSERT INTO ssh_keys (
    key_name, public_key, fingerprint, key_algorithm, owner_name
) VALUES (
    'platform-admin',
    'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGV4YW1wbGVwdWJsaWNrZXlkYXRh admin',
    'SHA256:example-platform-admin-fingerprint',
    'ssh-ed25519',
    'platform-team'
);

INSERT INTO security_groups (group_name, description) VALUES
    ('staging-web', 'Restricted SSH and public HTTPS'),
    ('unsafe-demo', 'Intentionally insecure policy test');

INSERT INTO security_group_rules (
    security_group_id, direction, protocol, from_port, to_port,
    source_cidr, description
)
SELECT security_group_id, 'ingress', 'tcp', 22, 22,
       '203.0.113.8/32', 'Administrator SSH'
FROM security_groups WHERE group_name = 'staging-web';

INSERT INTO security_group_rules (
    security_group_id, direction, protocol, from_port, to_port,
    source_cidr, description
)
SELECT security_group_id, 'ingress', 'tcp', 443, 443,
       '0.0.0.0/0', 'Public HTTPS'
FROM security_groups WHERE group_name = 'staging-web';

INSERT INTO security_group_rules (
    security_group_id, direction, protocol, from_port, to_port,
    source_cidr, description
)
SELECT security_group_id, 'ingress', 'tcp', 22, 22,
       '0.0.0.0/0', 'Intentionally unsafe SSH rule'
FROM security_groups WHERE group_name = 'unsafe-demo';

INSERT INTO deployment_policies (
    policy_name, minimum_disk_gib, maximum_hourly_cost,
    require_encrypted_disk, require_trusted_image, require_restricted_ssh
) VALUES (
    'production-baseline', 10, 0.500000, TRUE, TRUE, TRUE
);

-- Create a valid instance. The function returns its UUID through a CTE.
WITH created AS (
    SELECT deploy_virtual_machine(
        'staging-api', 'us-east-1', 'ubuntu-2404',
        (SELECT machine_type_id FROM machine_types WHERE name = 'general.small'),
        (SELECT ssh_key_id FROM ssh_keys WHERE key_name = 'platform-admin'),
        (SELECT security_group_id FROM security_groups WHERE group_name = 'staging-web'),
        (SELECT policy_id FROM deployment_policies WHERE policy_name = 'production-baseline'),
        20, TRUE, 'platform-team',
        '{"environment":"staging","owner":"platform"}'::jsonb
    ) AS instance_id
)
SELECT instance_id, 'Deployment accepted in pending state' AS result
FROM created;

-- Simulate successful provisioning, then a health check.
UPDATE virtual_machines
SET state = 'running', public_ip = '192.0.2.70'::inet
WHERE instance_name = 'staging-api' AND state = 'pending';

INSERT INTO instance_status_checks (instance_id, check_name, result, details)
SELECT instance_id, 'cloud-init', 'passed', '{"exit_code":0}'::jsonb
FROM virtual_machines WHERE instance_name = 'staging-api';

INSERT INTO instance_status_checks (instance_id, check_name, result, details)
SELECT instance_id, 'application-health', 'passed',
       '{"http_status":200}'::jsonb
FROM virtual_machines WHERE instance_name = 'staging-api';

-- A stopped VM loses its simulated public address. The lifecycle trigger
-- updates state_changed_at and writes a corresponding audit event.
UPDATE virtual_machines
SET state = 'stopped', public_ip = NULL
WHERE instance_name = 'staging-api' AND state = 'running';

-- Restarting a stopped VM is valid.
UPDATE virtual_machines
SET state = 'running', public_ip = '192.0.2.71'::inet
WHERE instance_name = 'staging-api' AND state = 'stopped';

-- Verify inbound network policy with PostgreSQL CIDR containment.
SELECT
    g.group_name,
    security_group_allows(
        g.security_group_id, 'tcp', 22, '203.0.113.8'::inet
    ) AS administrator_ssh_allowed,
    security_group_allows(
        g.security_group_id, 'tcp', 22, '198.51.100.20'::inet
    ) AS unrelated_ssh_allowed
FROM security_groups g
WHERE g.group_name = 'staging-web';

-- Compute-only estimate: storage, public IPv4, data transfer, and other
-- provider-specific charges are deliberately outside this simplified model.
CREATE VIEW running_compute_cost_estimate AS
SELECT
    vm.instance_id,
    vm.instance_name,
    vm.region_code,
    mt.name AS machine_type,
    mt.hourly_compute_cost,
    round(mt.hourly_compute_cost * 730, 2) AS estimated_monthly_compute_cost
FROM virtual_machines vm
JOIN machine_types mt ON mt.machine_type_id = vm.machine_type_id
WHERE vm.state = 'running';

SELECT * FROM running_compute_cost_estimate;

-- Inspect lifecycle events and health-check outcomes.
SELECT
    vm.instance_name,
    event.previous_state,
    event.current_state,
    event.action,
    event.occurred_at
FROM instance_state_events event
JOIN virtual_machines vm USING (instance_id)
ORDER BY event.occurred_at;

SELECT
    vm.instance_name,
    checks.check_name,
    checks.result,
    checks.checked_at
FROM instance_status_checks checks
JOIN virtual_machines vm USING (instance_id)
ORDER BY vm.instance_name, checks.checked_at;

-- The following failures are demonstrated as data predicates rather than
-- deliberately aborting the whole transaction.
SELECT image_id, status, trusted
FROM images
WHERE status <> 'available' OR NOT trusted;

SELECT group_name, r.source_cidr, r.from_port, r.to_port
FROM security_groups g
JOIN security_group_rules r USING (security_group_id)
WHERE r.direction = 'ingress'
  AND r.protocol = 'tcp'
  AND 22 BETWEEN r.from_port AND r.to_port
  AND r.source_cidr = '0.0.0.0/0'::cidr;

-- Demonstrate that database lifecycle constraints reject a direct
-- running-to-pending regression without leaving the transaction aborted.
DO $$
DECLARE
    target_id UUID;
BEGIN
    SELECT instance_id INTO target_id
    FROM virtual_machines
    WHERE instance_name = 'staging-api';

    BEGIN
        UPDATE virtual_machines
        SET state = 'pending'
        WHERE instance_id = target_id;
    EXCEPTION WHEN raise_exception THEN
        RAISE NOTICE 'Expected invalid lifecycle transition was rejected: %',
            SQLERRM;
    END;
END;
$$;

-- Termination is irreversible. Its trigger clears the public IP and stamps
-- terminated_at; a later restart will fail the transition guard.
UPDATE virtual_machines
SET state = 'terminated'
WHERE instance_name = 'staging-api' AND state = 'running';

SELECT instance_name, state, public_ip, terminated_at
FROM virtual_machines
WHERE instance_name = 'staging-api';

COMMIT;
