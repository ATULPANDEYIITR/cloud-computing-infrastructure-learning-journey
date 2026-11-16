"use strict";

/*
 * Docker Fundamentals: Event-Driven Runtime and Registry Model.
 *
 * Demonstrates:
 * - Docker client and daemon separation
 * - Image metadata and content-addressed layers
 * - Container lifecycle management
 * - Registry authentication and image distribution
 * - Asynchronous operations and event handling
 * - Resource allocation and policy evaluation
 * - Image and container inventory
 *
 * Runtime: Node.js 18+
 * Dependencies: None
 */

const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const EventEmitter = require("node:events");


class DockerError extends Error {
    constructor(message, code = "DOCKER_ERROR") {
        super(message);
        this.name = "DockerError";
        this.code = code;
    }
}


const ContainerState = Object.freeze({
    CREATED: "created",
    RUNNING: "running",
    STOPPED: "stopped",
    REMOVED: "removed"
});


const CheckState = Object.freeze({
    PASS: "pass",
    FAIL: "fail",
    PENDING: "pending"
});


function validateReference(reference) {
    if (typeof reference !== "string" || !reference.trim()) {
        throw new DockerError(
            "Image reference is required.",
            "INVALID_REFERENCE"
        );
    }

    if (/\s/.test(reference) || reference.startsWith("-")) {
        throw new DockerError(
            "Invalid image reference.",
            "INVALID_REFERENCE"
        );
    }

    const parts = reference.split(":");

    if (parts.length > 2) {
        throw new DockerError(
            "Invalid image reference.",
            "INVALID_REFERENCE"
        );
    }

    const repository = parts[0];
    const tag = parts[1] || "latest";

    if (!/^[a-zA-Z0-9._/-]+$/.test(repository)) {
        throw new DockerError(
            "Invalid repository name.",
            "INVALID_REFERENCE"
        );
    }

    if (!/^[a-zA-Z0-9_.-]+$/.test(tag)) {
        throw new DockerError(
            "Invalid image tag.",
            "INVALID_REFERENCE"
        );
    }

    return `${repository}:${tag}`;
}


function digest(value) {
    return "sha256:" + crypto
        .createHash("sha256")
        .update(value)
        .digest("hex");
}


class ResourceManager {
    constructor({ memoryMB = 8192, cpu = 8 } = {}) {
        if (memoryMB <= 0 || cpu <= 0) {
            throw new DockerError(
                "Resource capacity must be positive.",
                "INVALID_CAPACITY"
            );
        }

        this.capacity = { memoryMB, cpu };
        this.allocations = new Map();
    }

    reserve(containerId, memoryMB, cpu) {
        if (memoryMB <= 0 || cpu <= 0) {
            throw new DockerError(
                "Invalid resource allocation.",
                "INVALID_RESOURCE"
            );
        }

        if (this.allocations.has(containerId)) {
            throw new DockerError(
                "Resources already allocated.",
                "RESOURCE_CONFLICT"
            );
        }

        const current = [...this.allocations.values()].reduce(
            (total, item) => ({
                memoryMB: total.memoryMB + item.memoryMB,
                cpu: total.cpu + item.cpu
            }),
            { memoryMB: 0, cpu: 0 }
        );

        if (
            current.memoryMB + memoryMB > this.capacity.memoryMB ||
            current.cpu + cpu > this.capacity.cpu
        ) {
            throw new DockerError(
                "Insufficient daemon resources.",
                "RESOURCE_EXHAUSTED"
            );
        }

        this.allocations.set(containerId, { memoryMB, cpu });
    }

    release(containerId) {
        this.allocations.delete(containerId);
    }

    usage() {
        return [...this.allocations.values()].reduce(
            (total, item) => ({
                memoryMB: total.memoryMB + item.memoryMB,
                cpu: total.cpu + item.cpu
            }),
            { memoryMB: 0, cpu: 0 }
        );
    }
}


class Image {
    constructor({ repository, tag, instructions, environment = {} }) {
        this.reference = validateReference(`${repository}:${tag}`);

        if (!Array.isArray(instructions) || instructions.length === 0) {
            throw new DockerError(
                "At least one image layer is required.",
                "EMPTY_IMAGE"
            );
        }

        this.layers = instructions.map((instruction, index) => {
            if (
                typeof instruction !== "string" ||
                !instruction.trim()
            ) {
                throw new DockerError(
                    `Invalid layer at position ${index}.`,
                    "INVALID_LAYER"
                );
            }

            return Object.freeze({
                index,
                instruction,
                digest: digest(instruction)
            });
        });

        this.id = digest(
            this.layers.map(layer => layer.digest).join("")
        );

        this.environment = Object.freeze({ ...environment });
        this.createdAt = new Date().toISOString();
    }

    inspect() {
        return {
            id: this.id,
            reference: this.reference,
            layers: this.layers,
            environment: this.environment,
            createdAt: this.createdAt
        };
    }
}


class Registry {
    constructor(name) {
        if (!name || typeof name !== "string") {
            throw new DockerError(
                "Registry name is required.",
                "INVALID_REGISTRY"
            );
        }

        this.name = name;
        this.credentials = new Map();
        this.images = new Map();
    }

    authenticate(username, token) {
        if (!username || !token || token.length < 8) {
            throw new DockerError(
                "Invalid registry credentials.",
                "AUTHENTICATION_FAILED"
            );
        }

        // Demonstration only: production credentials must be stored
        // securely and never kept as plaintext in application memory.
        this.credentials.set(username, token);
    }

    verify(username, token) {
        const stored = this.credentials.get(username);

        if (
            !stored ||
            !crypto.timingSafeEqual(
                Buffer.from(stored),
                Buffer.from(token)
            )
        ) {
            throw new DockerError(
                "Registry authentication failed.",
                "AUTHENTICATION_FAILED"
            );
        }
    }

    async push(image, username, token) {
        await Promise.resolve();
        this.verify(username, token);

        this.images.set(image.reference, image);

        return {
            registry: this.name,
            reference: image.reference,
            imageId: image.id
        };
    }

    async pull(reference, username, token) {
        await Promise.resolve();
        this.verify(username, token);

        const image = this.images.get(validateReference(reference));

        if (!image) {
            throw new DockerError(
                "Image does not exist in registry.",
                "IMAGE_NOT_FOUND"
            );
        }

        return image;
    }
}


class Container {
    constructor({
        name,
        image,
        ports = {},
        environment = {},
        memoryMB = 512,
        cpu = 1
    }) {
        if (!/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$/.test(name)) {
            throw new DockerError(
                "Invalid container name.",
                "INVALID_NAME"
            );
        }

        this.id = crypto.randomUUID().replaceAll("-", "").slice(0, 12);
        this.name = name;
        this.imageId = image.id;
        this.imageReference = image.reference;
        this.state = ContainerState.CREATED;
        this.ports = { ...ports };
        this.environment = Object.freeze({ ...environment });
        this.memoryMB = memoryMB;
        this.cpu = cpu;
        this.logs = [];
        this.createdAt = new Date().toISOString();
    }
}


class DockerDaemon extends EventEmitter {
    constructor(options = {}) {
        super();

        this.images = new Map();
        this.tags = new Map();
        this.containers = new Map();
        this.registries = new Map();
        this.ports = new Map();

        this.resources = new ResourceManager(options);
        this.available = true;
        this.operationQueue = Promise.resolve();
    }

    assertAvailable() {
        if (!this.available) {
            throw new DockerError(
                "Docker daemon is unavailable.",
                "DAEMON_UNAVAILABLE"
            );
        }
    }

    emitAudit(action, resourceId, details = {}) {
        const event = Object.freeze({
            timestamp: new Date().toISOString(),
            action,
            resourceId,
            details
        });

        this.emit("docker:event", event);
    }

    async serialize(operation) {
        // Serialize state-changing operations to avoid concurrent
        // resource-allocation and port-reservation races.
        const current = this.operationQueue.then(operation);

        this.operationQueue = current.catch(() => {});

        return current;
    }

    registerRegistry(registry) {
        this.registries.set(registry.name, registry);
    }

    async buildImage(configuration) {
        return this.serialize(async () => {
            this.assertAvailable();

            const image = new Image(configuration);

            const existingId = this.tags.get(image.reference);

            if (existingId && existingId !== image.id) {
                const oldImage = this.images.get(existingId);

                if (
                    oldImage &&
                    ![...this.containers.values()].some(
                        container =>
                            container.imageId === existingId &&
                            container.state !== ContainerState.REMOVED
                    )
                ) {
                    this.images.delete(existingId);
                }
            }

            this.images.set(image.id, image);
            this.tags.set(image.reference, image.id);

            this.emitAudit("image:build", image.id, {
                reference: image.reference
            });

            return image;
        });
    }

    getImage(reference) {
        this.assertAvailable();

        const imageId = this.tags.get(reference) || reference;
        const image = this.images.get(imageId);

        if (!image) {
            throw new DockerError(
                `Image not found: ${reference}`,
                "IMAGE_NOT_FOUND"
            );
        }

        return image;
    }

    async push(reference, registryName, username, token) {
        this.assertAvailable();

        const registry = this.registries.get(registryName);

        if (!registry) {
            throw new DockerError(
                "Registry not found.",
                "REGISTRY_NOT_FOUND"
            );
        }

        const image = this.getImage(reference);
        const result = await registry.push(image, username, token);

        this.emitAudit("image:push", image.id, result);

        return result;
    }

    async pull(reference, registryName, username, token) {
        this.assertAvailable();

        const registry = this.registries.get(registryName);

        if (!registry) {
            throw new DockerError(
                "Registry not found.",
                "REGISTRY_NOT_FOUND"
            );
        }

        const image = await registry.pull(reference, username, token);

        return this.serialize(async () => {
            this.assertAvailable();

            this.images.set(image.id, image);
            this.tags.set(image.reference, image.id);

            this.emitAudit("image:pull", image.id, {
                reference: image.reference
            });

            return image;
        });
    }

    async createContainer(configuration) {
        return this.serialize(async () => {
            this.assertAvailable();

            const image = this.getImage(configuration.image);

            const duplicate = [...this.containers.values()].some(
                container =>
                    container.name === configuration.name &&
                    container.state !== ContainerState.REMOVED
            );

            if (duplicate) {
                throw new DockerError(
                    "Container name already exists.",
                    "NAME_CONFLICT"
                );
            }

            const container = new Container({
                ...configuration,
                image
            });

            for (const [host, target] of Object.entries(container.ports)) {
                const hostPort = Number(host);
                const containerPort = Number(target);

                if (
                    !Number.isInteger(hostPort) ||
                    !Number.isInteger(containerPort) ||
                    hostPort < 1 ||
                    hostPort > 65535 ||
                    containerPort < 1 ||
                    containerPort > 65535
                ) {
                    throw new DockerError(
                        "Invalid port mapping.",
                        "INVALID_PORT"
                    );
                }

                if (this.ports.has(hostPort)) {
                    throw new DockerError(
                        `Host port ${hostPort} is occupied.`,
                        "PORT_CONFLICT"
                    );
                }
            }

            this.containers.set(container.id, container);

            this.emitAudit("container:create", container.id, {
                name: container.name,
                image: image.reference
            });

            return container;
        });
    }

    async startContainer(containerId) {
        return this.serialize(async () => {
            this.assertAvailable();

            const container = this.containers.get(containerId);

            if (!container || container.state === ContainerState.REMOVED) {
                throw new DockerError(
                    "Container not found.",
                    "CONTAINER_NOT_FOUND"
                );
            }

            if (container.state === ContainerState.RUNNING) {
                throw new DockerError(
                    "Container is already running.",
                    "INVALID_STATE"
                );
            }

            // Validate every port before reserving any of them.
            for (const hostPort of Object.keys(container.ports)) {
                if (this.ports.has(Number(hostPort))) {
                    throw new DockerError(
                        `Port ${hostPort} is occupied.`,
                        "PORT_CONFLICT"
                    );
                }
            }

            this.resources.reserve(
                container.id,
                container.memoryMB,
                container.cpu
            );

            for (const hostPort of Object.keys(container.ports)) {
                this.ports.set(Number(hostPort), container.id);
            }

            container.state = ContainerState.RUNNING;
            container.logs.push("Container started.");

            this.emitAudit("container:start", container.id);

            return container;
        });
    }

    async stopContainer(containerId) {
        return this.serialize(async () => {
            this.assertAvailable();

            const container = this.containers.get(containerId);

            if (
                !container ||
                container.state !== ContainerState.RUNNING
            ) {
                throw new DockerError(
                    "Container is not running.",
                    "INVALID_STATE"
                );
            }

            container.state = ContainerState.STOPPED;

            for (const hostPort of Object.keys(container.ports)) {
                if (this.ports.get(Number(hostPort)) === container.id) {
                    this.ports.delete(Number(hostPort));
                }
            }

            this.resources.release(container.id);
            container.logs.push("Container stopped.");

            this.emitAudit("container:stop", container.id);

            return container;
        });
    }

    async removeContainer(containerId) {
        return this.serialize(async () => {
            this.assertAvailable();

            const container = this.containers.get(containerId);

            if (
                !container ||
                container.state === ContainerState.REMOVED
            ) {
                throw new DockerError(
                    "Container not found.",
                    "CONTAINER_NOT_FOUND"
                );
            }

            if (container.state === ContainerState.RUNNING) {
                throw new DockerError(
                    "Stop container before removal.",
                    "INVALID_STATE"
                );
            }

            container.state = ContainerState.REMOVED;

            this.emitAudit("container:remove", containerId);
        });
    }

    listContainers(runningOnly = false) {
        return [...this.containers.values()].filter(container => {
            if (container.state === ContainerState.REMOVED) {
                return false;
            }

            return !runningOnly ||
                container.state === ContainerState.RUNNING;
        });
    }

    async saveInventory(path) {
        const snapshot = {
            generatedAt: new Date().toISOString(),
            images: [...this.images.values()].map(image => image.inspect()),
            containers: [...this.containers.values()].map(container => ({
                id: container.id,
                name: container.name,
                imageId: container.imageId,
                state: container.state,
                ports: container.ports
            })),
            resourceUsage: this.resources.usage()
        };

        const temporary = `${path}.tmp`;

        await fs.writeFile(
            temporary,
            JSON.stringify(snapshot, null, 2),
            { mode: 0o600 }
        );

        await fs.rename(temporary, path);

        return snapshot;
    }
}


class DockerClient {
    constructor(daemon) {
        this.daemon = daemon;
    }

    async run(configuration) {
        const container = await this.daemon.createContainer(configuration);

        return this.daemon.startContainer(container.id);
    }

    async ps() {
        return this.daemon.listContainers();
    }

    async images() {
        return [...this.daemon.images.values()].map(
            image => image.inspect()
        );
    }
}


class MergeIndependentPolicy {
    static evaluate({
        requiredChecks,
        checks,
        requiredApprovals,
        approvals,
        conversationsResolved,
        protectedBranch,
        directPush
    }) {
        const failures = [];

        if (directPush && protectedBranch) {
            failures.push("Direct pushes are disabled.");
        }

        const approvedCount = approvals.filter(
            approval =>
                approval.eligible &&
                approval.state === "approved" &&
                !approval.stale &&
                !approval.dismissed
        ).length;

        if (approvedCount < requiredApprovals) {
            failures.push("Required approvals are missing.");
        }

        for (const required of requiredChecks) {
            if (checks.get(required) !== CheckState.PASS) {
                failures.push(`Status check not passed: ${required}`);
            }
        }

        if (!conversationsResolved) {
            failures.push("Unresolved review conversations exist.");
        }

        return {
            eligible: failures.length === 0,
            failures
        };
    }
}


async function main() {
    console.log("DOCKER FUNDAMENTALS");
    console.log("===================");

    const daemon = new DockerDaemon({
        memoryMB: 4096,
        cpu: 4
    });

    const client = new DockerClient(daemon);

    daemon.on("docker:event", event => {
        console.log(
            `[EVENT] ${event.action} | ${event.resourceId.slice(0, 16)}`
        );
    });

    const registry = new Registry("registry.example.com");

    const credentials = {
        username: "developer",
        token: "demo-token-2026"
    };

    registry.authenticate(
        credentials.username,
        credentials.token
    );

    daemon.registerRegistry(registry);

    console.log("\n1. BUILD IMAGE");

    const image = await daemon.buildImage({
        repository: "company/web-service",
        tag: "1.0",
        instructions: [
            "FROM node:22-alpine",
            "WORKDIR /app",
            "COPY package.json .",
            "RUN npm install --omit=dev",
            "COPY src/ ./src",
            "CMD node src/server.js"
        ],
        environment: {
            NODE_ENV: "production",
            PORT: "3000"
        }
    });

    console.log(image.inspect());

    console.log("\n2. PUSH IMAGE");

    await daemon.push(
        image.reference,
        registry.name,
        credentials.username,
        credentials.token
    );

    console.log("\n3. CREATE AND START CONTAINER");

    const container = await client.run({
        name: "web-service",
        image: image.reference,
        ports: { 8080: 3000 },
        memoryMB: 512,
        cpu: 1,
        environment: { NODE_ENV: "production" }
    });

    console.log({
        id: container.id,
        state: container.state,
        image: container.imageReference
    });

    console.log("\n4. RESOURCE USAGE");

    console.log(daemon.resources.usage());

    console.log("\n5. CONTAINER LIST");

    console.table(await client.ps());

    console.log("\n6. PORT CONFLICT");

    try {
        await client.run({
            name: "second-service",
            image: image.reference,
            ports: { 8080: 3001 }
        });
    } catch (error) {
        console.log(error.code, error.message);
    }

    console.log("\n7. REGISTRY PULL");

    const pulled = await daemon.pull(
        image.reference,
        registry.name,
        credentials.username,
        credentials.token
    );

    console.log("Retrieved:", pulled.reference);

    console.log("\n8. CONTAINER STOP");

    await daemon.stopContainer(container.id);

    console.log("\n9. CONTAINER RESTART");

    await daemon.startContainer(container.id);

    console.log("\n10. CONTAINER REMOVAL");

    await daemon.stopContainer(container.id);
    await daemon.removeContainer(container.id);

    console.log("\n11. MERGE POLICY EVALUATION");

    const decision = MergeIndependentPolicy.evaluate({
        requiredChecks: ["build", "tests", "security"],
        checks: new Map([
            ["build", CheckState.PASS],
            ["tests", CheckState.PASS],
            ["security", CheckState.PASS]
        ]),
        requiredApprovals: 2,
        approvals: [
            {
                eligible: true,
                state: "approved",
                stale: false,
                dismissed: false
            },
            {
                eligible: true,
                state: "approved",
                stale: false,
                dismissed: false
            }
        ],
        conversationsResolved: true,
        protectedBranch: true,
        directPush: false
    });

    console.log(decision);

    console.log("\n12. SAVE INVENTORY");

    const snapshot = await daemon.saveInventory(
        "docker_inventory.json"
    );

    console.log(
        `Saved ${snapshot.containers.length} container records.`
    );

    console.log("\n13. ASSERTIONS");

    if (container.state !== ContainerState.REMOVED) {
        throw new Error("Container lifecycle assertion failed.");
    }

    if (!decision.eligible) {
        throw new Error("Merge policy assertion failed.");
    }

    console.log("All assertions passed.");
}


main().catch(error => {
    console.error("Execution failed:", error.message);
    process.exitCode = 1;
});
