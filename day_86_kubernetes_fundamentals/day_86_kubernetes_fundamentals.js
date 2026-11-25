"use strict";

/**
 * Kubernetes Fundamentals: Event-Driven Control Plane
 *
 * Models:
 * - Declarative resource specifications
 * - Event-driven reconciliation
 * - Cluster and node health
 * - Asynchronous scheduling
 * - Pod lifecycle management
 * - Deployment scaling
 * - Service endpoint discovery
 * - Admission policies
 * - Resource quota enforcement
 * - Rolling update coordination
 *
 * Runtime: Node.js 18+
 * Dependencies: None
 */

const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");


class KubernetesError extends Error {
    constructor(message, code = "KUBERNETES_ERROR") {
        super(message);
        this.name = "KubernetesError";
        this.code = code;
    }
}


const PodPhase = Object.freeze({
    PENDING: "Pending",
    RUNNING: "Running",
    FAILED: "Failed",
    TERMINATING: "Terminating"
});

const NodeCondition = Object.freeze({
    READY: "Ready",
    NOT_READY: "NotReady",
    DRAINING: "Draining"
});


function validateName(name, field) {
    if (
        typeof name !== "string" ||
        !/^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/.test(name) ||
        name.length > 63
    ) {
        throw new KubernetesError(
            `Invalid ${field}: ${name}`,
            "INVALID_NAME"
        );
    }
}


function validateResources(resources) {
    if (
        !Number.isSafeInteger(resources.cpuMillicores) ||
        !Number.isSafeInteger(resources.memoryMB) ||
        resources.cpuMillicores <= 0 ||
        resources.memoryMB <= 0
    ) {
        throw new KubernetesError(
            "CPU and memory requests must be positive integers.",
            "INVALID_RESOURCE_REQUEST"
        );
    }
}


function clone(value) {
    return structuredClone(value);
}


class ClusterNode {
    constructor({ name, cpuMillicores, memoryMB }) {
        validateName(name, "node name");

        validateResources({
            cpuMillicores,
            memoryMB
        });

        this.name = name;
        this.cpuCapacity = cpuMillicores;
        this.memoryCapacity = memoryMB;
        this.condition = NodeCondition.READY;
        this.pods = new Map();
    }

    get allocatedCPU() {
        return [...this.pods.values()]
            .filter(pod =>
                pod.phase === PodPhase.RUNNING ||
                pod.phase === PodPhase.PENDING
            )
            .reduce(
                (total, pod) => total + pod.resources.cpuMillicores,
                0
            );
    }

    get allocatedMemory() {
        return [...this.pods.values()]
            .filter(pod =>
                pod.phase === PodPhase.RUNNING ||
                pod.phase === PodPhase.PENDING
            )
            .reduce(
                (total, pod) => total + pod.resources.memoryMB,
                0
            );
    }

    canHost(pod) {
        return (
            this.condition === NodeCondition.READY &&
            this.allocatedCPU + pod.resources.cpuMillicores
                <= this.cpuCapacity &&
            this.allocatedMemory + pod.resources.memoryMB
                <= this.memoryCapacity
        );
    }

    utilization() {
        return this.allocatedCPU / this.cpuCapacity;
    }
}


class AdmissionController {
    constructor({ maxPods, maxCPU, maxMemoryMB }) {
        this.limits = {
            maxPods,
            maxCPU,
            maxMemoryMB
        };

        this.policies = new Map();
    }

    registerPolicy(name, policy) {
        if (typeof policy !== "function") {
            throw new KubernetesError(
                "Admission policy must be a function."
            );
        }

        this.policies.set(name, policy);
    }

    async admit(pod, cluster) {
        const currentPods = cluster.countActivePods();

        if (currentPods >= this.limits.maxPods) {
            throw new KubernetesError(
                "Cluster pod quota exceeded.",
                "POD_QUOTA_EXCEEDED"
            );
        }

        const clusterCPU = cluster.nodes.reduce(
            (sum, node) => sum + node.cpuCapacity,
            0
        );

        if (pod.resources.cpuMillicores > clusterCPU) {
            throw new KubernetesError(
                "Pod CPU request exceeds total cluster capacity."
            );
        }

        for (const [name, policy] of this.policies) {
            const result = await policy(
                clone(pod),
                cluster
            );

            if (result !== true) {
                throw new KubernetesError(
                    `Admission rejected by policy: ${name}`,
                    "ADMISSION_DENIED"
                );
            }
        }

        return true;
    }
}


class KubernetesCluster extends EventEmitter {
    constructor(name, admissionController) {
        super();

        validateName(name, "cluster name");

        this.name = name;
        this.admission = admissionController;
        this.nodes = [];
        this.deployments = new Map();
        this.services = new Map();
        this.operations = new Map();
        this.eventSequence = 0;
    }

    emitAudit(type, details = {}) {
        this.emit("audit", Object.freeze({
            sequence: ++this.eventSequence,
            timestamp: new Date().toISOString(),
            type,
            details: clone(details)
        }));
    }

    addNode(node) {
        if (this.nodes.some(item => item.name === node.name)) {
            throw new KubernetesError("Duplicate node.");
        }

        this.nodes.push(node);
        this.emitAudit("NODE_ADDED", {
            node: node.name
        });
    }

    countActivePods() {
        return this.nodes.reduce(
            (sum, node) => sum + node.pods.size,
            0
        );
    }

    createDeployment(spec) {
        validateName(spec.name, "deployment name");
        validateResources(spec.resources);

        if (
            !Number.isInteger(spec.replicas) ||
            spec.replicas < 0
        ) {
            throw new KubernetesError("Invalid replica count.");
        }

        if (
            typeof spec.image !== "string" ||
            !spec.image.includes(":")
        ) {
            throw new KubernetesError(
                "Container image must specify a tag."
            );
        }

        if (this.deployments.has(spec.name)) {
            throw new KubernetesError("Deployment already exists.");
        }

        const deployment = {
            name: spec.name,
            image: spec.image,
            replicas: spec.replicas,
            selector: Object.freeze({ ...spec.selector }),
            resources: Object.freeze({ ...spec.resources }),
            generation: 1,
            pods: new Map(),
            revision: 1
        };

        if (Object.keys(deployment.selector).length === 0) {
            throw new KubernetesError(
                "Deployment selector cannot be empty."
            );
        }

        this.deployments.set(spec.name, deployment);

        this.emitAudit("DEPLOYMENT_CREATED", {
            name: spec.name,
            replicas: spec.replicas
        });

        return deployment;
    }

    createService(spec) {
        validateName(spec.name, "service name");

        if (
            !Number.isInteger(spec.port) ||
            !Number.isInteger(spec.targetPort) ||
            spec.port < 1 ||
            spec.port > 65535 ||
            spec.targetPort < 1 ||
            spec.targetPort > 65535
        ) {
            throw new KubernetesError("Invalid service ports.");
        }

        if (this.services.has(spec.name)) {
            throw new KubernetesError("Service already exists.");
        }

        const service = Object.freeze({
            name: spec.name,
            selector: Object.freeze({ ...spec.selector }),
            port: spec.port,
            targetPort: spec.targetPort
        });

        this.services.set(spec.name, service);

        this.emitAudit("SERVICE_CREATED", {
            name: spec.name
        });

        return service;
    }

    matchesSelector(pod, selector) {
        return Object.entries(selector).every(
            ([key, value]) => pod.labels[key] === value
        );
    }

    async schedule(pod) {
        await this.admission.admit(pod, this);

        const candidates = this.nodes
            .filter(node => node.canHost(pod))
            .sort((a, b) => {
                const utilizationDifference =
                    a.utilization() - b.utilization();

                return utilizationDifference ||
                    a.name.localeCompare(b.name);
            });

        if (candidates.length === 0) {
            throw new KubernetesError(
                `No feasible node for ${pod.name}`,
                "UNSCHEDULABLE"
            );
        }

        const node = candidates[0];

        node.pods.set(pod.id, pod);
        pod.nodeName = node.name;
        pod.phase = PodPhase.RUNNING;
        pod.ready = true;

        this.emitAudit("POD_SCHEDULED", {
            pod: pod.name,
            node: node.name
        });

        return node;
    }

    createPod(deployment, index) {
        return {
            id: crypto.randomUUID(),
            name: `${deployment.name}-${deployment.generation}-${index}`,
            image: deployment.image,
            resources: { ...deployment.resources },
            labels: { ...deployment.selector },
            phase: PodPhase.PENDING,
            nodeName: null,
            ready: false,
            restartCount: 0,
            revision: deployment.revision
        };
    }

    async reconcileDeployment(name) {
        const deployment = this.deployments.get(name);

        if (!deployment) {
            throw new KubernetesError("Deployment not found.");
        }

        const active = [...deployment.pods.values()].filter(
            pod => pod.phase === PodPhase.RUNNING ||
                pod.phase === PodPhase.PENDING
        );

        const missing = Math.max(
            0,
            deployment.replicas - active.length
        );

        const created = [];

        for (let i = 0; i < missing; i++) {
            const pod = this.createPod(
                deployment,
                deployment.pods.size + 1
            );

            try {
                await this.schedule(pod);
                deployment.pods.set(pod.id, pod);
                created.push(pod);
            } catch (error) {
                this.emitAudit("SCHEDULING_FAILED", {
                    pod: pod.name,
                    reason: error.message
                });
                break;
            }
        }

        const excess = Math.max(
            0,
            active.length - deployment.replicas
        );

        for (const pod of active.slice(0, excess)) {
            this.deletePod(deployment, pod);
        }

        this.emitAudit("RECONCILIATION_COMPLETED", {
            deployment: name,
            desired: deployment.replicas,
            active: [...deployment.pods.values()].filter(
                pod => pod.phase === PodPhase.RUNNING
            ).length
        });

        return created;
    }

    deletePod(deployment, pod) {
        pod.phase = PodPhase.TERMINATING;
        pod.ready = false;

        const node = this.nodes.find(
            item => item.name === pod.nodeName
        );

        if (node) {
            node.pods.delete(pod.id);
        }

        pod.phase = PodPhase.FAILED;
        deployment.pods.delete(pod.id);

        this.emitAudit("POD_DELETED", {
            pod: pod.name
        });
    }

    async scale(name, replicas) {
        if (!Number.isInteger(replicas) || replicas < 0) {
            throw new KubernetesError("Invalid replica count.");
        }

        const deployment = this.deployments.get(name);

        if (!deployment) {
            throw new KubernetesError("Deployment not found.");
        }

        deployment.replicas = replicas;
        deployment.generation++;

        this.emitAudit("DEPLOYMENT_SCALED", {
            name,
            replicas
        });

        return this.reconcileDeployment(name);
    }

    async rollingUpdate(name, newImage) {
        const deployment = this.deployments.get(name);

        if (!deployment) {
            throw new KubernetesError("Deployment not found.");
        }

        if (
            typeof newImage !== "string" ||
            !newImage.includes(":")
        ) {
            throw new KubernetesError("Invalid image reference.");
        }

        const oldImage = deployment.image;
        const oldRevision = deployment.revision;

        deployment.image = newImage;
        deployment.revision++;
        deployment.generation++;

        const previousPods = [...deployment.pods.values()]
            .filter(pod => pod.phase === PodPhase.RUNNING);

        const replacements = [];

        try {
            for (let i = 0; i < previousPods.length; i++) {
                const replacement = this.createPod(
                    deployment,
                    deployment.pods.size + 1
                );

                await this.schedule(replacement);

                deployment.pods.set(
                    replacement.id,
                    replacement
                );

                replacements.push(replacement);

                this.deletePod(deployment, previousPods[i]);
            }

            this.emitAudit("ROLLING_UPDATE_COMPLETED", {
                name,
                revision: deployment.revision
            });

            return true;

        } catch (error) {
            // Remove newly created replicas and restore the previous
            // workload specification.
            for (const pod of replacements) {
                this.deletePod(deployment, pod);
            }

            deployment.image = oldImage;
            deployment.revision = oldRevision;
            deployment.generation--;

            this.emitAudit("ROLLING_UPDATE_FAILED", {
                name,
                reason: error.message
            });

            return false;
        }
    }

    async failPod(deploymentName, podId) {
        const deployment = this.deployments.get(deploymentName);
        const pod = deployment?.pods.get(podId);

        if (!pod) {
            throw new KubernetesError("Pod not found.");
        }

        const node = this.nodes.find(
            item => item.name === pod.nodeName
        );

        if (node) {
            node.pods.delete(pod.id);
        }

        pod.phase = PodPhase.FAILED;
        pod.ready = false;
        pod.nodeName = null;
        pod.restartCount++;

        this.emitAudit("POD_FAILED", {
            pod: pod.name,
            restartCount: pod.restartCount
        });

        return this.reconcileDeployment(deploymentName);
    }

    serviceEndpoints(serviceName) {
        const service = this.services.get(serviceName);

        if (!service) {
            throw new KubernetesError("Service not found.");
        }

        const endpoints = [];

        for (const node of this.nodes) {
            for (const pod of node.pods.values()) {
                if (
                    pod.phase === PodPhase.RUNNING &&
                    pod.ready &&
                    this.matchesSelector(pod, service.selector)
                ) {
                    endpoints.push({
                        pod: pod.name,
                        node: node.name,
                        targetPort: service.targetPort
                    });
                }
            }
        }

        return endpoints;
    }

    async drainNode(name) {
        const node = this.nodes.find(item => item.name === name);

        if (!node) {
            throw new KubernetesError("Node not found.");
        }

        node.condition = NodeCondition.DRAINING;

        for (const pod of [...node.pods.values()]) {
            const deployment = [...this.deployments.values()]
                .find(item => item.pods.has(pod.id));

            if (deployment) {
                this.deletePod(deployment, pod);
                await this.reconcileDeployment(deployment.name);
            }
        }

        this.emitAudit("NODE_DRAINED", { name });
    }

    snapshot() {
        return {
            cluster: this.name,
            nodes: this.nodes.map(node => ({
                name: node.name,
                condition: node.condition,
                cpuAllocated: node.allocatedCPU,
                memoryAllocated: node.allocatedMemory,
                pods: node.pods.size
            })),
            deployments: [...this.deployments.values()].map(d => ({
                name: d.name,
                image: d.image,
                desired: d.replicas,
                actual: [...d.pods.values()].filter(
                    p => p.phase === PodPhase.RUNNING
                ).length,
                generation: d.generation
            })),
            endpoints: Object.fromEntries(
                [...this.services.keys()].map(name => [
                    name,
                    this.serviceEndpoints(name)
                ])
            )
        };
    }
}


async function main() {
    const admission = new AdmissionController({
        maxPods: 30,
        maxCPU: 10000,
        maxMemoryMB: 32768
    });

    admission.registerPolicy(
        "trusted-registry",
        async pod => pod.image.startsWith(
            "registry.example.com/"
        )
    );

    admission.registerPolicy(
        "minimum-memory",
        async pod => pod.resources.memoryMB >= 128
    );

    const cluster = new KubernetesCluster(
        "production-cluster",
        admission
    );

    cluster.on("audit", event => {
        console.log(
            `[${event.sequence}] ${event.type}`,
            event.details
        );
    });

    cluster.addNode(new ClusterNode({
        name: "worker-01",
        cpuMillicores: 4000,
        memoryMB: 8192
    }));

    cluster.addNode(new ClusterNode({
        name: "worker-02",
        cpuMillicores: 4000,
        memoryMB: 8192
    }));

    cluster.addNode(new ClusterNode({
        name: "worker-03",
        cpuMillicores: 2000,
        memoryMB: 4096
    }));

    cluster.createDeployment({
        name: "inventory-api",
        image: "registry.example.com/inventory:v1",
        replicas: 3,
        selector: { app: "inventory-api" },
        resources: {
            cpuMillicores: 500,
            memoryMB: 512
        }
    });

    cluster.createService({
        name: "inventory-service",
        selector: { app: "inventory-api" },
        port: 80,
        targetPort: 8080
    });

    await cluster.reconcileDeployment("inventory-api");

    console.log("\nINITIAL STATE");
    console.log(JSON.stringify(cluster.snapshot(), null, 2));

    console.log("\nSCALING");
    await cluster.scale("inventory-api", 5);

    console.log("\nROLLING UPDATE");
    const updated = await cluster.rollingUpdate(
        "inventory-api",
        "registry.example.com/inventory:v2"
    );

    console.log("Update successful:", updated);

    console.log("\nSERVICE ENDPOINTS");
    console.log(cluster.serviceEndpoints("inventory-service"));

    console.log("\nFAILURE RECOVERY");

    const deployment = cluster.deployments.get("inventory-api");
    const firstPod = deployment.pods.values().next().value;

    await cluster.failPod("inventory-api", firstPod.id);

    console.log("\nFINAL STATE");
    console.log(JSON.stringify(cluster.snapshot(), null, 2));

    try {
        await cluster.admission.admit({
            name: "untrusted",
            image: "untrusted.io/malware:v1",
            resources: {
                cpuMillicores: 100,
                memoryMB: 256
            }
        }, cluster);
    } catch (error) {
        console.log("\nExpected admission rejection:", error.message);
    }

    // Atomic file replacement prevents partially written audit exports.
    const auditFile = "kubernetes-audit.json";
    const temporaryFile = `${auditFile}.${process.pid}.tmp`;

    try {
        const events = [];
        // The event stream is exported from a separate audit subscriber
        // in production. This file records the final cluster snapshot.
        events.push(cluster.snapshot());

        await fs.writeFile(
            temporaryFile,
            JSON.stringify(events, null, 2),
            { encoding: "utf8", mode: 0o600 }
        );

        await fs.rename(temporaryFile, auditFile);
        console.log("\nAudit snapshot exported:", auditFile);

    } catch (error) {
        console.error("Audit export failed:", error.message);

        await fs.rm(temporaryFile, { force: true }).catch(() => {});
        throw error;
    }
}


main().catch(error => {
    console.error("Cluster execution failed:", error);
    process.exitCode = 1;
});
