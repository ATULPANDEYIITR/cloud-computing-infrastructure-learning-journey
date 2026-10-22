#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using Minutes = long long;

enum class Architecture {
    PilotLight,
    WarmStandby,
    ActiveActive
};

enum class ReviewStatus {
    Pending,
    Healthy,
    Failed
};

enum class BackupType {
    Full,
    Incremental
};

struct RecoveryPolicy {
    std::string service;
    Minutes rpoMinutes;
    Minutes rtoMinutes;

    void validate() const {
        if (service.empty()) {
            throw std::invalid_argument("Service name cannot be empty");
        }
        if (rpoMinutes < 0) {
            throw std::invalid_argument("RPO cannot be negative");
        }
        if (rtoMinutes <= 0) {
            throw std::invalid_argument("RTO must be positive");
        }
    }
};

struct Backup {
    std::string id;
    Minutes createdAt;
    BackupType type;
    int version;
    std::string checksum;

    void validate() const {
        if (id.empty()) {
            throw std::invalid_argument("Backup ID cannot be empty");
        }
        if (createdAt < 0) {
            throw std::invalid_argument("Backup timestamp cannot be negative");
        }
        if (version <= 0) {
            throw std::invalid_argument("Backup version must be positive");
        }
        if (checksum.empty()) {
            throw std::invalid_argument("Backup checksum cannot be empty");
        }
    }
};

struct StatusCheck {
    std::string name;
    bool passed;
    std::string commit;

    void validate() const {
        if (name.empty() || commit.empty()) {
            throw std::invalid_argument("Status check requires name and commit");
        }
    }
};

struct RecoveryNode {
    std::string name;
    Architecture architecture;
    bool healthy;
    bool servingTraffic;
    Minutes lastSync;

    void fail() {
        healthy = false;
        servingTraffic = false;
    }

    void recover() {
        healthy = true;
        servingTraffic = true;
    }
};

struct PullLikeChange {
    std::string changeId;
    std::string sourceVersion;
    std::string targetBranch;
    std::vector<StatusCheck> checks;
};

struct GovernanceDecision {
    bool eligible;
    std::vector<std::string> reasons;
};

class RecoveryPointManager {
private:
    std::vector<Backup> backups;

public:
    void addBackup(const Backup& backup) {
        backup.validate();

        auto duplicate = std::find_if(
            backups.begin(),
            backups.end(),
            [&](const Backup& existing) {
                return existing.id == backup.id;
            }
        );

        if (duplicate != backups.end()) {
            throw std::invalid_argument("Duplicate backup ID: " + backup.id);
        }

        backups.push_back(backup);

        std::sort(
            backups.begin(),
            backups.end(),
            [](const Backup& a, const Backup& b) {
                return a.createdAt < b.createdAt;
            }
        );
    }

    std::optional<Backup> latestBefore(Minutes failureTime) const {
        std::optional<Backup> result;

        for (const auto& backup : backups) {
            if (backup.createdAt <= failureTime) {
                result = backup;
            }
        }

        return result;
    }

    bool hasRecoveryPoint(Minutes failureTime) const {
        return latestBefore(failureTime).has_value();
    }
};

class MergeEligibilityEngine {
private:
    RecoveryPolicy policy;

public:
    explicit MergeEligibilityEngine(RecoveryPolicy p)
        : policy(std::move(p)) {
        policy.validate();
    }

    GovernanceDecision evaluate(
        const PullLikeChange& change,
        const std::set<std::string>& requiredChecks
    ) const {
        GovernanceDecision decision{true, {}};

        if (change.sourceVersion.empty()) {
            decision.eligible = false;
            decision.reasons.emplace_back("Source version is missing");
        }

        if (change.targetBranch.empty()) {
            decision.eligible = false;
            decision.reasons.emplace_back("Target branch is missing");
        }

        for (const auto& checkName : requiredChecks) {
            auto found = std::find_if(
                change.checks.begin(),
                change.checks.end(),
                [&](const StatusCheck& check) {
                    return check.name == checkName;
                }
            );

            if (found == change.checks.end()) {
                decision.eligible = false;
                decision.reasons.push_back(
                    "Required recovery validation is missing: " + checkName
                );
            } else if (!found->passed) {
                decision.eligible = false;
                decision.reasons.push_back(
                    "Required recovery validation failed: " + checkName
                );
            }
        }

        return decision;
    }
};

class DisasterRecoveryEngine {
private:
    RecoveryPolicy policy;
    Architecture architecture;
    RecoveryPointManager recoveryPoints;
    std::vector<RecoveryNode> nodes;

    Minutes architectureRto() const {
        switch (architecture) {
            case Architecture::PilotLight:
                return 45;
            case Architecture::WarmStandby:
                return 18;
            case Architecture::ActiveActive:
                return 2;
        }

        throw std::logic_error("Unknown architecture");
    }

public:
    DisasterRecoveryEngine(
        RecoveryPolicy p,
        Architecture a,
        RecoveryPointManager manager,
        std::vector<RecoveryNode> recoveryNodes
    )
        : policy(std::move(p)),
          architecture(a),
          recoveryPoints(std::move(manager)),
          nodes(std::move(recoveryNodes)) {
        policy.validate();

        if (nodes.empty()) {
            throw std::invalid_argument("At least one recovery node is required");
        }
    }

    GovernanceDecision evaluateRecovery(
        Minutes failureTime,
        const std::set<std::string>& requiredChecks
    ) const {
        GovernanceDecision decision{true, {}};

        auto point = recoveryPoints.latestBefore(failureTime);

        if (!point) {
            decision.eligible = false;
            decision.reasons.emplace_back("No recovery point exists");
            return decision;
        }

        Minutes rpo = failureTime - point->createdAt;
        Minutes rto = architectureRto();

        if (rpo > policy.rpoMinutes) {
            decision.eligible = false;
            decision.reasons.emplace_back(
                "RPO target violated: observed " +
                std::to_string(rpo) +
                " minutes"
            );
        }

        if (rto > policy.rtoMinutes) {
            decision.eligible = false;
            decision.reasons.emplace_back(
                "RTO target violated: observed " +
                std::to_string(rto) +
                " minutes"
            );
        }

        for (const auto& check : requiredChecks) {
            if (check == "backup-integrity") {
                if (point->checksum.empty()) {
                    decision.eligible = false;
                    decision.reasons.emplace_back(
                        "Backup integrity cannot be verified"
                    );
                }
            }

            if (check == "recovery-point-available") {
                if (!recoveryPoints.hasRecoveryPoint(failureTime)) {
                    decision.eligible = false;
                    decision.reasons.emplace_back(
                        "Required recovery point is unavailable"
                    );
                }
            }
        }

        return decision;
    }

    bool failover(const std::string& failedNodeName) {
        auto failed = std::find_if(
            nodes.begin(),
            nodes.end(),
            [&](RecoveryNode& node) {
                return node.name == failedNodeName;
            }
        );

        if (failed == nodes.end()) {
            throw std::invalid_argument(
                "Unknown recovery node: " + failedNodeName
            );
        }

        failed->fail();

        if (architecture == Architecture::ActiveActive) {
            auto surviving = std::find_if(
                nodes.begin(),
                nodes.end(),
                [](const RecoveryNode& node) {
                    return node.healthy && node.servingTraffic;
                }
            );

            return surviving != nodes.end();
        }

        failed->recover();
        return true;
    }

    void printTopology() const {
        std::cout << "Recovery topology\n";

        for (const auto& node : nodes) {
            std::cout
                << "  "
                << node.name
                << " healthy=" << std::boolalpha << node.healthy
                << " serving=" << node.servingTraffic
                << " last_sync=" << node.lastSync
                << '\n';
        }
    }
};

std::string architectureName(Architecture architecture) {
    switch (architecture) {
        case Architecture::PilotLight:
            return "Pilot Light";
        case Architecture::WarmStandby:
            return "Warm Standby";
        case Architecture::ActiveActive:
            return "Active-Active";
    }

    return "Unknown";
}

RecoveryPointManager buildRecoveryPoints() {
    RecoveryPointManager manager;

    manager.addBackup({
        "full-001",
        0,
        BackupType::Full,
        900,
        "sha256:11111111"
    });

    manager.addBackup({
        "inc-002",
        30,
        BackupType::Incremental,
        901,
        "sha256:22222222"
    });

    manager.addBackup({
        "inc-003",
        60,
        BackupType::Incremental,
        902,
        "sha256:33333333"
    });

    manager.addBackup({
        "inc-004",
        90,
        BackupType::Incremental,
        903,
        "sha256:44444444"
    });

    return manager;
}

void printDecision(const GovernanceDecision& decision) {
    std::cout
        << "Eligible: "
        << std::boolalpha
        << decision.eligible
        << '\n';

    for (const auto& reason : decision.reasons) {
        std::cout << "  - " << reason << '\n';
    }
}

void runArchitectureScenario(
    Architecture architecture,
    const RecoveryPolicy& policy
) {
    auto manager = buildRecoveryPoints();

    std::vector<RecoveryNode> nodes{
        {
            "region-a",
            architecture,
            true,
            true,
            90
        },
        {
            "region-b",
            architecture,
            true,
            architecture == Architecture::ActiveActive,
            90
        }
    };

    DisasterRecoveryEngine engine(
        policy,
        architecture,
        manager,
        nodes
    );

    std::cout
        << "\n=== "
        << architectureName(architecture)
        << " ===\n";

    auto decision = engine.evaluateRecovery(
        105,
        {"backup-integrity", "recovery-point-available"}
    );

    printDecision(decision);

    bool failoverSucceeded = engine.failover("region-a");

    std::cout
        << "Failover successful: "
        << std::boolalpha
        << failoverSucceeded
        << '\n';

    engine.printTopology();
}

int main() {
    try {
        RecoveryPolicy pilotPolicy{
            "Customer API",
            30,
            60
        };

        RecoveryPolicy warmPolicy{
            "Customer API",
            30,
            30
        };

        RecoveryPolicy activePolicy{
            "Customer API",
            5,
            5
        };

        runArchitectureScenario(
            Architecture::PilotLight,
            pilotPolicy
        );

        runArchitectureScenario(
            Architecture::WarmStandby,
            warmPolicy
        );

        runArchitectureScenario(
            Architecture::ActiveActive,
            activePolicy
        );

        std::cout << "\n=== Invalid backup demonstration ===\n";

        try {
            Backup invalid{
                "bad",
                10,
                BackupType::Full,
                0,
                ""
            };

            invalid.validate();
        } catch (const std::exception& error) {
            std::cout
                << "Validation rejected backup: "
                << error.what()
                << '\n';
        }

        /*
         * The separate MergeEligibilityEngine illustrates a related
         * production-governance principle: automated recovery checks can be
         * evaluated as explicit gates before operational state changes.
         * It is deliberately independent from backup and failover logic.
         */
        PullLikeChange recoveryChange{
            "recovery-change-17",
            "commit-903",
            "production",
            {
                {"backup-integrity", true, "commit-903"},
                {"recovery-point-available", true, "commit-903"}
            }
        };

        MergeEligibilityEngine governanceEngine(pilotPolicy);

        auto governanceDecision = governanceEngine.evaluate(
            recoveryChange,
            {"backup-integrity", "recovery-point-available"}
        );

        std::cout << "\n=== Recovery validation gates ===\n";
        printDecision(governanceDecision);

    } catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << '\n';

        return 1;
    }

    return 0;
}
