"use strict";

/*
 * Container Runtime and Deployment Policy Simulator
 *
 * Node.js 18+
 *
 * Engineering focus:
 * - Event-driven lifecycle management
 * - Image content addressing
 * - Asynchronous deployment operations
 * - Resource admission control
 * - Runtime isolation profiles
 * - Health monitoring
 * - Restart policy and backoff
 * - Immutable deployment configuration
 * - Event auditing
 *
 * This is a control-plane simulation. It does not create
 * real operating-system containers.
 */

const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const EventEmitter = require("node:events");

class ContainerError extends Error {}
class ValidationError extends ContainerError {}
class StateError extends ContainerError {}
class ResourceError extends ContainerError {}

const State = Object.freeze({
    CREATED: "created",
    RUNNING: "running",
    PAUSED: "paused",
    STOPPED: "stopped",
    FAILED: "failed",
    REMOVED: "removed"
});

const RestartPolicy = Object.freeze({
    NEVER: "never",
    ON_FAILURE: "on-failure",
    ALWAYS: "always"
});

const Isolation = Object.freeze([
    "pid",
    "network",
    "mount",
    "user",
    "ipc",
    "uts",
    "cgroup"
]);

function validateInteger(value, name, min, max) {
    if (
        !Number.isSafeInteger(value) ||
        value < min ||
        value > max
    ) {
        throw new ValidationError(`Invalid ${name}.`);
    }
}

function validateName(value, name = "name") {
    if (
        typeof value !== "string" ||
        !/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$/.test(value)
    ) {
        throw new ValidationError(`Invalid ${name}.`);
    }
}

function immutableEnvironment(environment = {}) {
    const entries = Object.entries(environment);

    if (entries.length > 128) {
        throw new ValidationError("Environment is too large.");
    }

    for (const [key, value] of entries) {
        if (!/^[A-Z_][A-Z0-9_]{0,63}$/.test(key)) {
            throw new ValidationError("Invalid environment key.");
        }

        if (typeof value !== "string" || value.length > 4096) {
            throw new ValidationError("Invalid environment value.");
        }
    }

    return Object.freeze({ ...environment });
}

class Image {
    constructor({
        name,
        version,
        layers,
        entrypoint,
        exposedPorts = []
    }) {
        if (
            typeof name !== "string" ||
            !/^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,127}$/.test(name)
        ) {
            throw new ValidationError("Invalid image name.");
        }

        if (!version || typeof version !== "string") {
            throw new ValidationError("Invalid image version.");
        }

        if (!Array.isArray(layers) || layers.length === 0) {
            throw new ValidationError("Image needs at least one layer.");
        }

        if (!entrypoint || typeof entrypoint !== "string") {
            throw new ValidationError("Entrypoint is required.");
        }

        for (const port of exposedPorts) {
            validateInteger(port, "port", 1, 65535);
        }

        this.name = name;
        this.version = version;

        this.layers = Object.freeze(
            layers.map(layer => Object.freeze({ ...layer }))
        );

        this.entrypoint = entrypoint;
        this.exposedPorts = Object.freeze([...exposedPorts]);

        const content = JSON.stringify({
            name,
            version,
            layers,
            entrypoint
        });

        this.digest = crypto
            .createHash("sha256")
            .update(content)
            .digest("hex");

        Object.freeze(this);
    }

    get reference() {
        return `${this.name}:${this.version}`;
    }
}

class Registry {
    #images = new Map();

    push(image) {
        if (!(image instanceof Image)) {
            throw new ValidationError("Invalid image object.");
        }

        this.#images.set(image.reference, image);
        this.#images.set(`sha256:${image.digest}`, image);
    }

    async pull(reference) {
        // Simulates asynchronous registry access.
        await Promise.resolve();

        const image = this.#images.get(reference);

        if (!image) {
            throw new ContainerError(
                `Image not found: ${reference}`
            );
        }

        return image;
    }
}

class ResourceBudget {
    constructor({
        cpuCores = 8,
        memoryMB = 8192,
        diskMB = 50000
    } = {}) {
        if (
            !Number.isFinite(cpuCores) ||
            cpuCores <= 0
        ) {
            throw new ValidationError("Invalid host CPU capacity.");
        }

        validateInteger(memoryMB, "host memory", 1, 100000000);
        validateInteger(diskMB, "host disk", 1, 1000000000);

        this.capacity = Object.freeze({
            cpuCores,
            memoryMB,
            diskMB
        });

        this.allocations = new Map();
    }

    allocate(id, limits) {
        if (this.allocations.has(id)) {
            throw new ResourceError("Duplicate allocation.");
        }

        const used = [...this.allocations.values()].reduce(
            (total, item) => ({
                cpuCores: total.cpuCores + item.cpuCores,
                memoryMB: total.memoryMB + item.memoryMB,
                diskMB: total.diskMB + item.diskMB
            }),
            { cpuCores: 0, memoryMB: 0, diskMB: 0 }
        );

        if (
            used.cpuCores + limits.cpuCores >
                this.capacity.cpuCores ||
            used.memoryMB + limits.memoryMB >
                this.capacity.memoryMB ||
            used.diskMB + limits.diskMB >
                this.capacity.diskMB
        ) {
            throw new ResourceError(
                "Insufficient host resources."
            );
        }

        this.allocations.set(id, Object.freeze({ ...limits }));
    }

    release(id) {
        this.allocations.delete(id);
    }

    snapshot() {
        return Object.freeze({
            capacity: this.capacity,
            allocatedContainers: this.allocations.size
        });
    }
}

class ContainerRuntime extends EventEmitter {
    #containers = new Map();
    #names = new Set();
    #restartCounts = new Map();

    constructor(registry, budget) {
        super();
        this.registry = registry;
        this.budget = budget;
    }

    async create({
        imageReference,
        name,
        limits = {
            cpuCores: 1,
            memoryMB: 256,
            diskMB: 512
        },
        environment = {},
        restartPolicy = RestartPolicy.NEVER
    }) {
        validateName(name);

        if (this.#names.has(name)) {
            throw new ValidationError("Container name exists.");
        }

        if (!Object.values(RestartPolicy).includes(restartPolicy)) {
            throw new ValidationError("Invalid restart policy.");
        }

        if (
            !Number.isFinite(limits.cpuCores) ||
            limits.cpuCores <= 0
        ) {
            throw new ValidationError("Invalid CPU limit.");
        }

        validateInteger(limits.memoryMB, "memory", 16, 1048576);
        validateInteger(limits.diskMB, "disk", 16, 10485760);

        const image = await this.registry.pull(imageReference);

        const id = crypto.randomUUID();

        this.budget.allocate(id, limits);

        const container = {
            id,
            name,
            image,
            limits: Object.freeze({ ...limits }),
            environment: immutableEnvironment(environment),
            isolation: Isolation,
            restartPolicy,
            state: State.CREATED,
            health: "unknown",
            createdAt: new Date().toISOString(),
            startedAt: null,
            exitCode: null,
            memoryUsedMB: 0,
            restartCount: 0
        };

        this.#containers.set(id, container);
        this.#names.add(name);

        this.emit("container.created", {
            id,
            name,
            image: image.reference
        });

        return id;
    }

    #get(id) {
        const container = this.#containers.get(id);

        if (!container) {
            throw new ContainerError("Container not found.");
        }

        return container;
    }

    async start(id) {
        const container = this.#get(id);

        if (![State.CREATED, State.STOPPED].includes(container.state)) {
            throw new StateError("Invalid start transition.");
        }

        container.state = State.RUNNING;
        container.startedAt = new Date().toISOString();

        this.emit("container.started", {
            id,
            name: container.name
        });
    }

    pause(id) {
        const container = this.#get(id);

        if (container.state !== State.RUNNING) {
            throw new StateError("Container is not running.");
        }

        container.state = State.PAUSED;
        this.emit("container.paused", { id });
    }

    resume(id) {
        const container = this.#get(id);

        if (container.state !== State.PAUSED) {
            throw new StateError("Container is not paused.");
        }

        container.state = State.RUNNING;
        this.emit("container.resumed", { id });
    }

    stop(id, exitCode = 0) {
        const container = this.#get(id);

        if (![State.RUNNING, State.PAUSED].includes(container.state)) {
            throw new StateError("Invalid stop transition.");
        }

        container.state = State.STOPPED;
        container.exitCode = exitCode;

        this.emit("container.stopped", { id, exitCode });
    }

    updateHealth(id, memoryUsedMB) {
        const container = this.#get(id);

        if (container.state !== State.RUNNING) {
            throw new StateError("Container is not running.");
        }

        validateInteger(memoryUsedMB, "memory usage", 0, 100000000);

        if (memoryUsedMB > container.limits.memoryMB) {
            container.health = "unhealthy";

            this.emit("container.resource-limit", {
                id,
                memoryUsedMB,
                limit: container.limits.memoryMB
            });

            throw new ResourceError("Memory limit exceeded.");
        }

        container.memoryUsedMB = memoryUsedMB;
        container.health = "healthy";

        this.emit("container.health", {
            id,
            status: container.health
        });
    }

    async fail(id, exitCode = 1) {
        const container = this.#get(id);

        if (container.state !== State.RUNNING) {
            throw new StateError("Only running containers can fail.");
        }

        container.state = State.FAILED;
        container.exitCode = exitCode;

        this.emit("container.failed", {
            id,
            exitCode
        });

        const shouldRestart =
            container.restartPolicy === RestartPolicy.ALWAYS ||
            (
                container.restartPolicy === RestartPolicy.ON_FAILURE &&
                exitCode !== 0
            );

        if (!shouldRestart) {
            return;
        }

        const previous = this.#restartCounts.get(id) || 0;

        if (previous >= 3) {
            this.emit("container.restart-exhausted", { id });
            return;
        }

        const delay = Math.min(100 * (2 ** previous), 1000);

        await new Promise(resolve => setTimeout(resolve, delay));

        this.#restartCounts.set(id, previous + 1);
        container.restartCount = previous + 1;
        container.state = State.RUNNING;
        container.startedAt = new Date().toISOString();

        this.emit("container.restarted", {
            id,
            restartCount: container.restartCount
        });
    }

    remove(id) {
        const container = this.#get(id);

        if (
            container.state === State.RUNNING ||
            container.state === State.PAUSED
        ) {
            throw new StateError("Stop before removal.");
        }

        container.state = State.REMOVED;

        this.#containers.delete(id);
        this.#names.delete(container.name);
        this.budget.release(id);

        this.emit("container.removed", { id });
    }

    list() {
        return [...this.#containers.values()].map(container => ({
            id: container.id,
            name: container.name,
            image: container.image.reference,
            digest: container.image.digest,
            state: container.state,
            health: container.health,
            memoryUsedMB: container.memoryUsedMB,
            memoryLimitMB: container.limits.memoryMB,
            restartCount: container.restartCount
        }));
    }
}

class DeploymentController {
    constructor(runtime) {
        this.runtime = runtime;
    }

    async deploy(configuration) {
        const id = await this.runtime.create(configuration);

        try {
            await this.runtime.start(id);
            return id;
        } catch (error) {
            this.runtime.remove(id);
            throw error;
        }
    }
}

async function main() {
    const registry = new Registry();

    const image = new Image({
        name: "enterprise/inventory",
        version: "2.0.0",
        layers: [
            { name: "base", content: "minimal-linux-rootfs" },
            { name: "runtime", content: "node-runtime" },
            { name: "application", content: "inventory-service" }
        ],
        entrypoint: "node server.js",
        exposedPorts: [8080]
    });

    registry.push(image);

    const budget = new ResourceBudget({
        cpuCores: 8,
        memoryMB: 8192,
        diskMB: 50000
    });

    const runtime = new ContainerRuntime(registry, budget);

    runtime.on("container.failed", event => {
        console.error("Failure event:", event);
    });

    runtime.on("container.restarted", event => {
        console.log("Restart event:", event);
    });

    runtime.on("container.health", event => {
        console.log("Health event:", event);
    });

    const controller = new DeploymentController(runtime);

    const id = await controller.deploy({
        imageReference: "enterprise/inventory:2.0.0",
        name: "inventory-service",
        limits: {
            cpuCores: 2,
            memoryMB: 1024,
            diskMB: 2048
        },
        environment: {
            APP_ENV: "production",
            LOG_LEVEL: "INFO"
        },
        restartPolicy: RestartPolicy.ON_FAILURE
    });

    runtime.updateHealth(id, 320);

    console.log("\nRunning containers:");
    console.log(JSON.stringify(runtime.list(), null, 2));

    await runtime.fail(id, 1);

    console.log("\nAfter restart:");
    console.log(JSON.stringify(runtime.list(), null, 2));

    runtime.pause(id);
    runtime.resume(id);
    runtime.stop(id);

    await fs.writeFile(
        "container-audit.json",
        JSON.stringify({
            generatedAt: new Date().toISOString(),
            containers: runtime.list(),
            resources: budget.snapshot()
        }, null, 2),
        { mode: 0o600 }
    );

    runtime.remove(id);

    console.log("\nFinal host allocation:");
    console.log(budget.snapshot());
}

async function test() {
    const registry = new Registry();

    registry.push(new Image({
        name: "test/app",
        version: "1",
        layers: [{ name: "base", content: "linux" }],
        entrypoint: "app"
    }));

    const runtime = new ContainerRuntime(
        registry,
        new ResourceBudget({
            cpuCores: 2,
            memoryMB: 1024,
            diskMB: 2048
        })
    );

    const id = await runtime.create({
        imageReference: "test/app:1",
        name: "test-app"
    });

    await runtime.start(id);

    try {
        await runtime.start(id);
        throw new Error("Invalid transition accepted.");
    } catch (error) {
        if (!(error instanceof StateError)) {
            throw error;
        }
    }

    runtime.stop(id);
    runtime.remove(id);

    console.log("All JavaScript tests passed.");
}

if (require.main === module) {
    test()
        .then(main)
        .catch(error => {
            console.error(error);
            process.exitCode = 1;
        });
}

module.exports = {
    Image,
    Registry,
    ResourceBudget,
    ContainerRuntime,
    DeploymentController,
    State,
    RestartPolicy
};
