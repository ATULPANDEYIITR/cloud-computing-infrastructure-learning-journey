"use strict";

/*
 * Kubernetes Pods: Event-driven lifecycle and policy engine.
 *
 * Runtime: Node.js 18+
 * Run: node pods.js
 *
 * Models:
 * - Pod admission and scheduling
 * - Multi-container networking and shared volumes
 * - Init container execution
 * - Container states and readiness
 * - Restart policies
 * - Lifecycle events
 * - Resource accounting
 * - Graceful termination
 */

const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");

const PodPhase = Object.freeze({
    PENDING: "Pending",
    RUNNING: "Running",
    SUCCEEDED: "Succeeded",
    FAILED: "Failed",
    UNKNOWN: "Unknown"
});

const ContainerState = Object.freeze({
    WAITING: "Waiting",
    RUNNING: "Running",
    TERMINATED: "Terminated"
});

const RestartPolicy = Object.freeze({
    ALWAYS: "Always",
    ON_FAILURE: "OnFailure",
    NEVER: "Never"
});

class ValidationError extends Error {}
class SchedulingError extends Error {}
class LifecycleError extends Error {}

function requirePositiveInteger(value, name) {
    if (!Number.isInteger(value) || value <= 0) {
        throw new ValidationError(`${name} must be a positive integer`);
    }
}

function validateName(value, field) {
    if (
        typeof value !== "string" ||
        !/^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/.test(value)
    ) {
        throw new ValidationError(`Invalid ${field}: ${value}`);
    }
}

class ResourceRequest {
    constructor(cpuMillicores, memoryMiB) {
        requirePositiveInteger(cpuMillicores, "CPU request");
        requirePositiveInteger(memoryMiB, "Memory request");

        this.cpuMillicores = cpuMillicores;
        this.memoryMiB = memoryMiB;
        Object.freeze(this);
    }
}

class ContainerDefinition {
    constructor({
        name,
        image,
        resources,
        ports = [],
        command = [],
        essential = true
    }) {
        validateName(name, "container name");

        if (
            typeof image !== "string" ||
            image.length === 0 ||
            image.length > 253
        ) {
            throw new ValidationError("Invalid container image");
        }

        if (!Array.isArray(ports) || ports.some(
            p => !Number.isInteger(p) || p < 1 || p > 65535
        )) {
            throw new ValidationError("Invalid container ports");
        }

        if (!Array.isArray(command) || command.some(
            item => typeof item !== "string"
        )) {
            throw new ValidationError("Command must be an array of strings");
        }

        if (!(resources instanceof ResourceRequest)) {
            throw new ValidationError("Valid resource request is required");
        }

        this.name = name;
        this.image = image;
        this.resources = resources;
        this.ports = [...ports];
        this.command = [...command];
        this.essential = Boolean(essential);
        Object.freeze(this.ports);
        Object.freeze(this.command);
        Object.freeze(this);
    }
}

class ContainerRuntime {
    constructor(definition) {
        this.definition = definition;
        this.state = ContainerState.WAITING;
        this.restartCount = 0;
        this.ready = false;
        this.exitCode = null;
        this.startedAt = null;
    }

    start() {
        if (this.state === ContainerState.RUNNING) {
            throw new LifecycleError("Container is already running");
        }

        this.state = ContainerState.RUNNING;
        this.exitCode = null;
        this.startedAt = Date.now();
        this.ready = false;
    }

    markReady() {
        if (this.state !== ContainerState.RUNNING) {
            throw new LifecycleError("Container is not running");
        }

        this.ready = true;
    }

    terminate(exitCode) {
        if (this.state !== ContainerState.RUNNING) {
            throw new LifecycleError("Container is not running");
        }

        if (!Number.isInteger(exitCode) || exitCode < 0) {
            throw new ValidationError("Invalid exit code");
        }

        this.state = ContainerState.TERMINATED;
        this.exitCode = exitCode;
        this.ready = false;
    }
}

class WorkerNode {
    constructor(name, cpuCapacity, memoryCapacity) {
        validateName(name, "node name");
        requirePositiveInteger(cpuCapacity, "CPU capacity");
        requirePositiveInteger(memoryCapacity, "Memory capacity");

        this.name = name;
        this.cpuCapacity = cpuCapacity;
        this.memoryCapacity = memoryCapacity;
        this.allocatedCPU = 0;
        this.allocatedMemory = 0;
        this.podIds = new Set();
    }

    canFit(cpu, memory) {
        return (
            this.allocatedCPU + cpu <= this.cpuCapacity &&
            this.allocatedMemory + memory <= this.memoryCapacity
        );
    }

    allocate(podId, cpu, memory) {
        if (!this.canFit(cpu, memory)) {
            throw new SchedulingError("Insufficient node capacity");
        }

        if (this.podIds.has(podId)) {
            throw new SchedulingError("Pod already allocated");
        }

        this.allocatedCPU += cpu;
        this.allocatedMemory += memory;
        this.podIds.add(podId);
    }

    release(podId, cpu, memory) {
        if (!this.podIds.has(podId)) return;

        this.allocatedCPU -= cpu;
        this.allocatedMemory -= memory;
        this.podIds.delete(podId);
    }
}

class Pod extends EventEmitter {
    constructor({
        name,
        namespace = "default",
        containers,
        initContainers = [],
        restartPolicy = RestartPolicy.ALWAYS,
        volumes = [],
        gracePeriodSeconds = 30,
        labels = {}
    }) {
        super();

        validateName(name, "Pod name");
        validateName(namespace, "namespace");

        if (!Array.isArray(containers) || containers.length === 0) {
            throw new ValidationError("Pod needs application containers");
        }

        if (!Object.values(RestartPolicy).includes(restartPolicy)) {
            throw new ValidationError("Invalid restart policy");
        }

        if (
            !Number.isInteger(gracePeriodSeconds) ||
            gracePeriodSeconds < 0
        ) {
            throw new ValidationError("Invalid termination grace period");
        }

        const all = [...initContainers, ...containers];

        if (all.some(c => !(c instanceof ContainerDefinition))) {
            throw new ValidationError("Invalid container definition");
        }

        const names = all.map(c => c.name);

        if (new Set(names).size !== names.length) {
            throw new ValidationError("Container names must be unique");
        }

        this.id = crypto.randomUUID();
        this.name = name;
        this.namespace = namespace;
        this.phase = PodPhase.PENDING;
        this.restartPolicy = restartPolicy;
        this.containers = containers.map(c => new ContainerRuntime(c));
        this.initContainers = initContainers.map(
            c => new ContainerRuntime(c)
        );
        this.volumes = new Set(volumes);
        this.labels = Object.freeze({ ...labels });
        this.gracePeriodSeconds = gracePeriodSeconds;
        this.node = null;
        this.deleting = false;
        this.createdAt = new Date();
        this.terminationTimer = null;
    }

    get resourceUsage() {
        return [...this.initContainers, ...this.containers].reduce(
            (total, runtime) => ({
                cpu: total.cpu + runtime.definition.resources.cpuMillicores,
                memory: total.memory +
                    runtime.definition.resources.memoryMiB
            }),
            { cpu: 0, memory: 0 }
        );
    }

    get ready() {
        return (
            this.phase === PodPhase.RUNNING &&
            this.containers.length > 0 &&
            this.containers.every(c =>
                c.state === ContainerState.RUNNING && c.ready
            )
        );
    }

    publish(type, details = {}) {
        const event = Object.freeze({
            podId: this.id,
            name: this.name,
            namespace: this.namespace,
            type,
            timestamp: new Date().toISOString(),
            ...details
        });

        this.emit("podEvent", event);
    }

    getContainer(name) {
        const runtime = this.containers.find(
            c => c.definition.name === name
        );

        if (!runtime) {
            throw new LifecycleError(`Unknown container: ${name}`);
        }

        return runtime;
    }
}

class PodController extends EventEmitter {
    constructor(nodes) {
        super();

        if (!Array.isArray(nodes) || nodes.length === 0) {
            throw new ValidationError("At least one node is required");
        }

        this.nodes = nodes;
        this.pods = new Map();
    }

    register(pod) {
        if (!(pod instanceof Pod)) {
            throw new ValidationError("Expected Pod instance");
        }

        const key = `${pod.namespace}/${pod.name}`;

        if (this.pods.has(key)) {
            throw new LifecycleError(`Duplicate Pod: ${key}`);
        }

        this.pods.set(key, pod);

        pod.on("podEvent", event => this.emit("event", event));
        pod.publish("PodCreated");

        return pod;
    }

    schedule(pod) {
        if (pod.phase !== PodPhase.PENDING || pod.node) {
            throw new LifecycleError("Pod is not schedulable");
        }

        const usage = pod.resourceUsage;

        const node = this.nodes.find(n =>
            n.canFit(usage.cpu, usage.memory)
        );

        if (!node) {
            pod.publish("SchedulingFailed", {
                reason: "Insufficient CPU or memory"
            });
            return false;
        }

        node.allocate(pod.id, usage.cpu, usage.memory);
        pod.node = node;
        pod.publish("PodScheduled", { node: node.name });

        return true;
    }

    async initialize(pod) {
        if (!pod.node || pod.phase !== PodPhase.PENDING) {
            throw new LifecycleError("Pod must be scheduled first");
        }

        // Init containers run sequentially, not alongside application containers.
        for (const runtime of pod.initContainers) {
            runtime.start();
            pod.publish("InitContainerStarted", {
                container: runtime.definition.name
            });

            runtime.markReady();
            runtime.terminate(0);

            pod.publish("InitContainerCompleted", {
                container: runtime.definition.name
            });
        }

        for (const runtime of pod.containers) {
            runtime.start();

            pod.publish("ContainerStarted", {
                container: runtime.definition.name
            });
        }

        pod.phase = PodPhase.RUNNING;
        pod.publish("PodRunning");
        return pod;
    }

    setReady(pod, containerName, ready) {
        const runtime = pod.getContainer(containerName);

        if (ready) {
            runtime.markReady();
        } else {
            if (runtime.state !== ContainerState.RUNNING) {
                throw new LifecycleError("Container is not running");
            }
            runtime.ready = false;
        }

        pod.publish("ReadinessChanged", {
            container: containerName,
            ready,
            podReady: pod.ready
        });
    }

    terminateContainer(pod, containerName, exitCode) {
        const runtime = pod.getContainer(containerName);
        runtime.terminate(exitCode);

        pod.publish("ContainerTerminated", {
            container: containerName,
            exitCode
        });

        const restart = (
            pod.restartPolicy === RestartPolicy.ALWAYS ||
            (
                pod.restartPolicy === RestartPolicy.ON_FAILURE &&
                exitCode !== 0
            )
        );

        if (restart && !pod.deleting) {
            runtime.restartCount++;
            runtime.start();

            pod.publish("ContainerRestarted", {
                container: containerName,
                restartCount: runtime.restartCount
            });

            return true;
        }

        if (exitCode !== 0 && runtime.definition.essential) {
            pod.phase = PodPhase.FAILED;
            pod.publish("PodFailed", {
                reason: "Essential container terminated unsuccessfully"
            });
            this.release(pod);
            return false;
        }

        const allTerminated = pod.containers.every(
            c => c.state === ContainerState.TERMINATED
        );

        if (allTerminated) {
            pod.phase = PodPhase.SUCCEEDED;
            pod.publish("PodSucceeded");
            this.release(pod);
        }

        return false;
    }

    release(pod) {
        if (!pod.node) return;

        const usage = pod.resourceUsage;

        pod.node.release(pod.id, usage.cpu, usage.memory);
        pod.node = null;
    }

    async delete(pod) {
        if (pod.deleting) return;

        pod.deleting = true;
        pod.publish("DeletionRequested", {
            gracePeriodSeconds: pod.gracePeriodSeconds
        });

        for (const runtime of pod.containers) {
            runtime.ready = false;
        }

        // Simulates the grace-period boundary without blocking the event loop.
        await new Promise(resolve => {
            pod.terminationTimer = setTimeout(
                resolve,
                Math.min(pod.gracePeriodSeconds * 1000, 100)
            );
        });

        for (const runtime of pod.containers) {
            if (runtime.state === ContainerState.RUNNING) {
                runtime.terminate(143);
            }
        }

        pod.phase = PodPhase.SUCCEEDED;
        this.release(pod);

        this.pods.delete(`${pod.namespace}/${pod.name}`);

        pod.publish("PodDeleted");
    }

    snapshot() {
        return {
            pods: [...this.pods.values()].map(pod => ({
                id: pod.id,
                name: pod.name,
                namespace: pod.namespace,
                phase: pod.phase,
                ready: pod.ready,
                node: pod.node?.name ?? null,
                containers: pod.containers.map(runtime => ({
                    name: runtime.definition.name,
                    state: runtime.state,
                    ready: runtime.ready,
                    restartCount: runtime.restartCount
                }))
            })),
            nodes: this.nodes.map(node => ({
                name: node.name,
                allocatedCPU: node.allocatedCPU,
                allocatedMemory: node.allocatedMemory
            }))
        };
    }
}

async function main() {
    const controller = new PodController([
        new WorkerNode("worker-a", 2000, 4096),
        new WorkerNode("worker-b", 1000, 2048)
    ]);

    controller.on("event", event => {
        console.log(
            `[${event.type}] ${event.namespace}/${event.name}`,
            JSON.stringify(event)
        );
    });

    const pod = new Pod({
        name: "orders-api",
        namespace: "production",
        restartPolicy: RestartPolicy.ALWAYS,
        containers: [
            new ContainerDefinition({
                name: "api",
                image: "node:22-alpine",
                resources: new ResourceRequest(300, 256),
                ports: [8080]
            }),
            new ContainerDefinition({
                name: "metrics",
                image: "prom/node-exporter:v1.8.2",
                resources: new ResourceRequest(100, 128),
                ports: [9100]
            })
        ],
        initContainers: [
            new ContainerDefinition({
                name: "schema-check",
                image: "busybox:1.36",
                resources: new ResourceRequest(50, 64),
                command: ["sh", "-c", "echo checking schema"]
            })
        ],
        volumes: ["shared-logs"],
        labels: {
            app: "orders-api",
            tier: "backend"
        }
    });

    controller.register(pod);

    if (!controller.schedule(pod)) {
        throw new SchedulingError("Unable to schedule application Pod");
    }

    await controller.initialize(pod);

    controller.setReady(pod, "api", true);
    controller.setReady(pod, "metrics", true);

    console.log("\nInitial snapshot:");
    console.log(JSON.stringify(controller.snapshot(), null, 2));

    controller.setReady(pod, "metrics", false);

    console.log("\nReadiness after sidecar failure:", pod.ready);

    controller.setReady(pod, "metrics", true);

    controller.terminateContainer(pod, "api", 1);

    console.log(
        "\nRestart count:",
        pod.getContainer("api").restartCount
    );

    console.log("\nFinal snapshot:");
    console.log(JSON.stringify(controller.snapshot(), null, 2));

    await controller.delete(pod);

    console.log("\nAfter deletion:");
    console.log(JSON.stringify(controller.snapshot(), null, 2));
}

main().catch(error => {
    console.error("Pod controller failure:", error.message);
    process.exitCode = 1;
});
