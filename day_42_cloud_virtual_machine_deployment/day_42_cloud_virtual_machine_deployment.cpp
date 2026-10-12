#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

enum class State { Pending, Running, Stopped, Failed, Terminated };

std::string toString(State state) {
    switch (state) {
        case State::Pending: return "pending";
        case State::Running: return "running";
        case State::Stopped: return "stopped";
        case State::Failed: return "failed";
        case State::Terminated: return "terminated";
    }
    throw std::logic_error("Unknown instance state");
}

struct Image {
    std::string id;
    std::string publisher;
    std::string version;
    std::string architecture;
    bool trusted;
    bool deprecated;
    int minimumDiskGiB;
};

struct MachineType {
    std::string name;
    std::string architecture;
    int vcpus;
    int memoryGiB;
    double hourlyCost;
};

struct SSHKey {
    std::string name;
    std::string fingerprint;
    bool publicKeyValidated;
};

struct InboundRule {
    std::string protocol;
    int fromPort;
    int toPort;
    std::string cidr;
    std::string description;
    bool publicInternet;
};

struct BranchlessPolicy {
    // A security group evaluates network reachability, not user identity.
    // SSH key possession and network access are independent controls.
    std::string name;
    std::vector<InboundRule> inbound;

    void validate() const {
        for (const auto& rule : inbound) {
            if (rule.protocol != "tcp" && rule.protocol != "udp") {
                throw std::invalid_argument("Unsupported network protocol");
            }
            if (rule.fromPort < 1 || rule.toPort > 65535 ||
                rule.fromPort > rule.toPort) {
                throw std::invalid_argument("Invalid security-group port range");
            }
            if (rule.cidr.empty() || rule.description.empty()) {
                throw std::invalid_argument("Network rule requires CIDR and description");
            }
            if (rule.protocol == "tcp" && rule.fromPort <= 22 &&
                rule.toPort >= 22 && rule.publicInternet) {
                throw std::invalid_argument("Publicly exposed SSH is prohibited");
            }
        }
    }

    bool permitsSSH(const std::string& sourceAddress) const {
        // The case study uses explicit approved-address entries instead of
        // implementing a partial and potentially misleading CIDR parser.
        for (const auto& rule : inbound) {
            if (rule.protocol == "tcp" &&
                rule.fromPort <= 22 && rule.toPort >= 22 &&
                rule.cidr == sourceAddress + "/32") {
                return true;
            }
        }
        return false;
    }
};

struct ProtectionPolicy {
    bool requireApprovedImage = true;
    bool requireSSHKey = true;
    bool requireSecurityGroup = true;
    bool requireEncryption = true;
    int minimumDiskGiB = 8;
    double maximumHourlyCost = 1.00;
};

struct Instance {
    std::string id;
    std::string name;
    std::string region;
    Image image;
    MachineType machine;
    SSHKey key;
    std::string securityGroupName;
    int diskGiB;
    bool encrypted;
    State state = State::Pending;
    std::optional<std::string> publicAddress;
    std::vector<std::string> audit;
};

class GovernanceEngine {
private:
    ProtectionPolicy policy_;
    std::map<std::string, Image> images_;
    std::map<std::string, MachineType> machines_;
    std::map<std::string, SSHKey> keys_;
    std::map<std::string, BranchlessPolicy> groups_;
    std::map<std::string, Instance> instances_;
    unsigned long nextId_ = 1;

    static bool transitionAllowed(State from, State to) {
        switch (from) {
            case State::Pending:
                return to == State::Running || to == State::Failed ||
                       to == State::Terminated;
            case State::Running:
                return to == State::Stopped || to == State::Failed ||
                       to == State::Terminated;
            case State::Stopped:
                return to == State::Running || to == State::Terminated;
            case State::Failed:
                return to == State::Terminated;
            case State::Terminated:
                return false;
        }
        return false;
    }

    void transition(Instance& vm, State target, const std::string& reason) {
        if (!transitionAllowed(vm.state, target)) {
            throw std::logic_error("Invalid lifecycle transition: " +
                toString(vm.state) + " -> " + toString(target));
        }
        const std::string before = toString(vm.state);
        vm.state = target;
        vm.audit.push_back(before + " -> " + toString(target) + ": " + reason);
    }

    void validateDeployment(
        const std::string& name,
        const std::string& region,
        const Image& image,
        const MachineType& machine,
        const SSHKey& key,
        const BranchlessPolicy& group,
        int diskGiB,
        bool encrypted
    ) const {
        if (name.empty() || region.empty()) {
            throw std::invalid_argument("Instance name and region are required");
        }
        if (!image.trusted || image.deprecated) {
            throw std::invalid_argument("Image is untrusted or deprecated");
        }
        if (image.architecture != machine.architecture) {
            throw std::invalid_argument("Image and machine architectures differ");
        }
        if (!key.publicKeyValidated || key.fingerprint.empty()) {
            throw std::invalid_argument("A validated SSH public key is required");
        }
        if (diskGiB < std::max(image.minimumDiskGiB, policy_.minimumDiskGiB)) {
            throw std::invalid_argument("Root disk violates the image or policy minimum");
        }
        if (machine.vcpus < 1 || machine.memoryGiB < 1 ||
            !std::isfinite(machine.hourlyCost) || machine.hourlyCost < 0 ||
            machine.hourlyCost > policy_.maximumHourlyCost) {
            throw std::invalid_argument("Machine capacity or cost violates policy");
        }
        if (policy_.requireEncryption && !encrypted) {
            throw std::invalid_argument("Encrypted root storage is required");
        }
        group.validate();

        for (const auto& pair : instances_) {
            const auto& existing = pair.second;
            if (existing.name == name && existing.state != State::Terminated) {
                throw std::invalid_argument("Active instance name already exists");
            }
        }
    }

public:
    explicit GovernanceEngine(ProtectionPolicy policy) : policy_(policy) {}

    void addImage(Image image) {
        if (images_.count(image.id)) {
            throw std::invalid_argument("Duplicate image identifier");
        }
        images_.emplace(image.id, std::move(image));
    }

    void addMachine(MachineType machine) {
        if (machines_.count(machine.name)) {
            throw std::invalid_argument("Duplicate machine type");
        }
        machines_.emplace(machine.name, std::move(machine));
    }

    void addKey(SSHKey key) {
        if (!key.publicKeyValidated || key.fingerprint.empty()) {
            throw std::invalid_argument("Invalid SSH key registration");
        }
        keys_.insert_or_assign(key.name, std::move(key));
    }

    void addSecurityGroup(BranchlessPolicy group) {
        group.validate();
        groups_.insert_or_assign(group.name, std::move(group));
    }

    Instance& deploy(
        const std::string& name,
        const std::string& region,
        const std::string& imageId,
        const std::string& machineName,
        const std::string& keyName,
        const std::string& groupName,
        int diskGiB,
        bool encrypted,
        bool bootSucceeds = true
    ) {
        const auto imageIt = images_.find(imageId);
        const auto machineIt = machines_.find(machineName);
        const auto keyIt = keys_.find(keyName);
        const auto groupIt = groups_.find(groupName);

        if (imageIt == images_.end() || machineIt == machines_.end() ||
            keyIt == keys_.end() || groupIt == groups_.end()) {
            throw std::invalid_argument("Deployment references an unknown resource");
        }

        validateDeployment(
            name, region, imageIt->second, machineIt->second, keyIt->second,
            groupIt->second, diskGiB, encrypted
        );

        Instance vm;
        vm.id = "vm-" + std::to_string(nextId_++);
        vm.name = name;
        vm.region = region;
        vm.image = imageIt->second;
        vm.machine = machineIt->second;
        vm.key = keyIt->second;
        vm.securityGroupName = groupName;
        vm.diskGiB = diskGiB;
        vm.encrypted = encrypted;
        vm.audit.push_back("Creation requested");

        auto result = instances_.emplace(vm.id, std::move(vm));
        Instance& created = result.first->second;

        if (bootSucceeds) {
            transition(created, State::Running, "image boot completed");
            // Reserved documentation IP only. No public cloud address is allocated.
            created.publicAddress = "192.0.2.40";
        } else {
            transition(created, State::Failed, "boot health check failed");
        }
        return created;
    }

    void stop(const std::string& id) {
        Instance& vm = get(id);
        transition(vm, State::Stopped, "operator requested stop");
        vm.publicAddress.reset();
    }

    void start(const std::string& id) {
        Instance& vm = get(id);
        transition(vm, State::Running, "operator requested start");
        vm.publicAddress = "192.0.2.41";
    }

    void terminate(const std::string& id) {
        Instance& vm = get(id);
        transition(vm, State::Terminated, "decommission approved");
        vm.publicAddress.reset();
    }

    Instance& get(const std::string& id) {
        auto it = instances_.find(id);
        if (it == instances_.end()) throw std::invalid_argument("Unknown instance");
        return it->second;
    }

    double monthlyComputeEstimate(const Instance& vm, double hours = 730.0) const {
        if (!std::isfinite(hours) || hours < 0) {
            throw std::invalid_argument("Billing hours must be non-negative");
        }
        if (vm.state != State::Running) return 0.0;
        return vm.machine.hourlyCost * hours;
    }

    void printReport(const Instance& vm) const {
        std::cout << "\nInstance " << vm.id << " (" << vm.name << ")\n"
                  << "  Region: " << vm.region << "\n"
                  << "  Image: " << vm.image.name << " " << vm.image.version << "\n"
                  << "  Machine: " << vm.machine.name << ", "
                  << vm.machine.vcpus << " vCPU, "
                  << vm.machine.memoryGiB << " GiB RAM\n"
                  << "  Root disk: " << vm.diskGiB << " GiB, encrypted="
                  << std::boolalpha << vm.encrypted << "\n"
                  << "  State: " << toString(vm.state) << "\n"
                  << "  Monthly compute estimate: $"
                  << std::fixed << std::setprecision(2)
                  << monthlyComputeEstimate(vm) << "\n"
                  << "  Audit:\n";
        for (const auto& entry : vm.audit) {
            std::cout << "    " << entry << '\n';
        }
    }
};

int main() {
    try {
        ProtectionPolicy policy;
        policy.minimumDiskGiB = 10;
        policy.maximumHourlyCost = 0.50;

        GovernanceEngine cloud(policy);

        cloud.addImage({
            "ubuntu-2404", "verified-publisher", "24.04", "x86_64",
            true, false, 8
        });
        cloud.addImage({
            "legacy-linux", "verified-publisher", "18.04", "x86_64",
            true, true, 8
        });

        cloud.addMachine({"general.small", "x86_64", 2, 4, 0.0416});
        cloud.addMachine({"compute.arm", "arm64", 4, 8, 0.08});
        cloud.addKey({"platform-admin", "SHA256:example-fingerprint", true});

        BranchlessPolicy group{
            "staging-web",
            {
                {"tcp", 22, 22, "203.0.113.8/32", "Approved administrator SSH", false},
                {"tcp", 443, 443, "0.0.0.0/0", "Public HTTPS", true}
            }
        };
        cloud.addSecurityGroup(group);

        Instance& vm = cloud.deploy(
            "api-staging", "us-east-1", "ubuntu-2404",
            "general.small", "platform-admin", "staging-web", 20, true
        );
        cloud.printReport(vm);

        cloud.stop(vm.id);
        std::cout << "\nStopped state: " << toString(vm.state)
                  << ", compute estimate: $" << cloud.monthlyComputeEstimate(vm) << '\n';

        cloud.start(vm.id);
        std::cout << "Restarted state: " << toString(vm.state) << '\n';

        cloud.terminate(vm.id);
        std::cout << "Terminated state: " << toString(vm.state) << '\n';

        try {
            cloud.start(vm.id);
        } catch (const std::exception& error) {
            std::cout << "Expected transition rejection: " << error.what() << '\n';
        }

        try {
            cloud.deploy(
                "insecure-api", "us-east-1", "ubuntu-2404",
                "general.small", "platform-admin", "staging-web", 20, false
            );
        } catch (const std::exception& error) {
            std::cout << "Expected storage-policy rejection: "
                      << error.what() << '\n';
        }

        try {
            cloud.deploy(
                "deprecated-api", "us-east-1", "legacy-linux",
                "general.small", "platform-admin", "staging-web", 20, true
            );
        } catch (const std::exception& error) {
            std::cout << "Expected image-policy rejection: "
                      << error.what() << '\n';
        }

        Instance& failed = cloud.deploy(
            "worker-failed", "us-east-1", "ubuntu-2404",
            "general.small", "platform-admin", "staging-web", 20, true, false
        );
        std::cout << "Provisioning failure state: " << toString(failed.state) << '\n';
    } catch (const std::exception& error) {
        std::cerr << "Governance engine error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
