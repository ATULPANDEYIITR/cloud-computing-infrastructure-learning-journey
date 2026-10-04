#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <numeric>
#include <optional>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

/*
 * Server Virtualization Governance and Merge-Eligibility-Style Resource Engine
 *
 * Technical case study:
 * A private cloud operator manages a cluster of physical virtualization
 * hosts. Workloads arrive as virtual machines with CPU, memory, storage,
 * network, reservation, and scheduling requirements.
 *
 * The program models:
 * - host resource capacity
 * - VM placement and admission
 * - resource sharing
 * - CPU weighted scheduling
 * - memory reclamation
 * - overcommitment
 * - isolation boundaries
 * - host health
 * - migration admission
 * - failure handling
 *
 * C++17 or later.
 *
 * No external libraries are required.
 */

enum class VMState {
    Stopped,
    Running,
    Paused,
    Failed
};

std::string stateName(VMState state) {
    switch (state) {
        case VMState::Stopped:
            return "stopped";
        case VMState::Running:
            return "running";
        case VMState::Paused:
            return "paused";
        case VMState::Failed:
            return "failed";
    }

    return "unknown";
}

struct ResourceCapacity {
    int cpuCores{};
    double memoryGB{};
    double storageGB{};
    double networkGbps{};

    void validate() const {
        if (cpuCores <= 0) {
            throw std::invalid_argument(
                "Physical CPU capacity must be positive."
            );
        }

        if (memoryGB <= 0 || storageGB <= 0 || networkGbps <= 0) {
            throw std::invalid_argument(
                "Physical memory, storage, and network capacity must be positive."
            );
        }
    }
};

struct VM {
    std::string id;
    int vcpus{};
    double memoryGB{};
    double storageGB{};
    double networkGbps{};

    int cpuShares{100};
    int cpuReservation{0};
    double memoryReservationGB{0.0};

    std::optional<int> cpuLimit;
    std::optional<double> memoryLimitGB;

    std::string isolationDomain{"default"};
    VMState state{VMState::Stopped};

    double cpuDemand{0.0};
    double memoryDemandGB{0.0};
    double balloonedMemoryGB{0.0};

    VM(
        std::string vmId,
        int cpu,
        double memory,
        double storage,
        double network,
        int shares = 100,
        int cpuReserve = 0,
        double memoryReserve = 0.0,
        std::optional<int> cpuMax = std::nullopt,
        std::optional<double> memoryMax = std::nullopt,
        std::string isolation = "default"
    )
        : id(std::move(vmId)),
          vcpus(cpu),
          memoryGB(memory),
          storageGB(storage),
          networkGbps(network),
          cpuShares(shares),
          cpuReservation(cpuReserve),
          memoryReservationGB(memoryReserve),
          cpuLimit(cpuMax),
          memoryLimitGB(memoryMax),
          isolationDomain(std::move(isolation)) {
        validate();
    }

    void validate() const {
        if (id.empty()) {
            throw std::invalid_argument("VM identifier cannot be empty.");
        }

        if (vcpus <= 0) {
            throw std::invalid_argument(
                id + ": vCPU count must be positive."
            );
        }

        if (memoryGB <= 0 || storageGB <= 0) {
            throw std::invalid_argument(
                id + ": memory and storage must be positive."
            );
        }

        if (networkGbps < 0) {
            throw std::invalid_argument(
                id + ": network allocation cannot be negative."
            );
        }

        if (cpuShares <= 0) {
            throw std::invalid_argument(
                id + ": CPU shares must be positive."
            );
        }

        if (cpuReservation < 0 || cpuReservation > vcpus) {
            throw std::invalid_argument(
                id + ": CPU reservation exceeds VM capacity."
            );
        }

        if (
            memoryReservationGB < 0 ||
            memoryReservationGB > memoryGB
        ) {
            throw std::invalid_argument(
                id + ": memory reservation exceeds VM memory."
            );
        }

        if (
            cpuLimit.has_value() &&
            *cpuLimit < cpuReservation
        ) {
            throw std::invalid_argument(
                id + ": CPU limit is below CPU reservation."
            );
        }

        if (
            memoryLimitGB.has_value() &&
            *memoryLimitGB < memoryReservationGB
        ) {
            throw std::invalid_argument(
                id + ": memory limit is below memory reservation."
            );
        }
    }

    int effectiveCpuLimit() const {
        return cpuLimit.value_or(vcpus);
    }

    double effectiveMemoryLimit() const {
        return memoryLimitGB.value_or(memoryGB);
    }

    void start() {
        if (state == VMState::Failed) {
            throw std::runtime_error(
                id + ": failed VM cannot be started directly."
            );
        }

        if (state == VMState::Running) {
            return;
        }

        state = VMState::Running;
    }

    void stop() {
        state = VMState::Stopped;
        cpuDemand = 0;
        memoryDemandGB = 0;
        balloonedMemoryGB = 0;
    }

    void pause() {
        if (state != VMState::Running) {
            throw std::runtime_error(
                id + ": only a running VM can be paused."
            );
        }

        state = VMState::Paused;
    }

    void setDemand(double cpu, double memory) {
        if (cpu < 0 || memory < 0) {
            throw std::invalid_argument(
                id + ": resource demand cannot be negative."
            );
        }

        cpuDemand = std::min(
            cpu,
            static_cast<double>(effectiveCpuLimit())
        );

        memoryDemandGB = std::min(
            memory,
            effectiveMemoryLimit()
        );
    }
};

struct Allocation {
    std::string vmId;
    double cpuAllocated{};
    double memoryAllocatedGB{};
    double memoryReclaimedGB{};
    bool cpuThrottled{};
};

class IsolationController {
private:
    std::unordered_map<std::string, std::vector<std::string>>
        members;

public:
    void registerVM(const VM& vm) {
        members[vm.isolationDomain].push_back(vm.id);
    }

    bool canDirectlyAccess(
        const VM& source,
        const VM& target
    ) const {
        /*
         * Membership in the same isolation domain does not grant arbitrary
         * guest memory access. Direct access is allowed only to itself in
         * this model. Real virtualization boundaries are enforced by the
         * hypervisor, hardware page translation, I/O mediation, and device
         * isolation.
         */
        return source.id == target.id;
    }

    void printDomain(const std::string& domain) const {
        auto it = members.find(domain);

        if (it == members.end()) {
            std::cout << "Isolation domain " << domain
                      << " does not exist.\n";
            return;
        }

        std::cout << "Isolation domain " << domain << ": ";

        for (const auto& id : it->second) {
            std::cout << id << " ";
        }

        std::cout << "\n";
    }
};

class VirtualizationHost {
private:
    std::string name;
    ResourceCapacity capacity;

    std::unordered_map<std::string, VM> virtualMachines;
    IsolationController isolation;

    bool allowCpuOvercommit{true};
    bool allowMemoryOvercommit{true};

public:
    VirtualizationHost(
        std::string hostName,
        ResourceCapacity physicalCapacity,
        bool cpuOvercommit = true,
        bool memoryOvercommit = true
    )
        : name(std::move(hostName)),
          capacity(physicalCapacity),
          allowCpuOvercommit(cpuOvercommit),
          allowMemoryOvercommit(memoryOvercommit) {
        capacity.validate();
    }

    const std::string& getName() const {
        return name;
    }

    const ResourceCapacity& getCapacity() const {
        return capacity;
    }

    VM& getVM(const std::string& id) {
        auto it = virtualMachines.find(id);

        if (it == virtualMachines.end()) {
            throw std::out_of_range(
                "VM " + id + " does not exist on " + name + "."
            );
        }

        return it->second;
    }

    const VM& getVM(const std::string& id) const {
        auto it = virtualMachines.find(id);

        if (it == virtualMachines.end()) {
            throw std::out_of_range(
                "VM " + id + " does not exist on " + name + "."
            );
        }

        return it->second;
    }

    int allocatedVCPUs() const {
        int total = 0;

        for (const auto& [id, vm] : virtualMachines) {
            total += vm.vcpus;
        }

        return total;
    }

    double allocatedMemory() const {
        double total = 0;

        for (const auto& [id, vm] : virtualMachines) {
            total += vm.memoryGB;
        }

        return total;
    }

    double allocatedStorage() const {
        double total = 0;

        for (const auto& [id, vm] : virtualMachines) {
            total += vm.storageGB;
        }

        return total;
    }

    double allocatedNetwork() const {
        double total = 0;

        for (const auto& [id, vm] : virtualMachines) {
            total += vm.networkGbps;
        }

        return total;
    }

    void admit(VM vm) {
        if (virtualMachines.contains(vm.id)) {
            throw std::runtime_error(
                "VM " + vm.id + " already exists on " + name + "."
            );
        }

        const int projectedCPU =
            allocatedVCPUs() + vm.vcpus;

        const double projectedMemory =
            allocatedMemory() + vm.memoryGB;

        const double projectedStorage =
            allocatedStorage() + vm.storageGB;

        const double projectedNetwork =
            allocatedNetwork() + vm.networkGbps;

        if (projectedStorage > capacity.storageGB) {
            throw std::runtime_error(
                "Storage admission failed for " + vm.id + "."
            );
        }

        if (projectedNetwork > capacity.networkGbps) {
            throw std::runtime_error(
                "Network admission failed for " + vm.id + "."
            );
        }

        if (
            projectedCPU > capacity.cpuCores &&
            !allowCpuOvercommit
        ) {
            throw std::runtime_error(
                "CPU overcommitment is disabled on " + name + "."
            );
        }

        if (
            projectedMemory > capacity.memoryGB &&
            !allowMemoryOvercommit
        ) {
            throw std::runtime_error(
                "Memory overcommitment is disabled on " + name + "."
            );
        }

        isolation.registerVM(vm);
        virtualMachines.emplace(vm.id, std::move(vm));
    }

    std::vector<std::reference_wrapper<VM>> runningVMs() {
        std::vector<std::reference_wrapper<VM>> result;

        for (auto& [id, vm] : virtualMachines) {
            if (vm.state == VMState::Running) {
                result.push_back(vm);
            }
        }

        return result;
    }

    std::map<std::string, double> scheduleCPU() {
        auto running = runningVMs();
        std::map<std::string, double> allocation;

        double remaining =
            static_cast<double>(capacity.cpuCores);

        /*
         * Reservations are consumed before weighted sharing. This models
         * the distinction between a guaranteed minimum and a relative
         * scheduling weight.
         */
        for (VM& vm : running) {
            const double guaranteed = std::min(
                {
                    static_cast<double>(vm.cpuReservation),
                    vm.cpuDemand,
                    static_cast<double>(vm.effectiveCpuLimit())
                }
            );

            allocation[vm.id] = guaranteed;
            remaining -= guaranteed;
        }

        std::vector<VM*> active;

        for (VM& vm : running) {
            if (vm.cpuDemand > allocation[vm.id]) {
                active.push_back(&vm);
            }
        }

        while (
            remaining > 0.000001 &&
            !active.empty()
        ) {
            int totalShares = 0;

            for (const VM* vm : active) {
                totalShares += vm->cpuShares;
            }

            if (totalShares <= 0) {
                break;
            }

            double distributed = 0;

            for (VM* vm : active) {
                const double current = allocation[vm->id];

                const double demandRemaining =
                    std::max(
                        0.0,
                        vm->cpuDemand - current
                    );

                const double limitRemaining =
                    std::max(
                        0.0,
                        static_cast<double>(
                            vm->effectiveCpuLimit()
                        ) - current
                    );

                const double share =
                    remaining *
                    static_cast<double>(vm->cpuShares) /
                    static_cast<double>(totalShares);

                const double grant =
                    std::min(
                        {share, demandRemaining, limitRemaining}
                    );

                allocation[vm->id] += grant;
                distributed += grant;
            }

            if (distributed <= 0.000001) {
                break;
            }

            remaining -= distributed;

            active.erase(
                std::remove_if(
                    active.begin(),
                    active.end(),
                    [&](const VM* vm) {
                        return
                            vm->cpuDemand - allocation[vm->id]
                                <= 0.000001 ||
                            static_cast<double>(
                                vm->effectiveCpuLimit()
                            ) - allocation[vm->id]
                                <= 0.000001;
                    }
                ),
                active.end()
            );
        }

        return allocation;
    }

    std::map<std::string, double> reclaimMemory() {
        auto running = runningVMs();

        double totalDemand = 0;

        for (VM& vm : running) {
            totalDemand += vm.memoryDemandGB;
            vm.balloonedMemoryGB = 0;
        }

        std::map<std::string, double> result;

        if (totalDemand <= capacity.memoryGB) {
            for (VM& vm : running) {
                result[vm.id] = 0;
            }

            return result;
        }

        const double deficit =
            totalDemand - capacity.memoryGB;

        struct Reclaimable {
            VM* vm;
            double amount;
        };

        std::vector<Reclaimable> candidates;
        double totalReclaimable = 0;

        for (VM& vm : running) {
            const double amount = std::max(
                0.0,
                vm.memoryDemandGB -
                    vm.memoryReservationGB
            );

            candidates.push_back({&vm, amount});
            totalReclaimable += amount;
        }

        if (totalReclaimable <= 0) {
            for (VM& vm : running) {
                vm.state = VMState::Failed;
            }

            throw std::runtime_error(
                "Host memory exhausted and no reclaimable memory remains."
            );
        }

        for (const auto& candidate : candidates) {
            const double proportional =
                deficit *
                candidate.amount /
                totalReclaimable;

            const double maximum =
                std::max(
                    0.0,
                    candidate.vm->memoryGB -
                        candidate.vm->memoryReservationGB
                );

            const double reclaimed =
                std::min(proportional, maximum);

            candidate.vm->balloonedMemoryGB = reclaimed;
            result[candidate.vm->id] = reclaimed;
        }

        return result;
    }

    std::vector<Allocation> schedule() {
        const auto cpu = scheduleCPU();
        const auto memory = reclaimMemory();

        std::vector<Allocation> result;

        for (VM& vm : runningVMs()) {
            const double cpuAllocated =
                cpu.contains(vm.id)
                    ? cpu.at(vm.id)
                    : 0.0;

            const double reclaimed =
                memory.contains(vm.id)
                    ? memory.at(vm.id)
                    : 0.0;

            const double memoryAllocated =
                std::max(
                    0.0,
                    vm.memoryDemandGB - reclaimed
                );

            result.push_back(
                Allocation{
                    vm.id,
                    cpuAllocated,
                    memoryAllocated,
                    reclaimed,
                    cpuAllocated + 0.000001 <
                        vm.cpuDemand
                }
            );
        }

        return result;
    }

    double cpuOvercommitRatio() const {
        return static_cast<double>(allocatedVCPUs()) /
               capacity.cpuCores;
    }

    double memoryOvercommitRatio() const {
        return allocatedMemory() /
               capacity.memoryGB;
    }

    void startVM(const std::string& id) {
        getVM(id).start();
    }

    void stopVM(const std::string& id) {
        getVM(id).stop();
    }

    bool canMigrateTo(
        const std::string& vmId,
        const VirtualizationHost& destination,
        std::string& reason
    ) const {
        const VM& vm = getVM(vmId);

        if (
            destination.allocatedStorage() +
                vm.storageGB >
            destination.capacity.storageGB
        ) {
            reason = "Destination storage capacity is insufficient.";
            return false;
        }

        if (
            destination.allocatedNetwork() +
                vm.networkGbps >
            destination.capacity.networkGbps
        ) {
            reason = "Destination network capacity is insufficient.";
            return false;
        }

        if (
            destination.allocatedVCPUs() +
                vm.vcpus >
            destination.capacity.cpuCores &&
            !destination.allowCpuOvercommit
        ) {
            reason = "Destination rejects CPU overcommitment.";
            return false;
        }

        if (
            destination.allocatedMemory() +
                vm.memoryGB >
            destination.capacity.memoryGB &&
            !destination.allowMemoryOvercommit
        ) {
            reason = "Destination rejects memory overcommitment.";
            return false;
        }

        reason = "Destination admission checks passed.";
        return true;
    }

    void printStatus() const {
        std::cout << "\nHost: " << name << "\n";
        std::cout
            << "Physical CPU: " << capacity.cpuCores
            << " cores | RAM: " << capacity.memoryGB
            << " GB | Storage: " << capacity.storageGB
            << " GB | Network: " << capacity.networkGbps
            << " Gbps\n";

        std::cout
            << "Allocated vCPU: " << allocatedVCPUs()
            << " (" << std::fixed << std::setprecision(2)
            << cpuOvercommitRatio() << "x)\n";

        std::cout
            << "Allocated RAM: " << allocatedMemory()
            << " GB (" << memoryOvercommitRatio()
            << "x)\n";

        for (const auto& [id, vm] : virtualMachines) {
            std::cout
                << "  " << std::left
                << std::setw(18) << vm.id
                << " state=" << std::setw(8)
                << stateName(vm.state)
                << " vCPU=" << std::setw(2)
                << vm.vcpus
                << " RAM=" << std::setw(5)
                << vm.memoryGB
                << " GB"
                << " shares=" << vm.cpuShares
                << "\n";
        }
    }

    void printIsolationCheck(
        const std::string& sourceId,
        const std::string& targetId
    ) const {
        const VM& source = getVM(sourceId);
        const VM& target = getVM(targetId);

        std::cout
            << "Isolation check "
            << sourceId << " -> "
            << targetId << ": "
            << (
                isolation.canDirectlyAccess(
                    source,
                    target
                )
                    ? "allowed"
                    : "blocked"
            )
            << "\n";
    }
};

void printAllocations(
    const std::vector<Allocation>& allocations
) {
    std::cout
        << "\n"
        << std::left
        << std::setw(18) << "VM"
        << std::setw(14) << "CPU allocated"
        << std::setw(16) << "RAM allocated"
        << std::setw(16) << "RAM reclaimed"
        << "CPU throttled\n";

    std::cout << std::string(78, '-') << "\n";

    for (const auto& allocation : allocations) {
        std::cout
            << std::left
            << std::setw(18) << allocation.vmId
            << std::setw(14)
            << std::fixed << std::setprecision(2)
            << allocation.cpuAllocated
            << std::setw(16)
            << allocation.memoryAllocatedGB
            << std::setw(16)
            << allocation.memoryReclaimedGB
            << (allocation.cpuThrottled ? "yes" : "no")
            << "\n";
    }
}

void buildProductionLikeScenario() {
    std::cout
        << "\n=== Private Cloud Resource Governance Case Study ===\n";

    VirtualizationHost host(
        "hv-prod-01",
        ResourceCapacity{
            16,
            64.0,
            2000.0,
            25.0
        },
        true,
        true
    );

    host.admit(
        VM(
            "payments-db",
            6,
            20.0,
            300.0,
            5.0,
            700,
            4,
            16.0,
            6,
            20.0,
            "payments"
        )
    );

    host.admit(
        VM(
            "checkout-api",
            4,
            12.0,
            180.0,
            4.0,
            400,
            1,
            6.0,
            std::nullopt,
            12.0,
            "checkout"
        )
    );

    host.admit(
        VM(
            "reporting",
            6,
            16.0,
            250.0,
            3.0,
            150,
            0,
            0.0,
            std::nullopt,
            std::nullopt,
            "analytics"
        )
    );

    host.admit(
        VM(
            "monitoring",
            2,
            6.0,
            100.0,
            2.0,
            250,
            0,
            2.0,
            2,
            6.0,
            "operations"
        )
    );

    for (const std::string& id :
         {"payments-db", "checkout-api", "reporting", "monitoring"}) {
        host.startVM(id);
    }

    host.getVM("payments-db").setDemand(5.5, 19.0);
    host.getVM("checkout-api").setDemand(4.0, 11.0);
    host.getVM("reporting").setDemand(6.0, 15.0);
    host.getVM("monitoring").setDemand(1.5, 5.0);

    host.printStatus();

    const auto allocations = host.schedule();

    printAllocations(allocations);

    std::cout
        << "\nCPU overcommit ratio: "
        << std::fixed << std::setprecision(2)
        << host.cpuOvercommitRatio()
        << "x\n";

    std::cout
        << "Memory overcommit ratio: "
        << host.memoryOvercommitRatio()
        << "x\n";

    host.printIsolationCheck(
        "payments-db",
        "checkout-api"
    );

    host.printIsolationCheck(
        "checkout-api",
        "checkout-api"
    );
}

void demonstrateMemoryFailure() {
    std::cout
        << "\n=== Memory Failure Boundary ===\n";

    VirtualizationHost host(
        "hv-memory-pressure",
        ResourceCapacity{
            4,
            8.0,
            500.0,
            10.0
        },
        true,
        true
    );

    host.admit(
        VM(
            "vm-a",
            2,
            6.0,
            50.0,
            1.0,
            100,
            0,
            6.0
        )
    );

    host.admit(
        VM(
            "vm-b",
            2,
            6.0,
            50.0,
            1.0,
            100,
            0,
            6.0
        )
    );

    host.startVM("vm-a");
    host.startVM("vm-b");

    host.getVM("vm-a").setDemand(2, 6);
    host.getVM("vm-b").setDemand(2, 6);

    try {
        const auto allocations = host.schedule();
        printAllocations(allocations);
    } catch (const std::exception& error) {
        std::cout
            << "Memory handling failure: "
            << error.what()
            << "\n";
    }
}

void demonstrateMigration() {
    std::cout
        << "\n=== Migration Admission ===\n";

    VirtualizationHost source(
        "hv-source",
        ResourceCapacity{
            8,
            32.0,
            500.0,
            10.0
        }
    );

    VirtualizationHost destination(
        "hv-destination",
        ResourceCapacity{
            8,
            32.0,
            500.0,
            10.0
        },
        false,
        false
    );

    source.admit(
        VM(
            "application-vm",
            4,
            12.0,
            100.0,
            2.0
        )
    );

    source.startVM("application-vm");

    std::string reason;

    const bool allowed =
        source.canMigrateTo(
            "application-vm",
            destination,
            reason
        );

    std::cout
        << "Migration allowed: "
        << (allowed ? "yes" : "no")
        << "\nReason: "
        << reason
        << "\n";
}

void demonstrateValidation() {
    std::cout
        << "\n=== Configuration Validation ===\n";

    try {
        VM invalid(
            "invalid-vm",
            2,
            4.0,
            50.0,
            1.0,
            100,
            3,
            5.0
        );
    } catch (const std::exception& error) {
        std::cout
            << "Rejected VM configuration: "
            << error.what()
            << "\n";
    }

    try {
        VirtualizationHost strictHost(
            "hv-strict",
            ResourceCapacity{
                4,
                8.0,
                100.0,
                5.0
            },
            false,
            false
        );

        strictHost.admit(
            VM(
                "first-vm",
                4,
                8.0,
                30.0,
                1.0
            )
        );

        strictHost.admit(
            VM(
                "second-vm",
                2,
                4.0,
                30.0,
                1.0
            )
        );
    } catch (const std::exception& error) {
        std::cout
            << "Placement rejected: "
            << error.what()
            << "\n";
    }
}

void runBurstSimulation() {
    std::cout
        << "\n=== Workload Burst Simulation ===\n";

    VirtualizationHost host(
        "hv-burst",
        ResourceCapacity{
            8,
            32.0,
            1000.0,
            20.0
        }
    );

    host.admit(
        VM(
            "frontend",
            3,
            8.0,
            100.0,
            2.0,
            250
        )
    );

    host.admit(
        VM(
            "orders",
            4,
            12.0,
            150.0,
            3.0,
            500,
            1,
            6.0
        )
    );

    host.admit(
        VM(
            "analytics",
            5,
            12.0,
            200.0,
            2.0,
            100
        )
    );

    for (const std::string& id :
         {"frontend", "orders", "analytics"}) {
        host.startVM(id);
    }

    std::mt19937 generator(42);
    std::uniform_real_distribution<double> cpuFactor(0.35, 1.15);
    std::uniform_real_distribution<double> memoryFactor(0.50, 1.10);

    for (int interval = 1; interval <= 8; ++interval) {
        for (const std::string& id :
             {"frontend", "orders", "analytics"}) {
            VM& vm = host.getVM(id);

            vm.setDemand(
                vm.vcpus * cpuFactor(generator),
                vm.memoryGB * memoryFactor(generator)
            );
        }

        const auto allocations = host.schedule();

        double cpuDemand = 0;
        double memoryDemand = 0;

        for (const std::string& id :
             {"frontend", "orders", "analytics"}) {
            const VM& vm = host.getVM(id);
            cpuDemand += vm.cpuDemand;
            memoryDemand += vm.memoryDemandGB;
        }

        std::cout
            << "Interval " << interval
            << ": CPU demand="
            << std::fixed << std::setprecision(1)
            << (cpuDemand / host.getCapacity().cpuCores) * 100
            << "%, memory demand="
            << (memoryDemand / host.getCapacity().memoryGB) * 100
            << "%\n";

        for (const auto& allocation : allocations) {
            if (allocation.cpuThrottled) {
                std::cout
                    << "  CPU contention: "
                    << allocation.vmId
                    << " received "
                    << allocation.cpuAllocated
                    << " vCPU.\n";
            }

            if (allocation.memoryReclaimedGB > 0) {
                std::cout
                    << "  Memory reclamation: "
                    << allocation.vmId
                    << " reclaimed "
                    << allocation.memoryReclaimedGB
                    << " GB.\n";
            }
        }
    }
}

int main() {
    try {
        std::cout
            << "SERVER VIRTUALIZATION RESOURCE GOVERNANCE ENGINE\n"
            << "C++17 case study\n";

        buildProductionLikeScenario();
        demonstrateMemoryFailure();
        demonstrateMigration();
        demonstrateValidation();
        runBurstSimulation();

        std::cout
            << "\n=== Architectural Boundary ===\n"
            << "The VM defines a virtual resource contract. "
            << "The host owns physical capacity. "
            << "Admission control decides whether a VM can be placed. "
            << "Scheduling shares contested CPU. "
            << "Memory reclamation responds to physical pressure. "
            << "Isolation prevents one guest from directly accessing another "
            << "guest's private execution state.\n";

        return 0;
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal virtualization-engine error: "
            << error.what()
            << "\n";

        return 1;
    }
}
