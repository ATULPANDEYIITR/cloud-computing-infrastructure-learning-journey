#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

/*
 * Virtual machine governance and merge-like resource control case study.
 *
 * Scenario:
 * A small private-cloud platform runs database, CI, and analytics VMs on a
 * shared virtualization host. The control plane must determine whether a VM
 * can start, resize memory, expand a disk, receive CPU time, or revert to a
 * snapshot.
 *
 * The program models:
 *   - VM lifecycle states
 *   - vCPU allocation and weighted CPU scheduling
 *   - memory reservations and hard limits
 *   - thin and thick virtual disks
 *   - snapshot capture and restoration
 *   - validation and failure handling
 *
 * The implementation uses C++17 and only the standard library.
 */

enum class VMState {
    Defined,
    Stopped,
    Running,
    Paused,
    Suspended,
    Error
};

enum class DiskFormat {
    Raw,
    QCow2,
    VMDK
};

std::string toString(VMState state) {
    switch (state) {
        case VMState::Defined: return "defined";
        case VMState::Stopped: return "stopped";
        case VMState::Running: return "running";
        case VMState::Paused: return "paused";
        case VMState::Suspended: return "suspended";
        case VMState::Error: return "error";
    }
    return "unknown";
}

std::string toString(DiskFormat format) {
    switch (format) {
        case DiskFormat::Raw: return "raw";
        case DiskFormat::QCow2: return "qcow2";
        case DiskFormat::VMDK: return "vmdk";
    }
    return "unknown";
}

struct CPUAllocation {
    unsigned vcpus;
    double cpuLimitPercent{100.0};
    unsigned cpuShares{1024};
    std::map<unsigned, unsigned> pinning;

    void validate(unsigned hostVcpus) const {
        if (vcpus == 0) {
            throw std::invalid_argument(
                "A VM must have at least one vCPU."
            );
        }

        if (vcpus > hostVcpus) {
            throw std::invalid_argument(
                "Requested vCPUs exceed host CPU count."
            );
        }

        if (
            cpuLimitPercent < 1.0 ||
            cpuLimitPercent > static_cast<double>(vcpus) * 100.0
        ) {
            throw std::invalid_argument(
                "CPU limit is outside the permitted range."
            );
        }

        if (cpuShares < 2) {
            throw std::invalid_argument(
                "CPU shares must be at least 2."
            );
        }

        for (const auto& [vcpu, physicalCpu] : pinning) {
            if (vcpu >= vcpus) {
                throw std::invalid_argument(
                    "vCPU pinning references a nonexistent vCPU."
                );
            }

            if (physicalCpu >= hostVcpus) {
                throw std::invalid_argument(
                    "CPU pinning references a nonexistent host CPU."
                );
            }
        }
    }
};

struct MemoryAllocation {
    unsigned memoryMB;
    unsigned reservationMB;
    unsigned limitMB;
    bool ballooning{false};

    void validate(unsigned hostMemoryMB) const {
        if (memoryMB == 0) {
            throw std::invalid_argument(
                "VM memory must be positive."
            );
        }

        if (reservationMB > memoryMB) {
            throw std::invalid_argument(
                "Memory reservation cannot exceed configured memory."
            );
        }

        if (limitMB < memoryMB) {
            throw std::invalid_argument(
                "Memory limit cannot be below configured memory."
            );
        }

        if (limitMB > hostMemoryMB) {
            throw std::invalid_argument(
                "Memory limit exceeds host physical memory."
            );
        }
    }
};

class VirtualDisk {
public:
    VirtualDisk(
        std::string name,
        double capacityGB,
        double allocatedGB,
        DiskFormat format,
        bool thinProvisioned,
        bool readOnly = false
    )
        : name_(std::move(name)),
          capacityGB_(capacityGB),
          allocatedGB_(allocatedGB),
          format_(format),
          thinProvisioned_(thinProvisioned),
          readOnly_(readOnly) {
        validate();
    }

    const std::string& name() const {
        return name_;
    }

    double capacityGB() const {
        return capacityGB_;
    }

    double allocatedGB() const {
        return allocatedGB_;
    }

    bool thinProvisioned() const {
        return thinProvisioned_;
    }

    void expand(double newCapacityGB) {
        if (newCapacityGB <= capacityGB_) {
            throw std::invalid_argument(
                "Disk expansion must increase capacity."
            );
        }

        capacityGB_ = newCapacityGB;
    }

    void write(double amountGB) {
        if (readOnly_) {
            throw std::runtime_error(
                "Write rejected because the disk is read-only."
            );
        }

        if (amountGB < 0.0) {
            throw std::invalid_argument(
                "Disk write cannot be negative."
            );
        }

        if (allocatedGB_ + amountGB > capacityGB_) {
            throw std::runtime_error(
                "Virtual disk capacity would be exceeded."
            );
        }

        allocatedGB_ += amountGB;
    }

    void restoreAllocation(double allocationGB) {
        if (
            allocationGB < 0.0 ||
            allocationGB > capacityGB_
        ) {
            throw std::invalid_argument(
                "Snapshot allocation is incompatible with disk capacity."
            );
        }

        allocatedGB_ = allocationGB;
    }

private:
    void validate() const {
        if (name_.empty()) {
            throw std::invalid_argument(
                "Virtual disk name cannot be empty."
            );
        }

        if (capacityGB_ <= 0.0) {
            throw std::invalid_argument(
                "Virtual disk capacity must be positive."
            );
        }

        if (
            allocatedGB_ < 0.0 ||
            allocatedGB_ > capacityGB_
        ) {
            throw std::invalid_argument(
                "Disk allocation must remain within capacity."
            );
        }
    }

    std::string name_;
    double capacityGB_;
    double allocatedGB_;
    DiskFormat format_;
    bool thinProvisioned_;
    bool readOnly_;
};

struct Snapshot {
    std::string id;
    std::string description;
    VMState capturedState;
    CPUAllocation cpu;
    MemoryAllocation memory;
    std::map<std::string, double> diskAllocations;
};

class VirtualMachine {
public:
    VirtualMachine(
        std::string name,
        CPUAllocation cpu,
        MemoryAllocation memory
    )
        : name_(std::move(name)),
          cpu_(std::move(cpu)),
          memory_(std::move(memory)) {}

    const std::string& name() const {
        return name_;
    }

    VMState state() const {
        return state_;
    }

    void setState(VMState state) {
        state_ = state;
    }

    CPUAllocation& cpu() {
        return cpu_;
    }

    MemoryAllocation& memory() {
        return memory_;
    }

    const CPUAllocation& cpu() const {
        return cpu_;
    }

    const MemoryAllocation& memory() const {
        return memory_;
    }

    void addDisk(VirtualDisk disk) {
        if (findDisk(disk.name()).has_value()) {
            throw std::invalid_argument(
                "A VM cannot contain duplicate disk names."
            );
        }

        disks_.push_back(std::move(disk));
    }

    std::optional<std::reference_wrapper<VirtualDisk>>
    findDisk(const std::string& name) {
        for (auto& disk : disks_) {
            if (disk.name() == name) {
                return disk;
            }
        }

        return std::nullopt;
    }

    const std::vector<VirtualDisk>& disks() const {
        return disks_;
    }

    double diskCapacityGB() const {
        double total = 0.0;

        for (const auto& disk : disks_) {
            total += disk.capacityGB();
        }

        return total;
    }

    double diskAllocationGB() const {
        double total = 0.0;

        for (const auto& disk : disks_) {
            total += disk.allocatedGB();
        }

        return total;
    }

    void addSnapshot(Snapshot snapshot) {
        if (snapshots_.count(snapshot.id) != 0) {
            throw std::invalid_argument(
                "Snapshot identifier already exists."
            );
        }

        snapshots_.emplace(snapshot.id, std::move(snapshot));
    }

    Snapshot& snapshot(const std::string& id) {
        auto iterator = snapshots_.find(id);

        if (iterator == snapshots_.end()) {
            throw std::out_of_range(
                "Snapshot does not exist."
            );
        }

        return iterator->second;
    }

    void removeSnapshot(const std::string& id) {
        if (snapshots_.erase(id) == 0) {
            throw std::out_of_range(
                "Snapshot does not exist."
            );
        }
    }

    const std::map<std::string, Snapshot>& snapshots() const {
        return snapshots_;
    }

private:
    std::string name_;
    CPUAllocation cpu_;
    MemoryAllocation memory_;
    VMState state_{VMState::Defined};
    std::vector<VirtualDisk> disks_;
    std::map<std::string, Snapshot> snapshots_;
};

class Hypervisor {
public:
    Hypervisor(
        std::string name,
        unsigned hostVcpus,
        unsigned hostMemoryMB,
        double storageCapacityGB
    )
        : name_(std::move(name)),
          hostVcpus_(hostVcpus),
          hostMemoryMB_(hostMemoryMB),
          storageCapacityGB_(storageCapacityGB) {
        if (hostVcpus_ == 0) {
            throw std::invalid_argument(
                "Host must expose at least one vCPU."
            );
        }

        if (hostMemoryMB_ < 512) {
            throw std::invalid_argument(
                "Host memory is too small."
            );
        }

        if (storageCapacityGB_ <= 0.0) {
            throw std::invalid_argument(
                "Host storage must be positive."
            );
        }
    }

    VirtualMachine& vm(const std::string& name) {
        auto iterator = vms_.find(name);

        if (iterator == vms_.end()) {
            throw std::out_of_range(
                "VM does not exist: " + name
            );
        }

        return *iterator->second;
    }

    void createVM(std::unique_ptr<VirtualMachine> machine) {
        const std::string machineName = machine->name();

        if (vms_.count(machineName) != 0) {
            throw std::invalid_argument(
                "VM name already exists."
            );
        }

        validateVM(*machine);

        const unsigned requiredMemory =
            usedMemoryReservation() +
            machine->memory().reservationMB;

        if (requiredMemory > hostMemoryMB_) {
            throw std::runtime_error(
                "Host memory reservation capacity exceeded."
            );
        }

        const double requiredStorage =
            usedStorage() +
            machine->diskAllocationGB();

        if (requiredStorage > storageCapacityGB_) {
            throw std::runtime_error(
                "Host storage capacity exceeded."
            );
        }

        machine->setState(VMState::Stopped);
        vms_.emplace(
            machineName,
            std::move(machine)
        );
    }

    void start(const std::string& name) {
        VirtualMachine& machine = vm(name);

        if (
            machine.state() != VMState::Stopped &&
            machine.state() != VMState::Paused
        ) {
            throw std::runtime_error(
                "VM cannot start from state " +
                toString(machine.state())
            );
        }

        if (
            machine.memory().reservationMB >
            hostMemoryMB_
        ) {
            throw std::runtime_error(
                "VM memory reservation exceeds host memory."
            );
        }

        machine.setState(VMState::Running);
    }

    void stop(const std::string& name) {
        VirtualMachine& machine = vm(name);

        if (machine.state() == VMState::Stopped) {
            return;
        }

        if (
            machine.state() != VMState::Running &&
            machine.state() != VMState::Paused &&
            machine.state() != VMState::Suspended
        ) {
            throw std::runtime_error(
                "VM cannot stop from state " +
                toString(machine.state())
            );
        }

        machine.setState(VMState::Stopped);
    }

    void pause(const std::string& name) {
        VirtualMachine& machine = vm(name);

        if (machine.state() != VMState::Running) {
            throw std::runtime_error(
                "Only a running VM can be paused."
            );
        }

        machine.setState(VMState::Paused);
    }

    void resume(const std::string& name) {
        VirtualMachine& machine = vm(name);

        if (machine.state() != VMState::Paused) {
            throw std::runtime_error(
                "Only a paused VM can be resumed."
            );
        }

        machine.setState(VMState::Running);
    }

    void suspend(const std::string& name) {
        VirtualMachine& machine = vm(name);

        if (machine.state() != VMState::Running) {
            throw std::runtime_error(
                "Only a running VM can be suspended."
            );
        }

        machine.setState(VMState::Suspended);
    }

    void resizeMemory(
        const std::string& name,
        unsigned memoryMB,
        unsigned reservationMB,
        unsigned limitMB
    ) {
        VirtualMachine& machine = vm(name);

        MemoryAllocation next{
            memoryMB,
            reservationMB,
            limitMB,
            machine.memory().ballooning
        };

        next.validate(hostMemoryMB_);

        const unsigned available =
            hostMemoryMB_ -
            usedMemoryReservation(name);

        if (reservationMB > available) {
            throw std::runtime_error(
                "Insufficient unreserved host memory."
            );
        }

        machine.memory() = next;
    }

    void expandDisk(
        const std::string& vmName,
        const std::string& diskName,
        double newCapacityGB
    ) {
        VirtualMachine& machine = vm(vmName);

        auto diskReference = machine.findDisk(diskName);

        if (!diskReference.has_value()) {
            throw std::out_of_range(
                "Disk does not exist."
            );
        }

        VirtualDisk& disk = diskReference->get();

        if (newCapacityGB <= disk.capacityGB()) {
            throw std::invalid_argument(
                "Disk expansion must increase capacity."
            );
        }

        const double additionalPhysicalStorage =
            disk.thinProvisioned()
                ? 0.0
                : newCapacityGB - disk.capacityGB();

        if (
            usedStorage() +
            additionalPhysicalStorage >
            storageCapacityGB_
        ) {
            throw std::runtime_error(
                "Host storage cannot support the expansion."
            );
        }

        disk.expand(newCapacityGB);
    }

    void writeDisk(
        const std::string& vmName,
        const std::string& diskName,
        double amountGB
    ) {
        VirtualMachine& machine = vm(vmName);

        if (machine.state() != VMState::Running) {
            throw std::runtime_error(
                "Disk I/O requires a running VM."
            );
        }

        auto diskReference = machine.findDisk(diskName);

        if (!diskReference.has_value()) {
            throw std::out_of_range(
                "Disk does not exist."
            );
        }

        VirtualDisk& disk = diskReference->get();

        if (
            disk.thinProvisioned() &&
            usedStorage() + amountGB >
            storageCapacityGB_
        ) {
            throw std::runtime_error(
                "Thin-provisioned backing storage is full."
            );
        }

        disk.write(amountGB);
    }

    void createSnapshot(
        const std::string& vmName,
        const std::string& id,
        const std::string& description
    ) {
        VirtualMachine& machine = vm(vmName);

        Snapshot snapshot{
            id,
            description,
            machine.state(),
            machine.cpu(),
            machine.memory(),
            {}
        };

        for (const auto& disk : machine.disks()) {
            snapshot.diskAllocations.emplace(
                disk.name(),
                disk.allocatedGB()
            );
        }

        machine.addSnapshot(std::move(snapshot));
    }

    void revertSnapshot(
        const std::string& vmName,
        const std::string& snapshotId
    ) {
        VirtualMachine& machine = vm(vmName);

        if (machine.state() == VMState::Running) {
            throw std::runtime_error(
                "Stop the VM before snapshot restoration."
            );
        }

        Snapshot& snapshot =
            machine.snapshot(snapshotId);

        machine.cpu() = snapshot.cpu;
        machine.memory() = snapshot.memory;

        for (const auto& [diskName, allocation] :
             snapshot.diskAllocations) {
            auto diskReference =
                machine.findDisk(diskName);

            if (!diskReference.has_value()) {
                throw std::runtime_error(
                    "Snapshot references a missing disk."
                );
            }

            diskReference->get().restoreAllocation(
                allocation
            );
        }

        machine.setState(VMState::Stopped);
    }

    std::map<std::string, double>
    allocateCpuTime(double durationSeconds) const {
        if (durationSeconds < 0.0) {
            throw std::invalid_argument(
                "Duration cannot be negative."
            );
        }

        unsigned totalShares = 0;
        unsigned runningVcpus = 0;

        for (const auto& [name, machine] : vms_) {
            if (machine->state() == VMState::Running) {
                totalShares += machine->cpu().cpuShares;
                runningVcpus += machine->cpu().vcpus;
            }
        }

        std::map<std::string, double> result;

        if (totalShares == 0) {
            return result;
        }

        const double hostCpuSeconds =
            static_cast<double>(hostVcpus_) *
            durationSeconds;

        for (const auto& [name, machine] : vms_) {
            if (machine->state() != VMState::Running) {
                continue;
            }

            const double weightedShare =
                hostCpuSeconds *
                (
                    static_cast<double>(
                        machine->cpu().cpuShares
                    ) /
                    static_cast<double>(totalShares)
                );

            const double configuredLimit =
                static_cast<double>(
                    machine->cpu().vcpus
                ) *
                durationSeconds *
                (
                    machine->cpu().cpuLimitPercent /
                    100.0
                );

            result[name] =
                std::min(
                    weightedShare,
                    configuredLimit
                );
        }

        return result;
    }

    void printInventory() const {
        std::cout
            << "\n"
            << std::left
            << std::setw(18) << "VM"
            << std::setw(12) << "State"
            << std::setw(8) << "vCPU"
            << std::setw(12) << "Memory"
            << std::setw(14) << "Disk Used"
            << std::setw(12) << "Snapshots"
            << "\n";

        std::cout << std::string(76, '-') << "\n";

        for (const auto& [name, machine] : vms_) {
            std::cout
                << std::left
                << std::setw(18) << machine->name()
                << std::setw(12) << toString(machine->state())
                << std::setw(8) << machine->cpu().vcpus
                << std::setw(12)
                << std::to_string(
                    machine->memory().memoryMB
                )
                << std::setw(14)
                << machine->diskAllocationGB()
                << std::setw(12)
                << machine->snapshots().size()
                << "\n";
        }
    }

private:
    void validateVM(
        const VirtualMachine& machine
    ) const {
        machine.cpu().validate(hostVcpus_);
        machine.memory().validate(hostMemoryMB_);

        if (machine.disks().empty()) {
            throw std::invalid_argument(
                "VM must contain at least one disk."
            );
        }
    }

    unsigned usedMemoryReservation(
        const std::string& excludeName = ""
    ) const {
        unsigned total = 0;

        for (const auto& [name, machine] : vms_) {
            if (name == excludeName) {
                continue;
            }

            if (machine->state() != VMState::Error) {
                total += machine->memory().reservationMB;
            }
        }

        return total;
    }

    double usedStorage(
        const std::string& excludeName = ""
    ) const {
        double total = 0.0;

        for (const auto& [name, machine] : vms_) {
            if (name == excludeName) {
                continue;
            }

            total += machine->diskAllocationGB();
        }

        return total;
    }

    std::string name_;
    unsigned hostVcpus_;
    unsigned hostMemoryMB_;
    double storageCapacityGB_;
    std::map<
        std::string,
        std::unique_ptr<VirtualMachine>
    > vms_;
};

void printHeading(const std::string& title) {
    std::cout
        << "\n"
        << std::string(78, '=')
        << "\n"
        << title
        << "\n"
        << std::string(78, '=')
        << "\n";
}

std::unique_ptr<VirtualMachine> makeDatabaseVM() {
    auto machine =
        std::make_unique<VirtualMachine>(
            "database",
            CPUAllocation{
                4,
                90.0,
                2048,
                {{0, 0}, {1, 1}}
            },
            MemoryAllocation{
                6144,
                4096,
                8192,
                false
            }
        );

    machine->addDisk(
        VirtualDisk(
            "os",
            50.0,
            25.0,
            DiskFormat::QCow2,
            true
        )
    );

    machine->addDisk(
        VirtualDisk(
            "database",
            200.0,
            100.0,
            DiskFormat::QCow2,
            true
        )
    );

    return machine;
}

std::unique_ptr<VirtualMachine> makeWorkerVM() {
    auto machine =
        std::make_unique<VirtualMachine>(
            "ci-worker",
            CPUAllocation{
                2,
                100.0,
                1024,
                {}
            },
            MemoryAllocation{
                4096,
                2048,
                4096,
                true
            }
        );

    machine->addDisk(
        VirtualDisk(
            "os",
            60.0,
            30.0,
            DiskFormat::Raw,
            false
        )
    );

    return machine;
}

void demonstrateLifecycle(Hypervisor& host) {
    printHeading("VM lifecycle");

    host.start("database");
    std::cout
        << "After start: "
        << toString(host.vm("database").state())
        << "\n";

    host.pause("database");
    std::cout
        << "After pause: "
        << toString(host.vm("database").state())
        << "\n";

    host.resume("database");
    std::cout
        << "After resume: "
        << toString(host.vm("database").state())
        << "\n";

    host.suspend("database");
    std::cout
        << "After suspend: "
        << toString(host.vm("database").state())
        << "\n";

    host.stop("database");
    std::cout
        << "After stop: "
        << toString(host.vm("database").state())
        << "\n";

    try {
        host.resume("database");
    } catch (const std::exception& error) {
        std::cout
            << "Expected lifecycle failure: "
            << error.what()
            << "\n";
    }
}

void demonstrateCPU(Hypervisor& host) {
    printHeading("CPU allocation and scheduling");

    host.start("database");
    host.start("ci-worker");

    const auto allocation =
        host.allocateCpuTime(20.0);

    for (const auto& [name, cpuSeconds] :
         allocation) {
        std::cout
            << name
            << ": "
            << std::fixed
            << std::setprecision(2)
            << cpuSeconds
            << " CPU-seconds\n";
    }

    host.stop("database");
    host.stop("ci-worker");
}

void demonstrateMemory(Hypervisor& host) {
    printHeading("Memory allocation");

    host.resizeMemory(
        "database",
        7168,
        4096,
        8192
    );

    const auto& memory =
        host.vm("database").memory();

    std::cout
        << "Database memory="
        << memory.memoryMB
        << " MB, reservation="
        << memory.reservationMB
        << " MB, limit="
        << memory.limitMB
        << " MB\n";

    try {
        host.resizeMemory(
            "database",
            20000,
            19000,
            22000
        );
    } catch (const std::exception& error) {
        std::cout
            << "Expected memory failure: "
            << error.what()
            << "\n";
    }
}

void demonstrateDisks(Hypervisor& host) {
    printHeading("Virtual disk management");

    host.expandDisk(
        "database",
        "database",
        250.0
    );

    host.start("database");

    host.writeDisk(
        "database",
        "database",
        8.0
    );

    auto databaseDisk =
        host.vm("database")
            .findDisk("database");

    if (databaseDisk.has_value()) {
        std::cout
            << "Database disk after writes: "
            << databaseDisk->get().allocatedGB()
            << " GB allocated out of "
            << databaseDisk->get().capacityGB()
            << " GB capacity\n";
    }

    host.stop("database");
}

void demonstrateSnapshots(Hypervisor& host) {
    printHeading("Snapshot capture and restoration");

    host.createSnapshot(
        "database",
        "before-index-migration",
        "Known-good state before database index migration"
    );

    auto disk =
        host.vm("database")
            .findDisk("database");

    if (!disk.has_value()) {
        throw std::runtime_error(
            "Database disk unexpectedly missing."
        );
    }

    const double before =
        disk->get().allocatedGB();

    disk->get().write(12.0);

    std::cout
        << "Allocated before simulated migration: "
        << before
        << " GB\n"
        << "Allocated after simulated migration: "
        << disk->get().allocatedGB()
        << " GB\n";

    host.revertSnapshot(
        "database",
        "before-index-migration"
    );

    std::cout
        << "Allocated after snapshot restoration: "
        << disk->get().allocatedGB()
        << " GB\n";

    host.vm("database")
        .removeSnapshot("before-index-migration");
}

void demonstrateValidation(Hypervisor& host) {
    printHeading("Validation and failure handling");

    try {
        auto oversized =
            std::make_unique<VirtualMachine>(
                "oversized",
                CPUAllocation{
                    16,
                    100.0,
                    1024,
                    {}
                },
                MemoryAllocation{
                    1024,
                    512,
                    2048,
                    false
                }
            );

        oversized->addDisk(
            VirtualDisk(
                "os",
                20.0,
                5.0,
                DiskFormat::QCow2,
                true
            )
        );

        host.createVM(std::move(oversized));
    } catch (const std::exception& error) {
        std::cout
            << "Expected resource validation failure: "
            << error.what()
            << "\n";
    }

    try {
        host.vm("database")
            .findDisk("missing")
            .value()
            .get()
            .write(1.0);
    } catch (const std::exception& error) {
        std::cout
            << "Expected disk lookup failure: "
            << error.what()
            << "\n";
    }
}

int main() {
    try {
        Hypervisor host(
            "private-cloud-01",
            8,
            16384,
            500.0
        );

        host.createVM(makeDatabaseVM());
        host.createVM(makeWorkerVM());

        demonstrateLifecycle(host);
        demonstrateCPU(host);
        demonstrateMemory(host);
        demonstrateDisks(host);
        demonstrateSnapshots(host);
        demonstrateValidation(host);

        printHeading("Final host inventory");
        host.printInventory();

    } catch (const std::exception& error) {
        std::cerr
            << "Fatal control-plane error: "
            << error.what()
            << "\n";

        return 1;
    }

    return 0;
}
