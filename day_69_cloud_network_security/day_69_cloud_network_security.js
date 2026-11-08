'use strict';

/*
 * Cloud Network Security Policy Engine
 *
 * Features:
 * - Stateful security groups
 * - Stateless network ACLs
 * - Ordered firewall evaluation
 * - CIDR matching for IPv4
 * - Connection tracking with expiration
 * - Event-driven policy changes
 * - Asynchronous packet inspection
 * - Rule validation and security auditing
 *
 * Runtime: Node.js 18+
 * Dependencies: None
 */

const net = require('node:net');
const fs = require('node:fs/promises');
const { EventEmitter } = require('node:events');

const Direction = Object.freeze({
    INBOUND: 'inbound',
    OUTBOUND: 'outbound'
});

const Action = Object.freeze({
    ALLOW: 'allow',
    DENY: 'deny'
});

const Protocol = Object.freeze({
    TCP: 'tcp',
    UDP: 'udp',
    ICMP: 'icmp',
    ALL: 'all'
});

class PolicyError extends Error {
    constructor(message) {
        super(message);
        this.name = 'PolicyError';
    }
}

function validateIPv4(address) {
    if (net.isIP(address) !== 4) {
        throw new PolicyError(`Invalid IPv4 address: ${address}`);
    }

    return address.split('.').reduce(
        (value, octet) => ((value << 8) | Number(octet)) >>> 0,
        0
    );
}

function parseCIDR(cidr) {
    const parts = cidr.split('/');

    if (parts.length !== 2) {
        throw new PolicyError(`Invalid CIDR: ${cidr}`);
    }

    const address = validateIPv4(parts[0]);
    const prefix = Number(parts[1]);

    if (!Number.isInteger(prefix) || prefix < 0 || prefix > 32) {
        throw new PolicyError(`Invalid CIDR prefix: ${cidr}`);
    }

    const mask = prefix === 0
        ? 0
        : (0xFFFFFFFF << (32 - prefix)) >>> 0;

    return {
        network: (address & mask) >>> 0,
        mask
    };
}

function matchesCIDR(address, cidr) {
    const ip = validateIPv4(address);
    const { network, mask } = parseCIDR(cidr);

    return ((ip & mask) >>> 0) === network;
}

function validatePacket(packet) {
    validateIPv4(packet.sourceIP);
    validateIPv4(packet.destinationIP);

    if (!Object.values(Protocol).includes(packet.protocol)) {
        throw new PolicyError('Unsupported protocol');
    }

    for (const field of ['sourcePort', 'destinationPort']) {
        if (
            !Number.isInteger(packet[field]) ||
            packet[field] < 0 ||
            packet[field] > 65535
        ) {
            throw new PolicyError(`Invalid ${field}`);
        }
    }

    if (
        [Protocol.ICMP, Protocol.ALL].includes(packet.protocol) &&
        (packet.sourcePort !== 0 || packet.destinationPort !== 0)
    ) {
        throw new PolicyError('ICMP and ALL packets must use zero ports');
    }
}

class Rule {
    constructor({
        id,
        direction,
        action,
        protocol,
        cidr,
        portStart = 0,
        portEnd = 65535,
        priority = 100,
        description = ''
    }) {
        if (!id || typeof id !== 'string') {
            throw new PolicyError('Rule ID is required');
        }

        if (!Object.values(Direction).includes(direction)) {
            throw new PolicyError('Invalid direction');
        }

        if (!Object.values(Action).includes(action)) {
            throw new PolicyError('Invalid action');
        }

        if (!Object.values(Protocol).includes(protocol)) {
            throw new PolicyError('Invalid protocol');
        }

        parseCIDR(cidr);

        if (
            !Number.isInteger(portStart) ||
            !Number.isInteger(portEnd) ||
            portStart < 0 ||
            portEnd > 65535 ||
            portStart > portEnd
        ) {
            throw new PolicyError('Invalid port range');
        }

        if (!Number.isInteger(priority) || priority < 0) {
            throw new PolicyError('Invalid priority');
        }

        if (
            [Protocol.ICMP, Protocol.ALL].includes(protocol) &&
            (portStart !== 0 || portEnd !== 65535)
        ) {
            throw new PolicyError(
                'ICMP and ALL rules must use the full port range'
            );
        }

        Object.assign(this, {
            id,
            direction,
            action,
            protocol,
            cidr,
            portStart,
            portEnd,
            priority,
            description
        });

        Object.freeze(this);
    }

    matches(packet, direction) {
        if (this.direction !== direction) return false;

        const address = direction === Direction.INBOUND
            ? packet.sourceIP
            : packet.destinationIP;

        if (!matchesCIDR(address, this.cidr)) return false;

        if (
            this.protocol !== Protocol.ALL &&
            this.protocol !== packet.protocol
        ) {
            return false;
        }

        if ([Protocol.ICMP, Protocol.ALL].includes(packet.protocol)) {
            return true;
        }

        return (
            packet.destinationPort >= this.portStart &&
            packet.destinationPort <= this.portEnd
        );
    }
}

class ConnectionTracker {
    constructor(ttlMilliseconds = 300000) {
        if (!Number.isFinite(ttlMilliseconds) || ttlMilliseconds <= 0) {
            throw new PolicyError('Invalid connection TTL');
        }

        this.ttl = ttlMilliseconds;
        this.connections = new Map();
    }

    key(packet) {
        return [
            packet.sourceIP,
            packet.destinationIP,
            packet.protocol,
            packet.sourcePort,
            packet.destinationPort
        ].join('|');
    }

    reverseKey(packet) {
        return [
            packet.destinationIP,
            packet.sourceIP,
            packet.protocol,
            packet.destinationPort,
            packet.sourcePort
        ].join('|');
    }

    contains(packet) {
        const now = Date.now();
        const keys = [this.key(packet), this.reverseKey(packet)];

        for (const key of keys) {
            const expiry = this.connections.get(key);

            if (expiry && expiry > now) return true;

            if (expiry) this.connections.delete(key);
        }

        return false;
    }

    add(packet) {
        this.connections.set(
            this.key(packet),
            Date.now() + this.ttl
        );
    }

    cleanup() {
        const now = Date.now();

        for (const [key, expiry] of this.connections) {
            if (expiry <= now) this.connections.delete(key);
        }
    }
}

class PolicyLayer extends EventEmitter {
    constructor(name) {
        super();
        this.name = name;
        this.rules = new Map();
    }

    addRule(rule) {
        if (this.rules.has(rule.id)) {
            throw new PolicyError(`Duplicate rule ID: ${rule.id}`);
        }

        this.rules.set(rule.id, rule);
        this.emit('ruleAdded', {
            layer: this.name,
            ruleId: rule.id
        });
    }

    orderedRules() {
        return [...this.rules.values()].sort(
            (a, b) => a.priority - b.priority
        );
    }

    inspectRules(packet, direction) {
        for (const rule of this.orderedRules()) {
            if (rule.matches(packet, direction)) {
                return {
                    allowed: rule.action === Action.ALLOW,
                    layer: this.name,
                    ruleId: rule.id,
                    reason: `Matched rule ${rule.id}`
                };
            }
        }

        return {
            allowed: false,
            layer: this.name,
            ruleId: null,
            reason: 'Default deny'
        };
    }
}

class SecurityGroup extends PolicyLayer {
    constructor(name) {
        super(name);
        this.connections = new ConnectionTracker();
    }

    addRule(rule) {
        if (rule.action !== Action.ALLOW) {
            throw new PolicyError(
                'Security groups support ALLOW rules only'
            );
        }

        super.addRule(rule);
    }

    inspect(packet, direction) {
        if (this.connections.contains(packet)) {
            return {
                allowed: true,
                layer: this.name,
                reason: 'Established connection'
            };
        }

        const result = this.inspectRules(packet, direction);

        if (
            result.allowed &&
            direction === Direction.OUTBOUND
        ) {
            this.connections.add(packet);
        }

        return result;
    }
}

class NetworkACL extends PolicyLayer {
    inspect(packet, direction) {
        // ACL rules are stateless: reverse traffic is evaluated separately.
        return this.inspectRules(packet, direction);
    }
}

class Firewall extends PolicyLayer {
    constructor(name) {
        super(name);
        this.connections = new ConnectionTracker();
    }

    inspect(packet, direction) {
        if (this.connections.contains(packet)) {
            return {
                allowed: true,
                layer: this.name,
                reason: 'Established firewall connection'
            };
        }

        const result = this.inspectRules(packet, direction);

        if (
            result.allowed &&
            direction === Direction.INBOUND
        ) {
            this.connections.add(packet);
        }

        return result;
    }
}

class CloudNetworkEngine extends EventEmitter {
    constructor({ securityGroup, networkACL, firewall }) {
        super();

        this.layers = [
            networkACL,
            securityGroup,
            firewall
        ];
    }

    async inspect(packet, direction) {
        validatePacket(packet);

        if (!Object.values(Direction).includes(direction)) {
            throw new PolicyError('Invalid packet direction');
        }

        const auditTrail = [];

        // Sequential inspection preserves security-layer ordering.
        for (const layer of this.layers) {
            const result = await Promise.resolve(
                layer.inspect(packet, direction)
            );

            auditTrail.push(result);

            this.emit('inspection', result);

            if (!result.allowed) {
                const denied = {
                    decision: 'DENY',
                    failedLayer: layer.name,
                    auditTrail
                };

                this.emit('denied', denied);
                return denied;
            }
        }

        const accepted = {
            decision: 'ALLOW',
            failedLayer: null,
            auditTrail
        };

        this.emit('allowed', accepted);
        return accepted;
    }

    audit() {
        return this.layers.map(layer => ({
            name: layer.name,
            ruleCount: layer.rules.size,
            rules: layer.orderedRules().map(rule => ({
                id: rule.id,
                direction: rule.direction,
                action: rule.action,
                protocol: rule.protocol,
                cidr: rule.cidr,
                ports: `${rule.portStart}-${rule.portEnd}`,
                priority: rule.priority
            }))
        }));
    }

    async exportPolicy(filename) {
        const content = JSON.stringify(this.audit(), null, 2);
        await fs.writeFile(filename, content, {
            encoding: 'utf8',
            mode: 0o600
        });
    }
}

function createDemo() {
    const sg = new SecurityGroup('application-sg');
    const acl = new NetworkACL('application-acl');
    const firewall = new Firewall('edge-firewall');

    sg.addRule(new Rule({
        id: 'sg-https',
        direction: Direction.INBOUND,
        action: Action.ALLOW,
        protocol: Protocol.TCP,
        cidr: '0.0.0.0/0',
        portStart: 443,
        portEnd: 443
    }));

    sg.addRule(new Rule({
        id: 'sg-database',
        direction: Direction.OUTBOUND,
        action: Action.ALLOW,
        protocol: Protocol.TCP,
        cidr: '10.0.2.0/24',
        portStart: 5432,
        portEnd: 5432
    }));

    acl.addRule(new Rule({
        id: 'acl-https',
        direction: Direction.INBOUND,
        action: Action.ALLOW,
        protocol: Protocol.TCP,
        cidr: '0.0.0.0/0',
        portStart: 443,
        portEnd: 443,
        priority: 100
    }));

    acl.addRule(new Rule({
        id: 'acl-return',
        direction: Direction.OUTBOUND,
        action: Action.ALLOW,
        protocol: Protocol.TCP,
        cidr: '0.0.0.0/0',
        priority: 100
    }));

    firewall.addRule(new Rule({
        id: 'fw-block',
        direction: Direction.INBOUND,
        action: Action.DENY,
        protocol: Protocol.ALL,
        cidr: '198.51.100.0/24',
        priority: 10
    }));

    firewall.addRule(new Rule({
        id: 'fw-https',
        direction: Direction.INBOUND,
        action: Action.ALLOW,
        protocol: Protocol.TCP,
        cidr: '0.0.0.0/0',
        portStart: 443,
        portEnd: 443,
        priority: 100
    }));

    firewall.addRule(new Rule({
        id: 'fw-outbound',
        direction: Direction.OUTBOUND,
        action: Action.ALLOW,
        protocol: Protocol.ALL,
        cidr: '0.0.0.0/0'
    }));

    return new CloudNetworkEngine({
        securityGroup: sg,
        networkACL: acl,
        firewall
    });
}

async function main() {
    const engine = createDemo();

    engine.on('denied', event => {
        console.log(
            `BLOCKED at ${event.failedLayer}`
        );
    });

    engine.on('allowed', () => {
        console.log('Traffic passed all security layers.');
    });

    const packets = [
        {
            name: 'Public HTTPS',
            direction: Direction.INBOUND,
            packet: {
                sourceIP: '203.0.113.10',
                destinationIP: '10.0.0.10',
                protocol: Protocol.TCP,
                sourcePort: 51000,
                destinationPort: 443
            },
            expected: 'ALLOW'
        },
        {
            name: 'Malicious source',
            direction: Direction.INBOUND,
            packet: {
                sourceIP: '198.51.100.20',
                destinationIP: '10.0.0.10',
                protocol: Protocol.TCP,
                sourcePort: 51000,
                destinationPort: 443
            },
            expected: 'DENY'
        }
    ];

    for (const test of packets) {
        const result = await engine.inspect(
            test.packet,
            test.direction
        );

        console.log(
            `${test.name}: ${result.decision}`
        );

        if (result.decision !== test.expected) {
            throw new Error(`Failed test: ${test.name}`);
        }
    }

    console.log('\nPolicy audit:');
    console.log(JSON.stringify(engine.audit(), null, 2));

    await engine.exportPolicy('cloud-network-policy.json');
    console.log('\nPolicy exported successfully.');
}

main().catch(error => {
    console.error('Security engine failure:', error.message);
    process.exitCode = 1;
});
