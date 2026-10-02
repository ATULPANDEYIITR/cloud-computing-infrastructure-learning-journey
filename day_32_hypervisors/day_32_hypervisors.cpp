#include <algorithm>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <queue>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Hypervisor governance and resource-management case study.
 *
 * Scenario:
 * A small infrastructure team operates a virtualization node that hosts
 * application VMs. The system must decide whether a VM can be created,
 * started, scheduled, and allowed to consume virtual resources.
 *
 * The case study models the architectural boundary between:
 *
 *   Type 1:
 *       hardware -> hypervisor -> VMs
 *
 *   Type 2:
 *       hardware -> host OS -> hosted hypervisor -> VMs
 *
 * It then focuses on a Type 1 production-style resource manager. The
 * implementation covers CPU scheduling, memory mappings, virtual disks,
 * virtual NICs, lifecycle transitions, overcommitment policy, snapshots,
 * validation, and isolation checks.
 *
 * This is a simulation. A production hypervisor additionally depends on
 * processor virtualization extensions, interrupt virtualization, nested page
 * tables, IOMMUs, device models, kernel integration, firmware, and hardware.
 */

enum class HypervisorType {
    Type1,
    Type2
};

enum class VMState {
    Created,
    Running,
    Paused,
    Stopped,
    Failed
};

std::string toString(HypervisorType type) {
    return type == HypervisorType::Type1
        ? "Type 1 / bare-metal"
        : "Type 2 / hosted";
}

std::string toString(VMState state) {
    switch (state) {
        case VMState::Created: return "created";
        case VMState::Running: return "running";
        case VMState::Paused: return "paused";
        case VMState::Stopped: return "stopped";
        case VMState::Failed: return "failed";
    }
    return "unknown";
}

class ValidationError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class ResourceError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class LifecycleError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct Host {
    std::string name;
    std::size_t physicalCpus;
    std::size_t memoryMiB;
    std::size_t storageGiB;
    std::optional<std::string> hostOs;
    HypervisorType type;

    std::string architecture() const {
        if (type == HypervisorType::Type1) {
            return "hardware -> Type 1 hypervisor -> virtual machines";
        }

        return "hardware -> host OS -> Type 2 hypervisor -> virtual machines";
    }
};

struct VirtualDisk {
    std::size_t capacityGiB;
    std::size_t usedGiB = 0;

    void write(std::size_t amountGiB) {
        if (amountGiB == 0) {
            throw ValidationError("Disk write must be greater than zero.");
        }

        if (usedGiB + amountGiB > capacityGiB) {
            throw ResourceError("Virtual disk capacity exceeded.");
        }

        usedGiB += amountGiB;
    }
};

struct VirtualNic {
    std::string mac;
    bool connected = true;
    std::uint64_t packetsSent = 0;

    void send(std::uint64_t packets) {
        if (packets == 0) {
            throw ValidationError("Packet count must be greater than zero.");
        }

        if (!connected) {
            throw LifecycleError("Virtual NIC is disconnected.");
        }

        packetsSent += packets;
    }
};

struct MemoryMapping {
    std::size_t guestFrame;
    std::size_t hostFrame;
    bool writable;
};

struct Snapshot {
    VMState state;
    std::size_t memoryUsedMiB;
    std::size_t diskUsedGiB;
    std::uint64_t cpuTimeMs;
};

struct VirtualMachine {
    std::string id;
    std::string name;
    std::size_t vcpus;
    std::size_t memoryMiB;
    VirtualDisk disk;
    VirtualNic nic;
    VMState state = VMState::Created;
    std::size_t memoryUsedMiB = 0;
    std::uint64_t cpuTimeMs = 0;
    std::map<std::size_t, MemoryMapping> mappings;
    std::optional<Snapshot> snapshot;

    void allocateMemory(std::size_t amountMiB) {
        if (amountMiB == 0) {
            throw ValidationError("Memory allocation must be greater than zero.");
        }

        if (memoryUsedMiB + amountMiB > memoryMiB) {
            throw ResourceError(
                "VM memory limit would be exceeded."
            );
        }

        memoryUsedMiB += amountMiB;
    }

    void runCpu(std::uint64_t milliseconds) {
        if (state != VMState::Running) {
            throw LifecycleError("VM is not running.");
        }

        if (milliseconds == 0) {
            throw ValidationError("CPU quantum must be greater than zero.");
        }

        cpuTimeMs += milliseconds;
    }

    void takeSnapshot() {
        snapshot = Snapshot{
            state,
            memoryUsedMiB,
            disk.usedGiB,
            cpuTimeMs
        };
    }

    void restoreSnapshot() {
        if (!snapshot.has_value()) {
            throw LifecycleError("VM has no snapshot.");
        }

        state = snapshot->state;
        memoryUsedMiB = snapshot->memoryUsedMiB;
        disk.usedGiB = snapshot->diskUsedGiB;
        cpuTimeMs = snapshot->cpuTimeMs;
    }
};

class MemoryManager {
private:
    std::queue<std::size_t> freeFrames;

public:
    explicit MemoryManager(std::size_t frameCount) {
        if (frameCount == 0) {
            throw ValidationError("Memory manager requires host frames.");
        }

        for (std::size_t frame = 0; frame < frameCount; ++frame) {
            freeFrames.push(frame);
        }
    }

    MemoryMapping map(VirtualMachine& vm, std::size_t guestFrame) {
        auto existing = vm.mappings.find(guestFrame);

        if (existing != vm.mappings.end()) {
            return existing->second;
        }

        if (freeFrames.empty()) {
            throw ResourceError("No free host memory frames remain.");
        }

        const std::size_t hostFrame = freeFrames.front();
        freeFrames.pop();

        MemoryMapping mapping{
            guestFrame,
            hostFrame,
            true
        };

        vm.mappings[guestFrame] = mapping;
        return mapping;
    }
};

struct VirtualCPU {
    std::string id;
    VirtualMachine* vm;
    std::uint64_t instructions = 0;
};

class CpuScheduler {
private:
    std::size_t physicalCpus;
    std::queue<VirtualCPU*> readyQueue;

public:
    explicit CpuScheduler(std::size_t cpuCount)
        : physicalCpus(cpuCount) {
        if (physicalCpus == 0) {
            throw ValidationError("Scheduler requires a physical CPU.");
        }
    }

    void enqueue(VirtualCPU* vcpu) {
        if (vcpu != nullptr && vcpu->vm->state == VMState::Running) {
            readyQueue.push(vcpu);
        }
    }

    std::vector<std::string> tick(std::uint64_t quantumMs) {
        if (quantumMs == 0) {
            throw ValidationError("Scheduler quantum must be positive.");
        }

        std::vector<std::string> events;
        std::vector<VirtualCPU*> executed;

        for (std::size_t core = 0;
             core < physicalCpus && !readyQueue.empty();
             ++core) {

            VirtualCPU* vcpu = readyQueue.front();
            readyQueue.pop();

            if (vcpu->vm->state != VMState::Running) {
                continue;
            }

            vcpu->instructions += quantumMs * 1000;
            vcpu->vm->runCpu(quantumMs);

            std::ostringstream event;
            event << "physical core " << core
                  << " -> " << vcpu->id
                  << " -> " << vcpu->vm->name
                  << " for " << quantumMs << " ms";

            events.push_back(event.str());
            executed.push_back(vcpu);
        }

        for (VirtualCPU* vcpu : executed) {
            if (vcpu->vm->state == VMState::Running) {
                readyQueue.push(vcpu);
            }
        }

        return events;
    }
};

class Hypervisor {
private:
    Host host;
    bool allowOvercommit;
    std::unordered_map<std::string, VirtualMachine> vms;
    std::vector<VirtualCPU> virtualCpus;

    MemoryManager memoryManager;
    CpuScheduler scheduler;

    std::size_t allocatedVcpus = 0;
    std::size_t allocatedMemoryMiB = 0;
    std::size_t allocatedStorageGiB = 0;

    static void validatePositive(std::size_t value, const std::string& field) {
        if (value == 0) {
            throw ValidationError(field + " must be greater than zero.");
        }
    }

public:
    Hypervisor(Host hostConfig, bool overcommit)
        : host(std::move(hostConfig)),
          allowOvercommit(overcommit),
          memoryManager(std::max<std::size_t>(1, host.memoryMiB / 4)),
          scheduler(host.physicalCpus) {}

    VirtualMachine& createVm(
        std::string id,
        std::string name,
        std::size_t vcpus,
        std::size_t memoryMiB,
        std::size_t diskGiB,
        std::string mac
    ) {
        if (id.empty() || name.empty()) {
            throw ValidationError("VM id and name are required.");
        }

        validatePositive(vcpus, "vCPU count");
        validatePositive(memoryMiB, "memory");
        validatePositive(diskGiB, "disk");

        if (vms.find(id) != vms.end()) {
            throw ValidationError("A VM with this identifier already exists.");
        }

        const auto nextVcpus = allocatedVcpus + vcpus;
        const auto nextMemory = allocatedMemoryMiB + memoryMiB;
        const auto nextStorage = allocatedStorageGiB + diskGiB;

        if (!allowOvercommit) {
            if (nextVcpus > host.physicalCpus) {
                throw ResourceError("vCPU capacity exceeded.");
            }

            if (nextMemory > host.memoryMiB) {
                throw ResourceError("Memory capacity exceeded.");
            }

            if (nextStorage > host.storageGiB) {
                throw ResourceError("Storage capacity exceeded.");
            }
        }

        VirtualMachine vm{
            id,
            name,
            vcpus,
            memoryMiB,
            VirtualDisk{diskGiB},
            VirtualNic{std::move(mac)}
        };

        auto [iterator, inserted] = vms.emplace(id, std::move(vm));

        if (!inserted) {
            throw ValidationError("VM insertion failed.");
        }

        allocatedVcpus = nextVcpus;
        allocatedMemoryMiB = nextMemory;
        allocatedStorageGiB = nextStorage;

        return iterator->second;
    }

    VirtualMachine& getVm(const std::string& id) {
        auto iterator = vms.find(id);

        if (iterator == vms.end()) {
            throw LifecycleError("Unknown VM: " + id);
        }

        return iterator->second;
    }

    void start(const std::string& id) {
        VirtualMachine& vm = getVm(id);

        if (vm.state == VMState::Running) {
            throw LifecycleError("VM is already running.");
        }

        if (vm.state == VMState::Failed) {
            throw LifecycleError("Failed VM requires repair.");
        }

        vm.state = VMState::Running;

        /*
         * A vCPU is a schedulable virtual execution context. It is not
         * equivalent to permanently reserving one physical core.
         */
        for (std::size_t index = 0; index < vm.vcpus; ++index) {
            std::ostringstream idBuilder;
            idBuilder << vm.id << "-vcpu-" << index;

            virtualCpus.push_back(
                VirtualCPU{idBuilder.str(), &vm, 0}
            );

            scheduler.enqueue(&virtualCpus.back());
        }
    }

    void pause(const std::string& id) {
        VirtualMachine& vm = getVm(id);

        if (vm.state != VMState::Running) {
            throw LifecycleError("Only a running VM can be paused.");
        }

        vm.state = VMState::Paused;
    }

    void stop(const std::string& id) {
        VirtualMachine& vm = getVm(id);
        vm.state = VMState::Stopped;
    }

    MemoryMapping mapGuestPage(
        const std::string& id,
        std::size_t guestFrame
    ) {
        return memoryManager.map(getVm(id), guestFrame);
    }

    std::vector<std::string> schedule(std::uint64_t quantumMs) {
        return scheduler.tick(quantumMs);
    }

    void printCapacity() const {
        std::cout
            << "physical CPUs: " << host.physicalCpus << '\n'
            << "allocated vCPUs: " << allocatedVcpus << '\n'
            << "physical memory: " << host.memoryMiB << " MiB\n"
            << "allocated memory: " << allocatedMemoryMiB << " MiB\n"
            << "physical storage: " << host.storageGiB << " GiB\n"
            << "allocated storage: " << allocatedStorageGiB << " GiB\n"
            << "overcommitment: "
            << (allowOvercommit ? "enabled" : "disabled")
            << "\n";
    }

    void printIsolationModel() const {
        std::cout
            << "\nIsolation controls:\n"
            << "  CPU: guest execution is represented through schedulable vCPUs\n"
            << "  Memory: guest frames map only to allocated host frames\n"
            << "  Storage: each VM receives a bounded virtual disk\n"
            << "  Network: each VM has an explicit virtual NIC\n"
            << "  Management: lifecycle operations remain outside guest state\n";
    }
};

void showArchitectureComparison() {
    std::cout << "=== Hypervisor Architecture ===\n";

    Host type1{
        "datacenter-node",
        16,
        65536,
        2000,
        std::nullopt,
        HypervisorType::Type1
    };

    Host type2{
        "developer-workstation",
        8,
        32768,
        1000,
        std::string("Linux"),
        HypervisorType::Type2
    };

    std::cout << type1.name << ": " << type1.architecture() << '\n';
    std::cout << type2.name << ": " << type2.architecture() << '\n';

    std::cout
        << "\nThe key architectural distinction is where the virtualization "
           "layer sits. Type 1 runs directly against the machine hardware, "
           "while Type 2 relies on a conventional host operating system.\n\n";
}

void demonstrateProductionCaseStudy() {
    std::cout << "=== Production VM Resource Manager ===\n";

    Host productionHost{
        "production-node-01",
        8,
        32768,
        1000,
        std::nullopt,
        HypervisorType::Type1
    };

    Hypervisor hypervisor(productionHost, false);

    auto& api = hypervisor.createVm(
        "vm-api",
        "api-service",
        2,
        4096,
        80,
        "02:00:aa:10:20:30"
    );

    auto& database = hypervisor.createVm(
        "vm-db",
        "database-service",
        2,
        8192,
        200,
        "02:00:bb:10:20:30"
    );

    hypervisor.start(api.id);
    hypervisor.start(database.id);

    api.allocateMemory(1024);
    database.allocateMemory(4096);

    api.disk.write(12);
    database.disk.write(35);

    api.nic.send(1000);
    database.nic.send(250);

    std::cout << "\nGuest-to-host memory mappings:\n";

    for (std::size_t guestFrame : {0u, 1u, 2u, 3u}) {
        const auto mapping = hypervisor.mapGuestPage(
            api.id,
            guestFrame
        );

        std::cout
            << "  guest frame " << mapping.guestFrame
            << " -> host frame " << mapping.hostFrame
            << " writable=" << std::boolalpha
            << mapping.writable << '\n';
    }

    std::cout << "\nCPU scheduler activity:\n";

    for (int tick = 0; tick < 3; ++tick) {
        const auto events = hypervisor.schedule(10);

        for (const auto& event : events) {
            std::cout << "  " << event << '\n';
        }
    }

    api.takeSnapshot();
    api.allocateMemory(256);
    api.disk.write(4);

    std::cout
        << "\nAPI VM before snapshot restore: "
        << api.memoryUsedMiB << " MiB memory, "
        << api.disk.usedGiB << " GiB disk used\n";

    api.restoreSnapshot();

    std::cout
        << "API VM after snapshot restore: "
        << api.memoryUsedMiB << " MiB memory, "
        << api.disk.usedGiB << " GiB disk used\n";

    hypervisor.pause(database.id);

    std::cout
        << "Database VM state after pause: "
        << toString(database.state) << '\n';

    hypervisor.printCapacity();
    hypervisor.printIsolationModel();
}

void demonstrateCapacityFailure() {
    std::cout << "\n=== Capacity Failure ===\n";

    Host constrainedHost{
        "small-node",
        4,
        8192,
        250,
        std::nullopt,
        HypervisorType::Type1
    };

    Hypervisor strictHypervisor(constrainedHost, false);

    strictHypervisor.createVm(
        "vm-a",
        "service-a",
        2,
        4096,
        40,
        "02:00:01:01:01:01"
    );

    try {
        strictHypervisor.createVm(
            "vm-b",
            "service-b",
            2,
            4096,
            40,
            "02:00:02:02:02:02"
        );

        std::cout << "Unexpected allocation success.\n";
    } catch (const ResourceError& error) {
        std::cout
            << "Allocation rejected safely: "
            << error.what() << '\n';
    }

    /*
     * With overcommitment enabled, the virtual allocation may exceed the
     * physical inventory. This improves consolidation potential but moves
     * pressure management into runtime scheduling and memory policy.
     */
    Hypervisor overcommittingHypervisor(constrainedHost, true);

    overcommittingHypervisor.createVm(
        "vm-a",
        "service-a",
        4,
        4096,
        40,
        "02:00:03:03:03:03"
    );

    overcommittingHypervisor.createVm(
        "vm-b",
        "service-b",
        4,
        4096,
        40,
        "02:00:04:04:04:04"
    );

    std::cout
        << "Overcommitment accepted the virtual configuration because "
           "policy allows configured capacity to exceed physical capacity.\n";
}

void demonstrateSecurityFailure() {
    std::cout << "\n=== Virtual Device Failure ===\n";

    Host host{
        "security-node",
        4,
        16384,
        500,
        std::nullopt,
        HypervisorType::Type1
    };

    Hypervisor hypervisor(host, false);

    auto& vm = hypervisor.createVm(
        "vm-secure",
        "isolated-service",
        1,
        2048,
        30,
        "02:00:10:20:30:40"
    );

    hypervisor.start(vm.id);

    vm.nic.connected = false;

    try {
        vm.nic.send(10);
    } catch (const LifecycleError& error) {
        std::cout
            << "Network operation blocked at the virtual-device boundary: "
            << error.what() << '\n';
    }

    std::cout
        << "The simulated boundary illustrates why a hypervisor must control "
           "device access instead of allowing guests unrestricted hardware access.\n";
}

void explainPerformanceTradeOffs() {
    std::cout << "\n=== Performance and Architecture ===\n";

    std::cout
        << "CPU scheduling introduces a distinction between virtual and "
           "physical processors.\n"
        << "Memory virtualization adds address-translation work, although "
           "modern CPUs accelerate it with nested page translation.\n"
        << "Device emulation can introduce overhead because guest I/O may "
           "cross virtualization and host software boundaries.\n"
        << "Paravirtualized devices and hardware-assisted mechanisms can "
           "reduce virtualization overhead.\n"
        << "NUMA-aware placement matters on multi-socket hosts because "
           "remote memory access can cost more than local memory access.\n";
}

int main() {
    try {
        showArchitectureComparison();
        demonstrateProductionCaseStudy();
        demonstrateCapacityFailure();
        demonstrateSecurityFailure();
        explainPerformanceTradeOffs();

        std::cout << "\nCase study completed successfully.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal simulation error: "
            << error.what() << '\n';
        return 1;
    }
}
