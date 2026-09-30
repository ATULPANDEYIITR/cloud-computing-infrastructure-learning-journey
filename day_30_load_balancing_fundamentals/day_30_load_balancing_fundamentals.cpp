#include <algorithm>
#include <chrono>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <numeric>
#include <optional>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

/*
 * Load Balancing Governance and Routing Engine
 *
 * This C++17 case study models a production-oriented load-balancing decision
 * engine for an HTTP service. It combines:
 *
 * - Layer 4 transport routing
 * - Layer 7 HTTP routing
 * - weighted traffic distribution
 * - least-connections selection
 * - active health checks
 * - sticky sessions
 * - connection draining
 * - backend capacity
 * - application failures
 *
 * The program is a deterministic local model rather than a real network proxy.
 */

enum class Protocol {
    TCP,
    HTTP
};

enum class BackendState {
    Healthy,
    Unhealthy,
    Draining
};

enum class Algorithm {
    RoundRobin,
    WeightedRoundRobin,
    LeastConnections,
    IpHash,
    StickySession
};

struct Request {
    int id{};
    std::string clientIp;
    Protocol protocol{Protocol::TCP};
    std::string method{"GET"};
    std::string path{"/"};
    std::string sessionId;
};

struct Backend {
    std::string id;
    std::string address;
    int port{8080};
    int weight{1};
    int maxConnections{100};
    int activeConnections{0};
    int totalRequests{0};
    int failedRequests{0};
    int healthFailures{0};
    int healthSuccesses{0};
    double latencyMs{20.0};

    BackendState state{BackendState::Healthy};
    bool healthEndpointAvailable{true};
    bool applicationHealthy{true};

    bool canAccept() const {
        return state == BackendState::Healthy &&
               activeConnections < maxConnections;
    }

    bool openConnection() {
        if (!canAccept()) {
            return false;
        }

        ++activeConnections;
        ++totalRequests;
        return true;
    }

    void closeConnection(bool success) {
        activeConnections = std::max(0, activeConnections - 1);

        if (!success) {
            ++failedRequests;
        }
    }
};

struct RouteRule {
    std::string method{"*"};
    std::string pathPrefix;
    std::string backendId;
};

struct HealthResult {
    std::string backendId;
    bool healthy{};
    std::string reason;
};

struct RoutingResult {
    bool routed{false};
    bool applicationSuccess{false};
    std::string backendId;
    std::string reason;
};

class HealthChecker {
public:
    HealthChecker(int failureThreshold = 2, int recoveryThreshold = 2)
        : failureThreshold_(failureThreshold),
          recoveryThreshold_(recoveryThreshold) {}

    HealthResult check(Backend& backend) const {
        if (backend.healthEndpointAvailable &&
            backend.state != BackendState::Draining) {
            ++backend.healthSuccesses;
            backend.healthFailures = 0;

            if (backend.state == BackendState::Unhealthy &&
                backend.healthSuccesses >= recoveryThreshold_) {
                backend.state = BackendState::Healthy;
            }

            return {
                backend.id,
                true,
                "health endpoint is available"
            };
        }

        ++backend.healthFailures;
        backend.healthSuccesses = 0;

        if (backend.healthFailures >= failureThreshold_) {
            backend.state = BackendState::Unhealthy;
        }

        return {
            backend.id,
            false,
            "health endpoint failed or backend is draining"
        };
    }

private:
    int failureThreshold_;
    int recoveryThreshold_;
};

class TrafficSelector {
public:
    Backend* roundRobin(std::vector<Backend>& backends) {
        auto eligible = eligibleBackends(backends);

        if (eligible.empty()) {
            return nullptr;
        }

        Backend* selected = eligible[cursor_ % eligible.size()];
        cursor_ = (cursor_ + 1) % eligible.size();
        return selected;
    }

    Backend* weightedRoundRobin(std::vector<Backend>& backends) {
        std::vector<Backend*> weightedPool;

        for (Backend& backend : backends) {
            if (!backend.canAccept() || backend.weight <= 0) {
                continue;
            }

            for (int i = 0; i < backend.weight; ++i) {
                weightedPool.push_back(&backend);
            }
        }

        if (weightedPool.empty()) {
            return nullptr;
        }

        Backend* selected = weightedPool[cursor_ % weightedPool.size()];
        cursor_ = (cursor_ + 1) % weightedPool.size();
        return selected;
    }

    Backend* leastConnections(std::vector<Backend>& backends) {
        Backend* best = nullptr;

        for (Backend& backend : backends) {
            if (!backend.canAccept()) {
                continue;
            }

            if (best == nullptr ||
                backend.activeConnections < best->activeConnections ||
                (backend.activeConnections == best->activeConnections &&
                 backend.weight > best->weight)) {
                best = &backend;
            }
        }

        return best;
    }

    Backend* ipHash(
        std::vector<Backend>& backends,
        const std::string& clientIp
    ) const {
        auto eligible = eligibleBackends(backends);

        if (eligible.empty()) {
            return nullptr;
        }

        /*
         * std::hash provides deterministic behavior for the same execution
         * environment. Production systems often use explicit hash functions
         * and consistent hashing to reduce remapping when servers change.
         */
        std::size_t value = std::hash<std::string>{}(clientIp);
        return eligible[value % eligible.size()];
    }

private:
    static std::vector<Backend*> eligibleBackends(
        std::vector<Backend>& backends
    ) {
        std::vector<Backend*> result;

        for (Backend& backend : backends) {
            if (backend.canAccept()) {
                result.push_back(&backend);
            }
        }

        return result;
    }

    std::size_t cursor_{0};
};

class StickySessionTable {
public:
    Backend* find(
        std::vector<Backend>& backends,
        const std::string& sessionId
    ) const {
        auto mapping = sessions_.find(sessionId);

        if (mapping == sessions_.end()) {
            return nullptr;
        }

        for (Backend& backend : backends) {
            if (backend.id == mapping->second && backend.canAccept()) {
                return &backend;
            }
        }

        return nullptr;
    }

    void bind(const std::string& sessionId, const Backend& backend) {
        if (!sessionId.empty()) {
            sessions_[sessionId] = backend.id;
        }
    }

    void invalidateBackend(const std::string& backendId) {
        for (auto iterator = sessions_.begin();
             iterator != sessions_.end();) {
            if (iterator->second == backendId) {
                iterator = sessions_.erase(iterator);
            } else {
                ++iterator;
            }
        }
    }

    std::string mappedBackend(const std::string& sessionId) const {
        auto iterator = sessions_.find(sessionId);

        if (iterator == sessions_.end()) {
            return "<none>";
        }

        return iterator->second;
    }

private:
    std::unordered_map<std::string, std::string> sessions_;
};

class HttpRouter {
public:
    void addRule(RouteRule rule) {
        if (rule.pathPrefix.empty() || rule.pathPrefix.front() != '/') {
            throw std::invalid_argument(
                "HTTP route prefix must start with '/'"
            );
        }

        rules_.push_back(std::move(rule));
    }

    const RouteRule* match(const Request& request) const {
        for (const RouteRule& rule : rules_) {
            bool methodMatches =
                rule.method == "*" || rule.method == request.method;

            bool pathMatches =
                request.path.rfind(rule.pathPrefix, 0) == 0;

            if (methodMatches && pathMatches) {
                return &rule;
            }
        }

        return nullptr;
    }

private:
    std::vector<RouteRule> rules_;
};

class LoadBalancer {
public:
    LoadBalancer(
        std::vector<Backend> backends,
        Algorithm algorithm
    )
        : backends_(std::move(backends)),
          algorithm_(algorithm) {}

    void addHttpRoute(RouteRule rule) {
        router_.addRule(std::move(rule));
    }

    std::vector<HealthResult> runHealthChecks() {
        std::vector<HealthResult> results;

        for (Backend& backend : backends_) {
            results.push_back(healthChecker_.check(backend));

            if (backend.state == BackendState::Unhealthy) {
                stickySessions_.invalidateBackend(backend.id);
            }
        }

        return results;
    }

    RoutingResult process(const Request& request) {
        ++totalRequests_;

        Backend* backend = selectBackend(request);

        if (backend == nullptr) {
            ++routingFailures_;

            return {
                false,
                false,
                "",
                "no healthy backend has available capacity"
            };
        }

        if (!backend->openConnection()) {
            ++routingFailures_;

            return {
                false,
                false,
                "",
                "backend rejected the connection"
            };
        }

        /*
         * Transport success and application success are deliberately tracked
         * separately. A server can accept TCP connections while its HTTP
         * application is returning errors.
         */
        bool applicationSuccess = backend->applicationHealthy;

        backend->closeConnection(applicationSuccess);

        if (!applicationSuccess) {
            ++applicationFailures_;
        }

        return {
            true,
            applicationSuccess,
            backend->id,
            applicationSuccess
                ? "request routed successfully"
                : "backend application returned an error"
        };
    }

    void drain(const std::string& backendId) {
        Backend& backend = getBackend(backendId);
        backend.state = BackendState::Draining;
        stickySessions_.invalidateBackend(backendId);
    }

    void restore(const std::string& backendId) {
        Backend& backend = getBackend(backendId);
        backend.state = BackendState::Healthy;
        backend.healthEndpointAvailable = true;
    }

    void failHealthEndpoint(const std::string& backendId) {
        Backend& backend = getBackend(backendId);
        backend.healthEndpointAvailable = false;
    }

    void recoverHealthEndpoint(const std::string& backendId) {
        Backend& backend = getBackend(backendId);
        backend.healthEndpointAvailable = true;
    }

    std::string sessionBackend(const std::string& sessionId) const {
        return stickySessions_.mappedBackend(sessionId);
    }

    const std::vector<Backend>& backends() const {
        return backends_;
    }

    void printMetrics() const {
        std::cout
            << "Requests: " << totalRequests_
            << ", routing failures: " << routingFailures_
            << ", application failures: " << applicationFailures_
            << '\n';

        for (const Backend& backend : backends_) {
            std::cout
                << "  " << backend.id
                << " requests=" << backend.totalRequests
                << " failed=" << backend.failedRequests
                << " state=" << stateName(backend.state)
                << '\n';
        }
    }

private:
    Backend* selectBackend(const Request& request) {
        /*
         * HTTP routing rules are evaluated first because they represent an
         * application-aware Layer 7 decision. TCP traffic skips this stage.
         */
        if (request.protocol == Protocol::HTTP) {
            const RouteRule* rule = router_.match(request);

            if (rule != nullptr) {
                Backend* routed = findEligible(rule->backendId);

                if (routed != nullptr) {
                    return routed;
                }
            }
        }

        switch (algorithm_) {
            case Algorithm::RoundRobin:
                return selector_.roundRobin(backends_);

            case Algorithm::WeightedRoundRobin:
                return selector_.weightedRoundRobin(backends_);

            case Algorithm::LeastConnections:
                return selector_.leastConnections(backends_);

            case Algorithm::IpHash:
                return selector_.ipHash(backends_, request.clientIp);

            case Algorithm::StickySession: {
                if (!request.sessionId.empty()) {
                    Backend* existing =
                        stickySessions_.find(backends_, request.sessionId);

                    if (existing != nullptr) {
                        return existing;
                    }
                }

                Backend* selected = selector_.roundRobin(backends_);

                if (selected != nullptr && !request.sessionId.empty()) {
                    stickySessions_.bind(request.sessionId, *selected);
                }

                return selected;
            }
        }

        return nullptr;
    }

    Backend* findEligible(const std::string& backendId) {
        for (Backend& backend : backends_) {
            if (backend.id == backendId && backend.canAccept()) {
                return &backend;
            }
        }

        return nullptr;
    }

    Backend& getBackend(const std::string& backendId) {
        for (Backend& backend : backends_) {
            if (backend.id == backendId) {
                return backend;
            }
        }

        throw std::invalid_argument("unknown backend: " + backendId);
    }

    static std::string stateName(BackendState state) {
        switch (state) {
            case BackendState::Healthy:
                return "healthy";
            case BackendState::Unhealthy:
                return "unhealthy";
            case BackendState::Draining:
                return "draining";
        }

        return "unknown";
    }

    std::vector<Backend> backends_;
    Algorithm algorithm_;

    TrafficSelector selector_;
    StickySessionTable stickySessions_;
    HttpRouter router_;
    HealthChecker healthChecker_;

    long long totalRequests_{0};
    long long routingFailures_{0};
    long long applicationFailures_{0};
};

std::vector<Backend> createBackends() {
    return {
        {
            "app-01",
            "10.0.10.11",
            8080,
            3,
            100,
            0,
            0,
            0,
            0,
            12.0
        },
        {
            "app-02",
            "10.0.10.12",
            8080,
            2,
            100,
            0,
            0,
            0,
            0,
            20.0
        },
        {
            "app-03",
            "10.0.10.13",
            8080,
            1,
            100,
            0,
            0,
            0,
            0,
            35.0
        }
    };
}

std::string protocolName(Protocol protocol) {
    return protocol == Protocol::TCP ? "TCP" : "HTTP";
}

void printResult(const RoutingResult& result) {
    std::cout
        << "routed=" << std::boolalpha << result.routed
        << " application_success=" << result.applicationSuccess
        << " backend=" << (result.backendId.empty() ? "<none>" : result.backendId)
        << " reason=" << result.reason
        << '\n';
}

void demonstrateLayer4() {
    std::cout << "\n=== Layer 4 service ===\n";

    LoadBalancer balancer(
        createBackends(),
        Algorithm::RoundRobin
    );

    std::map<std::string, int> distribution;

    for (int id = 1; id <= 12; ++id) {
        Request request{
            id,
            "192.0.2." + std::to_string(id),
            Protocol::TCP,
            "",
            "",
            ""
        };

        RoutingResult result = balancer.process(request);

        if (result.routed) {
            ++distribution[result.backendId];
        }
    }

    std::cout << "TCP connection distribution:\n";

    for (const auto& [backend, count] : distribution) {
        std::cout << "  " << backend << ": " << count << '\n';
    }
}

void demonstrateLayer7() {
    std::cout << "\n=== Layer 7 HTTP routing ===\n";

    LoadBalancer balancer(
        createBackends(),
        Algorithm::RoundRobin
    );

    balancer.addHttpRoute({
        "GET",
        "/api/",
        "app-01"
    });

    balancer.addHttpRoute({
        "GET",
        "/static/",
        "app-03"
    });

    std::vector<Request> requests{
        {
            100,
            "198.51.100.10",
            Protocol::HTTP,
            "GET",
            "/api/orders",
            ""
        },
        {
            101,
            "198.51.100.11",
            Protocol::HTTP,
            "GET",
            "/static/logo.svg",
            ""
        },
        {
            102,
            "198.51.100.12",
            Protocol::HTTP,
            "GET",
            "/",
            ""
        }
    };

    for (const Request& request : requests) {
        std::cout
            << protocolName(request.protocol)
            << " "
            << request.method
            << " "
            << request.path
            << " -> ";

        printResult(balancer.process(request));
    }
}

void demonstrateWeightedDistribution() {
    std::cout << "\n=== Weighted traffic distribution ===\n";

    LoadBalancer balancer(
        createBackends(),
        Algorithm::WeightedRoundRobin
    );

    for (int id = 0; id < 60; ++id) {
        balancer.process({
            id,
            "203.0.113." + std::to_string((id % 20) + 1),
            Protocol::TCP,
            "",
            "",
            ""
        });
    }

    for (const Backend& backend : balancer.backends()) {
        std::cout
            << backend.id
            << " weight=" << backend.weight
            << " requests=" << backend.totalRequests
            << '\n';
    }
}

void demonstrateHealthChecks() {
    std::cout << "\n=== Active health checks ===\n";

    LoadBalancer balancer(
        createBackends(),
        Algorithm::RoundRobin
    );

    for (const HealthResult& result : balancer.runHealthChecks()) {
        std::cout
            << result.backendId
            << " healthy=" << std::boolalpha << result.healthy
            << " reason=" << result.reason
            << '\n';
    }

    balancer.failHealthEndpoint("app-02");

    std::cout << "\nAfter app-02 begins failing health checks:\n";

    /*
     * The checker requires two consecutive failures. This models hysteresis:
     * a single transient failure does not immediately eject a backend.
     */
    balancer.runHealthChecks();
    balancer.runHealthChecks();

    for (int id = 200; id < 206; ++id) {
        printResult(balancer.process({
            id,
            "192.0.2." + std::to_string(id - 199),
            Protocol::TCP,
            "",
            "",
            ""
        }));
    }

    balancer.recoverHealthEndpoint("app-02");

    balancer.runHealthChecks();
    balancer.runHealthChecks();

    std::cout << "app-02 health endpoint recovered.\n";
}

void demonstrateStickySessions() {
    std::cout << "\n=== Sticky sessions ===\n";

    LoadBalancer balancer(
        createBackends(),
        Algorithm::StickySession
    );

    for (int id = 300; id < 305; ++id) {
        printResult(balancer.process({
            id,
            "198.51.100.40",
            Protocol::HTTP,
            "GET",
            "/checkout",
            "session-42"
        }));
    }

    std::string original =
        balancer.sessionBackend("session-42");

    std::cout
        << "session-42 initially mapped to "
        << original
        << '\n';

    /*
     * A sticky session does not override backend health. When the mapped
     * server fails its health checks, the session is invalidated and can be
     * rebound to an eligible server.
     */
    balancer.failHealthEndpoint(original);
    balancer.runHealthChecks();
    balancer.runHealthChecks();

    std::cout
        << "session-42 mapping after backend failure: "
        << balancer.sessionBackend("session-42")
        << '\n';

    printResult(balancer.process({
        305,
        "198.51.100.40",
        Protocol::HTTP,
        "GET",
        "/checkout",
        "session-42"
    }));

    std::cout
        << "session-42 new mapping: "
        << balancer.sessionBackend("session-42")
        << '\n';
}

void demonstrateConnectionDraining() {
    std::cout << "\n=== Connection draining ===\n";

    LoadBalancer balancer(
        createBackends(),
        Algorithm::RoundRobin
    );

    /*
     * Draining is useful during deployments. The server is removed from new
     * routing decisions while existing connections are allowed to finish.
     */
    balancer.drain("app-01");

    for (int id = 400; id < 406; ++id) {
        printResult(balancer.process({
            id,
            "203.0.113." + std::to_string(id),
            Protocol::TCP,
            "",
            "",
            ""
        }));
    }

    balancer.restore("app-01");

    std::cout << "app-01 restored to normal routing eligibility.\n";
}

void demonstrateCapacityFailure() {
    std::cout << "\n=== Capacity exhaustion ===\n";

    auto backends = createBackends();
    backends[0].maxConnections = 1;

    LoadBalancer balancer(
        std::move(backends),
        Algorithm::RoundRobin
    );

    /*
     * This simulation processes each request synchronously, so a normal
     * request releases its connection before the next one. The scenario is
     * represented by putting a backend into draining state, which also
     * removes it from the eligible set.
     */
    balancer.drain("app-01");

    printResult(balancer.process({
        500,
        "198.51.100.80",
        Protocol::TCP,
        "",
        "",
        ""
    }));

    balancer.restore("app-01");
}

void demonstrateApplicationFailure() {
    std::cout << "\n=== Application failure versus routing failure ===\n";

    auto backends = createBackends();
    backends[0].applicationHealthy = false;

    LoadBalancer balancer(
        std::move(backends),
        Algorithm::RoundRobin
    );

    RoutingResult result = balancer.process({
        600,
        "198.51.100.90",
        Protocol::HTTP,
        "GET",
        "/api/orders",
        ""
    });

    printResult(result);

    /*
     * The backend accepted the connection, so this is not a routing failure.
     * The application-level failure is separately recorded in metrics.
     */
    balancer.printMetrics();
}

void demonstrateLeastConnections() {
    std::cout << "\n=== Least-connections policy ===\n";

    auto backends = createBackends();

    /*
     * Simulate long-lived connections so that backend load differs before
     * the next routing decision. This is where least-connections differs
     * materially from simple round robin.
     */
    backends[0].activeConnections = 8;
    backends[1].activeConnections = 2;
    backends[2].activeConnections = 5;

    LoadBalancer balancer(
        std::move(backends),
        Algorithm::LeastConnections
    );

    printResult(balancer.process({
        700,
        "192.0.2.70",
        Protocol::TCP,
        "",
        "",
        ""
    }));
}

int main() {
    try {
        demonstrateLayer4();
        demonstrateLayer7();
        demonstrateWeightedDistribution();
        demonstrateHealthChecks();
        demonstrateStickySessions();
        demonstrateConnectionDraining();
        demonstrateCapacityFailure();
        demonstrateApplicationFailure();
        demonstrateLeastConnections();

        std::cout << "\n=== Governance observations ===\n";
        std::cout
            << "Layer 4 routing avoids application parsing, while Layer 7 "
               "routing can make decisions from HTTP metadata.\n";

        std::cout
            << "Health checks control backend eligibility, but their design "
               "must balance detection speed against false positives.\n";

        std::cout
            << "Sticky sessions preserve state locality but can reduce "
               "distribution quality and complicate failover.\n";

        std::cout
            << "Traffic policy should account for backend capacity, failure "
               "behavior, connection lifetime, and application correctness.\n";

        return 0;
    } catch (const std::exception& error) {
        std::cerr
            << "Load-balancing simulation failed: "
            << error.what()
            << '\n';

        return 1;
    }
}
