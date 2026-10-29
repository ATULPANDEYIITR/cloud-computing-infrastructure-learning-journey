'use strict';

const crypto = require('node:crypto');
const { EventEmitter } = require('node:events');

const ReplicationMode = Object.freeze({
    SYNC: 'synchronous',
    ASYNC: 'asynchronous'
});

const ReplicaState = Object.freeze({
    ONLINE: 'online',
    LAGGING: 'lagging',
    OFFLINE: 'offline'
});

function checksum(sequence, key, value) {
    return crypto
        .createHash('sha256')
        .update(`${sequence}|${key}|${value ?? 'NULL'}`)
        .digest('hex');
}

class ReplicationError extends Error {
    constructor(message, code) {
        super(message);
        this.name = 'ReplicationError';
        this.code = code;
    }
}

class PrimaryDatabase extends EventEmitter {
    constructor(name) {
        super();
        this.name = name;
        this.sequence = 0;
        this.data = new Map();
        this.log = [];
    }

    commit(key, value) {
        if (typeof key !== 'string' || key.length < 1 || key.length > 128) {
            throw new ReplicationError('Key must contain 1-128 characters', 'INVALID_KEY');
        }

        if (value !== null && typeof value !== 'string') {
            throw new ReplicationError('Value must be a string or null', 'INVALID_VALUE');
        }

        const sequence = ++this.sequence;
        const change = {
            sequence,
            key,
            value,
            checksum: checksum(sequence, key, value)
        };

        if (value === null) {
            this.data.delete(key);
        } else {
            this.data.set(key, value);
        }

        this.log.push(change);
        this.emit('commit', change);

        return change;
    }

    read(key) {
        return this.data.has(key) ? this.data.get(key) : null;
    }
}

class ReadReplica {
    constructor(name) {
        this.name = name;
        this.state = ReplicaState.ONLINE;
        this.appliedSequence = 0;
        this.data = new Map();
        this.queue = [];
    }

    receive(change) {
        if (this.state === ReplicaState.OFFLINE) {
            throw new ReplicationError(
                `${this.name} is offline`,
                'REPLICA_OFFLINE'
            );
        }

        const expected = this.appliedSequence + this.queue.length + 1;

        if (change.sequence !== expected) {
            throw new ReplicationError(
                `${this.name} expected sequence ${expected}, received ${change.sequence}`,
                'SEQUENCE_GAP'
            );
        }

        const expectedChecksum = checksum(
            change.sequence,
            change.key,
            change.value
        );

        if (change.checksum !== expectedChecksum) {
            throw new ReplicationError(
                `${this.name} rejected corrupted change`,
                'CHECKSUM_FAILURE'
            );
        }

        this.queue.push(change);
        this.state = ReplicaState.LAGGING;
    }

    async applyQueue() {
        if (this.state === ReplicaState.OFFLINE) {
            throw new ReplicationError(
                `${this.name} is offline`,
                'REPLICA_OFFLINE'
            );
        }

        // Yielding to the event loop models asynchronous replication work.
        await new Promise(resolve => setImmediate(resolve));

        for (const change of this.queue) {
            if (change.value === null) {
                this.data.delete(change.key);
            } else {
                this.data.set(change.key, change.value);
            }

            this.appliedSequence = change.sequence;
        }

        this.queue.length = 0;
        this.state = ReplicaState.ONLINE;
    }

    read(key) {
        if (this.state === ReplicaState.OFFLINE) {
            throw new ReplicationError(
                `${this.name} is offline`,
                'REPLICA_OFFLINE'
            );
        }

        return this.data.has(key) ? this.data.get(key) : null;
    }
}

class ReplicationCluster extends EventEmitter {
    constructor(primary, replicas, mode, synchronousQuorum = null) {
        super();

        if (!Object.values(ReplicationMode).includes(mode)) {
            throw new TypeError(`Unsupported replication mode: ${mode}`);
        }

        this.primary = primary;
        this.replicas = replicas;
        this.mode = mode;
        this.synchronousQuorum =
            synchronousQuorum ?? replicas.length;

        this.primary.on('commit', change => {
            this.emit('change', change);
        });
    }

    async write(key, value) {
        const change = this.primary.commit(key, value);
        const acknowledgements = [];
        const failures = [];

        for (const replica of this.replicas) {
            try {
                replica.receive(change);

                if (this.mode === ReplicationMode.SYNC) {
                    await replica.applyQueue();
                }

                acknowledgements.push(replica.name);
            } catch (error) {
                failures.push({
                    replica: replica.name,
                    code: error.code ?? 'UNKNOWN',
                    message: error.message
                });
            }
        }

        if (
            this.mode === ReplicationMode.SYNC &&
            acknowledgements.length < this.synchronousQuorum
        ) {
            return {
                acknowledged: false,
                sequence: change.sequence,
                acknowledgements,
                failures
            };
        }

        return {
            acknowledged: true,
            sequence: change.sequence,
            acknowledgements,
            failures
        };
    }

    async drainReplicas() {
        await Promise.all(
            this.replicas
                .filter(replica => replica.state !== ReplicaState.OFFLINE)
                .map(replica => replica.applyQueue())
        );
    }

    lag(replica) {
        return this.primary.sequence - replica.appliedSequence;
    }

    routeRead(key, preferredReplica = null) {
        if (preferredReplica) {
            return preferredReplica.read(key);
        }

        return this.primary.read(key);
    }

    health() {
        return this.replicas.map(replica => ({
            name: replica.name,
            state: replica.state,
            appliedSequence: replica.appliedSequence,
            lag: this.lag(replica)
        }));
    }
}

async function main() {
    const primary = new PrimaryDatabase('primary');
    const replicaA = new ReadReplica('read-a');
    const replicaB = new ReadReplica('read-b');

    const cluster = new ReplicationCluster(
        primary,
        [replicaA, replicaB],
        ReplicationMode.ASYNC
    );

    cluster.on('change', change => {
        console.log(`Primary committed sequence ${change.sequence}`);
    });

    console.log('=== Asynchronous write ===');
    console.log(await cluster.write('account:101', 'ACTIVE'));

    console.log('Primary value:', primary.read('account:101'));
    console.log('Replica A before catch-up:', replicaA.read('account:101'));
    console.log('Health:', cluster.health());

    await cluster.drainReplicas();

    console.log('Replica A after catch-up:', replicaA.read('account:101'));
    console.log('Health:', cluster.health());

    console.log('\n=== Read routing ===');
    console.log(
        'Replica read:',
        cluster.routeRead('account:101', replicaA)
    );

    console.log('\n=== Offline replica ===');
    replicaB.state = ReplicaState.OFFLINE;

    console.log(await cluster.write('account:101', 'SUSPENDED'));
    console.log('Health:', cluster.health());

    console.log('\n=== Synchronous quorum ===');
    const syncPrimary = new PrimaryDatabase('sync-primary');
    const syncA = new ReadReplica('sync-a');
    const syncB = new ReadReplica('sync-b');
    syncB.state = ReplicaState.OFFLINE;

    const synchronousCluster = new ReplicationCluster(
        syncPrimary,
        [syncA, syncB],
        ReplicationMode.SYNC,
        2
    );

    console.log(
        await synchronousCluster.write('payment:700', 'SETTLED')
    );
}

main().catch(error => {
    console.error('Fatal error:', error);
    process.exitCode = 1;
});
