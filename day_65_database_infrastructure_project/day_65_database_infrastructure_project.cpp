#include <algorithm>
#include <chrono>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

/*
 * C++17 Database Infrastructure Governance Engine
 *
 * Models a multi-node database cluster with:
 * - Primary and replica nodes
 * - Replication sequence numbers
 * - Read routing
 * - Replication lag
 * - Cache invalidation
 * - Backup snapshots
 * - Checksummed recovery
 * - Failover eligibility
 * - RPO and RTO observations
 *
 * Standard library only.
 */

using namespace std;

enum class Role {
    PRIMARY,
    REPLICA
};

enum class State {
    HEALTHY,
    DEGRADED,
    DOWN,
    RECOVERING
};

enum class ReplicationMode {
    SYNCHRONOUS,
    ASYNCHRONOUS
};

string toString(Role role) {
    return role == Role::PRIMARY ? "PRIMARY" : "REPLICA";
}

string toString(State state) {
    switch (state) {
        case State::HEALTHY: return "HEALTHY";
        case State::DEGRADED: return "DEGRADED";
        case State::DOWN: return "DOWN";
        case State::RECOVERING: return "RECOVERING";
    }

    return "UNKNOWN";
}

class InfrastructureError : public runtime_error {
public:
    explicit InfrastructureError(const string& message)
        : runtime_error(message) {}
};

struct Record {
    string value;
    uint64_t version;
    chrono::system_clock::time_point updatedAt;
};

struct Node {
    string id;
    Role role;
    State state = State::HEALTHY;
    map<string, Record> records;
    uint64_t position = 0;
    size_t activeConnections = 0;

    bool available() const {
        return state == State::HEALTHY ||
               state == State::DEGRADED;
    }
};

struct Configuration {
    ReplicationMode mode = ReplicationMode::ASYNCHRONOUS;
    uint64_t maximumLag = 5;
    size_t maximumConnections = 100;
    size_t cacheCapacity = 100;

    void validate() const {
        if (maximumConnections == 0 ||
            cacheCapacity == 0) {
            throw invalid_argument(
                "Connection and cache capacities must be positive"
            );
        }
    }
};

struct CacheEntry {
    Record record;
    chrono::steady_clock::time_point expiresAt;
};

class LRUCache {
private:
    map<string, CacheEntry> values;
    vector<string> order;
    size_t capacity;
    chrono::seconds ttl;

    void touch(const string& key) {
        order.erase(
            remove(order.begin(), order.end(), key),
            order.end()
        );

        order.push_back(key);
    }

public:
    LRUCache(size_t capacity, int ttlSeconds)
        : capacity(capacity),
          ttl(ttlSeconds) {
        if (capacity == 0 || ttlSeconds <= 0) {
            throw invalid_argument("Invalid cache configuration");
        }
    }

    optional<Record> get(const string& key) {
        auto it = values.find(key);

        if (it == values.end()) {
            return nullopt;
        }

        if (chrono::steady_clock::now() >= it->second.expiresAt) {
            invalidate(key);
            return nullopt;
        }

        touch(key);
        return it->second.record;
    }

    void set(const string& key, const Record& record) {
        values[key] = {
            record,
            chrono::steady_clock::now() + ttl
        };

        touch(key);

        while (values.size() > capacity) {
            const string oldest = order.front();
            order.erase(order.begin());
            values.erase(oldest);
        }
    }

    void invalidate(const string& key) {
        values.erase(key);

        order.erase(
            remove(order.begin(), order.end(), key),
            order.end()
        );
    }

    void clear() {
        values.clear();
        order.clear();
    }

    size_t size() const {
        return values.size();
    }
};

struct LogEntry {
    uint64_t position;
    string key;
    Record record;
};

struct Backup {
    uint64_t position;
    map<string, Record> records;
    uint64_t checksum;
    chrono::system_clock::time_point createdAt;
};

class ReplicationManager {
private:
    vector<LogEntry> log;
    uint64_t sequence = 0;

public:
    uint64_t append(
        const string& key,
        const Record& record
    ) {
        const uint64_t position = ++sequence;

        log.push_back({
            position,
            key,
            record
        });

        return position;
    }

    size_t replicate(
        const Node& primary,
        Node& replica,
        uint64_t maximumLag
    ) const {
        if (!primary.available() || !replica.available()) {
            throw InfrastructureError(
                "Replication endpoint unavailable"
            );
        }

        size_t applied = 0;

        for (const auto& entry : log) {
            if (entry.position <= replica.position) {
                continue;
            }

            replica.records[entry.key] = entry.record;
            replica.position = entry.position;
            applied++;
        }

        const uint64_t lag =
            primary.position > replica.position
                ? primary.position - replica.position
                : 0;

        replica.state = lag > maximumLag
            ? State::DEGRADED
            : State::HEALTHY;

        return applied;
    }
};

class BackupManager {
private:
    static uint64_t hashRecords(
        const map<string, Record>& records
    ) {
        uint64_t hash = 1469598103934665603ULL;

        auto consume = [&](const string& text) {
            for (unsigned char character : text) {
                hash ^= character;
                hash *= 1099511628211ULL;
            }
        };

        for (const auto& [key, record] : records) {
            consume(key);
            consume(record.value);
            consume(to_string(record.version));
        }

        return hash;
    }

public:
    Backup create(const Node& node) const {
        if (!node.available()) {
            throw InfrastructureError(
                "Cannot back up an unavailable node"
            );
        }

        Backup backup{
            node.position,
            node.records,
            hashRecords(node.records),
            chrono::system_clock::now()
        };

        return backup;
    }

    bool verify(const Backup& backup) const {
        return backup.checksum ==
               hashRecords(backup.records);
    }

    void restore(Node& node, const Backup& backup) const {
        if (!verify(backup)) {
            throw InfrastructureError(
                "Backup integrity verification failed"
            );
        }

        node.state = State::RECOVERING;
        node.records = backup.records;
        node.position = backup.position;
        node.state = State::HEALTHY;
    }
};

class DatabaseCluster {
private:
    Configuration config;
    Node primary;
    vector<Node> replicas;

    ReplicationManager replication;
    BackupManager backupManager;
    LRUCache cache;

    uint64_t reads = 0;
    uint64_t writes = 0;
    uint64_t failovers = 0;
    uint64_t cacheHits = 0;
    uint64_t cacheMisses = 0;

    void acquire(Node& node) {
        if (!node.available()) {
            throw InfrastructureError(
                "Node is unavailable: " + node.id
            );
        }

        if (node.activeConnections >=
            config.maximumConnections) {
            throw InfrastructureError(
                "Connection pool exhausted: " + node.id
            );
        }

        node.activeConnections++;
    }

    void release(Node& node) {
        if (node.activeConnections > 0) {
            node.activeConnections--;
        }
    }

public:
    explicit DatabaseCluster(Configuration configuration)
        : config(configuration),
          primary{
              "primary-1",
              Role::PRIMARY
          },
          cache(configuration.cacheCapacity, 30) {
        config.validate();

        replicas.push_back({
            "replica-1",
            Role::REPLICA
        });

        replicas.push_back({
            "replica-2",
            Role::REPLICA
        });
    }

    void write(
        const string& key,
        const string& value
    ) {
        if (key.empty()) {
            throw invalid_argument("Empty record key");
        }

        acquire(primary);

        try {
            uint64_t version = 1;

            auto previous = primary.records.find(key);

            if (previous != primary.records.end()) {
                version = previous->second.version + 1;
            }

            Record record{
                value,
                version,
                chrono::system_clock::now()
            };

            uint64_t position = replication.append(
                key,
                record
            );

            primary.records[key] = record;
            primary.position = position;

            if (config.mode == ReplicationMode::SYNCHRONOUS) {
                bool replicated = false;

                for (auto& replica : replicas) {
                    if (replica.state == State::HEALTHY) {
                        replication.replicate(
                            primary,
                            replica,
                            config.maximumLag
                        );

                        replicated = true;
                    }
                }

                if (!replicated) {
                    throw InfrastructureError(
                        "Synchronous replication unavailable"
                    );
                }
            }

            cache.invalidate(key);
            writes++;

            release(primary);

        } catch (...) {
            release(primary);
            throw;
        }
    }

    optional<Record> read(
        const string& key,
        bool preferReplica = true
    ) {
        auto cached = cache.get(key);

        if (cached.has_value()) {
            cacheHits++;
            return cached;
        }

        cacheMisses++;

        Node* selected = &primary;

        if (preferReplica) {
            for (auto& replica : replicas) {
                if (
                    replica.available() &&
                    primary.position >= replica.position &&
                    primary.position - replica.position <=
                        config.maximumLag
                ) {
                    selected = &replica;
                    break;
                }
            }
        }

        acquire(*selected);

        try {
            auto it = selected->records.find(key);

            reads++;

            if (it == selected->records.end()) {
                release(*selected);
                return nullopt;
            }

            Record record = it->second;
            cache.set(key, record);

            release(*selected);

            return record;

        } catch (...) {
            release(*selected);
            throw;
        }
    }

    size_t synchronize() {
        size_t total = 0;

        for (auto& replica : replicas) {
            if (replica.available()) {
                total += replication.replicate(
                    primary,
                    replica,
                    config.maximumLag
                );
            }
        }

        return total;
    }

    Backup createBackup() const {
        return backupManager.create(primary);
    }

    void restoreBackup(const Backup& backup) {
        backupManager.restore(primary, backup);

        for (auto& replica : replicas) {
            replica.records = primary.records;
            replica.position = primary.position;
            replica.state = State::HEALTHY;
        }

        cache.clear();
    }

    void failNode(const string& nodeId) {
        if (primary.id == nodeId) {
            primary.state = State::DOWN;
            return;
        }

        auto it = find_if(
            replicas.begin(),
            replicas.end(),
            [&](const Node& node) {
                return node.id == nodeId;
            }
        );

        if (it == replicas.end()) {
            throw invalid_argument("Unknown node");
        }

        it->state = State::DOWN;
    }

    void failover() {
        if (primary.state != State::DOWN) {
            throw InfrastructureError(
                "Primary is not down"
            );
        }

        auto candidate = replicas.end();

        for (auto it = replicas.begin();
             it != replicas.end();
             ++it) {
            if (
                it->available() &&
                (
                    candidate == replicas.end() ||
                    it->position > candidate->position
                )
            ) {
                candidate = it;
            }
        }

        if (candidate == replicas.end()) {
            throw InfrastructureError(
                "No healthy replica available"
            );
        }

        Node oldPrimary = primary;

        primary = *candidate;
        primary.role = Role::PRIMARY;

        replicas.erase(candidate);

        oldPrimary.role = Role::REPLICA;
        replicas.push_back(oldPrimary);

        cache.clear();
        failovers++;

        cout << "Failover completed. New primary: "
             << primary.id << '\n';
    }

    void printHealth() const {
        cout << "\nDATABASE CLUSTER HEALTH\n";
        cout << "Primary: " << primary.id << '\n';

        auto printNode = [&](const Node& node) {
            cout << left
                 << setw(18) << node.id
                 << setw(12) << toString(node.role)
                 << setw(12) << toString(node.state)
                 << "Position: " << node.position
                 << " Records: " << node.records.size()
                 << '\n';
        };

        printNode(primary);

        for (const auto& replica : replicas) {
            printNode(replica);
        }

        cout << "\nMetrics\n"
             << "Reads: " << reads << '\n'
             << "Writes: " << writes << '\n'
             << "Cache hits: " << cacheHits << '\n'
             << "Cache misses: " << cacheMisses << '\n'
             << "Failovers: " << failovers << '\n'
             << "Cache entries: " << cache.size() << '\n';
    }
};

int main() {
    try {
        Configuration config;

        config.mode = ReplicationMode::ASYNCHRONOUS;
        config.maximumLag = 5;
        config.maximumConnections = 100;
        config.cacheCapacity = 100;

        DatabaseCluster cluster(config);

        cout << "1. Database writes\n";

        cluster.write("account:1001", "balance=50000");
        cluster.write("account:1002", "balance=75000");
        cluster.write("account:1003", "balance=90000");

        cout << "2. Replica synchronization\n";

        cluster.synchronize();

        cout << "3. Read routing\n";

        auto account = cluster.read("account:1001");

        if (account) {
            cout << "Value: " << account->value << '\n';
        }

        cluster.read("account:1001");

        cout << "4. Backup and checksum verification\n";

        Backup backup = cluster.createBackup();

        BackupManager verifier;

        if (!verifier.verify(backup)) {
            throw InfrastructureError("Backup invalid");
        }

        cout << "Backup verified at position "
             << backup.position << '\n';

        cout << "5. Primary failure simulation\n";

        cluster.failNode("primary-1");
        cluster.failover();

        cout << "6. Post-failover write\n";

        cluster.write("account:1004", "balance=120000");
        cluster.synchronize();

        cout << "7. Health monitoring\n";

        cluster.printHealth();

        cout << "8. Point-in-time snapshot restoration\n";

        cluster.restoreBackup(backup);

        cout << "Backup restoration completed\n";

        cluster.printHealth();

        return 0;

    } catch (const exception& error) {
        cerr << "Infrastructure error: "
             << error.what() << '\n';

        return 1;
    }
}
