#include <algorithm>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include <optional>
#include <numeric>

using namespace std;

/*
 * Kubernetes Control Plane
 *
 * C++17 implementation of a cluster-state management engine.
 *
 * Components:
 * - API server
 * - Versioned etcd-style state store
 * - Node registry
 * - Scheduler
 * - Deployment controller
 * - Pod lifecycle
 * - Reconciliation
 * - Resource allocation
 * - Cluster validation
 */

enum class PodPhase {
    Pending,
    Running,
    Failed,
    Succeeded
};

enum class NodeCondition {
    Ready,
    NotReady
};

enum class ResourceKind {
    Node,
    Pod,
    Deployment
};


string toString(PodPhase phase) {
    switch (phase) {
        case PodPhase::Pending: return "Pending";
        case PodPhase::Running: return "Running";
        case PodPhase::Failed: return "Failed";
        case PodPhase::Succeeded: return "Succeeded";
    }

    return "Unknown";
}


class ControlPlaneError : public runtime_error {
public:
    explicit ControlPlaneError(const string& message)
        : runtime_error(message) {}
};


class ValidationError : public ControlPlaneError {
public:
    using ControlPlaneError::ControlPlaneError;
};


class ConflictError : public ControlPlaneError {
public:
    using ControlPlaneError::ControlPlaneError;
};


class NotFoundError : public ControlPlaneError {
public:
    using ControlPlaneError::ControlPlaneError;
};


// ============================================================
// DOMAIN STRUCTURES
// ============================================================

struct Resource {
    string name;
    string namespaceName = "default";
    string uid;
    unsigned long long resourceVersion = 0;
    map<string, string> labels;
};


struct Node : Resource {
    int cpuCapacity = 0;
    int memoryCapacity = 0;
    int cpuUsed = 0;
    int memoryUsed = 0;
    NodeCondition condition = NodeCondition::Ready;

    int availableCPU() const {
        return cpuCapacity - cpuUsed;
    }

    int availableMemory() const {
        return memoryCapacity - memoryUsed;
    }
};


struct Pod : Resource {
    string image;
    int cpuRequest = 1;
    int memoryRequest = 256;
    string owner;
    optional<string> nodeName;
    PodPhase phase = PodPhase::Pending;
};


struct Deployment : Resource {
    int desiredReplicas = 1;
    string image;
    int cpuRequest = 1;
    int memoryRequest = 256;
    map<string, string> selector;
};


// ============================================================
// VALIDATION
// ============================================================

void validateName(const string& name) {

    if (
        name.empty() ||
        name.size() > 253 ||
        name.front() == '-' ||
        name.back() == '-'
    ) {
        throw ValidationError("Invalid resource name");
    }

    for (unsigned char ch : name) {
        if (
            !islower(ch) &&
            !isdigit(ch) &&
            ch != '-'
        ) {
            throw ValidationError(
                "Names must use lowercase letters, digits and hyphens"
            );
        }
    }
}


void validatePod(const Pod& pod) {

    validateName(pod.name);
    validateName(pod.namespaceName);

    if (pod.image.empty()) {
        throw ValidationError("Pod image is required");
    }

    if (pod.cpuRequest <= 0 || pod.memoryRequest <= 0) {
        throw ValidationError("Invalid resource requests");
    }
}


void validateDeployment(const Deployment& deployment) {

    validateName(deployment.name);

    if (
        deployment.desiredReplicas < 0 ||
        deployment.desiredReplicas > 10000
    ) {
        throw ValidationError("Invalid replica count");
    }

    if (deployment.image.empty()) {
        throw ValidationError("Deployment image is required");
    }

    if (deployment.selector.empty()) {
        throw ValidationError("Deployment selector is required");
    }

    if (
        deployment.cpuRequest <= 0 ||
        deployment.memoryRequest <= 0
    ) {
        throw ValidationError("Invalid deployment resources");
    }
}


// ============================================================
// ETCD-STYLE STATE STORE
// ============================================================

template <typename T>
struct VersionedValue {
    T value;
    unsigned long long version;
};


template <typename T>
class StateStore {

private:
    map<string, VersionedValue<T>> records;
    unsigned long long revision = 0;

public:

    unsigned long long getRevision() const {
        return revision;
    }

    T get(const string& key) const {

        auto it = records.find(key);

        if (it == records.end()) {
            throw NotFoundError("Resource not found: " + key);
        }

        return it->second.value;
    }

    bool exists(const string& key) const {
        return records.find(key) != records.end();
    }

    T put(
        const string& key,
        const T& value,
        optional<unsigned long long> expectedVersion = nullopt
    ) {

        auto it = records.find(key);

        unsigned long long actual =
            it == records.end() ? 0 : it->second.version;

        if (
            expectedVersion.has_value() &&
            actual != expectedVersion.value()
        ) {
            throw ConflictError("Resource version conflict");
        }

        T stored = value;
        stored.resourceVersion = ++revision;

        records[key] = {
            stored,
            revision
        };

        return stored;
    }

    void erase(
        const string& key,
        optional<unsigned long long> expectedVersion = nullopt
    ) {

        auto it = records.find(key);

        if (it == records.end()) {
            throw NotFoundError(key);
        }

        if (
            expectedVersion.has_value() &&
            it->second.version != expectedVersion.value()
        ) {
            throw ConflictError("Delete version conflict");
        }

        records.erase(it);
        ++revision;
    }

    vector<T> list(const string& prefix) const {

        vector<T> result;

        for (const auto& entry : records) {
            if (entry.first.rfind(prefix, 0) == 0) {
                result.push_back(entry.second.value);
            }
        }

        return result;
    }
};


// ============================================================
// API SERVER
// ============================================================

class APIServer {

private:
    StateStore<Node> nodes;
    StateStore<Pod> pods;
    StateStore<Deployment> deployments;

    static string key(
        const string& namespaceName,
        const string& name
    ) {
        return namespaceName + "/" + name;
    }

public:

    Node createNode(Node node) {

        validateName(node.name);

        if (
            node.cpuCapacity <= 0 ||
            node.memoryCapacity <= 0
        ) {
            throw ValidationError("Invalid node capacity");
        }

        return nodes.put(
            key(node.namespaceName, node.name),
            node,
            0
        );
    }

    Pod createPod(Pod pod) {

        validatePod(pod);

        return pods.put(
            key(pod.namespaceName, pod.name),
            pod,
            0
        );
    }

    Deployment createDeployment(Deployment deployment) {

        validateDeployment(deployment);

        return deployments.put(
            key(deployment.namespaceName, deployment.name),
            deployment,
            0
        );
    }

    Node updateNode(Node node) {

        return nodes.put(
            key(node.namespaceName, node.name),
            node,
            node.resourceVersion
        );
    }

    Pod updatePod(Pod pod) {

        return pods.put(
            key(pod.namespaceName, pod.name),
            pod,
            pod.resourceVersion
        );
    }

    Node getNode(const string& name) const {
        return nodes.get(key("default", name));
    }

    vector<Node> listNodes() const {
        return nodes.list("");
    }

    vector<Pod> listPods() const {
        return pods.list("");
    }

    vector<Deployment> listDeployments() const {
        return deployments.list("");
    }

    void deletePod(const Pod& pod) {

        pods.erase(
            key(pod.namespaceName, pod.name),
            pod.resourceVersion
        );
    }

    unsigned long long revision() const {
        return nodes.getRevision()
             + pods.getRevision()
             + deployments.getRevision();
    }
};


// ============================================================
// SCHEDULER
// ============================================================

class Scheduler {

private:
    APIServer& api;

public:

    explicit Scheduler(APIServer& server)
        : api(server) {}

    optional<string> schedule(Pod pod) {

        vector<Node> candidates = api.listNodes();

        candidates.erase(
            remove_if(
                candidates.begin(),
                candidates.end(),
                [&pod](const Node& node) {
                    return
                        node.condition != NodeCondition::Ready ||
                        node.availableCPU() < pod.cpuRequest ||
                        node.availableMemory() < pod.memoryRequest;
                }
            ),
            candidates.end()
        );

        if (candidates.empty()) {
            return nullopt;
        }

        // Best-fit selection reduces fragmentation of CPU capacity.
        sort(
            candidates.begin(),
            candidates.end(),
            [&pod](const Node& a, const Node& b) {

                int remainingA =
                    a.availableCPU() - pod.cpuRequest;

                int remainingB =
                    b.availableCPU() - pod.cpuRequest;

                if (remainingA != remainingB) {
                    return remainingA > remainingB;
                }

                return a.availableMemory() >
                       b.availableMemory();
            }
        );

        Node selected = candidates.front();

        selected.cpuUsed += pod.cpuRequest;
        selected.memoryUsed += pod.memoryRequest;

        // Node allocation is persisted before Pod binding.
        Node updatedNode = api.updateNode(selected);

        pod.nodeName = updatedNode.name;
        pod.phase = PodPhase::Running;

        api.updatePod(pod);

        return updatedNode.name;
    }
};


// ============================================================
// DEPLOYMENT CONTROLLER
// ============================================================

class DeploymentController {

private:
    APIServer& api;

    static bool matches(
        const Pod& pod,
        const Deployment& deployment
    ) {

        for (const auto& selector : deployment.selector) {

            auto it = pod.labels.find(selector.first);

            if (
                it == pod.labels.end() ||
                it->second != selector.second
            ) {
                return false;
            }
        }

        return true;
    }

    void releaseResources(const Pod& pod) {

        if (!pod.nodeName.has_value()) {
            return;
        }

        Node node = api.getNode(pod.nodeName.value());

        node.cpuUsed = max(
            0,
            node.cpuUsed - pod.cpuRequest
        );

        node.memoryUsed = max(
            0,
            node.memoryUsed - pod.memoryRequest
        );

        api.updateNode(node);
    }

public:

    explicit DeploymentController(APIServer& server)
        : api(server) {}

    map<string, int> reconcile(
        const Deployment& deployment
    ) {

        vector<Pod> owned;

        for (const Pod& pod : api.listPods()) {

            if (
                pod.owner == deployment.uid &&
                matches(pod, deployment)
            ) {
                owned.push_back(pod);
            }
        }

        int running = static_cast<int>(
            count_if(
                owned.begin(),
                owned.end(),
                [](const Pod& pod) {
                    return pod.phase == PodPhase::Running;
                }
            )
        );

        int missing = max(
            0,
            deployment.desiredReplicas - running
        );

        int excess = max(
            0,
            static_cast<int>(owned.size()) -
                deployment.desiredReplicas
        );

        int removed = 0;

        for (int i = 0; i < excess; ++i) {

            Pod pod = owned[i];

            releaseResources(pod);
            api.deletePod(pod);
            ++removed;
        }

        int created = 0;

        for (int i = 0; i < missing; ++i) {

            Pod pod;

            pod.name =
                deployment.name + "-" +
                to_string(api.revision()) + "-" +
                to_string(i);

            pod.namespaceName = deployment.namespaceName;
            pod.owner = deployment.uid;
            pod.image = deployment.image;
            pod.cpuRequest = deployment.cpuRequest;
            pod.memoryRequest = deployment.memoryRequest;
            pod.labels = deployment.selector;

            api.createPod(pod);
            ++created;
        }

        return {
            {"desired", deployment.desiredReplicas},
            {"running", running},
            {"created", created},
            {"removed", removed}
        };
    }
};


// ============================================================
// CONTROL PLANE
// ============================================================

class KubernetesControlPlane {

private:
    APIServer api;
    Scheduler scheduler;
    DeploymentController controller;

public:

    KubernetesControlPlane()
        : scheduler(api),
          controller(api) {}

    void addNode(
        const string& name,
        int cpu,
        int memory
    ) {

        Node node;

        node.name = name;
        node.cpuCapacity = cpu;
        node.memoryCapacity = memory;

        api.createNode(node);
    }

    void deploy(const Deployment& deployment) {
        api.createDeployment(deployment);
    }

    void reconcile() {

        for (const Deployment& deployment :
             api.listDeployments()) {

            controller.reconcile(deployment);
        }

        // Read the current Pod collection after reconciliation.
        vector<Pod> pods = api.listPods();

        for (Pod pod : pods) {

            if (
                pod.phase != PodPhase::Pending ||
                pod.nodeName.has_value()
            ) {
                continue;
            }

            try {
                optional<string> assigned =
                    scheduler.schedule(pod);

                if (assigned.has_value()) {
                    cout << "Scheduled " << pod.name
                         << " on " << assigned.value() << "\n";
                } else {
                    cout << "Unschedulable: "
                         << pod.name << "\n";
                }

            } catch (const ConflictError& error) {
                cerr << "Scheduling conflict: "
                     << error.what() << "\n";
            }
        }
    }

    void printState() const {

        cout << "\nCLUSTER NODES\n";

        for (const Node& node : api.listNodes()) {

            cout << node.name
                 << " CPU " << node.cpuUsed
                 << "/" << node.cpuCapacity
                 << " MEMORY " << node.memoryUsed
                 << "/" << node.memoryCapacity
                 << "\n";
        }

        cout << "\nCLUSTER PODS\n";

        for (const Pod& pod : api.listPods()) {

            cout << pod.name
                 << " Phase=" << toString(pod.phase)
                 << " Node="
                 << pod.nodeName.value_or("Unassigned")
                 << "\n";
        }

        cout << "\nETCD-STYLE TOTAL REVISION: "
             << api.revision() << "\n";
    }

    APIServer& server() {
        return api;
    }
};


// ============================================================
// EXECUTABLE SCENARIO
// ============================================================

int main() {

    try {

        cout << "KUBERNETES CONTROL PLANE\n";
        cout << "========================\n";

        KubernetesControlPlane cluster;

        cluster.addNode("worker-01", 8, 16384);
        cluster.addNode("worker-02", 4, 8192);

        Deployment deployment;

        deployment.name = "inventory-api";
        deployment.uid = "deployment-inventory-001";
        deployment.desiredReplicas = 5;
        deployment.image = "inventory-api:3.0";
        deployment.cpuRequest = 2;
        deployment.memoryRequest = 1024;
        deployment.selector = {
            {"app", "inventory"}
        };

        cluster.deploy(deployment);

        cout << "\nFIRST RECONCILIATION\n";
        cluster.reconcile();

        cout << "\nSECOND RECONCILIATION\n";
        cluster.reconcile();

        cluster.printState();

        // Resource-version conflict.
        Node node = cluster.server().getNode("worker-01");

        try {

            Node stale = node;
            stale.resourceVersion = 0;

            cluster.server().updateNode(stale);

        } catch (const ConflictError& error) {

            cout << "\nEXPECTED CONFLICT: "
                 << error.what() << "\n";
        }

        // Invalid Pod request.
        try {

            Pod invalid;
            invalid.name = "invalid-pod";
            invalid.cpuRequest = 0;

            cluster.server().createPod(invalid);

        } catch (const ValidationError& error) {

            cout << "\nEXPECTED VALIDATION ERROR: "
                 << error.what() << "\n";
        }

    } catch (const exception& error) {

        cerr << "CONTROL PLANE ERROR: "
             << error.what() << "\n";

        return 1;
    }

    return 0;
}
