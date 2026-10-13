#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

/*
 * Repository-independent compute capacity case study:
 * a production order-processing service must choose a safe deployment
 * under throughput, memory, connection, network, cost, and scaling limits.
 *
 * Compile:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic compute_scaling.cpp -o compute_scaling
 *
 * Run:
 *   ./compute_scaling
 *
 * Capacities and prices are illustrative estimates.
 */

struct InstanceType {
    std::string name;
    int vcpus;
    double memoryGiB;
    int maxConnections;
    double networkGbps;
    double hourlyCost;
};

struct Workload {
    std::string name;
    double requestsPerSecond;
    double cpuCoresPerRequest;
    double memoryGiBPerReplica;
    int connectionsPerReplica;
    double networkGbpsPerReplica;
};

struct CapacityPolicy {
    double cpuTarget = 0.65;
    double memoryTarget = 0.75;
    double connectionTarget = 0.70;
    double networkTarget = 0.70;
    double requestsPerCoreSecond = 1.0;
    double safetyFactor = 1.25;
};

enum class ScalingMode {
    Vertical,
    Horizontal
};

struct Evaluation {
    ScalingMode mode;
    InstanceType instance;
    int replicas;
    double requestedRps;
    double capacityRps;
    double hourlyCost;
    std::vector<std::string> bottlenecks;
    std::vector<std::string> violations;

    bool feasible() const {
        return violations.empty() && requestedRps <= capacityRps;
    }
};

struct ResourceCapacity {
    double requestsPerSecond;
    std::vector<std::string> limitingResources;
};

class CapacityEngine {
public:
    explicit CapacityEngine(CapacityPolicy policy = {})
        : policy_(policy) {
        validatePolicy();
    }

    ResourceCapacity perReplicaCapacity(
        const InstanceType& instance,
        const Workload& workload
    ) const {
        validateInstance(instance);
        validateWorkload(workload);

        // Each independent resource imposes its own throughput ceiling.
        const std::map<std::string, double> ceilings = {
            {
                "cpu",
                instance.vcpus * policy_.requestsPerCoreSecond
                    * policy_.cpuTarget
                    / (workload.cpuCoresPerRequest * policy_.safetyFactor)
            },
            {
                "memory",
                instance.memoryGiB * policy_.memoryTarget
                    / workload.memoryGiBPerReplica
            },
            {
                "connections",
                instance.maxConnections * policy_.connectionTarget
                    / std::max(workload.connectionsPerReplica, 1)
            },
            {
                "network",
                instance.networkGbps * policy_.networkTarget
                    / std::max(workload.networkGbpsPerReplica, 0.001)
            }
        };

        double minimum = std::numeric_limits<double>::infinity();
        for (const auto& entry : ceilings) {
            minimum = std::min(minimum, entry.second);
        }

        std::vector<std::string> bottlenecks;
        for (const auto& entry : ceilings) {
            if (std::abs(entry.second - minimum) <= 1e-9) {
                bottlenecks.push_back(entry.first);
            }
        }

        return {minimum, bottlenecks};
    }

    Evaluation evaluate(
        const InstanceType& instance,
        int replicas,
        const Workload& workload,
        ScalingMode mode
    ) const {
        if (replicas < 1) {
            throw std::invalid_argument("Replicas must be positive.");
        }

        const auto resourceCapacity = perReplicaCapacity(instance, workload);
        const double totalCapacity = resourceCapacity.requestsPerSecond * replicas;

        const double cpuDemand =
            workload.requestsPerSecond * workload.cpuCoresPerRequest;
        const double cpuUtilization = cpuDemand / (instance.vcpus * replicas);
        const double memoryUtilization =
            workload.memoryGiBPerReplica / instance.memoryGiB;
        const double connectionUtilization =
            static_cast<double>(workload.connectionsPerReplica)
            / instance.maxConnections;
        const double networkUtilization =
            workload.networkGbpsPerReplica / instance.networkGbps;

        std::vector<std::string> violations;
        if (cpuUtilization > policy_.cpuTarget) {
            violations.push_back("cpu target exceeded");
        }
        if (memoryUtilization > policy_.memoryTarget) {
            violations.push_back("memory target exceeded");
        }
        if (connectionUtilization > policy_.connectionTarget) {
            violations.push_back("connection target exceeded");
        }
        if (networkUtilization > policy_.networkTarget) {
            violations.push_back("network target exceeded");
        }
        if (workload.requestsPerSecond > totalCapacity) {
            violations.push_back("throughput capacity exceeded");
        }

        return {
            mode,
            instance,
            replicas,
            workload.requestsPerSecond,
            totalCapacity,
            instance.hourlyCost * replicas,
            resourceCapacity.limitingResources,
            violations
        };
    }

    std::optional<Evaluation> planVertical(
        const std::vector<InstanceType>& catalog,
        int fixedReplicas,
        const Workload& workload,
        int maxVcpus,
        double maxMemoryGiB
    ) const {
        std::vector<InstanceType> candidates;
        for (const auto& instance : catalog) {
            if (instance.vcpus <= maxVcpus
                && instance.memoryGiB <= maxMemoryGiB) {
                candidates.push_back(instance);
            }
        }

        // Evaluate cheaper types first; vertical scaling has a hard
        // upper bound because the largest instance may still be insufficient.
        std::sort(
            candidates.begin(),
            candidates.end(),
            [](const auto& a, const auto& b) {
                return a.hourlyCost < b.hourlyCost;
            }
        );

        for (const auto& instance : candidates) {
            auto result = evaluate(
                instance, fixedReplicas, workload, ScalingMode::Vertical
            );
            if (result.feasible()) {
                return result;
            }
        }

        return std::nullopt;
    }

    std::optional<Evaluation> planHorizontal(
        const InstanceType& instance,
        const Workload& workload,
        int minimumReplicas,
        int maximumReplicas
    ) const {
        if (minimumReplicas < 1 || maximumReplicas < minimumReplicas) {
            throw std::invalid_argument("Invalid replica bounds.");
        }

        // Replica count is increased until all modeled resource constraints pass.
        for (int replicas = minimumReplicas;
             replicas <= maximumReplicas;
             ++replicas) {
            auto result = evaluate(
                instance, replicas, workload, ScalingMode::Horizontal
            );
            if (result.feasible()) {
                return result;
            }
        }

        return std::nullopt;
    }

private:
    CapacityPolicy policy_;

    void validatePolicy() const {
        for (double target : {
            policy_.cpuTarget,
            policy_.memoryTarget,
            policy_.connectionTarget,
            policy_.networkTarget
        }) {
            if (target <= 0 || target > 1 || !std::isfinite(target)) {
                throw std::invalid_argument("Utilization targets must be in (0, 1].");
            }
        }
        if (policy_.requestsPerCoreSecond <= 0
            || policy_.safetyFactor < 1) {
            throw std::invalid_argument("Invalid benchmark or safety factor.");
        }
    }

    static void validateInstance(const InstanceType& instance) {
        if (instance.name.empty() || instance.vcpus < 1
            || instance.memoryGiB <= 0 || instance.maxConnections < 1
            || instance.networkGbps <= 0 || instance.hourlyCost < 0) {
            throw std::invalid_argument("Invalid instance specification.");
        }
    }

    static void validateWorkload(const Workload& workload) {
        if (workload.name.empty() || workload.requestsPerSecond < 0
            || workload.cpuCoresPerRequest <= 0
            || workload.memoryGiBPerReplica <= 0
            || workload.connectionsPerReplica < 0
            || workload.networkGbpsPerReplica < 0) {
            throw std::invalid_argument("Invalid workload specification.");
        }
    }
};

class ReplicaAutoscaler {
public:
    ReplicaAutoscaler(
        int initialReplicas,
        int minimumReplicas,
        int maximumReplicas,
        double scaleOutThreshold,
        double scaleInThreshold,
        double cooldownSeconds
    )
        : replicas_(initialReplicas),
          minimum_(minimumReplicas),
          maximum_(maximumReplicas),
          scaleOut_(scaleOutThreshold),
          scaleIn_(scaleInThreshold),
          cooldown_(cooldownSeconds),
          lastActionSeconds_(-std::numeric_limits<double>::infinity()) {
        if (minimum_ < 1 || maximum_ < minimum_
            || initialReplicas < minimum_ || initialReplicas > maximum_) {
            throw std::invalid_argument("Invalid autoscaler replica limits.");
        }
        if (!(0 < scaleIn_ && scaleIn_ < scaleOut_ && scaleOut_ <= 1)
            || cooldown_ < 0) {
            throw std::invalid_argument("Invalid thresholds or cooldown.");
        }
    }

    std::string observe(double utilization, double timestampSeconds) {
        if (!std::isfinite(utilization) || utilization < 0
            || !std::isfinite(timestampSeconds) || timestampSeconds < 0) {
            throw std::invalid_argument("Invalid autoscaler observation.");
        }
        if (timestampSeconds < lastObservationSeconds_) {
            throw std::invalid_argument("Observations must be chronological.");
        }
        lastObservationSeconds_ = timestampSeconds;

        if (timestampSeconds - lastActionSeconds_ < cooldown_) {
            return "cooldown";
        }

        if (utilization > scaleOut_) {
            if (replicas_ >= maximum_) {
                return "maximum-reached";
            }
            ++replicas_;
            lastActionSeconds_ = timestampSeconds;
            return "scale-out";
        }

        if (utilization < scaleIn_) {
            if (replicas_ <= minimum_) {
                return "minimum-reached";
            }
            --replicas_;
            lastActionSeconds_ = timestampSeconds;
            return "scale-in";
        }

        return "stable";
    }

    int replicas() const {
        return replicas_;
    }

private:
    int replicas_;
    int minimum_;
    int maximum_;
    double scaleOut_;
    double scaleIn_;
    double cooldown_;
    double lastActionSeconds_;
    double lastObservationSeconds_ = 0;
};

double percentile(std::vector<double> observations, double quantile) {
    if (observations.empty() || quantile < 0 || quantile > 1) {
        throw std::invalid_argument("Invalid percentile input.");
    }
    for (double value : observations) {
        if (!std::isfinite(value) || value < 0) {
            throw std::invalid_argument("Traffic values must be non-negative.");
        }
    }

    std::sort(observations.begin(), observations.end());
    const double position = (observations.size() - 1) * quantile;
    const auto lower = static_cast<std::size_t>(std::floor(position));
    const auto upper = static_cast<std::size_t>(std::ceil(position));
    const double fraction = position - lower;

    return observations[lower]
        + (observations[upper] - observations[lower]) * fraction;
}

void printEvaluation(
    const std::string& title,
    const std::optional<Evaluation>& evaluation
) {
    std::cout << "\n" << title << "\n";
    if (!evaluation) {
        std::cout << "No feasible deployment within configured limits.\n";
        return;
    }

    const auto& item = *evaluation;
    std::cout << "Instance: " << item.instance.name << "\n"
              << "Replicas: " << item.replicas << "\n"
              << "Requested RPS: " << item.requestedRps << "\n"
              << "Estimated capacity RPS: " << item.capacityRps << "\n"
              << "Hourly cost: $" << item.hourlyCost << "\n"
              << "Monthly compute estimate: $" << item.hourlyCost * 730 << "\n"
              << "Feasible: " << std::boolalpha << item.feasible() << "\n"
              << "Bottlenecks: ";

    for (const auto& resource : item.bottlenecks) {
        std::cout << resource << " ";
    }

    std::cout << "\nViolations: ";
    if (item.violations.empty()) {
        std::cout << "none";
    } else {
        for (const auto& violation : item.violations) {
            std::cout << violation << "; ";
        }
    }
    std::cout << "\n";
}

int main() {
    try {
        std::cout << std::fixed << std::setprecision(2);
        const std::vector<InstanceType> catalog = {
            {"worker-small", 2, 4, 500, 1.0, 0.08},
            {"worker-medium", 4, 8, 1500, 2.0, 0.16},
            {"worker-large", 8, 16, 3000, 5.0, 0.32},
            {"worker-xlarge", 16, 32, 6000, 10.0, 0.64},
            {"worker-2xlarge", 32, 64, 12000, 20.0, 1.28}
        };

        const std::vector<double> hourlyTraffic = {
            120, 145, 138, 160, 175, 210, 245, 300,
            360, 420, 510, 480, 450, 390, 350, 320,
            290, 275, 260, 230, 210, 190, 160, 140
        };

        const double p95 = percentile(hourlyTraffic, 0.95);
        const double growthRate = 0.30;
        const double safetyFactor = 1.20;
        const double planningRps = p95 * (1 + growthRate) * safetyFactor;

        std::cout << "Compute capacity planning case study\n"
                  << "P95 traffic: " << p95 << " RPS\n"
                  << "Forecast planning demand: " << planningRps << " RPS\n";

        const Workload orderApi = {
            "order-processing-api",
            planningRps,
            0.08,
            2.0,
            300,
            0.15
        };

        CapacityEngine engine;
        printEvaluation(
            "Vertical scaling with two fixed replicas",
            engine.planVertical(catalog, 2, orderApi, 64, 128)
        );

        printEvaluation(
            "Horizontal scaling on a medium instance",
            engine.planHorizontal(catalog[1], orderApi, 2, 20)
        );

        std::cout << "\nAutoscaler simulation\n";
        ReplicaAutoscaler autoscaler(3, 2, 8, 0.70, 0.30, 60);

        const std::vector<std::pair<double, double>> samples = {
            {0, 0.82},
            {20, 0.90},
            {65, 0.91},
            {130, 0.15},
            {200, 0.12}
        };

        for (const auto& sample : samples) {
            const auto action = autoscaler.observe(sample.second, sample.first);
            std::cout << "t=" << sample.first
                      << "s utilization=" << sample.second * 100
                      << "% action=" << action
                      << " replicas=" << autoscaler.replicas() << "\n";
        }

        // Assertions protect important boundaries in the planning engine.
        const auto tiny = Workload{
            "tiny-api", 1, 0.01, 0.5, 10, 0.01
        };
        const auto tinyPlan = engine.planVertical(catalog, 1, tiny, 64, 128);
        if (!tinyPlan || !tinyPlan->feasible()) {
            throw std::runtime_error("A tiny workload should fit.");
        }

        const auto impossible = Workload{
            "impossible-api", 1'000'000, 1.0, 1000, 1'000'000, 1000
        };
        if (engine.planVertical(catalog, 1, impossible, 64, 128)) {
            throw std::runtime_error("Impossible vertical plan was accepted.");
        }
        if (engine.planHorizontal(catalog[0], impossible, 2, 3)) {
            throw std::runtime_error("Impossible horizontal plan was accepted.");
        }

        const double monthlyCost = 0.32 * 2 * 730;
        if (std::abs(monthlyCost - 467.20) > 1e-9) {
            throw std::runtime_error("Monthly cost calculation failed.");
        }

        std::cout << "\nAll case-study assertions passed.\n";
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << "\n";
        return 1;
    }

    return 0;
}
