"use strict";

/*
 * Cloud load-balancing model.
 *
 * Application load balancing is modeled as Layer-7 request routing.
 * Network load balancing is modeled as Layer-4 flow distribution.
 * Target groups own targets and health-check configuration.
 */

const LoadBalancerType = Object.freeze({
    APPLICATION: "application",
    NETWORK: "network"
});

const TargetState = Object.freeze({
    HEALTHY: "healthy",
    UNHEALTHY: "unhealthy",
    DRAINING: "draining"
});

const Protocol = Object.freeze({
    HTTP: "HTTP",
    HTTPS: "HTTPS",
    TCP: "TCP",
    TLS: "TLS"
});

class ValidationError extends Error {}

class HealthCheck {
    constructor({
        protocol,
        port,
        path = null,
        intervalSeconds = 10,
        timeoutSeconds = 3,
        healthyThreshold = 2,
        unhealthyThreshold = 3
    }) {
        this.protocol = protocol;
        this.port = port;
        this.path = path;
        this.intervalSeconds = intervalSeconds;
        this.timeoutSeconds = timeoutSeconds;
        this.healthyThreshold = healthyThreshold;
        this.unhealthyThreshold = unhealthyThreshold;
        this.validate();
    }

    validate() {
        if (!Number.isInteger(this.port) || this.port < 1 || this.port > 65535) {
            throw new ValidationError("Health-check port is invalid.");
        }

        if ([Protocol.HTTP, Protocol.HTTPS].includes(this.protocol) && !this.path) {
            throw new ValidationError("HTTP health checks require a path.");
        }

        if (this.intervalSeconds <= 0 || this.timeoutSeconds <= 0) {
            throw new ValidationError("Health-check timings must be positive.");
        }

        if (this.timeoutSeconds >= this.intervalSeconds) {
            throw new ValidationError("Health-check timeout must be shorter than interval.");
        }

        if (this.healthyThreshold <= 0 || this.unhealthyThreshold <= 0) {
            throw new ValidationError("Health thresholds must be positive.");
        }
    }
}

class Target {
    constructor({ id, address, port, state = TargetState.HEALTHY, zone }) {
        this.id = id;
        this.address = address;
        this.port = port;
        this.state = state;
        this.zone = zone;
        this.activeConnections = 0;
        this.validate();
    }

    validate() {
        if (!this.id || !this.address) {
            throw new ValidationError("Target ID and address are required.");
        }

        if (!Number.isInteger(this.port) || this.port < 1 || this.port > 65535) {
            throw new ValidationError(`Invalid port for target ${this.id}.`);
        }
    }

    canReceiveTraffic() {
        return this.state === TargetState.HEALTHY;
    }
}

class TargetGroup {
    constructor({ name, protocol, port, healthCheck }) {
        this.name = name;
        this.protocol = protocol;
        this.port = port;
        this.healthCheck = healthCheck;
        this.targets = new Map();

        if (!name || !healthCheck) {
            throw new ValidationError("Target group requires a name and health check.");
        }
    }

    addTarget(target) {
        if (this.targets.has(target.id)) {
            throw new ValidationError(`Duplicate target: ${target.id}`);
        }

        if (target.port !== this.port) {
            throw new ValidationError(
                `Target ${target.id} does not match target-group port ${this.port}.`
            );
        }

        this.targets.set(target.id, target);
    }

    healthyTargets() {
        return [...this.targets.values()].filter(target => target.canReceiveTraffic());
    }

    setState(targetId, state) {
        const target = this.targets.get(targetId);
        if (!target) {
            throw new ValidationError(`Unknown target: ${targetId}`);
        }
        target.state = state;
    }
}

class LoadBalancer {
    constructor(name, type) {
        this.name = name;
        this.type = type;
        this.targetGroups = new Map();
        this.listeners = new Map();
        this.roundRobinCounters = new Map();
    }

    addTargetGroup(group) {
        if (this.targetGroups.has(group.name)) {
            throw new ValidationError(`Duplicate target group: ${group.name}`);
        }
        this.targetGroups.set(group.name, group);
    }

    addListener(protocol, port, targetGroupName) {
        const key = `${protocol}:${port}`;

        if (this.listeners.has(key)) {
            throw new ValidationError(`Listener already exists: ${key}`);
        }

        if (!this.targetGroups.has(targetGroupName)) {
            throw new ValidationError(`Unknown target group: ${targetGroupName}`);
        }

        this.listeners.set(key, {
            protocol,
            port,
            targetGroupName
        });
    }

    route(request) {
        const key = `${request.protocol}:${request.port}`;
        const listener = this.listeners.get(key);

        if (!listener) {
            throw new Error(`No listener configured for ${key}`);
        }

        const group = this.targetGroups.get(listener.targetGroupName);
        const healthy = group.healthyTargets();

        if (healthy.length === 0) {
            throw new Error("No healthy targets are available.");
        }

        let selected;

        if (this.type === LoadBalancerType.APPLICATION) {
            if (![Protocol.HTTP, Protocol.HTTPS].includes(request.protocol)) {
                throw new Error("Application load balancers require HTTP or HTTPS.");
            }

            selected = this.selectRoundRobin(group, healthy);
        } else {
            if (![Protocol.TCP, Protocol.TLS].includes(request.protocol)) {
                throw new Error("Network load balancers require TCP or TLS.");
            }

            selected = this.selectFlowTarget(request, healthy);
        }

        selected.activeConnections += 1;

        return {
            requestId: request.id,
            targetId: selected.id,
            targetAddress: selected.address,
            targetPort: selected.port
        };
    }

    selectRoundRobin(group, healthyTargets) {
        const current = this.roundRobinCounters.get(group.name) || 0;
        const selected = healthyTargets[current % healthyTargets.length];
        this.roundRobinCounters.set(group.name, current + 1);
        return selected;
    }

    selectFlowTarget(request, healthyTargets) {
        const flow = [
            request.sourceIp || "",
            request.protocol,
            request.sourcePort || "",
            request.port
        ].join("|");

        let hash = 0;
        for (let index = 0; index < flow.length; index++) {
            hash = ((hash << 5) - hash) + flow.charCodeAt(index);
            hash |= 0;
        }

        const bucket = Math.abs(hash) % healthyTargets.length;
        return healthyTargets[bucket];
    }

    closeConnection(targetId) {
        for (const group of this.targetGroups.values()) {
            const target = group.targets.get(targetId);

            if (target) {
                if (target.activeConnections <= 0) {
                    throw new Error(`No active connections for ${targetId}.`);
                }
                target.activeConnections -= 1;
                return;
            }
        }

        throw new Error(`Unknown target: ${targetId}`);
    }

    async runHealthCheck(groupName, targetId, probe) {
        const group = this.targetGroups.get(groupName);
        if (!group) {
            throw new Error(`Unknown target group: ${groupName}`);
        }

        const target = group.targets.get(targetId);
        if (!target) {
            throw new Error(`Unknown target: ${targetId}`);
        }

        // The probe is deliberately injected so production code can use
        // an HTTP/TCP client while this model remains dependency-free.
        const result = await Promise.resolve(probe(target, group.healthCheck));

        target.state = result
            ? TargetState.HEALTHY
            : TargetState.UNHEALTHY;

        return target.state;
    }

    report() {
        return Object.fromEntries(
            [...this.targetGroups.entries()].map(([name, group]) => [
                name,
                Object.fromEntries(
                    [...group.targets.values()].map(target => [
                        target.id,
                        {
                            state: target.state,
                            connections: target.activeConnections,
                            zone: target.zone
                        }
                    ])
                )
            ])
        );
    }
}

function createApplicationLoadBalancer() {
    const alb = new LoadBalancer("orders-alb", LoadBalancerType.APPLICATION);

    const healthCheck = new HealthCheck({
        protocol: Protocol.HTTP,
        port: 8080,
        path: "/health"
    });

    const group = new TargetGroup({
        name: "orders-web",
        protocol: Protocol.HTTP,
        port: 8080,
        healthCheck
    });

    group.addTarget(new Target({
        id: "orders-a",
        address: "10.1.1.10",
        port: 8080,
        zone: "zone-a"
    }));

    group.addTarget(new Target({
        id: "orders-b",
        address: "10.1.2.10",
        port: 8080,
        zone: "zone-b"
    }));

    group.addTarget(new Target({
        id: "orders-c",
        address: "10.1.3.10",
        port: 8080,
        zone: "zone-c"
    }));

    alb.addTargetGroup(group);
    alb.addListener(Protocol.HTTP, 80, "orders-web");

    return alb;
}

function createNetworkLoadBalancer() {
    const nlb = new LoadBalancer("payments-nlb", LoadBalancerType.NETWORK);

    const healthCheck = new HealthCheck({
        protocol: Protocol.TCP,
        port: 9000
    });

    const group = new TargetGroup({
        name: "payment-tcp",
        protocol: Protocol.TCP,
        port: 9000,
        healthCheck
    });

    group.addTarget(new Target({
        id: "payment-a",
        address: "10.2.1.10",
        port: 9000,
        zone: "zone-a"
    }));

    group.addTarget(new Target({
        id: "payment-b",
        address: "10.2.2.10",
        port: 9000,
        zone: "zone-b"
    }));

    nlb.addTargetGroup(group);
    nlb.addListener(Protocol.TCP, 443, "payment-tcp");

    return nlb;
}

async function main() {
    const alb = createApplicationLoadBalancer();

    console.log("=== Application load balancing ===");

    for (const request of [
        {
            id: "web-001",
            protocol: Protocol.HTTP,
            port: 80,
            host: "orders.example.com",
            path: "/orders"
        },
        {
            id: "web-002",
            protocol: Protocol.HTTP,
            port: 80,
            host: "orders.example.com",
            path: "/customers"
        },
        {
            id: "web-003",
            protocol: Protocol.HTTP,
            port: 80,
            host: "orders.example.com",
            path: "/orders/42"
        }
    ]) {
        console.log(alb.route(request));
    }

    await alb.runHealthCheck(
        "orders-web",
        "orders-b",
        async () => false
    );

    console.log("After failed health check:");
    console.log(JSON.stringify(alb.report(), null, 2));

    const nlb = createNetworkLoadBalancer();

    console.log("\n=== Network load balancing ===");

    for (const request of [
        {
            id: "tcp-001",
            protocol: Protocol.TCP,
            port: 443,
            sourceIp: "198.51.100.10",
            sourcePort: 50001
        },
        {
            id: "tcp-002",
            protocol: Protocol.TCP,
            port: 443,
            sourceIp: "198.51.100.11",
            sourcePort: 50002
        },
        {
            id: "tcp-003",
            protocol: Protocol.TCP,
            port: 443,
            sourceIp: "198.51.100.10",
            sourcePort: 50001
        }
    ]) {
        console.log(nlb.route(request));
    }

    nlb.targetGroups.get("payment-tcp").setState(
        "payment-a",
        TargetState.DRAINING
    );

    console.log("After target draining:");
    console.log(JSON.stringify(nlb.report(), null, 2));

    // Security validation: unhealthy and draining targets must not receive new traffic.
    try {
        alb.targetGroups.get("orders-web").setState(
            "orders-a",
            TargetState.UNHEALTHY
        );

        const result = alb.route({
            id: "web-004",
            protocol: Protocol.HTTP,
            port: 80,
            host: "orders.example.com",
            path: "/orders"
        });

        if (result.targetId === "orders-a") {
            throw new Error("Unsafe routing to unhealthy target.");
        }
    } catch (error) {
        console.error("Validation failure:", error.message);
    }
}

main().catch(error => {
    console.error("Fatal error:", error.message);
    process.exitCode = 1;
});
