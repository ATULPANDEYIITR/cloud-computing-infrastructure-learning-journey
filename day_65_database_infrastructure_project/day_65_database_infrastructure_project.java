import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.ReentrantLock;
import java.util.stream.Collectors;

/*
 * Enterprise Database Infrastructure Management
 *
 * Java 17
 * Standard library only.
 *
 * Architecture:
 * - Cluster management
 * - Database node lifecycle
 * - Replication policies
 * - Quorum validation
 * - Connection governance
 * - Backup integrity
 * - Disaster recovery
 * - Cache invalidation
 * - Operational observability
 */

public class DatabaseInfrastructure {

    enum NodeRole {
        PRIMARY,
        REPLICA
    }

    enum NodeState {
        HEALTHY,
        DEGRADED,
        DOWN,
        RECOVERING
    }

    enum ReplicationPolicy {
        SYNCHRONOUS,
        ASYNCHRONOUS
    }

    record DatabaseConfig(
        ReplicationPolicy replicationPolicy,
        int requiredSynchronousReplicas,
        int maximumReplicationLag,
        int maximumConnections,
        int cacheCapacity
    ) {
        DatabaseConfig {
            Objects.requireNonNull(replicationPolicy);

            if (requiredSynchronousReplicas < 0 ||
                maximumReplicationLag < 0 ||
                maximumConnections <= 0 ||
                cacheCapacity <= 0) {
                throw new IllegalArgumentException(
                    "Invalid database configuration"
                );
            }
        }
    }

    record DatabaseRecord(
        String key,
        String value,
        long version,
        Instant updatedAt
    ) {
        DatabaseRecord {
            if (key == null || key.isBlank()) {
                throw new IllegalArgumentException(
                    "Record key cannot be empty"
                );
            }

            Objects.requireNonNull(value);
            Objects.requireNonNull(updatedAt);
        }
    }

    record LogEntry(
        long position,
        String key,
        DatabaseRecord record
    ) {}

    record BackupSnapshot(
        String backupId,
        Instant createdAt,
        long replicationPosition,
        Map<String, DatabaseRecord> records,
        String checksum
    ) {
        BackupSnapshot {
            records = Map.copyOf(records);
        }
    }

    static class InfrastructureException
        extends RuntimeException {

        InfrastructureException(String message) {
            super(message);
        }
    }

    static class ReplicationException
        extends InfrastructureException {

        ReplicationException(String message) {
            super(message);
        }
    }

    static class RecoveryException
        extends InfrastructureException {

        RecoveryException(String message) {
            super(message);
        }
    }

    static class DatabaseNode {
        private final String nodeId;
        private NodeRole role;
        private NodeState state = NodeState.HEALTHY;

        private final Map<String, DatabaseRecord> records =
            new ConcurrentHashMap<>();

        private long replicationPosition;
        private int connections;

        DatabaseNode(String nodeId, NodeRole role) {
            this.nodeId = nodeId;
            this.role = role;
        }

        synchronized void acquire(int maximum) {
            if (state != NodeState.HEALTHY &&
                state != NodeState.DEGRADED) {
                throw new InfrastructureException(
                    "Node unavailable: " + nodeId
                );
            }

            if (connections >= maximum) {
                throw new InfrastructureException(
                    "Connection pool exhausted: " + nodeId
                );
            }

            connections++;
        }

        synchronized void release() {
            if (connections > 0) {
                connections--;
            }
        }

        Optional<DatabaseRecord> read(String key) {
            if (state == NodeState.DOWN) {
                throw new InfrastructureException(
                    "Database node is down"
                );
            }

            return Optional.ofNullable(records.get(key));
        }

        String id() {
            return nodeId;
        }

        NodeRole role() {
            return role;
        }

        NodeState state() {
            return state;
        }

        long position() {
            return replicationPosition;
        }

        int recordCount() {
            return records.size();
        }
    }

    static class ReplicationService {
        private final List<LogEntry> transactionLog =
            new ArrayList<>();

        private final AtomicLong sequence = new AtomicLong();

        synchronized long append(
            String key,
            DatabaseRecord record
        ) {
            long position = sequence.incrementAndGet();

            transactionLog.add(
                new LogEntry(position, key, record)
            );

            return position;
        }

        synchronized int replicate(
            DatabaseNode replica,
            DatabaseNode primary,
            int maximumLag
        ) {
            if (replica.state == NodeState.DOWN ||
                primary.state == NodeState.DOWN) {
                throw new ReplicationException(
                    "Replication endpoint unavailable"
                );
            }

            int applied = 0;

            for (LogEntry entry : transactionLog) {
                if (entry.position() <=
                    replica.replicationPosition) {
                    continue;
                }

                replica.records.put(
                    entry.key(),
                    entry.record()
                );

                replica.replicationPosition =
                    entry.position();

                applied++;
            }

            long lag = Math.max(
                0,
                primary.replicationPosition -
                    replica.replicationPosition
            );

            replica.state = lag > maximumLag
                ? NodeState.DEGRADED
                : NodeState.HEALTHY;

            return applied;
        }
    }

    static class CacheService {
        private record CacheEntry(
            DatabaseRecord value,
            long expiresAt
        ) {}

        private final Map<String, CacheEntry> cache =
            new ConcurrentHashMap<>();

        private final int capacity;
        private final long ttlMillis;

        private final AtomicLong hits = new AtomicLong();
        private final AtomicLong misses = new AtomicLong();

        CacheService(int capacity, long ttlMillis) {
            this.capacity = capacity;
            this.ttlMillis = ttlMillis;
        }

        Optional<DatabaseRecord> get(String key) {
            CacheEntry entry = cache.get(key);

            if (entry == null ||
                System.currentTimeMillis() >= entry.expiresAt()) {
                cache.remove(key);
                misses.incrementAndGet();
                return Optional.empty();
            }

            hits.incrementAndGet();

            return Optional.of(entry.value());
        }

        synchronized void put(
            String key,
            DatabaseRecord value
        ) {
            if (!cache.containsKey(key) &&
                cache.size() >= capacity) {

                String oldest = cache.keySet()
                    .stream()
                    .findFirst()
                    .orElse(null);

                if (oldest != null) {
                    cache.remove(oldest);
                }
            }

            cache.put(
                key,
                new CacheEntry(
                    value,
                    System.currentTimeMillis() + ttlMillis
                )
            );
        }

        void invalidate(String key) {
            cache.remove(key);
        }

        void clear() {
            cache.clear();
        }

        long hits() {
            return hits.get();
        }

        long misses() {
            return misses.get();
        }
    }

    static class BackupService {

        private String checksum(
            Map<String, DatabaseRecord> records
        ) {
            try {
                MessageDigest digest =
                    MessageDigest.getInstance("SHA-256");

                String canonical = records.entrySet()
                    .stream()
                    .sorted(Map.Entry.comparingByKey())
                    .map(entry -> {
                        DatabaseRecord record = entry.getValue();

                        return entry.getKey() + "|" +
                            record.value() + "|" +
                            record.version();
                    })
                    .collect(Collectors.joining("\n"));

                return HexFormat.of().formatHex(
                    digest.digest(
                        canonical.getBytes(StandardCharsets.UTF_8)
                    )
                );

            } catch (NoSuchAlgorithmException error) {
                throw new RecoveryException(
                    "SHA-256 unavailable"
                );
            }
        }

        BackupSnapshot create(DatabaseNode node) {
            if (node.state == NodeState.DOWN) {
                throw new RecoveryException(
                    "Cannot back up unavailable node"
                );
            }

            Map<String, DatabaseRecord> snapshot =
                Map.copyOf(node.records);

            return new BackupSnapshot(
                java.util.UUID.randomUUID().toString(),
                Instant.now(),
                node.replicationPosition,
                snapshot,
                checksum(snapshot)
            );
        }

        boolean verify(BackupSnapshot backup) {
            return checksum(backup.records())
                .equals(backup.checksum());
        }

        void restore(
            DatabaseNode node,
            BackupSnapshot backup
        ) {
            if (!verify(backup)) {
                throw new RecoveryException(
                    "Backup checksum mismatch"
                );
            }

            node.state = NodeState.RECOVERING;

            node.records.clear();
            node.records.putAll(backup.records());

            node.replicationPosition =
                backup.replicationPosition();

            node.state = NodeState.HEALTHY;
        }
    }

    static class FailoverPolicy {
        Optional<DatabaseNode> select(
            List<DatabaseNode> replicas
        ) {
            return replicas.stream()
                .filter(node ->
                    node.state == NodeState.HEALTHY
                )
                .max(
                    Comparator.comparingLong(
                        DatabaseNode::position
                    )
                );
        }
    }

    static class DatabaseCluster {

        private final DatabaseConfig config;
        private final ReentrantLock lock =
            new ReentrantLock();

        private DatabaseNode primary;

        private final List<DatabaseNode> replicas =
            new ArrayList<>();

        private final ReplicationService replication =
            new ReplicationService();

        private final CacheService cache;

        private final BackupService backupService =
            new BackupService();

        private final FailoverPolicy failoverPolicy =
            new FailoverPolicy();

        private long reads;
        private long writes;
        private long failovers;

        DatabaseCluster(DatabaseConfig config) {
            this.config = config;

            this.primary = new DatabaseNode(
                "enterprise-primary",
                NodeRole.PRIMARY
            );

            replicas.add(
                new DatabaseNode(
                    "enterprise-replica-1",
                    NodeRole.REPLICA
                )
            );

            replicas.add(
                new DatabaseNode(
                    "enterprise-replica-2",
                    NodeRole.REPLICA
                )
            );

            if (config.requiredSynchronousReplicas() >
                replicas.size()) {
                throw new IllegalArgumentException(
                    "Required replica count exceeds cluster capacity"
                );
            }

            this.cache = new CacheService(
                config.cacheCapacity(),
                30000
            );
        }

        void write(String key, String value) {
            lock.lock();

            primary.acquire(config.maximumConnections());

            try {
                long version = Optional.ofNullable(
                    primary.records.get(key)
                )
                .map(record -> record.version() + 1)
                .orElse(1L);

                DatabaseRecord record = new DatabaseRecord(
                    key,
                    value,
                    version,
                    Instant.now()
                );

                long position = replication.append(
                    key,
                    record
                );

                List<DatabaseNode> healthyReplicas =
                    replicas.stream()
                        .filter(node ->
                            node.state == NodeState.HEALTHY
                        )
                        .toList();

                if (
                    config.replicationPolicy() ==
                        ReplicationPolicy.SYNCHRONOUS &&
                    healthyReplicas.size() <
                        config.requiredSynchronousReplicas()
                ) {
                    throw new ReplicationException(
                        "Synchronous replication quorum unavailable"
                    );
                }

                primary.records.put(key, record);
                primary.replicationPosition = position;

                if (
                    config.replicationPolicy() ==
                        ReplicationPolicy.SYNCHRONOUS
                ) {
                    healthyReplicas.stream()
                        .limit(config.requiredSynchronousReplicas())
                        .forEach(replica ->
                            replication.replicate(
                                replica,
                                primary,
                                config.maximumReplicationLag()
                            )
                        );
                }

                cache.invalidate(key);
                writes++;

            } finally {
                primary.release();
                lock.unlock();
            }
        }

        Optional<DatabaseRecord> read(
            String key,
            boolean preferReplica
        ) {
            Optional<DatabaseRecord> cached = cache.get(key);

            if (cached.isPresent()) {
                return cached;
            }

            lock.lock();

            try {
                DatabaseNode selected = primary;

                if (preferReplica) {
                    selected = replicas.stream()
                        .filter(node ->
                            node.state == NodeState.HEALTHY
                        )
                        .filter(node ->
                            primary.replicationPosition -
                                node.replicationPosition <=
                                config.maximumReplicationLag()
                        )
                        .findFirst()
                        .orElse(primary);
                }

                selected.acquire(config.maximumConnections());

                try {
                    Optional<DatabaseRecord> result =
                        selected.read(key);

                    reads++;

                    result.ifPresent(
                        record -> cache.put(key, record)
                    );

                    return result;

                } finally {
                    selected.release();
                }

            } finally {
                lock.unlock();
            }
        }

        void synchronize() {
            lock.lock();

            try {
                for (DatabaseNode replica : replicas) {
                    if (replica.state != NodeState.DOWN) {
                        replication.replicate(
                            replica,
                            primary,
                            config.maximumReplicationLag()
                        );
                    }
                }
            } finally {
                lock.unlock();
            }
        }

        BackupSnapshot backup() {
            lock.lock();

            try {
                return backupService.create(primary);
            } finally {
                lock.unlock();
            }
        }

        void failNode(String nodeId) {
            lock.lock();

            try {
                if (primary.id().equals(nodeId)) {
                    primary.state = NodeState.DOWN;
                    return;
                }

                DatabaseNode node = replicas.stream()
                    .filter(item -> item.id().equals(nodeId))
                    .findFirst()
                    .orElseThrow(() ->
                        new IllegalArgumentException(
                            "Unknown database node"
                        )
                    );

                node.state = NodeState.DOWN;

            } finally {
                lock.unlock();
            }
        }

        void failover() {
            lock.lock();

            try {
                if (primary.state != NodeState.DOWN) {
                    throw new InfrastructureException(
                        "Failover is not required"
                    );
                }

                DatabaseNode promoted = failoverPolicy
                    .select(replicas)
                    .orElseThrow(() ->
                        new InfrastructureException(
                            "No eligible replica for promotion"
                        )
                    );

                DatabaseNode oldPrimary = primary;

                replicas.remove(promoted);

                promoted.role = NodeRole.PRIMARY;

                oldPrimary.role = NodeRole.REPLICA;

                primary = promoted;
                replicas.add(oldPrimary);

                cache.clear();
                failovers++;

            } finally {
                lock.unlock();
            }
        }

        void recover(BackupSnapshot backup) {
            lock.lock();

            try {
                backupService.restore(primary, backup);

                for (DatabaseNode replica : replicas) {
                    replica.records.clear();
                    replica.records.putAll(primary.records);

                    replica.replicationPosition =
                        primary.replicationPosition;

                    if (replica.state != NodeState.DOWN) {
                        replica.state = NodeState.HEALTHY;
                    }
                }

                cache.clear();

            } finally {
                lock.unlock();
            }
        }

        void report() {
            lock.lock();

            try {
                System.out.println("\nCLUSTER REPORT");
                System.out.println(
                    "Primary: " + primary.id()
                );

                List<DatabaseNode> nodes =
                    new ArrayList<>();

                nodes.add(primary);
                nodes.addAll(replicas);

                nodes.forEach(node ->
                    System.out.printf(
                        "%-24s %-10s %-12s position=%d records=%d%n",
                        node.id(),
                        node.role(),
                        node.state(),
                        node.position(),
                        node.recordCount()
                    )
                );

                System.out.println("Reads: " + reads);
                System.out.println("Writes: " + writes);
                System.out.println("Failovers: " + failovers);
                System.out.println("Cache hits: " + cache.hits());
                System.out.println("Cache misses: " + cache.misses());

            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) {

        DatabaseConfig config = new DatabaseConfig(
            ReplicationPolicy.ASYNCHRONOUS,
            0,
            5,
            100,
            500
        );

        DatabaseCluster cluster =
            new DatabaseCluster(config);

        try {
            System.out.println("1. Writing enterprise records");

            cluster.write(
                "customer:1001",
                "name=Arjun;balance=50000"
            );

            cluster.write(
                "customer:1002",
                "name=Riya;balance=75000"
            );

            System.out.println("2. Synchronizing replicas");

            cluster.synchronize();

            System.out.println("3. Cache-backed read");

            System.out.println(
                cluster.read("customer:1001", true)
            );

            System.out.println(
                cluster.read("customer:1001", true)
            );

            System.out.println("4. Creating backup");

            BackupSnapshot backup = cluster.backup();

            System.out.println(
                "Backup ID: " + backup.backupId()
            );

            System.out.println("5. Simulating primary failure");

            String failedPrimary = "enterprise-primary";

            cluster.failNode(failedPrimary);
            cluster.failover();

            System.out.println("6. Post-failover write");

            cluster.write(
                "customer:1003",
                "name=Kabir;balance=95000"
            );

            cluster.synchronize();

            System.out.println("7. Monitoring");

            cluster.report();

            System.out.println("8. Disaster recovery");

            cluster.recover(backup);

            cluster.report();

        } catch (InfrastructureException |
                 IllegalArgumentException error) {

            System.err.println(
                "Infrastructure operation failed: " +
                error.getMessage()
            );

            System.exit(1);
        }
    }
}
