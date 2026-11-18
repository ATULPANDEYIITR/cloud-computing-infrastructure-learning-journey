"use strict";

/**
 * Docker Container Management
 *
 * Event-driven lifecycle and operational policy simulator.
 * Runtime: Node.js 18+
 *
 * This program models Docker operations. It does not execute
 * Docker commands or start real operating-system containers.
 */

const { EventEmitter } = require("node:events");
const fs = require("node:fs/promises");
const path = require("node:path");
const crypto = require("node:crypto");
const os = require("node:os");

const State = Object.freeze({
    CREATED: "created",
    RUNNING: "running",
    PAUSED: "paused",
    STOPPED: "stopped",
    EXITED: "exited",
    REMOVING: "removing"
});

const RestartPolicy = Object.freeze({
    NO: "no",
    ALWAYS: "always",
    ON_FAILURE: "on-failure",
    UNLESS_STOPPED: "unless-stopped"
});

class ContainerError extends Error {}
class ValidationError extends ContainerError {}
class LifecycleError extends ContainerError {}
class NotFoundError extends ContainerError {}
class SecurityError extends ContainerError {}

function validateName(name) {
    if (
        typeof name !== "string" ||
        !/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$/.test(name)
    ) {
        throw new ValidationError("Invalid container name.");
    }
}

function validateEnvironment(environment) {
    if (
        environment === null ||
        typeof environment !== "object" ||
        Array.isArray(environment)
    ) {
        throw new ValidationError("Environment must be an object.");
    }

    const result = {};

    for (const [key, value] of Object.entries(environment)) {
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
            throw new ValidationError(`Invalid environment key: ${key}`);
        }

        if (typeof value !== "string" || value.includes("\0")) {
            throw new ValidationError(
                `Invalid value for environment variable ${key}.`
            );
        }

        result[key] = value;
    }

    return Object.freeze(result);
}

function validateConfig(config) {
    if (!config || typeof config !== "object") {
        throw new ValidationError("Container configuration is required.");
    }

    if (
        typeof config.image !== "string" ||
        !/^[A-Za-z0-9._/:@-]+$/.test(config.image)
    ) {
        throw new ValidationError("Invalid image reference.");
    }

    const memory = config.memoryLimitMB ?? 512;
    const cpu = config.cpuLimit ?? 1;

    if (!Number.isInteger(memory) || memory < 16) {
        throw new ValidationError("Memory must be at least 16 MB.");
    }

    if (!Number.isFinite(cpu) || cpu < 0.1 || cpu > 64) {
        throw new ValidationError("CPU limit must be between 0.1 and 64.");
    }

    const restartPolicy = config.restartPolicy ?? RestartPolicy.NO;

    if (!Object.values(RestartPolicy).includes(restartPolicy)) {
        throw new ValidationError("Unsupported restart policy.");
    }

    const command = config.command ?? [];

    if (
        !Array.isArray(command) ||
        !command.every(item => typeof item === "string")
    ) {
        throw new ValidationError("Command must be an array of strings.");
    }

    return Object.freeze({
        image: config.image,
        command: Object.freeze([...command]),
        environment: validateEnvironment(config.environment ?? {}),
        memoryLimitMB: memory,
        cpuLimit: cpu,
        restartPolicy,
        labels: Object.freeze({ ...(config.labels ?? {}) })
    });
}

class ContainerManager extends EventEmitter {
    #containers = new Map();
    #names = new Map();
    #maximumContainers;

    constructor(maximumContainers = 1000) {
        super();

        if (!Number.isInteger(maximumContainers) || maximumContainers < 1) {
            throw new ValidationError("Invalid container capacity.");
        }

        this.#maximumContainers = maximumContainers;
    }

    #resolve(identifier) {
        const id = this.#names.get(identifier) ?? identifier;
        const container = this.#containers.get(id);

        if (!container) {
            throw new NotFoundError(`Container not found: ${identifier}`);
        }

        return container;
    }

    #record(container, message, level = "INFO") {
        const entry = Object.freeze({
            timestamp: new Date().toISOString(),
            level,
            message
        });

        container.logs.push(entry);

        this.emit("log", {
            containerId: container.id,
            name: container.name,
            ...entry
        });
    }

    #transition(container, expectedStates, nextState, message) {
        if (!expectedStates.includes(container.state)) {
            throw new LifecycleError(
                `Cannot transition from ${container.state} to ${nextState}.`
            );
        }

        const previousState = container.state;
        container.state = nextState;

        this.#record(container, message);

        this.emit("stateChanged", {
            containerId: container.id,
            previousState,
            currentState: nextState
        });
    }

    create(name, rawConfig) {
        validateName(name);

        if (this.#names.has(name)) {
            throw new ValidationError(`Name already exists: ${name}`);
        }

        if (this.#containers.size >= this.#maximumContainers) {
            throw new ContainerError("Container capacity reached.");
        }

        const config = validateConfig(rawConfig);

        const container = {
            id: crypto.randomUUID().replaceAll("-", "").slice(0, 12),
            name,
            config,
            state: State.CREATED,
            createdAt: new Date().toISOString(),
            startedAt: null,
            finishedAt: null,
            exitCode: null,
            restartCount: 0,
            logs: []
        };

        this.#containers.set(container.id, container);
        this.#names.set(name, container.id);

        this.#record(container, `Created from image ${config.image}`);

        this.emit("containerCreated", {
            id: container.id,
            name
        });

        return container.id;
    }

    start(identifier) {
        const container = this.#resolve(identifier);

        this.#transition(
            container,
            [State.CREATED, State.STOPPED, State.EXITED],
            State.RUNNING,
            "Container started."
        );

        container.startedAt = new Date().toISOString();
        container.finishedAt = null;
        container.exitCode = null;

        return this.inspect(identifier);
    }

    pause(identifier) {
        const container = this.#resolve(identifier);

        this.#transition(
            container,
            [State.RUNNING],
            State.PAUSED,
            "Container paused."
        );

        return this.inspect(identifier);
    }

    unpause(identifier) {
        const container = this.#resolve(identifier);

        this.#transition(
            container,
            [State.PAUSED],
            State.RUNNING,
            "Container resumed."
        );

        return this.inspect(identifier);
    }

    stop(identifier, exitCode = 0) {
        const container = this.#resolve(identifier);

        if (!Number.isInteger(exitCode) || exitCode < 0 || exitCode > 255) {
            throw new ValidationError("Exit code must be between 0 and 255.");
        }

        this.#transition(
            container,
            [State.RUNNING, State.PAUSED],
            State.STOPPED,
            `Container stopped with exit code ${exitCode}.`
        );

        container.exitCode = exitCode;
        container.finishedAt = new Date().toISOString();

        return this.inspect(identifier);
    }

    simulateExit(identifier, exitCode) {
        const container = this.#resolve(identifier);

        if (!Number.isInteger(exitCode) || exitCode < 0 || exitCode > 255) {
            throw new ValidationError("Invalid exit code.");
        }

        this.#transition(
            container,
            [State.RUNNING],
            State.EXITED,
            `Main process exited with code ${exitCode}.`
        );

        container.exitCode = exitCode;
        container.finishedAt = new Date().toISOString();

        return this.inspect(identifier);
    }

    async restart(identifier) {
        const container = this.#resolve(identifier);

        this.#transition(
            container,
            [State.RUNNING, State.PAUSED, State.STOPPED, State.EXITED],
            State.STOPPED,
            "Restart stopping phase completed."
        );

        // Yield to the event loop to model an asynchronous restart operation.
        await new Promise(resolve => setImmediate(resolve));

        this.#transition(
            container,
            [State.STOPPED],
            State.RUNNING,
            "Container restarted."
        );

        container.restartCount++;
        container.startedAt = new Date().toISOString();
        container.finishedAt = null;
        container.exitCode = null;

        return this.inspect(identifier);
    }

    async applyRestartPolicy(identifier, manuallyStopped = false) {
        const container = this.#resolve(identifier);

        if (container.state !== State.EXITED) {
            return false;
        }

        const policy = container.config.restartPolicy;

        const shouldRestart =
            policy === RestartPolicy.ALWAYS ||
            (
                policy === RestartPolicy.UNLESS_STOPPED &&
                !manuallyStopped
            ) ||
            (
                policy === RestartPolicy.ON_FAILURE &&
                container.exitCode !== 0
            );

        if (shouldRestart) {
            await this.restart(identifier);
        }

        return shouldRestart;
    }

    execute(identifier, command) {
        const container = this.#resolve(identifier);

        if (container.state !== State.RUNNING) {
            throw new LifecycleError("Container must be running.");
        }

        if (!Array.isArray(command) || command.length === 0) {
            throw new ValidationError("A command array is required.");
        }

        const allowed = new Set([
            "printenv",
            "echo",
            "hostname",
            "date",
            "uname"
        ]);

        const executable = command[0];

        if (!allowed.has(executable)) {
            throw new SecurityError(
                `Command rejected by execution policy: ${executable}`
            );
        }

        let output = "";

        switch (executable) {
            case "printenv": {
                const env = container.config.environment;

                output = command.length > 1
                    ? (env[command[1]] ?? "")
                    : Object.entries(env)
                        .sort(([a], [b]) => a.localeCompare(b))
                        .map(([key, value]) => `${key}=${value}`)
                        .join(os.EOL);
                break;
            }

            case "echo":
                output = command.slice(1).join(" ");
                break;

            case "hostname":
                output = container.name;
                break;

            case "date":
                output = new Date().toISOString();
                break;

            case "uname":
                output = "Simulated Linux container environment";
                break;
        }

        this.#record(
            container,
            `Executed: ${JSON.stringify(command)}`
        );

        return {
            command: [...command],
            output,
            exitCode: 0
        };
    }

    inspect(identifier) {
        const container = this.#resolve(identifier);

        return {
            id: container.id,
            name: container.name,
            image: container.config.image,
            state: container.state,
            createdAt: container.createdAt,
            startedAt: container.startedAt,
            finishedAt: container.finishedAt,
            exitCode: container.exitCode,
            restartCount: container.restartCount,
            environment: { ...container.config.environment },
            command: [...container.config.command],
            resources: {
                memoryLimitMB: container.config.memoryLimitMB,
                cpuLimit: container.config.cpuLimit
            },
            restartPolicy: container.config.restartPolicy,
            labels: { ...container.config.labels }
        };
    }

    list({ state = null, label = null } = {}) {
        return [...this.#containers.values()]
            .filter(container => state === null || container.state === state)
            .filter(container => {
                if (!label) return true;

                const [key, value] = label.split("=", 2);

                return container.config.labels[key] === value;
            })
            .map(container => ({
                id: container.id,
                name: container.name,
                image: container.config.image,
                state: container.state
            }))
            .sort((a, b) => a.name.localeCompare(b.name));
    }

    logs(identifier, { tail = null, level = null } = {}) {
        const container = this.#resolve(identifier);

        if (tail !== null && (!Number.isInteger(tail) || tail < 0)) {
            throw new ValidationError("Tail must be a non-negative integer.");
        }

        let entries = container.logs;

        if (level) {
            entries = entries.filter(
                entry => entry.level === level.toUpperCase()
            );
        }

        if (tail !== null) {
            entries = tail === 0 ? [] : entries.slice(-tail);
        }

        return entries.map(entry => ({ ...entry }));
    }

    async exportLogs(identifier, directory = "./container_logs") {
        const container = this.#resolve(identifier);

        await fs.mkdir(directory, { recursive: true });

        const filename = path.join(
            directory,
            `${container.id}.json`
        );

        const temporary = `${filename}.tmp`;

        await fs.writeFile(
            temporary,
            JSON.stringify(container.logs, null, 2),
            { encoding: "utf8", mode: 0o600 }
        );

        await fs.rename(temporary, filename);

        return filename;
    }

    remove(identifier, force = false) {
        const container = this.#resolve(identifier);

        if (
            [State.RUNNING, State.PAUSED].includes(container.state) &&
            !force
        ) {
            throw new LifecycleError(
                "Stop the container before removal or use force."
            );
        }

        container.state = State.REMOVING;

        this.#containers.delete(container.id);
        this.#names.delete(container.name);

        this.emit("containerRemoved", {
            id: container.id,
            name: container.name
        });
    }
}

async function main() {
    const manager = new ContainerManager(50);

    manager.on("stateChanged", event => {
        console.log(
            `[EVENT] ${event.containerId}: ` +
            `${event.previousState} -> ${event.currentState}`
        );
    });

    manager.on("log", event => {
        console.log(
            `[LOG] ${event.name}: ${event.message}`
        );
    });

    console.log("\n1. Create container");

    const id = manager.create("orders-api", {
        image: "node:22-alpine",
        command: ["node", "server.js"],
        environment: {
            NODE_ENV: "production",
            PORT: "3000",
            SERVICE_NAME: "orders-api"
        },
        memoryLimitMB: 1024,
        cpuLimit: 2,
        restartPolicy: RestartPolicy.ON_FAILURE,
        labels: {
            team: "platform",
            application: "orders"
        }
    });

    console.log("\n2. Start and inspect");

    manager.start(id);
    console.log(JSON.stringify(manager.inspect(id), null, 2));

    console.log("\n3. Execute commands");

    console.log(manager.execute(id, ["printenv", "NODE_ENV"]));
    console.log(manager.execute(id, ["echo", "Service ready"]));

    console.log("\n4. Pause and resume");

    manager.pause(id);
    manager.unpause(id);

    console.log("\n5. Container logs");

    console.log(manager.logs(id, { tail: 5 }));

    console.log("\n6. Simulate process failure");

    manager.simulateExit(id, 1);

    const restarted = await manager.applyRestartPolicy(id);
    console.log("Restart performed:", restarted);

    console.log("\n7. Container inventory");

    console.log(manager.list({
        state: State.RUNNING,
        label: "team=platform"
    }));

    console.log("\n8. Export logs");

    const exportedFile = await manager.exportLogs(id);
    console.log("Logs exported to:", exportedFile);

    console.log("\n9. Failure handling");

    try {
        manager.execute(id, ["rm", "-rf", "/"]);
    } catch (error) {
        console.log("Security rejection:", error.message);
    }

    try {
        manager.pause(id);
        manager.pause(id);
    } catch (error) {
        console.log("Lifecycle rejection:", error.message);
    }

    console.log("\n10. Stop and remove");

    manager.stop(id);
    manager.remove(id);

    console.log("Remaining containers:", manager.list());

    if (manager.list().length !== 0) {
        throw new Error("Final inventory assertion failed.");
    }

    console.log("\nAll checks completed.");
}

main().catch(error => {
    console.error("Application failure:", error.message);
    process.exitCode = 1;
});
