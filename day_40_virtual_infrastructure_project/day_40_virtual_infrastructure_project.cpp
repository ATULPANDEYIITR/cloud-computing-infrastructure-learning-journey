#include <algorithm>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

/*
 * Virtual Infrastructure Project: Multi-tenant hosting case study.
 *
 * Scenario:
 * An enterprise platform provisions isolated application environments.
 * Each environment receives a compute quota, an IP subnet, a VLAN, and
 * storage capacity. Provisioning is rejected when resource, addressing,
 * isolation, or lifecycle constraints are violated.
 *
 * Build:
 *   g++ -std=c++17 -Wall -Wextra -pedantic virtual_infrastructure.cpp -o infrastructure
 *
 * Run:
 *   ./infrastructure
 *
 * This program is a control-plane model, not a hypervisor implementation.
 */

namespace infrastructure {

enum class VmState {
    Stopped,
    Running,
    Suspended,
    Terminated
};

enum class Role {
    Viewer,
    Operator,
    Administrator
};

std::string toString(VmState state) {
    switch (state) {
        case VmState::Stopped: return "stopped";
        case VmState::Running: return "running";
        case VmState::Suspended: return "suspended";
        case VmState::Terminated: return "terminated";
    }
    throw std::logic_error("Unknown VM state");
}

class InfrastructureError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class CapacityError : public InfrastructureError {
public:
    using InfrastructureError::InfrastructureError;
};

class AuthorizationError : public InfrastructureError {
public:
    using InfrastructureError::InfrastructureError;
};

class InvalidTransition : public InfrastructureError {
public:
    using InfrastructureError::InfrastructureError;
};

struct Quota {
    int maxVms;
    int maxVcpus;
    std::int64_t maxMemoryMB;
    std::int64_t maxStorageGB;
};

struct VmSpec {
    std::string id;
    std::string name;
    std::string image;
    int vcpus;
    std::int64_t memoryMB;
    std::int64_t rootDiskGB;
};

struct VirtualMachine {
    VmSpec spec;
    std::string environmentId;
    std::string networkId;
    std::string ipAddress;
    VmState state = VmState::Stopped;
    std::set<std::string> attachedVolumes;
};

struct Subnet {
    std::uint32_t network;
    std::uint32_t broadcast;
    unsigned prefix;

    static std::uint32_t parseAddress(const std::string& text) {
        std::istringstream input(text);
        std::uint32_t result = 0;

        for (int i = 0; i < 4; ++i) {
            unsigned octet = 0;
            char delimiter = '\0';

            if (!(input >> octet) || octet > 255) {
                throw InfrastructureError("Invalid IPv4 address: " + text);
            }
            result = (result << 8U) | octet;

            if (i < 3) {
                if (!(input >> delimiter) || delimiter != '.') {
                    throw InfrastructureError("Invalid IPv4 address: " + text);
                }
            }
        }

        if (input.peek() != std::char_traits<char>::eof()) {
            throw InfrastructureError("Unexpected IPv4 address characters");
        }
        return result;
    }

    static Subnet parse(const std::string& cidr) {
        const auto slash = cidr.find('/');
        if (slash == std::string::npos) {
            throw InfrastructureError("CIDR prefix is required");
        }

        const auto address = parseAddress(cidr.substr(0, slash));
        const auto prefixText = cidr.substr(slash + 1);

        std::size_t consumed = 0;
        unsigned prefix;
        try {
            prefix = static_cast<unsigned>(
                std::stoul(prefixText, &consumed)
            );
        } catch (...) {
            throw InfrastructureError("Invalid CIDR prefix");
        }

        if (consumed != prefixText.size() || prefix < 16 || prefix > 30) {
            throw InfrastructureError("Supported IPv4 prefixes are /16 to /30");
        }

        const std::uint32_t mask =
            0xFFFFFFFFU << (32U - prefix);
        const std::uint32_t network = address & mask;

        if (address != network) {
            throw InfrastructureError("CIDR must identify a subnet boundary");
        }

        const std::uint32_t size = 1U << (32U - prefix);
        return {network, static_cast<std::uint32_t>(network + size - 1), prefix};
    }

    bool overlaps(const Subnet& other) const {
        return network <= other.broadcast && other.network <= broadcast;
    }

    bool containsUsable(std::uint32_t address) const {
        return address > network && address < broadcast;
    }

    static std::string formatAddress(std::uint32_t address) {
        std::ostringstream output;
        output << ((address >> 24U) & 255U) << '.'
               << ((address >> 16U) & 255U) << '.'
               << ((address >> 8U) & 255U) << '.'
               << (address & 255U);
        return output.str();
    }
};

struct Network {
    std::string id;
    std::string environmentId;
    Subnet subnet;
    std::uint32_t gateway;
    int vlanId;
    std::map<std::string, std::uint32_t> allocations;
};

struct Volume {
    std::string id;
    std::string environmentId;
    std::string poolId;
    std::int64_t sizeGB;
    std::optional<std::string> attachedVm;
    bool encrypted = true;
};

struct StoragePool {
    std::string id;
    std::string environmentId;
    std::int64_t capacityGB;
    std::map<std::string, std::int64_t> volumes;

    std::int64_t usedGB() const {
        std::int64_t total = 0;
        for (const auto& [id, size] : volumes) {
            (void)id;
            total += size;
        }
        return total;
    }

    std::int64_t availableGB() const {
        return capacityGB - usedGB();
    }
};

struct Environment {
    std::string id;
    std::string name;
    Quota quota;
    std::set<std::string> vmIds;
    std::set<std::string> networkIds;
    std::set<std::string> poolIds;
};

struct User {
    std::string username;
    Role role;
    std::set<std::string> environmentIds;
    bool enabled = true;
};

struct AuditRecord {
    std::string actor;
    std::string action;
    std::string resource;
    std::string outcome;
};

class InfrastructureManager {
private:
    std::map<std::string, Environment> environments;
    std::map<std::string, Network> networks;
    std::map<std::string, StoragePool> pools;
    std::map<std::string, VirtualMachine> vms;
    std::map<std::string, Volume> volumes;
    std::map<std::string, User> users;
    std::vector<AuditRecord> audit;

    void record(
        const std::string& actor,
        const std::string& action,
        const std::string& resource,
        const std::string& outcome
    ) {
        audit.push_back({actor, action, resource, outcome});
    }

    const Environment& activeEnvironment(const std::string& id) const {
        auto found = environments.find(id);
        if (found == environments.end()) {
            throw InfrastructureError("Environment does not exist: " + id);
        }
        return found->second;
    }

    Environment& activeEnvironment(const std::string& id) {
        auto found = environments.find(id);
        if (found == environments.end()) {
            throw InfrastructureError("Environment does not exist: " + id);
        }
        return found->second;
    }

    void authorize(
        const std::string& actor,
        const std::string& permission,
        const std::string& environmentId = ""
    ) const {
        const auto found = users.find(actor);
        if (found == users.end() || !found->second.enabled) {
            throw AuthorizationError("Unknown or disabled user");
        }

        const Role role = found->second.role;
        bool permitted = permission == "read";
        if (role == Role::Operator || role == Role::Administrator) {
            permitted = true;
        }
        if (permission == "admin" && role != Role::Administrator) {
            permitted = false;
        }
        if (!permitted) {
            throw AuthorizationError("Insufficient role permissions");
        }

        if (!environmentId.empty() &&
            role != Role::Administrator &&
            !found->second.environmentIds.count(environmentId)) {
            throw AuthorizationError("Environment access denied");
        }
    }

    std::string allocateAddress(Network& network, const std::string& vmId) {
        auto existing = network.allocations.find(vmId);
        if (existing != network.allocations.end()) {
            return Subnet::formatAddress(existing->second);
        }

        for (std::uint32_t address = network.subnet.network + 1;
             address < network.subnet.broadcast;
             ++address) {
            if (address == network.gateway) continue;

            const bool used = std::any_of(
                network.allocations.begin(),
                network.allocations.end(),
                [address](const auto& allocation) {
                    return allocation.second == address;
                }
            );

            if (!used) {
                network.allocations.emplace(vmId, address);
                return Subnet::formatAddress(address);
            }
        }

        throw CapacityError("Network has no free IP addresses");
    }

    void releaseAddress(const std::string& networkId, const std::string& vmId) {
        auto found = networks.find(networkId);
        if (found != networks.end()) {
            found->second.allocations.erase(vmId);
        }
    }

public:
    void addUser(const std::string& username, Role role) {
        if (users.count(username)) {
            throw InfrastructureError("User already exists");
        }
        users.emplace(username, User{username, role, {}, true});
    }

    void createEnvironment(
        const std::string& actor,
        const std::string& id,
        const std::string& name,
        const Quota& quota
    ) {
        authorize(actor, "admin");
        if (environments.count(id)) {
            throw InfrastructureError("Environment already exists");
        }
        if (quota.maxVms < 1 || quota.maxVcpus < 1 ||
            quota.maxMemoryMB < 128 || quota.maxStorageGB < 1) {
            throw InfrastructureError("Invalid environment quotas");
        }

        environments.emplace(id, Environment{id, name, quota, {}, {}, {}});
        users.at(actor).environmentIds.insert(id);
        record(actor, "create_environment", id, "success");
    }

    void grantAccess(
        const std::string& actor,
        const std::string& username,
        const std::string& environmentId
    ) {
        authorize(actor, "admin");
        if (!users.count(username)) {
            throw InfrastructureError("User does not exist");
        }
        activeEnvironment(environmentId);
        users.at(username).environmentIds.insert(environmentId);
        record(actor, "grant_access", environmentId, "success");
    }

    void createNetwork(
        const std::string& actor,
        const std::string& environmentId,
        const std::string& id,
        const std::string& cidr,
        const std::string& gateway,
        int vlanId
    ) {
        authorize(actor, "admin", environmentId);
        auto& environment = activeEnvironment(environmentId);
        if (networks.count(id)) {
            throw InfrastructureError("Network already exists");
        }
        if (vlanId < 1 || vlanId > 4094) {
            throw InfrastructureError("Invalid VLAN ID");
        }

        const Subnet subnet = Subnet::parse(cidr);
        const std::uint32_t gatewayAddress = Subnet::parseAddress(gateway);

        if (!subnet.containsUsable(gatewayAddress)) {
            throw InfrastructureError("Gateway is outside the usable subnet range");
        }

        for (const auto& [networkId, existing] : networks) {
            (void)networkId;
            if (subnet.overlaps(existing.subnet)) {
                throw InfrastructureError("Overlapping subnets are prohibited");
            }
        }

        networks.emplace(
            id, Network{id, environmentId, subnet, gatewayAddress, vlanId, {}}
        );
        environment.networkIds.insert(id);
        record(actor, "create_network", id, "success");
    }

    void createStoragePool(
        const std::string& actor,
        const std::string& environmentId,
        const std::string& id,
        std::int64_t capacityGB
    ) {
        authorize(actor, "admin", environmentId);
        auto& environment = activeEnvironment(environmentId);

        if (pools.count(id)) {
            throw InfrastructureError("Storage pool already exists");
        }
        if (capacityGB < 1) {
            throw InfrastructureError("Storage capacity must be positive");
        }

        std::int64_t allocatedCapacity = 0;
        for (const auto& poolId : environment.poolIds) {
            allocatedCapacity += pools.at(poolId).capacityGB;
        }
        if (allocatedCapacity + capacityGB > environment.quota.maxStorageGB) {
            throw CapacityError("Storage pool capacity exceeds environment quota");
        }

        pools.emplace(id, StoragePool{id, environmentId, capacityGB, {}});
        environment.poolIds.insert(id);
        record(actor, "create_storage_pool", id, "success");
    }

    void createVM(
        const std::string& actor,
        const std::string& environmentId,
        const VmSpec& spec,
        const std::string& networkId
    ) {
        authorize(actor, "operate", environmentId);
        auto& environment = activeEnvironment(environmentId);

        if (vms.count(spec.id)) {
            throw InfrastructureError("VM ID already exists");
        }
        if (spec.vcpus < 1 || spec.vcpus > 128 ||
            spec.memoryMB < 128 || spec.rootDiskGB < 1 ||
            spec.image.empty()) {
            throw InfrastructureError("Invalid VM specification");
        }

        auto network = networks.find(networkId);
        if (network == networks.end() ||
            network->second.environmentId != environmentId) {
            throw InfrastructureError("Network isolation policy violation");
        }

        int allocatedVcpus = 0;
        std::int64_t allocatedMemory = 0;
        int activeCount = 0;

        for (const auto& vmId : environment.vmIds) {
            const auto& vm = vms.at(vmId);
            if (vm.state == VmState::Terminated) continue;
            ++activeCount;
            allocatedVcpus += vm.spec.vcpus;
            allocatedMemory += vm.spec.memoryMB;
        }

        if (activeCount + 1 > environment.quota.maxVms ||
            allocatedVcpus + spec.vcpus > environment.quota.maxVcpus ||
            allocatedMemory + spec.memoryMB > environment.quota.maxMemoryMB) {
            throw CapacityError("Compute quota exceeded");
        }

        const std::string ip = allocateAddress(network->second, spec.id);
        try {
            VirtualMachine vm{spec, environmentId, networkId, ip};
            vms.emplace(spec.id, std::move(vm));
            environment.vmIds.insert(spec.id);
        } catch (...) {
            releaseAddress(networkId, spec.id);
            throw;
        }

        record(actor, "create_vm", spec.id, "success");
    }

    void createVolume(
        const std::string& actor,
        const std::string& environmentId,
        const std::string& id,
        const std::string& poolId,
        std::int64_t sizeGB
    ) {
        authorize(actor, "operate", environmentId);
        auto& environment = activeEnvironment(environmentId);
        auto pool = pools.find(poolId);

        if (volumes.count(id)) {
            throw InfrastructureError("Volume already exists");
        }
        if (pool == pools.end() ||
            pool->second.environmentId != environmentId) {
            throw InfrastructureError("Storage isolation policy violation");
        }
        if (sizeGB < 1 || sizeGB > pool->second.availableGB()) {
            throw CapacityError("Storage pool cannot satisfy volume request");
        }

        std::int64_t usedAcrossPools = 0;
        for (const auto& environmentPoolId : environment.poolIds) {
            usedAcrossPools += pools.at(environmentPoolId).usedGB();
        }
        if (usedAcrossPools + sizeGB > environment.quota.maxStorageGB) {
            throw CapacityError("Environment storage quota exceeded");
        }

        pool->second.volumes.emplace(id, sizeGB);
        volumes.emplace(
            id, Volume{id, environmentId, poolId, sizeGB, std::nullopt, true}
        );
        record(actor, "create_volume", id, "success");
    }

    void attachVolume(
        const std::string& actor,
        const std::string& vmId,
        const std::string& volumeId
    ) {
        auto vm = vms.find(vmId);
        auto volume = volumes.find(volumeId);
        if (vm == vms.end() || volume == volumes.end()) {
            throw InfrastructureError("VM or volume does not exist");
        }

        authorize(actor, "operate", vm->second.environmentId);

        if (vm->second.state == VmState::Terminated ||
            vm->second.environmentId != volume->second.environmentId ||
            volume->second.attachedVm.has_value()) {
            throw InfrastructureError("Volume attachment violates policy");
        }

        volume->second.attachedVm = vmId;
        vm->second.attachedVolumes.insert(volumeId);
        record(actor, "attach_volume", volumeId, "success");
    }

    void changeState(
        const std::string& actor,
        const std::string& vmId,
        const std::string& action
    ) {
        auto found = vms.find(vmId);
        if (found == vms.end()) {
            throw InfrastructureError("VM does not exist");
        }

        auto& vm = found->second;
        authorize(actor, "operate", vm.environmentId);

        if (action == "start" &&
            (vm.state == VmState::Stopped || vm.state == VmState::Suspended)) {
            vm.state = VmState::Running;
        } else if (action == "stop" && vm.state == VmState::Running) {
            vm.state = VmState::Stopped;
        } else if (action == "suspend" && vm.state == VmState::Running) {
            vm.state = VmState::Suspended;
        } else if (action == "terminate" && vm.state != VmState::Terminated) {
            vm.state = VmState::Terminated;
            releaseAddress(vm.networkId, vmId);

            // Preserve volumes, but detach them before the VM disappears.
            for (const auto& volumeId : vm.attachedVolumes) {
                volumes.at(volumeId).attachedVm.reset();
            }
            vm.attachedVolumes.clear();
            vm.ipAddress.clear();
        } else {
            throw InvalidTransition(
                "Cannot " + action + " VM from " + toString(vm.state)
            );
        }

        record(actor, action, vmId, "success");
    }

    void printInventory(const std::string& actor, const std::string& environmentId) const {
        authorize(actor, "read", environmentId);
        const auto& environment = activeEnvironment(environmentId);

        int activeVMs = 0;
        int runningVMs = 0;
        int vcpus = 0;
        std::int64_t memory = 0;

        std::cout << "\nEnvironment: " << environment.name
                  << " [" << environment.id << "]\n";

        for (const auto& vmId : environment.vmIds) {
            const auto& vm = vms.at(vmId);
            std::cout << "  " << std::left << std::setw(14) << vm.spec.id
                      << " state=" << std::setw(10) << toString(vm.state)
                      << " ip=" << std::setw(15)
                      << (vm.ipAddress.empty() ? "-" : vm.ipAddress)
                      << " vCPU=" << vm.spec.vcpus
                      << " memoryMiB=" << vm.spec.memoryMB << '\n';

            if (vm.state != VmState::Terminated) {
                ++activeVMs;
                vcpus += vm.spec.vcpus;
                memory += vm.spec.memoryMB;
                if (vm.state == VmState::Running) ++runningVMs;
            }
        }

        std::int64_t storageCapacity = 0;
        std::int64_t storageUsed = 0;
        for (const auto& poolId : environment.poolIds) {
            const auto& pool = pools.at(poolId);
            storageCapacity += pool.capacityGB;
            storageUsed += pool.usedGB();
        }

        std::cout << "  Active VMs: " << activeVMs
                  << ", running: " << runningVMs
                  << ", allocated vCPUs: " << vcpus
                  << ", allocated memory MiB: " << memory << '\n'
                  << "  Storage GiB: " << storageUsed
                  << " used / " << storageCapacity << " pool capacity\n";
    }

    bool invariantsHold() const {
        for (const auto& [poolId, pool] : pools) {
            (void)poolId;
            if (pool.usedGB() > pool.capacityGB) return false;
        }

        for (const auto& [vmId, vm] : vms) {
            if (vm.state != VmState::Terminated) {
                const auto& network = networks.at(vm.networkId);
                if (!network.allocations.count(vmId)) return false;
            }

            for (const auto& volumeId : vm.attachedVolumes) {
                auto volume = volumes.find(volumeId);
                if (volume == volumes.end() ||
                    !volume->second.attachedVm ||
                    *volume->second.attachedVm != vmId) {
                    return false;
                }
            }
        }

        for (const auto& [volumeId, volume] : volumes) {
            if (volume.attachedVm) {
                auto vm = vms.find(*volume.attachedVm);
                if (vm == vms.end() ||
                    !vm->second.attachedVolumes.count(volumeId)) {
                    return false;
                }
            }
        }
        return true;
    }

    std::size_t auditCount() const {
        return audit.size();
    }
};

}  // namespace infrastructure

int main() {
    using namespace infrastructure;

    try {
        InfrastructureManager manager;
        manager.addUser("administrator", Role::Administrator);
        manager.addUser("engineer", Role::Operator);
        manager.addUser("observer", Role::Viewer);

        manager.createEnvironment(
            "administrator", "production", "Production Application",
            Quota{6, 24, 32768, 300}
        );
        manager.grantAccess("administrator", "engineer", "production");
        manager.grantAccess("administrator", "observer", "production");

        manager.createNetwork(
            "administrator", "production", "app_net",
            "10.70.1.0/24", "10.70.1.1", 170
        );
        manager.createStoragePool(
            "administrator", "production", "app_pool", 200
        );

        manager.createVM(
            "engineer", "production",
            VmSpec{"api_vm", "API Service", "ubuntu-24.04", 4, 8192, 30},
            "app_net"
        );

        manager.createVM(
            "engineer", "production",
            VmSpec{"worker_vm", "Background Worker", "debian-12", 2, 4096, 20},
            "app_net"
        );

        manager.createVolume(
            "engineer", "production", "api_data", "app_pool", 40
        );
        manager.attachVolume("engineer", "api_vm", "api_data");
        manager.changeState("engineer", "api_vm", "start");
        manager.changeState("engineer", "worker_vm", "start");

        manager.printInventory("observer", "production");

        std::cout << "\nIsolation test: ";
        try {
            manager.createVM(
                "engineer", "production",
                VmSpec{"invalid_vm", "Invalid VM", "ubuntu-24.04", 1, 1024, 10},
                "missing_network"
            );
            std::cout << "FAILED: invalid network was accepted\n";
        } catch (const InfrastructureError& error) {
            std::cout << "rejected correctly (" << error.what() << ")\n";
        }

        std::cout << "Storage accounting and attachment invariants: "
                  << (manager.invariantsHold() ? "PASS" : "FAIL") << '\n';
        std::cout << "Audit records: " << manager.auditCount() << '\n';

        if (!manager.invariantsHold()) return 1;

        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Infrastructure failure: " << error.what() << '\n';
        return 1;
    }
}
