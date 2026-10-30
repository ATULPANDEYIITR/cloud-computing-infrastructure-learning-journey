import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.locks.ReentrantLock;
import java.util.stream.Collectors;

/*
 * Database High Availability: enterprise repository and failover domain.
 *
 * This Java 17 application models an active-passive database cluster with
 * explicit domain types, validation, health observations, independent
 * fencing confirmation, quorum rules, state transitions, and audit events.
 *
 * The program is an executable control-plane model, not a database driver
 * or a deployment tool for a real database platform.
 */

public class DatabaseHighAvailability {

    enum NodeRole {
        PRIMARY,
        REPLICA
    }

    enum HealthStatus {
        HEALTHY,
        DEGRADED,
        UNREACHABLE,
        UNKNOWN
    }

    enum ReplicationMode {
        SYNCHRONOUS,
        ASYNCHRONOUS
    }

    record HealthObservation(
        HealthStatus status,
        Instant observedAt,
        String source
    ) {
        HealthObservation {
            Objects.requireNonNull(status, "Health status is required");
            Objects.requireNonNull(observedAt, "Observation time is required");

            if (source == null || source.isBlank()) {
                throw new IllegalArgumentException("Observation source is required");
            }
        }
    }

    record FailoverPolicy(
        int quorumRequired,
        long maxReplicationLagMs,
        boolean requireSynchronousReplica,
        Duration maxObservationAge,
        int minimumAvailabilityZones
    ) {
        FailoverPolicy {
            if (quorumRequired < 1) {
                throw new IllegalArgumentException("Quorum must be positive");
            }
            if (maxReplicationLagMs < 0) {
                throw new IllegalArgumentException("Replication lag cannot be negative");
            }
            if (maxObservationAge == null ||
                maxObservationAge.isZero() ||
                maxObservationAge.isNegative()) {
                throw new IllegalArgumentException("Observation age must be positive");
            }
            if (minimumAvailabilityZones < 2) {
                throw new IllegalArgumentException("At least two zones are required");
            }
        }
    }

    record Decision(
        boolean eligible,
        List<String> reasons,
        int healthyVoters,
        String candidateId,
        long candidateLagMs
    ) {
        Decision {
            reasons = List.copyOf(reasons);
        }
    }

    record FencingReceipt(
        String nodeId,
        String proofId,
        Instant issuedAt
    ) {
        FencingReceipt {
            if (nodeId == null || nodeId.isBlank() ||
                proofId == null || proofId.isBlank()) {
                throw new IllegalArgumentException("Invalid fencing receipt");
            }
            Objects.requireNonNull(issuedAt, "Fencing timestamp is required");
        }
    }

    record FailoverEvent(
        String clusterId,
        String oldPrimaryId,
        String newPrimaryId,
        long previousEpoch,
        long newEpoch,
        long fencingToken,
        int healthyVoters,
        Instant occurredAt,
        String fencingProofId
    ) {}

    @FunctionalInterface
    interface FencingService {
        FencingReceipt fence(DatabaseNode node);
    }

    static final class DatabaseNode {
        private final String id;
        private final String zone;
        private final boolean votingMember;
        private final ReplicationMode replicationMode;

        private NodeRole role;
        private long replicationLagMs;
        private HealthObservation healthObservation;
        private boolean fenced;
        private long fencingToken;

        DatabaseNode(
            String id,
            String zone,
            NodeRole role,
            boolean votingMember,
            ReplicationMode replicationMode,
            long replicationLagMs,
            HealthObservation healthObservation,
            boolean fenced,
            long fencingToken
        ) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Node ID is required");
            }
            if (zone == null || zone.isBlank()) {
                throw new IllegalArgumentException("Availability zone is required");
            }
            if (replicationLagMs < 0 || fencingToken < 0) {
                throw new IllegalArgumentException("Invalid node metrics");
            }

            this.id = id;
            this.zone = zone;
            this.role = Objects.requireNonNull(role);
            this.votingMember = votingMember;
            this.replicationMode = Objects.requireNonNull(replicationMode);
            this.replicationLagMs = replicationLagMs;
            this.healthObservation = Objects.requireNonNull(healthObservation);
            this.fenced = fenced;
            this.fencingToken = fencingToken;
        }

        String id() {
            return id;
        }

        String zone() {
            return zone;
        }

        NodeRole role() {
            return role;
        }

        HealthObservation healthObservation() {
            return healthObservation;
        }

        long replicationLagMs() {
            return replicationLagMs;
        }

        ReplicationMode replicationMode() {
            return replicationMode;
        }

        boolean fenced() {
            return fenced;
        }

        long fencingToken() {
            return fencingToken;
        }

        void recordObservation(
            HealthObservation observation,
            long replicationLagMs
        ) {
            Objects.requireNonNull(observation);
            if (replicationLagMs < 0) {
                throw new IllegalArgumentException("Replication lag cannot be negative");
            }

            this.healthObservation = observation;
            this.replicationLagMs = replicationLagMs;
        }
    }

    static final class DatabaseCluster {
        private final String id;
        private final Map<String, DatabaseNode> nodes;
        private String primaryNodeId;
        private long epoch;
        private long fencingToken;

        DatabaseCluster(
            String id,
            List<DatabaseNode> members,
            String primaryNodeId,
            long epoch,
            long fencingToken,
            FailoverPolicy policy
        ) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Cluster ID is required");
            }
            if (epoch < 1 || fencingToken < 0) {
                throw new IllegalArgumentException("Invalid cluster version");
            }

            this.id = id;
            this.primaryNodeId = Objects.requireNonNull(primaryNodeId);
            this.epoch = epoch;
            this.fencingToken = fencingToken;
            this.nodes = new LinkedHashMap<>();

            for (DatabaseNode node : members) {
                if (nodes.putIfAbsent(node.id(), node) != null) {
                    throw new IllegalArgumentException(
                        "Duplicate node identifier: " + node.id()
                    );
                }
            }

            validateTopology(policy);
        }

        private void validateTopology(FailoverPolicy policy) {
            if (nodes.size() < 2 || !nodes.containsKey(primaryNodeId)) {
                throw new IllegalArgumentException("Invalid cluster membership");
            }

            long primaryCount = nodes.values().stream()
                .filter(node -> node.role() == NodeRole.PRIMARY)
                .count();

            long voters = nodes.values().stream()
                .filter(node -> node.votingMember)
                .count();

            Set<String> zones = nodes.values().stream()
                .map(DatabaseNode::zone)
                .collect(Collectors.toSet());

            if (primaryCount != 1 ||
                nodes.get(primaryNodeId).role() != NodeRole.PRIMARY) {
                throw new IllegalArgumentException(
                    "Cluster must have exactly one identified primary"
                );
            }
            if (policy.quorumRequired() > voters) {
                throw new IllegalArgumentException("Quorum exceeds voting membership");
            }
            if (zones.size() < policy.minimumAvailabilityZones()) {
                throw new IllegalArgumentException(
                    "Cluster does not meet the availability-zone requirement"
                );
            }
        }

        DatabaseNode node(String nodeId) {
            return nodes.get(nodeId);
        }

        List<DatabaseNode> members() {
            return List.copyOf(nodes.values());
        }

        String primaryNodeId() {
            return primaryNodeId;
        }

        long epoch() {
            return epoch;
        }
    }

    static final class FailoverService {
        private final DatabaseCluster cluster;
        private final FailoverPolicy policy;
        private final FencingService fencingService;
        private final ReentrantLock promotionLock = new ReentrantLock();
        private final List<FailoverEvent> auditEvents = new ArrayList<>();

        FailoverService(
            DatabaseCluster cluster,
            FailoverPolicy policy,
            FencingService fencingService
        ) {
            this.cluster = Objects.requireNonNull(cluster);
            this.policy = Objects.requireNonNull(policy);
            this.fencingService = Objects.requireNonNull(fencingService);
        }

        private boolean isFresh(DatabaseNode node, Instant now) {
            Duration age = Duration.between(
                node.healthObservation().observedAt(),
                now
            );

            return !age.isNegative() &&
                age.compareTo(policy.maxObservationAge()) <= 0;
        }

        Decision evaluate(String candidateId, Instant now) {
            DatabaseNode candidate = cluster.node(candidateId);

            if (candidate == null) {
                return new Decision(
                    false,
                    List.of("candidate_not_found"),
                    0,
                    candidateId,
                    0
                );
            }

            DatabaseNode primary = cluster.node(cluster.primaryNodeId());
            List<String> reasons = new ArrayList<>();

            if (candidateId.equals(cluster.primaryNodeId())) {
                reasons.add("candidate_is_already_primary");
            }
            if (candidate.role() != NodeRole.REPLICA) {
                reasons.add("candidate_is_not_a_replica");
            }
            if (candidate.healthObservation().status() != HealthStatus.HEALTHY) {
                reasons.add("candidate_is_not_healthy");
            }
            if (!isFresh(candidate, now)) {
                reasons.add("candidate_observation_is_stale");
            }
            if (policy.requireSynchronousReplica() &&
                candidate.replicationMode() != ReplicationMode.SYNCHRONOUS) {
                reasons.add("candidate_is_not_synchronous");
            }
            if (candidate.replicationLagMs() > policy.maxReplicationLagMs()) {
                reasons.add("candidate_lag_exceeds_policy");
            }

            if (primary.healthObservation().status() == HealthStatus.HEALTHY &&
                isFresh(primary, now)) {
                reasons.add("current_primary_is_still_healthy");
            }
            if (!primary.fenced()) {
                reasons.add("current_primary_has_not_been_fenced");
            }

            int healthyVoters = (int) cluster.members().stream()
                .filter(node -> node.votingMember)
                .filter(node ->
                    node.healthObservation().status() == HealthStatus.HEALTHY
                )
                .filter(node -> isFresh(node, now))
                .count();

            if (healthyVoters < policy.quorumRequired()) {
                reasons.add("healthy_voter_quorum_not_reached");
            }

            return new Decision(
                reasons.isEmpty(),
                reasons,
                healthyVoters,
                candidateId,
                candidate.replicationLagMs()
            );
        }

        FailoverEvent failover(String candidateId, long expectedEpoch) {
            promotionLock.lock();

            try {
                if (expectedEpoch != cluster.epoch) {
                    throw new IllegalStateException(
                        "Stale epoch: expected " + expectedEpoch +
                        ", current " + cluster.epoch
                    );
                }

                DatabaseNode oldPrimary = cluster.node(cluster.primaryNodeId());
                if (oldPrimary == null) {
                    throw new IllegalStateException("Current primary is missing");
                }

                String proofId = "previously-fenced";

                // A successful infrastructure response is required before
                // the former primary is marked as fenced in cluster state.
                if (!oldPrimary.fenced) {
                    FencingReceipt receipt = fencingService.fence(oldPrimary);

                    if (!receipt.nodeId().equals(oldPrimary.id())) {
                        throw new IllegalStateException(
                            "Fencing receipt refers to a different node"
                        );
                    }

                    oldPrimary.fenced = true;
                    proofId = receipt.proofId();
                }

                Instant decisionTime = Instant.now();
                Decision decision = evaluate(candidateId, decisionTime);

                if (!decision.eligible()) {
                    throw new IllegalStateException(
                        "Promotion rejected: " +
                        String.join(", ", decision.reasons())
                    );
                }

                DatabaseNode newPrimary = cluster.node(candidateId);
                long previousEpoch = cluster.epoch;
                long nextEpoch = previousEpoch + 1;
                long nextToken = cluster.fencingToken + 1;

                // State changes occur under the same lock as validation.
                oldPrimary.role = NodeRole.REPLICA;
                newPrimary.role = NodeRole.PRIMARY;
                newPrimary.fenced = false;
                newPrimary.fencingToken = nextToken;

                cluster.primaryNodeId = newPrimary.id();
                cluster.epoch = nextEpoch;
                cluster.fencingToken = nextToken;

                FailoverEvent event = new FailoverEvent(
                    cluster.id,
                    oldPrimary.id(),
                    newPrimary.id(),
                    previousEpoch,
                    nextEpoch,
                    nextToken,
                    decision.healthyVoters(),
                    decisionTime,
                    proofId
                );

                auditEvents.add(event);
                return event;
            } finally {
                promotionLock.unlock();
            }
        }

        List<FailoverEvent> auditEvents() {
            return List.copyOf(auditEvents);
        }

        void printState() {
            System.out.println("\nCluster: " + cluster.id);
            System.out.println("Primary: " + cluster.primaryNodeId());
            System.out.println("Epoch: " + cluster.epoch());

            for (DatabaseNode node : cluster.members()) {
                System.out.printf(
                    "Node %s | zone=%s | role=%s | health=%s | " +
                    "replication=%s | lag_ms=%d | fenced=%s | token=%d%n",
                    node.id(),
                    node.zone(),
                    node.role(),
                    node.healthObservation().status(),
                    node.replicationMode(),
                    node.replicationLagMs(),
                    node.fenced(),
                    node.fencingToken()
                );
            }
        }
    }

    public static void main(String[] args) {
        Instant now = Instant.now();

        FailoverPolicy policy = new FailoverPolicy(
            2,
            100,
            true,
            Duration.ofSeconds(30),
            3
        );

        List<DatabaseNode> nodes = List.of(
            new DatabaseNode(
                "db-az1-primary",
                "availability-zone-a",
                NodeRole.PRIMARY,
                true,
                ReplicationMode.SYNCHRONOUS,
                0,
                new HealthObservation(
                    HealthStatus.UNREACHABLE,
                    now,
                    "regional-monitor"
                ),
                false,
                14
            ),
            new DatabaseNode(
                "db-az2-replica",
                "availability-zone-b",
                NodeRole.REPLICA,
                true,
                ReplicationMode.SYNCHRONOUS,
                15,
                new HealthObservation(
                    HealthStatus.HEALTHY,
                    now,
                    "regional-monitor"
                ),
                false,
                0
            ),
            new DatabaseNode(
                "db-az3-replica",
                "availability-zone-c",
                NodeRole.REPLICA,
                true,
                ReplicationMode.ASYNCHRONOUS,
                160,
                new HealthObservation(
                    HealthStatus.HEALTHY,
                    now,
                    "regional-monitor"
                ),
                false,
                0
            )
        );

        DatabaseCluster cluster = new DatabaseCluster(
            "orders-production",
            nodes,
            "db-az1-primary",
            7,
            14,
            policy
        );

        // This adapter represents an independently authenticated fencing
        // service. A production adapter must verify that write access to the
        // former primary has actually been revoked.
        FencingService fencingService = node -> new FencingReceipt(
            node.id(),
            "fencing-proof-" + node.id(),
            Instant.now()
        );

        FailoverService service = new FailoverService(
            cluster,
            policy,
            fencingService
        );

        System.out.println("DATABASE HIGH AVAILABILITY: ENTERPRISE MODEL");

        Decision delayedDecision = service.evaluate(
            "db-az3-replica",
            now
        );

        System.out.println("\nAsynchronous replica:");
        System.out.println(delayedDecision);

        if (delayedDecision.eligible()) {
            throw new IllegalStateException(
                "An over-lagged asynchronous replica must not be promoted"
            );
        }

        try {
            service.failover("db-az3-replica", 7);
        } catch (IllegalStateException exception) {
            System.out.println("\nExpected candidate rejection:");
            System.out.println(exception.getMessage());
        }

        // The former primary remains fenced after the rejected attempt.
        Decision preferredDecision = service.evaluate(
            "db-az2-replica",
            Instant.now()
        );

        System.out.println("\nSynchronous replica:");
        System.out.println(preferredDecision);

        if (!preferredDecision.eligible()) {
            throw new IllegalStateException(
                "Expected synchronous replica is not eligible"
            );
        }

        FailoverEvent event = service.failover(
            "db-az2-replica",
            7
        );

        System.out.println("\nPromotion event:");
        System.out.println(event);

        service.printState();

        System.out.println("\nAudit events:");
        service.auditEvents().forEach(System.out::println);

        try {
            service.failover("db-az3-replica", 7);
        } catch (IllegalStateException exception) {
            System.out.println("\nExpected stale-epoch rejection:");
            System.out.println(exception.getMessage());
        }
    }
}
