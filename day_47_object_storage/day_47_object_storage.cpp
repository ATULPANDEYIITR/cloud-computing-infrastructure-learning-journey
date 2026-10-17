#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

/*
 * Repository-independent object storage governance case study.
 *
 * Scenario:
 * An engineering organization stores deployment manifests, compliance
 * evidence, and operational exports. The storage service must decide whether
 * an operation is authorized, retain historical versions, enforce lifecycle
 * policies, and prevent deletion of protected records.
 *
 * Compile:
 *   g++ -std=c++17 -Wall -Wextra -pedantic object_storage_governance.cpp -o storage_demo
 */

using Clock = std::chrono::system_clock;
using TimePoint = Clock::time_point;
using Days = std::chrono::duration<double, std::ratio<86400>>;

enum class Versioning { Disabled, Enabled, Suspended };
enum class StorageClass { Standard, InfrequentAccess, Archive };
enum class Effect { Allow, Deny };
enum class Operation {
    ListObjects,
    GetObject,
    PutObject,
    DeleteObject,
    GetVersion,
    DeleteVersion,
    RestoreObject,
    ManageLifecycle
};

std::string toString(StorageClass value) {
    switch (value) {
        case StorageClass::Standard: return "STANDARD";
        case StorageClass::InfrequentAccess: return "INFREQUENT_ACCESS";
        case StorageClass::Archive: return "ARCHIVE";
    }
    throw std::logic_error("Unknown storage class.");
}

std::string toString(Operation value) {
    switch (value) {
        case Operation::ListObjects: return "ListObjects";
        case Operation::GetObject: return "GetObject";
        case Operation::PutObject: return "PutObject";
        case Operation::DeleteObject: return "DeleteObject";
        case Operation::GetVersion: return "GetVersion";
        case Operation::DeleteVersion: return "DeleteVersion";
        case Operation::RestoreObject: return "RestoreObject";
        case Operation::ManageLifecycle: return "ManageLifecycle";
    }
    throw std::logic_error("Unknown operation.");
}

struct Principal {
    std::string name;
    std::set<std::string> roles;
    bool authenticated{true};
};

struct PolicyStatement {
    Effect effect;
    std::set<Operation> actions;
    std::set<std::string> resourcePrefixes;
    std::set<std::string> principals;
    std::map<std::string, std::string> conditions;
};

struct Metadata {
    std::string contentType;
    std::size_t contentLength{};
    std::string checksum;
    std::map<std::string, std::string> user;
};

struct ObjectVersion {
    std::string key;
    std::string versionId;
    std::string payload;
    Metadata metadata;
    TimePoint createdAt;
    std::optional<TimePoint> noncurrentSince;
    std::optional<TimePoint> retentionUntil;
    StorageClass storageClass{StorageClass::Standard};
    bool deleteMarker{false};
};

struct LifecycleRule {
    std::string id;
    std::string prefix;
    std::optional<double> transitionDays;
    StorageClass transitionTarget{StorageClass::InfrequentAccess};
    std::optional<double> expirationDays;
    std::optional<double> noncurrentExpirationDays;
    bool enabled{true};
};

class StorageError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class AuthorizationError : public StorageError {
public:
    using StorageError::StorageError;
};

class ObjectNotFound : public StorageError {
public:
    using StorageError::StorageError;
};

class PreconditionError : public StorageError {
public:
    using StorageError::StorageError;
};

class Bucket {
public:
    Bucket(std::string name, Principal owner, Versioning versioning)
        : name_(std::move(name)),
          owner_(std::move(owner)),
          versioning_(versioning) {
        if (name_.size() < 3 || name_.size() > 63) {
            throw StorageError("Bucket name length must be between 3 and 63.");
        }
        if (!std::all_of(name_.begin(), name_.end(), [](unsigned char ch) {
                return (ch >= 'a' && ch <= 'z') ||
                       (ch >= '0' && ch <= '9') || ch == '.' || ch == '-';
            })) {
            throw StorageError("Bucket names must use lowercase ASCII letters, digits, dots, and hyphens.");
        }
    }

    const std::string& name() const { return name_; }
    const Principal& owner() const { return owner_; }
    Versioning versioning() const { return versioning_; }
    void setVersioning(Versioning state) { versioning_ = state; }

    void addPolicy(PolicyStatement statement) {
        policy_.push_back(std::move(statement));
    }

    void replacePolicies(std::vector<PolicyStatement> statements) {
        policy_ = std::move(statements);
    }

    void addLifecycleRule(LifecycleRule rule) {
        if (rule.id.empty()) throw StorageError("Lifecycle rule ID cannot be empty.");
        const auto duplicate = std::find_if(
            lifecycle_.begin(), lifecycle_.end(),
            [&rule](const LifecycleRule& item) { return item.id == rule.id; }
        );
        if (duplicate != lifecycle_.end()) {
            throw StorageError("Lifecycle rule IDs must be unique.");
        }
        lifecycle_.push_back(std::move(rule));
    }

    bool authorize(
        const Principal& principal,
        Operation action,
        const std::string& key,
        const std::map<std::string, std::string>& context
    ) const {
        if (!principal.authenticated) return false;
        if (principal.name == owner_.name) return true;

        const std::string resource = "arn:object:" + name_ + "/" + key;
        bool allowed = false;

        for (const auto& statement : policy_) {
            bool principalMatch = statement.principals.count("*") > 0 ||
                                  statement.principals.count(principal.name) > 0;
            if (!principalMatch) {
                for (const auto& role : principal.roles) {
                    if (statement.principals.count(role) > 0) {
                        principalMatch = true;
                        break;
                    }
                }
            }

            bool resourceMatch = false;
            for (const auto& prefix : statement.resourcePrefixes) {
                if (prefix == "*" ||
                    resource.compare(0, prefix.size(), prefix) == 0) {
                    resourceMatch = true;
                    break;
                }
            }

            bool conditionsMatch = true;
            for (const auto& [name, expected] : statement.conditions) {
                const auto found = context.find(name);
                if (found == context.end() || found->second != expected) {
                    conditionsMatch = false;
                    break;
                }
            }

            if (!principalMatch || !resourceMatch ||
                statement.actions.count(action) == 0 || !conditionsMatch) {
                continue;
            }

            // Explicit deny takes precedence over any matching allow statement.
            if (statement.effect == Effect::Deny) return false;
            allowed = true;
        }
        return allowed;
    }

    std::vector<ObjectVersion>& versions(const std::string& key) {
        return objects_[key];
    }

    const std::vector<ObjectVersion>& versions(const std::string& key) const {
        const auto found = objects_.find(key);
        if (found == objects_.end()) throw ObjectNotFound("Object key not found.");
        return found->second;
    }

    const std::map<std::string, std::vector<ObjectVersion>>& allObjects() const {
        return objects_;
    }

    const std::vector<LifecycleRule>& lifecycleRules() const {
        return lifecycle_;
    }

    void removeKeyIfEmpty(const std::string& key) {
        auto found = objects_.find(key);
        if (found != objects_.end() && found->second.empty()) {
            objects_.erase(found);
        }
    }

private:
    std::string name_;
    Principal owner_;
    Versioning versioning_;
    std::vector<PolicyStatement> policy_;
    std::vector<LifecycleRule> lifecycle_;
    std::map<std::string, std::vector<ObjectVersion>> objects_;
};

class GovernanceEngine {
public:
    explicit GovernanceEngine(Bucket& bucket) : bucket_(bucket) {}

    ObjectVersion put(
        const Principal& principal,
        const std::string& key,
        const std::string& payload,
        Metadata metadata,
        const std::map<std::string, std::string>& context = {},
        const std::optional<std::string>& expectedChecksum = std::nullopt
    ) {
        validateKey(key);
        require(principal, Operation::PutObject, key, context);

        if (expectedChecksum && *expectedChecksum != metadata.checksum) {
            throw PreconditionError("Payload checksum did not match the expected checksum.");
        }
        if (metadata.contentLength != payload.size()) {
            throw StorageError("Content-Length metadata does not match the payload.");
        }
        if (metadata.contentType.empty()) {
            throw StorageError("Content type is required.");
        }

        auto& history = bucket_.versions(key);
        const TimePoint now = Clock::now();

        if (bucket_.versioning() == Versioning::Disabled) {
            history.clear();
        } else {
            for (auto& version : history) {
                if (!version.deleteMarker && !version.noncurrentSince) {
                    version.noncurrentSince = now;
                }
            }
        }

        ObjectVersion version{
            key,
            bucket_.versioning() == Versioning::Enabled
                ? "v-" + std::to_string(++sequence_)
                : "null",
            payload,
            std::move(metadata),
            now,
            std::nullopt,
            std::nullopt,
            StorageClass::Standard,
            false
        };

        if (bucket_.versioning() == Versioning::Suspended) {
            history.erase(
                std::remove_if(history.begin(), history.end(),
                    [](const ObjectVersion& item) { return item.versionId == "null"; }),
                history.end()
            );
        }
        history.insert(history.begin(), version);
        return version;
    }

    ObjectVersion get(
        const Principal& principal,
        const std::string& key,
        const std::map<std::string, std::string>& context = {},
        const std::optional<std::string>& versionId = std::nullopt
    ) const {
        validateKey(key);
        require(
            principal,
            versionId ? Operation::GetVersion : Operation::GetObject,
            key,
            context
        );

        const auto& history = bucket_.versions(key);
        const auto found = versionId
            ? std::find_if(history.begin(), history.end(),
                [&versionId](const ObjectVersion& item) {
                    return item.versionId == *versionId;
                })
            : history.begin();

        if (found == history.end() || found->deleteMarker) {
            throw ObjectNotFound("No retrievable object version exists.");
        }
        if (found->storageClass == StorageClass::Archive) {
            throw StorageError("Archive object must be restored before retrieval.");
        }
        if (found->metadata.contentLength != found->payload.size()) {
            throw StorageError("Stored payload failed length verification.");
        }
        return *found;
    }

    void erase(
        const Principal& principal,
        const std::string& key,
        const std::map<std::string, std::string>& context = {},
        const std::optional<std::string>& versionId = std::nullopt
    ) {
        validateKey(key);
        require(
            principal,
            versionId ? Operation::DeleteVersion : Operation::DeleteObject,
            key,
            context
        );

        auto& history = bucket_.versions(key);
        const TimePoint now = Clock::now();

        if (versionId) {
            const auto found = std::find_if(
                history.begin(), history.end(),
                [&versionId](const ObjectVersion& item) {
                    return item.versionId == *versionId;
                }
            );
            if (found == history.end()) throw ObjectNotFound("Version not found.");
            if (found->retentionUntil && now < *found->retentionUntil) {
                throw StorageError("Retention period prohibits deleting this version.");
            }
            history.erase(found);
        } else if (bucket_.versioning() == Versioning::Enabled) {
            for (auto& version : history) {
                if (!version.deleteMarker && !version.noncurrentSince) {
                    version.noncurrentSince = now;
                }
            }
            history.insert(history.begin(), ObjectVersion{
                key, "marker-" + std::to_string(++sequence_), "",
                Metadata{"application/x-delete-marker", 0, "", {}},
                now, std::nullopt, std::nullopt,
                StorageClass::Standard, true
            });
        } else {
            if (history.empty() || history.front().deleteMarker) {
                throw ObjectNotFound("Current object does not exist.");
            }
            if (history.front().retentionUntil && now < *history.front().retentionUntil) {
                throw StorageError("Retention period prohibits deleting the object.");
            }
            history.clear();
        }
        bucket_.removeKeyIfEmpty(key);
    }

    std::vector<std::string> list(
        const Principal& principal,
        const std::string& prefix,
        const std::map<std::string, std::string>& context = {}
    ) const {
        require(principal, Operation::ListObjects, prefix, context);
        std::vector<std::string> result;

        for (const auto& [key, history] : bucket_.allObjects()) {
            if (key.compare(0, prefix.size(), prefix) != 0 || history.empty()) continue;
            if (history.front().deleteMarker) continue;
            result.push_back(key);
        }
        return result;
    }

    std::map<std::string, std::size_t> executeLifecycle(TimePoint now) {
        std::map<std::string, std::size_t> result{
            {"transitioned", 0},
            {"expired", 0},
            {"noncurrentDeleted", 0}
        };

        std::vector<std::string> keys;
        for (const auto& [key, ignored] : bucket_.allObjects()) {
            (void)ignored;
            keys.push_back(key);
        }

        for (const auto& key : keys) {
            auto& history = bucket_.versions(key);
            for (std::size_t index = 0; index < history.size();) {
                auto& version = history[index];
                if (version.deleteMarker) {
                    ++index;
                    continue;
                }

                const double age = Days(now - version.createdAt).count();
                const std::optional<double> noncurrentAge =
                    version.noncurrentSince
                    ? std::optional<double>(Days(now - *version.noncurrentSince).count())
                    : std::nullopt;

                bool removed = false;
                for (const auto& rule : bucket_.lifecycleRules()) {
                    if (!rule.enabled ||
                        key.compare(0, rule.prefix.size(), rule.prefix) != 0) {
                        continue;
                    }

                    if (rule.transitionDays && age >= *rule.transitionDays &&
                        version.storageClass != StorageClass::Archive &&
                        version.storageClass != rule.transitionTarget) {
                        version.storageClass = rule.transitionTarget;
                        ++result["transitioned"];
                    }

                    if (rule.noncurrentExpirationDays && noncurrentAge &&
                        *noncurrentAge >= *rule.noncurrentExpirationDays) {
                        if (!version.retentionUntil || now >= *version.retentionUntil) {
                            history.erase(history.begin() + static_cast<std::ptrdiff_t>(index));
                            ++result["noncurrentDeleted"];
                            removed = true;
                        }
                        break;
                    }

                    const bool current = index == 0 && !version.noncurrentSince;
                    if (current && rule.expirationDays && age >= *rule.expirationDays) {
                        if (version.retentionUntil && now < *version.retentionUntil) {
                            continue;
                        }

                        if (bucket_.versioning() == Versioning::Enabled) {
                            version.noncurrentSince = now;
                            history.insert(history.begin(), ObjectVersion{
                                key,
                                "marker-" + std::to_string(++sequence_),
                                "",
                                Metadata{"application/x-delete-marker", 0, "", {}},
                                now,
                                std::nullopt,
                                std::nullopt,
                                StorageClass::Standard,
                                true
                            });
                        } else {
                            history.erase(history.begin() + static_cast<std::ptrdiff_t>(index));
                        }
                        ++result["expired"];
                        removed = true;
                        break;
                    }
                }

                if (!removed) ++index;
            }
            bucket_.removeKeyIfEmpty(key);
        }

        return result;
    }

private:
    Bucket& bucket_;
    std::uint64_t sequence_{0};

    static void validateKey(const std::string& key) {
        if (key.empty() || key.front() == '/' || key.find('\0') != std::string::npos) {
            throw StorageError("Invalid object key.");
        }
        if (key.size() > 1024) throw StorageError("Object key exceeds 1024 bytes.");
        std::istringstream stream(key);
        std::string segment;
        while (std::getline(stream, segment, '/')) {
            if (segment == "..") throw StorageError("Parent-directory segment is prohibited.");
        }
    }

    void require(
        const Principal& principal,
        Operation action,
        const std::string& key,
        const std::map<std::string, std::string>& context
    ) const {
        if (!bucket_.authorize(principal, action, key, context)) {
            throw AuthorizationError(
                principal.name + " is not authorized for " + toString(action)
            );
        }
    }
};

Metadata makeMetadata(const std::string& payload, const std::string& contentType) {
    // A real implementation should compute a cryptographic checksum such as
    // SHA-256. This deterministic illustrative field is not a security checksum.
    std::ostringstream checksum;
    checksum << std::hex << std::hash<std::string>{}(payload);
    return Metadata{contentType, payload.size(), checksum.str(), {}};
}

int main() {
    try {
        Principal owner{"storage-platform", {"storage-admin"}, true};
        Principal writer{"deployment-service", {"release-writer"}, true};
        Principal auditor{"compliance-reviewer", {"audit"}, true};
        Principal guest{"external-client", {}, false};

        Bucket bucket("deployment-evidence-prod", owner, Versioning::Enabled);

        bucket.addPolicy(PolicyStatement{
            Effect::Allow,
            {Operation::PutObject, Operation::GetObject, Operation::DeleteObject},
            {"arn:object:deployment-evidence-prod/releases/"},
            {"release-writer"},
            {{"transport", "tls"}}
        });

        bucket.addPolicy(PolicyStatement{
            Effect::Allow,
            {Operation::GetObject, Operation::GetVersion, Operation::ListObjects},
            {"arn:object:deployment-evidence-prod/compliance/"},
            {"audit"},
            {}
        });

        bucket.addPolicy(PolicyStatement{
            Effect::Deny,
            {Operation::DeleteObject, Operation::DeleteVersion},
            {"arn:object:deployment-evidence-prod/compliance/"},
            {"*"},
            {}
        });

        bucket.addLifecycleRule(LifecycleRule{
            "release-archive",
            "releases/archive/",
            30.0,
            StorageClass::Archive,
            std::nullopt,
            180.0,
            true
        });

        GovernanceEngine engine(bucket);
        const std::map<std::string, std::string> tls{{"transport", "tls"}};

        const std::string firstPayload = "{\"release\":\"4.8.0\",\"approved\":true}";
        auto first = engine.put(
            writer,
            "releases/current.json",
            firstPayload,
            makeMetadata(firstPayload, "application/json"),
            tls
        );

        const std::string secondPayload = "{\"release\":\"4.8.1\",\"approved\":true}";
        auto second = engine.put(
            writer,
            "releases/current.json",
            secondPayload,
            makeMetadata(secondPayload, "application/json"),
            tls
        );

        std::cout << "Deployment evidence storage\n";
        std::cout << "Original version: " << first.versionId << '\n';
        std::cout << "Current version:  " << second.versionId << '\n';
        std::cout << "Current payload: "
                  << engine.get(writer, "releases/current.json", tls).payload
                  << '\n';

        std::cout << "Historical payload: "
                  << engine.get(
                         auditor,
                         "compliance/previous-audit.json",
                         {},
                         std::nullopt
                     ).payload
                  << '\n';
    } catch (const ObjectNotFound& error) {
        std::cout << "Expected missing-object condition: " << error.what() << '\n';
    } catch (const StorageError& error) {
        std::cerr << "Storage error: " << error.what() << '\n';
        return 1;
    }

    try {
        Principal owner{"storage-platform", {"storage-admin"}, true};
        Principal writer{"deployment-service", {"release-writer"}, true};
        Principal auditor{"compliance-reviewer", {"audit"}, true};
        Principal guest{"external-client", {}, false};

        Bucket bucket("deployment-evidence-archive", owner, Versioning::Enabled);
        bucket.addPolicy(PolicyStatement{
            Effect::Allow,
            {Operation::PutObject, Operation::GetObject, Operation::DeleteObject},
            {"arn:object:deployment-evidence-archive/releases/"},
            {"release-writer"},
            {{"transport", "tls"}}
        });
        bucket.addPolicy(PolicyStatement{
            Effect::Allow,
            {Operation::GetObject, Operation::GetVersion, Operation::ListObjects},
            {"arn:object:deployment-evidence-archive/compliance/"},
            {"audit"},
            {}
        });
        bucket.addPolicy(PolicyStatement{
            Effect::Deny,
            {Operation::DeleteObject, Operation::DeleteVersion},
            {"arn:object:deployment-evidence-archive/compliance/"},
            {"*"},
            {}
        });

        bucket.addLifecycleRule(LifecycleRule{
            "archive-old-evidence", "releases/archive/", 30.0,
            StorageClass::Archive, std::nullopt, 180.0, true
        });

        GovernanceEngine engine(bucket);
        const std::map<std::string, std::string> tls{{"transport", "tls"}};
        const std::string payload = "{\"release\":\"4.8.1\",\"approved\":true}";
        auto current = engine.put(
            writer, "releases/current.json", payload,
            makeMetadata(payload, "application/json"), tls
        );

        try {
            engine.get(guest, "releases/current.json");
        } catch (const AuthorizationError& error) {
            std::cout << "Unauthenticated read rejected: " << error.what() << '\n';
        }

        try {
            engine.erase(writer, "compliance/retention-record.json");
        } catch (const AuthorizationError& error) {
            std::cout << "Compliance deletion rejected: " << error.what() << '\n';
        }

        const std::string archivePayload = "release_id,checksum\n4.2.0,abc123\n";
        auto archive = engine.put(
            owner, "releases/archive/4.2.0.csv", archivePayload,
            makeMetadata(archivePayload, "text/csv")
        );

        // Backdate a version only to make lifecycle behavior deterministic.
        auto& versions = bucket.versions("releases/archive/4.2.0.csv");
        versions.front().createdAt = Clock::now() - std::chrono::hours(24 * 45);

        const auto lifecycle = engine.executeLifecycle(Clock::now());
        std::cout << "Lifecycle transitions: " << lifecycle.at("transitioned") << '\n';

        try {
            engine.get(owner, "releases/archive/4.2.0.csv");
        } catch (const StorageError& error) {
            std::cout << "Archived retrieval blocked: " << error.what() << '\n';
        }

        engine.erase(writer, "releases/current.json", tls);
        try {
            engine.get(writer, "releases/current.json", tls);
        } catch (const ObjectNotFound& error) {
            std::cout << "Delete marker hides current object: " << error.what() << '\n';
        }

        std::cout << "Stored archive version: " << archive.versionId << '\n';
        std::cout << "Stored current version: " << current.versionId << '\n';
        std::cout << "Compliance auditor: " << auditor.name << '\n';
    } catch (const StorageError& error) {
        std::cerr << "Case-study failure: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
