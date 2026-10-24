#include <algorithm>
#include <cstdint>
#include <exception>
#include <functional>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

enum class LoadBalancerType {
    Application,
    Network
};

enum class Protocol {
    HTTP,
    HTTPS,
    TCP,
    TLS
};

enum class TargetState {
    Healthy,
    Unhealthy,
    Draining
};

enum class CheckResult {
    Success,
    Failure
};

struct HealthCheck {
    Protocol protocol;
    int port;
    std::optional<std::string> path;
    int intervalSeconds{10};
    int timeoutSeconds{3};
    int healthyThreshold{2};
    int unhealthyThreshold{3};

    void validate() const {
        if (port < 1 || port > 65535) {
            throw std::invalid_argument("Invalid health-check port.");
        }

        if ((protocol == Protocol::HTTP || protocol == Protocol::HTTPS) &&
            !path.has_value()) {
            throw std::invalid_argument(
                "HTTP/HTTPS health checks require a path."
            );
        }

        if (intervalSeconds <= 0 || timeoutSeconds <= 0) {
            throw std::invalid_argument("Health-check timings must be positive.");
        }

        if (timeoutSeconds >= intervalSeconds) {
            throw std::invalid_argument(
                "Health-check timeout must be shorter than interval."
            );
        }

        if (healthyThreshold <= 0 || unhealthyThreshold <= 0) {
            throw std::invalid_argument(
                "Health thresholds must be positive."
            );
        }
    }
};

struct Target {
    std::string id;
    std::string address;
    int port;
    TargetState state{TargetState::Healthy};
    int activeConnections{0};
    std::string zone;

    void validate() const {
        if (id.empty() || address.empty()) {
            throw std::invalid_argument("Target ID and address are required.");
        }

        if (port < 1 || port > 65535) {
            throw std::invalid_argument("Target port is invalid.");
        }

        if (activeConnections < 0) {
            throw std::invalid_argument(
                "Active connection count cannot be negative."
            );
        }
    }

    bool acceptsNewTraffic() const {
        return state == TargetState::Healthy;
    }
};

class TargetGroup {
private:
    std::string name_;
    Protocol protocol_;
    int port_;
    HealthCheck healthCheck_;
    std::unordered_map<std::string, Target> targets_;

public:
    TargetGroup(
        std::string name,
        Protocol protocol,
        int port,
        HealthCheck healthCheck
    )
        : name_(std::move(name)),
          protocol_(protocol),
          port_(port),
          healthCheck_(std::move(healthCheck)) {
        if (name_.empty()) {
            throw std::invalid_argument("Target-group name is required.");
        }

        if (port_ < 1 || port_ > 65535) {
            throw std::invalid_argument("Target-group port is invalid.");
        }

        healthCheck_.validate();
    }

    void addTarget(Target target) {
        target.validate();

        if (target.port != port_) {
            throw std::invalid_argument(
                "Target port does not match target-group port."
            );
        }

        if (targets_.contains(target.id)) {
            throw std::invalid_argument("Duplicate target: " + target.id);
        }

        targets_.emplace(target.id, std::move(target));
    }

    void setState(const std::string& targetId, TargetState state) {
        auto iterator = targets_.find(targetId);

        if (iterator == targets_.end()) {
            throw std::out_of_range("Unknown target: " + targetId);
        }

        iterator->second.state = state;
    }

    std::vector<std::reference_wrapper<Target>> healthyTargets() {
        std::vector<std::reference_wrapper<Target>> result;

        for (auto& [id, target] : targets_) {
            if (target.acceptsNewTraffic()) {
                result.emplace_back(target);
            }
        }

        return result;
    }

    Target& target(const std::string& targetId) {
        auto iterator = targets_.find(targetId);

        if (iterator == targets_.end()) {
            throw std::out_of_range("Unknown target: " + targetId);
        }

        return iterator->second;
    }

    const std::string& name() const {
        return name_;
    }

    Protocol protocol() const {
        return protocol_;
    }

    int port() const {
        return port_;
    }

    const HealthCheck& healthCheck() const {
        return healthCheck_;
    }
};

struct Request {
    std::string id;
    Protocol protocol;
    int listenerPort;
    std::string sourceAddress;
    std::uint16_t sourcePort;
    std::string host;
    std::string path;
};

struct Listener {
    Protocol protocol;
    int port;
    std::string targetGroup;
};

class GovernanceEngine {
private:
    LoadBalancerType type_;
    std::unordered_map<std::string, TargetGroup> groups_;
    std::vector<Listener> listeners_;
    std::unordered_map<std::string, std::size_t> roundRobin_;

    const Listener& findListener(Protocol protocol, int port) const {
        for (const auto& listener : listeners_) {
            if (listener.protocol == protocol && listener.port == port) {
                return listener;
            }
        }

        throw std::runtime_error("No matching listener.");
    }

    Target& selectApplicationTarget(
        const std::string& groupName,
        std::vector<std::reference_wrapper<Target>>& healthy
    ) {
        if (healthy.empty()) {
            throw std::runtime_error("No healthy targets available.");
        }

        std::size_t index = roundRobin_[groupName] % healthy.size();
        ++roundRobin_[groupName];

        return healthy[index].get();
    }

    Target& selectNetworkTarget(
        const Request& request,
        std::vector<std::reference_wrapper<Target>>& healthy
    ) {
        if (healthy.empty()) {
            throw std::runtime_error("No healthy targets available.");
        }

        // FNV-style deterministic flow hashing provides stable selection
        // for the same source address and source port.
        std::string flow =
            request.sourceAddress + ":" +
            std::to_string(request.sourcePort) + ":" +
            std::to_string(request.listenerPort);

        std::uint64_t hash = 1469598103934665603ULL;

        for (unsigned char character : flow) {
            hash ^= character;
            hash *= 1099511628211ULL;
        }

        std::size_t index = hash % healthy.size();
        return healthy[index].get();
    }

public:
    explicit GovernanceEngine(LoadBalancerType type)
        : type_(type) {}

    void addGroup(TargetGroup group) {
        if (groups_.contains(group.name())) {
            throw std::invalid_argument(
                "Duplicate target group: " + group.name()
            );
        }

        groups_.emplace(group.name(), std::move(group));
    }

    void addListener(Listener listener) {
        if (!groups_.contains(listener.targetGroup)) {
            throw std::invalid_argument(
                "Listener references an unknown target group."
            );
        }

        for (const auto& existing : listeners_) {
            if (existing.protocol == listener.protocol &&
                existing.port == listener.port) {
                throw std::invalid_argument(
                    "Duplicate listener."
                );
            }
        }

        listeners_.push_back(std::move(listener));
    }

    std::string route(const Request& request) {
        const Listener& listener =
            findListener(request.protocol, request.listenerPort);

        auto groupIterator = groups_.find(listener.targetGroup);

        if (groupIterator == groups_.end()) {
            throw std::runtime_error("Target group disappeared.");
        }

        TargetGroup& group = groupIterator->second;
        auto healthy = group.healthyTargets();

        Target* selected = nullptr;

        if (type_ == LoadBalancerType::Application) {
            if (request.protocol != Protocol::HTTP &&
                request.protocol != Protocol::HTTPS) {
                throw std::runtime_error(
                    "Application load balancing requires HTTP/HTTPS."
                );
            }

            selected = &selectApplicationTarget(group.name(), healthy);
        } else {
            if (request.protocol != Protocol::TCP &&
                request.protocol != Protocol::TLS) {
                throw std::runtime_error(
                    "Network load balancing requires TCP/TLS."
                );
            }

            selected = &selectNetworkTarget(request, healthy);
        }

        ++selected->activeConnections;
        return selected->id;
    }

    void closeConnection(
        const std::string& groupName,
        const std::string& targetId
    ) {
        auto group = groups_.find(groupName);

        if (group == groups_.end()) {
            throw std::out_of_range("Unknown target group.");
        }

        Target& target = group->second.target(targetId);

        if (target.activeConnections <= 0) {
            throw std::runtime_error(
                "Cannot close a connection that is not active."
            );
        }

        --target.activeConnections;
    }

    void updateHealth(
        const std::string& groupName,
        const std::string& targetId,
        CheckResult result
    ) {
        auto group = groups_.find(groupName);

        if (group == groups_.end()) {
            throw std::out_of_range("Unknown target group.");
        }

        Target& target = group->second.target(targetId);

        target.state =
            result == CheckResult::Success
                ? TargetState::Healthy
                : TargetState::Unhealthy;
    }

    void drainTarget(
        const std::string& groupName,
        const std::string& targetId
    ) {
        auto group = groups_.find(groupName);

        if (group == groups_.end()) {
            throw std::out_of_range("Unknown target group.");
        }

        group->second.setState(targetId, TargetState::Draining);
    }
};

TargetGroup createWebGroup() {
    HealthCheck check{
        Protocol::HTTP,
        8080,
        std::string("/health"),
        10,
        3,
        2,
        3
    };

    TargetGroup group(
        "web-targets",
        Protocol::HTTP,
        8080,
        check
    );

    group.addTarget({
        "web-a",
        "10.0.1.10",
        8080,
        TargetState::Healthy,
        0,
        "zone-a"
    });

    group.addTarget({
        "web-b",
        "10.0.2.10",
        8080,
        TargetState::Healthy,
        0,
        "zone-b"
    });

    group.addTarget({
        "web-c",
        "10.0.3.10",
        8080,
        TargetState::Healthy,
        0,
        "zone-c"
    });

    return group;
}

TargetGroup createTcpGroup() {
    HealthCheck check{
        Protocol::TCP,
        9000,
        std::nullopt,
        10,
        3,
        2,
        3
    };

    TargetGroup group(
        "tcp-targets",
        Protocol::TCP,
        9000,
        check
    );

    group.addTarget({
        "tcp-a",
        "10.1.1.10",
        9000,
        TargetState::Healthy,
        0,
        "zone-a"
    });

    group.addTarget({
        "tcp-b",
        "10.1.2.10",
        9000,
        TargetState::Healthy,
        0,
        "zone-b"
    });

    return group;
}

int main() {
    try {
        GovernanceEngine applicationLb(LoadBalancerType::Application);
        applicationLb.addGroup(createWebGroup());
        applicationLb.addListener({
            Protocol::HTTP,
            80,
            "web-targets"
        });

        std::cout << "Application load balancer\n";

        for (const auto& request : std::vector<Request>{
            {
                "req-1",
                Protocol::HTTP,
                80,
                "192.0.2.10",
                51001,
                "api.example.com",
                "/users"
            },
            {
                "req-2",
                Protocol::HTTP,
                80,
                "192.0.2.11",
                51002,
                "api.example.com",
                "/orders"
            },
            {
                "req-3",
                Protocol::HTTP,
                80,
                "192.0.2.12",
                51003,
                "api.example.com",
                "/orders/42"
            }
        }) {
            std::cout
                << request.id
                << " -> "
                << applicationLb.route(request)
                << '\n';
        }

        applicationLb.updateHealth(
            "web-targets",
            "web-b",
            CheckResult::Failure
        );

        std::cout << "web-b marked unhealthy\n";

        std::cout
            << "Next request -> "
            << applicationLb.route({
                "req-4",
                Protocol::HTTP,
                80,
                "192.0.2.20",
                51020,
                "api.example.com",
                "/health"
            })
            << '\n';

        GovernanceEngine networkLb(LoadBalancerType::Network);
        networkLb.addGroup(createTcpGroup());
        networkLb.addListener({
            Protocol::TCP,
            443,
            "tcp-targets"
        });

        std::cout << "\nNetwork load balancer\n";

        Request stableFlow{
            "flow-1",
            Protocol::TCP,
            443,
            "198.51.100.20",
            55001,
            "",
            ""
        };

        std::string first = networkLb.route(stableFlow);
        std::string second = networkLb.route(stableFlow);

        std::cout << "First flow selection: " << first << '\n';
        std::cout << "Repeated flow selection: " << second << '\n';

        networkLb.drainTarget("tcp-targets", first);

        std::cout << "Selected target has entered draining state.\n";

        // A draining target remains useful for existing connections but
        // cannot receive new connections through route().
        std::string replacement = networkLb.route({
            "flow-2",
            Protocol::TCP,
            443,
            "198.51.100.21",
            55002,
            "",
            ""
        });

        std::cout << "New flow -> " << replacement << '\n';

        if (first == replacement) {
            throw std::runtime_error(
                "Draining target incorrectly received new traffic."
            );
        }

    } catch (const std::exception& error) {
        std::cerr << "Load-balancer error: "
                  << error.what()
                  << '\n';
        return 1;
    }

    return 0;
}
