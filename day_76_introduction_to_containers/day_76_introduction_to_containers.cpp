#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

/*
 * Container Governance and Runtime Engine
 *
 * C++17 implementation of:
 * - Image and layer modeling
 * - Container lifecycle
 * - Host resource allocation
 * - Isolation configuration
 * - Runtime state transitions
 * - Health monitoring
 * - Restart policies
 * - Deployment admission control
 *
 * This is a runtime simulation, not an operating-system
 * namespace or cgroup implementation.
 */

enum class State {
    Created,
    Running,
    Paused,
    Stopped,
    Failed,
    Removed
};

enum class RestartPolicy {
    Never,
    OnFailure,
    Always
};

enum class Isolation {
    Process,
    Network,
    Mount,
    User,
    IPC,
    UTS,
    Cgroup
};

std::string toString(State state) {
    switch (state) {
        case State::Created: return "CREATED";
        case State::Running: return "RUNNING";
        case State::Paused: return "PAUSED";
        case State::Stopped: return "STOPPED";
        case State::Failed: return "FAILED";
        case State::Removed: return "REMOVED";
    }

    throw std::logic_error("Unknown container state.");
}

class ContainerException : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct ResourceLimits {
    double cpuCores = 1.0;
    int memoryMB = 256;
    int diskMB = 512;
    int processLimit = 64;

    void validate() const {
        if (!std::isfinite(cpuCores) ||
            cpuCores <= 0 || cpuCores > 128) {
            throw ContainerException("Invalid CPU limit.");
        }

        if (memoryMB < 16 || memoryMB > 1048576) {
            throw ContainerException("Invalid memory limit.");
        }

        if (diskMB < 16 || diskMB > 10485760) {
            throw ContainerException("Invalid disk limit.");
        }

        if (processLimit < 1 || processLimit > 100000) {
            throw ContainerException("Invalid process limit.");
        }
    }
};

struct ImageLayer {
    std::string name;
    std::string content;
};

class ContainerImage {
private:
    std::string name_;
    std::string version_;
    std::string entrypoint_;
    std::vector<ImageLayer> layers_;
    std::set<int> ports_;

public:
    ContainerImage(
        std::string name,
        std::string version,
        std::string entrypoint,
        std::vector<ImageLayer> layers,
        std::set<int> ports
    ) :
        name_(std::move(name)),
        version_(std::move(version)),
        entrypoint_(std::move(entrypoint)),
        layers_(std::move(layers)),
        ports_(std::move(ports)) {

        if (name_.empty() || version_.empty() ||
            entrypoint_.empty() || layers_.empty()) {
            throw ContainerException("Invalid image definition.");
        }

        for (const auto& layer : layers_) {
            if (layer.name.empty()) {
                throw ContainerException("Invalid image layer.");
            }
        }

        for (int port : ports_) {
            if (port < 1 || port > 65535) {
                throw ContainerException("Invalid image port.");
            }
        }
    }

    std::string reference() const {
        return name_ + ":" + version_;
    }

    const std::vector<ImageLayer>& layers() const {
        return layers_;
    }

    const std::string& entrypoint() const {
        return entrypoint_;
    }
};

class ImageRegistry {
private:
    std::map<std::string, std::shared_ptr<const ContainerImage>> images_;

public:
    void push(std::shared_ptr<const ContainerImage> image) {
        if (!image) {
            throw ContainerException("Null image.");
        }

        images_[image->reference()] = std::move(image);
    }

    std::shared_ptr<const ContainerImage> pull(
        const std::string& reference
    ) const {
        auto iterator = images_.find(reference);

        if (iterator == images_.end()) {
            throw ContainerException("Image not found: " + reference);
        }

        return iterator->second;
    }
};

struct ResourceUsage {
    double cpuCores = 0;
    int memoryMB = 0;
    int diskMB = 0;
    int processes = 0;
};

class Host {
private:
    ResourceLimits capacity_;
    std::map<std::string, ResourceLimits> allocations_;

public:
    explicit Host(ResourceLimits capacity) : capacity_(capacity) {
        capacity_.validate();
    }

    void allocate(
        const std::string& containerId,
        const ResourceLimits& requested
    ) {
        requested.validate();

        if (allocations_.count(containerId)) {
            throw ContainerException("Duplicate resource allocation.");
        }

        double cpu = 0;
        int memory = 0;
        int disk = 0;

        for (const auto& entry : allocations_) {
            cpu += entry.second.cpuCores;
            memory += entry.second.memoryMB;
            disk += entry.second.diskMB;
        }

        if (cpu + requested.cpuCores > capacity_.cpuCores ||
            memory + requested.memoryMB > capacity_.memoryMB ||
            disk + requested.diskMB > capacity_.diskMB) {
            throw ContainerException("Insufficient host capacity.");
        }

        allocations_.emplace(containerId, requested);
    }

    void release(const std::string& containerId) {
        allocations_.erase(containerId);
    }

    std::size_t allocationCount() const {
        return allocations_.size();
    }
};

struct Container {
    std::string id;
    std::string name;
    std::shared_ptr<const ContainerImage> image;

    ResourceLimits limits;
    ResourceUsage usage;

    RestartPolicy restartPolicy;
    State state = State::Created;

    std::set<Isolation> isolation;
    std::map<std::string, std::string> environment;

    int exitCode = 0;
    int restartCount = 0;
    bool healthy = false;
};

class Runtime {
private:
    ImageRegistry& registry_;
    Host& host_;

    std::map<std::string, Container> containers_;
    std::set<std::string> names_;

    static void validateName(const std::string& name) {
        if (name.empty() || name.size() > 63) {
            throw ContainerException("Invalid container name.");
        }

        for (char c : name) {
            if (!std::isalnum(static_cast<unsigned char>(c)) &&
                c != '-' && c != '_' && c != '.') {
                throw ContainerException("Invalid container name.");
            }
        }
    }

    Container& get(const std::string& id) {
        auto iterator = containers_.find(id);

        if (iterator == containers_.end()) {
            throw ContainerException("Container not found.");
        }

        return iterator->second;
    }

public:
    Runtime(ImageRegistry& registry, Host& host)
        : registry_(registry), host_(host) {}

    std::string create(
        const std::string& imageReference,
        const std::string& name,
        const ResourceLimits& limits,
        RestartPolicy policy,
        std::map<std::string, std::string> environment
    ) {
        validateName(name);
        limits.validate();

        if (names_.count(name)) {
            throw ContainerException("Container name already exists.");
        }

        for (const auto& variable : environment) {
            if (variable.first.empty() ||
                variable.first.size() > 64 ||
                variable.second.size() > 4096) {
                throw ContainerException("Invalid environment variable.");
            }
        }

        auto image = registry_.pull(imageReference);

        static unsigned long long sequence = 0;

        std::string id = "container-" + std::to_string(++sequence);

        host_.allocate(id, limits);

        try {
            Container container;

            container.id = id;
            container.name = name;
            container.image = std::move(image);
            container.limits = limits;
            container.restartPolicy = policy;
            container.environment = std::move(environment);

            container.isolation = {
                Isolation::Process,
                Isolation::Network,
                Isolation::Mount,
                Isolation::User,
                Isolation::IPC,
                Isolation::UTS,
                Isolation::Cgroup
            };

            containers_.emplace(id, std::move(container));
            names_.insert(name);

        } catch (...) {
            host_.release(id);
            throw;
        }

        return id;
    }

    void start(const std::string& id) {
        Container& c = get(id);

        if (c.state != State::Created &&
            c.state != State::Stopped) {
            throw ContainerException("Invalid start transition.");
        }

        c.state = State::Running;
        c.healthy = true;
    }

    void pause(const std::string& id) {
        Container& c = get(id);

        if (c.state != State::Running) {
            throw ContainerException("Only running containers can pause.");
        }

        c.state = State::Paused;
    }

    void resume(const std::string& id) {
        Container& c = get(id);

        if (c.state != State::Paused) {
            throw ContainerException("Container is not paused.");
        }

        c.state = State::Running;
    }

    void stop(const std::string& id, int exitCode = 0) {
        Container& c = get(id);

        if (c.state != State::Running &&
            c.state != State::Paused) {
            throw ContainerException("Invalid stop transition.");
        }

        c.state = State::Stopped;
        c.exitCode = exitCode;
    }

    void updateUsage(
        const std::string& id,
        const ResourceUsage& usage
    ) {
        Container& c = get(id);

        if (c.state != State::Running) {
            throw ContainerException("Container is not running.");
        }

        if (usage.cpuCores < 0 ||
            usage.memoryMB < 0 ||
            usage.diskMB < 0 ||
            usage.processes < 0) {
            throw ContainerException("Negative resource usage.");
        }

        if (usage.cpuCores > c.limits.cpuCores ||
            usage.memoryMB > c.limits.memoryMB ||
            usage.diskMB > c.limits.diskMB ||
            usage.processes > c.limits.processLimit) {
            c.healthy = false;
            throw ContainerException("Resource limit exceeded.");
        }

        c.usage = usage;
        c.healthy = true;
    }

    void fail(const std::string& id, int exitCode) {
        Container& c = get(id);

        if (c.state != State::Running) {
            throw ContainerException("Only running containers can fail.");
        }

        c.state = State::Failed;
        c.exitCode = exitCode;
        c.healthy = false;

        bool restart =
            c.restartPolicy == RestartPolicy::Always ||
            (
                c.restartPolicy == RestartPolicy::OnFailure &&
                exitCode != 0
            );

        if (restart && c.restartCount < 3) {
            ++c.restartCount;
            c.state = State::Running;
            c.healthy = true;
        }
    }

    void remove(const std::string& id) {
        Container& c = get(id);

        if (c.state == State::Running ||
            c.state == State::Paused) {
            throw ContainerException("Stop container before removal.");
        }

        names_.erase(c.name);
        host_.release(id);
        containers_.erase(id);
    }

    void report() const {
        std::cout << "\nCONTAINER INVENTORY\n";
        std::cout << std::left
                  << std::setw(18) << "ID"
                  << std::setw(22) << "NAME"
                  << std::setw(12) << "STATE"
                  << std::setw(14) << "MEMORY"
                  << "RESTARTS\n";

        for (const auto& entry : containers_) {
            const Container& c = entry.second;

            std::cout << std::left
                      << std::setw(18) << c.id
                      << std::setw(22) << c.name
                      << std::setw(12) << toString(c.state)
                      << std::setw(14) << c.usage.memoryMB
                      << c.restartCount << '\n';
        }
    }

    std::size_t size() const {
        return containers_.size();
    }
};

void runTests() {
    ResourceLimits capacity;
    capacity.cpuCores = 4;
    capacity.memoryMB = 2048;
    capacity.diskMB = 4096;

    Host host(capacity);
    ImageRegistry registry;

    auto image = std::make_shared<ContainerImage>(
        "test/service",
        "1.0",
        "service",
        std::vector<ImageLayer>{
            {"base", "minimal-linux"},
            {"application", "service-binary"}
        },
        std::set<int>{8080}
    );

    registry.push(image);

    Runtime runtime(registry, host);

    ResourceLimits limits;
    limits.cpuCores = 1;
    limits.memoryMB = 512;
    limits.diskMB = 1024;

    std::string id = runtime.create(
        "test/service:1.0",
        "test-service",
        limits,
        RestartPolicy::OnFailure,
        {{"APP_ENV", "test"}}
    );

    runtime.start(id);

    try {
        runtime.start(id);
        throw ContainerException("Duplicate start was accepted.");
    } catch (const ContainerException& error) {
        if (std::string(error.what()) ==
            "Duplicate start was accepted.") {
            throw;
        }
    }

    ResourceUsage usage;
    usage.cpuCores = 0.5;
    usage.memoryMB = 128;
    usage.diskMB = 100;
    usage.processes = 4;

    runtime.updateUsage(id, usage);
    runtime.pause(id);
    runtime.resume(id);
    runtime.fail(id, 137);

    runtime.stop(id);
    runtime.remove(id);

    if (runtime.size() != 0 || host.allocationCount() != 0) {
        throw ContainerException("Cleanup test failed.");
    }

    std::cout << "C++17 tests passed.\n";
}

int main() {
    try {
        runTests();

        ResourceLimits hostCapacity;
        hostCapacity.cpuCores = 8;
        hostCapacity.memoryMB = 8192;
        hostCapacity.diskMB = 50000;

        Host host(hostCapacity);
        ImageRegistry registry;

        auto image = std::make_shared<ContainerImage>(
            "enterprise/inventory",
            "2.0",
            "inventory-server",
            std::vector<ImageLayer>{
                {"base", "linux-rootfs"},
                {"runtime", "application-runtime"},
                {"application", "inventory-service"}
            },
            std::set<int>{8080, 9090}
        );

        registry.push(image);

        Runtime runtime(registry, host);

        ResourceLimits limits;
        limits.cpuCores = 2;
        limits.memoryMB = 1024;
        limits.diskMB = 2048;
        limits.processLimit = 100;

        std::string id = runtime.create(
            image->reference(),
            "inventory-api",
            limits,
            RestartPolicy::OnFailure,
            {
                {"APP_ENV", "production"},
                {"LOG_LEVEL", "INFO"}
            }
        );

        runtime.start(id);

        ResourceUsage usage;
        usage.cpuCores = 0.8;
        usage.memoryMB = 320;
        usage.diskMB = 500;
        usage.processes = 12;

        runtime.updateUsage(id, usage);

        runtime.report();

        runtime.fail(id, 1);

        std::cout << "\nAfter restart:\n";
        runtime.report();

        runtime.pause(id);
        runtime.resume(id);
        runtime.stop(id);
        runtime.remove(id);

        std::cout << "\nHost allocations remaining: "
                  << host.allocationCount() << '\n';

    } catch (const std::exception& error) {
        std::cerr << "Runtime error: "
                  << error.what() << '\n';

        return 1;
    }

    return 0;
}
