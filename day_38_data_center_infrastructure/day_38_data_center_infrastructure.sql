DROP SCHEMA IF EXISTS datacenter CASCADE;
CREATE SCHEMA datacenter;

SET search_path = datacenter;

-- PostgreSQL is used because generated identity columns, CHECK constraints,
-- partial indexes, JSONB, CTEs, and transactional semantics are useful for
-- modeling physical infrastructure and its operating state.

CREATE TYPE server_state AS ENUM (
    'RUNNING',
    'FAILED',
    'MAINTENANCE'
);

CREATE TYPE power_configuration AS ENUM (
    'SINGLE_A',
    'SINGLE_B',
    'DUAL'
);

CREATE TABLE data_center (
    data_center_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE,
    location text NOT NULL,
    total_floor_area_m2 numeric(10,2) NOT NULL
        CHECK (total_floor_area_m2 > 0)
);

CREATE TABLE rack (
    rack_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    data_center_id bigint NOT NULL
        REFERENCES data_center(data_center_id)
        ON DELETE CASCADE,
    rack_label text NOT NULL,
    capacity_u integer NOT NULL DEFAULT 42
        CHECK (capacity_u > 0),
    power_capacity_kw numeric(10,2) NOT NULL
        CHECK (power_capacity_kw > 0),
    UNIQUE (data_center_id, rack_label)
);

CREATE TABLE power_feed (
    power_feed_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    data_center_id bigint NOT NULL
        REFERENCES data_center(data_center_id)
        ON DELETE CASCADE,
    feed_name text NOT NULL,
    capacity_kw numeric(10,2) NOT NULL
        CHECK (capacity_kw > 0),
    available boolean NOT NULL DEFAULT true,
    UNIQUE (data_center_id, feed_name)
);

CREATE TABLE cooling_system (
    cooling_system_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    data_center_id bigint NOT NULL
        REFERENCES data_center(data_center_id)
        ON DELETE CASCADE,
    system_name text NOT NULL,
    capacity_kw numeric(10,2) NOT NULL
        CHECK (capacity_kw > 0),
    available boolean NOT NULL DEFAULT true,
    UNIQUE (data_center_id, system_name)
);

CREATE TABLE network_switch (
    network_switch_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    data_center_id bigint NOT NULL
        REFERENCES data_center(data_center_id)
        ON DELETE CASCADE,
    switch_name text NOT NULL,
    port_capacity integer NOT NULL
        CHECK (port_capacity > 0),
    available boolean NOT NULL DEFAULT true,
    UNIQUE (data_center_id, switch_name)
);

CREATE TABLE server (
    server_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rack_id bigint NOT NULL
        REFERENCES rack(rack_id)
        ON DELETE RESTRICT,
    hostname text NOT NULL UNIQUE,
    role text NOT NULL,
    power_kw numeric(10,2) NOT NULL
        CHECK (power_kw > 0),
    network_ports integer NOT NULL DEFAULT 2
        CHECK (network_ports BETWEEN 1 AND 8),
    power_configuration power_configuration NOT NULL,
    state server_state NOT NULL DEFAULT 'RUNNING'
);

CREATE TABLE server_power_feed (
    server_id bigint NOT NULL
        REFERENCES server(server_id)
        ON DELETE CASCADE,
    power_feed_id bigint NOT NULL
        REFERENCES power_feed(power_feed_id)
        ON DELETE RESTRICT,
    allocation_kw numeric(10,2) NOT NULL
        CHECK (allocation_kw > 0),
    PRIMARY KEY (server_id, power_feed_id)
);

CREATE TABLE server_network_connection (
    server_id bigint NOT NULL
        REFERENCES server(server_id)
        ON DELETE CASCADE,
    network_switch_id bigint NOT NULL
        REFERENCES network_switch(network_switch_id)
        ON DELETE RESTRICT,
    port_number integer NOT NULL
        CHECK (port_number > 0),
    PRIMARY KEY (server_id, network_switch_id),
    UNIQUE (network_switch_id, port_number)
);

CREATE TABLE server_cooling_assignment (
    server_id bigint NOT NULL
        REFERENCES server(server_id)
        ON DELETE CASCADE,
    cooling_system_id bigint NOT NULL
        REFERENCES cooling_system(cooling_system_id)
        ON DELETE RESTRICT,
    thermal_load_kw numeric(10,2) NOT NULL
        CHECK (thermal_load_kw > 0),
    PRIMARY KEY (server_id, cooling_system_id)
);

CREATE TABLE capacity_snapshot (
    snapshot_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    data_center_id bigint NOT NULL
        REFERENCES data_center(data_center_id)
        ON DELETE CASCADE,
    captured_at timestamptz NOT NULL DEFAULT now(),
    it_load_kw numeric(12,2) NOT NULL CHECK (it_load_kw >= 0),
    cooling_load_kw numeric(12,2) NOT NULL CHECK (cooling_load_kw >= 0),
    power_load_kw numeric(12,2) NOT NULL CHECK (power_load_kw >= 0)
);

CREATE INDEX idx_rack_datacenter
    ON rack(data_center_id);

CREATE INDEX idx_server_rack
    ON server(rack_id);

CREATE INDEX idx_server_running
    ON server(rack_id)
    WHERE state = 'RUNNING';

CREATE INDEX idx_power_feed_datacenter
    ON power_feed(data_center_id);

CREATE INDEX idx_cooling_datacenter
    ON cooling_system(data_center_id);

CREATE INDEX idx_network_switch_datacenter
    ON network_switch(data_center_id);

INSERT INTO data_center (
    name,
    location,
    total_floor_area_m2
)
VALUES (
    'Enterprise Primary Data Hall',
    'Lucknow',
    1800.00
);

INSERT INTO rack (
    data_center_id,
    rack_label,
    capacity_u,
    power_capacity_kw
)
SELECT
    data_center_id,
    rack_label,
    42,
    8.00
FROM data_center,
     (VALUES ('R01'), ('R02')) AS rack_list(rack_label)
WHERE name = 'Enterprise Primary Data Hall';

INSERT INTO power_feed (
    data_center_id,
    feed_name,
    capacity_kw
)
SELECT data_center_id, feed_name, 10.00
FROM data_center,
     (VALUES ('A'), ('B')) AS feeds(feed_name)
WHERE name = 'Enterprise Primary Data Hall';

INSERT INTO cooling_system (
    data_center_id,
    system_name,
    capacity_kw
)
SELECT data_center_id, system_name, 12.00
FROM data_center,
     (VALUES ('CRAC-A'), ('CRAC-B')) AS systems(system_name)
WHERE name = 'Enterprise Primary Data Hall';

INSERT INTO network_switch (
    data_center_id,
    switch_name,
    port_capacity
)
SELECT data_center_id, switch_name, 48
FROM data_center,
     (VALUES ('TOR-A'), ('TOR-B')) AS switches(switch_name)
WHERE name = 'Enterprise Primary Data Hall';

INSERT INTO server (
    rack_id,
    hostname,
    role,
    power_kw,
    network_ports,
    power_configuration
)
SELECT
    r.rack_id,
    v.hostname,
    v.role,
    v.power_kw,
    v.network_ports,
    v.power_configuration::power_configuration
FROM rack r
JOIN data_center dc
    ON dc.data_center_id = r.data_center_id
JOIN (
    VALUES
        ('R01', 'DB-PRIMARY', 'DATABASE', 2.40, 2, 'DUAL'),
        ('R01', 'APP-01', 'APPLICATION', 1.40, 2, 'DUAL'),
        ('R02', 'APP-02', 'APPLICATION', 1.40, 2, 'DUAL'),
        ('R02', 'BACKUP-01', 'BACKUP', 1.80, 2, 'DUAL')
) AS v(
    rack_label,
    hostname,
    role,
    power_kw,
    network_ports,
    power_configuration
)
    ON v.rack_label = r.rack_label
WHERE dc.name = 'Enterprise Primary Data Hall';

-- A dual-fed server is represented with two independent allocations.
-- The database constraint allows the application to prove which feed
-- carries the load rather than merely storing a textual "redundant" flag.
INSERT INTO server_power_feed (
    server_id,
    power_feed_id,
    allocation_kw
)
SELECT
    s.server_id,
    p.power_feed_id,
    s.power_kw / 2
FROM server s
JOIN power_feed p
    ON p.feed_name IN ('A', 'B')
JOIN data_center dc
    ON dc.data_center_id = p.data_center_id
WHERE dc.name = 'Enterprise Primary Data Hall'
  AND s.power_configuration = 'DUAL';

INSERT INTO server_network_connection (
    server_id,
    network_switch_id,
    port_number
)
SELECT
    s.server_id,
    n.network_switch_id,
    ROW_NUMBER() OVER (
        PARTITION BY n.network_switch_id
        ORDER BY s.server_id
    )::integer
FROM server s
JOIN network_switch n
    ON n.switch_name IN ('TOR-A', 'TOR-B')
JOIN data_center dc
    ON dc.data_center_id = n.data_center_id
WHERE dc.name = 'Enterprise Primary Data Hall';

INSERT INTO server_cooling_assignment (
    server_id,
    cooling_system_id,
    thermal_load_kw
)
SELECT
    s.server_id,
    c.cooling_system_id,
    s.power_kw
FROM server s
JOIN cooling_system c
    ON c.system_name = 'CRAC-A'
JOIN data_center dc
    ON dc.data_center_id = c.data_center_id
WHERE dc.name = 'Enterprise Primary Data Hall';

-- Rack power utilization. This query is intentionally based on actual
-- installed equipment rather than a static rack label.
SELECT
    r.rack_label,
    r.capacity_u,
    COUNT(s.server_id) AS used_u,
    r.power_capacity_kw,
    COALESCE(SUM(s.power_kw), 0) AS used_power_kw,
    r.power_capacity_kw - COALESCE(SUM(s.power_kw), 0)
        AS remaining_power_kw
FROM rack r
LEFT JOIN server s
    ON s.rack_id = r.rack_id
   AND s.state = 'RUNNING'
GROUP BY
    r.rack_id,
    r.rack_label,
    r.capacity_u,
    r.power_capacity_kw
ORDER BY r.rack_label;

-- Power-path utilization shows whether one electrical path has become
-- a hidden bottleneck even when total facility power looks acceptable.
SELECT
    p.feed_name,
    p.capacity_kw,
    COALESCE(SUM(spf.allocation_kw), 0) AS allocated_kw,
    p.capacity_kw - COALESCE(SUM(spf.allocation_kw), 0)
        AS remaining_kw
FROM power_feed p
LEFT JOIN server_power_feed spf
    ON spf.power_feed_id = p.power_feed_id
GROUP BY
    p.power_feed_id,
    p.feed_name,
    p.capacity_kw
ORDER BY p.feed_name;

-- Cooling utilization treats electrical IT consumption as thermal load.
SELECT
    c.system_name,
    c.capacity_kw,
    COALESCE(SUM(sca.thermal_load_kw), 0) AS thermal_load_kw,
    c.capacity_kw - COALESCE(SUM(sca.thermal_load_kw), 0)
        AS remaining_kw
FROM cooling_system c
LEFT JOIN server_cooling_assignment sca
    ON sca.cooling_system_id = c.cooling_system_id
GROUP BY
    c.cooling_system_id,
    c.system_name,
    c.capacity_kw
ORDER BY c.system_name;

-- Servers with only one network connection represent a network failure
-- exposure. A redundant physical network design requires distinct switches.
SELECT
    s.hostname,
    COUNT(snc.network_switch_id) AS connected_switches
FROM server s
LEFT JOIN server_network_connection snc
    ON snc.server_id = s.server_id
GROUP BY s.server_id, s.hostname
HAVING COUNT(snc.network_switch_id) < 2;

-- Test the effect of losing power feed A. Dual-fed equipment is expected
-- to retain another electrical path.
WITH feed_failure AS (
    SELECT s.server_id, s.hostname, s.power_configuration
    FROM server s
    JOIN server_power_feed spf
        ON spf.server_id = s.server_id
    JOIN power_feed pf
        ON pf.power_feed_id = spf.power_feed_id
    WHERE pf.feed_name = 'A'
      AND s.state = 'RUNNING'
)
SELECT
    hostname,
    power_configuration,
    CASE
        WHEN power_configuration = 'DUAL'
            THEN 'SURVIVES_WITH_ALTERNATE_PATH'
        ELSE 'SINGLE_PATH_EXPOSURE'
    END AS failure_result
FROM feed_failure
ORDER BY hostname;

-- A single cooling-system failure is survivable only when remaining
-- cooling capacity is at least the active thermal load.
WITH active_load AS (
    SELECT COALESCE(SUM(power_kw), 0) AS it_load_kw
    FROM server
    WHERE state = 'RUNNING'
),
remaining_cooling AS (
    SELECT COALESCE(SUM(capacity_kw), 0) AS remaining_capacity_kw
    FROM cooling_system
    WHERE system_name <> 'CRAC-A'
      AND available = true
)
SELECT
    active_load.it_load_kw,
    remaining_cooling.remaining_capacity_kw,
    CASE
        WHEN remaining_cooling.remaining_capacity_kw >= active_load.it_load_kw
            THEN 'SURVIVABLE'
        ELSE 'INSUFFICIENT_COOLING'
    END AS cooling_failure_result
FROM active_load
CROSS JOIN remaining_cooling;

-- PUE relates total facility energy to IT energy. This example uses
-- a measured 4 kW facility overhead value.
WITH it AS (
    SELECT COALESCE(SUM(power_kw), 0) AS it_kw
    FROM server
    WHERE state = 'RUNNING'
)
SELECT
    it_kw,
    4.00 AS facility_overhead_kw,
    ROUND(((it_kw + 4.00) / NULLIF(it_kw, 0))::numeric, 3) AS pue
FROM it;

-- Demonstrate a transaction that rejects an unsafe capacity change.
BEGIN;

UPDATE rack
SET power_capacity_kw = 3.00
WHERE rack_label = 'R01';

-- The query exposes the invalid resulting state before committing.
SELECT
    r.rack_label,
    r.power_capacity_kw,
    SUM(s.power_kw) AS installed_power_kw,
    CASE
        WHEN SUM(s.power_kw) > r.power_capacity_kw
            THEN 'CAPACITY_VIOLATION'
        ELSE 'VALID'
    END AS state_check
FROM rack r
JOIN server s
    ON s.rack_id = r.rack_id
WHERE r.rack_label = 'R01'
GROUP BY r.rack_label, r.power_capacity_kw;

-- Roll back because the physical model must not retain a rack whose
-- installed IT load exceeds its stated electrical capacity.
ROLLBACK;

-- Capture a valid operational snapshot.
INSERT INTO capacity_snapshot (
    data_center_id,
    it_load_kw,
    cooling_load_kw,
    power_load_kw
)
SELECT
    dc.data_center_id,
    COALESCE((
        SELECT SUM(power_kw)
        FROM server
        WHERE state = 'RUNNING'
    ), 0),
    COALESCE((
        SELECT SUM(thermal_load_kw)
        FROM server_cooling_assignment sca
        JOIN server s
            ON s.server_id = sca.server_id
        WHERE s.state = 'RUNNING'
    ), 0),
    COALESCE((
        SELECT SUM(allocation_kw)
        FROM server_power_feed spf
        JOIN server s
            ON s.server_id = spf.server_id
        WHERE s.state = 'RUNNING'
    ), 0)
FROM data_center dc
WHERE dc.name = 'Enterprise Primary Data Hall';

SELECT
    snapshot_id,
    captured_at,
    it_load_kw,
    cooling_load_kw,
    power_load_kw
FROM capacity_snapshot
ORDER BY captured_at DESC;
