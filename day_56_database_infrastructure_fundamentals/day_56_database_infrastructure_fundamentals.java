import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

public class DatabaseInfrastructureDemo {

    enum TransactionState {
        ACTIVE, COMMITTED, ROLLED_BACK
    }

    enum NodeRole {
        PRIMARY, REPLICA
    }

    enum OperationType {
        PUT, DELETE
    }

    enum IsolationLevel {
        READ_COMMITTED, REPEATABLE_READ, SERIALIZABLE
    }

    record Account(String id, String owner, double balance) {
        Account {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Account ID is required.");
            }
            if (owner == null || owner.isBlank()) {
                throw new IllegalArgumentException("Account owner is required.");
            }
            if (!Double.isFinite(balance) || balance < 0) {
                throw new IllegalArgumentException(
                    "Account balance must be finite and non-negative."
                );
            }
        }
    }

    record WalRecord(
        long lsn,
        String transactionId,
        OperationType operation,
        String key,
        Account value,
        Instant timestamp
    ) {}

    static class DatabaseException extends RuntimeException {
        DatabaseException(String message) {
            super(message);
        }
    }

    static class TransactionException extends DatabaseException {
        TransactionException(String message) {
            super(message);
        }
    }

    static class ConstraintViolation extends DatabaseException {
        ConstraintViolation(String message) {
            super(message);
        }
    }

    static class ReplicationException extends DatabaseException {
        ReplicationException(String message) {
            super(message);
        }
    }

    /*
     * The storage abstraction isolates logical records from transaction
     * management. A production engine would replace this map with pages,
     * buffer management, checksums and durable files.
     */
    static final class StorageEngine {
        private final Map<String, Account> records = new HashMap<>();

        Optional<Account> read(String key) {
            return Optional.ofNullable(records.get(key));
        }

        void write(String key, Account account) {
            if (key == null || key.isBlank()) {
                throw new ConstraintViolation("Storage key is required.");
            }
            records.put(key, account);
        }

        void delete(String key) {
            records.remove(key);
        }

        Map<String, Account> snapshot() {
            return new HashMap<>(records);
        }

        void restore(Map<String, Account> snapshot) {
            records.clear();
            records.putAll(snapshot);
        }
    }

    static final class Transaction {
        private final String id;
        private final IsolationLevel isolationLevel;
        private TransactionState state = TransactionState.ACTIVE;
        private final List<Operation> operations = new ArrayList<>();

        Transaction(IsolationLevel isolationLevel) {
            this.id = UUID.randomUUID().toString();
            this.isolationLevel = Objects.requireNonNull(isolationLevel);
        }

        void ensureActive() {
            if (state != TransactionState.ACTIVE) {
                throw new TransactionException(
                    "Transaction is already " + state
                );
            }
        }

        void put(String key, Account account) {
            ensureActive();
            operations.add(new Operation(OperationType.PUT, key, account));
        }

        void delete(String key) {
            ensureActive();
            operations.add(new Operation(OperationType.DELETE, key, null));
        }

        String id() {
            return id;
        }

        IsolationLevel isolationLevel() {
            return isolationLevel;
        }

        List<Operation> operations() {
            return Collections.unmodifiableList(operations);
        }

        void commit() {
            ensureActive();
            state = TransactionState.COMMITTED;
        }

        void rollback() {
            ensureActive();
            operations.clear();
            state = TransactionState.ROLLED_BACK;
        }
    }

    record Operation(
        OperationType type,
        String key,
        Account value
    ) {}

    static final class TransactionManager {
        private final StorageEngine storage;
        private final List<WalRecord> wal = new ArrayList<>();
        private long nextLsn = 1;

        TransactionManager(StorageEngine storage) {
            this.storage = storage;
        }

        Transaction begin(IsolationLevel isolationLevel) {
            return new Transaction(isolationLevel);
        }

        List<WalRecord> commit(Transaction transaction) {
            transaction.ensureActive();

            Map<String, Account> backup = storage.snapshot();
            List<WalRecord> committedRecords = new ArrayList<>();

            try {
                for (Operation operation : transaction.operations()) {
                    if (operation.type() == OperationType.PUT) {
                        storage.write(operation.key(), operation.value());
                    } else {
                        storage.delete(operation.key());
                    }

                    committedRecords.add(
                        new WalRecord(
                            nextLsn++,
                            transaction.id(),
                            operation.type(),
                            operation.key(),
                            operation.value(),
                            Instant.now()
                        )
                    );
                }

                wal.addAll(committedRecords);
                transaction.commit();
                return committedRecords;
            } catch (RuntimeException error) {
                storage.restore(backup);
                throw error;
            }
        }

        List<WalRecord> wal() {
            return Collections.unmodifiableList(wal);
        }
    }

    static final class DatabaseNode {
        private final String name;
        private NodeRole role;
        private final StorageEngine storage = new StorageEngine();
        private boolean available = true;
        private long appliedLsn = 0;

        DatabaseNode(String name, NodeRole role) {
            this.name = Objects.requireNonNull(name);
            this.role = Objects.requireNonNull(role);
        }

        void apply(WalRecord record) {
            if (!available) {
                throw new ReplicationException(name + " is unavailable.");
            }

            if (record.lsn() <= appliedLsn) {
                return;
            }

            if (record.operation() == OperationType.PUT) {
                storage.write(record.key(), record.value());
            } else {
                storage.delete(record.key());
            }

            appliedLsn = record.lsn();
        }

        String name() {
            return name;
        }

        StorageEngine storage() {
            return storage;
        }

        long lsn() {
            return appliedLsn;
        }

        void setRole(NodeRole role) {
            this.role = role;
        }

        void setAvailable(boolean available) {
            this.available = available;
        }

        boolean available() {
            return available;
        }
    }

    static final class ReplicationService {
        private final DatabaseNode primary;
        private final List<DatabaseNode> replicas = new ArrayList<>();

        ReplicationService(DatabaseNode primary) {
            this.primary = primary;
        }

        void addReplica(DatabaseNode replica) {
            if (replica == primary) {
                throw new ReplicationException("Primary cannot be its own replica.");
            }
            replicas.add(replica);
        }

        void replicate(List<WalRecord> records) {
            for (DatabaseNode replica : replicas) {
                if (!replica.available()) {
                    continue;
                }

                for (WalRecord record : records) {
                    replica.apply(record);
                }
            }
        }

        DatabaseNode promoteMostCurrentReplica() {
            return replicas.stream()
                .filter(DatabaseNode::available)
                .max((a, b) -> Long.compare(a.lsn(), b.lsn()))
                .map(node -> {
                    primary.setRole(NodeRole.REPLICA);
                    node.setRole(NodeRole.PRIMARY);
                    return node;
                })
                .orElseThrow(() ->
                    new ReplicationException(
                        "No available replica can be promoted."
                    )
                );
        }

        List<DatabaseNode> replicas() {
            return Collections.unmodifiableList(replicas);
        }
    }

    interface AccountPolicy {
        void validateTransfer(
            Account source,
            Account target,
            double amount
        );
    }

    static final class ProductionTransferPolicy implements AccountPolicy {
        @Override
        public void validateTransfer(
            Account source,
            Account target,
            double amount
        ) {
            if (source.id().equals(target.id())) {
                throw new ConstraintViolation(
                    "Source and target accounts must differ."
                );
            }

            if (!Double.isFinite(amount) || amount <= 0) {
                throw new ConstraintViolation(
                    "Transfer amount must be positive."
                );
            }

            if (source.balance() < amount) {
                throw new ConstraintViolation("Insufficient funds.");
            }

            if (amount > 100_000) {
                throw new ConstraintViolation(
                    "Single transfer exceeds operational policy."
                );
            }
        }
    }

    static final class AccountService {
        private final StorageEngine storage;
        private final AccountPolicy policy;

        AccountService(StorageEngine storage, AccountPolicy policy) {
            this.storage = storage;
            this.policy = policy;
        }

        private String key(String id) {
            return "account:" + id;
        }

        void create(
            Transaction transaction,
            String id,
            String owner,
            double balance
        ) {
            String storageKey = key(id);

            if (storage.read(storageKey).isPresent()) {
                throw new ConstraintViolation(
                    "Account already exists: " + id
                );
            }

            transaction.put(
                storageKey,
                new Account(id, owner, balance)
            );
        }

        void transfer(
            Transaction transaction,
            String sourceId,
            String targetId,
            double amount
        ) {
            Account source = storage.read(key(sourceId))
                .orElseThrow(() ->
                    new ConstraintViolation("Source account not found.")
                );

            Account target = storage.read(key(targetId))
                .orElseThrow(() ->
                    new ConstraintViolation("Target account not found.")
                );

            policy.validateTransfer(source, target, amount);

            transaction.put(
                key(sourceId),
                new Account(
                    source.id(),
                    source.owner(),
                    source.balance() - amount
                )
            );

            transaction.put(
                key(targetId),
                new Account(
                    target.id(),
                    target.owner(),
                    target.balance() + amount
                )
            );
        }
    }

    static void printHealth(
        DatabaseNode primary,
        List<DatabaseNode> replicas
    ) {
        System.out.println(
            "Primary " + primary.name()
                + " LSN=" + primary.lsn()
                + " available=" + primary.available()
        );

        for (DatabaseNode replica : replicas) {
            System.out.println(
                "Replica " + replica.name()
                    + " LSN=" + replica.lsn()
                    + " lag=" + (primary.lsn() - replica.lsn())
                    + " available=" + replica.available()
            );
        }
    }

    public static void main(String[] args) {
        DatabaseNode primary =
            new DatabaseNode("db-primary-01", NodeRole.PRIMARY);

        DatabaseNode replicaA =
            new DatabaseNode("db-replica-01", NodeRole.REPLICA);

        DatabaseNode replicaB =
            new DatabaseNode("db-replica-02", NodeRole.REPLICA);

        ReplicationService replication =
            new ReplicationService(primary);

        replication.addReplica(replicaA);
        replication.addReplica(replicaB);

        TransactionManager transactions =
            new TransactionManager(primary.storage());

        AccountService accounts =
            new AccountService(
                primary.storage(),
                new ProductionTransferPolicy()
            );

        Transaction creation =
            transactions.begin(IsolationLevel.READ_COMMITTED);

        accounts.create(
            creation,
            "A100",
            "Operations",
            1000.00
        );

        accounts.create(
            creation,
            "A200",
            "Analytics",
            250.00
        );

        List<WalRecord> creationWal =
            transactions.commit(creation);

        replication.replicate(creationWal);

        Transaction transfer =
            transactions.begin(IsolationLevel.SERIALIZABLE);

        accounts.transfer(
            transfer,
            "A100",
            "A200",
            125.00
        );

        List<WalRecord> transferWal =
            transactions.commit(transfer);

        replication.replicate(transferWal);

        double replicaBalance =
            replicaA.storage()
                .read("account:A200")
                .orElseThrow()
                .balance();

        if (replicaBalance != 375.00) {
            throw new DatabaseException(
                "Replication consistency check failed."
            );
        }

        Transaction invalid =
            transactions.begin(IsolationLevel.SERIALIZABLE);

        try {
            accounts.transfer(
                invalid,
                "A100",
                "A200",
                5000
            );
            transactions.commit(invalid);
        } catch (ConstraintViolation error) {
            invalid.rollback();
            System.out.println(
                "Rejected transaction: " + error.getMessage()
            );
        }

        replicaB.setAvailable(false);

        System.out.println(
            "\nEnterprise database infrastructure model"
        );
        System.out.println(
            "=========================================="
        );

        printHealth(
            primary,
            replication.replicas()
        );

        DatabaseNode promoted =
            replication.promoteMostCurrentReplica();

        Account a100 =
            promoted.storage()
                .read("account:A100")
                .orElseThrow();

        Account a200 =
            promoted.storage()
                .read("account:A200")
                .orElseThrow();

        System.out.println(
            "\nPromoted primary: " + promoted.name()
        );

        System.out.printf(
            "A100 balance: %.2f%n",
            a100.balance()
        );

        System.out.printf(
            "A200 balance: %.2f%n",
            a200.balance()
        );

        System.out.println(
            "WAL records: " + transactions.wal().size()
        );

        System.out.println(
            "Isolation level used for transfer: "
                + transfer.isolationLevel()
        );
    }
}
