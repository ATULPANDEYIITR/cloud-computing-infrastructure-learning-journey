#include <algorithm>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

/*
 * Repository-style infrastructure case study:
 *
 * A service platform must decide whether each workload should run inside a
 * container or a virtual machine. The engine evaluates resource requirements,
 * isolation needs, kernel requirements, startup sensitivity, and portability.
 *
 * Compile:
 *   g++ -std=c++17 -O2 containers_vs_vms.cpp -o containers_vs_vms
 */

enum class RuntimeKind {
    Container,
    VirtualMachine
};

enum class WorkloadKind {
    WebApi,
    Database,
    LegacyApplication,
    BatchProcessing,
    MultiService
};

string toString(RuntimeKind kind) {
    return kind == RuntimeKind::Container
        ? "Container"
        : "Virtual Machine";
}

string toString(WorkloadKind kind) {
    switch (kind) {
        case WorkloadKind::WebApi:
            return "Web API";
        case WorkloadKind::Database:
            return "Database";
        case WorkloadKind::LegacyApplication:
            return "Legacy Application";
        case WorkloadKind::BatchProcessing:
            return "Batch Processing";
        case WorkloadKind::MultiService:
            return "Multi-Service";
    }

    return "Unknown";
}

struct Workload {
    string name;
    WorkloadKind kind;
    double cpuCores;
    double memoryGb;
    double storageGb;
    bool requiresCustomKernel;
    bool untrustedCode;
    string architecture;
};

class Runtime {
protected:
    string name_;
    Workload workload_;
    double cpuLimit_;
    double memoryLimitGb_;
    double startupSeconds_;
    double cpuOverhead_;
    double memoryOverheadGb_;
    double isolationScore_;
    double portabilityScore_;

public:
    Runtime(
        string name,
        Workload workload,
        double cpuLimit,
        double memoryLimitGb,
        double startupSeconds,
        double cpuOverhead,
        double memoryOverheadGb,
        double isolationScore,
        double portabilityScore
    )
        : name_(move(name)),
          workload_(move(workload)),
          cpuLimit_(cpuLimit),
          memoryLimitGb_(memoryLimitGb),
          startupSeconds_(startupSeconds),
          cpuOverhead_(cpuOverhead),
          memoryOverheadGb_(memoryOverheadGb),
          isolationScore_(isolationScore),
          portabilityScore_(portabilityScore) {

        if (cpuLimit_ <= 0 || memoryLimitGb_ <= 0) {
            throw invalid_argument(
                "Runtime limits must be greater than zero"
            );
        }

        if (cpuLimit_ < workload_.cpuCores) {
            throw invalid_argument(
                "CPU limit is smaller than workload requirement"
            );
        }

        if (memoryLimitGb_ < workload_.memoryGb) {
            throw invalid_argument(
                "Memory limit is smaller than workload requirement"
            );
        }
    }

    virtual ~Runtime() = default;

    virtual RuntimeKind kind() const = 0;

    virtual bool supportsHost(
        const string& hostArchitecture
    ) const = 0;

    const string& name() const {
        return name_;
    }

    const Workload& workload() const {
        return workload_;
    }

    double cpuLimit() const {
        return cpuLimit_;
    }

    double memoryLimitGb() const {
        return memoryLimitGb_;
    }

    double storageGb() const {
        return workload_.storageGb;
    }

    double startupSeconds() const {
        return startupSeconds_;
    }

    double effectiveMemoryGb() const {
        return memoryLimitGb_ - memoryOverheadGb_;
    }

    double isolationScore() const {
        return isolationScore_;
    }

    double portabilityScore() const {
        return portabilityScore_;
    }

    virtual string boundaryDescription() const = 0;
};

class Container final : public Runtime {
public:
    Container(
        string name,
        Workload workload,
        double cpuLimit,
        double memoryLimitGb
    )
        : Runtime(
            move(name),
            move(workload),
            cpuLimit,
            memoryLimitGb,
            0.8,
            0.02,
            0.08,
            0.72,
            0.95
        ) {}

    RuntimeKind kind() const override {
        return RuntimeKind::Container;
    }

    bool supportsHost(const string& hostArchitecture) const override {
        return hostArchitecture == workload_.architecture;
    }

    string boundaryDescription() const override {
        return "Process and namespace isolation with a shared host kernel";
    }
};

class VirtualMachine final : public Runtime {
private:
    string guestOs_;

public:
    VirtualMachine(
        string name,
        Workload workload,
        double cpuLimit,
        double memoryLimitGb,
        string guestOs
    )
        : Runtime(
            move(name),
            move(workload),
            cpuLimit,
            memoryLimitGb,
            22.0,
            0.20,
            0.65,
            0.96,
            0.82
        ),
          guestOs_(move(guestOs)) {}

    RuntimeKind kind() const override {
        return RuntimeKind::VirtualMachine;
    }

    bool supportsHost(const string& hostArchitecture) const override {
        return hostArchitecture == workload_.architecture;
    }

    string boundaryDescription() const override {
        return "Virtual hardware boundary with an independent guest kernel";
    }

    const string& guestOs() const {
        return guestOs_;
    }
};

class ComputeNode {
private:
    string name_;
    string architecture_;
    double totalCpu_;
    double totalMemoryGb_;
    double totalStorageGb_;
    vector<const Runtime*> workloads_;

public:
    ComputeNode(
        string name,
        string architecture,
        double cpu,
        double memoryGb,
        double storageGb
    )
        : name_(move(name)),
          architecture_(move(architecture)),
          totalCpu_(cpu),
          totalMemoryGb_(memoryGb),
          totalStorageGb_(storageGb) {

        if (cpu <= 0 || memoryGb <= 0 || storageGb <= 0) {
            throw invalid_argument(
                "Node resources must be greater than zero"
            );
        }
    }

    double allocatedCpu() const {
        double total = 0.0;

        for (const Runtime* runtime : workloads_) {
            total += runtime->cpuLimit();
        }

        return total;
    }

    double allocatedMemory() const {
        double total = 0.0;

        for (const Runtime* runtime : workloads_) {
            total += runtime->memoryLimitGb();
        }

        return total;
    }

    double allocatedStorage() const {
        double total = 0.0;

        for (const Runtime* runtime : workloads_) {
            total += runtime->storageGb();
        }

        return total;
    }

    bool canDeploy(const Runtime& runtime) const {
        if (!runtime.supportsHost(architecture_)) {
            return false;
        }

        return allocatedCpu() + runtime.cpuLimit() <= totalCpu_
            && allocatedMemory() + runtime.memoryLimitGb()
                <= totalMemoryGb_
            && allocatedStorage() + runtime.storageGb()
                <= totalStorageGb_;
    }

    void deploy(const Runtime& runtime) {
        if (!canDeploy(runtime)) {
            throw runtime_error(
                "Runtime cannot be deployed on node " + name_
            );
        }

        workloads_.push_back(&runtime);
    }

    double cpuUtilization() const {
        return allocatedCpu() / totalCpu_;
    }

    double memoryUtilization() const {
        return allocatedMemory() / totalMemoryGb_;
    }

    size_t workloadCount() const {
        return workloads_.size();
    }

    const string& name() const {
        return name_;
    }
};

struct PlacementDecision {
    RuntimeKind runtime;
    string reason;
};

class PlacementEngine {
public:
    static PlacementDecision decide(const Workload& workload) {
        if (workload.requiresCustomKernel) {
            return {
                RuntimeKind::VirtualMachine,
                "The workload requires kernel independence."
            };
        }

        if (workload.kind == WorkloadKind::LegacyApplication) {
            return {
                RuntimeKind::VirtualMachine,
                "Legacy software benefits from a complete guest OS."
            };
        }

        if (
            workload.kind == WorkloadKind::WebApi ||
            workload.kind == WorkloadKind::BatchProcessing ||
            workload.kind == WorkloadKind::MultiService
        ) {
            return {
                RuntimeKind::Container,
                "The workload benefits from fast startup and low overhead."
            };
        }

        return {
            RuntimeKind::Container,
            "Container is the initial choice; storage and isolation "
            "requirements must still be validated."
        };
    }
};

void printRuntime(const Runtime& runtime) {
    cout << left
         << setw(24) << runtime.name()
         << setw(20) << toString(runtime.kind())
         << setw(12) << runtime.startupSeconds()
         << setw(12) << runtime.isolationScore()
         << setw(12) << runtime.portabilityScore()
         << '\n';

    cout << "  Boundary: "
         << runtime.boundaryDescription()
         << '\n';

    cout << "  Effective memory: "
         << fixed << setprecision(2)
         << runtime.effectiveMemoryGb()
         << " GB\n";
}

void runCaseStudy() {
    cout << "CONTAINERS VS VIRTUAL MACHINES\n";
    cout << "===============================\n\n";

    vector<Workload> workloads{
        {
            "customer-api",
            WorkloadKind::WebApi,
            1.0,
            1.0,
            5.0,
            false,
            false,
            "x86_64"
        },
        {
            "analytics-worker",
            WorkloadKind::BatchProcessing,
            4.0,
            8.0,
            20.0,
            false,
            false,
            "x86_64"
        },
        {
            "legacy-payment",
            WorkloadKind::LegacyApplication,
            2.0,
            4.0,
            40.0,
            true,
            false,
            "x86_64"
        },
        {
            "orders-db",
            WorkloadKind::Database,
            4.0,
            12.0,
            200.0,
            false,
            false,
            "x86_64"
        }
    };

    cout << "Placement decisions\n";
    cout << "--------------------\n";

    for (const auto& workload : workloads) {
        PlacementDecision decision =
            PlacementEngine::decide(workload);

        cout << workload.name
             << " [" << toString(workload.kind) << "] -> "
             << toString(decision.runtime)
             << '\n';

        cout << "Reason: "
             << decision.reason
             << "\n\n";
    }

    Workload api = workloads.front();

    Container apiContainer(
        "customer-api-container",
        api,
        1.0,
        1.0
    );

    VirtualMachine apiVm(
        "customer-api-vm",
        api,
        1.0,
        1.0,
        "Linux"
    );

    cout << "Runtime characteristics\n";
    cout << "-----------------------\n";
    cout << left
         << setw(24) << "Name"
         << setw(20) << "Runtime"
         << setw(12) << "Startup"
         << setw(12) << "Isolation"
         << setw(12) << "Portability"
         << '\n';

    printRuntime(apiContainer);
    printRuntime(apiVm);

    ComputeNode containerNode(
        "container-node",
        "x86_64",
        16.0,
        32.0,
        500.0
    );

    vector<unique_ptr<Runtime>> containerWorkloads;

    for (int i = 0; i < 12; ++i) {
        Workload repeated{
            "web-" + to_string(i + 1),
            WorkloadKind::WebApi,
            1.0,
            1.0,
            4.0,
            false,
            false,
            "x86_64"
        };

        auto instance = make_unique<Container>(
            repeated.name,
            repeated,
            1.0,
            1.0
        );

        containerNode.deploy(*instance);
        containerWorkloads.push_back(move(instance));
    }

    cout << "\nResource density\n";
    cout << "----------------\n";
    cout << "Container workloads deployed: "
         << containerNode.workloadCount()
         << '\n';

    cout << "CPU utilization: "
         << fixed << setprecision(1)
         << containerNode.cpuUtilization() * 100.0
         << "%\n";

    cout << "Memory utilization: "
         << containerNode.memoryUtilization() * 100.0
         << "%\n";

    ComputeNode vmNode(
        "vm-node",
        "x86_64",
        16.0,
        32.0,
        500.0
    );

    vector<unique_ptr<Runtime>> vmWorkloads;

    for (int i = 0; i < 11; ++i) {
        Workload repeated{
            "vm-web-" + to_string(i + 1),
            WorkloadKind::WebApi,
            1.0,
            1.0,
            4.0,
            false,
            false,
            "x86_64"
        };

        auto instance = make_unique<VirtualMachine>(
            repeated.name,
            repeated,
            1.0,
            1.0,
            "Linux"
        );

        if (vmNode.canDeploy(*instance)) {
            vmNode.deploy(*instance);
            vmWorkloads.push_back(move(instance));
        } else {
            break;
        }
    }

    cout << "\nVM workloads deployed: "
         << vmNode.workloadCount()
         << '\n';

    cout << "VM CPU utilization: "
         << vmNode.cpuUtilization() * 100.0
         << "%\n";

    cout << "VM memory utilization: "
         << vmNode.memoryUtilization() * 100.0
         << "%\n";

    cout << "\nSecurity analysis\n";
    cout << "-----------------\n";
    cout << "For untrusted workloads, a container shares the host kernel.\n";
    cout << "A VM supplies a guest-kernel boundary.\n";
    cout << "Neither model should be considered secure by default.\n";
    cout << "Container hardening can include dropped capabilities, read-only\n";
    cout << "filesystems, seccomp, namespaces, resource limits, and image\n";
    cout << "provenance checks. VM security also depends on the hypervisor,\n";
    cout << "host configuration, device exposure, and management plane.\n";

    cout << "\nArchitectural trade-off\n";
    cout << "-----------------------\n";
    cout << "Containers generally provide lower overhead and faster startup.\n";
    cout << "VMs generally provide stronger workload isolation and kernel independence.\n";
    cout << "A common production architecture uses VMs as infrastructure boundaries\n";
    cout << "and containers as application packaging inside those VMs.\n";
}

int main() {
    try {
        runCaseStudy();
        return 0;
    } catch (const exception& error) {
        cerr << "Execution error: "
             << error.what()
             << '\n';
        return 1;
    }
}
