#include <algorithm>
#include <cstddef>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <numeric>
#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

enum class OperationType {
    Read,
    Write
};

enum class Consistency {
    Strong,
    Eventual
};

enum class ScalingStrategy {
    Vertical,
    Horizontal,
    Partitioning,
    ReadReplica
};

std::string toString(ScalingStrategy strategy) {
    switch (strategy) {
        case ScalingStrategy::Vertical:
            return "vertical";
        case ScalingStrategy::Horizontal:
            return "horizontal";
        case ScalingStrategy::Partitioning:
            return "partitioning";
        case ScalingStrategy::ReadReplica:
            return "read_replica";
    }

    throw std::logic_error("Unknown scaling strategy");
}

struct StatusCheck {
    std::string name;
    bool passed;
};

struct Review {
    std::string reviewer;
    bool approved;
};

struct DatabaseNode {
    std::string id;
    std::string region;
    std::size_t capacityOps;
    std::size_t activeOps{0};
    bool healthy{true};

    bool canAccept() const {
        return healthy && activeOps < capacityOps;
    }

    double utilization() const {
        if (capacityOps == 0) {
            return 1.0;
        }

        return static_cast<double>(activeOps) /
               static_cast<double>(capacityOps);
    }
};

struct BranchProtection {
    std::size_t requiredApprovals{2};
    bool requireSuccessfulChecks{true};
    bool requireResolvedConversations{true};
    bool allowDirectPush{false};
    bool allowForcePush{false};
    bool requireLinearHistory{true};
};

struct PullRequest {
    int id;
    std::string sourceBranch;
    std::string targetBranch;
    std::vector<std::string> commits;
    std::vector<Review> reviews;
    std::vector<StatusCheck> checks;
    std::size_t unresolvedConversations{0};
    bool draft{false};
    bool mergeConflict{false};
    bool sourceUpToDate{true};
    bool open{true};
};

class MergeEligibilityEngine {
public:
    explicit MergeEligibilityEngine(BranchProtection policy)
        : policy_(std::move(policy)) {}

    std::vector<std::string> evaluate(const PullRequest& pr) const {
        std::vector<std::string> failures;

        if (!pr.open) {
            failures.emplace_back("pull request is not open");
        }

        if (pr.draft) {
            failures.emplace_back("pull request is still a draft");
        }

        if (pr.commits.empty()) {
            failures.emplace_back("pull request has no commits");
        }

        if (pr.sourceBranch.empty() || pr.targetBranch.empty()) {
            failures.emplace_back("source and target branches are required");
        }

        if (pr.mergeConflict) {
            failures.emplace_back("merge conflict must be resolved");
        }

        if (!pr.sourceUpToDate) {
            failures.emplace_back("source branch must be synchronized");
        }

        std::size_t approvals = 0;
        for (const auto& review : pr.reviews) {
            if (review.approved) {
                ++approvals;
            }
        }

        if (approvals < policy_.requiredApprovals) {
            failures.emplace_back("required approvals are missing");
        }

        if (policy_.requireSuccessfulChecks) {
            for (const auto& check : pr.checks) {
                if (!check.passed) {
                    failures.emplace_back(
                        "status check failed: " + check.name
                    );
                }
            }

            if (pr.checks.empty()) {
                failures.emplace_back("no status checks were recorded");
            }
        }

        if (policy_.requireResolvedConversations &&
            pr.unresolvedConversations > 0) {
            failures.emplace_back(
                "unresolved review conversations remain"
            );
        }

        return failures;
    }

    bool canMerge(const PullRequest& pr) const {
        return evaluate(pr).empty();
    }

private:
    BranchProtection policy_;
};

class ShardRouter {
public:
    explicit ShardRouter(std::vector<std::string> shards)
        : shards_(std::move(shards)) {
        if (shards_.empty()) {
            throw std::invalid_argument("At least one shard is required");
        }
    }

    const std::string& route(std::int64_t customerId) const {
        if (customerId < 0) {
            throw std::invalid_argument("Customer ID cannot be negative");
        }

        return shards_[
            static_cast<std::size_t>(customerId) % shards_.size()
        ];
    }

private:
    std::vector<std::string> shards_;
};

class PartitionedOrderTable {
public:
    struct Partition {
        std::string name;
        std::int64_t minimum;
        std::int64_t maximum;
        std::vector<std::pair<std::int64_t, double>> rows;

        bool contains(std::int64_t customerId) const {
            return customerId >= minimum && customerId <= maximum;
        }
    };

    explicit PartitionedOrderTable(std::vector<Partition> partitions)
        : partitions_(std::move(partitions)) {
        if (partitions_.empty()) {
            throw std::invalid_argument(
                "Partitioned table needs at least one partition"
            );
        }
    }

    void insert(std::int64_t customerId, double amount) {
        Partition* partition = findPartition(customerId);

        if (amount < 0.0) {
            throw std::invalid_argument(
                "Order amount cannot be negative"
            );
        }

        partition->rows.emplace_back(customerId, amount);
    }

    std::size_t countForCustomer(std::int64_t customerId) const {
        const Partition* partition = findPartitionConst(customerId);

        return static_cast<std::size_t>(
            std::count_if(
                partition->rows.begin(),
                partition->rows.end(),
                [customerId](const auto& row) {
                    return row.first == customerId;
                }
            )
        );
    }

    const std::vector<Partition>& partitions() const {
        return partitions_;
    }

private:
    Partition* findPartition(std::int64_t customerId) {
        for (auto& partition : partitions_) {
            if (partition.contains(customerId)) {
                return &partition;
            }
        }

        throw std::out_of_range(
            "No partition covers customer ID " +
            std::to_string(customerId)
        );
    }

    const Partition* findPartitionConst(
        std::int64_t customerId
    ) const {
        for (const auto& partition : partitions_) {
            if (partition.contains(customerId)) {
                return &partition;
            }
        }

        throw std::out_of_range(
            "No partition covers customer ID " +
            std::to_string(customerId)
        );
    }

    std::vector<Partition> partitions_;
};

class ReadReplicaRouter {
public:
    ReadReplicaRouter(
        DatabaseNode primary,
        std::vector<DatabaseNode> replicas
    )
        : primary_(std::move(primary)),
          replicas_(std::move(replicas)) {}

    DatabaseNode& route(
        OperationType operation,
        Consistency consistency
    ) {
        if (operation == OperationType::Write ||
            consistency == Consistency::Strong) {
            if (!primary_.canAccept()) {
                throw std::runtime_error(
                    "Primary cannot accept request"
                );
            }

            return primary_;
        }

        for (std::size_t offset = 0; offset < replicas_.size(); ++offset) {
            std::size_t index =
                (cursor_ + offset) % replicas_.size();

            if (replicas_[index].canAccept()) {
                cursor_ = index + 1;
                return replicas_[index];
            }
        }

        if (primary_.canAccept()) {
            return primary_;
        }

        throw std::runtime_error(
            "No database node can serve the read"
        );
    }

private:
    DatabaseNode primary_;
    std::vector<DatabaseNode> replicas_;
    std::size_t cursor_{0};
};

ScalingStrategy chooseScalingStrategy(
    std::size_t workloadOps,
    std::size_t nodeCapacity,
    double writeRatio,
    std::size_t rowCount
) {
    if (workloadOps == 0 || nodeCapacity == 0) {
        throw std::invalid_argument(
            "Workload and capacity must be positive"
        );
    }

    if (writeRatio < 0.0 || writeRatio > 1.0) {
        throw std::invalid_argument(
            "Write ratio must be between zero and one"
        );
    }

    const double utilization =
        static_cast<double>(workloadOps) /
        static_cast<double>(nodeCapacity);

    if (utilization <= 0.70) {
        return ScalingStrategy::Vertical;
    }

    if (writeRatio < 0.30) {
        return ScalingStrategy::ReadReplica;
    }

    if (rowCount > 10'000'000) {
        return ScalingStrategy::Partitioning;
    }

    return ScalingStrategy::Horizontal;
}

PullRequest buildGoodPullRequest() {
    PullRequest pr{
        42,
        "feature/order-index",
        "main",
        {"a1b2c3", "d4e5f6"},
        {
            {"reviewer-a", true},
            {"reviewer-b", true},
            {"reviewer-c", false}
        },
        {
            {"unit-tests", true},
            {"integration-tests", true},
            {"security-scan", true}
        },
        0,
        false,
        false,
        true,
        true
    };

    return pr;
}

int main() {
    try {
        std::cout << "Database Scaling Case Study\n";
        std::cout << std::string(60, '=') << '\n';

        std::cout << "\nScaling policy:\n";

        const std::vector<std::tuple<
            std::size_t,
            std::size_t,
            double,
            std::size_t
        >> scenarios{
            {500, 1000, 0.50, 100'000},
            {900, 1000, 0.10, 500'000},
            {900, 1000, 0.80, 20'000'000},
            {950, 1000, 0.50, 2'000'000}
        };

        for (const auto& [workload, capacity, writes, rows] : scenarios) {
            auto strategy = chooseScalingStrategy(
                workload,
                capacity,
                writes,
                rows
            );

            std::cout
                << "workload=" << workload
                << ", capacity=" << capacity
                << ", writeRatio=" << std::fixed
                << std::setprecision(2) << writes
                << ", rows=" << rows
                << " -> " << toString(strategy)
                << '\n';
        }

        std::cout << "\nPartitioning:\n";

        PartitionedOrderTable table({
            {"p0_999", 0, 999, {}},
            {"p1000_1999", 1000, 1999, {}},
            {"p2000_2999", 2000, 2999, {}}
        });

        table.insert(101, 250.0);
        table.insert(1500, 400.0);
        table.insert(2100, 800.0);
        table.insert(101, 125.0);

        for (const auto& partition : table.partitions()) {
            std::cout
                << partition.name
                << " rows=" << partition.rows.size()
                << '\n';
        }

        std::cout
            << "Customer 101 rows="
            << table.countForCustomer(101)
            << '\n';

        try {
            table.insert(5000, 100.0);
        } catch (const std::exception& ex) {
            std::cout
                << "Rejected out-of-range customer: "
                << ex.what() << '\n';
        }

        std::cout << "\nSharding:\n";

        ShardRouter router({
            "shard-a",
            "shard-b",
            "shard-c"
        });

        for (std::int64_t customer : {101, 102, 103, 104, 105}) {
            std::cout
                << customer
                << " -> "
                << router.route(customer)
                << '\n';
        }

        std::cout << "\nRead replica routing:\n";

        ReadReplicaRouter replicaRouter(
            DatabaseNode{"primary", "ap-south", 1000},
            {
                {"replica-1", "ap-south", 800},
                {"replica-2", "ap-southeast", 800}
            }
        );

        auto& writeNode = replicaRouter.route(
            OperationType::Write,
            Consistency::Strong
        );

        auto& strongReadNode = replicaRouter.route(
            OperationType::Read,
            Consistency::Strong
        );

        auto& eventualReadNode = replicaRouter.route(
            OperationType::Read,
            Consistency::Eventual
        );

        std::cout << "Write -> " << writeNode.id << '\n';
        std::cout << "Strong read -> " << strongReadNode.id << '\n';
        std::cout << "Eventual read -> " << eventualReadNode.id << '\n';

        std::cout << "\nMerge eligibility engine:\n";

        BranchProtection protection;
        MergeEligibilityEngine engine(protection);

        PullRequest valid = buildGoodPullRequest();
        auto failures = engine.evaluate(valid);

        std::cout
            << "Valid PR mergeable="
            << std::boolalpha
            << failures.empty()
            << '\n';

        PullRequest blocked = valid;
        blocked.unresolvedConversations = 2;
        blocked.mergeConflict = true;

        auto blockedFailures = engine.evaluate(blocked);

        std::cout << "Blocked PR reasons:\n";
        for (const auto& failure : blockedFailures) {
            std::cout << "- " << failure << '\n';
        }

        std::cout << "\nEngineering considerations:\n";
        std::cout
            << "- Vertical scaling is operationally simple but has a hardware ceiling.\n"
            << "- Horizontal scaling increases capacity through independent nodes.\n"
            << "- Partitioning reduces the amount of data scanned for partition-key queries.\n"
            << "- Sharding increases write capacity but makes cross-shard operations harder.\n"
            << "- Read replicas improve read throughput while exposing replication lag.\n"
            << "- Routing metadata and administrative database operations require strict access control.\n";

        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "Fatal error: " << ex.what() << '\n';
        return 1;
    }
}
