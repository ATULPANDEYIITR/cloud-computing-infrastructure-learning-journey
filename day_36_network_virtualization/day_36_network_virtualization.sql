-- PostgreSQL 16+ compatible
-- Network Virtualization Laboratory
--
-- The schema models:
--   virtual networks
--   virtual switches
--   virtual ports
--   virtual machines
--   virtual NICs
--   overlay tunnel endpoints
--   logical forwarding state
--   SDN policies
--   network packets and status observations
--
-- The database enforces structural rules while queries demonstrate
-- forwarding, isolation, overlay mapping, and operational analysis.

DROP SCHEMA IF EXISTS network_virtualization_lab CASCADE;

CREATE SCHEMA network_virtualization_lab;

SET search_path TO network_virtualization_lab;

CREATE TYPE network_kind AS ENUM (
    'FRONTEND',
    'BACKEND',
    'DATABASE',
    'MANAGEMENT'
);

CREATE TYPE policy_action AS ENUM (
    'ALLOW',
    'DENY'
);

CREATE TYPE port_state AS ENUM (
    'UP',
    'DOWN'
);

CREATE TYPE port_kind AS ENUM (
    'HOST',
    'UPLINK',
    'PATCH'
);

CREATE TYPE packet_result AS ENUM (
    'FORWARDED',
    'FLOODED',
    'ROUTED',
    'DROPPED',
    'DENIED'
);

CREATE TABLE virtual_network (
    network_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    network_name TEXT NOT NULL UNIQUE,
    network_kind network_kind NOT NULL,
    cidr CIDR NOT NULL,
    vlan_id INTEGER NOT NULL UNIQUE,
    vni INTEGER NOT NULL UNIQUE,
    gateway INET NOT NULL,
    isolated BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT virtual_network_vlan_range
        CHECK (vlan_id BETWEEN 1 AND 4094),

    CONSTRAINT virtual_network_vni_range
        CHECK (vni BETWEEN 1 AND 16777215),

    CONSTRAINT virtual_network_gateway_family
        CHECK (family(gateway) = 4),

    CONSTRAINT virtual_network_gateway_inside_subnet
        CHECK (gateway <<= cidr)
);

CREATE TABLE virtual_switch (
    switch_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    switch_name TEXT NOT NULL UNIQUE,
    management_ip INET,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE virtual_port (
    port_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    switch_id BIGINT NOT NULL REFERENCES virtual_switch(switch_id),
    port_name TEXT NOT NULL,
    port_kind port_kind NOT NULL,
    state port_state NOT NULL DEFAULT 'UP',

    CONSTRAINT unique_switch_port
        UNIQUE (switch_id, port_name)
);

CREATE TABLE virtual_machine (
    vm_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_name TEXT NOT NULL UNIQUE,
    host_node TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE virtual_nic (
    nic_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id BIGINT NOT NULL REFERENCES virtual_machine(vm_id),
    network_id BIGINT NOT NULL REFERENCES virtual_network(network_id),
    port_id BIGINT REFERENCES virtual_port(port_id),
    nic_name TEXT NOT NULL,
    mac_address MACADDR NOT NULL UNIQUE,
    ip_address INET NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT unique_vm_nic_name
        UNIQUE (vm_id, nic_name)
);

CREATE TABLE overlay_endpoint (
    endpoint_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    network_id BIGINT NOT NULL REFERENCES virtual_network(network_id),
    endpoint_name TEXT NOT NULL,
    underlay_ip INET NOT NULL,
    vni INTEGER NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT overlay_vni_range
        CHECK (vni BETWEEN 1 AND 16777215),

    CONSTRAINT unique_overlay_endpoint
        UNIQUE (network_id, endpoint_name)
);

CREATE TABLE overlay_mac_location (
    mac_location_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    endpoint_id BIGINT NOT NULL REFERENCES overlay_endpoint(endpoint_id),
    mac_address MACADDR NOT NULL,
    learned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,

    CONSTRAINT unique_overlay_mac
        UNIQUE (mac_address),

    CONSTRAINT valid_mac_location_lifetime
        CHECK (
            expires_at IS NULL
            OR expires_at > learned_at
        )
);

CREATE TABLE sdn_policy (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_network_id BIGINT NOT NULL
        REFERENCES virtual_network(network_id),
    destination_network_id BIGINT NOT NULL
        REFERENCES virtual_network(network_id),
    action policy_action NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    description TEXT NOT NULL,

    CONSTRAINT policy_priority_range
        CHECK (priority >= 0),

    CONSTRAINT unique_policy_priority
        UNIQUE (
            source_network_id,
            destination_network_id,
            priority
        )
);

CREATE TABLE mac_forwarding_entry (
    forwarding_entry_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    switch_id BIGINT NOT NULL REFERENCES virtual_switch(switch_id),
    vlan_id INTEGER REFERENCES virtual_network(vlan_id),
    mac_address MACADDR NOT NULL,
    output_port_id BIGINT NOT NULL REFERENCES virtual_port(port_id),
    learned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    packet_count BIGINT NOT NULL DEFAULT 0,
    byte_count BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT forwarding_vlan_range
        CHECK (
            vlan_id IS NULL
            OR vlan_id BETWEEN 1 AND 4094
        ),

    CONSTRAINT forwarding_packet_count
        CHECK (packet_count >= 0),

    CONSTRAINT forwarding_byte_count
        CHECK (byte_count >= 0),

    CONSTRAINT unique_switch_vlan_mac
        UNIQUE (switch_id, vlan_id, mac_address)
);

CREATE TABLE packet_event (
    packet_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_nic_id BIGINT REFERENCES virtual_nic(nic_id),
    destination_nic_id BIGINT REFERENCES virtual_nic(nic_id),
    source_mac MACADDR NOT NULL,
    destination_mac MACADDR NOT NULL,
    source_ip INET,
    destination_ip INET,
    vlan_id INTEGER,
    vni INTEGER,
    result packet_result NOT NULL,
    reason TEXT,
    payload_bytes INTEGER NOT NULL DEFAULT 0,
    ttl INTEGER NOT NULL DEFAULT 64,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT packet_payload_size
        CHECK (payload_bytes >= 0),

    CONSTRAINT packet_ttl_range
        CHECK (ttl BETWEEN 0 AND 255),

    CONSTRAINT packet_vlan_range
        CHECK (
            vlan_id IS NULL
            OR vlan_id BETWEEN 1 AND 4094
        ),

    CONSTRAINT packet_vni_range
        CHECK (
            vni IS NULL
            OR vni BETWEEN 1 AND 16777215
        )
);

CREATE INDEX idx_virtual_nic_network
    ON virtual_nic(network_id);

CREATE INDEX idx_virtual_nic_ip
    ON virtual_nic(ip_address);

CREATE INDEX idx_virtual_port_switch_state
    ON virtual_port(switch_id, state);

CREATE INDEX idx_forwarding_lookup
    ON mac_forwarding_entry(switch_id, vlan_id, mac_address);

CREATE INDEX idx_overlay_mac_lookup
    ON overlay_mac_location(mac_address);

CREATE INDEX idx_packet_destination
    ON packet_event(destination_ip, occurred_at DESC);

CREATE INDEX idx_packet_result_time
    ON packet_event(result, occurred_at DESC);

INSERT INTO virtual_network
    (
        network_name,
        network_kind,
        cidr,
        vlan_id,
        vni,
        gateway,
        isolated
    )
VALUES
    (
        'frontend',
        'FRONTEND',
        '10.10.10.0/24',
        110,
        5001,
        '10.10.10.1',
        FALSE
    ),
    (
        'backend',
        'BACKEND',
        '10.10.20.0/24',
        120,
        5002,
        '10.10.20.1',
        FALSE
    ),
    (
        'database',
        'DATABASE',
        '10.10.30.0/24',
        130,
        5003,
        '10.10.30.1',
        TRUE
    ),
    (
        'management',
        'MANAGEMENT',
        '10.10.40.0/24',
        140,
        5004,
        '10.10.40.1',
        TRUE
    );

INSERT INTO virtual_switch
    (switch_name, management_ip)
VALUES
    ('vswitch-a', '192.0.2.10'),
    ('vswitch-b', '192.0.2.20');

INSERT INTO virtual_port
    (switch_id, port_name, port_kind)
SELECT
    switch_id,
    'web-port',
    'HOST'
FROM virtual_switch
WHERE switch_name = 'vswitch-a';

INSERT INTO virtual_port
    (switch_id, port_name, port_kind)
SELECT
    switch_id,
    'app-port',
    'HOST'
FROM virtual_switch
WHERE switch_name = 'vswitch-a';

INSERT INTO virtual_port
    (switch_id, port_name, port_kind)
SELECT
    switch_id,
    'overlay-uplink',
    'UPLINK'
FROM virtual_switch
WHERE switch_name = 'vswitch-a';

INSERT INTO virtual_port
    (switch_id, port_name, port_kind)
SELECT
    switch_id,
    'db-port',
    'HOST'
FROM virtual_switch
WHERE switch_name = 'vswitch-b';

INSERT INTO virtual_port
    (switch_id, port_name, port_kind)
SELECT
    switch_id,
    'overlay-uplink',
    'UPLINK'
FROM virtual_switch
WHERE switch_name = 'vswitch-b';

INSERT INTO virtual_machine
    (vm_name, host_node)
VALUES
    ('web-01', 'compute-a'),
    ('app-01', 'compute-a'),
    ('db-01', 'compute-b');

INSERT INTO virtual_nic
    (
        vm_id,
        network_id,
        port_id,
        nic_name,
        mac_address,
        ip_address
    )
SELECT
    vm.vm_id,
    vn.network_id,
    vp.port_id,
    'eth0',
    '02:00:00:00:10:01',
    '10.10.10.10'
FROM virtual_machine vm
JOIN virtual_network vn
    ON vn.network_name = 'frontend'
JOIN virtual_port vp
    ON vp.port_name = 'web-port'
JOIN virtual_switch vs
    ON vs.switch_id = vp.switch_id
WHERE vm.vm_name = 'web-01'
  AND vs.switch_name = 'vswitch-a';

INSERT INTO virtual_nic
    (
        vm_id,
        network_id,
        port_id,
        nic_name,
        mac_address,
        ip_address
    )
SELECT
    vm.vm_id,
    vn.network_id,
    vp.port_id,
    'eth0',
    '02:00:00:00:20:01',
    '10.10.20.10'
FROM virtual_machine vm
JOIN virtual_network vn
    ON vn.network_name = 'backend'
JOIN virtual_port vp
    ON vp.port_name = 'app-port'
JOIN virtual_switch vs
    ON vs.switch_id = vp.switch_id
WHERE vm.vm_name = 'app-01'
  AND vs.switch_name = 'vswitch-a';

INSERT INTO virtual_nic
    (
        vm_id,
        network_id,
        port_id,
        nic_name,
        mac_address,
        ip_address
    )
SELECT
    vm.vm_id,
    vn.network_id,
    vp.port_id,
    'eth0',
    '02:00:00:00:30:01',
    '10.10.30.10'
FROM virtual_machine vm
JOIN virtual_network vn
    ON vn.network_name = 'database'
JOIN virtual_port vp
    ON vp.port_name = 'db-port'
JOIN virtual_switch vs
    ON vs.switch_id = vp.switch_id
WHERE vm.vm_name = 'db-01'
  AND vs.switch_name = 'vswitch-b';

INSERT INTO overlay_endpoint
    (
        network_id,
        endpoint_name,
        underlay_ip,
        vni
    )
SELECT
    network_id,
    'vtep-a-frontend',
    '192.0.2.10',
    vni
FROM virtual_network
WHERE network_name = 'frontend';

INSERT INTO overlay_endpoint
    (
        network_id,
        endpoint_name,
        underlay_ip,
        vni
    )
SELECT
    network_id,
    'vtep-a-backend',
    '192.0.2.10',
    vni
FROM virtual_network
WHERE network_name = 'backend';

INSERT INTO overlay_endpoint
    (
        network_id,
        endpoint_name,
        underlay_ip,
        vni
    )
SELECT
    network_id,
    'vtep-b-database',
    '192.0.2.20',
    vni
FROM virtual_network
WHERE network_name = 'database';

INSERT INTO overlay_mac_location
    (
        endpoint_id,
        mac_address
    )
SELECT
    oe.endpoint_id,
    vn_mac.mac_address
FROM overlay_endpoint oe
JOIN virtual_network vn
    ON vn.network_id = oe.network_id
JOIN (
    SELECT
        network_id,
        mac_address
    FROM virtual_nic
) AS vn_mac
    ON vn_mac.network_id = vn.network_id;

INSERT INTO sdn_policy
    (
        source_network_id,
        destination_network_id,
        action,
        priority,
        description
    )
SELECT
    source.network_id,
    destination.network_id,
    'ALLOW',
    100,
    'Same-segment traffic is allowed'
FROM virtual_network source
JOIN virtual_network destination
    ON source.network_id = destination.network_id;

INSERT INTO sdn_policy
    (
        source_network_id,
        destination_network_id,
        action,
        priority,
        description
    )
SELECT
    source.network_id,
    destination.network_id,
    'ALLOW',
    100,
    'Frontend services may call backend services'
FROM virtual_network source
JOIN virtual_network destination
    ON destination.network_name = 'backend'
WHERE source.network_name = 'frontend';

INSERT INTO sdn_policy
    (
        source_network_id,
        destination_network_id,
        action,
        priority,
        description
    )
SELECT
    source.network_id,
    destination.network_id,
    'ALLOW',
    100,
    'Backend services may reach database services'
FROM virtual_network source
JOIN virtual_network destination
    ON destination.network_name = 'database'
WHERE source.network_name = 'backend';

INSERT INTO sdn_policy
    (
        source_network_id,
        destination_network_id,
        action,
        priority,
        description
    )
SELECT
    source.network_id,
    destination.network_id,
    'DENY',
    50,
    'Frontend must not directly access the isolated database segment'
FROM virtual_network source
JOIN virtual_network destination
    ON destination.network_name = 'database'
WHERE source.network_name = 'frontend';

INSERT INTO sdn_policy
    (
        source_network_id,
        destination_network_id,
        action,
        priority,
        description
    )
SELECT
    source.network_id,
    destination.network_id,
    'DENY',
    50,
    'Database segment must not initiate frontend traffic'
FROM virtual_network source
JOIN virtual_network destination
    ON destination.network_name = 'frontend'
WHERE source.network_name = 'database';

INSERT INTO mac_forwarding_entry
    (
        switch_id,
        vlan_id,
        mac_address,
        output_port_id,
        packet_count,
        byte_count
    )
SELECT
    vs.switch_id,
    vn.vlan_id,
    nic.mac_address,
    vp.port_id,
    25,
    4096
FROM virtual_nic nic
JOIN virtual_network vn
    ON vn.network_id = nic.network_id
JOIN virtual_port vp
    ON vp.port_id = nic.port_id
JOIN virtual_switch vs
    ON vs.switch_id = vp.switch_id;

INSERT INTO packet_event
    (
        source_nic_id,
        destination_nic_id,
        source_mac,
        destination_mac,
        source_ip,
        destination_ip,
        vlan_id,
        vni,
        result,
        reason,
        payload_bytes,
        ttl
    )
SELECT
    source.nic_id,
    destination.nic_id,
    source.mac_address,
    destination.mac_address,
    source.ip_address,
    destination.ip_address,
    source_network.vlan_id,
    source_network.vni,
    'FORWARDED',
    'Known destination learned by virtual switch',
    1200,
    64
FROM virtual_nic source
JOIN virtual_nic destination
    ON destination.ip_address = '10.10.20.10'
JOIN virtual_network source_network
    ON source_network.network_id = source.network_id
WHERE source.ip_address = '10.10.10.10';

INSERT INTO packet_event
    (
        source_nic_id,
        destination_nic_id,
        source_mac,
        destination_mac,
        source_ip,
        destination_ip,
        vlan_id,
        vni,
        result,
        reason,
        payload_bytes,
        ttl
    )
SELECT
    source.nic_id,
    destination.nic_id,
    source.mac_address,
    destination.mac_address,
    source.ip_address,
    destination.ip_address,
    source_network.vlan_id,
    source_network.vni,
    'ROUTED',
    'Inter-network traffic permitted by SDN policy',
    900,
    63
FROM virtual_nic source
JOIN virtual_nic destination
    ON destination.ip_address = '10.10.20.10'
JOIN virtual_network source_network
    ON source_network.network_id = source.network_id
WHERE source.ip_address = '10.10.10.10';

INSERT INTO packet_event
    (
        source_nic_id,
        destination_nic_id,
        source_mac,
        destination_mac,
        source_ip,
        destination_ip,
        vlan_id,
        vni,
        result,
        reason,
        payload_bytes,
        ttl
    )
SELECT
    source.nic_id,
    destination.nic_id,
    source.mac_address,
    destination.mac_address,
    source.ip_address,
    destination.ip_address,
    source_network.vlan_id,
    source_network.vni,
    'DENIED',
    'Frontend to isolated database policy',
    700,
    64
FROM virtual_nic source
JOIN virtual_nic destination
    ON destination.ip_address = '10.10.30.10'
JOIN virtual_network source_network
    ON source_network.network_id = source.network_id
WHERE source.ip_address = '10.10.10.10';

-- Network inventory query.
SELECT
    network_name,
    network_kind,
    cidr,
    vlan_id,
    vni,
    gateway,
    isolated
FROM virtual_network
ORDER BY vlan_id;

-- Show the logical relationship between virtual NICs, VMs,
-- virtual networks, and switch ports.
SELECT
    vm.vm_name,
    nic.nic_name,
    nic.mac_address,
    nic.ip_address,
    vn.network_name,
    vn.vlan_id,
    vn.vni,
    vs.switch_name,
    vp.port_name,
    vp.state
FROM virtual_machine vm
JOIN virtual_nic nic
    ON nic.vm_id = vm.vm_id
JOIN virtual_network vn
    ON vn.network_id = nic.network_id
LEFT JOIN virtual_port vp
    ON vp.port_id = nic.port_id
LEFT JOIN virtual_switch vs
    ON vs.switch_id = vp.switch_id
ORDER BY vm.vm_name;

-- SDN policy matrix.
SELECT
    source.network_name AS source_network,
    destination.network_name AS destination_network,
    policy.action,
    policy.priority,
    policy.description
FROM sdn_policy policy
JOIN virtual_network source
    ON source.network_id = policy.source_network_id
JOIN virtual_network destination
    ON destination.network_id = policy.destination_network_id
ORDER BY
    source.network_name,
    destination.network_name,
    policy.priority;

-- Determine the effective policy using the highest-priority rule.
WITH ranked_policy AS (
    SELECT
        source_network_id,
        destination_network_id,
        action,
        priority,
        ROW_NUMBER() OVER (
            PARTITION BY
                source_network_id,
                destination_network_id
            ORDER BY priority ASC
        ) AS rule_rank
    FROM sdn_policy
)
SELECT
    source.network_name AS source_network,
    destination.network_name AS destination_network,
    ranked_policy.action AS effective_action,
    ranked_policy.priority
FROM ranked_policy
JOIN virtual_network source
    ON source.network_id = ranked_policy.source_network_id
JOIN virtual_network destination
    ON destination.network_id = ranked_policy.destination_network_id
WHERE ranked_policy.rule_rank = 1
ORDER BY source.network_name, destination.network_name;

-- Overlay endpoint view: the VNI identifies the logical segment while
-- the underlay IP identifies the physical transport endpoint.
SELECT
    vn.network_name,
    oe.endpoint_name,
    oe.underlay_ip,
    oe.vni,
    oe.enabled
FROM overlay_endpoint oe
JOIN virtual_network vn
    ON vn.network_id = oe.network_id
ORDER BY oe.underlay_ip, oe.vni;

-- MAC learning database used by the virtual switches.
SELECT
    vs.switch_name,
    mfe.vlan_id,
    mfe.mac_address,
    vp.port_name,
    mfe.packet_count,
    mfe.byte_count,
    mfe.last_seen_at
FROM mac_forwarding_entry mfe
JOIN virtual_switch vs
    ON vs.switch_id = mfe.switch_id
JOIN virtual_port vp
    ON vp.port_id = mfe.output_port_id
ORDER BY vs.switch_name, mfe.vlan_id, mfe.mac_address;

-- Identify isolated networks and their attached workloads.
SELECT
    vn.network_name,
    vn.cidr,
    vm.vm_name,
    nic.ip_address
FROM virtual_network vn
JOIN virtual_nic nic
    ON nic.network_id = vn.network_id
JOIN virtual_machine vm
    ON vm.vm_id = nic.vm_id
WHERE vn.isolated = TRUE
ORDER BY vn.network_name, vm.vm_name;

-- Operational packet-result analysis.
SELECT
    result,
    COUNT(*) AS event_count,
    COALESCE(SUM(payload_bytes), 0) AS total_payload_bytes
FROM packet_event
GROUP BY result
ORDER BY event_count DESC;

-- Explain why denied traffic exists in the event stream.
SELECT
    occurred_at,
    source_ip,
    destination_ip,
    result,
    reason
FROM packet_event
WHERE result = 'DENIED'
ORDER BY occurred_at DESC;

-- Find disabled virtual ports that could explain forwarding failures.
SELECT
    vs.switch_name,
    vp.port_name,
    vp.port_kind,
    vp.state
FROM virtual_port vp
JOIN virtual_switch vs
    ON vs.switch_id = vp.switch_id
WHERE vp.state = 'DOWN'
ORDER BY vs.switch_name, vp.port_name;

-- Transactional demonstration:
-- moving a virtual NIC to another virtual switch port must be performed
-- atomically so the inventory does not temporarily point at the wrong port.
BEGIN;

WITH target_port AS (
    SELECT vp.port_id
    FROM virtual_port vp
    JOIN virtual_switch vs
        ON vs.switch_id = vp.switch_id
    WHERE vs.switch_name = 'vswitch-a'
      AND vp.port_name = 'app-port'
)
UPDATE virtual_nic
SET port_id = (
    SELECT port_id
    FROM target_port
)
WHERE mac_address = '02:00:00:00:20:01';

COMMIT;

-- Database-level integrity check:
-- This query exposes any NIC whose IP does not belong to its logical
-- virtual network. A production system could turn the invariant into
-- a trigger if application-side validation is not sufficient.
SELECT
    vm.vm_name,
    nic.nic_name,
    nic.ip_address,
    vn.network_name,
    vn.cidr
FROM virtual_nic nic
JOIN virtual_machine vm
    ON vm.vm_id = nic.vm_id
JOIN virtual_network vn
    ON vn.network_id = nic.network_id
WHERE NOT (
    nic.ip_address <<= vn.cidr
);

-- Performance-oriented query:
-- This lookup matches the operation a virtual switch needs when it searches
-- for a learned destination MAC within a VLAN.
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    output_port_id,
    packet_count,
    byte_count,
    last_seen_at
FROM mac_forwarding_entry
WHERE switch_id = (
    SELECT switch_id
    FROM virtual_switch
    WHERE switch_name = 'vswitch-a'
)
AND vlan_id = 120
AND mac_address = '02:00:00:00:20:01';

-- Security-oriented query:
-- Find policies that explicitly expose an isolated network.
SELECT
    source.network_name AS source_network,
    destination.network_name AS isolated_destination,
    policy.action,
    policy.priority
FROM sdn_policy policy
JOIN virtual_network source
    ON source.network_id = policy.source_network_id
JOIN virtual_network destination
    ON destination.network_id = policy.destination_network_id
WHERE destination.isolated = TRUE
  AND policy.action = 'ALLOW'
ORDER BY destination.network_name, policy.priority;
