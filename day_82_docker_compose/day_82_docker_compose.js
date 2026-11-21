"use strict";

/*
 * Docker Compose: Event-Driven Deployment and Policy Engine
 *
 * Implements:
 * - Service dependency management
 * - Asynchronous startup
 * - Health conditions
 * - Network isolation
 * - Volume configuration
 * - Environment validation
 * - Failure propagation
 * - Restart policies
 * - Deployment lifecycle events
 *
 * Requires Node.js 18+.
 */

const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");

class ComposeError extends Error {
    constructor(message) {
        super(message);
        this.name = "ComposeError";
    }
}

class ConfigurationError extends ComposeError {
    constructor(message) {
        super(message);
        this.name = "ConfigurationError";
    }
}

class DependencyError extends ComposeError {
    constructor(message) {
        super(message);
        this.name = "DependencyError";
    }
}

class DeploymentError extends ComposeError {
    constructor(message) {
        super(message);
        this.name = "DeploymentError";
    }
}

const STATES = Object.freeze({
    CREATED: "created",
    STARTING: "starting",
    RUNNING: "running",
    HEALTHY: "healthy",
    UNHEALTHY: "unhealthy",
    STOPPED: "stopped",
    FAILED: "failed"
});

const CONDITIONS = Object.freeze({
    STARTED: "service_started",
    HEALTHY: "service_healthy",
    COMPLETED: "service_completed_successfully"
});

class Service {
    constructor(config) {
        this.name = config.name;
        this.image = config.image;
        this.dependencies = config.dependencies ?? [];
        this.networks = new Set(config.networks ?? []);
        this.volumes = config.volumes ?? [];
        this.environment = Object.freeze({
            ...(config.environment ?? {})
        });
        this.healthcheck = config.healthcheck ?? false;
        this.restartPolicy = config.restartPolicy ?? "no";
        this.memoryLimit = config.memoryLimit ?? 256;
        this.state = STATES.CREATED;
        this.restartCount = 0;
        this.ports = config.ports ?? [];
        this.startTime = null;

        this.validate();
    }

    validate() {
        if (!this.name || !/^[a-z0-9][a-z0-9_-]*$/i.test(this.name)) {
            throw new ConfigurationError(
                `Invalid service name: ${this.name}`
            );
        }

        if (!this.image || /\s/.test(this.image)) {
            throw new ConfigurationError(
                `Invalid image for ${this.name}`
            );
        }

        if (!Number.isInteger(this.memoryLimit) ||
            this.memoryLimit <= 0) {
            throw new ConfigurationError(
                `Invalid memory limit for ${this.name}`
            );
        }

        if (!["no", "always", "unless-stopped", "on-failure"]
            .includes(this.restartPolicy)) {
            throw new ConfigurationError(
                `Invalid restart policy for ${this.name}`
            );
        }

        for (const [key, value] of Object.entries(this.environment)) {
            if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
                throw new ConfigurationError(
                    `Invalid environment key: ${key}`
                );
            }

            if (typeof value !== "string" ||
                value.includes("\0")) {
                throw new ConfigurationError(
                    `Invalid environment value: ${key}`
                );
            }
        }

        for (const port of this.ports) {
            if (!Number.isInteger(port.host) ||
                !Number.isInteger(port.container) ||
                port.host < 1 || port.host > 65535 ||
                port.container < 1 || port.container > 65535) {
                throw new ConfigurationError(
                    `Invalid port mapping for ${this.name}`
                );
            }
        }
    }
}

class ComposeApplication extends EventEmitter {
    constructor(config) {
        super();

        this.services = new Map();
        this.networks = new Map();
        this.volumes = new Map();
        this.events = [];
        this.maxConcurrentStarts = config.maxConcurrentStarts ?? 3;

        for (const network of config.networks ?? []) {
            this.networks.set(network.name, {
                name: network.name,
                internal: Boolean(network.internal)
            });
        }

        for (const volume of config.volumes ?? []) {
            this.volumes.set(volume.name, {
                name: volume.name,
                persistent: volume.persistent !== false,
                driver: volume.driver ?? "local"
            });
        }

        for (const serviceConfig of config.services) {
            const service = new Service(serviceConfig);

            if (this.services.has(service.name)) {
                throw new ConfigurationError(
                    `Duplicate service: ${service.name}`
                );
            }

            this.services.set(service.name, service);
        }

        this.validate();
    }

    record(type, service, details = {}) {
        const event = Object.freeze({
            id: crypto.randomUUID(),
            timestamp: new Date().toISOString(),
            type,
            service,
            details
        });

        this.events.push(event);
        this.emit("deployment-event", event);
    }

    validate() {
        if (this.services.size === 0) {
            throw new ConfigurationError(
                "Application requires at least one service."
            );
        }

        const hostPorts = new Map();

        for (const service of this.services.values()) {
            for (const network of service.networks) {
                if (!this.networks.has(network)) {
                    throw new ConfigurationError(
                        `${service.name} references unknown network ${network}`
                    );
                }
            }

            for (const volume of service.volumes) {
                if (!this.volumes.has(volume.name)) {
                    throw new ConfigurationError(
                        `${service.name} references unknown volume ${volume.name}`
                    );
                }
            }

            for (const dependency of service.dependencies) {
                if (!this.services.has(dependency.service)) {
                    throw new DependencyError(
                        `${service.name} depends on missing ${dependency.service}`
                    );
                }

                if (!Object.values(CONDITIONS).includes(
                    dependency.condition
                )) {
                    throw new DependencyError(
                        `Invalid dependency condition in ${service.name}`
                    );
                }

                if (dependency.service === service.name) {
                    throw new DependencyError(
                        `${service.name} cannot depend on itself`
                    );
                }
            }

            for (const port of service.ports) {
                if (hostPorts.has(port.host)) {
                    throw new ConfigurationError(
                        `Host port ${port.host} conflicts with ${hostPorts.get(port.host)}`
                    );
                }

                hostPorts.set(port.host, service.name);
            }
        }

        this.topologicalOrder();
    }

    topologicalOrder() {
        const visited = new Set();
        const active = new Set();
        const order = [];

        const visit = (name) => {
            if (active.has(name)) {
                throw new DependencyError(
                    `Circular dependency detected: ${name}`
                );
            }

            if (visited.has(name)) {
                return;
            }

            active.add(name);

            const service = this.services.get(name);

            for (const dependency of service.dependencies) {
                visit(dependency.service);
            }

            active.delete(name);
            visited.add(name);
            order.push(name);
        };

        for (const name of this.services.keys()) {
            visit(name);
        }

        return order;
    }

    dependencySatisfied(dependency) {
        const state = this.services.get(
            dependency.service
        ).state;

        switch (dependency.condition) {
            case CONDITIONS.STARTED:
                return [
                    STATES.RUNNING,
                    STATES.HEALTHY
                ].includes(state);

            case CONDITIONS.HEALTHY:
                return state === STATES.HEALTHY;

            case CONDITIONS.COMPLETED:
                return state === STATES.STOPPED;

            default:
                return false;
        }
    }

    async startService(name) {
        const service = this.services.get(name);

        if (!service) {
            throw new DeploymentError(
                `Unknown service: ${name}`
            );
        }

        if ([STATES.RUNNING, STATES.HEALTHY].includes(
            service.state
        )) {
            return;
        }

        for (const dependency of service.dependencies) {
            if (!this.dependencySatisfied(dependency)) {
                throw new DependencyError(
                    `${name} cannot start because ${dependency.service} ` +
                    `does not satisfy ${dependency.condition}`
                );
            }
        }

        service.state = STATES.STARTING;

        this.record("SERVICE_STARTING", name);

        // Simulates asynchronous image/container initialization.
        await new Promise(resolve => setImmediate(resolve));

        service.state = STATES.RUNNING;
        service.startTime = Date.now();

        this.record("SERVICE_RUNNING", name);

        if (service.healthcheck) {
            await this.checkHealth(name, true);
        }
    }

    async checkHealth(name, success) {
        const service = this.services.get(name);

        if (!service ||
            ![STATES.RUNNING, STATES.HEALTHY,
                STATES.UNHEALTHY].includes(service.state)) {
            throw new DeploymentError(
                `Invalid healthcheck state for ${name}`
            );
        }

        service.state = success
            ? STATES.HEALTHY
            : STATES.UNHEALTHY;

        this.record("HEALTHCHECK", name, {
            result: service.state
        });

        return success;
    }

    async startAll() {
        const order = this.topologicalOrder();

        // Dependency layers are started concurrently.
        const remaining = new Set(order);
        const completed = new Set();

        while (remaining.size > 0) {
            const ready = [...remaining].filter(name => {
                const service = this.services.get(name);

                return service.dependencies.every(dep =>
                    completed.has(dep.service)
                );
            });

            if (ready.length === 0) {
                throw new DependencyError(
                    "No services can start. Dependency graph is blocked."
                );
            }

            for (let i = 0; i < ready.length;
                 i += this.maxConcurrentStarts) {
                const batch = ready.slice(
                    i,
                    i + this.maxConcurrentStarts
                );

                // Promise.allSettled prevents unhandled sibling failures.
                const results = await Promise.allSettled(
                    batch.map(name => this.startService(name))
                );

                const failures = results
                    .map((result, index) => ({
                        result,
                        name: batch[index]
                    }))
                    .filter(item =>
                        item.result.status === "rejected"
                    );

                if (failures.length > 0) {
                    for (const failure of failures) {
                        const service = this.services.get(
                            failure.name
                        );

                        service.state = STATES.FAILED;

                        this.record("SERVICE_FAILED", failure.name, {
                            error: failure.result.reason.message
                        });
                    }

                    throw new DeploymentError(
                        "One or more services failed to start."
                    );
                }

                for (const name of batch) {
                    remaining.delete(name);
                    completed.add(name);
                }
            }
        }

        return order;
    }

    async restart(name) {
        const service = this.services.get(name);

        if (!service) {
            throw new DeploymentError(
                `Unknown service: ${name}`
            );
        }

        if (service.restartPolicy === "no") {
            throw new DeploymentError(
                `Restart disabled for ${name}`
            );
        }

        service.restartCount++;
        service.state = STATES.CREATED;

        this.record("SERVICE_RESTART", name, {
            attempt: service.restartCount
        });

        await this.startService(name);
    }

    networkPeers(name) {
        const service = this.services.get(name);

        if (!service) {
            throw new DeploymentError(
                `Unknown service: ${name}`
            );
        }

        return [...this.services.values()]
            .filter(other =>
                other.name !== name &&
                [...service.networks].some(network =>
                    other.networks.has(network)
                )
            )
            .map(other => other.name);
    }

    async stopAll() {
        const order = this.topologicalOrder().reverse();

        for (const name of order) {
            const service = this.services.get(name);

            if (service.state !== STATES.STOPPED) {
                service.state = STATES.STOPPED;

                this.record("SERVICE_STOPPED", name);
            }
        }
    }

    report() {
        return {
            serviceCount: this.services.size,
            services: Object.fromEntries(
                [...this.services.entries()].map(([name, service]) => [
                    name,
                    {
                        image: service.image,
                        state: service.state,
                        restartCount: service.restartCount,
                        networks: [...service.networks],
                        volumes: service.volumes
                    }
                ])
            ),
            networks: [...this.networks.values()],
            volumes: [...this.volumes.values()],
            events: this.events
        };
    }
}

async function main() {
    const application = new ComposeApplication({
        maxConcurrentStarts: 2,

        networks: [
            { name: "frontend" },
            { name: "backend", internal: true }
        ],

        volumes: [
            { name: "database_data", persistent: true },
            { name: "cache_data", persistent: true }
        ],

        services: [
            {
                name: "database",
                image: "postgres:18",
                networks: ["backend"],
                volumes: [{ name: "database_data" }],
                environment: {
                    POSTGRES_DB: "application",
                    POSTGRES_USER: "appuser",
                    POSTGRES_PASSWORD: "development-secret"
                },
                healthcheck: true,
                restartPolicy: "unless-stopped",
                memoryLimit: 1024
            },
            {
                name: "cache",
                image: "redis:7-alpine",
                networks: ["backend"],
                volumes: [{ name: "cache_data" }],
                healthcheck: true,
                restartPolicy: "unless-stopped"
            },
            {
                name: "api",
                image: "example/api:1.0",
                dependencies: [
                    {
                        service: "database",
                        condition: CONDITIONS.HEALTHY
                    },
                    {
                        service: "cache",
                        condition: CONDITIONS.STARTED
                    }
                ],
                networks: ["frontend", "backend"],
                ports: [{ host: 8080, container: 8080 }],
                environment: {
                    DATABASE_HOST: "database",
                    CACHE_HOST: "cache"
                },
                healthcheck: true,
                restartPolicy: "on-failure"
            },
            {
                name: "web",
                image: "example/web:1.0",
                dependencies: [
                    {
                        service: "api",
                        condition: CONDITIONS.HEALTHY
                    }
                ],
                networks: ["frontend"],
                ports: [{ host: 3000, container: 3000 }],
                environment: {
                    API_URL: "http://api:8080"
                }
            }
        ]
    });

    application.on("deployment-event", event => {
        console.log(
            `[${event.type}] ${event.service}`,
            event.details
        );
    });

    try {
        console.log("\nSTARTING APPLICATION");

        const order = await application.startAll();

        console.log("\nSTARTUP ORDER:", order);

        console.log(
            "\nBACKEND NETWORK PEERS:",
            application.networkPeers("database")
        );

        console.log("\nSIMULATING API FAILURE");

        const api = application.services.get("api");
        api.state = STATES.FAILED;

        await application.restart("api");

        console.log("\nDEPLOYMENT REPORT");

        console.log(
            JSON.stringify(application.report(), null, 2)
        );

    } catch (error) {
        console.error(
            `${error.name}: ${error.message}`
        );

        process.exitCode = 1;

    } finally {
        await application.stopAll();

        console.log("\nAPPLICATION STOPPED");
    }
}

if (require.main === module) {
    main().catch(error => {
        console.error("Fatal error:", error);
        process.exitCode = 1;
    });
}

module.exports = {
    Service,
    ComposeApplication,
    ComposeError,
    ConfigurationError,
    DependencyError,
    DeploymentError,
    STATES,
    CONDITIONS
};
