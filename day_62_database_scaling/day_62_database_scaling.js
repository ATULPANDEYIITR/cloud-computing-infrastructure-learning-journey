'use strict';

/*
 * Database Scaling Case Study
 *
 * Models vertical scaling, horizontal scaling, partitioning, sharding,
 * and read replicas through an event-driven workload simulator.
 */

const EventEmitter = require('node:events');
const crypto = require('node:crypto');

const ScalingStrategy = Object.freeze({
    VERTICAL: 'vertical',
    HORIZONTAL: 'horizontal',
    PARTITIONING: 'partitioning',
    SHARDING: 'sharding',
    READ_REPLICA: 'read_replica'
});

const Operation = Object.freeze({
    READ: 'read',
    WRITE: 'write'
});

const Consistency = Object.freeze({
    STRONG: 'strong',
    EVENTUAL: 'eventual'
});

class DatabaseNode {
    constructor(id, region, capacityOps) {
        if (!id || !region || !Number.isInteger(capacityOps) || capacityOps <= 0) {
            throw new Error('Invalid database node configuration');
        }

        this.id = id;
        this.region = region;
        this.capacityOps = capacityOps;
        this.activeOps = 0;
        this.healthy = true;
    }

    get utilization() {
        return this.activeOps / this.capacityOps;
    }

    canAccept() {
        return this.healthy && this.activeOps < this.capacityOps;
    }
}

class Partition {
    constructor(id, minCustomer, maxCustomer) {
        if (minCustomer > maxCustomer) {
            throw new Error('Invalid partition range');
        }

        this.id = id;
        this.minCustomer = minCustomer;
        this.maxCustomer = maxCustomer;
        this.rows = [];
    }

    contains(customerId) {
        return customerId >= this.minCustomer &&
               customerId <= this.maxCustomer;
    }

    insert(row) {
        if (!this.contains(row.customerId)) {
            throw new Error(
                `Customer ${row.customerId} does not belong to ${this.id}`
            );
        }
        this.rows.push(Object.freeze({ ...row }));
    }
}

class PartitionedTable {
    constructor(partitions) {
        if (!partitions.length) {
            throw new Error('At least one partition is required');
        }
        this.partitions = partitions;
    }

    locate(customerId) {
        const partition = this.partitions.find(
            p => p.contains(customerId)
        );

        if (!partition) {
            throw new Error(`No partition for customer ${customerId}`);
        }

        return partition;
    }

    insert(row) {
        if (!Number.isInteger(row.customerId) || row.customerId < 0) {
            throw new Error('Customer ID must be a non-negative integer');
        }

        this.locate(row.customerId).insert(row);
    }

    findByCustomer(customerId) {
        const partition = this.locate(customerId);
        return partition.rows.filter(
            row => row.customerId === customerId
        );
    }
}

class ShardRouter {
    constructor(shardIds) {
        if (!Array.isArray(shardIds) || shardIds.length === 0) {
            throw new Error('Shard list cannot be empty');
        }

        this.shardIds = [...shardIds];
    }

    shardFor(customerId) {
        if (!Number.isInteger(customerId) || customerId < 0) {
            throw new Error('Invalid customer ID');
        }

        return this.shardIds[customerId % this.shardIds.length];
    }
}

class ReadReplicaPool {
    constructor(primary, replicas) {
        this.primary = primary;
        this.replicas = replicas;
        this.cursor = 0;
    }

    route(operation, consistency) {
        if (operation === Operation.WRITE ||
            consistency === Consistency.STRONG) {
            if (!this.primary.canAccept()) {
                throw new Error('Primary is unavailable');
            }
            return this.primary;
        }

        const healthyReplicas = this.replicas.filter(
            node => node.canAccept()
        );

        if (healthyReplicas.length === 0) {
            if (this.primary.canAccept()) {
                return this.primary;
            }
            throw new Error('No read-capable database node is available');
        }

        const node = healthyReplicas[this.cursor % healthyReplicas.length];
        this.cursor += 1;
        return node;
    }
}

class ScalingPolicy {
    constructor() {
        this.readReplicaThreshold = 0.70;
        this.partitionRowThreshold = 10_000_000;
    }

    evaluate({ workloadOps, nodeCapacityOps, writeRatio, rows }) {
        if (!Number.isFinite(workloadOps) || workloadOps <= 0) {
            throw new Error('Workload must be positive');
        }

        if (!Number.isFinite(nodeCapacityOps) || nodeCapacityOps <= 0) {
            throw new Error('Node capacity must be positive');
        }

        if (writeRatio < 0 || writeRatio > 1) {
            throw new Error('Write ratio must be between zero and one');
        }

        const utilization = workloadOps / nodeCapacityOps;

        if (utilization <= 0.70) {
            return ScalingStrategy.VERTICAL;
        }

        if (writeRatio < 0.30) {
            return ScalingStrategy.READ_REPLICA;
        }

        if (rows > this.partitionRowThreshold) {
            return ScalingStrategy.PARTITIONING;
        }

        return ScalingStrategy.HORIZONTAL;
    }
}

class Metrics {
    constructor() {
        this.operations = new Map();
        this.latencies = [];
    }

    record(operation, latencyMs) {
        this.operations.set(
            operation,
            (this.operations.get(operation) || 0) + 1
        );
        this.latencies.push(latencyMs);
    }

    summary() {
        if (this.latencies.length === 0) {
            return {
                operations: Object.fromEntries(this.operations),
                averageLatencyMs: 0,
                p95LatencyMs: 0
            };
        }

        const values = [...this.latencies].sort((a, b) => a - b);
        const average =
            values.reduce((sum, value) => sum + value, 0) / values.length;
        const p95 =
            values[Math.min(values.length - 1, Math.floor(values.length * 0.95))];

        return {
            operations: Object.fromEntries(this.operations),
            averageLatencyMs: average,
            p95LatencyMs: p95
        };
    }
}

class WorkloadSimulator extends EventEmitter {
    constructor(cluster) {
        super();
        this.cluster = cluster;
        this.metrics = new Metrics();
    }

    async process(request) {
        const node = this.cluster.route(
            request.operation,
            request.consistency
        );

        node.activeOps += 1;
        this.emit('routed', {
            requestId: request.requestId,
            nodeId: node.id
        });

        try {
            // A Promise models asynchronous database I/O without requiring
            // an external database driver.
            await new Promise(resolve => setImmediate(resolve));

            const latency = node === this.cluster.primary ? 5 : 2.5;
            this.metrics.record(request.operation, latency);

            this.emit('completed', {
                requestId: request.requestId,
                nodeId: node.id,
                latency
            });

            return {
                requestId: request.requestId,
                nodeId: node.id,
                latency
            };
        } finally {
            node.activeOps -= 1;
        }
    }

    async run(requests) {
        const results = [];

        for (const request of requests) {
            results.push(await this.process(request));
        }

        return results;
    }
}

function createRequest(customerId, operation, consistency) {
    return {
        requestId: crypto.randomUUID(),
        customerId,
        operation,
        consistency
    };
}

async function main() {
    console.log('Database Scaling Case Study');
    console.log('='.repeat(60));

    const policy = new ScalingPolicy();

    console.log('\nScaling decisions:');
    const scenarios = [
        { workloadOps: 500, nodeCapacityOps: 1000, writeRatio: 0.5, rows: 100_000 },
        { workloadOps: 900, nodeCapacityOps: 1000, writeRatio: 0.1, rows: 500_000 },
        { workloadOps: 900, nodeCapacityOps: 1000, writeRatio: 0.8, rows: 20_000_000 },
        { workloadOps: 950, nodeCapacityOps: 1000, writeRatio: 0.5, rows: 2_000_000 }
    ];

    for (const scenario of scenarios) {
        console.log(
            scenario,
            '=>',
            policy.evaluate(scenario)
        );
    }

    console.log('\nPartitioning:');
    const table = new PartitionedTable([
        new Partition('p0_999', 0, 999),
        new Partition('p1000_1999', 1000, 1999),
        new Partition('p2000_2999', 2000, 2999)
    ]);

    table.insert({ orderId: 1, customerId: 101, amount: 250 });
    table.insert({ orderId: 2, customerId: 1500, amount: 400 });
    table.insert({ orderId: 3, customerId: 2100, amount: 800 });

    for (const partition of table.partitions) {
        console.log(partition.id, partition.rows.length);
    }

    console.log('\nSharding:');
    const router = new ShardRouter([
        'shard-a',
        'shard-b',
        'shard-c'
    ]);

    for (const customerId of [101, 102, 103, 104, 105]) {
        console.log(
            customerId,
            '=>',
            router.shardFor(customerId)
        );
    }

    console.log('\nRead replicas:');

    const primary = new DatabaseNode('primary', 'ap-south', 1000);
    const replicas = [
        new DatabaseNode('replica-1', 'ap-south', 800),
        new DatabaseNode('replica-2', 'ap-southeast', 800)
    ];

    const cluster = new ReadReplicaPool(primary, replicas);
    const simulator = new WorkloadSimulator(cluster);

    simulator.on('routed', event => {
        console.log(`Routed ${event.requestId} -> ${event.nodeId}`);
    });

    simulator.on('completed', event => {
        console.log(
            `Completed ${event.requestId} on ${event.nodeId}, ` +
            `${event.latency} ms`
        );
    });

    const requests = [
        createRequest(101, Operation.READ, Consistency.EVENTUAL),
        createRequest(102, Operation.READ, Consistency.EVENTUAL),
        createRequest(103, Operation.READ, Consistency.STRONG),
        createRequest(104, Operation.WRITE, Consistency.STRONG),
        createRequest(105, Operation.READ, Consistency.EVENTUAL),
        createRequest(106, Operation.WRITE, Consistency.STRONG)
    ];

    await simulator.run(requests);
    console.log('Metrics:', simulator.metrics.summary());

    console.log('\nFailure handling:');
    replicas.forEach(replica => {
        replica.healthy = false;
    });

    const fallback = cluster.route(
        Operation.READ,
        Consistency.EVENTUAL
    );

    console.log(
        `All replicas unavailable; eventual read routed to ${fallback.id}`
    );

    try {
        table.insert({
            orderId: 4,
            customerId: 5000,
            amount: 100
        });
    } catch (error) {
        console.log('Rejected invalid partition:', error.message);
    }

    try {
        new ShardRouter([]);
    } catch (error) {
        console.log('Rejected invalid shard configuration:', error.message);
    }

    console.log('\nSecurity and production controls:');
    console.log('- Authenticate database clients before routing requests.');
    console.log('- Keep shard metadata server-side and protect routing configuration.');
    console.log('- Restrict administrative operations with least privilege.');
    console.log('- Encrypt database traffic and replication channels.');
    console.log('- Monitor replication lag, saturation, connection counts, and errors.');
}

main().catch(error => {
    console.error('Fatal error:', error.message);
    process.exitCode = 1;
});
