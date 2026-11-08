/*
 * CLOUD NETWORK SECURITY MANAGEMENT DATABASE
 *
 * PostgreSQL 14+
 *
 * Models:
 *   1. Cloud accounts and network resources
 *   2. Security groups and stateful allow rules
 *   3. Network ACLs and stateless ordered rules
 *   4. Stateful perimeter firewalls
 *   5. Packet inspection requests
 *   6. Connection tracking
 *   7. Policy evaluation and audit trails
 *   8. Rule validation and reporting
 *
 * Execute as a database role authorized to create schemas.
 */

BEGIN;

CREATE SCHEMA IF NOT EXISTS cloud_security;

SET search_path TO cloud_security, public;

CREATE TYPE traffic_direction AS ENUM (
    'inbound',
    'outbound'
);

CREATE TYPE traffic_action AS ENUM (
    'allow',
    'deny'
);

CREATE TYPE network_protocol AS ENUM (
    'tcp',
    'udp',
    'icmp',
    'all'
);

CREATE TYPE policy_layer AS ENUM (
    'security_group',
    'network_acl',
    'firewall'
);

CREATE TYPE inspection_decision AS ENUM (
    'allow',
    'deny'
);

CREATE TYPE resource_status AS ENUM (
    'active',
    'disabled',
    'under_review'
);

CREATE TYPE connection_status AS ENUM (
    'established',
    'expired',
    'closed'
);

CREATE TABLE cloud_accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_name VARCHAR(120) NOT NULL UNIQUE,
    cloud_provider VARCHAR(40) NOT NULL,
    environment VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (environment IN (
        'development',
        'testing',
        'staging',
        'production'
    ))
);

CREATE TABLE network_resources (
    resource_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL
        REFERENCES cloud_accounts(account_id),
    resource_name VARCHAR(120) NOT NULL,
    resource_type VARCHAR(40) NOT NULL,
    cidr_block CIDR NOT NULL,
    status resource_status NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (account_id, resource_name),

    CHECK (resource_type IN (
        'vpc',
        'subnet',
        'instance',
        'load_balancer',
        'database'
    ))
);

CREATE TABLE security_groups (
    security_group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    resource_id BIGINT NOT NULL
        REFERENCES network_resources(resource_id),
    group_name VARCHAR(120) NOT NULL,
    description TEXT,
    stateful BOOLEAN NOT NULL DEFAULT TRUE,
    status resource_status NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (resource_id, group_name),

    CHECK (stateful = TRUE)
);

CREATE TABLE security_group_rules (
    rule_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    security_group_id BIGINT NOT NULL
        REFERENCES security_groups(security_group_id)
        ON DELETE CASCADE,
    rule_key VARCHAR(80) NOT NULL,
    direction traffic_direction NOT NULL,
    protocol network_protocol NOT NULL,
    cidr CIDR NOT NULL,
    port_start INTEGER NOT NULL DEFAULT 0,
    port_end INTEGER NOT NULL DEFAULT 65535,
    description TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (security_group_id, rule_key),

    CHECK (port_start BETWEEN 0 AND 65535),
    CHECK (port_end BETWEEN 0 AND 65535),
    CHECK (port_start <= port_end),

    CHECK (
        protocol NOT IN ('icmp', 'all')
        OR (port_start = 0 AND port_end = 65535)
    )
);

CREATE TABLE network_acls (
    acl_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    resource_id BIGINT NOT NULL
        REFERENCES network_resources(resource_id),
    acl_name VARCHAR(120) NOT NULL,
    stateful BOOLEAN NOT NULL DEFAULT FALSE,
    status resource_status NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (resource_id, acl_name),

    CHECK (stateful = FALSE)
);

CREATE TABLE network_acl_rules (
    rule_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    acl_id BIGINT NOT NULL
        REFERENCES network_acls(acl_id)
        ON DELETE CASCADE,
    rule_number INTEGER NOT NULL,
    direction traffic_direction NOT NULL,
    action traffic_action NOT NULL,
    protocol network_protocol NOT NULL,
    cidr CIDR NOT NULL,
    port_start INTEGER NOT NULL DEFAULT 0,
    port_end INTEGER NOT NULL DEFAULT 65535,
    description TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    UNIQUE (acl_id, rule_number),

    CHECK (rule_number > 0),
    CHECK (port_start BETWEEN 0 AND 65535),
    CHECK (port_end BETWEEN 0 AND 65535),
    CHECK (port_start <= port_end),

    CHECK (
        protocol NOT IN ('icmp', 'all')
        OR (port_start = 0 AND port_end = 65535)
    )
);

CREATE TABLE firewalls (
    firewall_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL
        REFERENCES cloud_accounts(account_id),
    firewall_name VARCHAR(120) NOT NULL,
    stateful BOOLEAN NOT NULL DEFAULT TRUE,
    status resource_status NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (account_id, firewall_name),

    CHECK (stateful = TRUE)
);

CREATE TABLE firewall_rules (
    rule_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    firewall_id BIGINT NOT NULL
        REFERENCES firewalls(firewall_id)
        ON DELETE CASCADE,
    rule_key VARCHAR(80) NOT NULL,
    priority INTEGER NOT NULL,
    direction traffic_direction NOT NULL,
    action traffic_action NOT NULL,
    protocol network_protocol NOT NULL,
    cidr CIDR NOT NULL,
    port_start INTEGER NOT NULL DEFAULT 0,
    port_end INTEGER NOT NULL DEFAULT 65535,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    description TEXT,

    UNIQUE (firewall_id, rule_key),

    CHECK (priority >= 0),
    CHECK (port_start BETWEEN 0 AND 65535),
    CHECK (port_end BETWEEN 0 AND 65535),
    CHECK (port_start <= port_end),

    CHECK (
        protocol NOT IN ('icmp', 'all')
        OR (port_start = 0 AND port_end = 65535)
    )
);

CREATE TABLE packet_inspections (
    inspection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    resource_id BIGINT NOT NULL
        REFERENCES network_resources(resource_id),
    source_ip INET NOT NULL,
    destination_ip INET NOT NULL,
    protocol network_protocol NOT NULL,
    source_port INTEGER NOT NULL DEFAULT 0,
    destination_port INTEGER NOT NULL DEFAULT 0,
    direction traffic_direction NOT NULL,
    decision inspection_decision NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rejection_reason TEXT,

    CHECK (family(source_ip) = 4),
    CHECK (family(destination_ip) = 4),
    CHECK (source_port BETWEEN 0 AND 65535),
    CHECK (destination_port BETWEEN 0 AND 65535),

    CHECK (
        protocol NOT IN ('icmp', 'all')
        OR (source_port = 0 AND destination_port = 0)
    ),

    CHECK (
        decision <> 'deny'
        OR rejection_reason IS NOT NULL
    )
);

CREATE TABLE inspection_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    inspection_id BIGINT NOT NULL
        REFERENCES packet_inspections(inspection_id)
        ON DELETE CASCADE,
    layer policy_layer NOT NULL,
    rule_id BIGINT,
    decision inspection_decision NOT NULL,
    explanation TEXT NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE tracked_connections (
    connection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    resource_id BIGINT NOT NULL
        REFERENCES network_resources(resource_id),
    source_ip INET NOT NULL,
    destination_ip INET NOT NULL,
    protocol network_protocol NOT NULL,
    source_port INTEGER NOT NULL,
    destination_port INTEGER NOT NULL,
    status connection_status NOT NULL DEFAULT 'established',
    established_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,

    CHECK (family(source_ip) = 4),
    CHECK (family(destination_ip) = 4),
    CHECK (source_port BETWEEN 0 AND 65535),
    CHECK (destination_port BETWEEN 0 AND 65535),
    CHECK (expires_at > established_at)
);

CREATE INDEX idx_resources_account
    ON network_resources(account_id, status);

CREATE INDEX idx_sg_rules_lookup
    ON security_group_rules(
        security_group_id,
        direction,
        enabled
    );

CREATE INDEX idx_acl_priority
    ON network_acl_rules(
        acl_id,
        direction,
        rule_number
    )
    WHERE enabled = TRUE;

CREATE INDEX idx_firewall_priority
    ON firewall_rules(
        firewall_id,
        direction,
        priority
    )
    WHERE enabled = TRUE;

CREATE INDEX idx_inspection_resource_time
    ON packet_inspections(resource_id, evaluated_at DESC);

CREATE INDEX idx_inspection_decision
    ON packet_inspections(decision, evaluated_at DESC);

CREATE INDEX idx_connection_lookup
    ON tracked_connections(
        resource_id,
        source_ip,
        destination_ip,
        protocol,
        status
    );

CREATE INDEX idx_connection_expiration
    ON tracked_connections(expires_at)
    WHERE status = 'established';


/*
 * Trigger: reject overlapping configuration errors for
 * ICMP and ALL protocols at database insertion/update time.
 */

CREATE OR REPLACE FUNCTION validate_network_rule()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.port_start > NEW.port_end THEN
        RAISE EXCEPTION 'Invalid port range';
    END IF;

    IF NEW.protocol IN ('icmp', 'all')
       AND (
           NEW.port_start <> 0
           OR NEW.port_end <> 65535
       ) THEN
        RAISE EXCEPTION
            'ICMP and ALL rules require the full port range';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_sg_rule
BEFORE INSERT OR UPDATE ON security_group_rules
FOR EACH ROW
EXECUTE FUNCTION validate_network_rule();

CREATE TRIGGER trg_validate_acl_rule
BEFORE INSERT OR UPDATE ON network_acl_rules
FOR EACH ROW
EXECUTE FUNCTION validate_network_rule();

CREATE TRIGGER trg_validate_firewall_rule
BEFORE INSERT OR UPDATE ON firewall_rules
FOR EACH ROW
EXECUTE FUNCTION validate_network_rule();


/*
 * Centralized CIDR and port matching.
 * Inbound rules compare the source address.
 * Outbound rules compare the destination address.
 */

CREATE OR REPLACE FUNCTION network_rule_matches(
    p_packet_source INET,
    p_packet_destination INET,
    p_protocol network_protocol,
    p_destination_port INTEGER,
    p_rule_direction traffic_direction,
    p_requested_direction traffic_direction,
    p_rule_protocol network_protocol,
    p_cidr CIDR,
    p_port_start INTEGER,
    p_port_end INTEGER
)
RETURNS BOOLEAN
LANGUAGE SQL
IMMUTABLE
STRICT
AS $$
    SELECT
        p_rule_direction = p_requested_direction
        AND (
            p_rule_protocol = 'all'
            OR p_rule_protocol = p_protocol
        )
        AND (
            CASE
                WHEN p_requested_direction = 'inbound'
                    THEN p_packet_source <<= p_cidr
                ELSE p_packet_destination <<= p_cidr
            END
        )
        AND (
            p_protocol IN ('icmp', 'all')
            OR p_destination_port BETWEEN
                p_port_start AND p_port_end
        );
$$;


/*
 * Security group evaluator.
 * Security groups are stateful and have allow-only rules.
 * Unmatched traffic is denied.
 */

CREATE OR REPLACE FUNCTION evaluate_security_group(
    p_group_id BIGINT,
    p_source INET,
    p_destination INET,
    p_protocol network_protocol,
    p_destination_port INTEGER,
    p_direction traffic_direction
)
RETURNS TABLE (
    decision inspection_decision,
    matched_rule_id BIGINT,
    explanation TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_rule RECORD;
BEGIN
    FOR v_rule IN
        SELECT *
        FROM security_group_rules
        WHERE security_group_id = p_group_id
          AND enabled = TRUE
        ORDER BY rule_id
    LOOP
        IF network_rule_matches(
            p_source,
            p_destination,
            p_protocol,
            p_destination_port,
            v_rule.direction,
            p_direction,
            v_rule.protocol,
            v_rule.cidr,
            v_rule.port_start,
            v_rule.port_end
        ) THEN
            RETURN QUERY SELECT
                'allow'::inspection_decision,
                v_rule.rule_id,
                'Explicit security group allow rule'::TEXT;
            RETURN;
        END IF;
    END LOOP;

    RETURN QUERY SELECT
        'deny'::inspection_decision,
        NULL::BIGINT,
        'No matching security group allow rule'::TEXT;
END;
$$;


/*
 * Network ACL evaluator.
 * First matching rule wins, ordered by rule number.
 * An unmatched packet receives an implicit deny.
 */

CREATE OR REPLACE FUNCTION evaluate_network_acl(
    p_acl_id BIGINT,
    p_source INET,
    p_destination INET,
    p_protocol network_protocol,
    p_destination_port INTEGER,
    p_direction traffic_direction
)
RETURNS TABLE (
    decision inspection_decision,
    matched_rule_id BIGINT,
    explanation TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_rule RECORD;
BEGIN
    FOR v_rule IN
        SELECT *
        FROM network_acl_rules
        WHERE acl_id = p_acl_id
          AND enabled = TRUE
        ORDER BY rule_number
    LOOP
        IF network_rule_matches(
            p_source,
            p_destination,
            p_protocol,
            p_destination_port,
            v_rule.direction,
            p_direction,
            v_rule.protocol,
            v_rule.cidr,
            v_rule.port_start,
            v_rule.port_end
        ) THEN
            RETURN QUERY SELECT
                v_rule.action::TEXT::inspection_decision,
                v_rule.rule_id,
                ('Matched ACL rule ' || v_rule.rule_number)::TEXT;
            RETURN;
        END IF;
    END LOOP;

    RETURN QUERY SELECT
        'deny'::inspection_decision,
        NULL::BIGINT,
        'Implicit ACL deny'::TEXT;
END;
$$;


/*
 * Firewall evaluator.
 * Ordered, first-match processing.
 */

CREATE OR REPLACE FUNCTION evaluate_firewall(
    p_firewall_id BIGINT,
    p_source INET,
    p_destination INET,
    p_protocol network_protocol,
    p_destination_port INTEGER,
    p_direction traffic_direction
)
RETURNS TABLE (
    decision inspection_decision,
    matched_rule_id BIGINT,
    explanation TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_rule RECORD;
BEGIN
    FOR v_rule IN
        SELECT *
        FROM firewall_rules
        WHERE firewall_id = p_firewall_id
          AND enabled = TRUE
        ORDER BY priority, rule_id
    LOOP
        IF network_rule_matches(
            p_source,
            p_destination,
            p_protocol,
            p_destination_port,
            v_rule.direction,
            p_direction,
            v_rule.protocol,
            v_rule.cidr,
            v_rule.port_start,
            v_rule.port_end
        ) THEN
            RETURN QUERY SELECT
                v_rule.action::TEXT::inspection_decision,
                v_rule.rule_id,
                ('Matched firewall priority ' || v_rule.priority)::TEXT;
            RETURN;
        END IF;
    END LOOP;

    RETURN QUERY SELECT
        'deny'::inspection_decision,
        NULL::BIGINT,
        'Firewall default deny'::TEXT;
END;
$$;


/*
 * Complete packet inspection workflow.
 *
 * The three layers are evaluated sequentially.
 * Any denial immediately terminates evaluation.
 * Audit records are written within the same transaction.
 */

CREATE OR REPLACE PROCEDURE inspect_packet(
    p_resource_id BIGINT,
    p_group_id BIGINT,
    p_acl_id BIGINT,
    p_firewall_id BIGINT,
    p_source INET,
    p_destination INET,
    p_protocol network_protocol,
    p_source_port INTEGER,
    p_destination_port INTEGER,
    p_direction traffic_direction,
    INOUT p_inspection_id BIGINT DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_result RECORD;
    v_layer policy_layer;
    v_layer_decision inspection_decision;
    v_rule_id BIGINT;
    v_explanation TEXT;
BEGIN
    IF family(p_source) <> 4 OR family(p_destination) <> 4 THEN
        RAISE EXCEPTION 'Only IPv4 packets are supported';
    END IF;

    IF p_source_port NOT BETWEEN 0 AND 65535
       OR p_destination_port NOT BETWEEN 0 AND 65535 THEN
        RAISE EXCEPTION 'Invalid packet port';
    END IF;

    IF p_protocol IN ('icmp', 'all')
       AND (p_source_port <> 0 OR p_destination_port <> 0) THEN
        RAISE EXCEPTION 'ICMP and ALL packets must use zero ports';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM network_resources
        WHERE resource_id = p_resource_id
          AND status = 'active'
    ) THEN
        RAISE EXCEPTION 'Network resource is not active';
    END IF;

    INSERT INTO packet_inspections (
        resource_id,
        source_ip,
        destination_ip,
        protocol,
        source_port,
        destination_port,
        direction,
        decision,
        rejection_reason
    )
    VALUES (
        p_resource_id,
        p_source,
        p_destination,
        p_protocol,
        p_source_port,
        p_destination_port,
        p_direction,
        'deny',
        'Inspection pending'
    )
    RETURNING inspection_id INTO p_inspection_id;

    FOR v_layer IN
        SELECT unnest(ARRAY[
            'network_acl'::policy_layer,
            'security_group'::policy_layer,
            'firewall'::policy_layer
        ])
    LOOP
        IF v_layer = 'network_acl' THEN
            SELECT * INTO v_result
            FROM evaluate_network_acl(
                p_acl_id,
                p_source,
                p_destination,
                p_protocol,
                p_destination_port,
                p_direction
            );

        ELSIF v_layer = 'security_group' THEN
            SELECT * INTO v_result
            FROM evaluate_security_group(
                p_group_id,
                p_source,
                p_destination,
                p_protocol,
                p_destination_port,
                p_direction
            );

        ELSE
            SELECT * INTO v_result
            FROM evaluate_firewall(
                p_firewall_id,
                p_source,
                p_destination,
                p_protocol,
                p_destination_port,
                p_direction
            );
        END IF;

        v_layer_decision := v_result.decision;
        v_rule_id := v_result.matched_rule_id;
        v_explanation := v_result.explanation;

        INSERT INTO inspection_audit (
            inspection_id,
            layer,
            rule_id,
            decision,
            explanation
        )
        VALUES (
            p_inspection_id,
            v_layer,
            v_rule_id,
            v_layer_decision,
            v_explanation
        );

        IF v_layer_decision = 'deny' THEN
            UPDATE packet_inspections
            SET decision = 'deny',
                rejection_reason =
                    v_layer::TEXT || ': ' || v_explanation
            WHERE inspection_id = p_inspection_id;

            RETURN;
        END IF;
    END LOOP;

    UPDATE packet_inspections
    SET decision = 'allow',
        rejection_reason = NULL
    WHERE inspection_id = p_inspection_id;
END;
$$;


/*
 * Connection cleanup.
 */

CREATE OR REPLACE PROCEDURE expire_connections()
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE tracked_connections
    SET status = 'expired'
    WHERE status = 'established'
      AND expires_at <= NOW();

    DELETE FROM tracked_connections
    WHERE status IN ('expired', 'closed')
      AND expires_at < NOW() - INTERVAL '7 days';
END;
$$;


/*
 * Reporting view: inspection decisions by resource.
 */

CREATE OR REPLACE VIEW network_security_summary AS
SELECT
    r.resource_name,
    COUNT(i.inspection_id) AS total_packets,
    COUNT(*) FILTER (
        WHERE i.decision = 'allow'
    ) AS allowed_packets,
    COUNT(*) FILTER (
        WHERE i.decision = 'deny'
    ) AS denied_packets,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE i.decision = 'deny'
        ) / NULLIF(COUNT(i.inspection_id), 0),
        2
    ) AS denied_percentage
FROM network_resources r
LEFT JOIN packet_inspections i
    ON i.resource_id = r.resource_id
GROUP BY r.resource_id, r.resource_name;


/*
 * Sample cloud account and network topology.
 */

INSERT INTO cloud_accounts (
    account_name,
    cloud_provider,
    environment
)
VALUES (
    'production-cloud',
    'AWS',
    'production'
);

INSERT INTO network_resources (
    account_id,
    resource_name,
    resource_type,
    cidr_block
)
SELECT
    account_id,
    'application-subnet',
    'subnet',
    '10.0.0.0/24'
FROM cloud_accounts
WHERE account_name = 'production-cloud';

INSERT INTO security_groups (
    resource_id,
    group_name,
    description
)
SELECT
    resource_id,
    'application-sg',
    'Production application security group'
FROM network_resources
WHERE resource_name = 'application-subnet';

INSERT INTO network_acls (
    resource_id,
    acl_name
)
SELECT
    resource_id,
    'application-acl'
FROM network_resources
WHERE resource_name = 'application-subnet';

INSERT INTO firewalls (
    account_id,
    firewall_name
)
SELECT
    account_id,
    'enterprise-edge-firewall'
FROM cloud_accounts
WHERE account_name = 'production-cloud';


/*
 * Security group rules.
 */

INSERT INTO security_group_rules (
    security_group_id,
    rule_key,
    direction,
    protocol,
    cidr,
    port_start,
    port_end,
    description
)
SELECT
    security_group_id,
    'public-https',
    'inbound',
    'tcp',
    '0.0.0.0/0',
    443,
    443,
    'HTTPS application traffic'
FROM security_groups
WHERE group_name = 'application-sg';

INSERT INTO security_group_rules (
    security_group_id,
    rule_key,
    direction,
    protocol,
    cidr,
    port_start,
    port_end,
    description
)
SELECT
    security_group_id,
    'private-database',
    'outbound',
    'tcp',
    '10.0.2.0/24',
    5432,
    5432,
    'PostgreSQL database access'
FROM security_groups
WHERE group_name = 'application-sg';

INSERT INTO security_group_rules (
    security_group_id,
    rule_key,
    direction,
    protocol,
    cidr,
    port_start,
    port_end,
    description
)
SELECT
    security_group_id,
    'administrative-ssh',
    'inbound',
    'tcp',
    '10.0.1.0/24',
    22,
    22,
    'Restricted administration'
FROM security_groups
WHERE group_name = 'application-sg';


/*
 * Stateless ACL rules.
 * Return traffic requires explicit outbound permission.
 */

INSERT INTO network_acl_rules (
    acl_id,
    rule_number,
    direction,
    action,
    protocol,
    cidr,
    port_start,
    port_end,
    description
)
SELECT
    acl_id,
    100,
    'inbound',
    'allow',
    'tcp',
    '0.0.0.0/0',
    443,
    443,
    'HTTPS inbound'
FROM network_acls
WHERE acl_name = 'application-acl';

INSERT INTO network_acl_rules (
    acl_id,
    rule_number,
    direction,
    action,
    protocol,
    cidr,
    port_start,
    port_end,
    description
)
SELECT
    acl_id,
    110,
    'inbound',
    'allow',
    'tcp',
    '10.0.1.0/24',
    22,
    22,
    'Administrative access'
FROM network_acls
WHERE acl_name = 'application-acl';

INSERT INTO network_acl_rules (
    acl_id,
    rule_number,
    direction,
    action,
    protocol,
    cidr,
    port_start,
    port_end,
    description
)
SELECT
    acl_id,
    100,
    'outbound',
    'allow',
    'tcp',
    '0.0.0.0/0',
    0,
    65535,
    'Explicit TCP response and outbound traffic'
FROM network_acls
WHERE acl_name = 'application-acl';


/*
 * Ordered firewall rules.
 */

INSERT INTO firewall_rules (
    firewall_id,
    rule_key,
    priority,
    direction,
    action,
    protocol,
    cidr,
    port_start,
    port_end,
    description
)
SELECT
    firewall_id,
    'deny-hostile-network',
    10,
    'inbound',
    'deny',
    'all',
    '198.51.100.0/24',
    0,
    65535,
    'Block designated hostile network range'
FROM firewalls
WHERE firewall_name = 'enterprise-edge-firewall';

INSERT INTO firewall_rules (
    firewall_id,
    rule_key,
    priority,
    direction,
    action,
    protocol,
    cidr,
    port_start,
    port_end,
    description
)
SELECT
    firewall_id,
    'allow-https',
    100,
    'inbound',
    'allow',
    'tcp',
    '0.0.0.0/0',
    443,
    443,
    'Public HTTPS access'
FROM firewalls
WHERE firewall_name = 'enterprise-edge-firewall';

INSERT INTO firewall_rules (
    firewall_id,
    rule_key,
    priority,
    direction,
    action,
    protocol,
    cidr,
    port_start,
    port_end,
    description
)
SELECT
    firewall_id,
    'allow-admin',
    110,
    'inbound',
    'allow',
    'tcp',
    '10.0.1.0/24',
    22,
    22,
    'Administrative SSH'
FROM firewalls
WHERE firewall_name = 'enterprise-edge-firewall';

INSERT INTO firewall_rules (
    firewall_id,
    rule_key,
    priority,
    direction,
    action,
    protocol,
    cidr,
    port_start,
    port_end,
    description
)
SELECT
    firewall_id,
    'outbound-traffic',
    100,
    'outbound',
    'allow',
    'all',
    '0.0.0.0/0',
    0,
    65535,
    'Outbound firewall policy'
FROM firewalls
WHERE firewall_name = 'enterprise-edge-firewall';


/*
 * Packet inspection scenarios.
 *
 * Scenario 1: permitted public HTTPS.
 * Scenario 2: blocked hostile source.
 * Scenario 3: unauthorized SSH.
 */

DO $$
DECLARE
    v_resource BIGINT;
    v_group BIGINT;
    v_acl BIGINT;
    v_firewall BIGINT;
    v_id BIGINT;
BEGIN
    SELECT resource_id INTO STRICT v_resource
    FROM network_resources
    WHERE resource_name = 'application-subnet';

    SELECT security_group_id INTO STRICT v_group
    FROM security_groups
    WHERE group_name = 'application-sg';

    SELECT acl_id INTO STRICT v_acl
    FROM network_acls
    WHERE acl_name = 'application-acl';

    SELECT firewall_id INTO STRICT v_firewall
    FROM firewalls
    WHERE firewall_name = 'enterprise-edge-firewall';

    CALL inspect_packet(
        v_resource,
        v_group,
        v_acl,
        v_firewall,
        '203.0.113.10',
        '10.0.0.10',
        'tcp',
        51000,
        443,
        'inbound',
        v_id
    );

    RAISE NOTICE 'HTTPS inspection ID: %', v_id;

    CALL inspect_packet(
        v_resource,
        v_group,
        v_acl,
        v_firewall,
        '198.51.100.20',
        '10.0.0.10',
        'tcp',
        51000,
        443,
        'inbound',
        v_id
    );

    RAISE NOTICE 'Hostile traffic inspection ID: %', v_id;

    CALL inspect_packet(
        v_resource,
        v_group,
        v_acl,
        v_firewall,
        '203.0.113.20',
        '10.0.0.10',
        'tcp',
        51000,
        22,
        'inbound',
        v_id
    );

    RAISE NOTICE 'Unauthorized SSH inspection ID: %', v_id;
END;
$$;


/*
 * Query 1: retrieve packet inspection history.
 */

SELECT
    inspection_id,
    source_ip,
    destination_ip,
    protocol,
    destination_port,
    direction,
    decision,
    rejection_reason,
    evaluated_at
FROM packet_inspections
ORDER BY evaluated_at DESC;


/*
 * Query 2: inspect every policy decision for a packet.
 */

SELECT
    i.inspection_id,
    a.layer,
    a.decision,
    a.rule_id,
    a.explanation
FROM packet_inspections i
JOIN inspection_audit a
    ON a.inspection_id = i.inspection_id
ORDER BY i.inspection_id, a.audit_id;


/*
 * Query 3: aggregate traffic security metrics.
 */

SELECT *
FROM network_security_summary
ORDER BY denied_percentage DESC NULLS LAST;


/*
 * Query 4: identify overly broad public ingress rules.
 */

SELECT
    sg.group_name,
    r.rule_key,
    r.protocol,
    r.cidr,
    r.port_start,
    r.port_end
FROM security_group_rules r
JOIN security_groups sg
    ON sg.security_group_id = r.security_group_id
WHERE r.enabled = TRUE
  AND r.direction = 'inbound'
  AND r.cidr = '0.0.0.0/0'
ORDER BY sg.group_name, r.rule_key;


/*
 * Query 5: identify rules that expose administrative ports
 * to all IPv4 addresses.
 */

SELECT
    'security_group' AS layer,
    rule_key AS rule_name,
    cidr,
    port_start,
    port_end
FROM security_group_rules
WHERE enabled = TRUE
  AND direction = 'inbound'
  AND cidr = '0.0.0.0/0'
  AND port_start <= 22
  AND port_end >= 22

UNION ALL

SELECT
    'firewall',
    rule_key,
    cidr,
    port_start,
    port_end
FROM firewall_rules
WHERE enabled = TRUE
  AND direction = 'inbound'
  AND action = 'allow'
  AND cidr = '0.0.0.0/0'
  AND port_start <= 22
  AND port_end >= 22;


/*
 * Query 6: verify connection-tracking expiration.
 */

CALL expire_connections();

SELECT
    connection_id,
    source_ip,
    destination_ip,
    protocol,
    status,
    established_at,
    expires_at
FROM tracked_connections
ORDER BY expires_at;


/*
 * Query 7: rule counts by policy layer.
 */

SELECT
    'security_group' AS layer,
    COUNT(*) AS total_rules,
    COUNT(*) FILTER (WHERE enabled) AS enabled_rules
FROM security_group_rules

UNION ALL

SELECT
    'network_acl',
    COUNT(*),
    COUNT(*) FILTER (WHERE enabled)
FROM network_acl_rules

UNION ALL

SELECT
    'firewall',
    COUNT(*),
    COUNT(*) FILTER (WHERE enabled)
FROM firewall_rules;


/*
 * Query 8: CTE for repeated source-IP denial analysis.
 */

WITH denied_sources AS (
    SELECT
        source_ip,
        COUNT(*) AS denial_count,
        MAX(evaluated_at) AS last_denial
    FROM packet_inspections
    WHERE decision = 'deny'
    GROUP BY source_ip
)
SELECT
    source_ip,
    denial_count,
    last_denial,
    CASE
        WHEN denial_count >= 10 THEN 'HIGH'
        WHEN denial_count >= 5 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS investigation_priority
FROM denied_sources
ORDER BY denial_count DESC, last_denial DESC;


/*
 * Transaction example: disable an unsafe rule atomically.
 * The transaction is rolled back to preserve demonstration data.
 */

SAVEPOINT before_policy_change;

UPDATE security_group_rules
SET enabled = FALSE
WHERE rule_key = 'public-https'
  AND security_group_id IN (
      SELECT security_group_id
      FROM security_groups
      WHERE group_name = 'application-sg'
  );

SELECT rule_key, enabled
FROM security_group_rules
WHERE rule_key = 'public-https';

ROLLBACK TO SAVEPOINT before_policy_change;

COMMIT;
