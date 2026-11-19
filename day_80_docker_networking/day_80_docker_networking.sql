/*
 * Docker Networking: PostgreSQL Network Inventory and Governance
 *
 * PostgreSQL 15+
 *
 * Models:
 * - Docker hosts
 * - Bridge and host networks
 * - IPv4 subnets and gateways
 * - Containers
 * - Network attachments
 * - Container IP allocations
 * - DNS aliases
 * - Port mappings
 * - Network policies
 * - Communication evaluations
 * - Network events
 * - Network inventory reporting
 *
 * All simulated operations use relational constraints,
 * transactional functions and audit triggers.
 */

BEGIN;

CREATE SCHEMA IF NOT EXISTS docker_lab;

SET search_path TO docker_lab, public;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Remove existing demonstration objects in dependency order.
DROP VIEW IF EXISTS communication_report CASCADE;
DROP VIEW IF EXISTS network_inventory CASCADE;
DROP VIEW IF EXISTS container_network_inventory CASCADE;

DROP TABLE IF EXISTS network_events CASCADE;
DROP TABLE IF EXISTS communication_attempts CASCADE;
DROP TABLE IF EXISTS network_policies CASCADE;
DROP TABLE IF EXISTS port_mappings CASCADE;
DROP TABLE IF EXISTS dns_aliases CASCADE;
DROP TABLE IF EXISTS network_attachments CASCADE;
DROP TABLE IF EXISTS containers CASCADE;
DROP TABLE IF EXISTS docker_networks CASCADE;
DROP TABLE IF EXISTS docker_hosts CASCADE;

DROP FUNCTION IF EXISTS allocate_container_ip CASCADE;
DROP FUNCTION IF EXISTS attach_container CASCADE;
DROP FUNCTION IF EXISTS detach_container CASCADE;
DROP FUNCTION IF EXISTS publish_container_port CASCADE;
DROP FUNCTION IF EXISTS evaluate_communication CASCADE;
DROP FUNCTION IF EXISTS record_network_event CASCADE;
DROP FUNCTION IF EXISTS audit_container_change CASCADE;
DROP FUNCTION IF EXISTS validate_network_configuration CASCADE;
DROP FUNCTION IF EXISTS reject_overlapping_subnet CASCADE;

CREATE TABLE docker_hosts (
    host_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hostname VARCHAR(120) NOT NULL UNIQUE,
    operating_system VARCHAR(100) NOT NULL,
    docker_version VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'INACTIVE', 'MAINTENANCE')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE docker_networks (
    network_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    host_id UUID NOT NULL REFERENCES docker_hosts(host_id),
    network_name VARCHAR(120) NOT NULL,
    driver VARCHAR(20) NOT NULL
        CHECK (driver IN ('bridge', 'host')),
    subnet CIDR,
    gateway INET,
    internal_network BOOLEAN NOT NULL DEFAULT FALSE,
    attachable BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(host_id, network_name),

    CHECK (
        (
            driver = 'bridge'
            AND subnet IS NOT NULL
            AND family(subnet) = 4
            AND masklen(subnet) BETWEEN 16 AND 30
            AND gateway IS NOT NULL
            AND family(gateway) = 4
            AND gateway <<= subnet
        )
        OR
        (
            driver = 'host'
            AND subnet IS NULL
            AND gateway IS NULL
        )
    )
);

CREATE TABLE containers (
    container_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    host_id UUID NOT NULL REFERENCES docker_hosts(host_id),
    container_name VARCHAR(120) NOT NULL,
    image_name VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'RUNNING'
        CHECK (
            status IN (
                'CREATED',
                'RUNNING',
                'STOPPED',
                'RESTARTING',
                'REMOVED'
            )
        ),
    restart_count INTEGER NOT NULL DEFAULT 0
        CHECK (restart_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(host_id, container_name),
    UNIQUE(container_id, host_id)
);

CREATE TABLE network_attachments (
    attachment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    container_id UUID NOT NULL REFERENCES containers(container_id),
    network_id UUID NOT NULL REFERENCES docker_networks(network_id),
    ipv4_address INET,
    connected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    disconnected_at TIMESTAMPTZ,

    UNIQUE(container_id, network_id),

    CHECK (
        ipv4_address IS NULL
        OR (
            family(ipv4_address) = 4
            AND masklen(ipv4_address) = 32
        )
    ),

    CHECK (
        disconnected_at IS NULL
        OR disconnected_at >= connected_at
    )
);

CREATE UNIQUE INDEX uq_active_container_ip
ON network_attachments(network_id, ipv4_address)
WHERE disconnected_at IS NULL
AND ipv4_address IS NOT NULL;

CREATE INDEX idx_attachment_container_active
ON network_attachments(container_id, network_id)
WHERE disconnected_at IS NULL;

CREATE TABLE dns_aliases (
    alias_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    network_id UUID NOT NULL REFERENCES docker_networks(network_id),
    container_id UUID NOT NULL REFERENCES containers(container_id),
    alias VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(network_id, alias)
);

CREATE INDEX idx_dns_alias_lookup
ON dns_aliases(network_id, alias);

CREATE TABLE port_mappings (
    mapping_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    container_id UUID NOT NULL REFERENCES containers(container_id),
    host_ip INET NOT NULL DEFAULT '0.0.0.0',
    host_port INTEGER NOT NULL
        CHECK (host_port BETWEEN 1 AND 65535),
    container_port INTEGER NOT NULL
        CHECK (container_port BETWEEN 1 AND 65535),
    protocol VARCHAR(5) NOT NULL
        CHECK (protocol IN ('tcp', 'udp')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX uq_active_host_port
ON port_mappings(host_ip, host_port, protocol)
WHERE active = TRUE;

CREATE INDEX idx_port_mapping_container
ON port_mappings(container_id)
WHERE active = TRUE;

CREATE TABLE network_policies (
    policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    network_id UUID NOT NULL REFERENCES docker_networks(network_id),
    policy_name VARCHAR(120) NOT NULL,
    source_container_id UUID REFERENCES containers(container_id),
    destination_container_id UUID REFERENCES containers(container_id),
    destination_port INTEGER NOT NULL
        CHECK (destination_port BETWEEN 1 AND 65535),
    protocol VARCHAR(5) NOT NULL
        CHECK (protocol IN ('tcp', 'udp')),
    action VARCHAR(10) NOT NULL
        CHECK (action IN ('ALLOW', 'DENY')),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(network_id, policy_name)
);

CREATE TABLE communication_attempts (
    attempt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_container_id UUID NOT NULL REFERENCES containers(container_id),
    destination_container_id UUID NOT NULL REFERENCES containers(container_id),
    network_id UUID NOT NULL REFERENCES docker_networks(network_id),
    destination_port INTEGER NOT NULL
        CHECK (destination_port BETWEEN 1 AND 65535),
    protocol VARCHAR(5) NOT NULL
        CHECK (protocol IN ('tcp', 'udp')),
    decision VARCHAR(10) NOT NULL
        CHECK (decision IN ('ALLOW', 'DENY')),
    reason TEXT NOT NULL,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_communication_attempt_time
ON communication_attempts(attempted_at DESC);

CREATE TABLE network_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type VARCHAR(60) NOT NULL,
    entity_type VARCHAR(40) NOT NULL,
    entity_id UUID,
    description TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_network_events_entity
ON network_events(entity_type, entity_id, occurred_at DESC);


-- Validate network and host relationships.
CREATE OR REPLACE FUNCTION validate_network_configuration()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    host_status TEXT;
BEGIN
    SELECT status
    INTO host_status
    FROM docker_hosts
    WHERE host_id = NEW.host_id;

    IF host_status IS DISTINCT FROM 'ACTIVE' THEN
        RAISE EXCEPTION 'Docker host must be ACTIVE';
    END IF;

    IF NEW.driver = 'bridge' THEN
        IF NOT (NEW.gateway <<= NEW.subnet) THEN
            RAISE EXCEPTION 'Gateway is outside the subnet';
        END IF;

        IF NEW.gateway = broadcast(NEW.subnet) THEN
            RAISE EXCEPTION 'Gateway cannot be broadcast address';
        END IF;

        IF NEW.gateway = network(NEW.subnet) THEN
            RAISE EXCEPTION 'Gateway cannot be network address';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_network
BEFORE INSERT OR UPDATE ON docker_networks
FOR EACH ROW
EXECUTE FUNCTION validate_network_configuration();


-- Prevent overlapping bridge subnets on the same Docker host.
CREATE OR REPLACE FUNCTION reject_overlapping_subnet()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.driver <> 'bridge' THEN
        RETURN NEW;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM docker_networks existing
        WHERE existing.host_id = NEW.host_id
          AND existing.driver = 'bridge'
          AND existing.network_id <> NEW.network_id
          AND existing.subnet && NEW.subnet
    ) THEN
        RAISE EXCEPTION
            'Bridge subnet % overlaps an existing network',
            NEW.subnet;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_reject_overlapping_subnet
BEFORE INSERT OR UPDATE ON docker_networks
FOR EACH ROW
EXECUTE FUNCTION reject_overlapping_subnet();


-- Validate container and network ownership during attachment.
CREATE OR REPLACE FUNCTION allocate_container_ip()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    network_record docker_networks%ROWTYPE;
    container_host UUID;
    selected_ip INET;
BEGIN
    SELECT *
    INTO network_record
    FROM docker_networks
    WHERE network_id = NEW.network_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Network does not exist';
    END IF;

    SELECT host_id
    INTO container_host
    FROM containers
    WHERE container_id = NEW.container_id
      AND status <> 'REMOVED';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Container does not exist or was removed';
    END IF;

    IF container_host <> network_record.host_id THEN
        RAISE EXCEPTION 'Container and network belong to different hosts';
    END IF;

    IF NOT network_record.attachable THEN
        RAISE EXCEPTION 'Network does not allow new attachments';
    END IF;

    IF network_record.driver = 'host' THEN
        IF NEW.ipv4_address IS NOT NULL THEN
            RAISE EXCEPTION 'Host network does not allocate container IPs';
        END IF;

        RETURN NEW;
    END IF;

    IF NEW.ipv4_address IS NULL THEN
        SELECT candidate
        INTO selected_ip
        FROM (
            SELECT
                (network_record.subnet).network AS unused
        ) initial_value
        CROSS JOIN LATERAL (
            SELECT host(candidate_number)::INET AS candidate
            FROM generate_series(
                network(network_record.subnet)::BIGINT + 2,
                broadcast(network_record.subnet)::BIGINT - 1
            ) AS candidate_number
        ) candidates
        WHERE candidate <> network_record.gateway
          AND NOT EXISTS (
              SELECT 1
              FROM network_attachments attachment
              WHERE attachment.network_id = NEW.network_id
                AND attachment.disconnected_at IS NULL
                AND attachment.ipv4_address = candidate
          )
        ORDER BY candidate
        LIMIT 1;

        IF selected_ip IS NULL THEN
            RAISE EXCEPTION 'No available addresses in subnet %',
                network_record.subnet;
        END IF;

        NEW.ipv4_address := selected_ip;
    END IF;

    IF NOT (NEW.ipv4_address <<= network_record.subnet) THEN
        RAISE EXCEPTION 'Container IP is outside the network subnet';
    END IF;

    IF NEW.ipv4_address = network_record.gateway
       OR NEW.ipv4_address = broadcast(network_record.subnet)
       OR NEW.ipv4_address = network(network_record.subnet) THEN
        RAISE EXCEPTION 'Reserved network address cannot be allocated';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_allocate_container_ip
BEFORE INSERT ON network_attachments
FOR EACH ROW
EXECUTE FUNCTION allocate_container_ip();


-- Record operational events.
CREATE OR REPLACE FUNCTION record_network_event(
    p_type TEXT,
    p_entity_type TEXT,
    p_entity_id UUID,
    p_description TEXT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO network_events(
        event_type,
        entity_type,
        entity_id,
        description
    )
    VALUES (
        p_type,
        p_entity_type,
        p_entity_id,
        p_description
    );
END;
$$;


CREATE OR REPLACE FUNCTION audit_container_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM record_network_event(
            'CONTAINER_CREATED',
            'CONTAINER',
            NEW.container_id,
            NEW.container_name || ' using ' || NEW.image_name
        );

        RETURN NEW;
    END IF;

    IF OLD.status IS DISTINCT FROM NEW.status THEN
        PERFORM record_network_event(
            'CONTAINER_STATUS_CHANGED',
            'CONTAINER',
            NEW.container_id,
            OLD.status || ' -> ' || NEW.status
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_container_audit
AFTER INSERT OR UPDATE ON containers
FOR EACH ROW
EXECUTE FUNCTION audit_container_change();


-- Attach a container and optionally register DNS aliases.
CREATE OR REPLACE FUNCTION attach_container(
    p_container UUID,
    p_network UUID,
    p_aliases TEXT[] DEFAULT ARRAY[]::TEXT[]
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    new_attachment UUID;
    selected_ip INET;
    alias_value TEXT;
BEGIN
    INSERT INTO network_attachments(
        container_id,
        network_id
    )
    VALUES (
        p_container,
        p_network
    )
    RETURNING attachment_id, ipv4_address
    INTO new_attachment, selected_ip;

    FOREACH alias_value IN ARRAY p_aliases LOOP
        IF alias_value IS NULL OR length(trim(alias_value)) = 0 THEN
            RAISE EXCEPTION 'DNS alias cannot be empty';
        END IF;

        INSERT INTO dns_aliases(
            network_id,
            container_id,
            alias
        )
        VALUES (
            p_network,
            p_container,
            alias_value
        );
    END LOOP;

    PERFORM record_network_event(
        'NETWORK_ATTACHED',
        'CONTAINER',
        p_container,
        'Attached to network ' || p_network
        || '; IP=' || COALESCE(selected_ip::TEXT, 'host-network')
    );

    RETURN new_attachment;
END;
$$;


CREATE OR REPLACE FUNCTION detach_container(
    p_container UUID,
    p_network UUID
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    network_driver TEXT;
BEGIN
    SELECT driver
    INTO network_driver
    FROM docker_networks
    WHERE network_id = p_network;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Network not found';
    END IF;

    IF network_driver = 'host' THEN
        RAISE EXCEPTION 'Host networking cannot be detached independently';
    END IF;

    UPDATE network_attachments
    SET disconnected_at = CURRENT_TIMESTAMP
    WHERE container_id = p_container
      AND network_id = p_network
      AND disconnected_at IS NULL;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active attachment not found';
    END IF;

    DELETE FROM dns_aliases
    WHERE container_id = p_container
      AND network_id = p_network;

    PERFORM record_network_event(
        'NETWORK_DETACHED',
        'CONTAINER',
        p_container,
        'Detached from network ' || p_network
    );
END;
$$;


-- Publish a host port using a transactional uniqueness check.
CREATE OR REPLACE FUNCTION publish_container_port(
    p_container UUID,
    p_host_ip INET,
    p_host_port INTEGER,
    p_container_port INTEGER,
    p_protocol TEXT DEFAULT 'tcp'
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    new_mapping UUID;
BEGIN
    IF p_host_port NOT BETWEEN 1 AND 65535
       OR p_container_port NOT BETWEEN 1 AND 65535 THEN
        RAISE EXCEPTION 'Invalid port number';
    END IF;

    IF p_protocol NOT IN ('tcp', 'udp') THEN
        RAISE EXCEPTION 'Invalid transport protocol';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM containers
        WHERE container_id = p_container
          AND status = 'RUNNING'
    ) THEN
        RAISE EXCEPTION 'Container must be running';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM port_mappings
        WHERE container_id = p_container
          AND container_port = p_container_port
          AND active = TRUE
    ) = FALSE THEN
        -- Port mappings are explicit declarations in this inventory.
        NULL;
    END IF;

    INSERT INTO port_mappings(
        container_id,
        host_ip,
        host_port,
        container_port,
        protocol
    )
    VALUES (
        p_container,
        p_host_ip,
        p_host_port,
        p_container_port,
        p_protocol
    )
    RETURNING mapping_id INTO new_mapping;

    PERFORM record_network_event(
        'PORT_PUBLISHED',
        'CONTAINER',
        p_container,
        p_host_ip || ':' || p_host_port
        || ' -> ' || p_container_port || '/' || p_protocol
    );

    RETURN new_mapping;
END;
$$;


-- Evaluate connectivity between two containers.
-- The model requires both containers to share an active bridge network,
-- or a host network attachment, and the destination port to be declared
-- through an active port mapping.
CREATE OR REPLACE FUNCTION evaluate_communication(
    p_source UUID,
    p_destination UUID,
    p_network UUID,
    p_port INTEGER,
    p_protocol TEXT DEFAULT 'tcp'
)
RETURNS TABLE(
    allowed BOOLEAN,
    decision_reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    network_driver TEXT;
    source_status TEXT;
    destination_status TEXT;
    policy_action TEXT;
    source_host UUID;
    destination_host UUID;
BEGIN
    SELECT driver
    INTO network_driver
    FROM docker_networks
    WHERE network_id = p_network;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Network not found';
    END IF;

    SELECT status, host_id
    INTO source_status, source_host
    FROM containers
    WHERE container_id = p_source;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Source container not found';
    END IF;

    SELECT status, host_id
    INTO destination_status, destination_host
    FROM containers
    WHERE container_id = p_destination;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Destination container not found';
    END IF;

    IF source_status <> 'RUNNING'
       OR destination_status <> 'RUNNING' THEN
        RETURN QUERY SELECT FALSE, 'A container is not running';
        RETURN;
    END IF;

    IF source_host <> destination_host THEN
        RETURN QUERY SELECT FALSE, 'Containers are on different hosts';
        RETURN;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM network_attachments source_attachment
        JOIN network_attachments destination_attachment
          ON destination_attachment.network_id =
             source_attachment.network_id
        WHERE source_attachment.container_id = p_source
          AND destination_attachment.container_id = p_destination
          AND source_attachment.network_id = p_network
          AND source_attachment.disconnected_at IS NULL
          AND destination_attachment.disconnected_at IS NULL
    ) THEN
        RETURN QUERY SELECT FALSE, 'No shared active network attachment';
        RETURN;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM port_mappings
        WHERE container_id = p_destination
          AND container_port = p_port
          AND protocol = p_protocol
          AND active = TRUE
    ) THEN
        RETURN QUERY SELECT FALSE, 'Destination port is not published';
        RETURN;
    END IF;

    SELECT action
    INTO policy_action
    FROM network_policies
    WHERE network_id = p_network
      AND enabled = TRUE
      AND destination_port = p_port
      AND protocol = p_protocol
      AND (
          source_container_id IS NULL
          OR source_container_id = p_source
      )
      AND (
          destination_container_id IS NULL
          OR destination_container_id = p_destination
      )
    ORDER BY
        CASE action WHEN 'DENY' THEN 0 ELSE 1 END
    LIMIT 1;

    IF policy_action = 'DENY' THEN
        RETURN QUERY SELECT FALSE, 'Explicit network policy denial';
        RETURN;
    END IF;

    IF policy_action = 'ALLOW' THEN
        RETURN QUERY SELECT TRUE, 'Explicit network policy allowance';
        RETURN;
    END IF;

    RETURN QUERY SELECT TRUE, 'Shared network and active port mapping';
END;
$$;


-- Container network inventory.
CREATE VIEW container_network_inventory AS
SELECT
    c.container_name,
    c.image_name,
    c.status,
    n.network_name,
    n.driver,
    a.ipv4_address,
    a.connected_at,
    a.disconnected_at
FROM containers c
JOIN network_attachments a
  ON a.container_id = c.container_id
JOIN docker_networks n
  ON n.network_id = a.network_id;

-- Network capacity and attachment inventory.
CREATE VIEW network_inventory AS
SELECT
    n.network_name,
    n.driver,
    n.subnet,
    n.gateway,
    COUNT(a.attachment_id)
        FILTER (WHERE a.disconnected_at IS NULL) AS active_attachments,
    COUNT(DISTINCT a.container_id)
        FILTER (WHERE a.disconnected_at IS NULL) AS connected_containers
FROM docker_networks n
LEFT JOIN network_attachments a
  ON a.network_id = n.network_id
GROUP BY
    n.network_id,
    n.network_name,
    n.driver,
    n.subnet,
    n.gateway;

CREATE VIEW communication_report AS
SELECT
    attempt_id,
    source_container_id,
    destination_container_id,
    network_id,
    destination_port,
    protocol,
    decision,
    reason,
    attempted_at
FROM communication_attempts;


-- Demonstration data.
INSERT INTO docker_hosts(
    hostname,
    operating_system,
    docker_version
)
VALUES (
    'docker-prod-01',
    'Ubuntu Server 24.04',
    '27.5'
);

INSERT INTO docker_networks(
    host_id,
    network_name,
    driver,
    subnet,
    gateway
)
SELECT
    host_id,
    'frontend',
    'bridge',
    '172.20.0.0/24',
    '172.20.0.1'
FROM docker_hosts
WHERE hostname = 'docker-prod-01';

INSERT INTO docker_networks(
    host_id,
    network_name,
    driver,
    subnet,
    gateway
)
SELECT
    host_id,
    'backend',
    'bridge',
    '172.21.0.0/24',
    '172.21.0.1'
FROM docker_hosts
WHERE hostname = 'docker-prod-01';

INSERT INTO docker_networks(
    host_id,
    network_name,
    driver
)
SELECT
    host_id,
    'host-mode',
    'host'
FROM docker_hosts
WHERE hostname = 'docker-prod-01';

INSERT INTO containers(
    host_id,
    container_name,
    image_name
)
SELECT
    host_id,
    'web',
    'nginx:1.27'
FROM docker_hosts
WHERE hostname = 'docker-prod-01';

INSERT INTO containers(
    host_id,
    container_name,
    image_name
)
SELECT
    host_id,
    'api',
    'python:3.13'
FROM docker_hosts
WHERE hostname = 'docker-prod-01';

INSERT INTO containers(
    host_id,
    container_name,
    image_name
)
SELECT
    host_id,
    'database',
    'postgres:18'
FROM docker_hosts
WHERE hostname = 'docker-prod-01';

-- Transactional attachment operations.
DO $$
DECLARE
    web_id UUID;
    api_id UUID;
    db_id UUID;
    frontend_id UUID;
    backend_id UUID;
    host_network_id UUID;
BEGIN
    SELECT container_id INTO web_id
    FROM containers WHERE container_name = 'web';

    SELECT container_id INTO api_id
    FROM containers WHERE container_name = 'api';

    SELECT container_id INTO db_id
    FROM containers WHERE container_name = 'database';

    SELECT network_id INTO frontend_id
    FROM docker_networks WHERE network_name = 'frontend';

    SELECT network_id INTO backend_id
    FROM docker_networks WHERE network_name = 'backend';

    SELECT network_id INTO host_network_id
    FROM docker_networks WHERE network_name = 'host-mode';

    PERFORM attach_container(web_id, frontend_id, ARRAY['web-service']);
    PERFORM attach_container(api_id, frontend_id, ARRAY['api-service']);
    PERFORM attach_container(api_id, backend_id, ARRAY['api-internal']);
    PERFORM attach_container(db_id, backend_id, ARRAY['db']);
    PERFORM attach_container(web_id, host_network_id, ARRAY[]::TEXT[]);
END;
$$;

-- Port publishing.
DO $$
DECLARE
    web_id UUID;
    api_id UUID;
    db_id UUID;
BEGIN
    SELECT container_id INTO web_id
    FROM containers WHERE container_name = 'web';

    SELECT container_id INTO api_id
    FROM containers WHERE container_name = 'api';

    SELECT container_id INTO db_id
    FROM containers WHERE container_name = 'database';

    PERFORM publish_container_port(
        web_id, '0.0.0.0', 8080, 80, 'tcp'
    );

    PERFORM publish_container_port(
        api_id, '127.0.0.1', 8000, 8000, 'tcp'
    );

    PERFORM publish_container_port(
        db_id, '127.0.0.1', 15432, 5432, 'tcp'
    );
END;
$$;

-- Explicit network policy.
INSERT INTO network_policies(
    network_id,
    policy_name,
    source_container_id,
    destination_container_id,
    destination_port,
    protocol,
    action
)
SELECT
    n.network_id,
    'frontend-api-allow',
    source.container_id,
    destination.container_id,
    8000,
    'tcp',
    'ALLOW'
FROM docker_networks n
CROSS JOIN containers source
CROSS JOIN containers destination
WHERE n.network_name = 'frontend'
  AND source.container_name = 'web'
  AND destination.container_name = 'api';

INSERT INTO network_policies(
    network_id,
    policy_name,
    source_container_id,
    destination_container_id,
    destination_port,
    protocol,
    action
)
SELECT
    n.network_id,
    'deny-web-database',
    source.container_id,
    destination.container_id,
    5432,
    'tcp',
    'DENY'
FROM docker_networks n
CROSS JOIN containers source
CROSS JOIN containers destination
WHERE n.network_name = 'backend'
  AND source.container_name = 'web'
  AND destination.container_name = 'database';


-- Evaluate successful and unsuccessful communication.
INSERT INTO communication_attempts(
    source_container_id,
    destination_container_id,
    network_id,
    destination_port,
    protocol,
    decision,
    reason
)
SELECT
    source.container_id,
    destination.container_id,
    n.network_id,
    8000,
    'tcp',
    result.allowed::TEXT::BOOLEAN::TEXT::VARCHAR::VARCHAR(10),
    result.decision_reason
FROM containers source
CROSS JOIN containers destination
CROSS JOIN docker_networks n
CROSS JOIN LATERAL evaluate_communication(
    source.container_id,
    destination.container_id,
    n.network_id,
    8000,
    'tcp'
) result
WHERE source.container_name = 'web'
  AND destination.container_name = 'api'
  AND n.network_name = 'frontend';


-- Capture an isolated-network failure.
INSERT INTO communication_attempts(
    source_container_id,
    destination_container_id,
    network_id,
    destination_port,
    protocol,
    decision,
    reason
)
SELECT
    source.container_id,
    destination.container_id,
    n.network_id,
    5432,
    'tcp',
    CASE WHEN result.allowed THEN 'ALLOW' ELSE 'DENY' END,
    result.decision_reason
FROM containers source
CROSS JOIN containers destination
CROSS JOIN docker_networks n
CROSS JOIN LATERAL evaluate_communication(
    source.container_id,
    destination.container_id,
    n.network_id,
    5432,
    'tcp'
) result
WHERE source.container_name = 'web'
  AND destination.container_name = 'database'
  AND n.network_name = 'frontend';


-- Retrieval: all active container network attachments.
SELECT *
FROM container_network_inventory
WHERE disconnected_at IS NULL
ORDER BY network_name, container_name;

-- Retrieval: DNS aliases.
SELECT
    n.network_name,
    d.alias,
    c.container_name
FROM dns_aliases d
JOIN docker_networks n USING (network_id)
JOIN containers c USING (container_id)
ORDER BY n.network_name, d.alias;

-- Aggregation: network usage.
SELECT *
FROM network_inventory
ORDER BY network_name;

-- Reporting: published ports.
SELECT
    c.container_name,
    p.host_ip,
    p.host_port,
    p.container_port,
    p.protocol
FROM port_mappings p
JOIN containers c USING (container_id)
WHERE p.active = TRUE
ORDER BY c.container_name;

-- Evaluation: recorded communication outcomes.
SELECT
    decision,
    reason,
    COUNT(*) AS attempt_count
FROM communication_attempts
GROUP BY decision, reason
ORDER BY decision, reason;

-- CTE: identify containers connected to multiple networks.
WITH attachment_counts AS (
    SELECT
        c.container_name,
        COUNT(*) AS network_count
    FROM containers c
    JOIN network_attachments a
      ON a.container_id = c.container_id
    WHERE a.disconnected_at IS NULL
    GROUP BY c.container_id, c.container_name
)
SELECT *
FROM attachment_counts
WHERE network_count > 1
ORDER BY network_count DESC;

-- Workflow: detach a container from a bridge network.
-- Historical attachment records are retained.
DO $$
DECLARE
    web_id UUID;
    frontend_id UUID;
BEGIN
    SELECT container_id INTO web_id
    FROM containers WHERE container_name = 'web';

    SELECT network_id INTO frontend_id
    FROM docker_networks WHERE network_name = 'frontend';

    PERFORM detach_container(web_id, frontend_id);
END;
$$;

-- Validation: find stopped containers with active published ports.
SELECT
    c.container_name,
    c.status,
    p.host_port
FROM containers c
JOIN port_mappings p USING (container_id)
WHERE c.status <> 'RUNNING'
  AND p.active = TRUE;

-- Validation: identify active IP allocation anomalies.
SELECT
    a.network_id,
    a.ipv4_address,
    COUNT(*) AS duplicate_count
FROM network_attachments a
WHERE a.disconnected_at IS NULL
  AND a.ipv4_address IS NOT NULL
GROUP BY a.network_id, a.ipv4_address
HAVING COUNT(*) > 1;

-- Audit event reporting.
SELECT
    event_type,
    entity_type,
    description,
    occurred_at
FROM network_events
ORDER BY occurred_at DESC, event_id DESC;

COMMIT;
