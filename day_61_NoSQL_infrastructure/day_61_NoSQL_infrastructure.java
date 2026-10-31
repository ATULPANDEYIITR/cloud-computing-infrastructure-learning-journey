import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Queue;
import java.util.Set;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class NoSqlInfrastructureCaseStudy {

    enum Consistency {
        STRONG,
        EVENTUAL
    }

    enum ReviewState {
        ACCEPTED,
        REJECTED,
        STALE
    }

    record VersionedValue(String value, long version, Instant updatedAt) {}

    record Document(
        String id,
        String name,
        String department,
        Set<String> capabilities
    ) {
        Document {
            Objects.requireNonNull(id);
            Objects.requireNonNull(name);
            Objects.requireNonNull(department);
            capabilities = Set.copyOf(capabilities);

            if (id.isBlank() || name.isBlank() || department.isBlank()) {
                throw new ValidationException("Required document fields are blank");
            }
        }
    }

    record ReviewDecision(
        String reviewer,
        ReviewState state,
        String reason
    ) {}

    static class ValidationException extends RuntimeException {
        ValidationException(String message) {
            super(message);
        }
    }

    static class ConflictException extends RuntimeException {
        ConflictException(String message) {
            super(message);
        }
    }

    static final class KeyValueService {
        private final Map<String, VersionedValue> data = new HashMap<>();

        synchronized long put(
            String key,
            String value,
            Optional<Long> expectedVersion
        ) {
            validateKey(key);

            VersionedValue current = data.get(key);
            long actualVersion = current == null ? 0 : current.version();

            if (expectedVersion.isPresent()
                && expectedVersion.get() != actualVersion) {
                throw new ConflictException(
                    "Optimistic concurrency check failed"
                );
            }

            long nextVersion = actualVersion + 1;

            data.put(
                key,
                new VersionedValue(
                    value,
                    nextVersion,
                    Instant.now()
                )
            );

            return nextVersion;
        }

        synchronized Optional<VersionedValue> get(String key) {
            validateKey(key);
            return Optional.ofNullable(data.get(key));
        }
    }

    static final class DocumentService {
        private final Map<String, Document> documents = new HashMap<>();

        void save(Document document) {
            if (documents.containsKey(document.id())) {
                throw new ConflictException(
                    "Duplicate document: " + document.id()
                );
            }

            documents.put(document.id(), document);
        }

        List<Document> query(Predicate<Document> condition) {
            return documents.values()
                .stream()
                .filter(condition)
                .collect(Collectors.toUnmodifiableList());
        }
    }

    static final class WideColumnService {
        private final Map<
            String,
            Map<String, Map<String, Object>>
        > partitions = new HashMap<>();

        void upsert(
            String partitionKey,
            String clusteringKey,
            Map<String, Object> columns
        ) {
            validateKey(partitionKey);
            validateKey(clusteringKey);

            partitions
                .computeIfAbsent(partitionKey, ignored -> new HashMap<>())
                .computeIfAbsent(clusteringKey, ignored -> new HashMap<>())
                .putAll(columns);
        }

        List<Map<String, Object>> queryPartition(String partitionKey) {
            Map<String, Map<String, Object>> partition =
                partitions.getOrDefault(
                    partitionKey,
                    Collections.emptyMap()
                );

            return partition.entrySet()
                .stream()
                .sorted(Map.Entry.comparingByKey())
                .map(entry -> {
                    Map<String, Object> row = new HashMap<>();
                    row.put("clusteringKey", entry.getKey());
                    row.putAll(entry.getValue());
                    return Map.copyOf(row);
                })
                .toList();
        }
    }

    static final class GraphService {
        private final Map<String, Set<String>> adjacency = new HashMap<>();

        void addNode(String node) {
            validateKey(node);
            adjacency.putIfAbsent(node, new HashSet<>());
        }

        void addEdge(String source, String target) {
            if (!adjacency.containsKey(source)
                || !adjacency.containsKey(target)) {
                throw new ValidationException(
                    "Graph endpoints must exist"
                );
            }

            adjacency.get(source).add(target);
        }

        Optional<List<String>> shortestPath(
            String source,
            String target
        ) {
            if (!adjacency.containsKey(source)
                || !adjacency.containsKey(target)) {
                return Optional.empty();
            }

            Queue<List<String>> queue = new ArrayDeque<>();
            Set<String> visited = new HashSet<>();

            queue.add(List.of(source));
            visited.add(source);

            while (!queue.isEmpty()) {
                List<String> path = queue.remove();
                String node = path.get(path.size() - 1);

                if (node.equals(target)) {
                    return Optional.of(path);
                }

                for (String next : adjacency.get(node)) {
                    if (visited.add(next)) {
                        List<String> nextPath =
                            new ArrayList<>(path);
                        nextPath.add(next);
                        queue.add(List.copyOf(nextPath));
                    }
                }
            }

            return Optional.empty();
        }
    }

    static final class RepositoryPolicy {
        private final int minimumApprovals;
        private final Set<String> requiredChecks;

        RepositoryPolicy(
            int minimumApprovals,
            Set<String> requiredChecks
        ) {
            if (minimumApprovals < 0) {
                throw new ValidationException(
                    "Approval requirement cannot be negative"
                );
            }

            this.minimumApprovals = minimumApprovals;
            this.requiredChecks = Set.copyOf(requiredChecks);
        }

        boolean eligible(
            List<ReviewDecision> reviews,
            Map<String, Boolean> checks
        ) {
            long validApprovals = reviews.stream()
                .filter(review ->
                    review.state() == ReviewState.ACCEPTED)
                .count();

            boolean checksPass = requiredChecks.stream()
                .allMatch(check -> Boolean.TRUE.equals(checks.get(check)));

            boolean noRejectedReview = reviews.stream()
                .noneMatch(review ->
                    review.state() == ReviewState.REJECTED);

            return validApprovals >= minimumApprovals
                && checksPass
                && noRejectedReview;
        }
    }

    static final class EventualCluster {
        private final KeyValueService leader = new KeyValueService();
        private final List<KeyValueService> replicas = new ArrayList<>();

        EventualCluster(int replicaCount) {
            if (replicaCount < 1) {
                throw new ValidationException(
                    "At least one replica is required"
                );
            }

            for (int i = 0; i < replicaCount; i++) {
                replicas.add(new KeyValueService());
            }
        }

        long write(String key, String value) {
            long version = leader.put(
                key,
                value,
                Optional.empty()
            );

            for (KeyValueService replica : replicas) {
                replica.put(key, value, Optional.empty());
            }

            return version;
        }

        Optional<VersionedValue> read(
            String key,
            Consistency consistency,
            int replicaIndex
        ) {
            if (consistency == Consistency.STRONG) {
                return leader.get(key);
            }

            if (replicaIndex < 0 || replicaIndex >= replicas.size()) {
                throw new ValidationException("Invalid replica index");
            }

            return replicas.get(replicaIndex).get(key);
        }
    }

    private static void validateKey(String key) {
        Objects.requireNonNull(key, "Key cannot be null");

        if (key.isBlank() || key.length() > 256) {
            throw new ValidationException(
                "Key must contain 1..256 characters"
            );
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(
                "=== Enterprise NoSQL Infrastructure Case Study ==="
            );

            KeyValueService keyValue = new KeyValueService();

            long version = keyValue.put(
                "employee:1001",
                "department=security;active=true",
                Optional.empty()
            );

            System.out.println(
                "Initial version: " + version
            );

            try {
                keyValue.put(
                    "employee:1001",
                    "department=admin",
                    Optional.of(version - 1)
                );
            } catch (ConflictException exception) {
                System.out.println(
                    "Expected concurrency failure: "
                    + exception.getMessage()
                );
            }

            DocumentService documents = new DocumentService();

            documents.save(
                new Document(
                    "u1001",
                    "Anita",
                    "security",
                    Set.of("python", "postgresql")
                )
            );

            documents.save(
                new Document(
                    "u1002",
                    "Ravi",
                    "engineering",
                    Set.of("java", "cpp")
                )
            );

            List<Document> securityUsers =
                documents.query(
                    document ->
                        document.department().equals("security")
                );

            System.out.println(
                "Security documents: "
                + securityUsers.size()
            );

            WideColumnService telemetry =
                new WideColumnService();

            telemetry.upsert(
                "device-42",
                "2026-10-31T11:00:00Z",
                Map.of(
                    "temperature", 31.2,
                    "battery", 88
                )
            );

            telemetry.upsert(
                "device-42",
                "2026-10-31T11:01:00Z",
                Map.of("temperature", 31.4)
            );

            System.out.println(
                "Telemetry rows: "
                + telemetry.queryPartition("device-42").size()
            );

            GraphService graph = new GraphService();

            for (String node :
                List.of("alice", "bob", "carol", "database")) {
                graph.addNode(node);
            }

            graph.addEdge("alice", "bob");
            graph.addEdge("bob", "carol");
            graph.addEdge("carol", "database");

            System.out.println(
                "Access path: "
                + graph.shortestPath("alice", "database")
                    .orElse(List.of("unreachable"))
            );

            RepositoryPolicy policy =
                new RepositoryPolicy(
                    2,
                    Set.of("unit-tests", "security-scan")
                );

            List<ReviewDecision> reviews = List.of(
                new ReviewDecision(
                    "reviewer-a",
                    ReviewState.ACCEPTED,
                    "Implementation is correct"
                ),
                new ReviewDecision(
                    "reviewer-b",
                    ReviewState.ACCEPTED,
                    "Security checks reviewed"
                )
            );

            Map<String, Boolean> checks = Map.of(
                "unit-tests", true,
                "security-scan", true
            );

            System.out.println(
                "Governance policy eligible: "
                + policy.eligible(reviews, checks)
            );

            EventualCluster cluster =
                new EventualCluster(2);

            cluster.write(
                "service:orders",
                "enabled=true"
            );

            System.out.println(
                "Strong read: "
                + cluster.read(
                    "service:orders",
                    Consistency.STRONG,
                    0
                ).orElseThrow().value()
            );

            System.out.println(
                "Eventual read: "
                + cluster.read(
                    "service:orders",
                    Consistency.EVENTUAL,
                    0
                ).orElseThrow().value()
            );

            System.out.println(
                "\nEnterprise controls:"
            );
            System.out.println(
                "- Domain validation rejects malformed identifiers."
            );
            System.out.println(
                "- Immutable records prevent accidental document mutation."
            );
            System.out.println(
                "- Version checks protect concurrent updates."
            );
            System.out.println(
                "- Policy objects separate governance rules from storage."
            );
            System.out.println(
                "- Eventual reads must tolerate replica staleness."
            );
            System.out.println(
                "- Secrets should not be stored as ordinary document fields."
            );

        } catch (RuntimeException exception) {
            System.err.println(
                "Application failure: "
                + exception.getMessage()
            );
            System.exit(1);
        }
    }
}
