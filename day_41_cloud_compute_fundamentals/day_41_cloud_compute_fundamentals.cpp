#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

enum class Architecture { X86_64, ARM64 };
enum class WorkloadClass { General, Web, Compute, Memory };
enum class InstanceState { Stopped, Running, Terminated };

std::string toString(Architecture architecture) {
    return architecture == Architecture::X86_64 ? "x86_64" : "arm64";
}

std::string toString(WorkloadClass workloadClass) {
    switch (workloadClass) {
        case WorkloadClass::General: return "general";
        case WorkloadClass::Web: return "web";
        case WorkloadClass::Compute: return "compute";
        case WorkloadClass::Memory: return "memory";
    }
    throw std::logic_error("Unknown workload class.");
}

std::string toString(InstanceState state) {
    switch (state) {
        case InstanceState::Stopped: return "stopped";
        case InstanceState::Running: return "running";
        case InstanceState::Terminated: return "terminated";
    }
    throw std::logic_error("Unknown instance state.");
}

struct MachineImage {
    std::string id;
    std::string name;
    Architecture architecture;
    int rootDiskGiB;
    bool trusted;
    bool encrypted;

    void validate() const {
        if (id.empty() || name.empty()) {
            throw std::invalid_argument("Image ID and name are required.");
        }
        if (rootDiskGiB < 8) {
            throw std::invalid_argument("Image root disk must be at least 8 GiB.");
        }
        if (!trusted || !encrypted) {
            throw std::invalid_argument(
                "Image must pass trust and encryption requirements."
            );
        }
    }
};

struct InstanceType {
    std::string name;
    std::string family;
    int vcpus;
    double memoryGiB;
    Architecture architecture;
    double networkGbps;
    double hourlyRate;
    std::vector<WorkloadClass> supportedWorkloads;
    bool burstable;

    void validate() const {
        if (name.empty() || family.empty() || vcpus <= 0 ||
            memoryGiB <= 0 || networkGbps <= 0 || hourlyRate < 0) {
            throw std::invalid_argument("Invalid instance type definition.");
        }
    }

    bool supports(WorkloadClass workloadClass) const {
        return std::find(
            supportedWorkloads.begin(),
            supportedWorkloads.end(),
            workloadClass
        ) != supportedWorkloads.end();
    }
};

struct Workload {
    std::string name;
    WorkloadClass workloadClass;
    int requiredVcpus;
    double requiredMemoryGiB;
    double minimumNetworkGbps;
    Architecture architecture;
    bool allowBurstable;

    void validate() const {
        if (name.empty() || requiredVcpus < 1 ||
            requiredMemoryGiB <= 0 || minimumNetworkGbps < 0) {
            throw std::invalid_argument("Invalid workload requirements.");
        }
    }
};

class GovernanceEngine {
private:
    std::vector<InstanceType> catalog_;

public:
    explicit GovernanceEngine(std::vector<InstanceType> catalog)
        : catalog_(std::move(catalog)) {
        for (const auto& type : catalog_) {
            type.validate();
        }
    }

    std::vector<InstanceType> recommend(const Workload& workload) const {
        workload.validate();
        std::vector<InstanceType> matches;

        for (const auto& type : catalog_) {
            if (type.architecture != workload.architecture) continue;
            if (!type.supports(workload.workloadClass)) continue;
            if (type.vcpus < workload.requiredVcpus) continue;
            if (type.memoryGiB < workload.requiredMemoryGiB) continue;
            if (type.networkGbps < workload.minimumNetworkGbps) continue;
            if (type.burstable && !workload.allowBurstable) continue;
            matches.push_back(type);
        }

        // Stable, deterministic ordering makes the planner's output reproducible.
        std::sort(matches.begin(), matches.end(),
            [](const InstanceType& left, const InstanceType& right) {
                if (left.hourlyRate != right.hourlyRate) {
                    return left.hourlyRate < right.hourlyRate;
                }
                if (left.memoryGiB != right.memoryGiB) {
                    return left.memoryGiB < right.memoryGiB;
                }
                return left.vcpus < right.vcpus;
            });

        return matches;
    }

    int workloadPlacements(
        const InstanceType& type,
        int workloadVcpus,
        double workloadMemoryGiB,
        double cpuReserveFraction = 0.10,
        double memoryReserveGiB = 0.5
    ) const {
        if (workloadVcpus < 1 || workloadMemoryGiB <= 0 ||
            cpuReserveFraction < 0 || cpuReserveFraction >= 1 ||
            memoryReserveGiB < 0) {
            throw std::invalid_argument("Invalid capacity-planning inputs.");
        }

        const double usableCpu = type.vcpus * (1.0 - cpuReserveFraction);
        const double usableMemory = type.memoryGiB - memoryReserveGiB;

        if (usableCpu < workloadVcpus || usableMemory < workloadMemoryGiB) {
            return 0;
        }

        const int cpuPlacements =
            static_cast<int>(std::floor(usableCpu / workloadVcpus));
        const int memoryPlacements =
            static_cast<int>(std::floor(usableMemory / workloadMemoryGiB));

        return std::min(cpuPlacements, memoryPlacements);
    }
};

class ComputeInstance {
private:
    std::string id_;
    const InstanceType& type_;
    const MachineImage& image_;
    InstanceState state_ = InstanceState::Stopped;

public:
    ComputeInstance(
        std::string id,
        const InstanceType& type,
        const MachineImage& image
    ) : id_(std::move(id)), type_(type), image_(image) {
        if (id_.empty()) {
            throw std::invalid_argument("Instance ID is required.");
        }
    }

    void start() {
        if (state_ == InstanceState::Terminated) {
            throw std::logic_error("Terminated instances cannot start.");
        }
        if (state_ == InstanceState::Running) {
            return;
        }

        image_.validate();
        if (type_.architecture != image_.architecture) {
            throw std::invalid_argument(
                "Machine image architecture does not match instance type."
            );
        }
        state_ = InstanceState::Running;
    }

    void stop() {
        if (state_ != InstanceState::Running) {
            throw std::logic_error("Only running instances can stop.");
        }
        state_ = InstanceState::Stopped;
    }

    void terminate() {
        if (state_ == InstanceState::Terminated) {
            throw std::logic_error("Instance is already terminated.");
        }
        state_ = InstanceState::Terminated;
    }

    InstanceState state() const {
        return state_;
    }

    const std::string& id() const {
        return id_;
    }
};

double monthlyComputeCost(
    double hourlyRate,
    double hoursPerDay = 24,
    int days = 30
) {
    if (hourlyRate < 0 || hoursPerDay < 0 || hoursPerDay > 24 || days < 1) {
        throw std::invalid_argument("Invalid billing parameters.");
    }
    return hourlyRate * hoursPerDay * days;
}

int main() {
    try {
        std::vector<InstanceType> catalog = {
            {"general.small", "general", 2, 4, Architecture::X86_64,
             1, 0.025, {WorkloadClass::General, WorkloadClass::Web}, false},
            {"compute.large", "compute", 8, 16, Architecture::X86_64,
             10, 0.120, {WorkloadClass::Compute, WorkloadClass::General}, false},
            {"memory.large", "memory", 4, 32, Architecture::X86_64,
             10, 0.150, {WorkloadClass::Memory, WorkloadClass::General}, false},
            {"arm.compute", "compute", 8, 16, Architecture::ARM64,
             10, 0.095, {WorkloadClass::Compute, WorkloadClass::General}, false},
            {"general.burst", "general", 2, 4, Architecture::X86_64,
             1, 0.012, {WorkloadClass::General, WorkloadClass::Web}, true}
        };

        GovernanceEngine planner(catalog);

        std::vector<Workload> workloads = {
            {"render-farm", WorkloadClass::Compute, 6, 8, 5,
             Architecture::X86_64, false},
            {"analytics-cache", WorkloadClass::Memory, 4, 24, 5,
             Architecture::X86_64, false},
            {"arm-build-workers", WorkloadClass::Compute, 4, 8, 2,
             Architecture::ARM64, false}
        };

        std::cout << "Cloud compute fleet planning case study\n";
        std::cout << "=======================================\n";

        for (const auto& workload : workloads) {
            const auto recommendations = planner.recommend(workload);
            std::cout << "\nWorkload: " << workload.name << '\n';

            if (recommendations.empty()) {
                std::cout << "No compatible instance type found.\n";
                continue;
            }

            for (const auto& type : recommendations) {
                std::cout << "  " << type.name
                          << " | " << type.vcpus << " vCPU"
                          << " | " << type.memoryGiB << " GiB"
                          << " | " << toString(type.architecture)
                          << " | $" << std::fixed << std::setprecision(3)
                          << type.hourlyRate << "/hour\n";
            }
        }

        const auto& computeType = catalog.at(1);
        std::cout << "\nCapacity on " << computeType.name << ": "
                  << planner.workloadPlacements(computeType, 2, 3)
                  << " workloads of 2 vCPU and 3 GiB each.\n";

        std::cout << "Continuous monthly cost: $"
                  << std::fixed << std::setprecision(2)
                  << monthlyComputeCost(computeType.hourlyRate) << '\n';

        MachineImage trustedImage{
            "img-linux-stable", "Hardened Linux", Architecture::X86_64,
            30, true, true
        };

        ComputeInstance instance("i-fleet-001", computeType, trustedImage);
        std::cout << "\nInitial state: " << toString(instance.state()) << '\n';
        instance.start();
        std::cout << "After start: " << toString(instance.state()) << '\n';
        instance.stop();
        std::cout << "After stop: " << toString(instance.state()) << '\n';
        instance.start();
        instance.terminate();
        std::cout << "After termination: "
                  << toString(instance.state()) << '\n';

        try {
            instance.start();
        } catch (const std::logic_error& error) {
            std::cout << "Lifecycle protection: " << error.what() << '\n';
        }

        MachineImage armImage{
            "img-arm", "ARM Linux", Architecture::ARM64, 20, true, true
        };
        try {
            ComputeInstance incompatible("i-invalid", computeType, armImage);
            incompatible.start();
        } catch (const std::invalid_argument& error) {
            std::cout << "Architecture validation: " << error.what() << '\n';
        }

        try {
            monthlyComputeCost(0.12, 25, 30);
        } catch (const std::invalid_argument& error) {
            std::cout << "Billing validation: " << error.what() << '\n';
        }

        std::cout << "\nEngineering considerations:\n"
                  << "- CPU and memory are independent placement constraints.\n"
                  << "- Architecture compatibility is a launch-time requirement.\n"
                  << "- Reserved headroom reduces theoretical packing capacity.\n"
                  << "- Burst performance and network limits need separate validation.\n"
                  << "- Prices are illustrative and exclude disks, egress, and taxes.\n";
    } catch (const std::exception& error) {
        std::cerr << "Planning failure: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
