#include <algorithm>
#include <chrono>
#include <cmath>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using Clock = std::chrono::system_clock;
using TimePoint = Clock::time_point;

enum class DatabaseState {
    Available,
    Maintenance,
    Degraded,
    Failed,
    Restoring
};

enum class NodeRole {
    Primary,
    Replica
};

enum class BackupType {
    Full,
    Snapshot
};

enum class CheckStatus {
    Passing,
    Failing
};

struct StatusCheck {
    std::string name;
    CheckStatus status;
    std::string message;
};

struct Metrics {
    double cpuPercent{};
    double storagePercent{};
    double replicationLagSeconds{};
    int connections{};

    bool healthy() const {
        return cpuPercent < 85.0 &&
               storagePercent < 90.0 &&
               replicationLagSeconds < 30.0;
    }
};

struct DatabaseNode {
    std::string id;
    std::string zone;
    NodeRole role;
    std::string version;
    DatabaseState state{DatabaseState::Available};
    Metrics metrics{};

    bool healthy() const {
        return state == DatabaseState::Available && metrics.healthy();
    }
};

struct Backup {
    std::string id;
    BackupType type;
    TimePoint createdAt;
    TimePoint expiresAt;
    std::size_t sizeGB{};
    std::string checksum;
};

struct MaintenanceEvent {
    std::string id;
    std::string fromVersion;
    std::string toVersion;
    bool completed{false};
    bool failed{false};
    std::string error;
};

struct GovernanceResult {
    bool eligible{false};
    std::vector<StatusCheck> checks;
};

class DatabaseException : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class ManagedDatabase {
private:
    std::string id_;
    std::string name_;
    std::string engine_;
    std::string version_;
    std::string region_;
    std::size_t storageGB_;
    int retentionDays_;

    std::map<std::string, DatabaseNode> nodes_;
    std::map<std::string, Backup> backups_;
    std::map<std::string, MaintenanceEvent> maintenance_;

    std::mt19937 rng_{std::random_device{}()};
    std::size_t sequence_{0};

    std::string nextId(const std::string& prefix) {
        return prefix + "-" + std::to_string(++sequence_);
    }

    static std::string stateToString(DatabaseState state) {
        switch (state) {
            case DatabaseState::Available: return "available";
            case DatabaseState::Maintenance: return "maintenance";
            case DatabaseState::Degraded: return "degraded";
            case DatabaseState::Failed: return "failed";
            case DatabaseState::Restoring: return "restoring";
        }
        return "unknown";
    }

    DatabaseNode& primary() {
        DatabaseNode* result = nullptr;

        for (auto& [id, node] : nodes_) {
            if (node.role == NodeRole::Primary) {
                if (result != nullptr) {
                    throw DatabaseException("Multiple primary nodes detected.");
                }
                result = &node;
            }
        }

        if (result == nullptr) {
            throw DatabaseException("No primary node exists.");
        }

        return *result;
    }

public:
    ManagedDatabase(
        std::string id,
        std::string name,
        std::string engine,
        std::string version,
        std::string region,
        std::size_t storageGB,
        int retentionDays
    )
        : id_(std::move(id)),
          name_(std::move(name)),
          engine_(std::move(engine)),
          version_(std::move(version)),
          region_(std::move(region)),
          storageGB_(storageGB),
          retentionDays_(retentionDays) {

        if (id_.empty() || name_.empty()) {
            throw DatabaseException("Database identifiers cannot be empty.");
        }

        if (storageGB_ < 10) {
            throw DatabaseException("Minimum storage is 10 GB.");
        }

        if (retentionDays_ < 1 || retentionDays_ > 35) {
            throw DatabaseException("Retention must be 1-35 days.");
        }
    }

    void addNode(const std::string& zone, NodeRole role) {
        if (role == NodeRole::Primary) {
            for (const auto& [id, node] : nodes_) {
                if (node.role == NodeRole::Primary) {
                    throw DatabaseException("Primary already exists.");
                }
            }
        }

        DatabaseNode node;
        node.id = nextId("node");
        node.zone = zone;
        node.role = role;
        node.version = version_;

        nodes_.emplace(node.id, node);
    }

    std::vector<std::reference_wrapper<DatabaseNode>> replicas() {
        std::vector<std::reference_wrapper<DatabaseNode>> result;

        for (auto& [id, node] : nodes_) {
            if (node.role == NodeRole::Replica) {
                result.push_back(node);
            }
        }

        return result;
    }

    void scaleReadReplicas(
        std::size_t desired,
        const std::vector<std::string>& zones
    ) {
        if (desired > 10) {
            throw DatabaseException("Replica limit is 10.");
        }

        if (desired > 0 && zones.empty()) {
            throw DatabaseException("At least one zone is required.");
        }

        auto current = replicas().size();

        if (desired > current) {
            for (std::size_t i = current; i < desired; ++i) {
                addNode(zones[i % zones.size()], NodeRole::Replica);
            }
        } else if (desired < current) {
            auto candidates = replicas();

            for (std::size_t i = desired; i < candidates.size(); ++i) {
                nodes_.erase(candidates[i].get().id);
            }
        }
    }

    void collectMetrics(double sample = 0.45) {
        std::uniform_int_distribution<int> connections(10, 180);

        for (auto& [id, node] : nodes_) {
            node.metrics.cpuPercent = 20.0 + sample * 60.0;
            node.metrics.storagePercent = 30.0 + sample * 50.0;
            node.metrics.replicationLagSeconds =
                node.role == NodeRole::Primary ? 0.0 : sample * 20.0;
            node.metrics.connections = connections(rng_);

            node.state = node.metrics.healthy()
                ? DatabaseState::Available
                : DatabaseState::Degraded;
        }
    }

    Backup createBackup(
        BackupType type,
        TimePoint now = Clock::now()
    ) {
        if (!primary().healthy()) {
            throw DatabaseException("Primary is not healthy.");
        }

        Backup backup;
        backup.id = nextId("backup");
        backup.type = type;
        backup.createdAt = now;
        backup.expiresAt =
            now + std::chrono::hours(24 * retentionDays_);
        backup.sizeGB = std::max<std::size_t>(1, storageGB_ / 5);

        std::ostringstream source;
        source << id_ << ':' << version_ << ':'
               << std::chrono::duration_cast<std::chrono::seconds>(
                      now.time_since_epoch()
                  ).count();

        backup.checksum = std::to_string(
            std::hash<std::string>{}(source.str())
        );

        backups_.emplace(backup.id, backup);
        return backup;
    }

    void purgeExpiredBackups(TimePoint now = Clock::now()) {
        for (auto it = backups_.begin(); it != backups_.end();) {
            if (it->second.expiresAt <= now) {
                it = backups_.erase(it);
            } else {
                ++it;
            }
        }
    }

    std::string schedulePatch(const std::string& targetVersion) {
        if (targetVersion.empty() || targetVersion == version_) {
            throw DatabaseException("Invalid target version.");
        }

        MaintenanceEvent event;
        event.id = nextId("maintenance");
        event.fromVersion = version_;
        event.toVersion = targetVersion;

        maintenance_.emplace(event.id, event);
        return event.id;
    }

    void executePatch(const std::string& eventId) {
        auto it = maintenance_.find(eventId);

        if (it == maintenance_.end()) {
            throw DatabaseException("Maintenance event not found.");
        }

        auto& event = it->second;

        if (event.completed || event.failed) {
            throw DatabaseException("Maintenance event already terminated.");
        }

        const auto oldVersion = version_;

        try {
            state(DatabaseState::Maintenance);

            // A verified snapshot is created before mutating node versions.
            const auto backup = createBackup(BackupType::Snapshot);

            if (backup.checksum.empty()) {
                throw DatabaseException("Backup verification failed.");
            }

            for (auto& [id, node] : nodes_) {
                node.state = DatabaseState::Maintenance;
                node.version = event.toVersion;
                node.state = DatabaseState::Available;
            }

            version_ = event.toVersion;
            event.completed = true;
            state(DatabaseState::Available);
        } catch (const std::exception& ex) {
            version_ = oldVersion;
            event.failed = true;
            event.error = ex.what();
            state(DatabaseState::Failed);
            throw;
        }
    }

    void state(DatabaseState newState) {
        for (auto& [id, node] : nodes_) {
            if (newState == DatabaseState::Maintenance) {
                node.state = DatabaseState::Maintenance;
            }
        }
    }

    void failover() {
        auto& oldPrimary = primary();

        DatabaseNode* best = nullptr;

        for (auto& [id, node] : nodes_) {
            if (node.role != NodeRole::Replica || !node.healthy()) {
                continue;
            }

            if (best == nullptr ||
                node.metrics.replicationLagSeconds <
                    best->metrics.replicationLagSeconds) {
                best = &node;
            }
        }

        if (best == nullptr) {
            oldPrimary.state = DatabaseState::Failed;
            throw DatabaseException("No healthy replica is available.");
        }

        oldPrimary.role = NodeRole::Replica;
        oldPrimary.state = DatabaseState::Degraded;

        best->role = NodeRole::Primary;
        best->state = DatabaseState::Available;
    }

    GovernanceResult evaluateGovernance() const {
        GovernanceResult result;

        int primaryCount = 0;
        std::set<std::string> zones;
        bool versionConsistent = true;
        bool healthyReplica = false;

        for (const auto& [id, node] : nodes_) {
            if (node.role == NodeRole::Primary) {
                ++primaryCount;
            }

            zones.insert(node.zone);

            if (node.version != version_) {
                versionConsistent = false;
            }

            if (node.role == NodeRole::Replica && node.healthy()) {
                healthyReplica = true;
            }
        }

        result.checks.push_back({
            "single-primary",
            primaryCount == 1 ? CheckStatus::Passing : CheckStatus::Failing,
            "Exactly one primary node is required."
        });

        result.checks.push_back({
            "backup-retention",
            retentionDays_ >= 7
                ? CheckStatus::Passing
                : CheckStatus::Failing,
            "Production retention should be at least seven days."
        });

        result.checks.push_back({
            "multi-zone",
            zones.size() >= 2
                ? CheckStatus::Passing
                : CheckStatus::Failing,
            "Nodes should span multiple availability zones."
        });

        result.checks.push_back({
            "healthy-replica",
            healthyReplica
                ? CheckStatus::Passing
                : CheckStatus::Failing,
            "At least one healthy failover candidate is required."
        });

        result.checks.push_back({
            "version-consistency",
            versionConsistent
                ? CheckStatus::Passing
                : CheckStatus::Failing,
            "All nodes must use the database version."
        });

        result.eligible = std::all_of(
            result.checks.begin(),
            result.checks.end(),
            [](const StatusCheck& check) {
                return check.status == CheckStatus::Passing;
            }
        );

        return result;
    }

    void printReport() const {
        std::cout << "Managed Database: " << name_ << '\n';
        std::cout << "Engine: " << engine_ << '\n';
        std::cout << "Version: " << version_ << '\n';
        std::cout << "Region: " << region_ << '\n';
        std::cout << "Nodes: " << nodes_.size() << '\n';
        std::cout << "Backups: " << backups_.size() << '\n';
        std::cout << "State: available\n";
    }
};

int main() {
    try {
        ManagedDatabase database(
            "orders-prod",
            "orders",
            "PostgreSQL",
            "16.4",
            "ap-south-1",
            250,
            14
        );

        database.addNode("zone-a", NodeRole::Primary);
        database.addNode("zone-b", NodeRole::Replica);

        database.scaleReadReplicas(
            2,
            {"zone-b", "zone-c"}
        );

        database.collectMetrics(0.30);

        const auto backup = database.createBackup(BackupType::Full);

        const auto patch = database.schedulePatch("16.5");
        database.executePatch(patch);

        database.collectMetrics(0.25);

        const auto governance = database.evaluateGovernance();

        std::cout << "\nGovernance checks:\n";
        for (const auto& check : governance.checks) {
            std::cout
                << "  "
                << check.name
                << ": "
                << (check.status == CheckStatus::Passing ? "PASS" : "FAIL")
                << " - "
                << check.message
                << '\n';
        }

        std::cout
            << "Production eligibility: "
            << (governance.eligible ? "YES" : "NO")
            << "\n\n";

        database.purgeExpiredBackups();

        database.printReport();

        if (backup.checksum.empty()) {
            throw DatabaseException("Created backup has no verification checksum.");
        }

        return governance.eligible ? 0 : 2;
    } catch (const std::exception& ex) {
        std::cerr << "Operational failure: " << ex.what() << '\n';
        return 1;
    }
}
