-- PostgreSQL 15+
-- Regional topology, availability zones, failure domains, workload placement,
-- outage simulation, and database-enforced infrastructure integrity.

BEGIN;

CREATE SCHEMA IF NOT EXISTS regional_resilience;
SET search_path TO regional_resilience, public;

CREATE TYPE zone_status AS ENUM ('healthy', 'degraded', 'down');
CREATE TYPE replication_policy AS ENUM ('single_zone', 'multi_zone');

CREATE TABLE regions (
    region_id TEXT PRIMARY KEY,
    region_name TEXT NOT NULL,
    geographic_area TEXT NOT NULL,
    residency_group TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(trim(region_id)) > 0),
    CHECK (length(trim(region_name)) > 0)
);

CREATE TABLE availability_zones (
    zone_id TEXT PRIMARY KEY,
    region_id TEXT NOT NULL REFERENCES regions(region_id),
    zone_name TEXT NOT NULL,
    status zone_status NOT NULL DEFAULT 'healthy',
    capacity_units INTEGER NOT NULL CHECK (capacity_units >= 0),
    used_capacity_units INTEGER NOT NULL DEFAULT 0,
    estimated_latency_ms NUMERIC(10, 3) NOT NULL DEFAULT 5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (used_capacity_units >= 0),
    CHECK (used_capacity_units <= capacity_units),
    CHECK (estimated_latency_ms >= 0),
    UNIQUE (region_id, zone_name)
);

CREATE INDEX idx_zones_region_status
    ON availability_zones(region_id, status);

CREATE TABLE failure_domains (
    failure_domain_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain_name TEXT NOT NULL UNIQUE,
    domain_type TEXT NOT NULL CHECK (
        domain_type IN (
            'power', 'network', 'cooling', 'control_plane',
            'physical_site', 'unknown'
        )
    ),
    description TEXT NOT NULL DEFAULT ''
);

-- Many-to-many modeling allows a zone to share multiple known dependencies.
CREATE TABLE zone_failure_domains (
    zone_id TEXT NOT NULL REFERENCES availability_zones(zone_id)
        ON DELETE CASCADE,
    failure_domain_id BIGINT NOT NULL
        REFERENCES failure_domains(failure_domain_id),
    PRIMARY KEY (zone_id, failure_domain_id)
);

CREATE TABLE workloads (
    workload_id TEXT PRIMARY KEY,
    region_id TEXT NOT NULL REFERENCES regions(region_id),
    workload_name TEXT NOT NULL,
    replication_policy replication_policy NOT NULL DEFAULT 'multi_zone',
    desired_replicas INTEGER NOT NULL CHECK (desired_replicas >= 1),
    minimum_healthy_replicas INTEGER NOT NULL,
    data_classification TEXT NOT NULL DEFAULT 'internal',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        minimum_healthy_replicas >= 1
        AND minimum_healthy_replicas <= desired_replicas
    ),
    UNIQUE (region_id, workload_name)
);

CREATE TABLE replica_placements (
    workload_id TEXT NOT NULL REFERENCES workloads(workload_id)
        ON DELETE CASCADE,
    zone_id TEXT NOT NULL REFERENCES availability_zones(zone_id),
    replica_count INTEGER NOT NULL DEFAULT 1 CHECK (replica_count >= 1),
    placed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workload_id, zone_id)
);

CREATE INDEX idx_placements_zone ON replica_placements(zone_id);

CREATE TABLE zone_incidents (
    incident_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zone_id TEXT NOT NULL REFERENCES availability_zones(zone_id),
    incident_type TEXT NOT NULL CHECK (
        incident_type IN ('outage', 'degradation', 'recovery', 'maintenance')
    ),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    details TEXT NOT NULL DEFAULT '',
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE TABLE infrastructure_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE regional_protection_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    region_id TEXT NOT NULL REFERENCES regions(region_id),
    policy_name TEXT NOT NULL,
    minimum_zone_count INTEGER NOT NULL CHECK (minimum_zone_count >= 1),
    prohibit_single_zone_critical_workloads BOOLEAN NOT NULL DEFAULT TRUE,
    require_distinct_power_domains BOOLEAN NOT NULL DEFAULT TRUE,
    require_distinct_network_domains BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (region_id, policy_name)
);

CREATE OR REPLACE FUNCTION validate_replica_placement()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    workload_region TEXT;
    zone_region TEXT;
    workload_policy replication_policy;
    zone_health zone_status;
BEGIN
    SELECT region_id, replication_policy
      INTO workload_region, workload_policy
      FROM workloads
     WHERE workload_id = NEW.workload_id;

    SELECT region_id, status
      INTO zone_region, zone_health
      FROM availability_zones
     WHERE zone_id = NEW.zone_id
     FOR UPDATE;

    IF workload_region IS NULL OR zone_region IS NULL THEN
        RAISE EXCEPTION 'Unknown workload or zone';
    END IF;

    IF workload_region <> zone_region THEN
        RAISE EXCEPTION
            'Workload % and zone % belong to different regions',
            NEW.workload_id, NEW.zone_id;
    END IF;

    IF zone_health <> 'healthy' THEN
        RAISE EXCEPTION 'Cannot place replicas in a non-healthy zone';
    END IF;

    IF workload_policy = 'single_zone' THEN
        IF EXISTS (
            SELECT 1
              FROM replica_placements
             WHERE workload_id = NEW.workload_id
               AND zone_id <> NEW.zone_id
        ) THEN
            RAISE EXCEPTION 'Single-zone workload cannot span zones';
        END IF;
    END IF;

    IF NEW.replica_count > (
        SELECT capacity_units - used_capacity_units
          FROM availability_zones
         WHERE zone_id = NEW.zone_id
    ) THEN
        RAISE EXCEPTION 'Insufficient zone capacity';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_replica_placement
BEFORE INSERT OR UPDATE ON replica_placements
FOR EACH ROW EXECUTE FUNCTION validate_replica_placement();

CREATE OR REPLACE FUNCTION maintain_zone_capacity()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE availability_zones
           SET used_capacity_units = used_capacity_units + NEW.replica_count
         WHERE zone_id = NEW.zone_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE availability_zones
           SET used_capacity_units = used_capacity_units - OLD.replica_count
         WHERE zone_id = OLD.zone_id;
        RETURN OLD;
    ELSE
        IF OLD.zone_id = NEW.zone_id THEN
            UPDATE availability_zones
               SET used_capacity_units =
                   used_capacity_units - OLD.replica_count + NEW.replica_count
             WHERE zone_id = NEW.zone_id;
        ELSE
            UPDATE availability_zones
               SET used_capacity_units = used_capacity_units - OLD.replica_count
             WHERE zone_id = OLD.zone_id;

            UPDATE availability_zones
               SET used_capacity_units = used_capacity_units + NEW.replica_count
             WHERE zone_id = NEW.zone_id;
        END IF;
        RETURN NEW;
    END IF;
END;
$$;

CREATE TRIGGER trg_maintain_zone_capacity
AFTER INSERT OR UPDATE OR DELETE ON replica_placements
FOR EACH ROW EXECUTE FUNCTION maintain_zone_capacity();

CREATE OR REPLACE FUNCTION enforce_workload_replica_limit()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    configured_count INTEGER;
    existing_count INTEGER;
BEGIN
    SELECT desired_replicas
      INTO configured_count
      FROM workloads
     WHERE workload_id = NEW.workload_id;

    SELECT COALESCE(SUM(replica_count), 0)
      INTO existing_count
      FROM replica_placements
     WHERE workload_id = NEW.workload_id
       AND (TG_OP <> 'UPDATE'
            OR zone_id <> OLD.zone_id);

    IF existing_count + NEW.replica_count > configured_count THEN
        RAISE EXCEPTION 'Placement exceeds desired replica count';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_enforce_workload_replica_limit
BEFORE INSERT OR UPDATE ON replica_placements
FOR EACH ROW EXECUTE FUNCTION enforce_workload_replica_limit();

CREATE OR REPLACE VIEW workload_health AS
SELECT
    w.workload_id,
    w.workload_name,
    w.region_id,
    w.desired_replicas,
    w.minimum_healthy_replicas,
    COALESCE(SUM(
        CASE WHEN z.status = 'healthy'
             THEN p.replica_count ELSE 0 END
    ), 0)::INTEGER AS healthy_replicas,
    COALESCE(SUM(p.replica_count), 0)::INTEGER AS placed_replicas,
    (
        COALESCE(SUM(
            CASE WHEN z.status = 'healthy'
                 THEN p.replica_count ELSE 0 END
        ), 0) >= w.minimum_healthy_replicas
    ) AS service_available
FROM workloads w
LEFT JOIN replica_placements p ON p.workload_id = w.workload_id
LEFT JOIN availability_zones z ON z.zone_id = p.zone_id
GROUP BY
    w.workload_id,
    w.workload_name,
    w.region_id,
    w.desired_replicas,
    w.minimum_healthy_replicas;

CREATE OR REPLACE VIEW zone_capacity_report AS
SELECT
    r.region_id,
    r.region_name,
    z.zone_id,
    z.zone_name,
    z.status,
    z.capacity_units,
    z.used_capacity_units,
    z.capacity_units - z.used_capacity_units AS free_capacity_units,
    z.estimated_latency_ms
FROM regions r
JOIN availability_zones z ON z.region_id = r.region_id;

INSERT INTO regions
    (region_id, region_name, geographic_area, residency_group)
VALUES
    ('ap-south', 'South Asia', 'Asia', 'IN'),
    ('eu-central', 'Central Europe', 'Europe', 'EU');

INSERT INTO availability_zones
    (zone_id, region_id, zone_name, capacity_units, estimated_latency_ms)
VALUES
    ('south-a', 'ap-south', 'Zone A', 100, 4),
    ('south-b', 'ap-south', 'Zone B', 100, 6),
    ('south-c', 'ap-south', 'Zone C', 100, 8),
    ('eu-a', 'eu-central', 'Zone A', 100, 90),
    ('eu-b', 'eu-central', 'Zone B', 100, 95);

INSERT INTO failure_domains (domain_name, domain_type, description)
VALUES
    ('power-a', 'power', 'Independent modeled power supply A'),
    ('power-b', 'power', 'Independent modeled power supply B'),
    ('power-c', 'power', 'Independent modeled power supply C'),
    ('network-a', 'network', 'Modeled network path A'),
    ('network-b', 'network', 'Modeled network path B'),
    ('network-c', 'network', 'Modeled network path C');

INSERT INTO zone_failure_domains (zone_id, failure_domain_id)
SELECT mapping.zone_id, domain.failure_domain_id
FROM (
    VALUES
        ('south-a', 'power-a'),
        ('south-b', 'power-b'),
        ('south-c', 'power-c'),
        ('south-a', 'network-a'),
        ('south-b', 'network-b'),
        ('south-c', 'network-c')
) AS mapping(zone_id, domain_name)
JOIN failure_domains domain
  ON domain.domain_name = mapping.domain_name;

INSERT INTO workloads
    (workload_id, region_id, workload_name, desired_replicas,
     minimum_healthy_replicas, data_classification)
VALUES
    ('checkout', 'ap-south', 'Checkout API', 3, 2, 'confidential'),
    ('ledger', 'ap-south', 'Ledger Service', 2, 2, 'restricted');

INSERT INTO regional_protection_policies
    (region_id, policy_name, minimum_zone_count,
     prohibit_single_zone_critical_workloads,
     require_distinct_power_domains, require_distinct_network_domains)
VALUES
    ('ap-south', 'production-resilience', 3, TRUE, TRUE, TRUE);

-- Placement triggers validate region boundaries and maintain capacity counters.
INSERT INTO replica_placements (workload_id, zone_id, replica_count)
VALUES
    ('checkout', 'south-a', 1),
    ('checkout', 'south-b', 1),
    ('checkout', 'south-c', 1),
    ('ledger', 'south-a', 1),
    ('ledger', 'south-b', 1);

-- Verify replica distribution and shared modeled failure domains.
SELECT
    p.workload_id,
    p.zone_id,
    p.replica_count,
    array_agg(fd.domain_name ORDER BY fd.domain_name) AS failure_domains
FROM replica_placements p
JOIN zone_failure_domains zfd ON zfd.zone_id = p.zone_id
JOIN failure_domains fd ON fd.failure_domain_id = zfd.failure_domain_id
GROUP BY p.workload_id, p.zone_id, p.replica_count
ORDER BY p.workload_id, p.zone_id;

-- Find workloads that currently fail their minimum healthy replica requirement.
SELECT *
FROM workload_health
WHERE NOT service_available;

-- Detect workloads whose replicas occupy too few distinct zones.
SELECT
    w.workload_id,
    w.workload_name,
    COUNT(DISTINCT p.zone_id) AS zone_count,
    w.desired_replicas
FROM workloads w
LEFT JOIN replica_placements p ON p.workload_id = w.workload_id
GROUP BY w.workload_id, w.workload_name, w.desired_replicas
HAVING COUNT(DISTINCT p.zone_id) < w.desired_replicas;

-- Check whether replicas share any explicitly modeled failure domain.
SELECT
    p1.workload_id,
    p1.zone_id AS first_zone,
    p2.zone_id AS second_zone,
    fd.domain_name,
    fd.domain_type
FROM replica_placements p1
JOIN replica_placements p2
  ON p1.workload_id = p2.workload_id
 AND p1.zone_id < p2.zone_id
JOIN zone_failure_domains d1 ON d1.zone_id = p1.zone_id
JOIN zone_failure_domains d2
  ON d2.failure_domain_id = d1.failure_domain_id
JOIN failure_domains fd ON fd.failure_domain_id = d1.failure_domain_id
WHERE d2.zone_id = p2.zone_id
ORDER BY p1.workload_id, fd.domain_name;

-- Simulate an outage transactionally and inspect the effect on workload health.
SAVEPOINT before_zone_outage;

UPDATE availability_zones
   SET status = 'down'
 WHERE zone_id = 'south-a';

INSERT INTO zone_incidents (zone_id, incident_type, details)
VALUES ('south-a', 'outage', 'Demonstration of a complete zone outage');

INSERT INTO infrastructure_audit
    (event_type, subject_type, subject_id, details)
VALUES
    ('zone_outage_simulated', 'availability_zone', 'south-a',
     '{"simulation": true, "reason": "resilience validation"}'::jsonb);

SELECT * FROM workload_health ORDER BY workload_id;

-- A recovery returns the zone to service. Real recovery also requires health
-- checks, replica consistency validation, and controlled traffic restoration.
UPDATE availability_zones
   SET status = 'healthy'
 WHERE zone_id = 'south-a';

UPDATE zone_incidents
   SET ended_at = now()
 WHERE zone_id = 'south-a'
   AND incident_type = 'outage'
   AND ended_at IS NULL;

SELECT * FROM zone_capacity_report ORDER BY region_id, zone_id;
SELECT * FROM workload_health ORDER BY workload_id;

COMMIT;

-- Invalid placement examples are intentionally not executed because they
-- should raise errors and abort their current transaction:
-- INSERT INTO replica_placements VALUES ('checkout', 'eu-a', 1, now());
-- UPDATE availability_zones SET capacity_units = 0 WHERE zone_id = 'south-b';
--
-- Cross-region placement is rejected by validate_replica_placement().
-- Capacity counters are maintained by triggers and constrained by the table.
-- Operational deployments should also serialize competing allocations,
-- enforce role permissions, and protect status transitions with audited
-- administrative procedures.
