'use strict';

/*
 * NoSQL infrastructure case study.
 *
 * The implementation focuses on event-driven processing:
 * - key-value state
 * - document validation
 * - wide-column event storage
 * - graph relationships
 * - asynchronous replica propagation
 * - policy checks for stale reads
 */

const { EventEmitter } = require('node:events');

class ValidationError extends Error {}
class ConflictError extends Error {}

function validateKey(key) {
    if (typeof key !== 'string' || key.trim().length === 0) {
        throw new ValidationError('Key must be a non-empty string');
    }
    if (key.length > 256) {
        throw new ValidationError('Key exceeds 256 characters');
    }
}

class KeyValueStore {
    constructor() {
        this.data = new Map();
    }

    put(key, value, expectedVersion = null) {
        validateKey(key);

        const current = this.data.get(key);
        const actualVersion = current ? current.version : 0;

        if (expectedVersion !== null && expectedVersion !== actualVersion) {
            throw new ConflictError(
                `Version conflict: expected ${expectedVersion}, got ${actualVersion}`
            );
        }

        const version = actualVersion + 1;
        this.data.set(key, {
            value: structuredClone(value),
            version,
            updatedAt: Date.now()
        });

        return version;
    }

    get(key) {
        validateKey(key);
        const item = this.data.get(key);
        return item ? structuredClone(item) : null;
    }
}

class DocumentStore {
    constructor(requiredFields) {
        this.requiredFields = new Set(requiredFields);
        this.documents = new Map();
        this.indexes = new Map();
    }

    insert(id, document) {
        validateKey(id);

        for (const field of this.requiredFields) {
            if (!(field in document)) {
                throw new ValidationError(`Missing field: ${field}`);
            }
        }

        if (this.documents.has(id)) {
            throw new ConflictError(`Document already exists: ${id}`);
        }

        const copy = structuredClone(document);
        this.documents.set(id, copy);

        for (const [field, value] of Object.entries(copy)) {
            if (
                typeof value === 'string' ||
                typeof value === 'number' ||
                typeof value === 'boolean'
            ) {
                if (!this.indexes.has(field)) {
                    this.indexes.set(field, new Map());
                }

                const index = this.indexes.get(field);

                if (!index.has(value)) {
                    index.set(value, new Set());
                }

                index.get(value).add(id);
            }
        }
    }

    findBy(field, value) {
        const index = this.indexes.get(field);
        if (!index) {
            return [];
        }

        const ids = index.get(value) || new Set();
        return [...ids].map(id => structuredClone(this.documents.get(id)));
    }
}

class WideColumnStore {
    constructor() {
        this.partitions = new Map();
    }

    upsert(partitionKey, clusteringKey, columns) {
        validateKey(partitionKey);
        validateKey(clusteringKey);

        if (!this.partitions.has(partitionKey)) {
            this.partitions.set(partitionKey, new Map());
        }

        const partition = this.partitions.get(partitionKey);
        const existing = partition.get(clusteringKey) || {};

        partition.set(clusteringKey, {
            ...existing,
            ...structuredClone(columns)
        });
    }

    queryPartition(partitionKey) {
        const partition = this.partitions.get(partitionKey);
        if (!partition) {
            return [];
        }

        return [...partition.entries()]
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([clusteringKey, columns]) => ({
                clusteringKey,
                ...structuredClone(columns)
            }));
    }
}

class GraphStore {
    constructor() {
        this.nodes = new Map();
        this.edges = new Map();
    }

    addNode(id, properties = {}) {
        validateKey(id);

        this.nodes.set(id, {
            ...(this.nodes.get(id) || {}),
            ...structuredClone(properties)
        });
    }

    addEdge(source, target, relationship, properties = {}) {
        if (!this.nodes.has(source) || !this.nodes.has(target)) {
            throw new ValidationError('Both graph endpoints must exist');
        }

        if (!this.edges.has(source)) {
            this.edges.set(source, []);
        }

        this.edges.get(source).push({
            target,
            relationship,
            properties: structuredClone(properties)
        });
    }

    shortestPath(source, target) {
        if (!this.nodes.has(source) || !this.nodes.has(target)) {
            return null;
        }

        const queue = [[source, [source]]];
        const visited = new Set([source]);

        while (queue.length > 0) {
            const [node, path] = queue.shift();

            if (node === target) {
                return path;
            }

            for (const edge of this.edges.get(node) || []) {
                if (!visited.has(edge.target)) {
                    visited.add(edge.target);
                    queue.push([edge.target, [...path, edge.target]]);
                }
            }
        }

        return null;
    }
}

class EventualConsistencyCluster extends EventEmitter {
    constructor(replicaNames) {
        super();
        this.leader = new KeyValueStore();
        this.replicas = new Map(
            replicaNames.map(name => [name, new KeyValueStore()])
        );
        this.queue = [];
    }

    write(key, value) {
        const version = this.leader.put(key, value);

        for (const name of this.replicas.keys()) {
            this.queue.push({
                replica: name,
                key,
                version
            });
        }

        this.emit('write', { key, version });
        return version;
    }

    async replicate(delayMs = 5) {
        while (this.queue.length > 0) {
            const event = this.queue.shift();

            await new Promise(resolve => setTimeout(resolve, delayMs));

            const leaderValue = this.leader.get(event.key);
            const replica = this.replicas.get(event.replica);
            const current = replica.get(event.key);

            if (!current || leaderValue.version >= current.version) {
                replica.put(event.key, leaderValue.value);
                this.emit('replicated', {
                    replica: event.replica,
                    key: event.key,
                    version: leaderValue.version
                });
            }
        }
    }

    read(key, replicaName = 'leader') {
        if (replicaName === 'leader') {
            return this.leader.get(key);
        }

        const replica = this.replicas.get(replicaName);
        if (!replica) {
            throw new ValidationError(`Unknown replica: ${replicaName}`);
        }

        return replica.get(key);
    }
}

async function main() {
    console.log('=== NoSQL Infrastructure Event Model ===');

    const kv = new KeyValueStore();
    const version = kv.put('user:1001', {
        role: 'engineer',
        active: true
    });

    console.log('KV:', kv.get('user:1001'));

    try {
        kv.put('user:1001', { role: 'admin' }, version - 1);
    } catch (error) {
        console.log('Expected conflict:', error.message);
    }

    const documents = new DocumentStore([
        'userId',
        'name',
        'department'
    ]);

    documents.insert('u1', {
        userId: 'u1',
        name: 'Anita',
        department: 'security',
        skills: ['javascript', 'postgresql']
    });

    documents.insert('u2', {
        userId: 'u2',
        name: 'Ravi',
        department: 'engineering',
        skills: ['cpp']
    });

    console.log(
        'Security documents:',
        documents.findBy('department', 'security')
    );

    const wide = new WideColumnStore();

    wide.upsert('device-42', '2026-10-31T11:00:00Z', {
        temperature: 31.2
    });

    wide.upsert('device-42', '2026-10-31T11:01:00Z', {
        temperature: 31.4,
        battery: 87
    });

    console.log('Telemetry:', wide.queryPartition('device-42'));

    const graph = new GraphStore();

    ['alice', 'bob', 'carol', 'database'].forEach(id => {
        graph.addNode(id);
    });

    graph.addEdge('alice', 'bob', 'trusts');
    graph.addEdge('bob', 'carol', 'trusts');
    graph.addEdge('carol', 'database', 'accesses');

    console.log(
        'Access path:',
        graph.shortestPath('alice', 'database')
    );

    const cluster = new EventualConsistencyCluster([
        'replica-a',
        'replica-b'
    ]);

    cluster.on('write', event => {
        console.log('Leader event:', event);
    });

    cluster.on('replicated', event => {
        console.log('Replication event:', event);
    });

    cluster.write('config:payments', {
        enabled: true,
        timeoutMs: 1500
    });

    console.log(
        'Replica before replication:',
        cluster.read('config:payments', 'replica-a')
    );

    await cluster.replicate();

    console.log(
        'Replica after replication:',
        cluster.read('config:payments', 'replica-a')
    );

    console.log('Security controls:');
    console.log('- Validate keys and document fields before writes.');
    console.log('- Authorize access before exposing database operations.');
    console.log('- Avoid putting credentials or tokens into documents.');
    console.log('- Use version checks for concurrent updates.');
    console.log('- Mark replica reads as potentially stale.');

    console.log('Performance model:');
    console.log('- Map-based key-value access is average O(1).');
    console.log('- Indexed document equality lookup scales with matching records.');
    console.log('- Wide-column reads are optimized around partition keys.');
    console.log('- Graph traversal is O(V + E) for breadth-first search.');
}

main().catch(error => {
    console.error('Fatal error:', error.message);
    process.exitCode = 1;
});
