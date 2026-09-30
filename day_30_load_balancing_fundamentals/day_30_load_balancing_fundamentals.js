"use strict";

/*
 * Load Balancing Fundamentals
 *
 * This Node.js program models a load-balancing control plane. It deliberately
 * uses JavaScript-specific mechanisms such as classes, Maps, Sets, async
 * health checks, Promises, event-driven state changes, and HTTP-aware routing.
 *
 * It is a local simulation rather than a production network proxy.
 */

const { EventEmitter } = require("node:events");

const Protocol = Object.freeze({
    TCP: "TCP",
    HTTP: "HTTP",
});

const BackendState = Object.freeze({
    HEALTHY: "healthy",
    UNHEALTHY: "unhealthy",
    DRAINING: "draining",
});

class Backend {
    constructor({
        id,
        host,
        port = 8080,
        weight = 1,
        latencyMs = 20,
        maxConnections = 100,
        role = "application",
    }) {
        if (!id || !host) {
            throw new Error("Backend id and host are required");
        }

        this.id = id;
        this.host = host;
        this.port = port;
        this.weight = weight;
        this.latencyMs = latencyMs;
        this.maxConnections = maxConnections;
        this.role = role;

        this.state = BackendState.HEALTHY;
        this.activeConnections = 0;
        this.totalRequests = 0;
        this.failedRequests = 0;

        this.health = {
            enabled: true,
            endpointAvailable: true,
            consecutiveFailures: 0,
            consecutiveSuccesses: 0,
        };

        this.applicationHealthy = true;
    }

    canAccept() {
        return (
            this.state === BackendState.HEALTHY &&
            this.activeConnections < this.maxConnections
        );
    }

    openConnection() {
        if (!this.canAccept()) {
            return false;
        }

        this.activeConnections += 1;
        this.totalRequests += 1;
        return true;
    }

    closeConnection(success = true) {
        this.activeConnections = Math.max(0, this.activeConnections - 1);

        if (!success) {
            this.failedRequests += 1;
        }
    }
}

class RoundRobin {
    constructor() {
        this.cursor = 0;
    }

    select(backends) {
        const eligible = backends.filter((backend) => backend.canAccept());

        if (eligible.length === 0) {
            return null;
        }

        const backend = eligible[this.cursor % eligible.length];
        this.cursor = (this.cursor + 1) % eligible.length;
        return backend;
    }
}

class WeightedRoundRobin {
    constructor() {
        this.cursor = 0;
    }

    select(backends) {
        const eligible = backends.filter(
            (backend) => backend.canAccept() && backend.weight > 0
        );

        if (eligible.length === 0) {
            return null;
        }

        const weightedPool = [];

        for (const backend of eligible) {
            for (let i = 0; i < backend.weight; i += 1) {
                weightedPool.push(backend);
            }
        }

        const backend = weightedPool[this.cursor % weightedPool.length];
        this.cursor = (this.cursor + 1) % weightedPool.length;
        return backend;
    }
}

class LeastConnections {
    select(backends) {
        const eligible = backends.filter((backend) => backend.canAccept());

        if (eligible.length === 0) {
            return null;
        }

        return eligible.reduce((best, current) => {
            if (current.activeConnections < best.activeConnections) {
                return current;
            }

            if (
                current.activeConnections === best.activeConnections &&
                current.weight > best.weight
            ) {
                return current;
            }

            return best;
        });
    }
}

class IpHash {
    /*
     * A stable integer hash creates deterministic client affinity.
     * Real implementations use carefully designed hashing and often account
     * for backend membership changes with consistent-hashing techniques.
     */
    hash(value) {
        let hash = 2166136261;

        for (const character of value) {
            hash ^= character.charCodeAt(0);
            hash = Math.imul(hash, 16777619);
        }

        return hash >>> 0;
    }

    select(backends, clientIp) {
        const eligible = backends.filter((backend) => backend.canAccept());

        if (eligible.length === 0) {
            return null;
        }

        return eligible[this.hash(clientIp) % eligible.length];
    }
}

class StickySessions {
    constructor(fallback) {
        this.fallback = fallback;
        this.sessions = new Map();
    }

    select(backends, sessionId) {
        const eligible = new Map(
            backends
                .filter((backend) => backend.canAccept())
                .map((backend) => [backend.id, backend])
        );

        if (sessionId && this.sessions.has(sessionId)) {
            const mappedId = this.sessions.get(sessionId);
            const mappedBackend = eligible.get(mappedId);

            if (mappedBackend) {
                return mappedBackend;
            }

            this.sessions.delete(sessionId);
        }

        const selected = this.fallback(backends);

        if (selected && sessionId) {
            this.sessions.set(sessionId, selected.id);
        }

        return selected;
    }

    invalidateBackend(backendId) {
        for (const [sessionId, mappedBackendId] of this.sessions.entries()) {
            if (mappedBackendId === backendId) {
                this.sessions.delete(sessionId);
            }
        }
    }
}

class HealthMonitor extends EventEmitter {
    constructor({ intervalMs = 100, failureThreshold = 2, successThreshold = 2 } = {}) {
        super();
        this.intervalMs = intervalMs;
        this.failureThreshold = failureThreshold;
        this.successThreshold = successThreshold;
    }

    async check(backend) {
        /*
         * setTimeout represents network latency. In a real health check,
         * fetch(), a TCP socket, or an HTTP client would perform the actual
         * network operation and would need a strict timeout.
         */
        await new Promise((resolve) =>
            setTimeout(resolve, Math.min(backend.latencyMs, this.intervalMs))
        );

        const healthy =
            backend.health.enabled &&
            backend.health.endpointAvailable &&
            backend.state !== BackendState.DRAINING;

        if (healthy) {
            backend.health.consecutiveSuccesses += 1;
            backend.health.consecutiveFailures = 0;

            if (
                backend.state === BackendState.UNHEALTHY &&
                backend.health.consecutiveSuccesses >= this.successThreshold
            ) {
                backend.state = BackendState.HEALTHY;
                this.emit("backendRecovered", backend);
            }
        } else {
            backend.health.consecutiveFailures += 1;
            backend.health.consecutiveSuccesses = 0;

            if (
                backend.health.consecutiveFailures >= this.failureThreshold &&
                backend.state === BackendState.HEALTHY
            ) {
                backend.state = BackendState.UNHEALTHY;
                this.emit("backendFailed", backend);
            }
        }

        return {
            backendId: backend.id,
            healthy,
            state: backend.state,
        };
    }

    async checkAll(backends) {
        return Promise.all(backends.map((backend) => this.check(backend)));
    }
}

class HttpRouter {
    constructor() {
        this.rules = [];
    }

    addRule({ method = "*", prefix, backendId }) {
        if (!prefix.startsWith("/")) {
            throw new Error("HTTP route prefixes must begin with '/'");
        }

        this.rules.push({
            method: method.toUpperCase(),
            prefix,
            backendId,
        });
    }

    match(request) {
        const normalizedMethod = request.method.toUpperCase();

        return (
            this.rules.find(
                (rule) =>
                    (rule.method === "*" || rule.method === normalizedMethod) &&
                    request.path.startsWith(rule.prefix)
            ) || null
        );
    }
}

class LoadBalancer {
    constructor({ backends, algorithm = "roundRobin" }) {
        this.backends = backends;
        this.algorithm = algorithm;

        this.roundRobin = new RoundRobin();
        this.weighted = new WeightedRoundRobin();
        this.leastConnections = new LeastConnections();
        this.ipHash = new IpHash();
        this.sticky = new StickySessions((items) =>
            this.roundRobin.select(items)
        );

        this.httpRouter = new HttpRouter();
        this.healthMonitor = new HealthMonitor();

        this.metrics = {
            requests: 0,
            routingFailures: 0,
            applicationFailures: 0,
        };

        this.healthMonitor.on("backendFailed", (backend) => {
            this.sticky.invalidateBackend(backend.id);
            console.log(`[health] ${backend.id} marked unhealthy`);
        });

        this.healthMonitor.on("backendRecovered", (backend) => {
            console.log(`[health] ${backend.id} recovered`);
        });
    }

    addHttpRoute(rule) {
        this.httpRouter.addRule(rule);
    }

    eligibleBackendById(id) {
        return (
            this.backends.find(
                (backend) => backend.id === id && backend.canAccept()
            ) || null
        );
    }

    chooseByAlgorithm(request) {
        switch (this.algorithm) {
            case "roundRobin":
                return this.roundRobin.select(this.backends);

            case "weighted":
                return this.weighted.select(this.backends);

            case "leastConnections":
                return this.leastConnections.select(this.backends);

            case "ipHash":
                return this.ipHash.select(this.backends, request.clientIp);

            case "sticky":
                return this.sticky.select(this.backends, request.sessionId);

            default:
                throw new Error(`Unknown algorithm: ${this.algorithm}`);
        }
    }

    chooseBackend(request) {
        /*
         * HTTP route matching is deliberately performed before the generic
         * balancing algorithm. This is a Layer 7 decision because the
         * selection depends on application-level HTTP metadata.
         */
        if (request.protocol === Protocol.HTTP) {
            const route = this.httpRouter.match(request);

            if (route) {
                const routedBackend = this.eligibleBackendById(route.backendId);

                if (routedBackend) {
                    return routedBackend;
                }
            }
        }

        return this.chooseByAlgorithm(request);
    }

    async handle(request) {
        this.metrics.requests += 1;

        const backend = this.chooseBackend(request);

        if (!backend) {
            this.metrics.routingFailures += 1;

            return {
                ok: false,
                requestId: request.id,
                reason: "No eligible backend",
            };
        }

        if (!backend.openConnection()) {
            this.metrics.routingFailures += 1;

            return {
                ok: false,
                requestId: request.id,
                reason: "Backend capacity exhausted",
            };
        }

        /*
         * A successful TCP connection does not prove that the application
         * produced a successful response. This distinction matters when
         * designing health checks and observability.
         */
        const applicationSuccess = backend.applicationHealthy;

        backend.closeConnection(applicationSuccess);

        if (!applicationSuccess) {
            this.metrics.applicationFailures += 1;
        }

        return {
            ok: applicationSuccess,
            requestId: request.id,
            backend: backend.id,
            protocol: request.protocol,
            path: request.path,
            sessionId: request.sessionId || null,
        };
    }

    drainBackend(id) {
        const backend = this.backends.find((item) => item.id === id);

        if (!backend) {
            throw new Error(`Unknown backend ${id}`);
        }

        backend.state = BackendState.DRAINING;
        this.sticky.invalidateBackend(id);
    }

    restoreBackend(id) {
        const backend = this.backends.find((item) => item.id === id);

        if (!backend) {
            throw new Error(`Unknown backend ${id}`);
        }

        backend.state = BackendState.HEALTHY;
        backend.health.endpointAvailable = true;
    }
}

function createBackends() {
    return [
        new Backend({
            id: "api-01",
            host: "10.0.1.11",
            weight: 3,
            latencyMs: 10,
            role: "api",
        }),
        new Backend({
            id: "api-02",
            host: "10.0.1.12",
            weight: 2,
            latencyMs: 20,
            role: "api",
        }),
        new Backend({
            id: "api-03",
            host: "10.0.1.13",
            weight: 1,
            latencyMs: 30,
            role: "api",
        }),
    ];
}

async function demonstrateLayer4() {
    console.log("\n=== Layer 4 traffic distribution ===");

    const loadBalancer = new LoadBalancer({
        backends: createBackends(),
        algorithm: "roundRobin",
    });

    const counts = new Map();

    for (let id = 1; id <= 12; id += 1) {
        const result = await loadBalancer.handle({
            id,
            clientIp: `192.0.2.${id}`,
            protocol: Protocol.TCP,
            path: "",
            method: "",
        });

        if (result.ok) {
            counts.set(
                result.backend,
                (counts.get(result.backend) || 0) + 1
            );
        }
    }

    console.log("TCP connection distribution:", Object.fromEntries(counts));
}

async function demonstrateLayer7() {
    console.log("\n=== Layer 7 HTTP routing ===");

    const loadBalancer = new LoadBalancer({
        backends: createBackends(),
        algorithm: "roundRobin",
    });

    loadBalancer.addHttpRoute({
        method: "GET",
        prefix: "/api/",
        backendId: "api-01",
    });

    loadBalancer.addHttpRoute({
        method: "GET",
        prefix: "/static/",
        backendId: "api-03",
    });

    const requests = [
        {
            id: 101,
            clientIp: "198.51.100.1",
            protocol: Protocol.HTTP,
            method: "GET",
            path: "/api/orders",
        },
        {
            id: 102,
            clientIp: "198.51.100.2",
            protocol: Protocol.HTTP,
            method: "GET",
            path: "/static/app.js",
        },
        {
            id: 103,
            clientIp: "198.51.100.3",
            protocol: Protocol.HTTP,
            method: "GET",
            path: "/",
        },
    ];

    for (const request of requests) {
        console.log(await loadBalancer.handle(request));
    }
}

async function demonstrateAlgorithms() {
    console.log("\n=== Algorithm comparison ===");

    for (const algorithm of [
        "roundRobin",
        "weighted",
        "leastConnections",
        "ipHash",
    ]) {
        const loadBalancer = new LoadBalancer({
            backends: createBackends(),
            algorithm,
        });

        const counts = new Map();

        for (let id = 0; id < 30; id += 1) {
            const result = await loadBalancer.handle({
                id,
                clientIp: `203.0.113.${(id % 5) + 1}`,
                protocol: Protocol.TCP,
            });

            if (result.ok) {
                counts.set(
                    result.backend,
                    (counts.get(result.backend) || 0) + 1
                );
            }
        }

        console.log(algorithm, Object.fromEntries(counts));
    }
}

async function demonstrateHealthChecks() {
    console.log("\n=== Active health checks ===");

    const loadBalancer = new LoadBalancer({
        backends: createBackends(),
        algorithm: "roundRobin",
    });

    console.log(await loadBalancer.healthMonitor.checkAll(loadBalancer.backends));

    const failedBackend = loadBalancer.backends[1];

    failedBackend.health.endpointAvailable = false;

    /*
     * The failure threshold prevents one transient failed probe from
     * immediately removing a backend. Production systems commonly combine
     * thresholds, timeouts, probe intervals, and recovery thresholds.
     */
    await loadBalancer.healthMonitor.check(failedBackend);
    await loadBalancer.healthMonitor.check(failedBackend);

    console.log(
        "After failure:",
        failedBackend.id,
        failedBackend.state
    );

    for (let id = 200; id < 206; id += 1) {
        console.log(
            await loadBalancer.handle({
                id,
                clientIp: `192.168.1.${id - 199}`,
                protocol: Protocol.TCP,
            })
        );
    }

    failedBackend.health.endpointAvailable = true;

    await loadBalancer.healthMonitor.check(failedBackend);
    await loadBalancer.healthMonitor.check(failedBackend);

    console.log(
        "After recovery:",
        failedBackend.id,
        failedBackend.state
    );
}

async function demonstrateStickySessions() {
    console.log("\n=== Sticky sessions ===");

    const loadBalancer = new LoadBalancer({
        backends: createBackends(),
        algorithm: "sticky",
    });

    const baseRequest = {
        clientIp: "203.0.113.50",
        protocol: Protocol.HTTP,
        method: "GET",
        path: "/checkout",
        sessionId: "customer-session-42",
    };

    for (let id = 300; id < 305; id += 1) {
        console.log(
            await loadBalancer.handle({
                ...baseRequest,
                id,
            })
        );
    }

    const sessionBackend = loadBalancer.sticky.sessions.get(
        "customer-session-42"
    );

    console.log("Session mapped to:", sessionBackend);

    const backend = loadBalancer.backends.find(
        (item) => item.id === sessionBackend
    );

    backend.health.endpointAvailable = false;

    await loadBalancer.healthMonitor.check(backend);
    await loadBalancer.healthMonitor.check(backend);

    console.log(
        "Session mapping after backend failure:",
        loadBalancer.sticky.sessions.get("customer-session-42") || "removed"
    );

    console.log(
        await loadBalancer.handle({
            ...baseRequest,
            id: 306,
        })
    );
}

async function demonstrateDrainAndCapacity() {
    console.log("\n=== Connection draining and capacity ===");

    const backends = createBackends();

    backends[0].maxConnections = 1;

    const loadBalancer = new LoadBalancer({
        backends,
        algorithm: "roundRobin",
    });

    /*
     * Simulate an active connection that is still being served. A draining
     * backend should not receive new traffic, while existing work can finish.
     */
    backends[0].openConnection();
    loadBalancer.drainBackend("api-01");

    console.log(
        await loadBalancer.handle({
            id: 400,
            clientIp: "198.51.100.50",
            protocol: Protocol.TCP,
        })
    );

    backends[0].closeConnection();
    loadBalancer.restoreBackend("api-01");

    console.log(
        "api-01 state after restoration:",
        backends[0].state
    );
}

async function demonstrateApplicationFailure() {
    console.log("\n=== Application failure versus routing failure ===");

    const backends = createBackends();
    const loadBalancer = new LoadBalancer({
        backends,
        algorithm: "roundRobin",
    });

    backends[0].applicationHealthy = false;

    const result = await loadBalancer.handle({
        id: 500,
        clientIp: "203.0.113.90",
        protocol: Protocol.HTTP,
        method: "GET",
        path: "/api/orders",
    });

    console.log("Application response failure:", result);
    console.log("Metrics:", loadBalancer.metrics);
}

async function main() {
    await demonstrateLayer4();
    await demonstrateLayer7();
    await demonstrateAlgorithms();
    await demonstrateHealthChecks();
    await demonstrateStickySessions();
    await demonstrateDrainAndCapacity();
    await demonstrateApplicationFailure();

    console.log("\n=== Operational distinctions ===");
    console.log(
        "Layer 4 can distribute transport connections without parsing HTTP."
    );
    console.log(
        "Layer 7 can route using HTTP paths and methods because it understands application data."
    );
    console.log(
        "Health checks determine backend eligibility; they do not automatically guarantee correct application responses."
    );
    console.log(
        "Sticky sessions preserve session locality but can concentrate traffic on individual backends."
    );
}

main().catch((error) => {
    console.error("Load-balancer simulation failed:", error.message);
    process.exitCode = 1;
});
