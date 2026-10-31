#include <algorithm>
#include <chrono>
#include <deque>
#include <exception>
#include <iostream>
#include <optional>
#include <queue>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

enum class ReviewConsistency {
    Strong,
    Eventual
};

struct VersionedValue {
    std::string value;
    std::uint64_t version;
};

class ValidationError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class ConflictError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

static void validateKey(const std::string& key) {
    if (key.empty() || key.size() > 256) {
        throw ValidationError("Key must contain 1..256 characters");
    }
}

class KeyValueStore {
private:
    std::unordered_map<std::string, VersionedValue> data;

public:
    std::uint64_t put(
        const std::string& key,
        const std::string& value,
        std::optional<std::uint64_t> expected = std::nullopt
    ) {
        validateKey(key);

        std::uint64_t currentVersion = 0;

        auto it = data.find(key);
        if (it != data.end()) {
            currentVersion = it->second.version;
        }

        if (expected.has_value() && expected.value() != currentVersion) {
            throw ConflictError("Optimistic version check failed");
        }

        const std::uint64_t newVersion = currentVersion + 1;
        data[key] = {value, newVersion};

        return newVersion;
    }

    std::optional<VersionedValue> get(const std::string& key) const {
        validateKey(key);

        auto it = data.find(key);
        if (it == data.end()) {
            return std::nullopt;
        }

        return it->second;
    }
};

struct Document {
    std::string id;
    std::unordered_map<std::string, std::string> fields;
};

class DocumentStore {
private:
    std::unordered_map<std::string, Document> documents;
    std::unordered_map<
        std::string,
        std::unordered_map<std::string, std::unordered_set<std::string>>
    > indexes;

public:
    void insert(const Document& document) {
        validateKey(document.id);

        if (documents.contains(document.id)) {
            throw ConflictError("Document already exists");
        }

        if (!document.fields.contains("department") ||
            !document.fields.contains("name")) {
            throw ValidationError("Document requires name and department");
        }

        documents.emplace(document.id, document);

        for (const auto& [field, value] : document.fields) {
            indexes[field][value].insert(document.id);
        }
    }

    std::vector<Document> find(
        const std::string& field,
        const std::string& value
    ) const {
        std::vector<Document> result;

        auto fieldIt = indexes.find(field);
        if (fieldIt == indexes.end()) {
            return result;
        }

        auto valueIt = fieldIt->second.find(value);
        if (valueIt == fieldIt->second.end()) {
            return result;
        }

        for (const auto& id : valueIt->second) {
            result.push_back(documents.at(id));
        }

        return result;
    }
};

struct TelemetryRow {
    std::string clusteringKey;
    std::unordered_map<std::string, double> values;
};

class WideColumnStore {
private:
    std::unordered_map<
        std::string,
        std::map<std::string, std::unordered_map<std::string, double>>
    > partitions;

public:
    void upsert(
        const std::string& partitionKey,
        const std::string& clusteringKey,
        const std::unordered_map<std::string, double>& columns
    ) {
        validateKey(partitionKey);
        validateKey(clusteringKey);

        auto& row = partitions[partitionKey][clusteringKey];

        for (const auto& [column, value] : columns) {
            row[column] = value;
        }
    }

    std::vector<TelemetryRow> query(
        const std::string& partitionKey
    ) const {
        std::vector<TelemetryRow> result;

        auto it = partitions.find(partitionKey);
        if (it == partitions.end()) {
            return result;
        }

        for (const auto& [clusteringKey, columns] : it->second) {
            result.push_back({clusteringKey, columns});
        }

        return result;
    }
};

struct Edge {
    std::string target;
    std::string relationship;
};

class GraphStore {
private:
    std::unordered_set<std::string> nodes;
    std::unordered_map<std::string, std::vector<Edge>> adjacency;

public:
    void addNode(const std::string& id) {
        validateKey(id);
        nodes.insert(id);
    }

    void addEdge(
        const std::string& source,
        const std::string& target,
        const std::string& relationship
    ) {
        if (!nodes.contains(source) || !nodes.contains(target)) {
            throw ValidationError("Graph endpoints must exist");
        }

        adjacency[source].push_back({target, relationship});
    }

    std::optional<std::vector<std::string>> shortestPath(
        const std::string& source,
        const std::string& target
    ) const {
        if (!nodes.contains(source) || !nodes.contains(target)) {
            return std::nullopt;
        }

        std::queue<std::pair<std::string, std::vector<std::string>>> queue;
        std::unordered_set<std::string> visited;

        queue.push({source, {source}});
        visited.insert(source);

        while (!queue.empty()) {
            auto [node, path] = std::move(queue.front());
            queue.pop();

            if (node == target) {
                return path;
            }

            auto it = adjacency.find(node);
            if (it == adjacency.end()) {
                continue;
            }

            for (const auto& edge : it->second) {
                if (!visited.contains(edge.target)) {
                    visited.insert(edge.target);

                    auto nextPath = path;
                    nextPath.push_back(edge.target);
                    queue.push({edge.target, std::move(nextPath)});
                }
            }
        }

        return std::nullopt;
    }
};

class ReplicatedKeyValueCluster {
private:
    KeyValueStore leader;
    std::vector<KeyValueStore> replicas;

    struct ReplicationEvent {
        std::size_t replicaIndex;
        std::string key;
        std::uint64_t version;
    };

    std::deque<ReplicationEvent> queue;

public:
    explicit ReplicatedKeyValueCluster(std::size_t replicaCount)
        : replicas(replicaCount) {}

    std::uint64_t write(
        const std::string& key,
        const std::string& value
    ) {
        const auto version = leader.put(key, value);

        for (std::size_t i = 0; i < replicas.size(); ++i) {
            queue.push_back({i, key, version});
        }

        return version;
    }

    std::optional<VersionedValue> read(
        const std::string& key,
        std::optional<std::size_t> replica = std::nullopt
    ) const {
        if (!replica.has_value()) {
            return leader.get(key);
        }

        if (replica.value() >= replicas.size()) {
            throw ValidationError("Invalid replica index");
        }

        return replicas[replica.value()].get(key);
    }

    void replicate() {
        while (!queue.empty()) {
            const auto event = queue.front();
            queue.pop_front();

            const auto leaderValue = leader.get(event.key);
            if (!leaderValue.has_value()) {
                continue;
            }

            const auto current = replicas[event.replicaIndex].get(event.key);

            if (!current.has_value() ||
                leaderValue->version >= current->version) {
                replicas[event.replicaIndex].put(
                    event.key,
                    leaderValue->value
                );
            }
        }
    }
};

static void printPath(
    const std::optional<std::vector<std::string>>& path
) {
    if (!path.has_value()) {
        std::cout << "No path\n";
        return;
    }

    for (std::size_t i = 0; i < path->size(); ++i) {
        if (i != 0) {
            std::cout << " -> ";
        }
        std::cout << path->at(i);
    }
    std::cout << '\n';
}

int main() {
    try {
        std::cout << "=== NoSQL Infrastructure Governance Case Study ===\n";

        KeyValueStore kv;
        const auto version = kv.put(
            "session:1001",
            "role=engineer;active=true"
        );

        std::cout << "KV version: " << version << '\n';

        try {
            kv.put(
                "session:1001",
                "role=admin",
                version - 1
            );
        } catch (const ConflictError& error) {
            std::cout << "Expected conflict: "
                      << error.what() << '\n';
        }

        DocumentStore documents;

        documents.insert({
            "u1001",
            {
                {"name", "Anita"},
                {"department", "security"},
                {"risk", "low"}
            }
        });

        documents.insert({
            "u1002",
            {
                {"name", "Ravi"},
                {"department", "engineering"},
                {"risk", "medium"}
            }
        });

        const auto securityUsers =
            documents.find("department", "security");

        std::cout << "Security documents: "
                  << securityUsers.size() << '\n';

        WideColumnStore telemetry;

        telemetry.upsert(
            "device-42",
            "2026-10-31T11:00:00Z",
            {{"temperature", 31.2}, {"battery", 88}}
        );

        telemetry.upsert(
            "device-42",
            "2026-10-31T11:01:00Z",
            {{"temperature", 31.4}}
        );

        std::cout << "Telemetry rows: "
                  << telemetry.query("device-42").size()
                  << '\n';

        GraphStore graph;

        for (const auto& node : {
            std::string("alice"),
            std::string("bob"),
            std::string("carol"),
            std::string("database")
        }) {
            graph.addNode(node);
        }

        graph.addEdge("alice", "bob", "trusts");
        graph.addEdge("bob", "carol", "trusts");
        graph.addEdge("carol", "database", "accesses");

        std::cout << "Graph path: ";
        printPath(graph.shortestPath("alice", "database"));

        ReplicatedKeyValueCluster cluster(2);

        cluster.write(
            "service:payments",
            "enabled=true;timeout=1500"
        );

        const auto beforeReplication =
            cluster.read("service:payments", 0);

        std::cout << "Replica before replication: "
                  << (beforeReplication.has_value()
                          ? beforeReplication->value
                          : "<stale/missing>")
                  << '\n';

        cluster.replicate();

        const auto afterReplication =
            cluster.read("service:payments", 0);

        std::cout << "Replica after replication: "
                  << afterReplication->value << '\n';

        std::cout << "\nDesign constraints:\n";
        std::cout << "- Key-value access uses hash-based lookup.\n";
        std::cout << "- Documents are indexed for equality queries.\n";
        std::cout << "- Wide-column data is partitioned by access pattern.\n";
        std::cout << "- Graph traversal uses breadth-first search.\n";
        std::cout << "- Replicas may be stale until queued writes propagate.\n";
        std::cout << "- Version checks prevent silent lost updates.\n";
        std::cout << "- Sensitive values require external encryption and access control.\n";

    } catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
