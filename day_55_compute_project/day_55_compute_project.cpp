#include <algorithm>
#include <chrono>
#include <cstddef>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

class InfrastructureError : public std::runtime_error {
public:
    explicit InfrastructureError(const std::string& message)
        : std::runtime_error(message) {}
};

enum class InstanceState {
    Running,
    Unhealthy,
    Stopped
};

enum class BackupState {
    Available,
    Restoring,
    Failed
};

struct Instance {
    std::string id;
    std::size_t capacity;
    std::size_t activeRequests = 0;
    InstanceState state = InstanceState::Running;

    double utilization() const {
        if (capacity == 0) {
            return 1.0;
        }
        return static_cast<double>(activeRequests) /
               static_cast<double>(capacity);
    }

    bool canReceiveTraffic() const {
        return state == InstanceState::Running &&
               activeRequests < capacity;
    }
};

struct ObjectRecord {
    std::string key;
    std::string content;
    std::size_t size;
    std::string checksum;
};

struct Backup {
    std::string id;
    BackupState state = BackupState::Available;
    std::unordered_map<std::string, ObjectRecord> objects;
};

struct BranchProtectionPolicy {
    bool requireHealthyInstances = true;
    bool requireBackup = true;
    bool requireMinimumCapacity = true;
    bool prohibitUnhealthyTargets = true;
    std::size_t minimumHealthyInstances = 2;
    std::size_t minimumCapacity = 200;
};

struct MergeEvaluation {
    bool eligible;
    std::vector<std::string> failures;
};

class ObjectStorage {
private:
    std::unordered_map<std::string, ObjectRecord> objects_;

    // This checksum is intentionally simple for a self-contained C++17
    // example. Production storage should use a cryptographic hash library.
    static std::string checksum(const std::string& content) {
        std::size_t value = std::hash<std::string>{}(content);
        std::ostringstream output;
        output << std::hex << value;
        return output.str();
    }

public:
    void put(const std::string& key, const std::string& content) {
        if (key.empty() || key.front() == '/') {
            throw InfrastructureError(
                "Storage key must be non-empty and relative."
            );
        }

        ObjectRecord record{
            key,
            content,
            content.size(),
            checksum(content)
        };

        objects_[key] = std::move(record);
    }

    const ObjectRecord& get(const std::string& key) const {
        auto iterator = objects_.find(key);

        if (iterator == objects_.end()) {
            throw InfrastructureError(
                "Storage object does not exist: " + key
            );
        }

        if (checksum(iterator->second.content) !=
            iterator->second.checksum) {
            throw InfrastructureError(
                "Storage integrity check failed: " + key
            );
        }

        return iterator->second;
    }

    void remove(const std::string& key) {
        if (objects_.erase(key) == 0) {
            throw InfrastructureError(
                "Cannot remove missing object: " + key
            );
        }
    }

    std::unordered_map<std::string, ObjectRecord> snapshot() const {
        return objects_;
    }

    void restore(
        const std::unordered_map<std::string, ObjectRecord>& snapshot
    ) {
        objects_ = snapshot;
    }

    std::size_t objectCount() const {
        return objects_.size();
    }

    std::size_t totalBytes() const {
        std::size_t total = 0;

        for (const auto& [key, object] : objects_) {
            total += object.size;
        }

        return total;
    }
};

class BackupManager {
private:
    ObjectStorage& storage_;
    std::vector<Backup> backups_;
    std::size_t sequence_ = 0;

public:
    explicit BackupManager(ObjectStorage& storage)
        : storage_(storage) {}

    const Backup& createBackup() {
        ++sequence_;

        Backup backup;
        std::ostringstream id;
        id << "backup-" << std::setw(4) << std::setfill('0')
           << sequence_;

        backup.id = id.str();
        backup.objects = storage_.snapshot();

        backups_.push_back(std::move(backup));
        return backups_.back();
    }

    void restore(const std::string& id) {
        auto iterator = std::find_if(
            backups_.begin(),
            backups_.end(),
            [&](const Backup& backup) {
                return backup.id == id;
            }
        );

        if (iterator == backups_.end()) {
            throw InfrastructureError(
                "Backup does not exist: " + id
            );
        }

        iterator->state = BackupState::Restoring;

        try {
            storage_.restore(iterator->objects);
            iterator->state = BackupState::Available;
        } catch (...) {
            iterator->state = BackupState::Failed;
            throw;
        }
    }

    bool hasBackup() const {
        return !backups_.empty();
    }

    std::size_t count() const {
        return backups_.size();
    }
};

class LoadBalancer {
private:
    std::vector<Instance>* instances_;

public:
    explicit LoadBalancer(std::vector<Instance>& instances)
        : instances_(&instances) {}

    Instance& route() {
        auto candidate = std::min_element(
            instances_->begin(),
            instances_->end(),
            [](const Instance& left, const Instance& right) {
                const bool leftAvailable = left.canReceiveTraffic();
                const bool rightAvailable = right.canReceiveTraffic();

                if (leftAvailable != rightAvailable) {
                    return leftAvailable;
                }

                return left.utilization() < right.utilization();
            }
        );

        if (candidate == instances_->end() ||
            !candidate->canReceiveTraffic()) {
            throw InfrastructureError(
                "Load balancer has no available compute capacity."
            );
        }

        return *candidate;
    }

    std::map<std::string, std::size_t>
    dispatch(std::size_t requestCount) {
        std::map<std::string, std::size_t> distribution;

        for (std::size_t i = 0; i < requestCount; ++i) {
            Instance& instance = route();
            ++instance.activeRequests;
            ++distribution[instance.id];
        }

        return distribution;
    }

    void complete(std::size_t requestCount) {
        std::size_t remaining = requestCount;

        std::sort(
            instances_->begin(),
            instances_->end(),
            [](const Instance& left, const Instance& right) {
                return left.activeRequests > right.activeRequests;
            }
        );

        for (auto& instance : *instances_) {
            const std::size_t completed =
                std::min(instance.activeRequests, remaining);

            instance.activeRequests -= completed;
            remaining -= completed;

            if (remaining == 0) {
                return;
            }
        }

        if (remaining > 0) {
            throw InfrastructureError(
                "Cannot complete more requests than are active."
            );
        }
    }
};

class RepositoryGovernanceEngine {
private:
    std::vector<Instance>& instances_;
    BackupManager& backups_;
    BranchProtectionPolicy policy_;

    std::size_t healthyInstances() const {
        return static_cast<std::size_t>(
            std::count_if(
                instances_.begin(),
                instances_.end(),
                [](const Instance& instance) {
                    return instance.state == InstanceState::Running;
                }
            )
        );
    }

    std::size_t healthyCapacity() const {
        std::size_t capacity = 0;

        for (const auto& instance : instances_) {
            if (instance.state == InstanceState::Running) {
                capacity += instance.capacity;
            }
        }

        return capacity;
    }

public:
    RepositoryGovernanceEngine(
        std::vector<Instance>& instances,
        BackupManager& backups,
        BranchProtectionPolicy policy
    )
        : instances_(instances),
          backups_(backups),
          policy_(policy) {}

    MergeEvaluation evaluateDeployment() const {
        MergeEvaluation result{true, {}};

        if (
            policy_.requireHealthyInstances &&
            healthyInstances() < policy_.minimumHealthyInstances
        ) {
            result.eligible = false;
            result.failures.push_back(
                "Required number of healthy compute instances is unavailable."
            );
        }

        if (
            policy_.requireMinimumCapacity &&
            healthyCapacity() < policy_.minimumCapacity
        ) {
            result.eligible = false;
            result.failures.push_back(
                "Healthy compute capacity is below the policy minimum."
            );
        }

        if (policy_.requireBackup && !backups_.hasBackup()) {
            result.eligible = false;
            result.failures.push_back(
                "A recoverable backup is required before deployment."
            );
        }

        return result;
    }
};

class ComputeStoragePlatform {
private:
    std::vector<Instance> instances_;
    ObjectStorage storage_;
    BackupManager backups_;
    LoadBalancer loadBalancer_;

public:
    ComputeStoragePlatform()
        : instances_{
              {"app-01", 100},
              {"app-02", 100}
          },
          storage_(),
          backups_(storage_),
          loadBalancer_(instances_) {}

    std::vector<Instance>& instances() {
        return instances_;
    }

    ObjectStorage& storage() {
        return storage_;
    }

    BackupManager& backups() {
        return backups_;
    }

    LoadBalancer& loadBalancer() {
        return loadBalancer_;
    }

    std::size_t healthyCapacity() const {
        std::size_t capacity = 0;

        for (const auto& instance : instances_) {
            if (instance.state == InstanceState::Running) {
                capacity += instance.capacity;
            }
        }

        return capacity;
    }

    void addInstance(const std::string& id, std::size_t capacity) {
        if (capacity == 0) {
            throw InfrastructureError(
                "A compute instance must have positive capacity."
            );
        }

        if (
            std::any_of(
                instances_.begin(),
                instances_.end(),
                [&](const Instance& instance) {
                    return instance.id == id;
                }
            )
        ) {
            throw InfrastructureError(
                "Duplicate instance identifier: " + id
            );
        }

        instances_.push_back({id, capacity});
    }

    void markUnhealthy(const std::string& id) {
        auto iterator = std::find_if(
            instances_.begin(),
            instances_.end(),
            [&](const Instance& instance) {
                return instance.id == id;
            }
        );

        if (iterator == instances_.end()) {
            throw InfrastructureError(
                "Instance does not exist: " + id
            );
        }

        if (iterator->activeRequests > 0) {
            throw InfrastructureError(
                "Instance must drain active requests before failure."
            );
        }

        iterator->state = InstanceState::Unhealthy;
    }
};

void assertCondition(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error("Test failed: " + message);
    }
}

void runTests() {
    ComputeStoragePlatform platform;

    platform.storage().put(
        "config/application.json",
        R"({"version":"1.0.0","region":"primary"})"
    );

    assertCondition(
        platform.storage().get("config/application.json").size > 0,
        "stored object should be retrievable"
    );

    auto distribution = platform.loadBalancer().dispatch(150);

    std::size_t totalRequests = 0;

    for (const auto& [id, count] : distribution) {
        totalRequests += count;
    }

    assertCondition(
        totalRequests == 150,
        "load balancer should route all requests"
    );

    platform.loadBalancer().complete(150);

    const Backup& backup = platform.backups().createBackup();

    platform.storage().remove("config/application.json");

    assertCondition(
        platform.storage().objectCount() == 0,
        "object should be removed"
    );

    platform.backups().restore(backup.id);

    assertCondition(
        platform.storage().objectCount() == 1,
        "backup restore should recover the object"
    );

    platform.markUnhealthy("app-01");

    assertCondition(
        platform.healthyCapacity() == 100,
        "one unhealthy instance should reduce capacity"
    );
}

void printEvaluation(const MergeEvaluation& evaluation) {
    std::cout << "\nDeployment eligibility: "
              << (evaluation.eligible ? "ELIGIBLE" : "BLOCKED")
              << "\n";

    if (!evaluation.eligible) {
        for (const auto& failure : evaluation.failures) {
            std::cout << " - " << failure << "\n";
        }
    }
}

int main() {
    try {
        runTests();

        ComputeStoragePlatform platform;

        platform.storage().put(
            "releases/v1/config.json",
            R"({"version":"1.0.0","environment":"production"})"
        );

        platform.storage().put(
            "releases/v1/index.html",
            "<html><body>Scalable application</body></html>"
        );

        std::cout << "Initial healthy capacity: "
                  << platform.healthyCapacity()
                  << "\n";

        auto distribution =
            platform.loadBalancer().dispatch(180);

        std::cout << "\nRequest distribution:\n";

        for (const auto& [instance, count] : distribution) {
            std::cout << " " << instance
                      << " -> " << count << " requests\n";
        }

        platform.loadBalancer().complete(180);

        const Backup& backup =
            platform.backups().createBackup();

        std::cout << "\nCreated backup: "
                  << backup.id << "\n";

        BranchProtectionPolicy policy{
            true,
            true,
            true,
            true,
            2,
            200
        };

        RepositoryGovernanceEngine governance(
            platform.instances(),
            platform.backups(),
            policy
        );

        printEvaluation(governance.evaluateDeployment());

        platform.addInstance("app-03", 100);

        std::cout << "\nCapacity after scale-out: "
                  << platform.healthyCapacity()
                  << "\n";

        printEvaluation(governance.evaluateDeployment());

        platform.markUnhealthy("app-01");

        std::cout << "\nCapacity after app-01 failure: "
                  << platform.healthyCapacity()
                  << "\n";

        printEvaluation(governance.evaluateDeployment());

        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Infrastructure operation failed: "
                  << error.what()
                  << "\n";
        return 1;
    }
}
