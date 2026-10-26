#include <algorithm>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

enum class NodeRole {
    Primary,
    Replica
};

enum class TransactionState {
    Active,
    Committed,
    RolledBack
};

enum class OperationType {
    Put,
    Delete
};

struct Account {
    std::string id;
    std::string owner;
    double balance{};
};

struct LogRecord {
    long long lsn{};
    std::string transactionId;
    OperationType operation;
    std::string key;
    std::optional<Account> value;
};

class DatabaseException : public std::runtime_error {
public:
    explicit DatabaseException(const std::string& message)
        : std::runtime_error(message) {}
};

class ConstraintViolation : public DatabaseException {
public:
    explicit ConstraintViolation(const std::string& message)
        : DatabaseException(message) {}
};

class ReplicationException : public DatabaseException {
public:
    explicit ReplicationException(const std::string& message)
        : DatabaseException(message) {}
};

/*
 * The storage layer uses a map to represent logical records.
 * A real database would map logical records to pages, buffers and
 * persistent files. Keeping the interface narrow lets the transaction
 * and replication layers remain independent of physical storage.
 */
class StorageEngine {
private:
    std::map<std::string, Account> records;

public:
    std::optional<Account> read(const std::string& key) const {
        auto it = records.find(key);
        if (it == records.end()) {
            return std::nullopt;
        }
        return it->second;
    }

    void write(const std::string& key, const Account& account) {
        if (key.empty()) {
            throw ConstraintViolation("Storage key cannot be empty.");
        }
        records[key] = account;
    }

    void erase(const std::string& key) {
        records.erase(key);
    }

    const std::map<std::string, Account>& all() const {
        return records;
    }
};

struct Operation {
    OperationType type;
    std::string key;
    std::optional<Account> value;
};

class Transaction {
private:
    std::string id;
    TransactionState state{TransactionState::Active};
    std::vector<Operation> operations;

public:
    explicit Transaction(std::string transactionId)
        : id(std::move(transactionId)) {}

    void ensureActive() const {
        if (state != TransactionState::Active) {
            throw DatabaseException("Transaction is no longer active.");
        }
    }

    void put(const std::string& key, const Account& account) {
        ensureActive();
        operations.push_back({OperationType::Put, key, account});
    }

    void erase(const std::string& key) {
        ensureActive();
        operations.push_back({OperationType::Delete, key, std::nullopt});
    }

    const std::string& transactionId() const {
        return id;
    }

    std::vector<Operation>& pendingOperations() {
        return operations;
    }

    void commit() {
        ensureActive();
        state = TransactionState::Committed;
    }

    void rollback() {
        ensureActive();
        operations.clear();
        state = TransactionState::RolledBack;
    }
};

class TransactionManager {
private:
    StorageEngine& engine;
    std::vector<LogRecord> wal;
    long long nextLsn{1};

public:
    explicit TransactionManager(StorageEngine& storage)
        : engine(storage) {}

    std::vector<LogRecord> commit(Transaction& transaction) {
        transaction.ensureActive();

        StorageEngine backup = engine;
        std::vector<LogRecord> records;

        try {
            for (const auto& operation : transaction.pendingOperations()) {
                if (operation.type == OperationType::Put) {
                    engine.write(operation.key, *operation.value);
                } else {
                    engine.erase(operation.key);
                }

                records.push_back({
                    nextLsn++,
                    transaction.transactionId(),
                    operation.type,
                    operation.key,
                    operation.value
                });
            }

            wal.insert(wal.end(), records.begin(), records.end());
            transaction.commit();
            return records;
        } catch (...) {
            engine = backup;
            throw;
        }
    }

    const std::vector<LogRecord>& writeAheadLog() const {
        return wal;
    }
};

class DatabaseNode {
private:
    std::string name;
    NodeRole role;
    StorageEngine storage;
    long long appliedLsn{0};
    bool available{true};

public:
    DatabaseNode(std::string nodeName, NodeRole nodeRole)
        : name(std::move(nodeName)), role(nodeRole) {}

    void setAvailable(bool value) {
        available = value;
    }

    bool isAvailable() const {
        return available;
    }

    long long lsn() const {
        return appliedLsn;
    }

    const std::string& nodeName() const {
        return name;
    }

    void setRole(NodeRole newRole) {
        role = newRole;
    }

    NodeRole getRole() const {
        return role;
    }

    StorageEngine& engine() {
        return storage;
    }

    const StorageEngine& engine() const {
        return storage;
    }

    void apply(const LogRecord& record) {
        if (!available) {
            throw ReplicationException(name + " is unavailable.");
        }

        if (record.lsn <= appliedLsn) {
            return;
        }

        if (record.operation == OperationType::Put) {
            storage.write(record.key, *record.value);
        } else {
            storage.erase(record.key);
        }

        appliedLsn = record.lsn;
    }
};

class DatabaseCluster {
private:
    DatabaseNode primary;
    std::vector<DatabaseNode> replicas;

public:
    explicit DatabaseCluster(std::string primaryName)
        : primary(std::move(primaryName), NodeRole::Primary) {}

    DatabaseNode& primaryNode() {
        return primary;
    }

    DatabaseNode& addReplica(const std::string& name) {
        replicas.emplace_back(name, NodeRole::Replica);
        return replicas.back();
    }

    void replicate(const std::vector<LogRecord>& records) {
        for (auto& replica : replicas) {
            if (!replica.isAvailable()) {
                continue;
            }

            for (const auto& record : records) {
                replica.apply(record);
            }
        }
    }

    DatabaseNode& failover() {
        auto candidate = std::max_element(
            replicas.begin(),
            replicas.end(),
            [](const DatabaseNode& left, const DatabaseNode& right) {
                return left.lsn() < right.lsn();
            }
        );

        if (candidate == replicas.end() || !candidate->isAvailable()) {
            throw ReplicationException("No available replica for failover.");
        }

        primary.setRole(NodeRole::Replica);
        candidate->setRole(NodeRole::Primary);

        /*
         * This educational model cannot move the object itself because
         * references to the cluster's primary are intentionally stable.
         * The promoted node is returned as the authoritative node.
         */
        return *candidate;
    }

    void printHealth() const {
        std::cout << "Primary: " << primary.nodeName()
                  << " LSN=" << primary.lsn()
                  << " available=" << std::boolalpha
                  << primary.isAvailable() << '\n';

        for (const auto& replica : replicas) {
            std::cout << "Replica: " << replica.nodeName()
                      << " LSN=" << replica.lsn()
                      << " lag=" << primary.lsn() - replica.lsn()
                      << " available=" << replica.isAvailable() << '\n';
        }
    }
};

class AccountService {
private:
    StorageEngine& engine;

    static std::string key(const std::string& id) {
        return "account:" + id;
    }

public:
    explicit AccountService(StorageEngine& storage)
        : engine(storage) {}

    void create(
        Transaction& transaction,
        const std::string& id,
        const std::string& owner,
        double balance
    ) {
        if (id.empty() || owner.empty()) {
            throw ConstraintViolation("Account ID and owner are required.");
        }

        if (balance < 0) {
            throw ConstraintViolation("Balance cannot be negative.");
        }

        if (engine.read(key(id)).has_value()) {
            throw ConstraintViolation("Account already exists.");
        }

        transaction.put(key(id), Account{id, owner, balance});
    }

    void transfer(
        Transaction& transaction,
        const std::string& source,
        const std::string& target,
        double amount
    ) {
        if (source == target) {
            throw ConstraintViolation("Source and target must differ.");
        }

        if (amount <= 0) {
            throw ConstraintViolation("Transfer must be positive.");
        }

        auto sourceAccount = engine.read(key(source));
        auto targetAccount = engine.read(key(target));

        if (!sourceAccount || !targetAccount) {
            throw ConstraintViolation("Both accounts must exist.");
        }

        if (sourceAccount->balance < amount) {
            throw ConstraintViolation("Insufficient funds.");
        }

        sourceAccount->balance -= amount;
        targetAccount->balance += amount;

        transaction.put(key(source), *sourceAccount);
        transaction.put(key(target), *targetAccount);
    }
};

int main() {
    try {
        DatabaseCluster cluster("db-primary-01");

        auto& replicaA = cluster.addReplica("db-replica-01");
        auto& replicaB = cluster.addReplica("db-replica-02");

        TransactionManager transactions(cluster.primaryNode().engine());
        AccountService accounts(cluster.primaryNode().engine());

        Transaction create("TX-1001");
        accounts.create(create, "A100", "Operations", 1000.00);
        accounts.create(create, "A200", "Analytics", 250.00);

        auto createLog = transactions.commit(create);
        cluster.replicate(createLog);

        Transaction transfer("TX-1002");
        accounts.transfer(transfer, "A100", "A200", 125.00);

        auto transferLog = transactions.commit(transfer);
        cluster.replicate(transferLog);

        auto replicatedAccount = replicaA.engine().read("account:A200");
        if (!replicatedAccount || replicatedAccount->balance != 375.00) {
            throw DatabaseException("Replica consistency validation failed.");
        }

        Transaction failed("TX-1003");

        try {
            accounts.transfer(failed, "A100", "A200", 5000.00);
            transactions.commit(failed);
        } catch (const ConstraintViolation&) {
            failed.rollback();
        }

        replicaB.setAvailable(false);

        std::cout << "Database infrastructure governance simulation\n";
        std::cout << "=============================================\n";
        cluster.printHealth();

        DatabaseNode& promoted = cluster.failover();

        std::cout << "\nPromoted replica: " << promoted.nodeName() << '\n';
        std::cout << "Promoted LSN: " << promoted.lsn() << '\n';

        auto accountA = promoted.engine().read("account:A100");
        auto accountB = promoted.engine().read("account:A200");

        if (accountA && accountB) {
            std::cout << std::fixed << std::setprecision(2);
            std::cout << "A100 balance: " << accountA->balance << '\n';
            std::cout << "A200 balance: " << accountB->balance << '\n';
        }

        std::cout << "\nWAL records: "
                  << transactions.writeAheadLog().size() << '\n';
        std::cout << "Replica A LSN: " << replicaA.lsn() << '\n';
        std::cout << "Replica B LSN: " << replicaB.lsn() << '\n';
    } catch (const std::exception& error) {
        std::cerr << "Database infrastructure failure: "
                  << error.what() << '\n';
        return 1;
    }

    return 0;
}
