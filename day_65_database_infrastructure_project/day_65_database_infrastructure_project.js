"use strict";

/*
 * Highly Available Database Infrastructure
 *
 * Node.js 18+
 * Standard library only.
 *
 * Engineering perspective:
 * - Event-driven infrastructure monitoring
 * - Circuit breakers
 * - Cache-aside reads
 * - Replica routing
 * - Replication positions
 * - Backup manifests
 * - Recovery validation
 * - Failover coordination
 * - Health probes
 */

const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");
const EventEmitter = require("node:events");

class InfrastructureError extends Error {}
class NodeUnavailableError extends InfrastructureError {}
class ReplicationError extends InfrastructureError {}
class RecoveryError extends InfrastructureError {}

const NodeState = Object.freeze({
    HEALTHY: "HEALTHY",
    DEGRADED: "DEGRADED",
    DOWN: "DOWN",
    RECOVERING: "RECOVERING"
});

const NodeRole = Object.freeze({
    PRIMARY: "PRIMARY",
    REPLICA: "REPLICA"
});

class Configuration {
    constructor({
        cacheCapacity = 500,
        cacheTTL = 15000,
        maximumLag = 5,
        maximumConnections = 100,
        backupDirectory = "./database_backups",
        synchronousReplicas = 0
    } = {}) {
        this.cacheCapacity = cacheCapacity;
        this.cacheTTL = cacheTTL;
        this.maximumLag = maximumLag;
        this.maximumConnections = maximumConnections;
        this.backupDirectory = backupDirectory;
        this.synchronousReplicas = synchronousReplicas;

        this.validate();
    }

    validate() {
        const positive = [
            ["cacheCapacity", this.cacheCapacity],
            ["cacheTTL", this.cacheTTL],
            ["maximumConnections", this.maximumConnections]
        ];

        for (const [name, value] of positive) {
            if (!Number.isInteger(value) || value <= 0) {
                throw new TypeError(`${name} must be a positive integer`);
            }
        }

        if (!Number.isInteger(this.maximumLag) ||
            this.maximumLag < 0) {
            throw new TypeError("maximumLag must be non-negative");
        }

        if (!Number.isInteger(this.synchronousReplicas) ||
            this.synchronousReplicas < 0) {
            throw new TypeError("Invalid synchronous replica count");
        }
    }
}

class DatabaseNode {
    constructor(id, role) {
        this.id = id;
        this.role = role;
        this.state = NodeState.HEALTHY;
        this.records = new Map();
        this.position = 0;
        this.connections = 0;
        this.lastHeartbeat = Date.now();
    }

    acquire(maximumConnections) {
        if (this.state !== NodeState.HEALTHY &&
            this.state !== NodeState.DEGRADED) {
            throw new NodeUnavailableError(
                `Node ${this.id} is ${this.state}`
            );
        }

        if (this.connections >= maximumConnections) {
            throw new NodeUnavailableError(
                `Connection limit reached on ${this.id}`
            );
        }

        this.connections++;
    }

    release() {
        if (this.connections > 0) {
            this.connections--;
        }
    }

    get(key) {
        if (this.state === NodeState.DOWN) {
            throw new NodeUnavailableError(this.id);
        }

        this.lastHeartbeat = Date.now();
        return this.records.get(key) ?? null;
    }
}

class LRUCache {
    constructor(capacity, ttl) {
        this.capacity = capacity;
        this.ttl = ttl;
        this.entries = new Map();
        this.hits = 0;
        this.misses = 0;
    }

    get(key) {
        const entry = this.entries.get(key);

        if (!entry) {
            this.misses++;
            return null;
        }

        if (Date.now() >= entry.expiresAt) {
            this.entries.delete(key);
            this.misses++;
            return null;
        }

        this.entries.delete(key);
        this.entries.set(key, entry);

        this.hits++;

        return structuredClone(entry.value);
    }

    set(key, value) {
        this.entries.delete(key);

        this.entries.set(key, {
            value: structuredClone(value),
            expiresAt: Date.now() + this.ttl
        });

        while (this.entries.size > this.capacity) {
            const oldest = this.entries.keys().next().value;
            this.entries.delete(oldest);
        }
    }

    invalidate(key) {
        this.entries.delete(key);
    }

    clear() {
        this.entries.clear();
    }
}

class ReplicationLog {
    constructor() {
        this.sequence = 0;
        this.entries = [];
    }

    append(key, record) {
        const entry = Object.freeze({
            position: ++this.sequence,
            key,
            record: structuredClone(record)
        });

        this.entries.push(entry);

        return entry.position;
    }

    pending(position) {
        return this.entries.filter(
            entry => entry.position > position
        );
    }
}

class CircuitBreaker {
    constructor(threshold = 3, resetMilliseconds = 5000) {
        this.threshold = threshold;
        this.resetMilliseconds = resetMilliseconds;
        this.failures = 0;
        this.openedAt = null;
    }

    allow() {
        if (this.openedAt === null) {
            return true;
        }

        if (Date.now() - this.openedAt >=
            this.resetMilliseconds) {
            this.openedAt = null;
            this.failures = 0;
            return true;
        }

        return false;
    }

    success() {
        this.failures = 0;
        this.openedAt = null;
    }

    failure() {
        this.failures++;

        if (this.failures >= this.threshold) {
            this.openedAt = Date.now();
        }
    }
}

class BackupService {
    constructor(directory) {
        this.directory = directory;
        this.manifests = [];
    }

    checksum(records) {
        const canonical = [...records.entries()]
            .sort(([a], [b]) => a.localeCompare(b));

        return crypto
            .createHash("sha256")
            .update(JSON.stringify(canonical))
            .digest("hex");
    }

    async create(node) {
        if (node.state !== NodeState.HEALTHY &&
            node.state !== NodeState.DEGRADED) {
            throw new RecoveryError(
                "Cannot back up an unavailable node"
            );
        }

        await fs.mkdir(this.directory, {
            recursive: true
        });

        const records = [...node.records.entries()]
            .map(([key, value]) => [
                key,
                structuredClone(value)
            ]);

        const manifest = {
            id: crypto.randomUUID(),
            timestamp: new Date().toISOString(),
            position: node.position,
            records,
            checksum: this.checksum(new Map(records))
        };

        const target = path.join(
            this.directory,
            `${manifest.id}.json`
        );

        const temporary = `${target}.tmp`;

        try {
            await fs.writeFile(
                temporary,
                JSON.stringify(manifest, null, 2),
                { flag: "wx", mode: 0o600 }
            );

            await fs.rename(temporary, target);
        } catch (error) {
            await fs.rm(temporary, { force: true });
            throw new RecoveryError(
                `Backup persistence failed: ${error.message}`
            );
        }

        this.manifests.push({
            id: manifest.id,
            target,
            checksum: manifest.checksum
        });

        return manifest;
    }

    verify(manifest) {
        const calculated = this.checksum(
            new Map(manifest.records)
        );

        return calculated === manifest.checksum;
    }

    async restore(node, manifest) {
        if (!this.verify(manifest)) {
            throw new RecoveryError("Backup integrity check failed");
        }

        node.state = NodeState.RECOVERING;

        node.records = new Map(
            manifest.records.map(([key, value]) => [
                key,
                structuredClone(value)
            ])
        );

        node.position = manifest.position;
        node.state = NodeState.HEALTHY;
    }
}

class HighAvailabilityCluster extends EventEmitter {
    constructor(configuration = new Configuration()) {
        super();

        this.config = configuration;

        this.primary = new DatabaseNode(
            "database-primary",
            NodeRole.PRIMARY
        );

        this.replicas = [
            new DatabaseNode("database-replica-1", NodeRole.REPLICA),
            new DatabaseNode("database-replica-2", NodeRole.REPLICA)
        ];

        this.log = new ReplicationLog();
        this.cache = new LRUCache(
            configuration.cacheCapacity,
            configuration.cacheTTL
        );

        this.backups = new BackupService(
            configuration.backupDirectory
        );

        this.breaker = new CircuitBreaker();

        this.metrics = {
            reads: 0,
            writes: 0,
            failedOperations: 0,
            replicationOperations: 0,
            failovers: 0,
            backups: 0
        };

        this.mutex = Promise.resolve();
    }

    async exclusive(operation) {
        const previous = this.mutex;

        let release;

        this.mutex = new Promise(resolve => {
            release = resolve;
        });

        await previous;

        try {
            return await operation();
        } finally {
            release();
        }
    }

    async write(key, value) {
        if (typeof key !== "string" || key.trim() === "") {
            throw new TypeError("Invalid database key");
        }

        return this.exclusive(async () => {
            const node = this.primary;

            node.acquire(this.config.maximumConnections);

            try {
                const previous = node.records.get(key);

                const record = {
                    value: structuredClone(value),
                    version: previous ? previous.version + 1 : 1,
                    updatedAt: new Date().toISOString()
                };

                const position = this.log.append(key, record);

                const synchronous = this.replicas.filter(
                    replica => replica.state === NodeState.HEALTHY
                );

                if (synchronous.length <
                    this.config.synchronousReplicas) {
                    throw new ReplicationError(
                        "Synchronous replication quorum unavailable"
                    );
                }

                node.records.set(key, record);
                node.position = position;

                if (this.config.synchronousReplicas > 0) {
                    for (const replica of synchronous.slice(
                        0,
                        this.config.synchronousReplicas
                    )) {
                        this.applyReplication(replica);
                    }
                }

                this.cache.invalidate(key);
                this.metrics.writes++;

                this.emit("database:write", {
                    key,
                    position
                });

                return structuredClone(record);
            } catch (error) {
                this.metrics.failedOperations++;
                throw error;
            } finally {
                node.release();
            }
        });
    }

    applyReplication(replica) {
        const pending = this.log.pending(replica.position);

        for (const entry of pending) {
            replica.records.set(
                entry.key,
                structuredClone(entry.record)
            );

            replica.position = entry.position;
        }

        this.metrics.replicationOperations += pending.length;

        return pending.length;
    }

    async replicateAll() {
        return this.exclusive(async () => {
            const result = [];

            for (const replica of this.replicas) {
                if (replica.state !== NodeState.DOWN) {
                    result.push({
                        node: replica.id,
                        replicated: this.applyReplication(replica)
                    });
                }
            }

            this.emit("database:replication", result);

            return result;
        });
    }

    async read(key, options = {}) {
        const cached = this.cache.get(key);

        if (cached !== null) {
            return cached;
        }

        const preferReplica = options.preferReplica !== false;

        const replica = preferReplica
            ? this.replicas.find(node =>
                node.state === NodeState.HEALTHY &&
                this.primary.position - node.position <=
                    this.config.maximumLag
            )
            : null;

        const node = replica || this.primary;

        if (!this.breaker.allow()) {
            throw new NodeUnavailableError(
                "Database circuit breaker is open"
            );
        }

        try {
            node.acquire(this.config.maximumConnections);

            try {
                const record = node.get(key);

                this.metrics.reads++;

                if (record !== null) {
                    this.cache.set(key, record);
                }

                this.breaker.success();

                return record;
            } finally {
                node.release();
            }
        } catch (error) {
            this.metrics.failedOperations++;
            this.breaker.failure();
            throw error;
        }
    }

    async createBackup() {
        return this.exclusive(async () => {
            const manifest = await this.backups.create(
                this.primary
            );

            this.metrics.backups++;

            this.emit("database:backup", {
                id: manifest.id,
                checksum: manifest.checksum
            });

            return manifest;
        });
    }

    async restoreBackup(manifest) {
        return this.exclusive(async () => {
            await this.backups.restore(
                this.primary,
                manifest
            );

            for (const replica of this.replicas) {
                replica.records = new Map(
                    [...this.primary.records.entries()].map(
                        ([key, value]) => [
                            key,
                            structuredClone(value)
                        ]
                    )
                );

                replica.position = this.primary.position;
            }

            this.cache.clear();

            this.emit("database:recovery", {
                position: this.primary.position
            });
        });
    }

    async failNode(nodeId) {
        return this.exclusive(async () => {
            const node = [
                this.primary,
                ...this.replicas
            ].find(item => item.id === nodeId);

            if (!node) {
                throw new TypeError("Unknown node");
            }

            node.state = NodeState.DOWN;

            this.emit("database:failure", {
                node: node.id
            });
        });
    }

    async failover() {
        return this.exclusive(async () => {
            if (this.primary.state !== NodeState.DOWN) {
                throw new InfrastructureError(
                    "Primary failure has not been detected"
                );
            }

            const eligible = this.replicas.filter(
                replica => replica.state === NodeState.HEALTHY
            );

            if (eligible.length === 0) {
                throw new NodeUnavailableError(
                    "No replica can be promoted"
                );
            }

            const promoted = eligible.reduce(
                (best, candidate) =>
                    candidate.position > best.position
                        ? candidate
                        : best
            );

            const previous = this.primary;

            previous.role = NodeRole.REPLICA;
            promoted.role = NodeRole.PRIMARY;

            this.replicas = this.replicas.filter(
                item => item !== promoted
            );

            this.replicas.push(previous);
            this.primary = promoted;

            this.metrics.failovers++;
            this.cache.clear();

            this.emit("database:failover", {
                newPrimary: promoted.id,
                recoveredPosition: promoted.position
            });

            return promoted.id;
        });
    }

    healthReport() {
        const nodes = [
            this.primary,
            ...this.replicas
        ];

        return {
            timestamp: new Date().toISOString(),
            clusterHealthy: this.primary.state === NodeState.HEALTHY,
            primary: this.primary.id,
            nodes: nodes.map(node => ({
                id: node.id,
                role: node.role,
                state: node.state,
                position: node.position,
                records: node.records.size,
                connections: node.connections,
                lag: Math.max(
                    0,
                    this.primary.position - node.position
                )
            })),
            cache: {
                entries: this.cache.entries.size,
                hits: this.cache.hits,
                misses: this.cache.misses
            },
            metrics: { ...this.metrics }
        };
    }
}

async function main() {
    const cluster = new HighAvailabilityCluster(
        new Configuration({
            cacheCapacity: 100,
            cacheTTL: 10000,
            maximumLag: 5,
            synchronousReplicas: 0,
            backupDirectory: "./database_backups"
        })
    );

    for (const event of [
        "database:write",
        "database:failure",
        "database:replication",
        "database:failover",
        "database:backup",
        "database:recovery"
    ]) {
        cluster.on(event, data => {
            console.log(`[EVENT] ${event}`, data);
        });
    }

    await cluster.write("order:1001", {
        customer: "C100",
        amount: 4500,
        status: "PAID"
    });

    await cluster.write("order:1002", {
        customer: "C101",
        amount: 7800,
        status: "PENDING"
    });

    await cluster.replicateAll();

    console.log("Read:", await cluster.read("order:1001"));
    console.log("Cached read:", await cluster.read("order:1001"));

    const backup = await cluster.createBackup();

    if (!cluster.backups.verify(backup)) {
        throw new RecoveryError("Backup verification failed");
    }

    const failedNode = cluster.primary.id;

    await cluster.failNode(failedNode);

    const promoted = await cluster.failover();

    console.log("Promoted node:", promoted);

    await cluster.write("order:1003", {
        customer: "C102",
        amount: 12000,
        status: "PAID"
    });

    await cluster.replicateAll();

    console.log(
        "Health report:",
        JSON.stringify(cluster.healthReport(), null, 2)
    );

    await cluster.restoreBackup(backup);

    console.log("Recovery completed and validated");
}

main().catch(error => {
    console.error("Infrastructure failure:", error);
    process.exitCode = 1;
});
