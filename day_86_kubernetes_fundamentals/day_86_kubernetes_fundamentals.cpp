#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <numeric>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

using namespace std;

/*
 * Kubernetes Fundamentals: Cluster Governance and Scheduling Engine
 *
 * Implements:
 * - Cluster and worker-node modeling
 * - CPU and memory resource accounting
 * - Pod scheduling
 * - Node health conditions
 * - Deployment replica reconciliation
 * - Readiness and health evaluation
 * - Service endpoint discovery
 * - Rolling update eligibility
 * - Failure recovery
 *
 * C++17, standard library only.
 */

enum class NodeState {
    Ready,
    NotReady,
    Draining
};

enum class PodState {
    Pending,
    Running,
    Failed,
    Terminating
};

enum class WorkloadState {
    Active,
    Degraded,
    Complete
};

struct Resources {
    int cpuMillicores;
    int memoryMB;

    void validate() const {
        if (cpuMillicores <= 0 || memoryMB <= 0) {
            throw invalid_argument(
                "Resource requests must be positive."
            );
        }
    }
};

struct Pod {
    string id;
    string name;
    string image;
    string deployment;
    map<string, string> labels;
    Resources requests;
    PodState state = PodState::Pending;
    string nodeName;
    bool ready = false;
    int restartCount = 0;
    int revision = 1;
};

struct Node {
    string name;
    int cpuCapacity;
    int memoryCapacity;
    NodeState state = NodeState::Ready;
    vector<Pod> pods;

    int allocatedCPU() const {
        int total = 0;

        for (const auto& pod : pods) {
            if (pod.state == PodState::Running ||
                pod.state == PodState::Pending) {
                total += pod.requests.cpuMillicores;
            }
        }

        return total;
    }

    int allocatedMemory() const {
        int total = 0;

        for (const auto& pod : pods) {
            if (pod.state == PodState::Running ||
                pod.state == PodState::Pending) {
                total += pod.requests.memoryMB;
            }
        }

        return total;
    }

    bool canHost(const Pod& pod) const {
        return state == NodeState::Ready &&
            allocatedCPU() + pod.requests.cpuMillicores
                <= cpuCapacity &&
            allocatedMemory() + pod.requests.memoryMB
                <= memoryCapacity;
    }

    double cpuUtilization() const {
        if (cpuCapacity == 0) return 1.0;

        return static_cast<double>(allocatedCPU()) /
               cpuCapacity;
    }
};

struct Deployment {
    string name;
    string image;
    map<string, string> selector;
    Resources requests;
    int desiredReplicas;
    int generation = 1;
    int revision = 1;
    vector<Pod> pods;
};

struct Service {
    string name;
    map<string, string> selector;
    int port;
    int targetPort;
};

class Cluster {
private:
    string name;
    vector<Node> nodes;
    map<string, Deployment> deployments;
    map<string, Service> services;
    int podSequence = 0;
    int eventSequence = 0;

    static bool validName(const string& value) {
        if (value.empty() || value.size() > 63) {
            return false;
        }

        if (!isalnum(static_cast<unsigned char>(value.front())) ||
            !isalnum(static_cast<unsigned char>(value.back()))) {
            return false;
        }

        return all_of(value.begin(), value.end(), [](char c) {
            return isalnum(static_cast<unsigned char>(c)) ||
                   c == '-';
        });
    }

    void event(const string& type, const string& detail) {
        cout << "[EVENT " << ++eventSequence << "] "
             << type << ": " << detail << '\n';
    }

    bool matches(
        const Pod& pod,
        const map<string, string>& selector
    ) const {
        for (const auto& [key, value] : selector) {
            auto it = pod.labels.find(key);

            if (it == pod.labels.end() || it->second != value) {
                return false;
            }
        }

        return true;
    }

    Node* findNode(const string& nodeName) {
        for (auto& node : nodes) {
            if (node.name == nodeName) {
                return &node;
            }
        }

        return nullptr;
    }

    void removeFromNode(const Pod& pod) {
        Node* node = findNode(pod.nodeName);

        if (!node) return;

        auto& list = node->pods;

        list.erase(
            remove_if(
                list.begin(),
                list.end(),
                [&](const Pod& current) {
                    return current.id == pod.id;
                }
            ),
            list.end()
        );
    }

    Pod createPod(const Deployment& deployment) {
        Pod pod;

        pod.id = "pod-" + to_string(++podSequence);
        pod.name = deployment.name + "-" +
                   to_string(podSequence);
        pod.image = deployment.image;
        pod.deployment = deployment.name;
        pod.labels = deployment.selector;
        pod.requests = deployment.requests;
        pod.revision = deployment.revision;

        return pod;
    }

public:
    explicit Cluster(string clusterName)
        : name(move(clusterName)) {

        if (!validName(name)) {
            throw invalid_argument("Invalid cluster name.");
        }
    }

    void addNode(Node node) {
        if (!validName(node.name) ||
            node.cpuCapacity <= 0 ||
            node.memoryCapacity <= 0) {
            throw invalid_argument("Invalid node configuration.");
        }

        if (findNode(node.name)) {
            throw invalid_argument("Duplicate node.");
        }

        nodes.push_back(move(node));

        event("NODE_ADDED", nodes.back().name);
    }

    void addDeployment(Deployment deployment) {
        if (!validName(deployment.name) ||
            deployment.image.empty() ||
            deployment.desiredReplicas < 0 ||
            deployment.selector.empty()) {
            throw invalid_argument("Invalid deployment.");
        }

        deployment.requests.validate();

        if (deployments.count(deployment.name)) {
            throw invalid_argument("Duplicate deployment.");
        }

        deployments.emplace(
            deployment.name,
            move(deployment)
        );

        event("DEPLOYMENT_CREATED", deployments.rbegin()->first);
    }

    void addService(Service service) {
        if (!validName(service.name) ||
            service.selector.empty() ||
            service.port < 1 || service.port > 65535 ||
            service.targetPort < 1 ||
            service.targetPort > 65535) {
            throw invalid_argument("Invalid service.");
        }

        if (services.count(service.name)) {
            throw invalid_argument("Duplicate service.");
        }

        string serviceName = service.name;
        services.emplace(serviceName, move(service));

        event("SERVICE_CREATED", serviceName);
    }

    optional<string> schedule(Pod& pod) {
        vector<Node*> candidates;

        for (auto& node : nodes) {
            if (node.canHost(pod)) {
                candidates.push_back(&node);
            }
        }

        if (candidates.empty()) {
            return nullopt;
        }

        sort(
            candidates.begin(),
            candidates.end(),
            [](const Node* a, const Node* b) {
                if (a->cpuUtilization() != b->cpuUtilization()) {
                    return a->cpuUtilization() <
                           b->cpuUtilization();
                }

                return a->name < b->name;
            }
        );

        Node* selected = candidates.front();

        pod.nodeName = selected->name;
        pod.state = PodState::Running;
        pod.ready = true;

        selected->pods.push_back(pod);

        event("POD_SCHEDULED", pod.name + " -> " + selected->name);

        return selected->name;
    }

    int activeReplicas(const Deployment& deployment) const {
        return static_cast<int>(count_if(
            deployment.pods.begin(),
            deployment.pods.end(),
            [](const Pod& pod) {
                return pod.state == PodState::Running;
            }
        ));
    }

    bool reconcile(const string& deploymentName) {
        auto it = deployments.find(deploymentName);

        if (it == deployments.end()) {
            throw out_of_range("Deployment not found.");
        }

        Deployment& deployment = it->second;

        int active = activeReplicas(deployment);

        while (active < deployment.desiredReplicas) {
            Pod pod = createPod(deployment);

            if (!schedule(pod)) {
                event("SCHEDULING_FAILED", pod.name);
                return false;
            }

            deployment.pods.push_back(move(pod));
            ++active;
        }

        while (active > deployment.desiredReplicas) {
            auto itPod = find_if(
                deployment.pods.begin(),
                deployment.pods.end(),
                [](const Pod& pod) {
                    return pod.state == PodState::Running;
                }
            );

            if (itPod == deployment.pods.end()) break;

            event("POD_TERMINATING", itPod->name);

            removeFromNode(*itPod);
            itPod->state = PodState::Terminating;
            itPod->ready = false;

            deployment.pods.erase(itPod);
            --active;
        }

        event(
            "RECONCILIATION_COMPLETED",
            deploymentName + " desired=" +
            to_string(deployment.desiredReplicas) +
            " actual=" + to_string(active)
        );

        return active == deployment.desiredReplicas;
    }

    void scale(const string& deploymentName, int replicas) {
        if (replicas < 0) {
            throw invalid_argument("Negative replica count.");
        }

        auto it = deployments.find(deploymentName);

        if (it == deployments.end()) {
            throw out_of_range("Deployment not found.");
        }

        it->second.desiredReplicas = replicas;
        ++it->second.generation;

        event("DEPLOYMENT_SCALED", deploymentName);

        reconcile(deploymentName);
    }

    void failPod(
        const string& deploymentName,
        const string& podId
    ) {
        auto it = deployments.find(deploymentName);

        if (it == deployments.end()) {
            throw out_of_range("Deployment not found.");
        }

        Deployment& deployment = it->second;

        auto pod = find_if(
            deployment.pods.begin(),
            deployment.pods.end(),
            [&](const Pod& item) {
                return item.id == podId;
            }
        );

        if (pod == deployment.pods.end()) {
            throw out_of_range("Pod not found.");
        }

        removeFromNode(*pod);

        pod->state = PodState::Failed;
        pod->ready = false;
        pod->nodeName.clear();
        ++pod->restartCount;

        event("POD_FAILED", pod->name);

        reconcile(deploymentName);
    }

    void markNodeNotReady(const string& nodeName) {
        Node* node = findNode(nodeName);

        if (!node) {
            throw out_of_range("Node not found.");
        }

        node->state = NodeState::NotReady;

        vector<string> affected;

        for (const auto& pod : node->pods) {
            affected.push_back(pod.id);
        }

        for (const string& id : affected) {
            auto it = find_if(
                deployments.begin(),
                deployments.end(),
                [&](auto& entry) {
                    return any_of(
                        entry.second.pods.begin(),
                        entry.second.pods.end(),
                        [&](const Pod& pod) {
                            return pod.id == id;
                        }
                    );
                }
            );

            if (it != deployments.end()) {
                auto& workload = it->second;

                auto pod = find_if(
                    workload.pods.begin(),
                    workload.pods.end(),
                    [&](const Pod& item) {
                        return item.id == id;
                    }
                );

                if (pod != workload.pods.end()) {
                    pod->state = PodState::Failed;
                    pod->ready = false;
                    pod->nodeName.clear();
                    ++pod->restartCount;
                }
            }
        }

        node->pods.clear();

        event("NODE_NOT_READY", nodeName);

        for (auto& [name, deployment] : deployments) {
            reconcile(name);
        }
    }

    bool rollingUpdate(
        const string& deploymentName,
        const string& newImage
    ) {
        auto it = deployments.find(deploymentName);

        if (it == deployments.end() || newImage.empty()) {
            throw invalid_argument("Invalid rolling update.");
        }

        Deployment& deployment = it->second;

        const string oldImage = deployment.image;
        const int oldRevision = deployment.revision;

        deployment.image = newImage;
        ++deployment.revision;
        ++deployment.generation;

        vector<Pod> oldPods;

        for (const auto& pod : deployment.pods) {
            if (pod.state == PodState::Running) {
                oldPods.push_back(pod);
            }
        }

        vector<string> replacements;

        for (const Pod& oldPod : oldPods) {
            Pod replacement = createPod(deployment);

            if (!schedule(replacement)) {
                for (auto& pod : deployment.pods) {
                    if (find(
                        replacements.begin(),
                        replacements.end(),
                        pod.id
                    ) != replacements.end()) {
                        removeFromNode(pod);
                        pod.state = PodState::Failed;
                    }
                }

                deployment.pods.erase(
                    remove_if(
                        deployment.pods.begin(),
                        deployment.pods.end(),
                        [](const Pod& pod) {
                            return pod.state == PodState::Failed;
                        }
                    ),
                    deployment.pods.end()
                );

                deployment.image = oldImage;
                deployment.revision = oldRevision;
                --deployment.generation;

                event("ROLLING_UPDATE_FAILED", deploymentName);

                reconcile(deploymentName);
                return false;
            }

            replacements.push_back(replacement.id);
            deployment.pods.push_back(replacement);

            auto old = find_if(
                deployment.pods.begin(),
                deployment.pods.end(),
                [&](const Pod& pod) {
                    return pod.id == oldPod.id;
                }
            );

            if (old != deployment.pods.end()) {
                removeFromNode(*old);
                deployment.pods.erase(old);
            }
        }

        event("ROLLING_UPDATE_COMPLETED", deploymentName);
        return true;
    }

    vector<string> serviceEndpoints(
        const string& serviceName
    ) const {
        auto service = services.find(serviceName);

        if (service == services.end()) {
            throw out_of_range("Service not found.");
        }

        vector<string> endpoints;

        for (const auto& node : nodes) {
            for (const auto& pod : node.pods) {
                if (
                    pod.state == PodState::Running &&
                    pod.ready &&
                    matches(pod, service->second.selector)
                ) {
                    endpoints.push_back(
                        pod.name + "@" + node.name + ":" +
                        to_string(service->second.targetPort)
                    );
                }
            }
        }

        return endpoints;
    }

    WorkloadState status(const string& name) const {
        const auto& deployment = deployments.at(name);

        const int ready = static_cast<int>(count_if(
            deployment.pods.begin(),
            deployment.pods.end(),
            [](const Pod& pod) {
                return pod.state == PodState::Running &&
                       pod.ready;
            }
        ));

        if (ready == deployment.desiredReplicas) {
            return WorkloadState::Complete;
        }

        if (ready == 0 && deployment.desiredReplicas > 0) {
            return WorkloadState::Degraded;
        }

        return WorkloadState::Active;
    }

    void report() const {
        cout << "\nCLUSTER: " << name << "\n";

        cout << "\nNODE RESOURCE REPORT\n";

        for (const auto& node : nodes) {
            cout << left << setw(15) << node.name
                 << " CPU " << node.allocatedCPU()
                 << "/" << node.cpuCapacity
                 << " millicores, Memory "
                 << node.allocatedMemory()
                 << "/" << node.memoryCapacity
                 << " MB, Pods " << node.pods.size()
                 << ", State ";

            switch (node.state) {
                case NodeState::Ready:
                    cout << "Ready";
                    break;
                case NodeState::NotReady:
                    cout << "NotReady";
                    break;
                case NodeState::Draining:
                    cout << "Draining";
                    break;
            }

            cout << '\n';
        }

        cout << "\nDEPLOYMENT REPORT\n";

        for (const auto& [name, deployment] : deployments) {
            cout << name
                 << " desired=" << deployment.desiredReplicas
                 << " running=" << activeReplicas(deployment)
                 << " image=" << deployment.image
                 << " generation=" << deployment.generation
                 << '\n';
        }
    }
};


int main() {
    try {
        Cluster cluster("production-cluster");

        cluster.addNode({
            "worker-01", 4000, 8192
        });

        cluster.addNode({
            "worker-02", 4000, 8192
        });

        cluster.addNode({
            "worker-03", 2000, 4096
        });

        Deployment deployment;

        deployment.name = "payment-api";
        deployment.image = "registry.example.com/payment:v1";
        deployment.selector = {
            {"app", "payment-api"},
            {"tier", "backend"}
        };
        deployment.requests = {500, 512};
        deployment.desiredReplicas = 3;

        cluster.addDeployment(deployment);

        cluster.addService({
            "payment-service",
            {{"app", "payment-api"}},
            80,
            8080
        });

        cout << "\nINITIAL DEPLOYMENT\n";
        cluster.reconcile("payment-api");
        cluster.report();

        cout << "\nSERVICE DISCOVERY\n";

        for (const auto& endpoint :
             cluster.serviceEndpoints("payment-service")) {
            cout << endpoint << '\n';
        }

        cout << "\nSIMULATING POD FAILURE\n";

        const auto& current =
            cluster.serviceEndpoints("payment-service");

        if (!current.empty()) {
            const string podName =
                current.front().substr(
                    0,
                    current.front().find('@')
                );

            // Locate the pod by its generated name.
            // The test uses the deployment's recorded identifiers.
            (void)podName;
        }

        cluster.failPod(
            "payment-api",
            "pod-1"
        );

        cout << "\nSCALING TO FIVE REPLICAS\n";
        cluster.scale("payment-api", 5);

        cout << "\nROLLING UPDATE\n";

        bool updated = cluster.rollingUpdate(
            "payment-api",
            "registry.example.com/payment:v2"
        );

        cout << "Update accepted: "
             << boolalpha << updated << '\n';

        cout << "\nNODE FAILURE\n";
        cluster.markNodeNotReady("worker-03");

        cluster.report();

        cout << "\nFINAL SERVICE ENDPOINTS\n";

        for (const auto& endpoint :
             cluster.serviceEndpoints("payment-service")) {
            cout << endpoint << '\n';
        }

        cout << "\nSimulation completed.\n";

    } catch (const exception& error) {
        cerr << "Cluster error: "
             << error.what() << '\n';

        return 1;
    }

    return 0;
}
