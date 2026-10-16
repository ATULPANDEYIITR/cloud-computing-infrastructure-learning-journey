#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

enum class StorageTier {
    Hot,
    Cool,
    Archive
};

enum class ReplicationPolicy {
    LocalOnly,
    Synchronous,
    Asynchronous
};

enum class CheckState {
    Pending,
    Passing,
    Failing
};

std::string tierName(StorageTier tier) {
    switch (tier) {
        case StorageTier::Hot: return "HOT";
        case StorageTier::Cool: return "COOL";
        case StorageTier::Archive: return "ARCHIVE";
    }
    throw std::logic_error("Unknown storage tier");
}

struct TierPolicy {
    double monthlyPricePerGB;
    double retrievalPricePerGB;
    int minimumRetentionDays;
    int retrievalDelayHours;
};

TierPolicy tierPolicy(StorageTier tier) {
    switch (tier) {
        case StorageTier::Hot: return {0.023, 0.0, 0, 0};
        case StorageTier::Cool: return {0.0125, 0.01, 30, 0};
        case StorageTier::Archive: return {0.004, 0.03, 90, 12};
    }
    throw std::logic_error("Unknown storage tier");
}

struct StoredObject {
    std::string key;
    std::size_t bytes;
    std::string checksum;
    int version;
    int createdDay;
    StorageTier tier;
};

struct Region {
    std::string name;
    bool available = true;
    std::map<std::string, StoredObject> objects;
};

struct ReplicationTask {
    std::string targetRegion;
    StoredObject object;
    bool completed = false;
};

class GovernanceStorageEngine {
private:
    std::map<std::string, Region> regions_;
    std::string primary_;
    ReplicationPolicy policy_;
    std::vector<ReplicationTask> replicationQueue_;
    std::map<std::string, int> latestVersions_;

public:
    GovernanceStorageEngine(
        const std::vector<std::string>& regionNames,
        ReplicationPolicy policy
    ) : policy_(policy) {
        if (regionNames.empty()) {
            throw std::invalid_argument("At least one region is required");
        }

        std::set<std::string> uniqueNames;
        for (const auto& name : regionNames) {
            if (name.empty() || !uniqueNames.insert(name).second) {
                throw std::invalid_argument("Region names must be non-empty and unique");
            }
            regions_.emplace(name, Region{name});
        }
        primary_ = regionNames.front();
    }

    const std::string& primaryRegion() const {
        return primary_;
    }

    void setAvailability(const std::string& name, bool available) {
        auto found = regions_.find(name);
        if (found == regions_.end()) {
            throw std::invalid_argument("Unknown region: " + name);
        }
        found->second.available = available;
    }

    void put(
        const std::string& key,
        std::size_t bytes,
        const std::string& checksum,
        int day,
        StorageTier tier
    ) {
        if (key.empty() || checksum.empty()) {
            throw std::invalid_argument("Object key and checksum are required");
        }
        if (bytes == 0 || day < 0) {
            throw std::invalid_argument("Object size must be positive and day non-negative");
        }

        Region& primary = regions_.at(primary_);
        if (!primary.available) {
            throw std::runtime_error("Primary region is unavailable");
        }

        std::vector<std::string> destinations;
        for (const auto& [name, region] : regions_) {
            if (name != primary_) {
                destinations.push_back(name);
                if (policy_ == ReplicationPolicy::Synchronous && !region.available) {
                    throw std::runtime_error(
                        "Synchronous write rejected: a destination is unavailable"
                    );
                }
            }
        }

        int version = latestVersions_[key] + 1;
        StoredObject object{key, bytes, checksum, version, day, tier};

        // Validate all synchronous destinations before committing any copy.
        // This avoids a partially acknowledged write in the simulation.
        primary.objects[key] = object;
        latestVersions_[key] = version;

        if (policy_ == ReplicationPolicy::Synchronous) {
            for (const auto& name : destinations) {
                regions_.at(name).objects[key] = object;
            }
        } else if (policy_ == ReplicationPolicy::Asynchronous) {
            for (const auto& name : destinations) {
                replicationQueue_.push_back({name, object, false});
            }
        }

        std::cout << "Stored " << key
                  << " version=" << version
                  << " tier=" << tierName(tier) << '\n';
    }

    std::size_t deliverReplication() {
        std::size_t delivered = 0;

        for (auto& task : replicationQueue_) {
            if (task.completed) continue;

            Region& target = regions_.at(task.targetRegion);
            if (!target.available) continue;

            auto existing = target.objects.find(task.object.key);
            if (existing == target.objects.end() ||
                existing->second.version < task.object.version) {
                target.objects[task.object.key] = task.object;
            }

            task.completed = true;
            ++delivered;
        }
        return delivered;
    }

    std::optional<StoredObject> read(
        const std::string& key,
        const std::optional<std::string>& preferredRegion = std::nullopt
    ) const {
        if (preferredRegion) {
            auto region = regions_.find(*preferredRegion);
            if (region == regions_.end()) {
                throw std::invalid_argument("Unknown preferred region");
            }
            if (!region->second.available) return std::nullopt;

            auto object = region->second.objects.find(key);
            if (object == region->second.objects.end()) return std::nullopt;
            return object->second;
        }

        // Prefer the current primary, then fall back to other available copies.
        const auto primary = regions_.find(primary_);
        if (primary != regions_.end() && primary->second.available) {
            auto object = primary->second.objects.find(key);
            if (object != primary->second.objects.end()) return object->second;
        }

        for (const auto& [name, region] : regions_) {
            if (!region.available) continue;
            auto object = region.objects.find(key);
            if (object != region.objects.end()) return object->second;
        }
        return std::nullopt;
    }

    void promoteRegion(const std::string& name) {
        auto region = regions_.find(name);
        if (region == regions_.end()) {
            throw std::invalid_argument("Unknown failover region");
        }
        if (!region->second.available) {
            throw std::runtime_error("Cannot promote an unavailable region");
        }
        if (region->second.objects.empty()) {
            throw std::runtime_error("Cannot promote a region without stored objects");
        }
        primary_ = name;
    }

    std::size_t accessibleCopyCount(const std::string& key) const {
        std::size_t count = 0;
        for (const auto& [name, region] : regions_) {
            if (region.available && region.objects.count(key) != 0) ++count;
        }
        return count;
    }

    void showReplicationQueue() const {
        for (const auto& task : replicationQueue_) {
            std::cout << "Replication target=" << task.targetRegion
                      << " key=" << task.object.key
                      << " version=" << task.object.version
                      << " state=" << (task.completed ? "COMPLETE" : "PENDING")
                      << '\n';
        }
    }
};

struct LifecycleDecision {
    bool allowed;
    std::string explanation;
    double estimatedMonthlyStorageCost;
};

LifecycleDecision evaluateTierTransition(
    const StoredObject& object,
    int currentDay,
    StorageTier targetTier,
    double retrievedGB
) {
    if (currentDay < object.createdDay || retrievedGB < 0) {
        throw std::invalid_argument("Invalid age or retrieval quantity");
    }

    const TierPolicy current = tierPolicy(object.tier);
    const TierPolicy target = tierPolicy(targetTier);
    const int age = currentDay - object.createdDay;

    if (age < current.minimumRetentionDays) {
        return {
            false,
            "Minimum retention period has not elapsed",
            0.0
        };
    }

    const double sizeGB = static_cast<double>(object.bytes) / 1'000'000'000.0;
    const double cost =
        sizeGB * target.monthlyPricePerGB +
        retrievedGB * target.retrievalPricePerGB;

    return {
        true,
        "Transition satisfies the configured retention rule",
        cost
    };
}

double redundantAvailability(double singlePathAvailability, int paths) {
    if (singlePathAvailability < 0 || singlePathAvailability > 1 || paths < 1) {
        throw std::invalid_argument("Invalid availability or path count");
    }
    return 1.0 - std::pow(1.0 - singlePathAvailability, paths);
}

int copiesForDurabilityTarget(double lossProbability, double targetProbability) {
    if (lossProbability <= 0 || lossProbability >= 1 ||
        targetProbability <= 0 || targetProbability >= 1) {
        throw std::invalid_argument("Probabilities must be between zero and one");
    }
    if (lossProbability <= targetProbability) return 1;

    return static_cast<int>(
        std::ceil(std::log(targetProbability) / std::log(lossProbability))
    );
}

int main() {
    try {
        std::cout << std::fixed << std::setprecision(6);
        std::cout << "Cloud storage regional resilience case study\n\n";

        GovernanceStorageEngine engine(
            {"ap-south-1", "ap-southeast-1", "eu-west-1"},
            ReplicationPolicy::Asynchronous
        );

        engine.put(
            "telemetry/plant-07/reading.bin",
            2'500'000,
            "sha256:2a3e91",
            0,
            StorageTier::Hot
        );

        std::cout << "Copies before replication: "
                  << engine.accessibleCopyCount(
                      "telemetry/plant-07/reading.bin"
                  ) << '\n';

        engine.setAvailability("eu-west-1", false);
        std::cout << "Delivered replicas: "
                  << engine.deliverReplication() << '\n';
        engine.showReplicationQueue();

        engine.setAvailability("eu-west-1", true);
        std::cout << "Delivered after recovery: "
                  << engine.deliverReplication() << '\n';

        engine.setAvailability("ap-south-1", false);
        auto recovered = engine.read(
            "telemetry/plant-07/reading.bin",
            std::string("ap-southeast-1")
        );

        if (recovered) {
            std::cout << "Failover read succeeded at version "
                      << recovered->version << '\n';
            engine.promoteRegion("ap-southeast-1");
            std::cout << "New primary: " << engine.primaryRegion() << '\n';
        } else {
            std::cout << "Failover read failed: no available replica\n";
        }

        std::cout << "\nStorage tier analysis\n";
        for (StorageTier tier :
             {StorageTier::Hot, StorageTier::Cool, StorageTier::Archive}) {
            const TierPolicy policy = tierPolicy(tier);
            std::cout << tierName(tier)
                      << " monthly_rate=$" << policy.monthlyPricePerGB
                      << "/GB"
                      << " retrieval_rate=$" << policy.retrievalPricePerGB
                      << "/GB"
                      << " minimum_days=" << policy.minimumRetentionDays
                      << " retrieval_delay_hours=" << policy.retrievalDelayHours
                      << '\n';
        }

        std::cout << "\nIllustrative reliability calculations\n";
        for (int paths : {1, 2, 3}) {
            std::cout << paths << " independent paths: "
                      << redundantAvailability(0.999, paths) * 100.0
                      << "% availability\n";
        }

        std::cout << "Copies needed under an independent-loss model: "
                  << copiesForDurabilityTarget(1e-4, 1e-12) << '\n';

        auto stored = engine.read(
            "telemetry/plant-07/reading.bin",
            std::string("ap-southeast-1")
        );

        if (stored) {
            const LifecycleDecision decision = evaluateTierTransition(
                *stored, 10, StorageTier::Archive, 0.0
            );
            std::cout << "Archive transition allowed: "
                      << std::boolalpha << decision.allowed
                      << " (" << decision.explanation << ")\n";
        }

        // Redundancy improves resilience only when failures are sufficiently
        // independent. Shared credentials, account deletion, regional control
        // planes, and propagated corruption can defeat every live replica.
        std::cout << "\nOperational distinction: replicas improve continuity; "
                     "versioned backups enable recovery from logical damage.\n";
    } catch (const std::exception& error) {
        std::cerr << "Storage simulation error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
