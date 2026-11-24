#include <algorithm>
#include <chrono>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

enum class ServiceState {
    STOPPED,
    STARTING,
    HEALTHY,
    UNHEALTHY,
    FAILED
};

enum class MergeMode {
    RECREATE,
    ROLLING
};

struct Service {
    string name;
    vector<string> dependencies;
    ServiceState state = ServiceState::STOPPED;
    bool healthcheckRequired = true;
    bool persistentStorage = false;
    int restartCount = 0;
};

struct DeploymentResult {
    bool success;
    vector<string> startupOrder;
    vector<string> failures;
};

class DeploymentEngine {
private:
    map<string, Service> services;

    static string stateName(ServiceState state) {
        switch (state) {
            case ServiceState::STOPPED: return "STOPPED";
            case ServiceState::STARTING: return "STARTING";
            case ServiceState::HEALTHY: return "HEALTHY";
            case ServiceState::UNHEALTHY: return "UNHEALTHY";
            case ServiceState::FAILED: return "FAILED";
        }
        return "UNKNOWN";
    }

    void visit(
        const string& name,
        map<string, int>& color,
        vector<string>& order
    ) {
        if (!services.count(name)) {
            throw invalid_argument("Unknown dependency: " + name);
        }

        if (color[name] == 1) {
            throw logic_error("Circular dependency detected at " + name);
        }

        if (color[name] == 2) {
            return;
        }

        color[name] = 1;

        for (const auto& dependency : services.at(name).dependencies) {
            visit(dependency, color, order);
        }

        color[name] = 2;
        order.push_back(name);
    }

public:
    void registerService(Service service) {
        if (service.name.empty()) {
            throw invalid_argument("Service name cannot be empty.");
        }

        if (services.count(service.name)) {
            throw invalid_argument("Duplicate service: " + service.name);
        }

        services.emplace(service.name, move(service));
    }

    vector<string> resolveStartupOrder() {
        map<string, int> color;
        vector<string> order;

        for (const auto& [name, service] : services) {
            visit(name, color, order);
        }

        return order;
    }

    void validateArchitecture() {
        for (const auto& [name, service] : services) {
            for (const auto& dependency : service.dependencies) {
                if (!services.count(dependency)) {
                    throw invalid_argument(
                        name + " depends on missing service " + dependency
                    );
                }
            }
        }

        resolveStartupOrder();

        if (!services.count("db") ||
            !services.count("backend") ||
            !services.count("frontend")) {
            throw logic_error("Required application services are missing.");
        }

        const auto& backend = services.at("backend");
        const auto& frontend = services.at("frontend");
        const auto& db = services.at("db");

        if (find(backend.dependencies.begin(),
                 backend.dependencies.end(), "db")
            == backend.dependencies.end()) {
            throw logic_error("Backend must depend on the database.");
        }

        if (find(frontend.dependencies.begin(),
                 frontend.dependencies.end(), "backend")
            == frontend.dependencies.end()) {
            throw logic_error("Frontend must depend on the backend.");
        }

        if (!db.persistentStorage) {
            throw logic_error("Database requires persistent storage.");
        }
    }

    DeploymentResult deploy(
        const map<string, bool>& simulatedHealth
    ) {
        DeploymentResult result{true, {}, {}};

        try {
            validateArchitecture();
            result.startupOrder = resolveStartupOrder();

            for (const auto& name : result.startupOrder) {
                auto& service = services.at(name);

                service.state = ServiceState::STARTING;

                cout << "Starting " << name << "...\n";

                bool dependenciesReady = true;

                for (const auto& dependency : service.dependencies) {
                    if (services.at(dependency).state != ServiceState::HEALTHY) {
                        dependenciesReady = false;
                        break;
                    }
                }

                if (!dependenciesReady) {
                    service.state = ServiceState::FAILED;
                    result.failures.push_back(
                        name + ": dependency unavailable"
                    );
                    result.success = false;
                    break;
                }

                auto health = simulatedHealth.find(name);
                bool healthy = health == simulatedHealth.end()
                    ? true
                    : health->second;

                if (service.healthcheckRequired && !healthy) {
                    service.state = ServiceState::UNHEALTHY;
                    service.restartCount++;

                    result.failures.push_back(
                        name + ": healthcheck failed"
                    );

                    result.success = false;
                    break;
                }

                service.state = ServiceState::HEALTHY;

                cout << name << " is HEALTHY\n";
            }

        } catch (const exception& error) {
            result.success = false;
            result.failures.push_back(error.what());
        }

        return result;
    }

    bool mergeEligible() const {
        return all_of(
            services.begin(),
            services.end(),
            [](const auto& entry) {
                return entry.second.state == ServiceState::HEALTHY;
            }
        );
    }

    void printReport() const {
        cout << "\nDEPLOYMENT REPORT\n";
        cout << "-----------------\n";

        for (const auto& [name, service] : services) {
            cout << name << ": "
                 << stateName(service.state)
                 << ", restarts=" << service.restartCount
                 << ", persistent="
                 << (service.persistentStorage ? "yes" : "no")
                 << '\n';
        }

        cout << "Application readiness: "
             << (mergeEligible() ? "READY" : "NOT READY")
             << '\n';
    }
};

int main() {
    try {
        DeploymentEngine engine;

        engine.registerService({
            "db",
            {},
            ServiceState::STOPPED,
            true,
            true
        });

        engine.registerService({
            "backend",
            {"db"},
            ServiceState::STOPPED,
            true,
            false
        });

        engine.registerService({
            "frontend",
            {"backend"},
            ServiceState::STOPPED,
            true,
            false
        });

        engine.validateArchitecture();

        cout << "Scenario 1: Successful deployment\n";

        auto successful = engine.deploy({
            {"db", true},
            {"backend", true},
            {"frontend", true}
        });

        engine.printReport();

        cout << "\nScenario 2: Backend healthcheck failure\n";

        DeploymentEngine failingEngine;

        failingEngine.registerService({
            "db", {}, ServiceState::STOPPED, true, true
        });

        failingEngine.registerService({
            "backend", {"db"}, ServiceState::STOPPED, true, false
        });

        failingEngine.registerService({
            "frontend", {"backend"}, ServiceState::STOPPED, true, false
        });

        auto failed = failingEngine.deploy({
            {"db", true},
            {"backend", false}
        });

        failingEngine.printReport();

        for (const auto& failure : failed.failures) {
            cerr << "FAILURE: " << failure << '\n';
        }

        cout << "\nScenario 3: Circular dependency detection\n";

        try {
            DeploymentEngine invalid;

            invalid.registerService({
                "alpha", {"beta"}, ServiceState::STOPPED, true, false
            });

            invalid.registerService({
                "beta", {"alpha"}, ServiceState::STOPPED, true, false
            });

            invalid.resolveStartupOrder();

        } catch (const exception& error) {
            cout << "Expected validation error: "
                 << error.what() << '\n';
        }

        return successful.success && !failed.success ? 0 : 1;

    } catch (const exception& error) {
        cerr << "Deployment engine error: "
             << error.what() << '\n';
        return 1;
    }
}
