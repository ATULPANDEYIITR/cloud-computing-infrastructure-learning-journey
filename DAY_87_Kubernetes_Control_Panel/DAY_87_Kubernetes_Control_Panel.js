"use strict";

/*
 * Kubernetes Control Plane
 *
 * Event-driven simulation of:
 * - API server request processing
 * - Versioned cluster-state storage
 * - Scheduler decisions
 * - Deployment reconciliation
 * - Controller events
 * - Node resource allocation
 * - Asynchronous operations
 * - Optimistic concurrency
 *
 * Runtime: Node.js 18+
 * Dependencies: None
 */

const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");


class ControlPlaneError extends Error {}
class ValidationError extends ControlPlaneError {}
class NotFoundError extends ControlPlaneError {}
class ConflictError extends ControlPlaneError {}
class SchedulingError extends ControlPlaneError {}


const PodPhase = Object.freeze({
    PENDING: "Pending",
    RUNNING: "Running",
    FAILED: "Failed",
    SUCCEEDED: "Succeeded"
});

const NodeCondition = Object.freeze({
    READY: "Ready",
    NOT_READY: "NotReady"
});


function validateName(name) {
    if (
        typeof name !== "string" ||
        !/^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/.test(name) ||
        name.length > 253
    ) {
        throw new ValidationError(`Invalid resource name: ${name}`);
    }
}


function clone(value) {
    return structuredClone(value);
}


// ============================================================
// VERSIONED CLUSTER STATE
// ============================================================

class EtcdStore extends EventEmitter {

    #records = new Map();
    #revision = 0;

    get revision() {
        return this.#revision;
    }

    get(key) {
        const record = this.#records.get(key);

        if (!record) {
            throw new NotFoundError(`Missing key: ${key}`);
        }

        return clone(record);
    }

    list(prefix) {
        const results = [];

        for (const [key, value] of this.#records.entries()) {
            if (key.startsWith(prefix)) {
                results.push(clone(value));
            }
        }

        return results;
    }

    put(key, object, expectedVersion = null) {

        const existing = this.#records.get(key);
        const currentVersion = existing?.resourceVersion ?? 0;

        if (
            expectedVersion !== null &&
            currentVersion !== expectedVersion
        ) {
            throw new ConflictError(
                `Expected version ${expectedVersion}, ` +
                `found ${currentVersion}`
            );
        }

        const saved = {
            ...clone(object),
            resourceVersion: ++this.#revision
        };

        this.#records.set(key, saved);

        this.emit("modified", {
            key,
            revision: this.#revision,
            object: clone(saved)
        });

        return clone(saved);
    }

    delete(key, expectedVersion = null) {

        const existing = this.#records.get(key);

        if (!existing) {
            throw new NotFoundError(key);
        }

        if (
            expectedVersion !== null &&
            existing.resourceVersion !== expectedVersion
        ) {
            throw new ConflictError("Delete version mismatch");
        }

        this.#records.delete(key);
        this.#revision++;

        this.emit("deleted", {
            key,
            revision: this.#revision
        });
    }
}


// ============================================================
// API SERVER
// ============================================================

class APIServer {

    constructor(store) {
        this.store = store;
        this.audit = [];
    }

    key(kind, namespace, name) {
        return `/registry/${kind}/${namespace}/${name}`;
    }

    create(kind, object) {

        validateName(object.name);
        validateName(object.namespace);

        const key = this.key(
            kind,
            object.namespace,
            object.name
        );

        const saved = this.store.put(key, object, 0);

        this.audit.push({
            action: "CREATE",
            key,
            revision: saved.resourceVersion,
            timestamp: new Date().toISOString()
        });

        return saved;
    }

    update(kind, object, expectedVersion) {

        const key = this.key(
            kind,
            object.namespace,
            object.name
        );

        const saved = this.store.put(
            key,
            object,
            expectedVersion
        );

        this.audit.push({
            action: "UPDATE",
            key,
            revision: saved.resourceVersion,
            timestamp: new Date().toISOString()
        });

        return saved;
    }

    get(kind, namespace, name) {
        return this.store.get(
            this.key(kind, namespace, name)
        );
    }

    list(kind) {
        return this.store.list(`/registry/${kind}/`);
    }
}


// ============================================================
// RESOURCE FACTORIES
// ============================================================

function createNode(name, cpu, memory) {

    validateName(name);

    if (
        !Number.isInteger(cpu) ||
        !Number.isInteger(memory) ||
        cpu <= 0 ||
        memory <= 0
    ) {
        throw new ValidationError("Invalid node capacity");
    }

    return {
        name,
        namespace: "default",
        uid: crypto.randomUUID(),
        condition: NodeCondition.READY,
        capacity: { cpu, memory },
        allocatable: { cpu, memory },
        used: { cpu: 0, memory: 0 }
    };
}


function createDeployment({
    name,
    replicas,
    image,
    selector,
    cpu = 1,
    memory = 256
}) {

    validateName(name);

    if (
        !Number.isInteger(replicas) ||
        replicas < 0 ||
        replicas > 10000
    ) {
        throw new ValidationError("Invalid replica count");
    }

    if (
        !image ||
        !selector ||
        Object.keys(selector).length === 0
    ) {
        throw new ValidationError(
            "Image and nonempty selector are required"
        );
    }

    if (
        !Number.isInteger(cpu) ||
        !Number.isInteger(memory) ||
        cpu <= 0 ||
        memory <= 0
    ) {
        throw new ValidationError("Invalid resource requests");
    }

    return {
        name,
        namespace: "default",
        uid: crypto.randomUUID(),
        generation: 1,
        replicas,
        image,
        selector: clone(selector),
        resources: { cpu, memory }
    };
}


function createPod(deployment, index) {

    return {
        name: `${deployment.name}-${deployment.generation}-${index}`,
        namespace: deployment.namespace,
        uid: crypto.randomUUID(),
        owner: deployment.uid,
        labels: clone(deployment.selector),
        image: deployment.image,
        resources: clone(deployment.resources),
        phase: PodPhase.PENDING,
        nodeName: null
    };
}


// ============================================================
// SCHEDULER
// ============================================================

class Scheduler {

    constructor(api) {
        this.api = api;
        this.events = [];
    }

    async schedule(pod) {

        const candidates = this.api.list("node")
            .filter(node =>
                node.condition === NodeCondition.READY &&
                node.allocatable.cpu - node.used.cpu >=
                    pod.resources.cpu &&
                node.allocatable.memory - node.used.memory >=
                    pod.resources.memory
            )
            .sort((a, b) => {
                const scoreA =
                    a.allocatable.cpu - a.used.cpu;
                const scoreB =
                    b.allocatable.cpu - b.used.cpu;

                return scoreB - scoreA;
            });

        if (candidates.length === 0) {
            this.events.push({
                pod: pod.name,
                result: "Unschedulable"
            });

            return false;
        }

        const node = candidates[0];

        // Allocation is committed with optimistic concurrency.
        const updatedNode = {
            ...node,
            used: {
                cpu: node.used.cpu + pod.resources.cpu,
                memory: node.used.memory + pod.resources.memory
            }
        };

        this.api.update(
            "node",
            updatedNode,
            node.resourceVersion
        );

        const updatedPod = {
            ...pod,
            nodeName: node.name,
            phase: PodPhase.RUNNING
        };

        this.api.update(
            "pod",
            updatedPod,
            pod.resourceVersion
        );

        this.events.push({
            pod: pod.name,
            result: `Scheduled on ${node.name}`
        });

        return true;
    }
}


// ============================================================
// DEPLOYMENT CONTROLLER
// ============================================================

class DeploymentController extends EventEmitter {

    constructor(api) {
        super();
        this.api = api;
        this.reconciliationCount = 0;
    }

    matches(pod, deployment) {
        return Object.entries(deployment.selector)
            .every(([key, value]) => pod.labels[key] === value);
    }

    async reconcile(deployment) {

        this.reconciliationCount++;

        const ownedPods = this.api.list("pod")
            .filter(pod =>
                pod.owner === deployment.uid &&
                this.matches(pod, deployment)
            );

        const runningPods = ownedPods.filter(
            pod => pod.phase === PodPhase.RUNNING
        );

        const missing = Math.max(
            0,
            deployment.replicas - runningPods.length
        );

        const excess = Math.max(
            0,
            ownedPods.length - deployment.replicas
        );

        let created = 0;
        let removed = 0;

        for (let i = 0; i < excess; i++) {

            const pod = ownedPods[i];

            if (pod.nodeName) {
                this.releaseResources(pod);
            }

            this.api.store.delete(
                this.api.key(
                    "pod",
                    pod.namespace,
                    pod.name
                ),
                pod.resourceVersion
            );

            removed++;
        }

        for (let i = 0; i < missing; i++) {

            const pod = createPod(
                deployment,
                this.reconciliationCount * 100 + i
            );

            this.api.create("pod", pod);
            created++;
        }

        const result = {
            desired: deployment.replicas,
            running: runningPods.length,
            created,
            removed
        };

        this.emit("reconciled", {
            deployment: deployment.name,
            ...result
        });

        return result;
    }

    releaseResources(pod) {

        const node = this.api.get(
            "node",
            "default",
            pod.nodeName
        );

        const updated = {
            ...node,
            used: {
                cpu: Math.max(
                    0,
                    node.used.cpu - pod.resources.cpu
                ),
                memory: Math.max(
                    0,
                    node.used.memory - pod.resources.memory
                )
            }
        };

        this.api.update(
            "node",
            updated,
            node.resourceVersion
        );
    }
}


// ============================================================
// CONTROL PLANE ORCHESTRATOR
// ============================================================

class KubernetesControlPlane extends EventEmitter {

    constructor() {
        super();

        this.store = new EtcdStore();
        this.api = new APIServer(this.store);
        this.scheduler = new Scheduler(this.api);
        this.controller = new DeploymentController(this.api);

        this.controller.on("reconciled", event => {
            this.emit("controller.reconciled", event);
        });

        this.store.on("modified", event => {
            this.emit("state.modified", event);
        });
    }

    addNode(name, cpu, memory) {
        return this.api.create(
            "node",
            createNode(name, cpu, memory)
        );
    }

    deploy(configuration) {

        const deployment = createDeployment(configuration);

        this.api.create("deployment", deployment);

        return deployment;
    }

    async reconcile() {

        const deployments = this.api.list("deployment");

        for (const deployment of deployments) {
            await this.controller.reconcile(deployment);
        }

        // Re-read state because reconciliation creates new Pods.
        const pending = this.api.list("pod")
            .filter(pod =>
                pod.phase === PodPhase.PENDING &&
                pod.nodeName === null
            );

        for (const pod of pending) {
            try {
                await this.scheduler.schedule(pod);
            } catch (error) {
                if (error instanceof ConflictError) {
                    this.emit("scheduling.conflict", {
                        pod: pod.name,
                        message: error.message
                    });
                } else {
                    throw error;
                }
            }
        }
    }

    snapshot() {

        return {
            revision: this.store.revision,
            nodes: this.api.list("node"),
            deployments: this.api.list("deployment"),
            pods: this.api.list("pod"),
            auditEvents: this.api.audit.length
        };
    }
}


// ============================================================
// DEMONSTRATION
// ============================================================

async function main() {

    const cluster = new KubernetesControlPlane();

    cluster.on("controller.reconciled", event => {
        console.log("CONTROLLER:", event);
    });

    cluster.on("scheduling.conflict", event => {
        console.log("CONFLICT:", event);
    });

    cluster.addNode("worker-01", 8, 16384);
    cluster.addNode("worker-02", 4, 8192);

    cluster.deploy({
        name: "payment-api",
        replicas: 4,
        image: "payment-api:2.1",
        selector: { app: "payment" },
        cpu: 1,
        memory: 512
    });

    await cluster.reconcile();

    // A second cycle demonstrates reconciliation stability.
    await cluster.reconcile();

    console.log("\nCLUSTER STATE");
    console.log(JSON.stringify(cluster.snapshot(), null, 2));

    console.log("\nSCHEDULING EVENTS");
    console.log(JSON.stringify(cluster.scheduler.events, null, 2));

    // Demonstrate stale resource-version rejection.
    const node = cluster.api.get(
        "node",
        "default",
        "worker-01"
    );

    try {
        cluster.api.update("node", node, 0);
    } catch (error) {
        console.log("\nEXPECTED FAILURE:", error.message);
    }

    // Demonstrate invalid configuration rejection.
    try {
        createDeployment({
            name: "invalid-app",
            replicas: -1,
            image: "nginx",
            selector: { app: "invalid" }
        });
    } catch (error) {
        console.log("\nVALIDATION FAILURE:", error.message);
    }
}


main().catch(error => {
    console.error("CONTROL PLANE FAILURE:", error);
    process.exitCode = 1;
});
