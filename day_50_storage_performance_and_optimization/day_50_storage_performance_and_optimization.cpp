#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <optional>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

enum class AccessType {
    Read,
    Write
};

struct StorageTier {
    std::string name;
    double maxIops;
    double maxThroughputMbps;
    double latencyMs;
    double costPerGbMonth;
};

struct IoRequest {
    std::size_t id;
    AccessType type;
    std::size_t sizeKb;
    std::string key;
};

struct Metrics {
    std::size_t requests = 0;
    std::size_t reads = 0;
    std::size_t writes = 0;
    std::size_t cacheHits = 0;
    std::size_t cacheMisses = 0;
    double totalLatencyMs = 0.0;
    std::size_t totalBytes = 0;
};

class LruCache {
private:
    struct Entry {
        std::string key;
        bool value;
    };

    std::size_t capacity_;
    std::list<Entry> entries_;
    std::unordered_map<std::string, std::list<Entry>::iterator> index_;

public:
    explicit LruCache(std::size_t capacity) : capacity_(capacity) {
        if (capacity == 0) {
            throw std::invalid_argument("Cache capacity must be positive");
        }
    }

    bool contains(const std::string& key) {
        auto it = index_.find(key);
        if (it == index_.end()) {
            return false;
        }

        entries_.splice(entries_.begin(), entries_, it->second);
        return true;
    }

    void put(const std::string& key) {
        auto existing = index_.find(key);

        if (existing != index_.end()) {
            entries_.splice(entries_.begin(), entries_, existing->second);
            return;
        }

        entries_.push_front({key, true});
        index_[key] = entries_.begin();

        if (entries_.size() > capacity_) {
            auto last = std::prev(entries_.end());
            index_.erase(last->key);
            entries_.pop_back();
        }
    }
};

class GovernanceEngine {
private:
    std::vector<StorageTier> tiers_;

public:
    GovernanceEngine()
        : tiers_{
              {"HDD", 180, 220, 8.0, 0.02},
              {"SATA SSD", 75000, 550, 0.10, 0.08},
              {"NVMe SSD", 800000, 7000, 0.025, 0.15}} {}

    const StorageTier& selectTier(
        double requiredIops,
        double requiredThroughput,
        double capacityGb,
        std::optional<double> maxMonthlyCost = std::nullopt) const {

        if (requiredIops < 0 ||
            requiredThroughput < 0 ||
            capacityGb <= 0) {
            throw std::invalid_argument("Invalid capacity planning requirements");
        }

        const StorageTier* best = nullptr;

        for (const auto& tier : tiers_) {
            const double monthlyCost =
                tier.costPerGbMonth * capacityGb;

            const bool meetsPerformance =
                tier.maxIops >= requiredIops &&
                tier.maxThroughputMbps >= requiredThroughput;

            const bool meetsCost =
                !maxMonthlyCost.has_value() ||
                monthlyCost <= *maxMonthlyCost;

            if (meetsPerformance && meetsCost &&
                (best == nullptr ||
                 tier.costPerGbMonth < best->costPerGbMonth)) {
                best = &tier;
            }
        }

        if (best == nullptr) {
            throw std::runtime_error(
                "No storage tier satisfies the requested constraints");
        }

        return *best;
    }

    double sustainableIops(
        const StorageTier& tier,
        std::size_t requestSizeKb) const {

        if (requestSizeKb == 0) {
            throw std::invalid_argument("Request size must be positive");
        }

        const double throughputLimitedIops =
            tier.maxThroughputMbps * 1024.0 /
            static_cast<double>(requestSizeKb);

        return std::min(tier.maxIops, throughputLimitedIops);
    }
};

class StorageSystem {
private:
    const StorageTier& tier_;
    LruCache cache_;
    Metrics metrics_;

    double storageLatency(std::size_t sizeKb) const {
        const double transferMs =
            (static_cast<double>(sizeKb) / 1024.0) /
            tier_.maxThroughputMbps * 1000.0;

        return tier_.latencyMs + transferMs;
    }

public:
    StorageSystem(const StorageTier& tier, std::size_t cacheCapacity)
        : tier_(tier), cache_(cacheCapacity) {}

    void process(const IoRequest& request) {
        if (request.sizeKb == 0) {
            throw std::invalid_argument("I/O size cannot be zero");
        }

        if (request.sizeKb > 1024 * 1024) {
            throw std::invalid_argument("I/O request exceeds configured limit");
        }

        if (request.key.empty() || request.key.size() > 256) {
            throw std::invalid_argument("Invalid storage key");
        }

        metrics_.requests++;
        metrics_.totalBytes += request.sizeKb * 1024;

        if (request.type == AccessType::Read) {
            metrics_.reads++;

            if (cache_.contains(request.key)) {
                metrics_.cacheHits++;

                // Cache latency is modeled as a fraction of device latency.
                metrics_.totalLatencyMs +=
                    std::max(0.05, tier_.latencyMs * 0.10);
            } else {
                metrics_.cacheMisses++;
                metrics_.totalLatencyMs += storageLatency(request.sizeKb);
                cache_.put(request.key);
            }
        } else {
            metrics_.writes++;
            metrics_.totalLatencyMs += storageLatency(request.sizeKb);

            // Write-through avoids serving stale cached data.
            cache_.put(request.key);
        }
    }

    const Metrics& metrics() const {
        return metrics_;
    }
};

int main() {
    try {
        GovernanceEngine planner;

        const double requiredIops = 120000;
        const double requiredThroughput = 1500;
        const double capacityGb = 2000;

        const auto& tier = planner.selectTier(
            requiredIops,
            requiredThroughput,
            capacityGb);

        std::cout << "Storage capacity decision\n";
        std::cout << "Required IOPS: " << requiredIops << '\n';
        std::cout << "Required throughput: "
                  << requiredThroughput << " MB/s\n";
        std::cout << "Capacity: " << capacityGb << " GB\n";
        std::cout << "Selected tier: " << tier.name << '\n';
        std::cout << "Estimated monthly cost: $"
                  << std::fixed << std::setprecision(2)
                  << tier.costPerGbMonth * capacityGb << "\n\n";

        StorageSystem storage(tier, 32);

        std::mt19937 generator(42);
        std::uniform_real_distribution<double> probability(0.0, 1.0);
        std::uniform_int_distribution<int> sizeSelector(0, 5);
        const std::vector<std::size_t> sizes{
            4, 8, 16, 32, 64, 128
        };

        for (std::size_t i = 0; i < 2000; ++i) {
            const bool hot = probability(generator) < 0.75;
            const bool read = probability(generator) < 0.80;

            std::string key;

            if (hot) {
                key = "customer:" +
                      std::to_string(i % 12);
            } else {
                key = "archive:" +
                      std::to_string(i % 200);
            }

            IoRequest request{
                i,
                read ? AccessType::Read : AccessType::Write,
                sizes[sizeSelector(generator)],
                key
            };

            storage.process(request);
        }

        const Metrics& metrics = storage.metrics();

        const double averageLatency =
            metrics.requests == 0
                ? 0.0
                : metrics.totalLatencyMs /
                  static_cast<double>(metrics.requests);

        const double hitRatio =
            metrics.cacheHits + metrics.cacheMisses == 0
                ? 0.0
                : static_cast<double>(metrics.cacheHits) /
                  static_cast<double>(
                      metrics.cacheHits + metrics.cacheMisses);

        const double modeledThroughput =
            metrics.totalLatencyMs <= 0
                ? 0.0
                : static_cast<double>(metrics.totalBytes) /
                  1024.0 / 1024.0 /
                  (metrics.totalLatencyMs / 1000.0);

        std::cout << "Workload results\n";
        std::cout << "Requests: " << metrics.requests << '\n';
        std::cout << "Reads: " << metrics.reads << '\n';
        std::cout << "Writes: " << metrics.writes << '\n';
        std::cout << "Cache hit ratio: "
                  << hitRatio * 100.0 << "%\n";
        std::cout << "Average latency: "
                  << averageLatency << " ms\n";
        std::cout << "Modeled throughput: "
                  << modeledThroughput << " MB/s\n\n";

        for (std::size_t requestSize : {4u, 64u, 256u}) {
            std::cout << "Sustainable IOPS at "
                      << requestSize << " KB: "
                      << planner.sustainableIops(
                             tier, requestSize)
                      << '\n';
        }

        std::cout << "\nDesign interpretation\n";

        if (hitRatio >= 0.70) {
            std::cout
                << "The workload has strong locality; caching can "
                   "substantially reduce backend reads.\n";
        } else {
            std::cout
                << "The workload has weak locality; more cache may "
                   "produce limited improvement.\n";
        }

        std::cout
            << "Small random I/O is generally IOPS and latency sensitive, "
               "while large sequential I/O is more throughput sensitive.\n";

        std::cout
            << "Real production decisions require device benchmarks, "
               "queue-depth measurements, workload traces, and cost data.\n";
    }
    catch (const std::exception& error) {
        std::cerr << "Storage evaluation failed: "
                  << error.what() << '\n';
        return 1;
    }

    return 0;
}
