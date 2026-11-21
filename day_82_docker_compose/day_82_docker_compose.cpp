#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <queue>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

using namespace std;

/*
 * Docker Compose Deployment Planner
 *
 * C++17 implementation of:
 * - Service configuration
 * - Dependency graph validation
 * - Startup ordering
 * - Health conditions
 * - Network connectivity
 * - Volume persistence
 * - Resource allocation
 * - Merge-like deployment eligibility checks
 *
 * The planner does not create actual Docker containers.
 */

enum class ServiceState {
    Created,
    Starting,
    Running,
    Healthy,
    Unhealthy,
    Stopped,
    Failed
};

enum class DependencyCondition {
    Started,
    Healthy,
    Completed
};

enum class RestartPolicy {
    No,
    Always,
    UnlessStopped,
    OnFailure
};

enum class VolumeType {
    Persistent,
    Temporary
};

struct Dependency {
    string service;
    DependencyCondition condition;
};

struct PortMapping {
    int hostPort;
    int containerPort;
};

struct Volume {
    string name;
    VolumeType type;
    bool readOnly = false;
};

struct Network {
    string name;
    bool internal = false;
};

struct Service {
    string name;
    string image;

    vector<Dependency> dependencies;
    set<string> networks;
    vector<Volume> volumes;
    vector<PortMapping> ports;

    int memoryMB = 256;
    double cpu = 1.0;

    bool healthcheck = false;
    RestartPolicy restartPolicy = RestartPolicy::No;

    ServiceState state = ServiceState::Created;
    int restartCount = 0;
};

class ComposeError : public runtime_error {
public:
    explicit ComposeError(const string& message)
        : runtime_error(message) {}
};

class DeploymentPlanner {
private:
    map<string, Service> services;
    map<string, Network> networks;
    map<string, Volume> volumes;

    int availableMemoryMB;
    double availableCPU;

    vector<string> deploymentEvents;

    void record(const string& event) {
        deploymentEvents.push_back(event);
        cout << "[EVENT] " << event << '\n';
    }

    bool dependencySatisfied(const Dependency& dependency) const {
        const auto& service = services.at(dependency.service);

        switch (dependency.condition) {
            case DependencyCondition::Started:
                return service.state == ServiceState::Running ||
                       service.state == ServiceState::Healthy;

            case DependencyCondition::Healthy:
                return service.state == ServiceState::Healthy;

            case DependencyCondition::Completed:
                return service.state == ServiceState::Stopped;
        }

        return false;
    }

public:
    DeploymentPlanner(
        int memoryMB,
        double cpu
    ) : availableMemoryMB(memoryMB),
        availableCPU(cpu) {

        if (memoryMB <= 0 || cpu <= 0) {
            throw ComposeError(
                "Host resources must be positive."
            );
        }
    }

    void addNetwork(const Network& network) {
        if (network.name.empty()) {
            throw ComposeError("Network name is required.");
        }

        if (networks.count(network.name)) {
            throw ComposeError("Duplicate network.");
        }

        networks.emplace(network.name, network);
    }

    void addVolume(const Volume& volume) {
        if (volume.name.empty()) {
            throw ComposeError("Volume name is required.");
        }

        if (volumes.count(volume.name)) {
            throw ComposeError("Duplicate volume.");
        }

        volumes.emplace(volume.name, volume);
    }

    void addService(const Service& service) {
        if (service.name.empty() || service.image.empty()) {
            throw ComposeError(
                "Service name and image are required."
            );
        }

        if (services.count(service.name)) {
            throw ComposeError(
                "Duplicate service: " + service.name
            );
        }

        if (service.memoryMB <= 0 ||
            !isfinite(service.cpu) ||
            service.cpu <= 0) {
            throw ComposeError(
                "Invalid resource limits."
            );
        }

        set<int> hostPorts;

        for (const auto& port : service.ports) {
            if (port.hostPort < 1 ||
                port.hostPort > 65535 ||
                port.containerPort < 1 ||
                port.containerPort > 65535) {
                throw ComposeError("Invalid port mapping.");
            }
        }

        services.emplace(service.name, service);
    }

    vector<string> topologicalOrder() const {
        unordered_map<string, int> indegree;
        unordered_map<string, vector<string>> adjacency;

        for (const auto& [name, service] : services) {
            indegree[name] = 0;
        }

        for (const auto& [name, service] : services) {
            for (const auto& dependency : service.dependencies) {
                if (!services.count(dependency.service)) {
                    throw ComposeError(
                        name + " depends on unknown service " +
                        dependency.service
                    );
                }

                if (dependency.service == name) {
                    throw ComposeError(
                        "Self-dependency: " + name
                    );
                }

                adjacency[dependency.service].push_back(name);
                indegree[name]++;
            }
        }

        priority_queue<
            string,
            vector<string>,
            greater<string>
        > ready;

        for (const auto& [name, degree] : indegree) {
            if (degree == 0) {
                ready.push(name);
            }
        }

        vector<string> order;

        while (!ready.empty()) {
            string current = ready.top();
            ready.pop();

            order.push_back(current);

            for (const string& next : adjacency[current]) {
                if (--indegree[next] == 0) {
                    ready.push(next);
                }
            }
        }

        if (order.size() != services.size()) {
            throw ComposeError(
                "Circular dependency detected."
            );
        }

        return order;
    }

    void validate() const {
        if (services.empty()) {
            throw ComposeError(
                "Deployment requires services."
            );
        }

        map<int, string> hostPorts;

        for (const auto& [name, service] : services) {
            for (const string& network : service.networks) {
                if (!networks.count(network)) {
                    throw ComposeError(
                        name + " references unknown network " +
                        network
                    );
                }
            }

            for (const auto& volume : service.volumes) {
                if (!volumes.count(volume.name)) {
                    throw ComposeError(
                        name + " references unknown volume " +
                        volume.name
                    );
                }
            }

            for (const auto& port : service.ports) {
                if (hostPorts.count(port.hostPort)) {
                    throw ComposeError(
                        "Host port collision: " +
                        to_string(port.hostPort)
                    );
                }

                hostPorts[port.hostPort] = name;
            }
        }

        topologicalOrder();
    }

    void startService(const string& name) {
        if (!services.count(name)) {
            throw ComposeError("Unknown service: " + name);
        }

        Service& service = services.at(name);

        if (service.state == ServiceState::Running ||
            service.state == ServiceState::Healthy) {
            return;
        }

        for (const auto& dependency : service.dependencies) {
            if (!dependencySatisfied(dependency)) {
                throw ComposeError(
                    "Dependency condition not satisfied for " +
                    name + ": " + dependency.service
                );
            }
        }

        service.state = ServiceState::Starting;

        record(name + " STARTING");

        service.state = ServiceState::Running;

        record(name + " RUNNING");

        if (service.healthcheck) {
            checkHealth(name, true);
        }
    }

    void checkHealth(
        const string& name,
        bool successful
    ) {
        if (!services.count(name)) {
            throw ComposeError("Unknown service.");
        }

        Service& service = services.at(name);

        if (service.state != ServiceState::Running &&
            service.state != ServiceState::Healthy &&
            service.state != ServiceState::Unhealthy) {
            throw ComposeError(
                "Service is not eligible for healthcheck."
            );
        }

        service.state = successful
            ? ServiceState::Healthy
            : ServiceState::Unhealthy;

        record(
            name +
            (successful ? " HEALTHY" : " UNHEALTHY")
        );
    }

    void startAll() {
        validate();

        const auto order = topologicalOrder();

        cout << "\nDEPENDENCY ORDER\n";

        for (const string& name : order) {
            cout << name << '\n';
            startService(name);
        }
    }

    vector<string> networkPeers(
        const string& serviceName
    ) const {
        if (!services.count(serviceName)) {
            throw ComposeError("Unknown service.");
        }

        const auto& service = services.at(serviceName);

        vector<string> peers;

        for (const auto& [name, other] : services) {
            if (name == serviceName) {
                continue;
            }

            vector<string> common;

            set_intersection(
                service.networks.begin(),
                service.networks.end(),
                other.networks.begin(),
                other.networks.end(),
                back_inserter(common)
            );

            if (!common.empty()) {
                peers.push_back(name);
            }
        }

        return peers;
    }

    void checkResources() const {
        long long requiredMemory = 0;
        double requiredCPU = 0;

        for (const auto& [name, service] : services) {
            requiredMemory += service.memoryMB;
            requiredCPU += service.cpu;
        }

        cout << "\nRESOURCE ANALYSIS\n";

        cout << "Required memory: "
             << requiredMemory << " MB\n";

        cout << "Available memory: "
             << availableMemoryMB << " MB\n";

        cout << "Required CPU: "
             << fixed << setprecision(2)
             << requiredCPU << '\n';

        cout << "Available CPU: "
             << availableCPU << '\n';

        if (requiredMemory > availableMemoryMB ||
            requiredCPU > availableCPU) {
            throw ComposeError(
                "Configured resource requests exceed host capacity."
            );
        }
    }

    void failService(const string& name) {
        if (!services.count(name)) {
            throw ComposeError("Unknown service.");
        }

        services.at(name).state = ServiceState::Failed;
        record(name + " FAILED");
    }

    void restartService(const string& name) {
        if (!services.count(name)) {
            throw ComposeError("Unknown service.");
        }

        Service& service = services.at(name);

        if (service.restartPolicy == RestartPolicy::No) {
            throw ComposeError(
                "Restart policy prevents restart."
            );
        }

        service.restartCount++;
        service.state = ServiceState::Created;

        record(
            name + " RESTART ATTEMPT " +
            to_string(service.restartCount)
        );

        startService(name);
    }

    void stopAll() {
        auto order = topologicalOrder();
        reverse(order.begin(), order.end());

        for (const string& name : order) {
            services.at(name).state = ServiceState::Stopped;
            record(name + " STOPPED");
        }
    }

    void report() const {
        cout << "\nSERVICE REPORT\n";

        for (const auto& [name, service] : services) {
            cout << left << setw(12) << name
                 << setw(18) << service.image
                 << "Memory=" << service.memoryMB
                 << "MB CPU=" << service.cpu
                 << " Restarts=" << service.restartCount
                 << '\n';
        }

        cout << "\nEVENT COUNT: "
             << deploymentEvents.size()
             << '\n';
    }
};

int main() {
    try {
        DeploymentPlanner planner(4096, 8.0);

        planner.addNetwork({
            "frontend",
            false
        });

        planner.addNetwork({
            "backend",
            true
        });

        planner.addVolume({
            "postgres_data",
            VolumeType::Persistent
        });

        planner.addVolume({
            "cache_data",
            VolumeType::Persistent
        });

        Service database;
        database.name = "database";
        database.image = "postgres:18";
        database.networks = {"backend"};
        database.volumes = {
            {"postgres_data", VolumeType::Persistent}
        };
        database.memoryMB = 1024;
        database.cpu = 2.0;
        database.healthcheck = true;
        database.restartPolicy = RestartPolicy::UnlessStopped;

        planner.addService(database);

        Service cache;
        cache.name = "cache";
        cache.image = "redis:7-alpine";
        cache.networks = {"backend"};
        cache.volumes = {
            {"cache_data", VolumeType::Persistent}
        };
        cache.memoryMB = 256;
        cache.cpu = 0.5;
        cache.healthcheck = true;
        cache.restartPolicy = RestartPolicy::Always;

        planner.addService(cache);

        Service api;
        api.name = "api";
        api.image = "example/api:1.0";
        api.dependencies = {
            {"database", DependencyCondition::Healthy},
            {"cache", DependencyCondition::Started}
        };
        api.networks = {"frontend", "backend"};
        api.ports = {{8080, 8080}};
        api.memoryMB = 512;
        api.cpu = 1.5;
        api.healthcheck = true;
        api.restartPolicy = RestartPolicy::OnFailure;

        planner.addService(api);

        Service web;
        web.name = "web";
        web.image = "example/web:1.0";
        web.dependencies = {
            {"api", DependencyCondition::Healthy}
        };
        web.networks = {"frontend"};
        web.ports = {{3000, 3000}};
        web.memoryMB = 256;
        web.cpu = 1.0;

        planner.addService(web);

        planner.validate();
        planner.checkResources();

        planner.startAll();

        cout << "\nDATABASE NETWORK PEERS\n";

        for (const auto& peer :
             planner.networkPeers("database")) {
            cout << peer << '\n';
        }

        cout << "\nFAILURE RECOVERY\n";

        planner.failService("api");
        planner.restartService("api");

        planner.report();

        cout << "\nSHUTDOWN\n";
        planner.stopAll();

        cout << "\nDEPLOYMENT COMPLETED\n";

    } catch (const exception& error) {
        cerr << "DEPLOYMENT ERROR: "
             << error.what() << '\n';

        return 1;
    }

    return 0;
}
