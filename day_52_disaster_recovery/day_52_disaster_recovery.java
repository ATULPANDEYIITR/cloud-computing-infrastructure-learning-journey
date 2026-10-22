import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Enterprise-oriented disaster recovery governance model.
 *
 * Covers:
 * - RPO/RTO policies
 * - backup lifecycle
 * - restore validation
 * - pilot light
 * - warm standby
 * - active-active
 * - explicit state transitions
 * - failover decisions
 * - recovery validation gates
 */
public class DisasterRecoveryEnterprise {

    enum Architecture {
        PILOT_LIGHT,
        WARM_STANDBY,
        ACTIVE_ACTIVE
    }

    enum NodeState {
        HEALTHY,
        FAILED,
        RECOVERING
    }

    enum BackupType {
        FULL,
        INCREMENTAL
    }

    enum RecoveryState {
        NORMAL,
        FAILOVER_REQUIRED,
        RECOVERING,
        RECOVERED,
        RECOVERY_FAILED
    }

    record RecoveryPolicy(
            String service,
            Duration rpo,
            Duration rto
    ) {
        RecoveryPolicy {
            Objects.requireNonNull(service, "service");
            Objects.requireNonNull(rpo, "rpo");
            Objects.requireNonNull(rto, "rto");

            if (service.isBlank()) {
                throw new IllegalArgumentException("Service cannot be blank");
            }
            if (rpo.isNegative()) {
                throw new IllegalArgumentException("RPO cannot be negative");
            }
            if (rto.isZero() || rto.isNegative()) {
                throw new IllegalArgumentException("RTO must be positive");
            }
        }
    }

    record Backup(
            String id,
            Instant createdAt,
            BackupType type,
            long version,
            String checksum
    ) {
        Backup {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(createdAt, "createdAt");
            Objects.requireNonNull(type, "type");
            Objects.requireNonNull(checksum, "checksum");

            if (id.isBlank()) {
                throw new IllegalArgumentException("Backup ID cannot be blank");
            }
            if (version <= 0) {
                throw new IllegalArgumentException("Backup version must be positive");
            }
            if (checksum.isBlank()) {
                throw new IllegalArgumentException("Checksum cannot be blank");
            }
        }
    }

    record RestorePlan(
            Backup recoveryPoint,
            Duration estimatedRestoreTime,
            boolean checksumValid
    ) {}

    record RecoveryDecision(
            boolean successful,
            boolean rpoSatisfied,
            boolean rtoSatisfied,
            Duration observedRpo,
            Duration observedRto,
            String explanation
    ) {}

    static final class RecoveryNode {
        private final String name;
        private final Architecture architecture;
        private NodeState state;
        private boolean servingTraffic;
        private Instant lastSynchronizedAt;

        RecoveryNode(
                String name,
                Architecture architecture,
                NodeState state,
                boolean servingTraffic,
                Instant lastSynchronizedAt
        ) {
            this.name = Objects.requireNonNull(name);
            this.architecture = Objects.requireNonNull(architecture);
            this.state = Objects.requireNonNull(state);
            this.servingTraffic = servingTraffic;
            this.lastSynchronizedAt = lastSynchronizedAt;
        }

        void fail() {
            state = NodeState.FAILED;
            servingTraffic = false;
        }

        void beginRecovery() {
            if (state != NodeState.FAILED) {
                throw new IllegalStateException(
                        "Only a failed node can enter recovery"
                );
            }
            state = NodeState.RECOVERING;
        }

        void markRecovered(Instant synchronizationTime) {
            if (state != NodeState.RECOVERING) {
                throw new IllegalStateException(
                        "Node must be recovering before it can become healthy"
                );
            }

            state = NodeState.HEALTHY;
            servingTraffic = true;
            lastSynchronizedAt = synchronizationTime;
        }

        boolean isHealthyAndServing() {
            return state == NodeState.HEALTHY && servingTraffic;
        }

        String name() {
            return name;
        }

        Architecture architecture() {
            return architecture;
        }

        NodeState state() {
            return state;
        }

        boolean servingTraffic() {
            return servingTraffic;
        }
    }

    static final class BackupRepository {
        private final List<Backup> backups = new ArrayList<>();

        void add(Backup backup) {
            if (backups.stream().anyMatch(
                    existing -> existing.id().equals(backup.id()))) {
                throw new IllegalArgumentException(
                        "Duplicate backup ID: " + backup.id()
                );
            }

            backups.add(backup);

            backups.sort(
                    java.util.Comparator.comparing(Backup::createdAt)
            );
        }

        Optional<Backup> latestBefore(Instant failureTime) {
            return backups.stream()
                    .filter(backup ->
                            !backup.createdAt().isAfter(failureTime))
                    .reduce((first, second) -> second);
        }

        List<Backup> all() {
            return List.copyOf(backups);
        }
    }

    interface RecoveryValidator {
        boolean validate(Backup backup);

        String name();
    }

    static final class ChecksumValidator implements RecoveryValidator {
        @Override
        public boolean validate(Backup backup) {
            return backup.checksum().matches(
                    "sha256:[0-9a-fA-F]{8,}"
            );
        }

        @Override
        public String name() {
            return "backup-checksum";
        }
    }

    static final class RecoveryEligibilityService {
        private final RecoveryPolicy policy;
        private final BackupRepository backups;
        private final List<RecoveryValidator> validators;

        RecoveryEligibilityService(
                RecoveryPolicy policy,
                BackupRepository backups,
                List<RecoveryValidator> validators
        ) {
            this.policy = Objects.requireNonNull(policy);
            this.backups = Objects.requireNonNull(backups);
            this.validators = List.copyOf(validators);
        }

        Optional<RestorePlan> buildPlan(
                Instant failureTime,
                Architecture architecture
        ) {
            Optional<Backup> selected =
                    backups.latestBefore(failureTime);

            if (selected.isEmpty()) {
                return Optional.empty();
            }

            Backup backup = selected.get();

            boolean valid = validators.stream()
                    .allMatch(validator -> validator.validate(backup));

            if (!valid) {
                return Optional.of(
                        new RestorePlan(
                                backup,
                                architectureRestoreDuration(architecture),
                                false
                        )
                );
            }

            return Optional.of(
                    new RestorePlan(
                            backup,
                            architectureRestoreDuration(architecture),
                            true
                    )
            );
        }

        RecoveryDecision evaluate(
                Instant failureTime,
                Architecture architecture
        ) {
            Optional<RestorePlan> plan =
                    buildPlan(failureTime, architecture);

            if (plan.isEmpty()) {
                return new RecoveryDecision(
                        false,
                        false,
                        false,
                        null,
                        null,
                        "No backup exists at or before the failure."
                );
            }

            RestorePlan restorePlan = plan.get();

            Duration observedRpo = Duration.between(
                    restorePlan.recoveryPoint().createdAt(),
                    failureTime
            );

            Duration observedRto =
                    restorePlan.estimatedRestoreTime();

            boolean rpoSatisfied =
                    !observedRpo.minus(policy.rpo()).isNegative();

            rpoSatisfied = observedRpo.compareTo(policy.rpo()) <= 0;

            boolean rtoSatisfied =
                    observedRto.compareTo(policy.rto()) <= 0;

            boolean successful =
                    restorePlan.checksumValid()
                            && rpoSatisfied
                            && rtoSatisfied;

            String explanation;

            if (!restorePlan.checksumValid()) {
                explanation = "Backup integrity validation failed.";
            } else if (!rpoSatisfied) {
                explanation = "Observed data loss exceeds the RPO.";
            } else if (!rtoSatisfied) {
                explanation = "Estimated restoration exceeds the RTO.";
            } else {
                explanation = "Recovery plan satisfies the defined policy.";
            }

            return new RecoveryDecision(
                    successful,
                    rpoSatisfied,
                    rtoSatisfied,
                    observedRpo,
                    observedRto,
                    explanation
            );
        }

        private Duration architectureRestoreDuration(
                Architecture architecture
        ) {
            return switch (architecture) {
                case PILOT_LIGHT -> Duration.ofMinutes(45);
                case WARM_STANDBY -> Duration.ofMinutes(18);
                case ACTIVE_ACTIVE -> Duration.ofMinutes(2);
            };
        }
    }

    static final class FailoverService {
        private final Architecture architecture;
        private RecoveryState state = RecoveryState.NORMAL;
        private final List<RecoveryNode> nodes;

        FailoverService(
                Architecture architecture,
                List<RecoveryNode> nodes
        ) {
            this.architecture = Objects.requireNonNull(architecture);
            this.nodes = new ArrayList<>(nodes);

            if (this.nodes.isEmpty()) {
                throw new IllegalArgumentException(
                        "At least one recovery node is required"
                );
            }
        }

        void declareFailure(String nodeName) {
            RecoveryNode node = findNode(nodeName);
            node.fail();
            state = RecoveryState.FAILOVER_REQUIRED;
        }

        boolean executeFailover(String failedNodeName) {
            RecoveryNode failed = findNode(failedNodeName);

            state = RecoveryState.RECOVERING;

            if (architecture == Architecture.ACTIVE_ACTIVE) {
                boolean survivingCapacity = nodes.stream()
                        .filter(node -> !node.name().equals(failed.name()))
                        .anyMatch(RecoveryNode::isHealthyAndServing);

                if (survivingCapacity) {
                    state = RecoveryState.RECOVERED;
                    return true;
                }

                state = RecoveryState.RECOVERY_FAILED;
                return false;
            }

            failed.beginRecovery();
            failed.markRecovered(Instant.now());
            state = RecoveryState.RECOVERED;
            return true;
        }

        Map<String, String> topology() {
            return nodes.stream().collect(
                    Collectors.toMap(
                            RecoveryNode::name,
                            node -> node.state()
                                    + ", serving="
                                    + node.servingTraffic()
                    )
            );
        }

        RecoveryState state() {
            return state;
        }

        private RecoveryNode findNode(String name) {
            return nodes.stream()
                    .filter(node -> node.name().equals(name))
                    .findFirst()
                    .orElseThrow(() ->
                            new IllegalArgumentException(
                                    "Unknown node: " + name
                            ));
        }
    }

    static BackupRepository createBackups() {
        BackupRepository repository = new BackupRepository();

        repository.add(new Backup(
                "full-001",
                Instant.parse("2026-10-22T00:00:00Z"),
                BackupType.FULL,
                1000,
                "sha256:11111111"
        ));

        repository.add(new Backup(
                "incremental-002",
                Instant.parse("2026-10-22T00:30:00Z"),
                BackupType.INCREMENTAL,
                1001,
                "sha256:22222222"
        ));

        repository.add(new Backup(
                "incremental-003",
                Instant.parse("2026-10-22T01:00:00Z"),
                BackupType.INCREMENTAL,
                1002,
                "sha256:33333333"
        ));

        repository.add(new Backup(
                "incremental-004",
                Instant.parse("2026-10-22T01:30:00Z"),
                BackupType.INCREMENTAL,
                1003,
                "sha256:44444444"
        ));

        return repository;
    }

    static void runScenario(
            Architecture architecture,
            RecoveryPolicy policy
    ) {
        BackupRepository backups = createBackups();

        RecoveryEligibilityService eligibility =
                new RecoveryEligibilityService(
                        policy,
                        backups,
                        List.of(new ChecksumValidator())
                );

        Instant failureTime =
                Instant.parse("2026-10-22T01:45:00Z");

        RecoveryDecision decision =
                eligibility.evaluate(
                        failureTime,
                        architecture
                );

        System.out.println(
                "\n=== " + architecture + " ==="
        );
        System.out.println(
                "Observed RPO: " + decision.observedRpo()
        );
        System.out.println(
                "Observed RTO: " + decision.observedRto()
        );
        System.out.println(
                "RPO satisfied: " + decision.rpoSatisfied()
        );
        System.out.println(
                "RTO satisfied: " + decision.rtoSatisfied()
        );
        System.out.println(
                "Recovery successful: " + decision.successful()
        );
        System.out.println(
                "Explanation: " + decision.explanation()
        );

        List<RecoveryNode> nodes = List.of(
                new RecoveryNode(
                        "region-a",
                        architecture,
                        NodeState.HEALTHY,
                        true,
                        failureTime.minus(Duration.ofMinutes(15))
                ),
                new RecoveryNode(
                        "region-b",
                        architecture,
                        NodeState.HEALTHY,
                        architecture == Architecture.ACTIVE_ACTIVE,
                        failureTime.minus(Duration.ofMinutes(15))
                )
        );

        FailoverService failover =
                new FailoverService(architecture, nodes);

        failover.declareFailure("region-a");

        boolean successful =
                failover.executeFailover("region-a");

        System.out.println(
                "Failover successful: " + successful
        );
        System.out.println(
                "Recovery state: " + failover.state()
        );
        System.out.println(
                "Topology: " + failover.topology()
        );
    }

    public static void main(String[] args) {
        runScenario(
                Architecture.PILOT_LIGHT,
                new RecoveryPolicy(
                        "Order Processing",
                        Duration.ofMinutes(30),
                        Duration.ofMinutes(60)
                )
        );

        runScenario(
                Architecture.WARM_STANDBY,
                new RecoveryPolicy(
                        "Order Processing",
                        Duration.ofMinutes(30),
                        Duration.ofMinutes(30)
                )
        );

        runScenario(
                Architecture.ACTIVE_ACTIVE,
                new RecoveryPolicy(
                        "Order Processing",
                        Duration.ofMinutes(5),
                        Duration.ofMinutes(5)
                )
        );

        try {
            new RecoveryPolicy(
                    "",
                    Duration.ofMinutes(10),
                    Duration.ofMinutes(20)
            );
        } catch (IllegalArgumentException exception) {
            System.out.println(
                    "\nPolicy validation rejected invalid configuration: "
                            + exception.getMessage()
            );
        }

        BackupRepository repository = createBackups();

        Set<BackupType> backupTypes =
                EnumSet.allOf(BackupType.class);

        System.out.println(
                "\nSupported backup types: " + backupTypes
        );

        System.out.println(
                "Configured backups: "
                        + repository.all().size()
        );
    }
}
