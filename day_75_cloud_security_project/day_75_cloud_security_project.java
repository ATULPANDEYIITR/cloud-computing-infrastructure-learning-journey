/*
 * CLOUD SECURITY GOVERNANCE ENGINE
 *
 * C++17
 *
 * Implements:
 * - IAM authorization with explicit deny precedence
 * - Least-privilege policy evaluation
 * - Encryption posture and key lifecycle
 * - Network segmentation
 * - Security audit records
 * - Centralized security findings
 * - Merge-independent cloud compliance evaluation
 *
 * Cryptographic encryption is represented through managed key
 * metadata. Production encryption must use a managed KMS/HSM.
 */

#include <algorithm>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

using namespace std;

// ============================================================
// ENUMERATIONS
// ============================================================

enum class Effect {
    ALLOW,
    DENY
};

enum class Severity {
    LOW,
    MEDIUM,
    HIGH,
    CRITICAL
};

enum class Environment {
    DEVELOPMENT,
    STAGING,
    PRODUCTION
};

enum class ResourceState {
    ACTIVE,
    ENCRYPTED,
    BLOCKED
};

string toString(Severity severity) {
    switch (severity) {
        case Severity::LOW: return "LOW";
        case Severity::MEDIUM: return "MEDIUM";
        case Severity::HIGH: return "HIGH";
        case Severity::CRITICAL: return "CRITICAL";
    }

    return "UNKNOWN";
}

string toString(Effect effect) {
    return effect == Effect::ALLOW ? "ALLOW" : "DENY";
}

// ============================================================
// VALIDATION
// ============================================================

void validateString(const string& value, const string& field) {
    if (value.empty() || value.size() > 128) {
        throw invalid_argument("Invalid " + field);
    }
}

bool matches(const string& pattern, const string& value) {
    if (pattern == "*") return true;

    if (!pattern.empty() && pattern.back() == '*') {
        return value.compare(
            0,
            pattern.size() - 1,
            pattern.substr(0, pattern.size() - 1)
        ) == 0;
    }

    return pattern == value;
}

string timestamp() {
    time_t now = time(nullptr);
    tm utc{};

#ifdef _WIN32
    gmtime_s(&utc, &now);
#else
    gmtime_r(&now, &utc);
#endif

    ostringstream output;

    output << put_time(&utc, "%Y-%m-%dT%H:%M:%SZ");

    return output.str();
}

// ============================================================
// IAM POLICY
// ============================================================

struct PolicyStatement {
    Effect effect;
    set<string> actions;
    set<string> resources;
};

class IAMPolicy {

private:
    vector<PolicyStatement> statements;

public:

    void addStatement(const PolicyStatement& statement) {
        if (
            statement.actions.empty() ||
            statement.resources.empty()
        ) {
            throw invalid_argument("Empty IAM statement");
        }

        statements.push_back(statement);
    }

    bool authorize(
        const string& action,
        const string& resource
    ) const {

        bool allowed = false;

        for (const auto& statement : statements) {

            bool actionMatch = any_of(
                statement.actions.begin(),
                statement.actions.end(),
                [&](const string& pattern) {
                    return matches(pattern, action);
                }
            );

            bool resourceMatch = any_of(
                statement.resources.begin(),
                statement.resources.end(),
                [&](const string& pattern) {
                    return matches(pattern, resource);
                }
            );

            if (!actionMatch || !resourceMatch) {
                continue;
            }

            if (statement.effect == Effect::DENY) {
                return false;
            }

            if (statement.effect == Effect::ALLOW) {
                allowed = true;
            }
        }

        return allowed;
    }
};

struct Identity {
    string id;
    IAMPolicy policy;
    bool active = true;
    bool mfaEnabled = false;
    bool privileged = false;
};

class IAMEngine {

private:
    unordered_map<string, Identity> identities;

public:

    void registerIdentity(const Identity& identity) {
        validateString(identity.id, "identity");

        if (identities.count(identity.id)) {
            throw invalid_argument("Duplicate identity");
        }

        identities.emplace(identity.id, identity);
    }

    bool authorize(
        const string& identityId,
        const string& action,
        const string& resource,
        bool requireMFA = true
    ) const {

        auto iterator = identities.find(identityId);

        if (iterator == identities.end()) {
            return false;
        }

        const Identity& identity = iterator->second;

        if (!identity.active) {
            return false;
        }

        if (requireMFA && !identity.mfaEnabled) {
            return false;
        }

        return identity.policy.authorize(action, resource);
    }

    const auto& getIdentities() const {
        return identities;
    }
};

// ============================================================
// KEY MANAGEMENT
// ============================================================

struct EncryptionKey {
    string alias;
    string keyId;
    bool enabled;
    unsigned int version;
};

class KeyManagementService {

private:
    map<string, EncryptionKey> keys;
    unsigned long long counter = 1000;

public:

    string createKey(const string& alias) {
        validateString(alias, "key alias");

        if (keys.count(alias)) {
            throw invalid_argument("Key already exists");
        }

        string keyId = "KMS-" + to_string(counter++);

        keys.emplace(
            alias,
            EncryptionKey{
                alias,
                keyId,
                true,
                1
            }
        );

        return keyId;
    }

    void rotateKey(const string& alias) {
        auto iterator = keys.find(alias);

        if (iterator == keys.end() || !iterator->second.enabled) {
            throw runtime_error("Key cannot be rotated");
        }

        iterator->second.keyId = "KMS-" + to_string(counter++);
        iterator->second.version++;
    }

    void disableKey(const string& alias) {
        auto iterator = keys.find(alias);

        if (iterator == keys.end()) {
            throw invalid_argument("Unknown key");
        }

        iterator->second.enabled = false;
    }

    bool enabled(const string& keyId) const {
        for (const auto& entry : keys) {
            if (
                entry.second.keyId == keyId &&
                entry.second.enabled
            ) {
                return true;
            }
        }

        return false;
    }

    optional<EncryptionKey> getKey(const string& alias) const {
        auto iterator = keys.find(alias);

        if (iterator == keys.end()) {
            return nullopt;
        }

        return iterator->second;
    }
};

// ============================================================
// CLOUD STORAGE
// ============================================================

struct StorageResource {
    string id;
    string owner;
    Environment environment;
    ResourceState state;
    optional<string> keyId;
};

class StorageService {

private:
    KeyManagementService& kms;
    unordered_map<string, StorageResource> resources;

public:

    explicit StorageService(KeyManagementService& service)
        : kms(service) {}

    void provision(const StorageResource& resource) {
        validateString(resource.id, "resource ID");

        if (resources.count(resource.id)) {
            throw invalid_argument("Duplicate resource");
        }

        resources.emplace(resource.id, resource);
    }

    void encrypt(
        const string& resourceId,
        const string& keyId
    ) {
        auto iterator = resources.find(resourceId);

        if (iterator == resources.end()) {
            throw invalid_argument("Resource not found");
        }

        if (!kms.enabled(keyId)) {
            throw runtime_error("Encryption key unavailable");
        }

        iterator->second.keyId = keyId;
        iterator->second.state = ResourceState::ENCRYPTED;
    }

    bool isSecure(const string& resourceId) const {
        auto iterator = resources.find(resourceId);

        if (iterator == resources.end()) {
            return false;
        }

        const auto& resource = iterator->second;

        return (
            resource.state == ResourceState::ENCRYPTED &&
            resource.keyId.has_value() &&
            kms.enabled(resource.keyId.value())
        );
    }

    const auto& getResources() const {
        return resources;
    }
};

// ============================================================
// NETWORK SECURITY
// ============================================================

struct NetworkRule {
    string source;
    string destination;
    int port;
    string protocol;
    Effect effect;
};

class NetworkSecurityGroup {

private:
    string name;
    vector<NetworkRule> rules;

public:

    explicit NetworkSecurityGroup(string groupName)
        : name(move(groupName)) {

        validateString(name, "network group");
    }

    void addRule(const NetworkRule& rule) {
        if (rule.port < 1 || rule.port > 65535) {
            throw invalid_argument("Invalid network port");
        }

        if (
            rule.protocol != "TCP" &&
            rule.protocol != "UDP" &&
            rule.protocol != "ICMP"
        ) {
            throw invalid_argument("Invalid protocol");
        }

        rules.push_back(rule);
    }

    bool permits(
        const string& source,
        const string& destination,
        int port,
        const string& protocol
    ) const {

        bool allowed = false;

        for (const auto& rule : rules) {

            bool sourceMatch = matches(rule.source, source);
            bool destinationMatch = matches(
                rule.destination,
                destination
            );

            if (
                sourceMatch &&
                destinationMatch &&
                rule.port == port &&
                rule.protocol == protocol
            ) {

                if (rule.effect == Effect::DENY) {
                    return false;
                }

                allowed = true;
            }
        }

        return allowed;
    }

    size_t ruleCount() const {
        return rules.size();
    }

    const string& getName() const {
        return name;
    }
};

// ============================================================
// AUDIT SYSTEM
// ============================================================

struct AuditEvent {
    unsigned long long sequence;
    string actor;
    string action;
    string resource;
    string result;
    string eventTime;
    Severity severity;
};

class AuditLogger {

private:
    vector<AuditEvent> events;

public:

    void record(
        const string& actor,
        const string& action,
        const string& resource,
        const string& result,
        Severity severity
    ) {
        events.push_back({
            events.size() + 1,
            actor,
            action,
            resource,
            result,
            timestamp(),
            severity
        });
    }

    void print() const {
        cout << "\nAUDIT EVENTS\n";

        for (const auto& event : events) {
            cout
                << event.sequence << " | "
                << event.eventTime << " | "
                << event.actor << " | "
                << event.action << " | "
                << event.resource << " | "
                << event.result << " | "
                << toString(event.severity)
                << '\n';
        }
    }

    size_t size() const {
        return events.size();
    }
};

// ============================================================
// SECURITY FINDINGS
// ============================================================

struct SecurityFinding {
    string category;
    string resource;
    string description;
    Severity severity;
};

class SecurityPostureEngine {

public:

    vector<SecurityFinding> evaluate(
        const IAMEngine& iam,
        const StorageService& storage,
        const KeyManagementService& kms,
        const NetworkSecurityGroup& network
    ) const {

        vector<SecurityFinding> findings;

        for (const auto& entry : iam.getIdentities()) {
            const auto& identity = entry.second;

            if (identity.active && !identity.mfaEnabled) {
                findings.push_back({
                    "IAM",
                    identity.id,
                    "Active identity lacks MFA",
                    Severity::HIGH
                });
            }
        }

        for (const auto& entry : storage.getResources()) {
            if (!storage.isSecure(entry.first)) {
                findings.push_back({
                    "ENCRYPTION",
                    entry.first,
                    "Storage encryption is missing or invalid",
                    Severity::CRITICAL
                });
            }
        }

        if (network.ruleCount() == 0) {
            findings.push_back({
                "NETWORK",
                network.getName(),
                "No explicit network rules",
                Severity::HIGH
            });
        }

        return findings;
    }
};

// ============================================================
// CLOUD GOVERNANCE APPLICATION
// ============================================================

class CloudSecurityPlatform {

private:
    KeyManagementService kms;
    StorageService storage;
    IAMEngine iam;
    NetworkSecurityGroup network;
    AuditLogger audit;
    SecurityPostureEngine posture;

public:

    CloudSecurityPlatform()
        : storage(kms),
          network("production-vpc") {}

    KeyManagementService& keyManager() {
        return kms;
    }

    StorageService& storageService() {
        return storage;
    }

    IAMEngine& iamEngine() {
        return iam;
    }

    NetworkSecurityGroup& networkGroup() {
        return network;
    }

    bool execute(
        const string& identity,
        const string& action,
        const string& resource
    ) {

        bool permitted = iam.authorize(
            identity,
            action,
            resource
        );

        audit.record(
            identity,
            action,
            resource,
            permitted ? "ALLOWED" : "DENIED",
            permitted ? Severity::LOW : Severity::HIGH
        );

        return permitted;
    }

    vector<SecurityFinding> evaluate() const {
        return posture.evaluate(iam, storage, kms, network);
    }

    void printReport() const {
        auto findings = evaluate();

        cout << "\nCLOUD SECURITY REPORT\n";

        cout << "Identities: "
             << iam.getIdentities().size() << '\n';

        cout << "Storage resources: "
             << storage.getResources().size() << '\n';

        cout << "Audit events: "
             << audit.size() << '\n';

        cout << "Findings: "
             << findings.size() << '\n';

        for (const auto& finding : findings) {
            cout
                << "[" << toString(finding.severity) << "] "
                << finding.category << " | "
                << finding.resource << " | "
                << finding.description << '\n';
        }

        cout << "Posture: "
             << (findings.empty() ? "COMPLIANT" : "ACTION REQUIRED")
             << '\n';

        audit.print();
    }
};

// ============================================================
// TESTS
// ============================================================

void runTests() {

    CloudSecurityPlatform platform;

    IAMPolicy policy;

    policy.addStatement({
        Effect::ALLOW,
        {"storage:read"},
        {"bucket:production/*"}
    });

    policy.addStatement({
        Effect::DENY,
        {"storage:delete"},
        {"*"}
    });

    Identity identity{
        "service-account-01",
        policy,
        true,
        true,
        false
    };

    platform.iamEngine().registerIdentity(identity);

    if (!platform.execute(
        "service-account-01",
        "storage:read",
        "bucket:production/reports"
    )) {
        throw runtime_error("IAM allow test failed");
    }

    if (platform.execute(
        "service-account-01",
        "storage:delete",
        "bucket:production/reports"
    )) {
        throw runtime_error("Explicit deny test failed");
    }

    if (platform.execute(
        "service-account-01",
        "storage:admin",
        "bucket:production/reports"
    )) {
        throw runtime_error("Default deny test failed");
    }

    string keyId = platform.keyManager().createKey(
        "production-key"
    );

    platform.storageService().provision({
        "database-backup",
        "database-team",
        Environment::PRODUCTION,
        ResourceState::ACTIVE,
        nullopt
    });

    platform.storageService().encrypt(
        "database-backup",
        keyId
    );

    if (!platform.storageService().isSecure("database-backup")) {
        throw runtime_error("Encryption test failed");
    }

    platform.networkGroup().addRule({
        "application-subnet",
        "database-subnet",
        5432,
        "TCP",
        Effect::ALLOW
    });

    platform.networkGroup().addRule({
        "internet",
        "database-subnet",
        5432,
        "TCP",
        Effect::DENY
    });

    if (!platform.networkGroup().permits(
        "application-subnet",
        "database-subnet",
        5432,
        "TCP"
    )) {
        throw runtime_error("Network allow test failed");
    }

    if (platform.networkGroup().permits(
        "internet",
        "database-subnet",
        5432,
        "TCP"
    )) {
        throw runtime_error("Network deny test failed");
    }

    cout << "All C++17 security tests passed.\n";

    platform.printReport();
}

// ============================================================
// MAIN
// ============================================================

int main() {

    try {
        runTests();
        return 0;
    }
    catch (const exception& error) {
        cerr << "Security engine error: "
             << error.what() << '\n';

        return 1;
    }
}
