#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

using namespace std;

/*
 * Docker Fundamentals: Repository and Runtime Governance Engine.
 *
 * C++17 implementation of:
 * - Docker daemon and client separation
 * - Image and layer management
 * - Registry distribution
 * - Container lifecycle
 * - Resource reservations
 * - Port mapping
 * - Runtime health
 * - Merge-independent deployment policy evaluation
 *
 * Build:
 * g++ -std=c++17 -O2 -Wall -Wextra -pedantic docker.cpp -o docker
 */

class DockerException : public runtime_error {
public:
    explicit DockerException(const string& message)
        : runtime_error(message) {}
};

enum class ContainerState {
    Created,
    Running,
    Stopped,
    Removed
};

enum class CheckState {
    Pending,
    Passed,
    Failed
};

enum class ReviewState {
    Pending,
    Approved,
    ChangesRequested,
    Dismissed
};

string toString(ContainerState state) {
    switch (state) {
        case ContainerState::Created: return "created";
        case ContainerState::Running: return "running";
        case ContainerState::Stopped: return "stopped";
        case ContainerState::Removed: return "removed";
    }
    throw DockerException("Unknown container state.");
}

struct ImageLayer {
    string instruction;
    string digest;
    double sizeMB;
};

struct Image {
    string id;
    string repository;
    string tag;
    vector<ImageLayer> layers;
    string architecture;

    string reference() const {
        return repository + ":" + tag;
    }

    double totalSize() const {
        double result = 0;

        for (const auto& layer : layers) {
            result += layer.sizeMB;
        }

        return result;
    }
};

struct Container {
    string id;
    string name;
    string imageId;
    ContainerState state = ContainerState::Created;

    map<int, int> ports;
    map<string, string> environment;

    int memoryMB = 512;
    double cpu = 1.0;

    vector<string> logs;
};

struct ResourceCapacity {
    int memoryMB = 8192;
    double cpu = 8.0;
};

struct ResourceUsage {
    int memoryMB = 0;
    double cpu = 0.0;
};

struct Approval {
    string reviewer;
    ReviewState state = ReviewState::Pending;
    bool eligible = false;
    bool stale = false;
    bool dismissed = false;
};

struct ProtectionPolicy {
    bool protectedBranch = true;
    bool directPushAllowed = false;
    bool forcePushAllowed = false;
    bool deletionAllowed = false;
    bool linearHistoryRequired = true;
    bool conversationsMustBeResolved = true;
    int requiredApprovals = 2;

    set<string> requiredChecks = {
        "build",
        "tests",
        "security"
    };
};

struct PullRequest {
    string id;
    string sourceBranch;
    string targetBranch;

    bool open = true;
    bool draft = false;
    bool mergeConflict = false;
    bool sourceSynchronized = true;
    bool linearHistory = true;
    bool conversationsResolved = true;

    vector<Approval> approvals;
    map<string, CheckState> checks;
};

struct MergeDecision {
    bool eligible = false;
    vector<string> reasons;
};

class DockerDaemon {
private:
    ResourceCapacity capacity_;

    unordered_map<string, Image> images_;
    map<string, string> tags_;

    unordered_map<string, Container> containers_;

    unordered_map<int, string> occupiedPorts_;
    unordered_map<string, ResourceUsage> allocations_;

    vector<string> events_;

    static bool validName(const string& value) {
        if (value.empty() || value.size() > 64) {
            return false;
        }

        if (!isalnum(static_cast<unsigned char>(value.front()))) {
            return false;
        }

        for (unsigned char ch : value) {
            if (!(isalnum(ch) || ch == '_' || ch == '.' || ch == '-')) {
                return false;
            }
        }

        return true;
    }

    void record(const string& action, const string& id) {
        events_.push_back(action + ":" + id);
    }

    Image& resolveImage(const string& reference) {
        auto tag = tags_.find(reference);

        if (tag == tags_.end()) {
            throw DockerException("Image not found: " + reference);
        }

        auto image = images_.find(tag->second);

        if (image == images_.end()) {
            throw DockerException("Image metadata unavailable.");
        }

        return image->second;
    }

    Container& resolveContainer(const string& id) {
        auto found = containers_.find(id);

        if (found == containers_.end()) {
            throw DockerException("Container not found.");
        }

        return found->second;
    }

    bool isNameInUse(const string& name) const {
        for (const auto& item : containers_) {
            if (
                item.second.name == name &&
                item.second.state != ContainerState::Removed
            ) {
                return true;
            }
        }

        return false;
    }

public:
    explicit DockerDaemon(ResourceCapacity capacity)
        : capacity_(capacity) {
        if (capacity.memoryMB <= 0 || capacity.cpu <= 0) {
            throw DockerException("Invalid daemon capacity.");
        }
    }

    Image buildImage(
        const string& repository,
        const string& tag,
        const vector<string>& instructions
    ) {
        if (repository.empty() || tag.empty()) {
            throw DockerException("Invalid image reference.");
        }

        if (instructions.empty()) {
            throw DockerException("Image requires layers.");
        }

        Image image;

        image.repository = repository;
        image.tag = tag;
        image.architecture = "amd64";

        // Deterministic demonstration identifier. Production images
        // should use cryptographic content digests.
        string material;

        for (const auto& instruction : instructions) {
            if (instruction.empty()) {
                throw DockerException("Empty image instruction.");
            }

            material += instruction;

            ImageLayer layer;
            layer.instruction = instruction;
            layer.digest = "layer-" + to_string(
                hash<string>{}(instruction)
            );
            layer.sizeMB = max(
                0.1,
                static_cast<double>(instruction.size()) / 1024.0
            );

            image.layers.push_back(layer);
        }

        image.id = "image-" + to_string(
            hash<string>{}(material)
        );

        images_[image.id] = image;
        tags_[image.reference()] = image.id;

        record("image_build", image.id);

        return image;
    }

    void tagImage(
        const string& source,
        const string& target
    ) {
        Image& image = resolveImage(source);

        if (target.empty() || target.find(' ') != string::npos) {
            throw DockerException("Invalid target image tag.");
        }

        tags_[target] = image.id;

        record("image_tag", image.id);
    }

    void pushImage(
        const string& reference,
        const string& registry,
        bool authenticated
    ) {
        if (!authenticated) {
            throw DockerException("Registry authentication required.");
        }

        if (registry.empty()) {
            throw DockerException("Registry name is required.");
        }

        Image& image = resolveImage(reference);

        record(
            "image_push",
            registry + "/" + image.reference()
        );
    }

    Container createContainer(
        const string& name,
        const string& imageReference,
        const map<int, int>& ports,
        int memoryMB,
        double cpu
    ) {
        if (!validName(name)) {
            throw DockerException("Invalid container name.");
        }

        if (isNameInUse(name)) {
            throw DockerException("Container name already exists.");
        }

        Image& image = resolveImage(imageReference);

        if (
            memoryMB <= 0 ||
            memoryMB > capacity_.memoryMB ||
            cpu <= 0 ||
            cpu > capacity_.cpu
        ) {
            throw DockerException("Invalid resource request.");
        }

        for (const auto& mapping : ports) {
            if (
                mapping.first < 1 ||
                mapping.first > 65535 ||
                mapping.second < 1 ||
                mapping.second > 65535
            ) {
                throw DockerException("Invalid port mapping.");
            }

            if (occupiedPorts_.count(mapping.first)) {
                throw DockerException("Host port is occupied.");
            }
        }

        Container container;

        container.id = "ctr-" + to_string(containers_.size() + 1);
        container.name = name;
        container.imageId = image.id;
        container.ports = ports;
        container.memoryMB = memoryMB;
        container.cpu = cpu;

        containers_[container.id] = container;

        record("container_create", container.id);

        return container;
    }

    ResourceUsage currentUsage() const {
        ResourceUsage result;

        for (const auto& allocation : allocations_) {
            result.memoryMB += allocation.second.memoryMB;
            result.cpu += allocation.second.cpu;
        }

        return result;
    }

    void startContainer(const string& id) {
        Container& container = resolveContainer(id);

        if (
            container.state == ContainerState::Running ||
            container.state == ContainerState::Removed
        ) {
            throw DockerException("Invalid container state.");
        }

        ResourceUsage usage = currentUsage();

        if (
            usage.memoryMB + container.memoryMB >
                capacity_.memoryMB ||
            usage.cpu + container.cpu > capacity_.cpu
        ) {
            throw DockerException("Insufficient daemon resources.");
        }

        for (const auto& mapping : container.ports) {
            if (occupiedPorts_.count(mapping.first)) {
                throw DockerException("Port conflict detected.");
            }
        }

        // Resource and port reservations occur after validation.
        allocations_[id] = {
            container.memoryMB,
            container.cpu
        };

        for (const auto& mapping : container.ports) {
            occupiedPorts_[mapping.first] = id;
        }

        container.state = ContainerState::Running;
        container.logs.push_back("Container started.");

        record("container_start", id);
    }

    void stopContainer(const string& id) {
        Container& container = resolveContainer(id);

        if (container.state != ContainerState::Running) {
            throw DockerException("Container is not running.");
        }

        container.state = ContainerState::Stopped;

        for (const auto& mapping : container.ports) {
            auto port = occupiedPorts_.find(mapping.first);

            if (port != occupiedPorts_.end() && port->second == id) {
                occupiedPorts_.erase(port);
            }
        }

        allocations_.erase(id);

        container.logs.push_back("Container stopped.");

        record("container_stop", id);
    }

    void removeContainer(const string& id) {
        Container& container = resolveContainer(id);

        if (container.state == ContainerState::Running) {
            throw DockerException(
                "Running containers cannot be removed."
            );
        }

        if (container.state == ContainerState::Removed) {
            throw DockerException("Container already removed.");
        }

        container.state = ContainerState::Removed;

        record("container_remove", id);
    }

    vector<Container> listContainers(bool runningOnly = false) const {
        vector<Container> result;

        for (const auto& item : containers_) {
            const Container& container = item.second;

            if (container.state == ContainerState::Removed) {
                continue;
            }

            if (
                runningOnly &&
                container.state != ContainerState::Running
            ) {
                continue;
            }

            result.push_back(container);
        }

        return result;
    }

    const vector<string>& events() const {
        return events_;
    }

    size_t imageCount() const {
        return images_.size();
    }
};


class Registry {
private:
    string name_;
    map<string, string> imageReferences_;

public:
    explicit Registry(string name)
        : name_(move(name)) {
        if (name_.empty()) {
            throw DockerException("Registry name is required.");
        }
    }

    void publish(
        const Image& image,
        bool authenticated
    ) {
        if (!authenticated) {
            throw DockerException("Registry access denied.");
        }

        imageReferences_[image.reference()] = image.id;
    }

    bool contains(const string& reference) const {
        return imageReferences_.count(reference) > 0;
    }
};


class GovernanceEngine {
public:
    static MergeDecision evaluate(
        const PullRequest& pr,
        const ProtectionPolicy& policy
    ) {
        MergeDecision decision;

        auto reject = [&](const string& reason) {
            decision.reasons.push_back(reason);
        };

        if (!pr.open) {
            reject("Pull Request is closed.");
        }

        if (pr.draft) {
            reject("Draft Pull Requests cannot be merged.");
        }

        if (pr.sourceBranch == pr.targetBranch) {
            reject("Source and target branches must differ.");
        }

        if (pr.mergeConflict) {
            reject("Merge conflicts must be resolved.");
        }

        if (!pr.sourceSynchronized) {
            reject("Source branch requires synchronization.");
        }

        if (
            policy.linearHistoryRequired &&
            !pr.linearHistory
        ) {
            reject("Linear history requirement failed.");
        }

        int validApprovals = 0;

        for (const auto& approval : pr.approvals) {
            if (
                approval.eligible &&
                approval.state == ReviewState::Approved &&
                !approval.stale &&
                !approval.dismissed
            ) {
                ++validApprovals;
            }
        }

        if (validApprovals < policy.requiredApprovals) {
            reject("Insufficient eligible approvals.");
        }

        for (const auto& required : policy.requiredChecks) {
            auto check = pr.checks.find(required);

            if (
                check == pr.checks.end() ||
                check->second != CheckState::Passed
            ) {
                reject("Required status check failed: " + required);
            }
        }

        if (
            policy.conversationsMustBeResolved &&
            !pr.conversationsResolved
        ) {
            reject("Unresolved review conversations.");
        }

        decision.eligible = decision.reasons.empty();

        return decision;
    }
};


class DockerClient {
private:
    DockerDaemon& daemon_;

public:
    explicit DockerClient(DockerDaemon& daemon)
        : daemon_(daemon) {}

    Container run(
        const string& name,
        const string& image,
        const map<int, int>& ports,
        int memoryMB = 512,
        double cpu = 1.0
    ) {
        Container container = daemon_.createContainer(
            name,
            image,
            ports,
            memoryMB,
            cpu
        );

        daemon_.startContainer(container.id);

        return container;
    }

    void printContainers() const {
        cout << "\nCONTAINER INVENTORY\n";
        cout << left
             << setw(15) << "ID"
             << setw(20) << "NAME"
             << setw(12) << "STATE"
             << "IMAGE\n";

        for (const auto& container : daemon_.listContainers()) {
            cout << left
                 << setw(15) << container.id
                 << setw(20) << container.name
                 << setw(12) << toString(container.state)
                 << container.imageId << "\n";
        }
    }
};


void demonstrateGovernance() {
    cout << "\nREPOSITORY GOVERNANCE EXAMPLE\n";

    ProtectionPolicy policy;

    PullRequest pr;

    pr.id = "PR-104";
    pr.sourceBranch = "feature/docker-runtime";
    pr.targetBranch = "main";
    pr.open = true;
    pr.draft = false;
    pr.mergeConflict = false;
    pr.sourceSynchronized = true;
    pr.linearHistory = true;
    pr.conversationsResolved = true;

    pr.approvals = {
        {"reviewer-a", ReviewState::Approved, true, false, false},
        {"reviewer-b", ReviewState::Approved, true, false, false}
    };

    pr.checks = {
        {"build", CheckState::Passed},
        {"tests", CheckState::Passed},
        {"security", CheckState::Passed}
    };

    MergeDecision decision = GovernanceEngine::evaluate(
        pr,
        policy
    );

    cout << "Pull Request: " << pr.id << "\n";
    cout << "Merge eligible: "
         << (decision.eligible ? "YES" : "NO")
         << "\n";

    for (const auto& reason : decision.reasons) {
        cout << "- " << reason << "\n";
    }

    // Demonstrate stale approval behavior.
    pr.approvals[0].stale = true;

    decision = GovernanceEngine::evaluate(pr, policy);

    cout << "\nAfter source changes, stale approval:\n";
    cout << "Merge eligible: "
         << (decision.eligible ? "YES" : "NO")
         << "\n";
}


int main() {
    try {
        cout << "DOCKER FUNDAMENTALS ENGINE\n";
        cout << "==========================\n";

        DockerDaemon daemon({
            4096,
            4.0
        });

        DockerClient client(daemon);

        cout << "\n1. BUILD IMAGE\n";

        Image image = daemon.buildImage(
            "company/web-service",
            "1.0",
            {
                "FROM node:22-alpine",
                "WORKDIR /app",
                "COPY package.json .",
                "RUN npm install --omit=dev",
                "COPY src/ ./src",
                "CMD node src/server.js"
            }
        );

        cout << "Image ID: " << image.id << "\n";
        cout << "Reference: " << image.reference() << "\n";
        cout << "Layers: " << image.layers.size() << "\n";
        cout << "Image size: " << image.totalSize() << " MB\n";

        cout << "\n2. REGISTRY PUSH\n";

        Registry registry("registry.example.com");

        registry.publish(image, true);

        cout << "Image published: "
             << registry.contains(image.reference())
             << "\n";

        cout << "\n3. CONTAINER START\n";

        Container container = client.run(
            "web-service",
            image.reference(),
            {{8080, 3000}},
            512,
            1.0
        );

        cout << "Container ID: " << container.id << "\n";

        client.printContainers();

        cout << "\n4. RESOURCE USAGE\n";

        ResourceUsage usage = daemon.currentUsage();

        cout << "Memory: " << usage.memoryMB << " MB\n";
        cout << "CPU: " << usage.cpu << "\n";

        cout << "\n5. PORT CONFLICT TEST\n";

        try {
            client.run(
                "second-service",
                image.reference(),
                {{8080, 3001}},
                512,
                1.0
            );
        } catch (const DockerException& exception) {
            cout << "Expected failure: "
                 << exception.what() << "\n";
        }

        cout << "\n6. STOP AND RESTART\n";

        daemon.stopContainer(container.id);
        daemon.startContainer(container.id);

        cout << "Container restarted successfully.\n";

        cout << "\n7. REMOVE CONTAINER\n";

        daemon.stopContainer(container.id);
        daemon.removeContainer(container.id);

        cout << "Container removed successfully.\n";

        cout << "\n8. IMAGE TAGGING\n";

        daemon.tagImage(
            image.reference(),
            "company/web-service:stable"
        );

        cout << "Additional tag created.\n";

        cout << "\n9. EVENT HISTORY\n";

        for (const auto& event : daemon.events()) {
            cout << event << "\n";
        }

        demonstrateGovernance();

        cout << "\n10. ASSERTIONS\n";

        if (daemon.listContainers().size() != 0) {
            throw DockerException("Container removal assertion failed.");
        }

        if (daemon.imageCount() != 1) {
            throw DockerException("Image count assertion failed.");
        }

        if (daemon.currentUsage().memoryMB != 0) {
            throw DockerException("Resource leak detected.");
        }

        cout << "All assertions passed.\n";

        return 0;

    } catch (const exception& exception) {
        cerr << "Fatal error: " << exception.what() << "\n";
        return 1;
    }
}
