#include <algorithm>
#include <cassert>
#include <cctype>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

/*
 * Deployments and ReplicaSets
 * C++17 declarative reconciliation and merge-style rollout engine.
 */

enum class PodState {
    Pending,
    Running,
    Ready,
    Failed,
    Terminating
};

enum class DeploymentState {
    Progressing,
    Available,
    Degraded,
    Paused
};

struct ContainerSpec {
    std::string name;
    std::string image;
    int port = 8080;
};

struct DeploymentSpec {
    std::string name;
    std::string namespace = "default";
    int replicas = 1;
    ContainerSpec container;
    int maxSurge = 1;
    int maxUnavailable = 0;
    int revisionHistoryLimit = 5;
};

struct Pod {
    int id;
    std::string image;
    PodState state = PodState::Pending;
};

struct ReplicaSet {
    int id;
    int revision;
    std::string image;
    int desiredReplicas = 0;
    std::map<int, Pod> pods;

    int activeReplicas() const {
        int count = 0;

        for (const auto& [id, pod] : pods) {
            if (
                pod.state == PodState::Pending ||
                pod.state == PodState::Running ||
                pod.state == PodState::Ready
            ) {
                ++count;
            }
        }

        return count;
    }

    int readyReplicas() const {
        int count = 0;

        for (const auto& [id, pod] : pods) {
            if (pod.state == PodState::Ready) {
                ++count;
            }
        }

        return count;
    }
};

class DeploymentError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class DeploymentController {
private:
    DeploymentSpec spec;
    int revision = 0;
    int nextReplicaSetId = 1;
    int nextPodId = 1;

    std::map<int, ReplicaSet> replicaSets;
    std::vector<std::pair<int, std::string>> history;

    DeploymentState state = DeploymentState::Progressing;
    bool paused = false;

    static bool validName(const std::string& value) {
        if (value.empty() || value.size() > 63) {
            return false;
        }

        if (!std::islower(
            static_cast<unsigned char>(value.front())
        ) && !std::isdigit(
            static_cast<unsigned char>(value.front())
        )) {
            return false;
        }

        if (!std::isalnum(
            static_cast<unsigned char>(value.back())
        )) {
            return false;
        }

        return std::all_of(
            value.begin(),
            value.end(),
            [](unsigned char c) {
                return std::islower(c) ||
                       std::isdigit(c) ||
                       c == '-';
            }
        );
    }

    static bool validImage(const std::string& image) {
        if (image.empty() || image.size() > 255) {
            return false;
        }

        return std::all_of(
            image.begin(),
            image.end(),
            [](unsigned char c) {
                return std::isalnum(c) ||
                       c == '.' || c == '-' ||
                       c == '_' || c == '/' ||
                       c == ':' || c == '@';
            }
        );
    }

    void validate(const DeploymentSpec& candidate) const {
        if (!validName(candidate.name)) {
            throw DeploymentError("Invalid deployment name");
        }

        if (!validName(candidate.name_space)) {
            throw DeploymentError("Invalid namespace");
        }

        if (!validImage(candidate.container.image)) {
            throw DeploymentError("Invalid image reference");
        }

        if (!validName(candidate.container.name)) {
            throw DeploymentError("Invalid container name");
        }

        if (candidate.container.port < 1 ||
            candidate.container.port > 65535) {
            throw DeploymentError("Invalid container port");
        }

        if (candidate.replicas < 0 ||
            candidate.replicas > 10000) {
            throw DeploymentError("Invalid replica count");
        }

        if (candidate.maxSurge < 0 ||
            candidate.maxSurge > 1000) {
            throw DeploymentError("Invalid maxSurge");
        }

        if (candidate.maxUnavailable < 0 ||
            candidate.maxUnavailable > candidate.replicas) {
            throw DeploymentError("Invalid maxUnavailable");
        }

        if (candidate.revisionHistoryLimit < 1) {
            throw DeploymentError("Invalid history limit");
        }
    }

    ReplicaSet& currentReplicaSet() {
        if (replicaSets.empty()) {
            throw DeploymentError("No ReplicaSet exists");
        }

        auto it = std::max_element(
            replicaSets.begin(),
            replicaSets.end(),
            [](const auto& a, const auto& b) {
                return a.second.revision < b.second.revision;
            }
        );

        return it->second;
    }

    const ReplicaSet& currentReplicaSet() const {
        if (replicaSets.empty()) {
            throw DeploymentError("No ReplicaSet exists");
        }

        auto it = std::max_element(
            replicaSets.begin(),
            replicaSets.end(),
            [](const auto& a, const auto& b) {
                return a.second.revision < b.second.revision;
            }
        );

        return it->second;
    }

    int totalReplicas() const {
        int total = 0;

        for (const auto& [id, rs] : replicaSets) {
            total += rs.activeReplicas();
        }

        return total;
    }

    int readyReplicas() const {
        int total = 0;

        for (const auto& [id, rs] : replicaSets) {
            total += rs.readyReplicas();
        }

        return total;
    }

    void createRevision(const std::string& image) {
        ++revision;

        ReplicaSet rs;
        rs.id = nextReplicaSetId++;
        rs.revision = revision;
        rs.image = image;

        replicaSets.emplace(rs.id, rs);
        history.emplace_back(revision, image);

        while (
            static_cast<int>(history.size()) >
            spec.revisionHistoryLimit
        ) {
            history.erase(history.begin());
        }

        std::cout
            << "Created ReplicaSet revision "
            << revision
            << " using "
            << image << '\n';
    }

    void updateState() {
        if (spec.replicas == 0) {
            state = DeploymentState::Available;
            return;
        }

        state = readyReplicas() >= spec.replicas
            ? DeploymentState::Available
            : DeploymentState::Progressing;
    }

public:
    explicit DeploymentController(DeploymentSpec initial)
        : spec(std::move(initial)) {
        validate(spec);
        createRevision(spec.container.image);
        reconcile();
    }

    const DeploymentSpec& desiredState() const {
        return spec;
    }

    DeploymentState status() const {
        return state;
    }

    int readyCount() const {
        return readyReplicas();
    }

    int totalCount() const {
        return totalReplicas();
    }

    int currentRevision() const {
        return revision;
    }

    void reconcile() {
        if (paused) {
            state = DeploymentState::Paused;
            return;
        }

        ReplicaSet& current = currentReplicaSet();
        current.desiredReplicas = spec.replicas;

        const int desired = spec.replicas;
        const int surgeLimit = desired + spec.maxSurge;

        std::vector<int> oldIds;

        for (const auto& [id, rs] : replicaSets) {
            if (id != current.id) {
                oldIds.push_back(id);
            }
        }

        // The newest ReplicaSet owns the desired replica count.
        for (int id : oldIds) {
            replicaSets.at(id).desiredReplicas = 0;
        }

        const int capacity = std::max(
            0,
            surgeLimit - totalReplicas()
        );

        const int missing = std::max(
            0,
            desired - current.activeReplicas()
        );

        const int amount = std::min(capacity, missing);

        for (int i = 0; i < amount; ++i) {
            Pod pod;
            pod.id = nextPodId++;
            pod.image = current.image;
            current.pods.emplace(pod.id, pod);
        }

        if (amount > 0) {
            std::cout
                << "Scaled current ReplicaSet by "
                << amount << '\n';
        }

        const int minimumAvailable = std::max(
            0,
            desired - spec.maxUnavailable
        );

        for (int id : oldIds) {
            ReplicaSet& old = replicaSets.at(id);

            std::vector<int> candidates;

            for (const auto& [podId, pod] : old.pods) {
                if (
                    pod.state == PodState::Pending ||
                    pod.state == PodState::Ready
                ) {
                    candidates.push_back(podId);
                }
            }

            for (int podId : candidates) {
                auto it = old.pods.find(podId);

                if (it == old.pods.end()) {
                    continue;
                }

                const bool isReady =
                    it->second.state == PodState::Ready;

                if (
                    isReady &&
                    readyReplicas() - 1 < minimumAvailable
                ) {
                    continue;
                }

                it->second.state = PodState::Terminating;
                old.pods.erase(it);
            }
        }

        updateState();
    }

    void completePendingPods(
        const std::set<std::string>& failedImages = {}
    ) {
        for (auto& [id, rs] : replicaSets) {
            std::vector<int> removeIds;

            for (auto& [podId, pod] : rs.pods) {
                if (pod.state != PodState::Pending) {
                    continue;
                }

                if (failedImages.count(pod.image)) {
                    pod.state = PodState::Failed;
                    removeIds.push_back(podId);
                    std::cerr
                        << "Container startup failed: "
                        << pod.image << '\n';
                } else {
                    pod.state = PodState::Running;
                    pod.state = PodState::Ready;
                }
            }

            for (int podId : removeIds) {
                rs.pods.erase(podId);
            }
        }

        reconcile();
    }

    void updateImage(const std::string& image) {
        if (!validImage(image)) {
            throw DeploymentError("Invalid image reference");
        }

        if (image == spec.container.image) {
            return;
        }

        spec.container.image = image;
        createRevision(image);
        reconcile();
    }

    void scale(int replicas) {
        DeploymentSpec candidate = spec;
        candidate.replicas = replicas;
        validate(candidate);

        spec = candidate;
        reconcile();
    }

    void rollingUpdate(const std::string& image, int maxSteps = 100) {
        updateImage(image);

        for (int step = 0; step < maxSteps; ++step) {
            completePendingPods();

            const ReplicaSet& current = currentReplicaSet();

            int oldActive = 0;

            for (const auto& [id, rs] : replicaSets) {
                if (id != current.id) {
                    oldActive += rs.activeReplicas();
                }
            }

            if (
                current.readyReplicas() == spec.replicas &&
                oldActive == 0
            ) {
                state = DeploymentState::Available;
                std::cout << "Rolling update completed\n";
                return;
            }

            reconcile();
        }

        state = DeploymentState::Degraded;
        throw DeploymentError("Rolling update exceeded step limit");
    }

    void rollback(std::optional<int> targetRevision = std::nullopt) {
        const ReplicaSet* target = nullptr;

        for (const auto& [id, rs] : replicaSets) {
            if (rs.revision >= revision) {
                continue;
            }

            if (
                targetRevision &&
                rs.revision != *targetRevision
            ) {
                continue;
            }

            if (
                target == nullptr ||
                rs.revision > target->revision
            ) {
                target = &rs;
            }
        }

        if (target == nullptr) {
            throw DeploymentError("Rollback revision not found");
        }

        const std::string targetImage = target->image;

        spec.container.image = targetImage;

        // Rollback creates a new revision, not a reversal of history.
        createRevision(targetImage);
        reconcile();

        std::cout
            << "Rollback initiated using "
            << targetImage << '\n';
    }

    void pause() {
        paused = true;
        state = DeploymentState::Paused;
    }

    void resume() {
        paused = false;
        reconcile();
    }

    void printReport() const {
        std::cout << "\nDeployment: "
                  << spec.namespace << '/'
                  << spec.name << '\n';

        std::cout << "Desired replicas: "
                  << spec.replicas << '\n';

        std::cout << "Ready replicas: "
                  << readyReplicas() << '\n';

        std::cout << "Total active replicas: "
                  << totalReplicas() << '\n';

        std::cout << "Revision: " << revision << '\n';
        std::cout << "Image: "
                  << spec.container.image << '\n';

        std::cout << "State: "
                  << (
                      state == DeploymentState::Available
                          ? "Available"
                          : state == DeploymentState::Paused
                              ? "Paused"
                              : state == DeploymentState::Degraded
                                  ? "Degraded"
                                  : "Progressing"
                  ) << '\n';

        std::cout << "\nReplicaSets\n";

        for (const auto& [id, rs] : replicaSets) {
            std::cout
                << "ID=" << rs.id
                << " revision=" << rs.revision
                << " image=" << rs.image
                << " desired=" << rs.desiredReplicas
                << " active=" << rs.activeReplicas()
                << " ready=" << rs.readyReplicas()
                << '\n';
        }
    }
};

int main() {
    try {
        DeploymentSpec spec;
        spec.name = "inventory-api";
        spec.name_space = "production";
        spec.replicas = 3;
        spec.container = {
            "inventory",
            "registry.example.com/inventory:v1",
            8080
        };
        spec.maxSurge = 1;
        spec.maxUnavailable = 0;
        spec.revisionHistoryLimit = 5;

        DeploymentController controller(spec);

        std::cout << "\nInitial deployment\n";
        controller.completePendingPods();
        controller.printReport();

        std::cout << "\nRolling update\n";
        controller.rollingUpdate(
            "registry.example.com/inventory:v2"
        );
        controller.printReport();

        std::cout << "\nSecond update\n";
        controller.rollingUpdate(
            "registry.example.com/inventory:v3"
        );
        controller.printReport();

        std::cout << "\nRollback to revision 2\n";
        controller.rollback(2);
        controller.completePendingPods();
        controller.printReport();

        std::cout << "\nScaling to five replicas\n";
        controller.scale(5);
        controller.completePendingPods();
        controller.printReport();

        std::cout << "\nPause and resume\n";
        controller.pause();
        controller.resume();
        controller.printReport();

        assert(controller.readyCount() == 5);

        std::cout << "\nValidation test\n";

        try {
            controller.scale(-1);
            assert(false && "Negative replicas accepted");
        } catch (const DeploymentError&) {
            std::cout << "Invalid replica count rejected\n";
        }

        std::cout << "\nAll C++17 tests passed.\n";
    } catch (const std::exception& error) {
        std::cerr << "Controller error: "
                  << error.what() << '\n';
        return 1;
    }

    return 0;
}
