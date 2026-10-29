#include <algorithm>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

enum class ReplicaState {
    Online,
    Lagging,
    Offline
};

enum class ReplicationMode {
    Synchronous,
    Asynchronous
};

enum class MergeDecision {
    Eligible,
    MissingReplicaAcknowledgement,
    ReplicaOffline,
    SequenceGap,
    InvalidChange
};

struct Change {
    std::uint64_t sequence{};
    std::string key;
    std::optional<std::string> value;
};

struct ReplicaHealth {
    std::string name;
    ReplicaState state;
    std::uint64_t appliedSequence{};
    std::uint64_t lag{};
};

static std::string stateToString(ReplicaState state) {
    switch (state) {
        case ReplicaState::Online: return "online";
        case ReplicaState::Lagging: return "lagging";
        case ReplicaState::Offline: return "offline";
    }
    return "unknown";
}

/*
 * The simulator uses a deterministic checksum rather than a cryptographic
 * library so the program remains dependency-free. Production systems should
 * use a vetted cryptographic hash implementation for integrity protection.
 */
static std::string checksum(const Change& change) {
    std::string input =
        std::to_string(change.sequence) + "|" +
        change.key + "|" +
        (change.value.has_value() ? *change.value : "NULL");

    std::uint64_t hash = 1469598103934665603ULL;
    for (unsigned char c : input) {
        hash ^= c;
        hash *= 1099511628211ULL;
    }

    std::ostringstream out;
    out << std::hex << hash;
    return out.str();
}

class Replica {
public:
    explicit Replica(std::string name)
        : name_(std::move(name)) {}

    const std::string& name() const {
        return name_;
    }

    void setState(ReplicaState state) {
        state_ = state;
    }

    ReplicaState state() const {
        return state_;
    }

    std::uint64_t appliedSequence() const {
        return appliedSequence_;
    }

    void receive(const Change& change) {
        if (state_ == ReplicaState::Offline) {
            throw std::runtime_error(name_ + " is offline");
        }

        const std::uint64_t expected =
            appliedSequence_ + pending_.size() + 1;

        if (change.sequence != expected) {
            throw std::runtime_error(
                name_ + " expected sequence " +
                std::to_string(expected) +
                ", received " +
                std::to_string(change.sequence)
            );
        }

        pending_.push_back(change);
        state_ = ReplicaState::Lagging;
    }

    void apply() {
        if (state_ == ReplicaState::Offline) {
            throw std::runtime_error(name_ + " is offline");
        }

        for (const Change& change : pending_) {
            if (change.value.has_value()) {
                data_[change.key] = *change.value;
            } else {
                data_.erase(change.key);
            }

            appliedSequence_ = change.sequence;
        }

        pending_.clear();
        state_ = ReplicaState::Online;
    }

    std::optional<std::string> read(const std::string& key) const {
        if (state_ == ReplicaState::Offline) {
            throw std::runtime_error(name_ + " is offline");
        }

        auto it = data_.find(key);
        if (it == data_.end()) {
            return std::nullopt;
        }

        return it->second;
    }

private:
    std::string name_;
    ReplicaState state_{ReplicaState::Online};
    std::uint64_t appliedSequence_{0};
    std::unordered_map<std::string, std::string> data_;
    std::vector<Change> pending_;
};

class Primary {
public:
    Change write(
        const std::string& key,
        const std::optional<std::string>& value
    ) {
        if (key.empty() || key.size() > 128) {
            throw std::invalid_argument("key must contain 1-128 characters");
        }

        ++sequence_;

        Change change{
            sequence_,
            key,
            value
        };

        if (value.has_value()) {
            data_[key] = *value;
        } else {
            data_.erase(key);
        }

        log_.push_back(change);
        return change;
    }

    std::uint64_t sequence() const {
        return sequence_;
    }

    std::optional<std::string> read(const std::string& key) const {
        auto it = data_.find(key);
        if (it == data_.end()) {
            return std::nullopt;
        }
        return it->second;
    }

private:
    std::uint64_t sequence_{0};
    std::unordered_map<std::string, std::string> data_;
    std::vector<Change> log_;
};

class GovernanceEngine {
public:
    GovernanceEngine(
        ReplicationMode mode,
        std::size_t requiredAcknowledgements
    )
        : mode_(mode),
          requiredAcknowledgements_(requiredAcknowledgements) {}

    void addReplica(Replica replica) {
        replicas_.push_back(std::move(replica));
    }

    Primary& primary() {
        return primary_;
    }

    const std::vector<Replica>& replicas() const {
        return replicas_;
    }

    bool write(
        const std::string& key,
        const std::optional<std::string>& value,
        std::string& reason
    ) {
        Change change = primary_.write(key, value);

        std::size_t acknowledgements = 0;

        for (Replica& replica : replicas_) {
            try {
                replica.receive(change);

                if (mode_ == ReplicationMode::Synchronous) {
                    replica.apply();
                }

                ++acknowledgements;
            } catch (const std::exception& error) {
                reason += replica.name() + ": " + error.what() + "; ";
            }
        }

        if (
            mode_ == ReplicationMode::Synchronous &&
            acknowledgements < requiredAcknowledgements_
        ) {
            reason +=
                "required acknowledgements=" +
                std::to_string(requiredAcknowledgements_) +
                ", received=" +
                std::to_string(acknowledgements);
            return false;
        }

        return true;
    }

    void catchUp() {
        for (Replica& replica : replicas_) {
            if (replica.state() != ReplicaState::Offline) {
                replica.apply();
            }
        }
    }

    std::vector<ReplicaHealth> health() const {
        std::vector<ReplicaHealth> result;

        for (const Replica& replica : replicas_) {
            result.push_back({
                replica.name(),
                replica.state(),
                replica.appliedSequence(),
                primary_.sequence() - replica.appliedSequence()
            });
        }

        return result;
    }

private:
    Primary primary_;
    std::vector<Replica> replicas_;
    ReplicationMode mode_;
    std::size_t requiredAcknowledgements_;
};

static void printHealth(const GovernanceEngine& engine) {
    for (const auto& health : engine.health()) {
        std::cout
            << health.name
            << " state=" << stateToString(health.state)
            << " applied=" << health.appliedSequence
            << " lag=" << health.lag
            << '\n';
    }
}

int main() {
    try {
        std::cout << "=== Asynchronous replication ===\n";

        GovernanceEngine asyncEngine(
            ReplicationMode::Asynchronous,
            0
        );

        asyncEngine.addReplica(Replica("read-1"));
        asyncEngine.addReplica(Replica("read-2"));

        std::string reason;

        bool committed = asyncEngine.write(
            "customer:100",
            std::string("ACTIVE"),
            reason
        );

        std::cout << "Committed: " << std::boolalpha << committed << '\n';
        printHealth(asyncEngine);

        asyncEngine.catchUp();

        std::cout << "After catch-up:\n";
        printHealth(asyncEngine);

        std::cout << "\n=== Synchronous replication ===\n";

        GovernanceEngine syncEngine(
            ReplicationMode::Synchronous,
            2
        );

        syncEngine.addReplica(Replica("sync-1"));

        Replica offline("sync-2");
        offline.setState(ReplicaState::Offline);
        syncEngine.addReplica(std::move(offline));

        reason.clear();

        committed = syncEngine.write(
            "order:500",
            std::string("PAID"),
            reason
        );

        std::cout
            << "Committed: "
            << std::boolalpha
            << committed
            << '\n';

        if (!reason.empty()) {
            std::cout << "Failure detail: " << reason << '\n';
        }

        printHealth(syncEngine);

        std::cout << "\n=== Recovery ===\n";

        for (const auto& health : syncEngine.health()) {
            std::cout
                << health.name
                << " lag=" << health.lag
                << '\n';
        }

    } catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
