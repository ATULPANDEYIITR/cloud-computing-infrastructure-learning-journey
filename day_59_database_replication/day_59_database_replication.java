import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class DatabaseReplicationDemo {

    enum ReplicationMode {
        SYNCHRONOUS,
        ASYNCHRONOUS
    }

    enum NodeState {
        ONLINE,
        LAGGING,
        OFFLINE
    }

    enum TransactionState {
        CREATED,
        COMMITTED,
        REJECTED
    }

    record Change(
        long sequence,
        String key,
        String value
    ) {
        Change {
            if (sequence <= 0) {
                throw new IllegalArgumentException("Sequence must be positive");
            }
            Objects.requireNonNull(key, "key");
            if (key.isBlank() || key.length() > 128) {
                throw new IllegalArgumentException(
                    "Key must contain 1-128 characters"
                );
            }
        }
    }

    record ReplicationPolicy(
        ReplicationMode mode,
        int requiredAcknowledgements,
        boolean allowStaleReads
    ) {
        ReplicationPolicy {
            Objects.requireNonNull(mode, "mode");

            if (requiredAcknowledgements < 0) {
                throw new IllegalArgumentException(
                    "Acknowledgement requirement cannot be negative"
                );
            }

            if (mode == ReplicationMode.SYNCHRONOUS &&
                requiredAcknowledgements == 0) {
                throw new IllegalArgumentException(
                    "Synchronous replication requires acknowledgements"
                );
            }
        }
    }

    record ReplicationResult(
        TransactionState state,
        long sequence,
        int acknowledgements,
        List<String> failures
    ) {}

    static final class ReplicationException extends Exception {
        ReplicationException(String message) {
            super(message);
        }
    }

    static final class PrimaryNode {
        private long sequence;
        private final Map<String, String> data = new HashMap<>();

        Change commit(String key, String value) {
            if (key == null || key.isBlank() || key.length() > 128) {
                throw new IllegalArgumentException(
                    "Key must contain 1-128 characters"
                );
            }

            Objects.requireNonNull(value, "value");

            Change change = new Change(++sequence, key, value);
            data.put(key, value);
            return change;
        }

        long currentSequence() {
            return sequence;
        }

        Optional<String> read(String key) {
            return Optional.ofNullable(data.get(key));
        }
    }

    static final class ReplicaNode {
        private final String name;
        private NodeState state = NodeState.ONLINE;
        private long appliedSequence;
        private final Map<String, String> data = new HashMap<>();
        private final Deque<Change> queue = new ArrayDeque<>();

        ReplicaNode(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Replica name is required");
            }
            this.name = name;
        }

        String name() {
            return name;
        }

        NodeState state() {
            return state;
        }

        void setState(NodeState state) {
            this.state = Objects.requireNonNull(state);
        }

        long appliedSequence() {
            return appliedSequence;
        }

        void receive(Change change) throws ReplicationException {
            if (state == NodeState.OFFLINE) {
                throw new ReplicationException(name + " is offline");
            }

            long expected = appliedSequence + queue.size() + 1;

            if (change.sequence() != expected) {
                throw new ReplicationException(
                    name + " expected sequence " +
                    expected +
                    " but received " +
                    change.sequence()
                );
            }

            queue.addLast(change);
            state = NodeState.LAGGING;
        }

        void apply() throws ReplicationException {
            if (state == NodeState.OFFLINE) {
                throw new ReplicationException(name + " is offline");
            }

            while (!queue.isEmpty()) {
                Change change = queue.removeFirst();

                if (change.sequence() != appliedSequence + 1) {
                    throw new ReplicationException(
                        name + " encountered a sequence gap"
                    );
                }

                data.put(change.key(), change.value());
                appliedSequence = change.sequence();
            }

            state = NodeState.ONLINE;
        }

        Optional<String> read(String key) throws ReplicationException {
            if (state == NodeState.OFFLINE) {
                throw new ReplicationException(name + " is offline");
            }

            return Optional.ofNullable(data.get(key));
        }
    }

    static final class ReplicationService {
        private final PrimaryNode primary;
        private final List<ReplicaNode> replicas;
        private final ReplicationPolicy policy;

        ReplicationService(
            PrimaryNode primary,
            List<ReplicaNode> replicas,
            ReplicationPolicy policy
        ) {
            this.primary = Objects.requireNonNull(primary);
            this.replicas = new ArrayList<>(replicas);
            this.policy = Objects.requireNonNull(policy);

            if (policy.requiredAcknowledgements() > replicas.size()) {
                throw new IllegalArgumentException(
                    "Required acknowledgements exceed replica count"
                );
            }
        }

        ReplicationResult write(String key, String value) {
            Change change = primary.commit(key, value);

            int acknowledgements = 0;
            List<String> failures = new ArrayList<>();

            for (ReplicaNode replica : replicas) {
                try {
                    replica.receive(change);

                    if (policy.mode() == ReplicationMode.SYNCHRONOUS) {
                        replica.apply();
                    }

                    acknowledgements++;
                } catch (ReplicationException error) {
                    failures.add(replica.name() + ": " + error.getMessage());
                }
            }

            boolean accepted =
                policy.mode() == ReplicationMode.ASYNCHRONOUS ||
                acknowledgements >= policy.requiredAcknowledgements();

            return new ReplicationResult(
                accepted
                    ? TransactionState.COMMITTED
                    : TransactionState.REJECTED,
                change.sequence(),
                acknowledgements,
                List.copyOf(failures)
            );
        }

        void catchUp() {
            replicas.stream()
                .filter(replica -> replica.state() != NodeState.OFFLINE)
                .forEach(replica -> {
                    try {
                        replica.apply();
                    } catch (ReplicationException error) {
                        throw new IllegalStateException(error);
                    }
                });
        }

        long lag(ReplicaNode replica) {
            return primary.currentSequence() - replica.appliedSequence();
        }

        List<ReplicaNode> replicas() {
            return Collections.unmodifiableList(replicas);
        }
    }

    private static void printResult(ReplicationResult result) {
        System.out.println(
            "state=" + result.state() +
            ", sequence=" + result.sequence() +
            ", acknowledgements=" + result.acknowledgements() +
            ", failures=" + result.failures()
        );
    }

    public static void main(String[] args) throws Exception {
        PrimaryNode primary = new PrimaryNode();

        ReplicaNode replicaA = new ReplicaNode("read-a");
        ReplicaNode replicaB = new ReplicaNode("read-b");

        ReplicationPolicy asyncPolicy = new ReplicationPolicy(
            ReplicationMode.ASYNCHRONOUS,
            0,
            true
        );

        ReplicationService asyncService = new ReplicationService(
            primary,
            List.of(replicaA, replicaB),
            asyncPolicy
        );

        System.out.println("=== Asynchronous replication ===");

        ReplicationResult first =
            asyncService.write("account:100", "ACTIVE");

        printResult(first);

        System.out.println(
            "Primary read: " +
            primary.read("account:100").orElse("<missing>")
        );

        System.out.println(
            "Replica lag: " +
            asyncService.lag(replicaA)
        );

        asyncService.catchUp();

        System.out.println(
            "Replica read after catch-up: " +
            replicaA.read("account:100").orElse("<missing>")
        );

        System.out.println("\n=== Synchronous policy ===");

        PrimaryNode synchronousPrimary = new PrimaryNode();

        ReplicaNode syncA = new ReplicaNode("sync-a");
        ReplicaNode syncB = new ReplicaNode("sync-b");
        syncB.setState(NodeState.OFFLINE);

        ReplicationPolicy syncPolicy = new ReplicationPolicy(
            ReplicationMode.SYNCHRONOUS,
            2,
            false
        );

        ReplicationService syncService = new ReplicationService(
            synchronousPrimary,
            List.of(syncA, syncB),
            syncPolicy
        );

        ReplicationResult second =
            syncService.write("payment:500", "SETTLED");

        printResult(second);

        System.out.println("\n=== Replica states ===");

        for (ReplicaNode replica : syncService.replicas()) {
            System.out.println(
                replica.name() +
                " state=" + replica.state() +
                " lag=" + syncService.lag(replica)
            );
        }
    }
}
