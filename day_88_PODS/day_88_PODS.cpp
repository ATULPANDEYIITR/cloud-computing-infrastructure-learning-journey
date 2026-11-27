#include <algorithm>
#include <cassert>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

/*
 * Kubernetes Pod governance and merge-independent lifecycle engine.
 *
 * C++17 implementation of:
 * - Pod architecture
 * - Container and init-container execution
 * - Resource-based scheduling
 * - Restart policies
 * - Readiness evaluation
 * - Multi-container resource accounting
 * - Pod lifecycle transitions
 */

enum class PodPhase {
    Pending,
    Running,
    Succeeded,
    Failed,
    Unknown
};

enum class ContainerState {
    Waiting,
    Running,
    Terminated
};

enum class RestartPolicy {
    Always,
    OnFailure,
    Never
};

std::string toString(PodPhase phase) {
    switch (phase) {
        case PodPhase::Pending: return "Pending";
        case PodPhase::Running: return "Running";
        case PodPhase::Succeeded: return "Succeeded";
        case PodPhase::Failed: return "Failed";
        case PodPhase::Unknown: return "Unknown";
    }
    throw std::logic_error("Unknown Pod phase");
}

std::string toString(ContainerState state) {
    switch (state) {
        case ContainerState::Waiting: return "Waiting";
        case ContainerState::Running: return "Running";
        case ContainerState::Terminated: return "Terminated";
    }
    throw std::logic_error("Unknown container state");
}

struct ResourceRequest {
    int cpuMillicores;
    int memoryMiB;

    void validate() const {
        if (cpuMillicores <= 0 || memoryMiB <= 0) {
            throw std::invalid_argument(
                "Resource requests must be positive"
            );
        }
    }
};

struct Container {
    std::string name;
    std::string image;
    ResourceRequest resources;
    std::vector<int> ports;

    ContainerState state = ContainerState::Waiting;
    int restartCount = 0;
    int exitCode = -1;
    bool ready = false;
    bool livenessHealthy = true;
    bool essential = true;

    void validate() const {
        if (name.empty() || name.size() > 63) {
            throw std::invalid_argument("Invalid container name");
        }

        if (image.empty()) {
            throw std::invalid_argument("Container image is required");
        }

        resources.validate();

        for (int port : ports) {
            if (port < 1 || port > 65535) {
                throw std::invalid_argument("Invalid container port");
            }
        }
    }
};

struct PodSpec {
    std::vector<Container> containers;
    std::vector<Container> initContainers;
    RestartPolicy restartPolicy = RestartPolicy::Always;
    std::map<std::string, std::string> labels;
    int terminationGracePeriodSeconds = 30;

    void validate() const {
        if (containers.empty()) {
            throw std::invalid_argument(
                "Pod requires at least one application container"
            );
        }

        if (terminationGracePeriodSeconds < 0) {
            throw std::invalid_argument(
                "Termination grace period cannot be negative"
            );
        }

        std::set<std::string> names;

        auto validateContainer = [&](const Container& container) {
            container.validate();

            if (!names.insert(container.name).second) {
                throw std::invalid_argument(
                    "Duplicate container name: " + container.name
                );
            }
        };

        for (const auto& container : initContainers) {
            validateContainer(container);
        }

        for (const auto& container : containers) {
            validateContainer(container);
        }
    }

    ResourceRequest totalResources() const {
        ResourceRequest result{0, 0};

        // This is a simplified scheduling model. Kubernetes accounts for
        // regular-container sums and init-container scheduling requirements.
        int applicationCPU = 0;
        int applicationMemory = 0;
        int maximumInitCPU = 0;
        int maximumInitMemory = 0;

        for (const auto& container : containers) {
            applicationCPU += container.resources.cpuMillicores;
            applicationMemory += container.resources.memoryMiB;
        }

        for (const auto& container : initContainers) {
            maximumInitCPU = std::max(
                maximumInitCPU,
                container.resources.cpuMillicores
            );
            maximumInitMemory = std::max(
                maximumInitMemory,
                container.resources.memoryMiB
            );
        }

        result.cpuMillicores = std::max(
            applicationCPU,
            maximumInitCPU
        );

        result.memoryMiB = std::max(
            applicationMemory,
            maximumInitMemory
        );

        return result;
    }
};

class Pod {
private:
    std::string name_;
    std::string namespace_;
    PodSpec spec_;
    PodPhase phase_ = PodPhase::Pending;
    std::optional<std::string> node_;
    bool scheduled_ = false;
    bool initialized_ = false;
    std::vector<std::string> events_;

public:
    Pod(
        std::string name,
        std::string namespaceName,
        PodSpec spec
    )
        : name_(std::move(name)),
          namespace_(std::move(namespaceName)),
          spec_(std::move(spec)) {

        if (name_.empty() || namespace_.empty()) {
            throw std::invalid_argument(
                "Pod name and namespace are required"
            );
        }

        spec_.validate();
    }

    const std::string& name() const {
        return name_;
    }

    const std::string& namespaceName() const {
        return namespace_;
    }

    const PodSpec& spec() const {
        return spec_;
    }

    PodSpec& mutableSpec() {
        return spec_;
    }

    PodPhase phase() const {
        return phase_;
    }

    const std::optional<std::string>& node() const {
        return node_;
    }

    bool scheduled() const {
        return scheduled_;
    }

    bool initialized() const {
        return initialized_;
    }

    void setNode(const std::string& nodeName) {
        node_ = nodeName;
        scheduled_ = true;
    }

    void setInitialized(bool value) {
        initialized_ = value;
    }

    void setPhase(PodPhase phase) {
        phase_ = phase;
    }

    void record(const std::string& event) {
        events_.push_back(event);
        std::cout << "[" << name_ << "] " << event << '\n';
    }

    const std::vector<std::string>& events() const {
        return events_;
    }

    bool ready() const {
        if (phase_ != PodPhase::Running || !initialized_) {
            return false;
        }

        return std::all_of(
            spec_.containers.begin(),
            spec_.containers.end(),
            [](const Container& container) {
                return container.state == ContainerState::Running
                    && container.ready;
            }
        );
    }
};

class Node {
private:
    std::string name_;
    int cpuCapacity_;
    int memoryCapacity_;
    int allocatedCPU_ = 0;
    int allocatedMemory_ = 0;
    std::set<std::string> allocatedPods_;

public:
    Node(std::string name, int cpu, int memory)
        : name_(std::move(name)),
          cpuCapacity_(cpu),
          memoryCapacity_(memory) {

        if (name_.empty() || cpu <= 0 || memory <= 0) {
            throw std::invalid_argument("Invalid node configuration");
        }
    }

    const std::string& name() const {
        return name_;
    }

    bool canFit(ResourceRequest resources) const {
        return allocatedCPU_ + resources.cpuMillicores <= cpuCapacity_
            && allocatedMemory_ + resources.memoryMiB <= memoryCapacity_;
    }

    void allocate(
        const std::string& podName,
        ResourceRequest resources
    ) {
        if (allocatedPods_.count(podName)) {
            throw std::runtime_error("Pod already allocated");
        }

        if (!canFit(resources)) {
            throw std::runtime_error("Node capacity exceeded");
        }

        allocatedCPU_ += resources.cpuMillicores;
        allocatedMemory_ += resources.memoryMiB;
        allocatedPods_.insert(podName);
    }

    void release(
        const std::string& podName,
        ResourceRequest resources
    ) {
        if (!allocatedPods_.erase(podName)) {
            return;
        }

        allocatedCPU_ -= resources.cpuMillicores;
        allocatedMemory_ -= resources.memoryMiB;
    }

    void print() const {
        std::cout
            << name_
            << " CPU=" << allocatedCPU_ << "/" << cpuCapacity_
            << "m Memory=" << allocatedMemory_ << "/"
            << memoryCapacity_ << "MiB\n";
    }
};

class PodScheduler {
private:
    std::vector<std::shared_ptr<Node>> nodes_;

public:
    explicit PodScheduler(std::vector<std::shared_ptr<Node>> nodes)
        : nodes_(std::move(nodes)) {

        if (nodes_.empty()) {
            throw std::invalid_argument("At least one node is required");
        }
    }

    bool schedule(Pod& pod) {
        if (pod.phase() != PodPhase::Pending || pod.scheduled()) {
            throw std::runtime_error("Pod cannot be scheduled");
        }

        const auto resources = pod.spec().totalResources();

        for (const auto& node : nodes_) {
            if (node->canFit(resources)) {
                node->allocate(pod.name(), resources);
                pod.setNode(node->name());

                pod.record("Scheduled on " + node->name());
                return true;
            }
        }

        pod.record("Scheduling failed: insufficient resources");
        return false;
    }

    void release(Pod& pod) {
        if (!pod.node()) return;

        auto node = std::find_if(
            nodes_.begin(),
            nodes_.end(),
            [&](const auto& candidate) {
                return candidate->name() == *pod.node();
            }
        );

        if (node != nodes_.end()) {
            (*node)->release(
                pod.name(),
                pod.spec().totalResources()
            );
        }

        pod.record("Node resources released");
    }

    void printNodes() const {
        for (const auto& node : nodes_) {
            node->print();
        }
    }
};

class PodLifecycle {
private:
    static Container* findContainer(
        Pod& pod,
        const std::string& name
    ) {
        auto& containers = pod.mutableSpec().containers;

        auto it = std::find_if(
            containers.begin(),
            containers.end(),
            [&](const Container& c) {
                return c.name == name;
            }
        );

        if (it == containers.end()) {
            throw std::runtime_error("Unknown container: " + name);
        }

        return &(*it);
    }

public:
    void start(Pod& pod) {
        if (!pod.scheduled() || pod.phase() != PodPhase::Pending) {
            throw std::runtime_error(
                "Pod must be scheduled before initialization"
            );
        }

        auto& spec = pod.mutableSpec();

        // Init containers execute one at a time.
        for (auto& container : spec.initContainers) {
            container.state = ContainerState::Running;
            pod.record("Init container started: " + container.name);

            container.state = ContainerState::Terminated;
            container.exitCode = 0;

            pod.record("Init container completed: " + container.name);
        }

        for (auto& container : spec.containers) {
            container.state = ContainerState::Running;
            container.ready = true;
            container.exitCode = -1;

            pod.record("Application container started: " + container.name);
        }

        pod.setInitialized(true);
        pod.setPhase(PodPhase::Running);
        pod.record("Pod entered Running phase");
    }

    void setReadiness(
        Pod& pod,
        const std::string& name,
        bool ready
    ) {
        Container* container = findContainer(pod, name);

        if (container->state != ContainerState::Running) {
            throw std::runtime_error("Container is not running");
        }

        container->ready = ready;
        pod.record(
            "Readiness updated for " + name +
            ": " + (ready ? "true" : "false")
        );
    }

    bool terminate(
        Pod& pod,
        const std::string& name,
        int exitCode
    ) {
        if (exitCode < 0) {
            throw std::invalid_argument("Invalid exit code");
        }

        Container* container = findContainer(pod, name);

        if (container->state != ContainerState::Running) {
            throw std::runtime_error("Container is not running");
        }

        container->state = ContainerState::Terminated;
        container->exitCode = exitCode;
        container->ready = false;

        pod.record(
            "Container terminated: " + name +
            ", exit code=" + std::to_string(exitCode)
        );

        const auto policy = pod.spec().restartPolicy;

        const bool restart =
            policy == RestartPolicy::Always ||
            (
                policy == RestartPolicy::OnFailure
                && exitCode != 0
            );

        if (restart) {
            ++container->restartCount;
            container->state = ContainerState::Running;
            container->exitCode = -1;
            container->ready = true;

            pod.record(
                "Container restarted: " + name +
                ", count=" + std::to_string(container->restartCount)
            );

            return true;
        }

        if (exitCode != 0 && container->essential) {
            pod.setPhase(PodPhase::Failed);
            pod.record("Pod failed because an essential container failed");
            return false;
        }

        const auto& containers = pod.spec().containers;

        const bool allTerminated = std::all_of(
            containers.begin(),
            containers.end(),
            [](const Container& c) {
                return c.state == ContainerState::Terminated;
            }
        );

        if (allTerminated) {
            pod.setPhase(PodPhase::Succeeded);
            pod.record("All application containers completed");
        }

        return false;
    }

    void livenessFailure(Pod& pod, const std::string& name) {
        Container* container = findContainer(pod, name);

        if (container->state != ContainerState::Running) {
            throw std::runtime_error("Container is not running");
        }

        container->livenessHealthy = false;
        container->state = ContainerState::Terminated;
        container->ready = false;
        container->exitCode = 137;
        ++container->restartCount;

        container->state = ContainerState::Running;
        container->exitCode = -1;
        container->ready = true;
        container->livenessHealthy = true;

        pod.record("Liveness failure restarted container: " + name);
    }

    void shutdown(Pod& pod, PodScheduler& scheduler) {
        if (
            pod.phase() == PodPhase::Succeeded ||
            pod.phase() == PodPhase::Failed
        ) {
            scheduler.release(pod);
            return;
        }

        pod.record("Graceful termination initiated");

        for (auto& container : pod.mutableSpec().containers) {
            container.ready = false;

            if (container.state == ContainerState::Running) {
                container.state = ContainerState::Terminated;
                container.exitCode = 143;
            }
        }

        pod.setPhase(PodPhase::Succeeded);
        scheduler.release(pod);
        pod.record("Pod terminated");
    }
};

void runApplicationScenario() {
    auto nodeA = std::make_shared<Node>("worker-a", 2000, 4096);
    auto nodeB = std::make_shared<Node>("worker-b", 1000, 2048);

    PodScheduler scheduler({nodeA, nodeB});
    PodLifecycle lifecycle;

    PodSpec spec;

    spec.containers = {
        Container{
            "api",
            "nginx:1.27",
            {300, 256},
            {8080}
        },
        Container{
            "log-agent",
            "fluent-bit:3.1",
            {100, 128},
            {}
        }
    };

    spec.initContainers = {
        Container{
            "config-init",
            "busybox:1.36",
            {50, 64},
            {}
        }
    };

    spec.restartPolicy = RestartPolicy::Always;
    spec.labels = {
        {"app", "orders"},
        {"environment", "production"}
    };

    Pod pod("orders-service", "production", spec);

    assert(scheduler.schedule(pod));
    lifecycle.start(pod);

    assert(pod.phase() == PodPhase::Running);
    assert(pod.ready());

    lifecycle.setReadiness(pod, "log-agent", false);
    assert(!pod.ready());

    lifecycle.setReadiness(pod, "log-agent", true);
    assert(pod.ready());

    assert(lifecycle.terminate(pod, "api", 1));
    assert(pod.ready());

    lifecycle.livenessFailure(pod, "api");

    std::cout << "\nPod state: " << toString(pod.phase()) << '\n';
    std::cout << "Pod ready: " << std::boolalpha << pod.ready() << '\n';

    scheduler.printNodes();

    lifecycle.shutdown(pod, scheduler);

    std::cout << "\nAfter termination:\n";
    scheduler.printNodes();
}

void runBatchScenario() {
    PodSpec spec;

    spec.containers = {
        Container{
            "worker",
            "python:3.13-slim",
            {200, 256},
            {}
        }
    };

    spec.restartPolicy = RestartPolicy::Never;

    Pod batch("data-processing", "jobs", spec);

    PodScheduler scheduler({
        std::make_shared<Node>("batch-node", 1000, 2048)
    });

    PodLifecycle lifecycle;

    assert(scheduler.schedule(batch));
    lifecycle.start(batch);

    assert(!lifecycle.terminate(batch, "worker", 0));
    assert(batch.phase() == PodPhase::Succeeded);

    scheduler.release(batch);
}

int main() {
    try {
        std::cout << "KUBERNETES POD GOVERNANCE ENGINE\n\n";

        runApplicationScenario();
        std::cout << "\nBATCH WORKLOAD SCENARIO\n";
        runBatchScenario();

        std::cout << "\nAll lifecycle assertions passed.\n";
    } catch (const std::exception& error) {
        std::cerr << "Execution error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
