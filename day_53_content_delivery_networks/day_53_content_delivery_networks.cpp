#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

using Clock = std::chrono::steady_clock;
using Milliseconds = std::chrono::milliseconds;

enum class ReviewState {
    Draft,
    Open,
    Approved,
    Blocked,
    Merged,
    Closed
};

enum class CheckState {
    Pending,
    Passed,
    Failed
};

struct EdgeLocation {
    std::string name;
    std::string region;
    std::size_t capacity;
};

struct CacheEntry {
    std::string etag;
    int version;
    Clock::time_point created;
    Clock::time_point expires;
};

struct StatusCheck {
    std::string name;
    CheckState state;
};

struct Review {
    std::string reviewer;
    bool eligible;
    bool approved;
    bool dismissed;
};

struct PullRequest {
    int id;
    std::string sourceBranch;
    std::string targetBranch;
    ReviewState state;
    int commits;
    std::vector<Review> reviews;
    std::vector<StatusCheck> checks;
    bool conversationsResolved;
    bool mergeable;
};

struct BranchProtection {
    std::string branch;
    int requiredApprovals;
    std::vector<std::string> requiredChecks;
    bool restrictDirectPush;
    bool restrictForcePush;
    bool requireResolvedConversations;
    bool requireLinearHistory;
    bool allowAdministratorBypass;
};

struct MergeDecision {
    bool eligible;
    std::vector<std::string> reasons;
};

class RepositoryGovernance {
private:
    std::map<int, PullRequest> pullRequests;
    std::map<std::string, BranchProtection> protections;

public:
    void addProtection(BranchProtection policy) {
        if (policy.branch.empty()) {
            throw std::invalid_argument("Protected branch cannot be empty");
        }
        if (policy.requiredApprovals < 0) {
            throw std::invalid_argument("Required approvals cannot be negative");
        }
        protections[policy.branch] = std::move(policy);
    }

    void addPullRequest(PullRequest request) {
        if (request.id <= 0) {
            throw std::invalid_argument("Pull Request ID must be positive");
        }
        if (request.sourceBranch.empty() || request.targetBranch.empty()) {
            throw std::invalid_argument("Branches cannot be empty");
        }
        if (request.commits <= 0) {
            throw std::invalid_argument("Pull Request must contain at least one commit");
        }
        pullRequests[request.id] = std::move(request);
    }

    MergeDecision evaluate(int id) const {
        auto requestIt = pullRequests.find(id);
        if (requestIt == pullRequests.end()) {
            throw std::out_of_range("Pull Request does not exist");
        }

        const PullRequest& pr = requestIt->second;
        MergeDecision decision{true, {}};

        if (pr.state != ReviewState::Open && pr.state != ReviewState::Approved) {
            decision.eligible = false;
            decision.reasons.push_back("Pull Request is not open for merging");
        }

        if (!pr.mergeable) {
            decision.eligible = false;
            decision.reasons.push_back("Source and target branches have unresolved merge conflicts");
        }

        auto protectionIt = protections.find(pr.targetBranch);
        if (protectionIt == protections.end()) {
            return decision;
        }

        const BranchProtection& policy = protectionIt->second;

        int validApprovals = 0;
        for (const Review& review : pr.reviews) {
            if (review.eligible && review.approved && !review.dismissed) {
                ++validApprovals;
            }
        }

        if (validApprovals < policy.requiredApprovals) {
            decision.eligible = false;
            decision.reasons.push_back(
                "Required eligible approvals have not been satisfied"
            );
        }

        for (const std::string& required : policy.requiredChecks) {
            auto checkIt = std::find_if(
                pr.checks.begin(),
                pr.checks.end(),
                [&](const StatusCheck& check) {
                    return check.name == required;
                }
            );

            if (checkIt == pr.checks.end()) {
                decision.eligible = false;
                decision.reasons.push_back(
                    "Required status check is missing: " + required
                );
            } else if (checkIt->state != CheckState::Passed) {
                decision.eligible = false;
                decision.reasons.push_back(
                    "Required status check has not passed: " + required
                );
            }
        }

        if (policy.requireResolvedConversations && !pr.conversationsResolved) {
            decision.eligible = false;
            decision.reasons.push_back("Review conversations remain unresolved");
        }

        return decision;
    }
};

class ContentDeliveryNetwork {
private:
    std::unordered_map<std::string, std::string> origin;
    std::unordered_map<std::string, int> versions;

    struct EdgeCache {
        EdgeLocation location;
        std::unordered_map<std::string, CacheEntry> objects;
    };

    std::vector<EdgeCache> edges;
    std::unordered_map<std::string, double> latency;
    std::size_t originFetches = 0;
    std::size_t requests = 0;
    std::size_t hits = 0;

    static std::string versionedEtag(
        const std::string& path,
        int version
    ) {
        return "\"" + path + ":v" + std::to_string(version) + "\"";
    }

    double networkLatency(
        const std::string& clientRegion,
        const std::string& edgeRegion
    ) const {
        const std::string key = clientRegion + ":" + edgeRegion;

        auto it = latency.find(key);
        return it == latency.end() ? 150.0 : it->second;
    }

    EdgeCache& chooseEdge(const std::string& clientRegion) {
        if (edges.empty()) {
            throw std::runtime_error("CDN has no edge locations");
        }

        auto selected = std::min_element(
            edges.begin(),
            edges.end(),
            [&](const EdgeCache& a, const EdgeCache& b) {
                return networkLatency(clientRegion, a.location.region) <
                       networkLatency(clientRegion, b.location.region);
            }
        );

        return *selected;
    }

public:
    ContentDeliveryNetwork() {
        edges.push_back({
            {"delhi-1", "India", 100},
            {}
        });

        edges.push_back({
            {"frankfurt-1", "Europe", 100},
            {}
        });

        edges.push_back({
            {"virginia-1", "North America", 100},
            {}
        });

        latency["India:India"] = 20;
        latency["India:Europe"] = 115;
        latency["India:North America"] = 210;

        latency["Europe:India"] = 115;
        latency["Europe:Europe"] = 25;
        latency["Europe:North America"] = 90;

        latency["North America:India"] = 210;
        latency["North America:Europe"] = 90;
        latency["North America:North America"] = 25;
    }

    void publish(
        const std::string& path,
        const std::string& content
    ) {
        if (path.empty() || path.front() != '/') {
            throw std::invalid_argument("Origin path must begin with '/'");
        }

        if (content.empty()) {
            throw std::invalid_argument("Origin content cannot be empty");
        }

        origin[path] = content;
        versions[path]++;
    }

    std::string request(
        const std::string& path,
        const std::string& clientRegion,
        int ttlSeconds
    ) {
        if (ttlSeconds < 0) {
            throw std::invalid_argument("TTL cannot be negative");
        }

        ++requests;

        EdgeCache& edge = chooseEdge(clientRegion);
        const auto now = Clock::now();

        auto cached = edge.objects.find(path);

        if (cached != edge.objects.end() &&
            now < cached->second.expires) {

            ++hits;

            std::cout
                << "CDN HIT  edge=" << edge.location.name
                << " path=" << path
                << " latency=" << networkLatency(
                    clientRegion,
                    edge.location.region
                ) << "ms\n";

            return cached->second.etag;
        }

        auto originObject = origin.find(path);
        if (originObject == origin.end()) {
            throw std::out_of_range("Origin object does not exist");
        }

        ++originFetches;

        if (edge.objects.size() >= edge.location.capacity &&
            cached == edge.objects.end()) {

            auto victim = std::min_element(
                edge.objects.begin(),
                edge.objects.end(),
                [](const auto& a, const auto& b) {
                    return a.second.expires < b.second.expires;
                }
            );

            if (victim != edge.objects.end()) {
                edge.objects.erase(victim);
            }
        }

        CacheEntry entry{
            versionedEtag(path, versions[path]),
            versions[path],
            now,
            now + std::chrono::seconds(ttlSeconds)
        };

        edge.objects[path] = entry;

        std::cout
            << "CDN MISS edge=" << edge.location.name
            << " path=" << path
            << " origin_fetch=true\n";

        return entry.etag;
    }

    std::size_t invalidate(const std::string& path) {
        std::size_t count = 0;

        for (auto& edge : edges) {
            if (edge.objects.erase(path) > 0) {
                ++count;
            }
        }

        return count;
    }

    void printStatistics() const {
        const std::size_t misses = requests - hits;
        const double ratio =
            requests == 0
                ? 0.0
                : static_cast<double>(hits) /
                  static_cast<double>(requests);

        std::cout << std::fixed << std::setprecision(2);
        std::cout << "\nCDN statistics\n";
        std::cout << "Requests: " << requests << "\n";
        std::cout << "Cache hits: " << hits << "\n";
        std::cout << "Cache misses: " << misses << "\n";
        std::cout << "Hit ratio: " << ratio * 100.0 << "%\n";
        std::cout << "Origin fetches: " << originFetches << "\n";
    }
};

void demonstrateGovernance() {
    RepositoryGovernance repository;

    repository.addProtection({
        "main",
        2,
        {"build", "security-scan"},
        true,
        false,
        true,
        true,
        false
    });

    repository.addPullRequest({
        101,
        "feature/cdn-cache",
        "main",
        ReviewState::Open,
        4,
        {
            {"alice", true, true, false},
            {"bob", true, true, false},
            {"carol", false, true, false}
        },
        {
            {"build", CheckState::Passed},
            {"security-scan", CheckState::Passed}
        },
        true,
        true
    });

    MergeDecision decision = repository.evaluate(101);

    std::cout << "\nRepository governance decision\n";
    std::cout
        << "PR #101 merge eligible: "
        << (decision.eligible ? "yes" : "no")
        << "\n";

    for (const std::string& reason : decision.reasons) {
        std::cout << "Reason: " << reason << "\n";
    }
}

int main() {
    try {
        ContentDeliveryNetwork cdn;

        cdn.publish(
            "/assets/app.js",
            "release-1"
        );

        cdn.publish(
            "/images/logo.svg",
            "<svg>cdn</svg>"
        );

        cdn.request("/assets/app.js", "India", 60);
        cdn.request("/assets/app.js", "India", 60);

        cdn.publish(
            "/assets/app.js",
            "release-2"
        );

        // Existing cached content remains valid until TTL expiry or
        // explicit invalidation. This is why deployment systems commonly
        // combine cache invalidation with immutable versioned assets.
        cdn.request("/assets/app.js", "India", 60);

        std::size_t removed = cdn.invalidate("/assets/app.js");
        std::cout << "Invalidated edge copies: " << removed << "\n";

        cdn.request("/assets/app.js", "India", 60);
        cdn.request("/images/logo.svg", "Europe", 300);

        cdn.printStatistics();

        demonstrateGovernance();
    }
    catch (const std::exception& error) {
        std::cerr << "Execution error: " << error.what() << "\n";
        return 1;
    }

    return 0;
}
