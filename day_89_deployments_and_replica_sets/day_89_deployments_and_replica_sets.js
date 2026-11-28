'use strict';

/**
 * Deployments and ReplicaSets
 *
 * Event-driven deployment controller and policy evaluator.
 * Runtime: Node.js 18+
 * Dependencies: Node.js standard library only.
 */

const { EventEmitter } = require('node:events');
const crypto = require('node:crypto');

const DeploymentPhase = Object.freeze({
    PROGRESSING: 'Progressing',
    AVAILABLE: 'Available',
    DEGRADED: 'Degraded',
    PAUSED: 'Paused'
});

const PodPhase = Object.freeze({
    PENDING: 'Pending',
    RUNNING: 'Running',
    READY: 'Ready',
    FAILED: 'Failed',
    TERMINATING: 'Terminating'
});

class DeploymentError extends Error {}
class ValidationError extends DeploymentError {}
class PolicyError extends DeploymentError {}

function assertInteger(value, name, min, max) {
    if (!Number.isInteger(value) || value < min || value > max) {
        throw new ValidationError(
            `${name} must be an integer between ${min} and ${max}`
        );
    }
}

function validateName(value, field) {
    if (
        typeof value !== 'string' ||
        !/^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/.test(value)
    ) {
        throw new ValidationError(`Invalid ${field}`);
    }
}

function validateImage(image) {
    if (
        typeof image !== 'string' ||
        image.length > 255 ||
        !/^[a-zA-Z0-9][a-zA-Z0-9._/:@-]*$/.test(image)
    ) {
        throw new ValidationError('Invalid image reference');
    }
}

class DeploymentSpec {
    constructor({
        name,
        namespace = 'default',
        replicas,
        image,
        port = 8080,
        maxSurge = 1,
        maxUnavailable = 0,
        revisionHistoryLimit = 5
    }) {
        validateName(name, 'deployment name');
        validateName(namespace, 'namespace');
        validateImage(image);

        assertInteger(replicas, 'replicas', 0, 10000);
        assertInteger(port, 'port', 1, 65535);
        assertInteger(maxSurge, 'maxSurge', 0, 1000);
        assertInteger(maxUnavailable, 'maxUnavailable', 0, replicas);
        assertInteger(revisionHistoryLimit, 'revisionHistoryLimit', 1, 100);

        this.name = name;
        this.namespace = namespace;
        this.replicas = replicas;
        this.image = image;
        this.port = port;
        this.maxSurge = maxSurge;
        this.maxUnavailable = maxUnavailable;
        this.revisionHistoryLimit = revisionHistoryLimit;

        Object.freeze(this);
    }
}

class Pod {
    constructor(replicaSetId, image) {
        this.id = crypto.randomUUID();
        this.replicaSetId = replicaSetId;
        this.image = image;
        this.phase = PodPhase.PENDING;
        this.createdAt = new Date();
        this.readyAt = null;
    }

    transition(next) {
        const allowed = {
            [PodPhase.PENDING]: [
                PodPhase.RUNNING,
                PodPhase.FAILED,
                PodPhase.TERMINATING
            ],
            [PodPhase.RUNNING]: [
                PodPhase.READY,
                PodPhase.FAILED,
                PodPhase.TERMINATING
            ],
            [PodPhase.READY]: [
                PodPhase.FAILED,
                PodPhase.TERMINATING
            ],
            [PodPhase.FAILED]: [],
            [PodPhase.TERMINATING]: []
        };

        if (!allowed[this.phase].includes(next)) {
            throw new DeploymentError(
                `Invalid Pod transition: ${this.phase} -> ${next}`
            );
        }

        this.phase = next;

        if (next === PodPhase.READY) {
            this.readyAt = new Date();
        }
    }
}

class ReplicaSet {
    constructor(deploymentName, revision, image) {
        this.id = crypto.randomUUID();
        this.deploymentName = deploymentName;
        this.revision = revision;
        this.image = image;
        this.pods = new Map();
        this.desiredReplicas = 0;
        this.createdAt = new Date();
    }

    get activeReplicas() {
        return [...this.pods.values()].filter(
            pod => [
                PodPhase.PENDING,
                PodPhase.RUNNING,
                PodPhase.READY
            ].includes(pod.phase)
        ).length;
    }

    get readyReplicas() {
        return [...this.pods.values()].filter(
            pod => pod.phase === PodPhase.READY
        ).length;
    }

    createPod() {
        const pod = new Pod(this.id, this.image);
        this.pods.set(pod.id, pod);
        return pod;
    }

    removePod(id) {
        const pod = this.pods.get(id);

        if (!pod) {
            throw new DeploymentError('Pod not found');
        }

        if (pod.phase !== PodPhase.TERMINATING) {
            pod.transition(PodPhase.TERMINATING);
        }

        this.pods.delete(id);
    }
}

class Deployment {
    constructor(spec) {
        this.spec = spec;
        this.revision = 0;
        this.phase = DeploymentPhase.PROGRESSING;
        this.paused = false;
        this.replicaSets = new Map();
        this.history = [];
        this.conditions = [];
    }

    get key() {
        return `${this.spec.namespace}/${this.spec.name}`;
    }

    get readyReplicas() {
        return [...this.replicaSets.values()].reduce(
            (total, rs) => total + rs.readyReplicas,
            0
        );
    }

    get totalReplicas() {
        return [...this.replicaSets.values()].reduce(
            (total, rs) => total + rs.activeReplicas,
            0
        );
    }

    get currentReplicaSet() {
        return [...this.replicaSets.values()].sort(
            (a, b) => b.revision - a.revision
        )[0] || null;
    }
}

class DeploymentController extends EventEmitter {
    constructor() {
        super();
        this.deployments = new Map();
        this.events = [];
        this.processing = new Set();
    }

    emitAudit(deployment, type, details = {}) {
        const event = Object.freeze({
            deployment: deployment.key,
            revision: deployment.revision,
            type,
            details,
            timestamp: new Date().toISOString()
        });

        this.events.push(event);
        this.emit('deployment-event', event);
    }

    createRevision(deployment, image) {
        deployment.revision++;

        const rs = new ReplicaSet(
            deployment.spec.name,
            deployment.revision,
            image
        );

        deployment.replicaSets.set(rs.id, rs);

        deployment.history.push({
            revision: rs.revision,
            image: rs.image,
            timestamp: rs.createdAt.toISOString()
        });

        if (
            deployment.history.length >
            deployment.spec.revisionHistoryLimit
        ) {
            deployment.history.splice(
                0,
                deployment.history.length -
                deployment.spec.revisionHistoryLimit
            );
        }

        this.emitAudit(deployment, 'REVISION_CREATED', {
            revision: rs.revision,
            image
        });

        return rs;
    }

    create(spec) {
        if (!(spec instanceof DeploymentSpec)) {
            throw new ValidationError('A validated DeploymentSpec is required');
        }

        const deployment = new Deployment(spec);

        if (this.deployments.has(deployment.key)) {
            throw new DeploymentError('Deployment already exists');
        }

        this.deployments.set(deployment.key, deployment);
        this.createRevision(deployment, spec.image);

        this.emitAudit(deployment, 'DEPLOYMENT_CREATED');
        this.reconcile(deployment);

        return deployment;
    }

    get(name, namespace = 'default') {
        const deployment = this.deployments.get(`${namespace}/${name}`);

        if (!deployment) {
            throw new DeploymentError('Deployment not found');
        }

        return deployment;
    }

    reconcile(deployment) {
        if (deployment.paused) {
            deployment.phase = DeploymentPhase.PAUSED;
            return;
        }

        if (this.processing.has(deployment.key)) {
            return;
        }

        this.processing.add(deployment.key);

        try {
            const spec = deployment.spec;
            const desired = spec.replicas;
            const current = deployment.currentReplicaSet;

            if (!current) {
                throw new DeploymentError('No ReplicaSet exists');
            }

            const sets = [...deployment.replicaSets.values()].sort(
                (a, b) => b.revision - a.revision
            );

            current.desiredReplicas = desired;

            for (const old of sets.slice(1)) {
                old.desiredReplicas = 0;
            }

            const total = deployment.totalReplicas;
            const surgeLimit = desired + spec.maxSurge;

            const scaleUp = Math.min(
                Math.max(0, desired - current.activeReplicas),
                Math.max(0, surgeLimit - total)
            );

            for (let i = 0; i < scaleUp; i++) {
                current.createPod();
            }

            if (scaleUp > 0) {
                this.emitAudit(deployment, 'SCALE_UP', {
                    replicaSet: current.id,
                    count: scaleUp
                });
            }

            const minimumAvailable = Math.max(
                0,
                desired - spec.maxUnavailable
            );

            for (const old of sets.slice(1)) {
                const candidates = [...old.pods.values()].sort(
                    (a, b) => {
                        if (a.phase === b.phase) return 0;
                        if (a.phase === PodPhase.PENDING) return -1;
                        if (b.phase === PodPhase.PENDING) return 1;
                        return 0;
                    }
                );

                for (const pod of candidates) {
                    if (old.activeReplicas <= 0) break;

                    if (
                        pod.phase === PodPhase.READY &&
                        deployment.readyReplicas - 1 < minimumAvailable
                    ) {
                        continue;
                    }

                    old.removePod(pod.id);
                    this.emitAudit(deployment, 'OLD_POD_REMOVED', {
                        podId: pod.id,
                        revision: old.revision
                    });
                }
            }

            this.updatePhase(deployment);
        } finally {
            this.processing.delete(deployment.key);
        }
    }

    updatePhase(deployment) {
        if (deployment.spec.replicas === 0) {
            deployment.phase = DeploymentPhase.AVAILABLE;
            return;
        }

        const current = deployment.currentReplicaSet;

        if (!current) {
            deployment.phase = DeploymentPhase.DEGRADED;
            return;
        }

        deployment.phase =
            deployment.readyReplicas >= deployment.spec.replicas
                ? DeploymentPhase.AVAILABLE
                : DeploymentPhase.PROGRESSING;
    }

    async update(name, namespace, changes) {
        const deployment = this.get(name, namespace);
        const old = deployment.spec;

        const next = new DeploymentSpec({
            name: old.name,
            namespace: old.namespace,
            replicas: changes.replicas ?? old.replicas,
            image: changes.image ?? old.image,
            port: old.port,
            maxSurge: changes.maxSurge ?? old.maxSurge,
            maxUnavailable:
                changes.maxUnavailable ?? old.maxUnavailable,
            revisionHistoryLimit: old.revisionHistoryLimit
        });

        const imageChanged = next.image !== old.image;

        deployment.spec = next;

        if (imageChanged) {
            this.createRevision(deployment, next.image);
        }

        this.emitAudit(
            deployment,
            imageChanged ? 'IMAGE_UPDATE' : 'REPLICA_UPDATE',
            { image: next.image, replicas: next.replicas }
        );

        this.reconcile(deployment);
        return deployment;
    }

    async completePendingPods(deployment, failedImages = new Set()) {
        for (const rs of deployment.replicaSets.values()) {
            for (const pod of [...rs.pods.values()]) {
                if (pod.phase !== PodPhase.PENDING) continue;

                if (failedImages.has(pod.image)) {
                    pod.transition(PodPhase.FAILED);
                    rs.pods.delete(pod.id);

                    this.emitAudit(deployment, 'POD_START_FAILED', {
                        podId: pod.id,
                        image: pod.image
                    });

                    continue;
                }

                pod.transition(PodPhase.RUNNING);
                pod.transition(PodPhase.READY);

                this.emitAudit(deployment, 'POD_READY', {
                    podId: pod.id,
                    image: pod.image
                });
            }
        }

        this.reconcile(deployment);
    }

    async rollout(name, namespace, image, maxIterations = 100) {
        let deployment = await this.update(
            name,
            namespace,
            { image }
        );

        for (let i = 0; i < maxIterations; i++) {
            await this.completePendingPods(deployment);

            const current = deployment.currentReplicaSet;
            const oldActive = [...deployment.replicaSets.values()]
                .filter(rs => rs.id !== current.id)
                .reduce((sum, rs) => sum + rs.activeReplicas, 0);

            if (
                current.readyReplicas === deployment.spec.replicas &&
                oldActive === 0
            ) {
                this.emitAudit(deployment, 'ROLLOUT_COMPLETED');
                return deployment;
            }

            this.reconcile(deployment);
        }

        deployment.phase = DeploymentPhase.DEGRADED;
        throw new DeploymentError('Rollout exceeded iteration limit');
    }

    async rollback(name, namespace, targetRevision) {
        const deployment = this.get(name, namespace);

        const candidates = [...deployment.replicaSets.values()]
            .filter(rs => rs.revision < deployment.revision)
            .filter(
                rs => targetRevision === undefined ||
                    rs.revision === targetRevision
            )
            .sort((a, b) => b.revision - a.revision);

        const target = candidates[0];

        if (!target) {
            throw new DeploymentError('Rollback revision not available');
        }

        const old = deployment.spec;

        deployment.spec = new DeploymentSpec({
            name: old.name,
            namespace: old.namespace,
            replicas: old.replicas,
            image: target.image,
            port: old.port,
            maxSurge: old.maxSurge,
            maxUnavailable: old.maxUnavailable,
            revisionHistoryLimit: old.revisionHistoryLimit
        });

        // Rollback creates a new revision containing an older image.
        this.createRevision(deployment, target.image);

        this.emitAudit(deployment, 'ROLLBACK_STARTED', {
            targetRevision: target.revision,
            image: target.image
        });

        this.reconcile(deployment);
        return deployment;
    }

    pause(name, namespace) {
        const deployment = this.get(name, namespace);
        deployment.paused = true;
        deployment.phase = DeploymentPhase.PAUSED;
        this.emitAudit(deployment, 'PAUSED');
    }

    resume(name, namespace) {
        const deployment = this.get(name, namespace);
        deployment.paused = false;
        this.emitAudit(deployment, 'RESUMED');
        this.reconcile(deployment);
    }

    snapshot(deployment) {
        return {
            name: deployment.spec.name,
            namespace: deployment.spec.namespace,
            image: deployment.spec.image,
            replicas: {
                desired: deployment.spec.replicas,
                ready: deployment.readyReplicas,
                total: deployment.totalReplicas
            },
            revision: deployment.revision,
            phase: deployment.phase,
            replicaSets: [...deployment.replicaSets.values()].map(rs => ({
                id: rs.id,
                revision: rs.revision,
                image: rs.image,
                desired: rs.desiredReplicas,
                active: rs.activeReplicas,
                ready: rs.readyReplicas
            }))
        };
    }
}

class RolloutPolicy {
    constructor({ maximumReplicas, approvedRegistries }) {
        this.maximumReplicas = maximumReplicas;
        this.approvedRegistries = new Set(approvedRegistries);
    }

    evaluate(spec) {
        const violations = [];

        if (spec.replicas > this.maximumReplicas) {
            violations.push('Replica limit exceeded');
        }

        const registry = spec.image.split('/')[0];

        if (!this.approvedRegistries.has(registry)) {
            violations.push('Image registry is not approved');
        }

        return Object.freeze({
            allowed: violations.length === 0,
            violations
        });
    }
}

async function runTests() {
    const controller = new DeploymentController();
    const policy = new RolloutPolicy({
        maximumReplicas: 10,
        approvedRegistries: ['registry.example.com']
    });

    const deployment = controller.create(
        new DeploymentSpec({
            name: 'catalog-api',
            namespace: 'production',
            replicas: 3,
            image: 'registry.example.com/catalog:v1',
            maxSurge: 1,
            maxUnavailable: 0
        })
    );

    await controller.completePendingPods(deployment);

    if (deployment.readyReplicas !== 3) {
        throw new Error('Initial replica reconciliation failed');
    }

    const decision = policy.evaluate(deployment.spec);

    if (!decision.allowed) {
        throw new Error('Expected rollout policy approval');
    }

    await controller.rollout(
        'catalog-api',
        'production',
        'registry.example.com/catalog:v2'
    );

    if (deployment.spec.image.endsWith(':v2') === false) {
        throw new Error('Rolling update failed');
    }

    if (deployment.readyReplicas !== 3) {
        throw new Error('Replica count mismatch');
    }

    await controller.rollback(
        'catalog-api',
        'production',
        1
    );

    await controller.completePendingPods(deployment);

    if (!deployment.spec.image.endsWith(':v1')) {
        throw new Error('Rollback failed');
    }

    await controller.update(
        'catalog-api',
        'production',
        { replicas: 5 }
    );

    await controller.completePendingPods(deployment);

    if (deployment.readyReplicas !== 5) {
        throw new Error('Scaling failed');
    }

    controller.pause('catalog-api', 'production');

    if (deployment.phase !== DeploymentPhase.PAUSED) {
        throw new Error('Pause failed');
    }

    controller.resume('catalog-api', 'production');

    try {
        new DeploymentSpec({
            name: 'invalid name',
            replicas: -1,
            image: 'bad image'
        });
        throw new Error('Invalid specification accepted');
    } catch (error) {
        if (!(error instanceof ValidationError)) throw error;
    }

    console.log('All JavaScript tests passed.');
    console.log(JSON.stringify(controller.snapshot(deployment), null, 2));
}

async function main() {
    const controller = new DeploymentController();

    controller.on('deployment-event', event => {
        console.log(
            `[${event.type}] ${event.deployment}`,
            event.details
        );
    });

    const deployment = controller.create(
        new DeploymentSpec({
            name: 'payment-service',
            namespace: 'production',
            replicas: 3,
            image: 'registry.example.com/payment:v1',
            maxSurge: 1,
            maxUnavailable: 0
        })
    );

    await controller.completePendingPods(deployment);

    console.log('\nInitial state');
    console.log(JSON.stringify(controller.snapshot(deployment), null, 2));

    await controller.rollout(
        'payment-service',
        'production',
        'registry.example.com/payment:v2'
    );

    console.log('\nAfter rolling update');
    console.log(JSON.stringify(controller.snapshot(deployment), null, 2));

    await controller.rollback(
        'payment-service',
        'production',
        1
    );

    await controller.completePendingPods(deployment);

    console.log('\nAfter rollback');
    console.log(JSON.stringify(controller.snapshot(deployment), null, 2));

    await runTests();
}

main().catch(error => {
    console.error('Controller failure:', error.message);
    process.exitCode = 1;
});
