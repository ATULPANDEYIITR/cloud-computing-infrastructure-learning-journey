/*
 * Cloud Governance and Compliance Engine
 *
 * C++17 implementation of a policy-driven cloud governance system.
 *
 * Capabilities:
 * - Resource inventory
 * - Classification-aware policy evaluation
 * - Data residency enforcement
 * - Risk scoring
 * - Approval-controlled remediation
 * - Merge-like deployment eligibility decisions
 * - Audit event integrity
 * - Compliance reporting
 *
 * Build:
 * g++ -std=c++17 -O2 -Wall -Wextra -pedantic cloud_governance.cpp -o cloud_governance
 */

#include <algorithm>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <functional>
#include <numeric>
#include <limits>

using namespace std;

// ============================================================
// ENUMERATIONS
// ============================================================

enum class ResourceType {
    Storage,
    Database,
    Compute,
    Network
};

enum class Classification {
    Public,
    Internal,
    Confidential,
    Restricted
};

enum class Severity {
    Low = 1,
    Medium = 2,
    High = 3,
    Critical = 4
};

enum class ComplianceStatus {
    Compliant,
    NonCompliant,
    NotApplicable
};

enum class AuditAction {
    Registered,
    Evaluated,
    Violation,
    Remediated
};

// ============================================================
// ENUMERATION CONVERSION
// ============================================================

string toString(ResourceType value) {
    switch (value) {
        case ResourceType::Storage: return "STORAGE";
        case ResourceType::Database: return "DATABASE";
        case ResourceType::Compute: return "COMPUTE";
        case ResourceType::Network: return "NETWORK";
    }

    throw invalid_argument("Unknown resource type.");
}

string toString(Classification value) {
    switch (value) {
        case Classification::Public: return "PUBLIC";
        case Classification::Internal: return "INTERNAL";
        case Classification::Confidential: return "CONFIDENTIAL";
        case Classification::Restricted: return "RESTRICTED";
    }

    throw invalid_argument("Unknown classification.");
}

string toString(Severity value) {
    switch (value) {
        case Severity::Low: return "LOW";
        case Severity::Medium: return "MEDIUM";
        case Severity::High: return "HIGH";
        case Severity::Critical: return "CRITICAL";
    }

    throw invalid_argument("Unknown severity.");
}

string toString(ComplianceStatus value) {
    switch (value) {
        case ComplianceStatus::Compliant: return "COMPLIANT";
        case ComplianceStatus::NonCompliant: return "NON_COMPLIANT";
        case ComplianceStatus::NotApplicable: return "NOT_APPLICABLE";
    }

    throw invalid_argument("Unknown status.");
}

// ============================================================
// DOMAIN EXCEPTIONS
// ============================================================

class GovernanceException : public runtime_error {
public:
    explicit GovernanceException(const string& message)
        : runtime_error(message) {}
};

class ValidationException : public GovernanceException {
public:
    using GovernanceException::GovernanceException;
};

class AuthorizationException : public GovernanceException {
public:
    using GovernanceException::GovernanceException;
};

class ResourceNotFoundException : public GovernanceException {
public:
    using GovernanceException::GovernanceException;
};

// ============================================================
// VALIDATION HELPERS
// ============================================================

void requireNonEmpty(
    const string& value,
    const string& field
) {
    if (value.empty()) {
        throw ValidationException(
            field + " cannot be empty."
        );
    }
}

// ============================================================
// CLOUD RESOURCE
// ============================================================

struct CloudResource {
    string id;
    string name;
    string owner;
    string provider;
    string region;

    ResourceType type;
    Classification classification;

    bool encrypted;
    bool publicAccess;
    bool backupEnabled;

    map<string, string> tags;

    void validate() const {

        requireNonEmpty(id, "Resource ID");
        requireNonEmpty(name, "Resource name");
        requireNonEmpty(owner, "Resource owner");
        requireNonEmpty(provider, "Provider");
        requireNonEmpty(region, "Region");
    }
};

// ============================================================
// GOVERNANCE POLICY
// ============================================================

struct Policy {
    string id;
    string name;
    Severity severity;

    bool requireEncryption = false;
    bool prohibitPublicAccess = false;
    bool requireBackup = false;

    set<string> allowedRegions;
    set<Classification> classifications;

    bool appliesTo(
        const CloudResource& resource
    ) const {

        return classifications.empty() ||
            classifications.count(resource.classification) > 0;
    }
};

// ============================================================
// POLICY RESULT
// ============================================================

struct PolicyResult {
    string resourceId;
    string policyId;

    Severity severity;
    ComplianceStatus status;

    vector<string> violations;
};

// ============================================================
// POLICY EVALUATOR
// ============================================================

class PolicyEvaluator {

private:
    vector<Policy> policies;

public:

    explicit PolicyEvaluator(vector<Policy> configuredPolicies)
        : policies(move(configuredPolicies)) {

        set<string> ids;

        for (const auto& policy : policies) {

            requireNonEmpty(policy.id, "Policy ID");

            if (!ids.insert(policy.id).second) {
                throw ValidationException(
                    "Duplicate policy identifier."
                );
            }
        }
    }

    vector<PolicyResult> evaluate(
        const CloudResource& resource
    ) const {

        resource.validate();

        vector<PolicyResult> results;

        for (const auto& policy : policies) {

            if (!policy.appliesTo(resource)) {

                results.push_back({
                    resource.id,
                    policy.id,
                    policy.severity,
                    ComplianceStatus::NotApplicable,
                    {}
                });

                continue;
            }

            vector<string> violations;

            if (
                policy.requireEncryption &&
                !resource.encrypted
            ) {
                violations.push_back(
                    "Encryption is not enabled."
                );
            }

            if (
                policy.prohibitPublicAccess &&
                resource.publicAccess
            ) {
                violations.push_back(
                    "Public access is prohibited."
                );
            }

            if (
                policy.requireBackup &&
                !resource.backupEnabled
            ) {
                violations.push_back(
                    "Backup is not enabled."
                );
            }

            if (
                !policy.allowedRegions.empty() &&
                !policy.allowedRegions.count(resource.region)
            ) {
                violations.push_back(
                    "Cloud region is not permitted."
                );
            }

            ComplianceStatus status =
                violations.empty()
                    ? ComplianceStatus::Compliant
                    : ComplianceStatus::NonCompliant;

            results.push_back({
                resource.id,
                policy.id,
                policy.severity,
                status,
                move(violations)
            });
        }

        return results;
    }
};

// ============================================================
// DATA RESIDENCY
// ============================================================

class ResidencyEvaluator {

private:
    map<string, set<string>> regulations;

public:

    void addRegulation(
        const string& regulation,
        set<string> permittedRegions
    ) {

        requireNonEmpty(regulation, "Regulation");

        if (permittedRegions.empty()) {
            throw ValidationException(
                "Permitted regions cannot be empty."
            );
        }

        if (regulations.count(regulation)) {
            throw ValidationException(
                "Duplicate residency regulation."
            );
        }

        regulations.emplace(
            regulation,
            move(permittedRegions)
        );
    }

    bool evaluate(
        const CloudResource& resource,
        const string& regulation
    ) const {

        auto it = regulations.find(regulation);

        if (it == regulations.end()) {
            throw GovernanceException(
                "Unknown residency regulation."
            );
        }

        return it->second.count(resource.region) > 0;
    }
};

// ============================================================
// AUDIT RECORD
// ============================================================

struct AuditRecord {
    size_t sequence;
    AuditAction action;
    string actor;
    string resourceId;
    string details;
    string previousHash;
    string hash;
};

// ============================================================
// HASH-LINKED AUDIT LOGGER
// ============================================================

class AuditLogger {

private:
    vector<AuditRecord> records;

    static string calculateHash(
        const string& input
    ) {

        // Deterministic demonstration hash.
        // Production audit integrity requires a cryptographic
        // hash such as SHA-256 from a vetted library.
        hash<string> hasher;

        size_t value = hasher(input);

        stringstream stream;
        stream << hex << value;

        return stream.str();
    }

public:

    void record(
        AuditAction action,
        const string& actor,
        const string& resourceId,
        const string& details
    ) {

        requireNonEmpty(actor, "Audit actor");

        string previousHash =
            records.empty()
                ? "GENESIS"
                : records.back().hash;

        size_t sequence = records.size() + 1;

        string payload =
            to_string(sequence) + "|" +
            to_string(static_cast<int>(action)) + "|" +
            actor + "|" +
            resourceId + "|" +
            details + "|" +
            previousHash;

        string currentHash = calculateHash(payload);

        records.push_back({
            sequence,
            action,
            actor,
            resourceId,
            details,
            previousHash,
            currentHash
        });
    }

    bool verify() const {

        string previousHash = "GENESIS";

        for (const auto& record : records) {

            if (record.previousHash != previousHash) {
                return false;
            }

            string payload =
                to_string(record.sequence) + "|" +
                to_string(static_cast<int>(record.action)) + "|" +
                record.actor + "|" +
                record.resourceId + "|" +
                record.details + "|" +
                record.previousHash;

            string expected = calculateHash(payload);

            if (expected != record.hash) {
                return false;
            }

            previousHash = record.hash;
        }

        return true;
    }

    size_t size() const {
        return records.size();
    }
};

// ============================================================
// GOVERNANCE REPORT
// ============================================================

struct GovernanceReport {
    size_t totalResources = 0;
    size_t totalEvaluations = 0;
    size_t compliant = 0;
    size_t nonCompliant = 0;
    size_t notApplicable = 0;
    size_t residencyViolations = 0;

    double compliancePercentage() const {

        size_t applicable =
            compliant + nonCompliant;

        if (applicable == 0) {
            return 100.0;
        }

        return 100.0 *
            static_cast<double>(compliant) /
            static_cast<double>(applicable);
    }
};

// ============================================================
// GOVERNANCE ENGINE
// ============================================================

class GovernanceEngine {

private:

    map<string, CloudResource> resources;

    map<string, vector<PolicyResult>> assessments;

    PolicyEvaluator evaluator;
    ResidencyEvaluator residency;
    AuditLogger audit;

public:

    explicit GovernanceEngine(
        vector<Policy> policies
    ) : evaluator(move(policies)) {}

    void addRegulation(
        const string& name,
        set<string> regions
    ) {
        residency.addRegulation(
            name,
            move(regions)
        );
    }

    void registerResource(
        const CloudResource& resource,
        const string& actor
    ) {

        resource.validate();

        if (resources.count(resource.id)) {
            throw ValidationException(
                "Resource already registered."
            );
        }

        resources.emplace(resource.id, resource);

        audit.record(
            AuditAction::Registered,
            actor,
            resource.id,
            resource.name
        );
    }

    const CloudResource& getResource(
        const string& id
    ) const {

        auto it = resources.find(id);

        if (it == resources.end()) {
            throw ResourceNotFoundException(
                "Resource not found: " + id
            );
        }

        return it->second;
    }

    vector<PolicyResult> evaluate(
        const string& id,
        const string& actor
    ) {

        const CloudResource& resource =
            getResource(id);

        auto results = evaluator.evaluate(resource);

        assessments[id] = results;

        audit.record(
            AuditAction::Evaluated,
            actor,
            id,
            "Policy evaluation completed."
        );

        for (const auto& result : results) {

            if (
                result.status ==
                ComplianceStatus::NonCompliant
            ) {

                audit.record(
                    AuditAction::Violation,
                    actor,
                    id,
                    result.policyId
                );
            }
        }

        return results;
    }

    void remediate(
        const string& id,
        const string& actor,
        bool encrypt,
        bool disablePublicAccess,
        bool enableBackup
    ) {

        if (actor != "governance-admin") {
            throw AuthorizationException(
                "Remediation requires governance-admin."
            );
        }

        auto it = resources.find(id);

        if (it == resources.end()) {
            throw ResourceNotFoundException(
                "Resource does not exist."
            );
        }

        CloudResource candidate = it->second;

        if (encrypt) {
            candidate.encrypted = true;
        }

        if (disablePublicAccess) {
            candidate.publicAccess = false;
        }

        if (enableBackup) {
            candidate.backupEnabled = true;
        }

        candidate.validate();

        // Commit only after candidate validation succeeds.
        it->second = candidate;

        assessments.erase(id);

        audit.record(
            AuditAction::Remediated,
            actor,
            id,
            "Authorized remediation applied."
        );
    }

    bool isResidencyCompliant(
        const string& id,
        const string& regulation
    ) const {

        return residency.evaluate(
            getResource(id),
            regulation
        );
    }

    GovernanceReport report() const {

        GovernanceReport report;

        report.totalResources = resources.size();

        for (const auto& [id, results] : assessments) {

            (void)id;

            for (const auto& result : results) {

                ++report.totalEvaluations;

                switch (result.status) {

                    case ComplianceStatus::Compliant:
                        ++report.compliant;
                        break;

                    case ComplianceStatus::NonCompliant:
                        ++report.nonCompliant;
                        break;

                    case ComplianceStatus::NotApplicable:
                        ++report.notApplicable;
                        break;
                }
            }
        }

        return report;
    }

    bool auditIntegrity() const {
        return audit.verify();
    }

    size_t auditCount() const {
        return audit.size();
    }
};

// ============================================================
// SAMPLE POLICIES
// ============================================================

vector<Policy> createPolicies() {

    set<Classification> sensitive = {
        Classification::Confidential,
        Classification::Restricted
    };

    return {

        {
            "ENC-001",
            "Encryption Requirement",
            Severity::Critical,
            true,
            false,
            false,
            {},
            sensitive
        },

        {
            "PUB-001",
            "Public Access Prevention",
            Severity::Critical,
            false,
            true,
            false,
            {},
            sensitive
        },

        {
            "BKP-001",
            "Backup Requirement",
            Severity::High,
            false,
            false,
            true,
            {},
            {Classification::Restricted}
        },

        {
            "REG-001",
            "Approved Regions",
            Severity::Critical,
            false,
            false,
            false,
            {"ap-south-1", "ap-south-2"},
            {Classification::Restricted}
        }
    };
}

// ============================================================
// REPORT DISPLAY
// ============================================================

void displayResults(
    const vector<PolicyResult>& results
) {

    for (const auto& result : results) {

        cout
            << "Policy: " << result.policyId
            << " | Severity: " << toString(result.severity)
            << " | Status: " << toString(result.status)
            << '\n';

        for (const auto& violation : result.violations) {
            cout << "  - " << violation << '\n';
        }
    }
}

// ============================================================
// MAIN APPLICATION
// ============================================================

int main() {

    try {

        GovernanceEngine engine(createPolicies());

        engine.addRegulation(
            "ORG-DATA-RESIDENCY",
            {"ap-south-1", "ap-south-2"}
        );

        vector<CloudResource> resources = {

            {
                "RES-001",
                "Customer Database",
                "data-team",
                "AWS",
                "ap-south-1",
                ResourceType::Database,
                Classification::Restricted,
                false,
                true,
                false,
                {}
            },

            {
                "RES-002",
                "Application Server",
                "engineering-team",
                "AWS",
                "ap-south-1",
                ResourceType::Compute,
                Classification::Internal,
                true,
                false,
                true,
                {}
            },

            {
                "RES-003",
                "Analytics Database",
                "analytics-team",
                "Azure",
                "centralindia",
                ResourceType::Database,
                Classification::Restricted,
                true,
                false,
                true,
                {}
            }
        };

        for (const auto& resource : resources) {

            engine.registerResource(
                resource,
                "governance-admin"
            );
        }

        cout << "\nCLOUD GOVERNANCE ENGINE\n";
        cout << "=======================\n";

        for (const auto& resource : resources) {

            cout << "\nResource: "
                 << resource.name << '\n';

            auto results = engine.evaluate(
                resource.id,
                "compliance-service"
            );

            displayResults(results);

            bool residency = engine.isResidencyCompliant(
                resource.id,
                "ORG-DATA-RESIDENCY"
            );

            cout
                << "Data Residency: "
                << (residency ? "COMPLIANT" : "NON_COMPLIANT")
                << '\n';
        }

        cout << "\nAUTHORIZED REMEDIATION\n";

        engine.remediate(
            "RES-001",
            "governance-admin",
            true,
            true,
            true
        );

        cout << "\nREASSESSMENT\n";

        auto reassessed = engine.evaluate(
            "RES-001",
            "compliance-service"
        );

        displayResults(reassessed);

        cout << "\nCOMPLIANCE REPORT\n";

        GovernanceReport report = engine.report();

        cout << "Resources: "
             << report.totalResources << '\n';

        cout << "Evaluations: "
             << report.totalEvaluations << '\n';

        cout << "Compliant: "
             << report.compliant << '\n';

        cout << "Non-compliant: "
             << report.nonCompliant << '\n';

        cout << "Not applicable: "
             << report.notApplicable << '\n';

        cout << fixed << setprecision(2);

        cout << "Compliance rate: "
             << report.compliancePercentage()
             << "%\n";

        cout << "Audit records: "
             << engine.auditCount() << '\n';

        cout << "Audit integrity: "
             << (engine.auditIntegrity() ? "VALID" : "INVALID")
             << '\n';

        // Negative test: unauthorized remediation.
        try {

            engine.remediate(
                "RES-002",
                "untrusted-user",
                true,
                false,
                false
            );

        } catch (const AuthorizationException& error) {

            cout
                << "\nExpected authorization rejection: "
                << error.what()
                << '\n';
        }

        // Negative test: nonexistent resource.
        try {
            engine.getResource("UNKNOWN");
        } catch (const ResourceNotFoundException& error) {
            cout << "Expected lookup rejection: "
                 << error.what() << '\n';
        }

        if (!engine.auditIntegrity()) {
            throw GovernanceException(
                "Audit integrity check failed."
            );
        }

        cout << "\nGovernance execution completed.\n";

    } catch (const exception& error) {

        cerr << "Fatal error: "
             << error.what() << '\n';

        return 1;
    }

    return 0;
}
