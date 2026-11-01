import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class DatabaseScalingCaseStudy {

    enum ScalingStrategy {
        VERTICAL,
        HORIZONTAL,
        PARTITIONING,
        READ_REPLICA
    }

    enum OperationType {
        READ,
        WRITE
    }

    enum Consistency {
        STRONG,
        EVENTUAL
    }

    record DatabaseNode(
        String id,
        String region,
        int capacityOps,
        int activeOps,
        boolean healthy
    ) {
        DatabaseNode {
            Objects.requireNonNull(id);
            Objects.requireNonNull(region);

            if (capacityOps <= 0) {
                throw new IllegalArgumentException(
                    "Database capacity must be positive"
                );
            }

            if (activeOps < 0) {
                throw new IllegalArgumentException(
                    "Active operations cannot be negative"
                );
            }
        }

        boolean canAccept() {
            return healthy && activeOps < capacityOps;
        }

        double utilization() {
            return (double) activeOps / capacityOps;
        }

        DatabaseNode withActiveOps(int value) {
            return new DatabaseNode(
                id,
                region,
                capacityOps,
                value,
                healthy
            );
        }

        DatabaseNode withHealth(boolean value) {
            return new DatabaseNode(
                id,
                region,
                capacityOps,
                activeOps,
                value
            );
        }
    }

    record Commit(String hash, String message) {
        Commit {
            if (hash == null || hash.isBlank()) {
                throw new IllegalArgumentException("Commit hash required");
            }
            if (message == null || message.isBlank()) {
                throw new IllegalArgumentException("Commit message required");
            }
        }
    }

    record Review(
        String reviewer,
        boolean approved,
        boolean stale,
        boolean dismissed
    ) {
        Review {
            if (reviewer == null || reviewer.isBlank()) {
                throw new IllegalArgumentException(
                    "Reviewer identity required"
                );
            }
        }

        boolean effectiveApproval() {
            return approved && !stale && !dismissed;
        }
    }

    record StatusCheck(String name, boolean passed) {
        StatusCheck {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                    "Status-check name required"
                );
            }
        }
    }

    record BranchProtectionPolicy(
        int requiredApprovals,
        boolean requireSuccessfulChecks,
        boolean requireResolvedConversations,
        boolean allowDirectPush,
        boolean allowForcePush,
        boolean requireLinearHistory
    ) {
        BranchProtectionPolicy {
            if (requiredApprovals < 0) {
                throw new IllegalArgumentException(
                    "Required approvals cannot be negative"
                );
            }
        }
    }

    static final class PullRequest {
        private final int id;
        private final String sourceBranch;
        private final String targetBranch;
        private final List<Commit> commits;
        private final List<Review> reviews;
        private final List<StatusCheck> statusChecks;

        private boolean draft;
        private boolean open;
        private boolean mergeConflict;
        private boolean sourceSynchronized;
        private int unresolvedConversations;

        PullRequest(
            int id,
            String sourceBranch,
            String targetBranch,
            List<Commit> commits
        ) {
            if (id <= 0) {
                throw new IllegalArgumentException(
                    "Pull Request ID must be positive"
                );
            }

            this.id = id;
            this.sourceBranch = requireText(sourceBranch, "source branch");
            this.targetBranch = requireText(targetBranch, "target branch");
            this.commits = new ArrayList<>(commits);
            this.reviews = new ArrayList<>();
            this.statusChecks = new ArrayList<>();
            this.open = true;
            this.sourceSynchronized = true;
        }

        void addReview(Review review) {
            reviews.add(Objects.requireNonNull(review));
        }

        void addStatusCheck(StatusCheck check) {
            statusChecks.add(Objects.requireNonNull(check));
        }

        void setDraft(boolean draft) {
            this.draft = draft;
        }

        void setMergeConflict(boolean mergeConflict) {
            this.mergeConflict = mergeConflict;
        }

        void setSourceSynchronized(boolean value) {
            this.sourceSynchronized = value;
        }

        void setUnresolvedConversations(int count) {
            if (count < 0) {
                throw new IllegalArgumentException(
                    "Conversation count cannot be negative"
                );
            }
            this.unresolvedConversations = count;
        }

        void close() {
            this.open = false;
        }

        List<Review> reviews() {
            return Collections.unmodifiableList(reviews);
        }

        List<StatusCheck> statusChecks() {
            return Collections.unmodifiableList(statusChecks);
        }

        List<Commit> commits() {
            return Collections.unmodifiableList(commits);
        }
    }

    interface MergeRule {
        String name();

        boolean passes(PullRequest pullRequest);
    }

    static final class ReviewApprovalRule implements MergeRule {
        private final int requiredApprovals;

        ReviewApprovalRule(int requiredApprovals) {
            this.requiredApprovals = requiredApprovals;
        }

        @Override
        public String name() {
            return "required approvals";
        }

        @Override
        public boolean passes(PullRequest pullRequest) {
            long effectiveApprovals = pullRequest.reviews()
                .stream()
                .filter(Review::effectiveApproval)
                .count();

            return effectiveApprovals >= requiredApprovals;
        }
    }

    static final class StatusCheckRule implements MergeRule {
        @Override
        public String name() {
            return "successful status checks";
        }

        @Override
        public boolean passes(PullRequest pullRequest) {
            return !pullRequest.statusChecks().isEmpty()
                && pullRequest.statusChecks()
                    .stream()
                    .allMatch(StatusCheck::passed);
        }
    }

    static final class MergePolicyService {
        private final BranchProtectionPolicy policy;
        private final List<MergeRule> rules;

        MergePolicyService(BranchProtectionPolicy policy) {
            this.policy = Objects.requireNonNull(policy);
            this.rules = List.of(
                new ReviewApprovalRule(policy.requiredApprovals()),
                new StatusCheckRule()
            );
        }

        List<String> validate(PullRequest pullRequest) {
            List<String> failures = new ArrayList<>();

            if (!pullRequest.open) {
                failures.add("Pull Request is closed");
            }

            if (pullRequest.draft) {
                failures.add("Pull Request is still a draft");
            }

            if (pullRequest.commits().isEmpty()) {
                failures.add("Pull Request contains no commits");
            }

            if (pullRequest.mergeConflict) {
                failures.add("Merge conflict must be resolved");
            }

            if (!pullRequest.sourceSynchronized) {
                failures.add("Source branch is not synchronized");
            }

            for (MergeRule rule : rules) {
                if (!rule.passes(pullRequest)) {
                    failures.add(rule.name() + " requirement failed");
                }
            }

            if (policy.requireResolvedConversations()
                && pullRequest.unresolvedConversations > 0) {
                failures.add("Unresolved conversations remain");
            }

            return failures;
        }

        boolean canMerge(PullRequest pullRequest) {
            return validate(pullRequest).isEmpty();
        }
    }

    static final class ShardRouter {
        private final List<String> shardIds;

        ShardRouter(List<String> shardIds) {
            if (shardIds == null || shardIds.isEmpty()) {
                throw new IllegalArgumentException(
                    "At least one shard is required"
                );
            }

            this.shardIds = List.copyOf(shardIds);
        }

        String route(long customerId) {
            if (customerId < 0) {
                throw new IllegalArgumentException(
                    "Customer ID cannot be negative"
                );
            }

            return shardIds.get(
                Math.floorMod(customerId, shardIds.size())
            );
        }
    }

    static final class ReadReplicaService {
        private final DatabaseNode primary;
        private final List<DatabaseNode> replicas;
        private int cursor;

        ReadReplicaService(
            DatabaseNode primary,
            List<DatabaseNode> replicas
        ) {
            this.primary = Objects.requireNonNull(primary);
            this.replicas = new ArrayList<>(replicas);
        }

        String route(
            OperationType operation,
            Consistency consistency
        ) {
            if (operation == OperationType.WRITE
                || consistency == Consistency.STRONG) {
                if (!primary.canAccept()) {
                    throw new IllegalStateException(
                        "Primary cannot accept request"
                    );
                }

                return primary.id();
            }

            for (int offset = 0; offset < replicas.size(); offset++) {
                int index = (cursor + offset) % replicas.size();
                DatabaseNode replica = replicas.get(index);

                if (replica.canAccept()) {
                    cursor = index + 1;
                    return replica.id();
                }
            }

            if (primary.canAccept()) {
                return primary.id();
            }

            throw new IllegalStateException(
                "No node is available for read"
            );
        }
    }

    static ScalingStrategy chooseScalingStrategy(
        int workloadOps,
        int nodeCapacity,
        double writeRatio,
        long rows
    ) {
        if (workloadOps <= 0 || nodeCapacity <= 0) {
            throw new IllegalArgumentException(
                "Workload and capacity must be positive"
            );
        }

        if (writeRatio < 0 || writeRatio > 1) {
            throw new IllegalArgumentException(
                "Write ratio must be between zero and one"
            );
        }

        double utilization =
            (double) workloadOps / nodeCapacity;

        if (utilization <= 0.70) {
            return ScalingStrategy.VERTICAL;
        }

        if (writeRatio < 0.30) {
            return ScalingStrategy.READ_REPLICA;
        }

        if (rows > 10_000_000L) {
            return ScalingStrategy.PARTITIONING;
        }

        return ScalingStrategy.HORIZONTAL;
    }

    static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                field + " cannot be blank"
            );
        }

        return value;
    }

    public static void main(String[] args) {
        System.out.println("Database Scaling Case Study");
        System.out.println("=".repeat(60));

        System.out.println("\nScaling policy:");

        int[][] scenarios = {
            {500, 1000, 50, 100_000},
            {900, 1000, 10, 500_000},
            {900, 1000, 80, 20_000_000},
            {950, 1000, 50, 2_000_000}
        };

        for (int[] scenario : scenarios) {
            ScalingStrategy strategy = chooseScalingStrategy(
                scenario[0],
                scenario[1],
                scenario[2] / 100.0,
                scenario[3]
            );

            System.out.printf(
                "workload=%d capacity=%d writeRatio=%d%% rows=%d -> %s%n",
                scenario[0],
                scenario[1],
                scenario[2],
                scenario[3],
                strategy
            );
        }

        System.out.println("\nPull Request governance:");

        PullRequest pullRequest = new PullRequest(
            101,
            "feature/customer-index",
            "main",
            List.of(
                new Commit("a1b2c3", "Add customer index"),
                new Commit("d4e5f6", "Add index validation")
            )
        );

        pullRequest.addReview(
            new Review("reviewer-a", true, false, false)
        );

        pullRequest.addReview(
            new Review("reviewer-b", true, false, false)
        );

        pullRequest.addStatusCheck(
            new StatusCheck("unit-tests", true)
        );

        pullRequest.addStatusCheck(
            new StatusCheck("integration-tests", true)
        );

        pullRequest.addStatusCheck(
            new StatusCheck("security-scan", true)
        );

        BranchProtectionPolicy policy =
            new BranchProtectionPolicy(
                2,
                true,
                true,
                false,
                false,
                true
            );

        MergePolicyService mergeService =
            new MergePolicyService(policy);

        System.out.println(
            "Merge eligible: "
                + mergeService.canMerge(pullRequest)
        );

        pullRequest.setUnresolvedConversations(1);

        System.out.println("Failure conditions:");

        for (String failure : mergeService.validate(pullRequest)) {
            System.out.println("- " + failure);
        }

        System.out.println("\nSharding:");

        ShardRouter router = new ShardRouter(
            List.of("shard-a", "shard-b", "shard-c")
        );

        for (long customerId : List.of(101L, 102L, 103L, 104L)) {
            System.out.println(
                customerId + " -> " + router.route(customerId)
            );
        }

        System.out.println("\nRead replicas:");

        ReadReplicaService replicas =
            new ReadReplicaService(
                new DatabaseNode(
                    "primary",
                    "ap-south",
                    1000,
                    0,
                    true
                ),
                List.of(
                    new DatabaseNode(
                        "replica-1",
                        "ap-south",
                        800,
                        0,
                        true
                    ),
                    new DatabaseNode(
                        "replica-2",
                        "ap-southeast",
                        800,
                        0,
                        true
                    )
                )
            );

        System.out.println(
            "Write -> "
                + replicas.route(
                    OperationType.WRITE,
                    Consistency.STRONG
                )
        );

        System.out.println(
            "Strong read -> "
                + replicas.route(
                    OperationType.READ,
                    Consistency.STRONG
                )
        );

        System.out.println(
            "Eventual read -> "
                + replicas.route(
                    OperationType.READ,
                    Consistency.EVENTUAL
                )
        );

        System.out.println("\nEnterprise design controls:");
        System.out.println(
            "- Keep routing metadata immutable from ordinary application users."
        );
        System.out.println(
            "- Treat replication lag as an explicit consistency condition."
        );
        System.out.println(
            "- Monitor connection saturation, query latency, storage growth, and lag."
        );
        System.out.println(
            "- Use least privilege for database administration and migration operations."
        );
        System.out.println(
            "- Test failover and recovery instead of assuming replicas are interchangeable."
        );
    }
}
