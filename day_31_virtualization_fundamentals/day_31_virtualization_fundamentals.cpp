#include <algorithm>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

/*
 * Virtualization Fundamentals
 *
 * Technical case study:
 * A small infrastructure platform operates physical servers and hosts
 * virtual machines. A hypervisor-like governance layer evaluates capacity,
 * places workloads, migrates VMs, and reports utilization.
 *
 * Compile:
 *   g++ -std=c++17 -Wall -Wextra -pedantic virtualization_fundamentals.cpp -o virtualization
 */

struct VirtualMachine {
    std::string name;
    std::string operatingSystem;
    int vcpus;
    double memoryGB;
    double storageGB;
    std::string workload;
    bool running = false;
    std::string host;

    void start() {
        if (host.empty()) {
            throw std::runtime_error(
                "A VM cannot start without a physical host."
            );
        }

        running = true;
    }

    void stop() {
        running = false;
    }
};


class PhysicalServer {
private:
    std::map<std::string, VirtualMachine> virtualMachines;

public:
    std::string name;
    int cpuCores;
    double memoryGB;
    double storageGB;
    double networkGbps;
    double powerWatts;

    PhysicalServer(
        std::string serverName,
        int cores,
        double memory,
        double storage,
        double network,
        double power
    )
        : name(std::move(serverName)),
          cpuCores(cores),
          memoryGB(memory),
          storageGB(storage),
          networkGbps(network),
          powerWatts(power) {

        if (cpuCores <= 0 || memoryGB <= 0 || storageGB <= 0) {
            throw std::invalid_argument(
                "Physical server resources must be positive."
            );
        }
    }

    double allocatedCPU() const {
        double total = 0;

        for (const auto& [name, vm] : virtualMachines) {
            (void)name;
            total += vm.vcpus;
        }

        return total;
    }

    double allocatedMemory() const {
        double total = 0;

        for (const auto& [name, vm] : virtualMachines) {
            (void)name;
            total += vm.memoryGB;
        }

        return total;
    }

    double allocatedStorage() const {
        double total = 0;

        for (const auto& [name, vm] : virtualMachines) {
            (void)name;
            total += vm.storageGB;
        }

        return total;
    }

    bool canHost(
        const VirtualMachine& vm,
        std::string& reason
    ) const {
        if (vm.vcpus <= 0 ||
            vm.memoryGB <= 0 ||
            vm.storageGB <= 0) {

            reason = "VM resource requests must be positive.";
            return false;
        }

        if (vm.vcpus > cpuCores - allocatedCPU()) {
            reason = "Insufficient physical CPU capacity.";
            return false;
        }

        if (vm.memoryGB > memoryGB - allocatedMemory()) {
            reason = "Insufficient physical memory capacity.";
            return false;
        }

        if (vm.storageGB > storageGB - allocatedStorage()) {
            reason = "Insufficient physical storage capacity.";
            return false;
        }

        reason = "Capacity available.";
        return true;
    }

    void deploy(VirtualMachine vm) {
        std::string reason;

        if (!canHost(vm, reason)) {
            throw std::runtime_error(
                "Deployment rejected on " + name + ": " + reason
            );
        }

        if (virtualMachines.contains(vm.name)) {
            throw std::runtime_error(
                "VM already exists on host: " + vm.name
            );
        }

        vm.host = name;
        virtualMachines.emplace(vm.name, std::move(vm));
    }

    VirtualMachine remove(const std::string& vmName) {
        auto iterator = virtualMachines.find(vmName);

        if (iterator == virtualMachines.end()) {
            throw std::runtime_error(
                "VM not found on host: " + vmName
            );
        }

        VirtualMachine vm = iterator->second;
        virtualMachines.erase(iterator);
        vm.host.clear();

        return vm;
    }

    const std::map<std::string, VirtualMachine>& vms() const {
        return virtualMachines;
    }

    double cpuUtilization() const {
        return allocatedCPU() / static_cast<double>(cpuCores);
    }

    double memoryUtilization() const {
        return allocatedMemory() / memoryGB;
    }

    double storageUtilization() const {
        return allocatedStorage() / storageGB;
    }

    void printReport() const {
        std::cout << "\nPhysical host: " << name << '\n';

        std::cout
            << "  Hardware: "
            << cpuCores << " CPU cores, "
            << memoryGB << " GB RAM, "
            << storageGB << " GB storage\n";

        std::cout
            << "  Allocated: "
            << allocatedCPU() << " vCPU, "
            << allocatedMemory() << " GB RAM, "
            << allocatedStorage() << " GB storage\n";

        std::cout << std::fixed << std::setprecision(1);

        std::cout
            << "  Utilization: CPU "
            << cpuUtilization() * 100.0 << "%, RAM "
            << memoryUtilization() * 100.0 << "%, storage "
            << storageUtilization() * 100.0 << "%\n";

        for (const auto& [vmName, vm] : virtualMachines) {
            std::cout
                << "    VM " << vmName
                << " | OS=" << vm.operatingSystem
                << " | vCPU=" << vm.vcpus
                << " | RAM=" << vm.memoryGB << " GB"
                << " | storage=" << vm.storageGB << " GB"
                << " | state=" << (vm.running ? "running" : "stopped")
                << '\n';
        }
    }
};


class VirtualizationPlatform {
private:
    std::map<std::string, PhysicalServer> hosts;

public:
    void addHost(PhysicalServer host) {
        if (hosts.contains(host.name)) {
            throw std::runtime_error(
                "Host already registered: " + host.name
            );
        }

        hosts.emplace(host.name, std::move(host));
    }

    PhysicalServer* chooseHost(
        const VirtualMachine& vm
    ) {
        PhysicalServer* selected = nullptr;
        double bestScore = 0.0;

        /*
         * This is a deliberately simple placement policy.
         * The platform minimizes projected CPU + memory utilization.
         *
         * Real systems can consider NUMA topology, CPU reservations,
         * affinity rules, storage latency, network topology, availability
         * zones, power state, and workload-specific constraints.
         */

        for (auto& [hostName, host] : hosts) {
            (void)hostName;

            std::string reason;

            if (!host.canHost(vm, reason)) {
                continue;
            }

            const double projectedCPU =
                (host.allocatedCPU() + vm.vcpus)
                / static_cast<double>(host.cpuCores);

            const double projectedMemory =
                (host.allocatedMemory() + vm.memoryGB)
                / host.memoryGB;

            const double score =
                projectedCPU + projectedMemory;

            if (selected == nullptr || score < bestScore) {
                selected = &host;
                bestScore = score;
            }
        }

        return selected;
    }

    void deploy(VirtualMachine vm) {
        PhysicalServer* host = chooseHost(vm);

        if (host == nullptr) {
            throw std::runtime_error(
                "No physical host has enough capacity for VM " +
                vm.name
            );
        }

        host->deploy(std::move(vm));
    }

    void migrate(
        const std::string& vmName,
        const std::string& sourceName,
        const std::string& destinationName
    ) {
        auto sourceIterator = hosts.find(sourceName);
        auto destinationIterator = hosts.find(destinationName);

        if (sourceIterator == hosts.end() ||
            destinationIterator == hosts.end()) {

            throw std::runtime_error(
                "Migration references an unknown physical host."
            );
        }

        PhysicalServer& source = sourceIterator->second;
        PhysicalServer& destination = destinationIterator->second;

        const auto vmIterator = source.vms().find(vmName);

        if (vmIterator == source.vms().end()) {
            throw std::runtime_error(
                "The requested VM is not on the source host."
            );
        }

        const VirtualMachine& currentVM = vmIterator->second;
        std::string reason;

        if (!destination.canHost(currentVM, reason)) {
            throw std::runtime_error(
                "Migration rejected: " + reason
            );
        }

        VirtualMachine vm = source.remove(vmName);

        /*
         * The VM's logical configuration remains intact while its physical
         * placement changes. Real live migration also transfers memory state,
         * CPU execution state, and storage/network dependencies.
         */
        destination.deploy(std::move(vm));
    }

    void printInfrastructure() const {
        std::cout << "\n=== Infrastructure State ===\n";

        for (const auto& [name, host] : hosts) {
            (void)name;
            host.printReport();
        }
    }

    void printPowerEstimate() const {
        double watts = 0;
        int activeHosts = 0;

        for (const auto& [name, host] : hosts) {
            (void)name;

            if (!host.vms().empty()) {
                watts += host.powerWatts;
                ++activeHosts;
            }
        }

        std::cout
            << "\nActive physical hosts: "
            << activeHosts << '\n';

        std::cout
            << "Illustrative active-host power budget: "
            << watts << " W\n";
    }
};


static VirtualMachine makeVM(
    const std::string& name,
    int vcpus,
    double memoryGB,
    double storageGB,
    const std::string& workload
) {
    return VirtualMachine{
        name,
        "Linux",
        vcpus,
        memoryGB,
        storageGB,
        workload,
        false,
        ""
    };
}


void demonstratePhysicalToVirtualAbstraction() {
    std::cout << "=== Physical-to-Virtual Resource Abstraction ===\n";

    PhysicalServer server(
        "physical-01",
        16,
        64,
        2000,
        10,
        500
    );

    VirtualMachine web = makeVM(
        "web-vm",
        4,
        8,
        100,
        "Web application"
    );

    VirtualMachine database = makeVM(
        "database-vm",
        6,
        20,
        400,
        "Database"
    );

    server.deploy(web);
    server.deploy(database);

    /*
     * Guests receive virtual hardware. The hypervisor is responsible for
     * mapping virtual CPU, memory, storage, and devices to physical resources.
     */
    server.printReport();

    std::cout
        << "\nThe two VMs share one physical server while maintaining "
        << "separate logical resource boundaries.\n";
}


void demonstrateCapacityFailure() {
    std::cout << "\n=== Capacity Failure ===\n";

    PhysicalServer smallServer(
        "small-01",
        4,
        8,
        250,
        1,
        180
    );

    VirtualMachine oversized = makeVM(
        "oversized-vm",
        8,
        16,
        100,
        "Workload exceeding host capacity"
    );

    std::string reason;

    if (!smallServer.canHost(oversized, reason)) {
        std::cout
            << "Deployment rejected before resource allocation.\n"
            << "Reason: " << reason << '\n';
    }
}


void demonstratePlatform() {
    std::cout << "\n=== Virtualized Infrastructure Platform ===\n";

    VirtualizationPlatform platform;

    platform.addHost(
        PhysicalServer(
            "compute-01",
            16,
            64,
            2000,
            10,
            500
        )
    );

    platform.addHost(
        PhysicalServer(
            "compute-02",
            16,
            64,
            2000,
            10,
            500
        )
    );

    platform.addHost(
        PhysicalServer(
            "compute-03",
            16,
            64,
            2000,
            10,
            500
        )
    );

    std::vector<VirtualMachine> workloads;

    workloads.push_back(
        makeVM("frontend-01", 4, 8, 120, "Frontend")
    );

    workloads.push_back(
        makeVM("api-01", 4, 12, 150, "API")
    );

    workloads.push_back(
        makeVM("database-01", 6, 20, 500, "Database")
    );

    workloads.push_back(
        makeVM("worker-01", 3, 10, 250, "Background worker")
    );

    workloads.push_back(
        makeVM("monitor-01", 1, 4, 80, "Monitoring")
    );

    for (auto& vm : workloads) {
        platform.deploy(vm);
    }

    platform.printInfrastructure();

    std::cout << "\n=== Migration ===\n";

    try {
        /*
         * Migration changes the physical placement of a VM without changing
         * the VM's virtual hardware definition.
         */
        platform.migrate(
            "frontend-01",
            "compute-01",
            "compute-03"
        );

        std::cout
            << "frontend-01 migrated successfully from compute-01 "
            << "to compute-03.\n";
    } catch (const std::exception& error) {
        std::cout
            << "Migration failed: "
            << error.what() << '\n';
    }

    platform.printInfrastructure();
    platform.printPowerEstimate();
}


void demonstrateTradeOffs() {
    std::cout << "\n=== Virtualization Trade-offs ===\n";

    std::cout
        << "Resource pooling can improve utilization, but virtualization "
        << "does not create additional physical CPU, RAM, storage, or "
        << "network bandwidth.\n";

    std::cout
        << "Multiple VMs can compete for the same host resources. "
        << "Oversubscription can increase flexibility, but excessive "
        << "overcommitment can create contention and unpredictable latency.\n";

    std::cout
        << "The hypervisor becomes an important infrastructure component. "
        << "Its configuration, isolation boundary, device model, and "
        << "management interfaces therefore require security controls.\n";

    std::cout
        << "VM mobility and consolidation can reduce the number of active "
        << "physical servers, but availability still requires redundancy "
        << "when host failure is a concern.\n";
}


int main() {
    try {
        std::cout
            << "VIRTUALIZATION FUNDAMENTALS\n"
            << "===========================\n";

        demonstratePhysicalToVirtualAbstraction();
        demonstrateCapacityFailure();
        demonstratePlatform();
        demonstrateTradeOffs();

        std::cout
            << "\nCase study complete.\n";

        return 0;
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << '\n';

        return 1;
    }
}
