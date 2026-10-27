import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class RelationalDatabaseArchitecture {

    enum TransactionState {
        ACTIVE,
        COMMITTED,
        ROLLED_BACK
    }

    enum ReviewDecision {
        APPROVED,
        CHANGES_REQUESTED,
        COMMENTED
    }

    record User(long id, String username) {
        public User {
            if (id <= 0) {
                throw new IllegalArgumentException("User ID must be positive.");
            }
            if (username == null || username.isBlank()) {
                throw new IllegalArgumentException("Username is required.");
            }
        }
    }

    record Branch(
        long id,
        long repositoryId,
        String name,
        boolean protectedBranch
    ) {}

    record StatusCheck(
        String name,
        boolean passed,
        Instant completedAt
    ) {}

    record Review(
        long reviewerId,
        ReviewDecision decision,
        String comment
    ) {}

    record MergePolicy(
        int requiredApprovals,
        boolean requirePassingChecks,
        boolean requireResolvedConversations,
        boolean prohibitDirectPush
    ) {}

    static final class Account {
        private final long id;
        private final long ownerId;
        private long balanceCents;
        private long version;

        Account(long id, long ownerId, long balanceCents) {
            if (balanceCents < 0) {
                throw new IllegalArgumentException(
                    "Balance cannot be negative."
                );
            }

            this.id = id;
            this.ownerId = ownerId;
            this.balanceCents = balanceCents;
        }

        long id() {
            return id;
        }

        long ownerId() {
            return ownerId;
        }

        long balanceCents() {
            return balanceCents;
        }

        long version() {
            return version;
        }

        void setBalanceCents(long balanceCents) {
            if (balanceCents < 0) {
                throw new IllegalArgumentException(
                    "Balance cannot be negative."
                );
            }

            this.balanceCents = balanceCents;
            version++;
        }
    }

    static final class RelationalRepository {
        private final Map<Long, User> users = new HashMap<>();
        private final Map<Long, Account> accounts = new HashMap<>();
        private long nextUserId = 1;
        private long nextAccountId = 1;

        User createUser(String username) {
            String normalized = Objects.requireNonNull(username).trim();

            boolean duplicate = users.values()
                .stream()
                .anyMatch(user ->
                    user.username().equalsIgnoreCase(normalized)
                );

            if (duplicate) {
                throw new IllegalArgumentException(
                    "Username must be unique."
                );
            }

            User user = new User(nextUserId++, normalized);
            users.put(user.id(), user);
            return user;
        }

        Account createAccount(long ownerId, long balanceCents) {
            if (!users.containsKey(ownerId)) {
                throw new IllegalArgumentException(
                    "Owner foreign key does not exist."
                );
            }

            Account account = new Account(
                nextAccountId++,
                ownerId,
                balanceCents
            );

            accounts.put(account.id(), account);
            return account;
        }

        Account account(long id) {
            Account account = accounts.get(id);

            if (account == null) {
                throw new IllegalArgumentException(
                    "Account does not exist."
                );
            }

            return account;
        }

        Map<Long, Account> accounts() {
            return accounts;
        }
    }

    static final class TransactionService {
        private final RelationalRepository repository;
        private final Map<Long, Long> stagedBalances = new HashMap<>();
        private final Map<Long, Long> originalVersions = new HashMap<>();
        private TransactionState state = TransactionState.ACTIVE;

        TransactionService(RelationalRepository repository) {
            this.repository = repository;

            repository.accounts().values().forEach(account -> {
                stagedBalances.put(
                    account.id(),
                    account.balanceCents()
                );
                originalVersions.put(
                    account.id(),
                    account.version()
                );
            });
        }

        private void requireActive() {
            if (state != TransactionState.ACTIVE) {
                throw new IllegalStateException(
                    "Transaction is not active."
                );
            }
        }

        void transfer(
            long sourceId,
            long destinationId,
            long amountCents
        ) {
            requireActive();

            if (sourceId == destinationId) {
                throw new IllegalArgumentException(
                    "Source and destination must differ."
                );
            }

            if (amountCents <= 0) {
                throw new IllegalArgumentException(
                    "Transfer amount must be positive."
                );
            }

            if (!stagedBalances.containsKey(sourceId)
                || !stagedBalances.containsKey(destinationId)) {
                throw new IllegalArgumentException(
                    "Both accounts must exist."
                );
            }

            long sourceBalance = stagedBalances.get(sourceId);

            if (sourceBalance < amountCents) {
                throw new IllegalArgumentException(
                    "Insufficient funds."
                );
            }

            stagedBalances.compute(
                sourceId,
                (id, balance) -> balance - amountCents
            );

            stagedBalances.compute(
                destinationId,
                (id, balance) -> balance + amountCents
            );
        }

        void commit() {
            requireActive();

            for (Map.Entry<Long, Long> entry : originalVersions.entrySet()) {
                Account account = repository.account(entry.getKey());

                if (account.version() != entry.getValue()) {
                    throw new IllegalStateException(
                        "Concurrent modification detected for account "
                            + account.id()
                    );
                }
            }

            for (Map.Entry<Long, Long> entry : stagedBalances.entrySet()) {
                Account account = repository.account(entry.getKey());

                if (account.balanceCents() != entry.getValue()) {
                    account.setBalanceCents(entry.getValue());
                }
            }

            state = TransactionState.COMMITTED;
        }

        void rollback() {
            requireActive();
            state = TransactionState.ROLLED_BACK;
        }
    }

    static final class MergeEligibilityService {

        boolean eligible(
            MergePolicy policy,
            List<Review> reviews,
            List<StatusCheck> checks,
            boolean unresolvedConversations,
            boolean directPush
        ) {
            if (directPush && policy.prohibitDirectPush()) {
                return false;
            }

            if (
                policy.requireResolvedConversations()
                    && unresolvedConversations
            ) {
                return false;
            }

            if (policy.requirePassingChecks()) {
                boolean allPassed = checks.stream()
                    .allMatch(StatusCheck::passed);

                if (!allPassed) {
                    return false;
                }
            }

            long approvals = reviews.stream()
                .filter(review ->
                    review.decision() == ReviewDecision.APPROVED
                )
                .count();

            return approvals >= policy.requiredApprovals();
        }
    }

    public static void main(String[] args) {
        RelationalRepository repository =
            new RelationalRepository();

        User alice = repository.createUser("alice");
        User bob = repository.createUser("bob");

        repository.createAccount(alice.id(), 10_000);
        repository.createAccount(bob.id(), 2_500);

        TransactionService transaction =
            new TransactionService(repository);

        transaction.transfer(1, 2, 3_000);
        transaction.commit();

        System.out.println("Committed balances:");

        repository.accounts()
            .values()
            .forEach(account ->
                System.out.printf(
                    "Account %d: $%.2f, version=%d%n",
                    account.id(),
                    account.balanceCents() / 100.0,
                    account.version()
                )
            );

        TransactionService failed =
            new TransactionService(repository);

        try {
            failed.transfer(1, 2, 100_000);
            failed.commit();
        } catch (IllegalArgumentException error) {
            failed.rollback();
            System.out.println(
                "Transaction rejected: " + error.getMessage()
            );
        }

        MergePolicy policy = new MergePolicy(
            2,
            true,
            true,
            true
        );

        List<Review> reviews = List.of(
            new Review(
                alice.id(),
                ReviewDecision.APPROVED,
                "Database migration reviewed."
            ),
            new Review(
                bob.id(),
                ReviewDecision.APPROVED,
                "Indexes and constraints reviewed."
            )
        );

        List<StatusCheck> checks = List.of(
            new StatusCheck(
                "unit-tests",
                true,
                Instant.now()
            ),
            new StatusCheck(
                "integration-tests",
                true,
                Instant.now()
            )
        );

        MergeEligibilityService eligibility =
            new MergeEligibilityService();

        boolean canMerge = eligibility.eligible(
            policy,
            reviews,
            checks,
            false,
            false
        );

        System.out.println(
            "Merge eligibility: "
                + (canMerge ? "eligible" : "blocked")
        );

        long totalBalance = repository.accounts()
            .values()
            .stream()
            .mapToLong(Account::balanceCents)
            .sum();

        if (totalBalance != 12_500) {
            throw new IllegalStateException(
                "Balance conservation invariant failed."
            );
        }

        System.out.println(
            "Relational database architecture workflow completed."
        );
    }
}
