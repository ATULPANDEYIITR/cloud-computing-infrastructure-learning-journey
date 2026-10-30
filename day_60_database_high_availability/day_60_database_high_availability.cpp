#include <algorithm>
#include <chrono>
#include <cstdint>
#include <exception>
#include <iostream>
#include <map>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

/*
 * Database High Availability: C++17 failover eligibility engine.
 *
 * The engine models an active-passive cluster. It evaluates voting quorum,
 * health-observation freshness, replica lag, synchronous replication,
 * primary fencing, and cluster epochs before changing node roles.
 *
 * A production implementation would obtain fencing confirmation from an
 * independent infrastructure control plane and persist state transitions
 * in a durable consensus-backed control store.
 */

using Clock = std::chrono::system_clock;
using TimePoint = Clock::time_point;

enum class NodeRole {
    Primary,
    Replica
};

enum class HealthStatus {
    Healthy,
    Degraded,
    Unreachable,
    Unknown
};

enum class ReplicationMode {
    Synchronous,
    Asynchronous
};

std::string toString(NodeRole role) {
    return role == NodeRole::Primary ? "primary" : "replica";
}

std::string toString(HealthStatus status) {
    switch (status) {
        case HealthStatus::Healthy: return "healthy";
        case HealthStatus::Degraded: return "degraded";
        case HealthStatus::Unreachable: return "unreachable";
        case HealthStatus::Unknown: return "unknown";
    }
    return "unknown";
}

std::string toString(ReplicationMode mode) {
    return mode == ReplicationMode::Synchronous
        ? "synchronous"
        : "asynchronous";
}

struct DatabaseNode {
    std::string id;
    std::string zone;
    NodeRole role;
    bool votingMember;
    ReplicationMode replicationMode;
    std::int64_t replicationLagMs;
    HealthStatus health;
    TimePoint observedAt;
    bool fenced;
    std::uint64_t fencingToken;
};

struct FailoverPolicy {
    std::size_t quorumRequired;
    std::int64_t maxReplicationLagMs;
    bool requireSynchronousReplica;
    std::chrono::seconds maxObservationAge;
    std::size_t minimumAvailabilityZones;
};

struct FailoverDecision {
    bool eligible = false;
    std::vector<std::string> reasons;
    std::size_t healthyVoters = 0;
    std::string candidateId;
    std::int64_t candidateLagMs = 0;
};

struct FailoverEvent {
    std::string oldPrimaryId;
    std::string newPrimaryId;
    std::uint64_t previousEpoch;
    std::uint64_t newEpoch;
    std::uint64_t fencingToken;
    std::size_t healthyVoters;
    TimePoint timestamp;
};

class FailoverEngine {
public:
    FailoverEngine(
        std::string clusterId,
        std::vector<DatabaseNode> nodes,
        std::string primaryId,
        FailoverPolicy policy,
        std::uint64_t initialEpoch,
        std::uint64_t initialFencingToken
    )
        : clusterId_(std::move(clusterId)),
          primaryId_(std::move(primaryId)),
          policy_(policy),
          epoch_(initialEpoch),
          fencingToken_(initialFencingToken) {

        if (clusterId_.empty() || primaryId_.empty()) {
            throw std::invalid_argument("Cluster and primary IDs are required");
        }
        if (policy_.quorumRequired == 0 ||
            policy_.maxReplicationLagMs < 0 ||
            policy_.maxObservationAge.count() <= 0 ||
            policy_.minimumAvailabilityZones < 2) {
            throw std::invalid_argument("Invalid failover policy");
        }

        for (auto& node : nodes) {
            if (node.id.empty() || node.zone.empty()) {
                throw std::invalid_argument("Node ID and zone are required");
            }
            if (node.replicationLagMs < 0) {
                throw std::invalid_argument("Replication lag cannot be negative");
            }
            const auto inserted = nodes_.emplace(node.id, std::move(node));
            if (!inserted.second) {
                throw std::invalid_argument("Duplicate node identifier");
            }
        }

        if (nodes_.empty() || nodes_.find(primaryId_) == nodes_.end()) {
            throw std::invalid_argument("Initial primary is not a cluster member");
        }

        std::size_t primaryCount = 0;
        std::size_t voterCount = 0;
        std::set<std::string> zones;

        for (const auto& entry : nodes_) {
            const auto& node = entry.second;
            primaryCount += node.role == NodeRole::Primary ? 1U : 0U;
            voterCount += node.votingMember ? 1U : 0U;
            zones.insert(node.zone);
        }

        if (primaryCount != 1 ||
            nodes_.at(primaryId_).role != NodeRole::Primary) {
            throw std::invalid_argument("Cluster must have exactly one primary");
        }
        if (policy_.quorumRequired > voterCount) {
            throw std::invalid_argument("Quorum exceeds voting membership");
        }
        if (zones.size() < policy_.minimumAvailabilityZones) {
            throw std::invalid_argument("Insufficient availability zones");
        }
    }

    FailoverDecision evaluate(
        const std::string& candidateId,
        TimePoint now = Clock::now()
    ) const {
        std::lock_guard<std::mutex> guard(mutex_);
        return evaluateUnlocked(candidateId, now);
    }

    FailoverEvent promote(
        const std::string& candidateId,
        std::uint64_t expectedEpoch,
        TimePoint now = Clock::now()
    ) {
        std::lock_guard<std::mutex> guard(mutex_);

        // Epoch comparison prevents an old control-plane request from
        // overriding a newer cluster state.
        if (expectedEpoch != epoch_) {
            throw std::runtime_error(
                "Stale cluster epoch: expected " +
                std::to_string(expectedEpoch) +
                ", current " + std::to_string(epoch_)
            );
        }

        const FailoverDecision decision = evaluateUnlocked(candidateId, now);
        if (!decision.eligible) {
            std::string message = "Promotion rejected:";
            for (const auto& reason : decision.reasons) {
                message += " " + reason + ";";
            }
            throw std::runtime_error(message);
        }

        DatabaseNode& oldPrimary = nodes_.at(primaryId_);
        DatabaseNode& newPrimary = nodes_.at(candidateId);

        const std::uint64_t previousEpoch = epoch_;
        const std::uint64_t nextEpoch = epoch_ + 1;
        const std::uint64_t nextToken = fencingToken_ + 1;

        // The previous primary is demoted before the replica becomes primary.
        oldPrimary.role = NodeRole::Replica;
        newPrimary.role = NodeRole::Primary;
        newPrimary.fenced = false;
        newPrimary.fencingToken = nextToken;

        primaryId_ = candidateId;
        epoch_ = nextEpoch;
        fencingToken_ = nextToken;

        FailoverEvent event{
            oldPrimary.id,
            newPrimary.id,
            previousEpoch,
            nextEpoch,
            nextToken,
            decision.healthyVoters,
            now
        };

        events_.push_back(event);
        return event;
    }

    void printState() const {
        std::lock_guard<std::mutex> guard(mutex_);

        std::cout << "\nCluster: " << clusterId_
                  << "\nPrimary: " << primaryId_
                  << "\nEpoch: " << epoch_
                  << "\nFencing token: " << fencingToken_ << '\n';

        for (const auto& entry : nodes_) {
            const auto& node = entry.second;
            std::cout
                << "Node " << node.id
                << " | zone=" << node.zone
                << " | role=" << toString(node.role)
                << " | health=" << toString(node.health)
                << " | replication=" << toString(node.replicationMode)
                << " | lag_ms=" << node.replicationLagMs
                << " | fenced=" << (node.fenced ? "true" : "false")
                << " | token=" << node.fencingToken
                << '\n';
        }
    }

    const std::vector<FailoverEvent>& events() const {
        return events_;
    }

private:
    bool observationFresh(const DatabaseNode& node, TimePoint now) const {
        if (node.observedAt > now) {
            return false;
        }

        return now - node.observedAt <= policy_.maxObservationAge;
    }

    FailoverDecision evaluateUnlocked(
        const std::string& candidateId,
        TimePoint now
    ) const {
        FailoverDecision decision;
        decision.candidateId = candidateId;

        const auto candidateIterator = nodes_.find(candidateId);
        if (candidateIterator == nodes_.end()) {
            decision.reasons.push_back("candidate_not_found");
            return decision;
        }

        const DatabaseNode& candidate = candidateIterator->second;
        const DatabaseNode& primary = nodes_.at(primaryId_);
        decision.candidateLagMs = candidate.replicationLagMs;

        if (candidateId == primaryId_) {
            decision.reasons.push_back("candidate_is_already_primary");
        }
        if (candidate.role != NodeRole::Replica) {
            decision.reasons.push_back("candidate_is_not_a_replica");
        }
        if (candidate.health != HealthStatus::Healthy) {
            decision.reasons.push_back("candidate_is_not_healthy");
        }
        if (!observationFresh(candidate, now)) {
            decision.reasons.push_back("candidate_observation_is_stale");
        }
        if (policy_.requireSynchronousReplica &&
            candidate.replicationMode != ReplicationMode::Synchronous) {
            decision.reasons.push_back("candidate_is_not_synchronous");
        }
        if (candidate.replicationLagMs > policy_.maxReplicationLagMs) {
            decision.reasons.push_back("candidate_lag_exceeds_policy");
        }

        if (primary.health == HealthStatus::Healthy &&
            observationFresh(primary, now)) {
            decision.reasons.push_back("current_primary_is_still_healthy");
        }
        if (!primary.fenced) {
            decision.reasons.push_back("current_primary_has_not_been_fenced");
        }

        for (const auto& entry : nodes_) {
            const DatabaseNode& node = entry.second;
            if (node.votingMember &&
                node.health == HealthStatus::Healthy &&
                observationFresh(node, now)) {
                ++decision.healthyVoters;
            }
        }

        if (decision.healthyVoters < policy_.quorumRequired) {
            decision.reasons.push_back("healthy_voter_quorum_not_reached");
        }

        decision.eligible = decision.reasons.empty();
        return decision;
    }

    std::string clusterId_;
    std::map<std::string, DatabaseNode> nodes_;
    std::string primaryId_;
    FailoverPolicy policy_;
    std::uint64_t epoch_;
    std::uint64_t fencingToken_;
    std::vector<FailoverEvent> events_;
    mutable std::mutex mutex_;
};

void printDecision(const FailoverDecision& decision) {
    std::cout << "Candidate: " << decision.candidateId
              << "\nEligible: " << (decision.eligible ? "yes" : "no")
              << "\nHealthy voters: " << decision.healthyVoters
              << "\nReplication lag: " << decision.candidateLagMs << " ms\n";

    for (const auto& reason : decision.reasons) {
        std::cout << "  Rejection reason: " << reason << '\n';
    }
}

int main() {
    try {
        const TimePoint now = Clock::now();

        std::vector<DatabaseNode> nodes{
            {
                "db-az1-primary",
                "availability-zone-a",
                NodeRole::Primary,
                true,
                ReplicationMode::Synchronous,
                0,
                HealthStatus::Unreachable,
                now,
                true,
                14
            },
            {
                "db-az2-replica",
                "availability-zone-b",
                NodeRole::Replica,
                true,
                ReplicationMode::Synchronous,
                15,
                HealthStatus::Healthy,
                now,
                false,
                0
            },
            {
                "db-az3-replica",
                "availability-zone-c",
                NodeRole::Replica,
                true,
                ReplicationMode::Asynchronous,
                160,
                HealthStatus::Healthy,
                now,
                false,
                0
            }
        };

        const FailoverPolicy policy{
            2,
            100,
            true,
            std::chrono::seconds(30),
            3
        };

        FailoverEngine engine(
            "orders-production",
            std::move(nodes),
            "db-az1-primary",
            policy,
            7,
            14
        );

        std::cout << "DATABASE HIGH AVAILABILITY ENGINE\n\n";

        const auto delayed = engine.evaluate("db-az3-replica", now);
        std::cout << "Asynchronous replica evaluation:\n";
        printDecision(delayed);

        if (delayed.eligible) {
            throw std::logic_error("Delayed candidate should not be eligible");
        }

        const auto preferred = engine.evaluate("db-az2-replica", now);
        std::cout << "\nSynchronous replica evaluation:\n";
        printDecision(preferred);

        if (!preferred.eligible) {
            throw std::runtime_error("Expected candidate is not eligible");
        }

        const FailoverEvent event = engine.promote(
            "db-az2-replica",
            7,
            now
        );

        std::cout << "\nPromotion completed:"
                  << "\nOld primary: " << event.oldPrimaryId
                  << "\nNew primary: " << event.newPrimaryId
                  << "\nEpoch: " << event.previousEpoch
                  << " -> " << event.newEpoch
                  << "\nFencing token: " << event.fencingToken
                  << "\nHealthy voters: " << event.healthyVoters
                  << '\n';

        engine.printState();

        try {
            engine.promote("db-az3-replica", 7, now);
        } catch (const std::exception& error) {
            std::cout << "\nExpected stale-request rejection: "
                      << error.what() << '\n';
        }

    } catch (const std::exception& error) {
        std::cerr << "Execution failed: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
