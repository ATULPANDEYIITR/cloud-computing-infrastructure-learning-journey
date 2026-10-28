import java.time.Instant;
import java.time.Duration;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Predicate;
import java.util.stream.Collectors;

/**
 * Enterprise-oriented managed database governance model.
 *
 * The model separates:
 * - database lifecycle state
 * - node roles
 * - maintenance operations
 * - backup policy
 * - health policy
 * - failover policy
 * - production eligibility
 */
public class ManagedCloudDatabase {

    enum DatabaseState {
        AVAILABLE,
        MAINTENANCE,
        DEGRADED,
        FAILED,
        RESTORING
    }

    enum NodeRole {
        PRIMARY,
        REPLICA
    }

    enum MaintenanceState {
        SCHEDULED,
        RUNNING,
        COMPLETED,
        FAILED
    }

    record Metrics(
        double cpuPercent,
        double storagePercent,
        double replicationLagSeconds,
        int connections
    ) {
        boolean healthy() {
            return cpuPercent < 85
                && storagePercent < 90
                && replicationLagSeconds < 30;
        }
    }

    record Backup(
        String id,
        Instant createdAt,
        Instant expiresAt,
        String checksum,
        long sizeGb
    ) {
        boolean validAt(Instant instant) {
            return expiresAt.isAfter(instant)
                && !checksum.isBlank()
                && sizeGb > 0;
        }
    }

    record StatusCheck(
        String name,
        boolean passed,
        String reason
    ) {}

    record GovernanceDecision(
        boolean eligible,
        List<StatusCheck> checks
    ) {}

    static final class DatabaseNode {
        private final String id;
        private final String zone;
        private NodeRole role;
        private String version;
        private DatabaseState state;
        private Metrics metrics;

        DatabaseNode(
            String id,
            String zone,
            NodeRole role,
            String version
        ) {
            this.id = id;
            this.zone = zone;
            this.role = role;
            this.version = version;
            this.state = DatabaseState.AVAILABLE;
            this.metrics = new Metrics(0, 0, 0, 0);
        }

        boolean healthy() {
            return state == DatabaseState.AVAILABLE && metrics.healthy();
        }
    }

    static final class MaintenanceJob {
        private final String id;
        private final String sourceVersion;
        private final String targetVersion;
        private MaintenanceState state;
        private String failureReason;

        MaintenanceJob(
            String sourceVersion,
            String targetVersion
        ) {
            this.id = UUID.randomUUID().toString();
            this.sourceVersion = sourceVersion;
            this.targetVersion = targetVersion;
            this.state = MaintenanceState.SCHEDULED;
        }
    }

    interface GovernancePolicy {
        StatusCheck evaluate(ManagedInstance database);
    }

    static final class BackupRetentionPolicy implements GovernancePolicy {
        private final int minimumDays;

        BackupRetentionPolicy(int minimumDays) {
            if (minimumDays < 1) {
                throw new IllegalArgumentException(
                    "Minimum retention must be positive."
                );
            }
            this.minimumDays = minimumDays;
        }

        @Override
        public StatusCheck evaluate(ManagedInstance database) {
            boolean passed =
                database.backupRetentionDays >= minimumDays;

            return new StatusCheck(
                "backup-retention",
                passed,
                passed
                    ? "Retention meets policy."
                    : "Retention is below policy."
            );
        }
    }

    static final class MultiZonePolicy implements GovernancePolicy {
        @Override
        public StatusCheck evaluate(ManagedInstance database) {
            Set<String> zones = database.nodes.values()
                .stream()
                .map(node -> node.zone)
                .collect(Collectors.toSet());

            boolean passed = zones.size() >= 2;

            return new StatusCheck(
                "multi-zone",
                passed,
                passed
                    ? "Nodes span multiple zones."
                    : "At least two zones are required."
            );
        }
    }

    static final class PrimaryPolicy implements GovernancePolicy {
        @Override
        public StatusCheck evaluate(ManagedInstance database) {
            long count = database.nodes.values()
                .stream()
                .filter(node -> node.role == NodeRole.PRIMARY)
                .count();

            boolean passed = count == 1;

            return new StatusCheck(
                "single-primary",
                passed,
                passed
                    ? "Exactly one primary exists."
                    : "Exactly one primary is required."
            );
        }
    }

    static final class ReplicaAvailabilityPolicy implements GovernancePolicy {
        @Override
        public StatusCheck evaluate(ManagedInstance database) {
            boolean passed = database.nodes.values()
                .stream()
                .anyMatch(
                    node ->
                        node.role == NodeRole.REPLICA
                            && node.healthy()
                );

            return new StatusCheck(
                "failover-capability",
                passed,
                passed
                    ? "Healthy failover candidate exists."
                    : "No healthy replica is available."
            );
        }
    }

    static final class VersionConsistencyPolicy implements GovernancePolicy {
        @Override
        public StatusCheck evaluate(ManagedInstance database) {
            boolean passed = database.nodes.values()
                .stream()
                .allMatch(node -> node.version.equals(database.version));

            return new StatusCheck(
                "version-consistency",
                passed,
                passed
                    ? "All nodes use the current version."
                    : "Node versions are inconsistent."
            );
        }
    }

    static final class ManagedInstance {
        private final String id;
        private final String name;
        private final String region;
        private final int storageGb;
        private final int backupRetentionDays;

        private String version;
        private DatabaseState state;

        private final Map<String, DatabaseNode> nodes =
            new HashMap<>();

        private final Map<String, Backup> backups =
            new HashMap<>();

        private final Map<String, MaintenanceJob> maintenance =
            new HashMap<>();

        ManagedInstance(
            String id,
            String name,
            String region,
            String version,
            int storageGb,
            int backupRetentionDays
        ) {
            if (id.isBlank() || name.isBlank()) {
                throw new IllegalArgumentException(
                    "Database identifiers cannot be blank."
                );
            }

            if (storageGb < 10) {
                throw new IllegalArgumentException(
                    "Minimum storage is 10 GB."
                );
            }

            if (backupRetentionDays < 1 ||
                backupRetentionDays > 35) {
                throw new IllegalArgumentException(
                    "Retention must be between 1 and 35 days."
                );
            }

            this.id = id;
            this.name = name;
            this.region = region;
            this.version = version;
            this.storageGb = storageGb;
            this.backupRetentionDays = backupRetentionDays;
            this.state = DatabaseState.AVAILABLE;
        }

        void addNode(String zone, NodeRole role) {
            if (role == NodeRole.PRIMARY &&
                nodes.values()
                    .stream()
                    .anyMatch(node -> node.role == NodeRole.PRIMARY)) {
                throw new IllegalStateException(
                    "A primary already exists."
                );
            }

            String id = UUID.randomUUID().toString();

            nodes.put(
                id,
                new DatabaseNode(
                    id,
                    zone,
                    role,
                    version
                )
            );
        }

        private DatabaseNode primary() {
            List<DatabaseNode> primaries = nodes.values()
                .stream()
                .filter(node -> node.role == NodeRole.PRIMARY)
                .toList();

            if (primaries.size() != 1) {
                throw new IllegalStateException(
                    "Exactly one primary is required."
                );
            }

            return primaries.get(0);
        }

        void collectMetrics() {
            for (DatabaseNode node : nodes.values()) {
                double cpu = node.role == NodeRole.PRIMARY
                    ? 45
                    : 35;

                double lag = node.role == NodeRole.PRIMARY
                    ? 0
                    : 4;

                node.metrics = new Metrics(
                    cpu,
                    55,
                    lag,
                    80
                );

                node.state = node.metrics.healthy()
                    ? DatabaseState.AVAILABLE
                    : DatabaseState.DEGRADED;
            }
        }

        Backup createBackup(Instant now) {
            if (!primary().healthy()) {
                throw new IllegalStateException(
                    "Cannot back up an unhealthy primary."
                );
            }

            String checksum = UUID.nameUUIDFromBytes(
                (
                    id + ":" +
                    version + ":" +
                    now
                ).getBytes()
            ).toString();

            Backup backup = new Backup(
                UUID.randomUUID().toString(),
                now,
                now.plus(Duration.ofDays(backupRetentionDays)),
                checksum,
                Math.max(1, storageGb / 5)
            );

            backups.put(backup.id(), backup);
            return backup;
        }

        String scheduleMaintenance(String targetVersion) {
            if (targetVersion.isBlank() ||
                targetVersion.equals(version)) {
                throw new IllegalArgumentException(
                    "Target version must differ from current version."
                );
            }

            MaintenanceJob job =
                new MaintenanceJob(version, targetVersion);

            maintenance.put(job.id, job);
            return job.id;
        }

        void executeMaintenance(String jobId) {
            MaintenanceJob job = maintenance.get(jobId);

            if (job == null) {
                throw new IllegalArgumentException(
                    "Maintenance job does not exist."
                );
            }

            if (job.state != MaintenanceState.SCHEDULED) {
                throw new IllegalStateException(
                    "Maintenance job has already been processed."
                );
            }

            job.state = MaintenanceState.RUNNING;
            state = DatabaseState.MAINTENANCE;

            String originalVersion = version;

            try {
                Backup backup = createBackup(Instant.now());

                if (!backup.validAt(Instant.now())) {
                    throw new IllegalStateException(
                        "Pre-maintenance backup validation failed."
                    );
                }

                for (DatabaseNode node : nodes.values()) {
                    node.state = DatabaseState.MAINTENANCE;
                    node.version = job.targetVersion;
                    node.state = DatabaseState.AVAILABLE;
                }

                version = job.targetVersion;
                job.state = MaintenanceState.COMPLETED;
                state = DatabaseState.AVAILABLE;
            } catch (RuntimeException ex) {
                version = originalVersion;
                job.state = MaintenanceState.FAILED;
                job.failureReason = ex.getMessage();
                state = DatabaseState.FAILED;
                throw ex;
            }
        }

        void failover() {
            DatabaseNode oldPrimary = primary();

            DatabaseNode candidate = nodes.values()
                .stream()
                .filter(node ->
                    node.role == NodeRole.REPLICA
                        && node.healthy()
                )
                .min(
                    java.util.Comparator.comparingDouble(
                        node -> node.metrics.replicationLagSeconds()
                    )
                )
                .orElseThrow(
                    () -> new IllegalStateException(
                        "No healthy replica is available."
                    )
                );

            oldPrimary.role = NodeRole.REPLICA;
            oldPrimary.state = DatabaseState.DEGRADED;

            candidate.role = NodeRole.PRIMARY;
            candidate.state = DatabaseState.AVAILABLE;

            state = DatabaseState.AVAILABLE;
        }

        GovernanceDecision evaluate(
            List<GovernancePolicy> policies
        ) {
            List<StatusCheck> checks = policies.stream()
                .map(policy -> policy.evaluate(this))
                .toList();

            boolean eligible = checks.stream()
                .allMatch(StatusCheck::passed);

            return new GovernanceDecision(
                eligible,
                checks
            );
        }

        String report() {
            return """
                Managed database: %s
                Region: %s
                Version: %s
                State: %s
                Nodes: %d
                Backups: %d
                """.formatted(
                    name,
                    region,
                    version,
                    state,
                    nodes.size(),
                    backups.size()
                );
        }
    }

    public static void main(String[] args) {
        ManagedInstance database = new ManagedInstance(
            "orders-prod",
            "orders",
            "ap-south-1",
            "16.4",
            250,
            14
        );

        database.addNode("zone-a", NodeRole.PRIMARY);
        database.addNode("zone-b", NodeRole.REPLICA);
        database.addNode("zone-c", NodeRole.REPLICA);

        database.collectMetrics();

        Backup backup = database.createBackup(Instant.now());

        String maintenanceId =
            database.scheduleMaintenance("16.5");

        database.executeMaintenance(maintenanceId);

        database.collectMetrics();

        List<GovernancePolicy> policies = List.of(
            new BackupRetentionPolicy(7),
            new MultiZonePolicy(),
            new PrimaryPolicy(),
            new ReplicaAvailabilityPolicy(),
            new VersionConsistencyPolicy()
        );

        GovernanceDecision decision =
            database.evaluate(policies);

        System.out.println(database.report());
        System.out.println("Backup valid: " +
            backup.validAt(Instant.now()));
        System.out.println(
            "Production eligible: " + decision.eligible()
        );

        for (StatusCheck check : decision.checks()) {
            System.out.printf(
                "%s: %s - %s%n",
                check.name(),
                check.passed() ? "PASS" : "FAIL",
                check.reason()
            );
        }

        if (!decision.eligible()) {
            System.err.println(
                "Database is not eligible for production operation."
            );
            System.exit(2);
        }
    }
}
