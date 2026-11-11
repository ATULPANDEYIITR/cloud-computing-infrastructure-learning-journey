/*
 * Security Monitoring and Auditing
 *
 * C++17
 *
 * Repository-independent security monitoring engine:
 * - Audit event processing
 * - Access control evaluation
 * - Hash-chained audit records
 * - Sliding-window detection
 * - Security alerts
 * - Alert lifecycle management
 * - Branch-independent policy enforcement
 *
 * No external libraries.
 */

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <ctime>
#include <deque>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

using namespace std;

// ============================================================
// DOMAIN TYPES
// ============================================================

enum class EventType {
    LoginSuccess,
    LoginFailure,
    Logout,
    AccessGranted,
    AccessDenied,
    PrivilegeChange,
    DataExport,
    ConfigurationChange,
    PasswordChange,
    FirewallChange
};

enum class Severity {
    Low,
    Medium,
    High,
    Critical
};

enum class AlertStatus {
    Open,
    Investigating,
    Resolved,
    FalsePositive
};

string toString(EventType type) {

    static const map<EventType, string> names = {
        {EventType::LoginSuccess, "LOGIN_SUCCESS"},
        {EventType::LoginFailure, "LOGIN_FAILURE"},
        {EventType::Logout, "LOGOUT"},
        {EventType::AccessGranted, "ACCESS_GRANTED"},
        {EventType::AccessDenied, "ACCESS_DENIED"},
        {EventType::PrivilegeChange, "PRIVILEGE_CHANGE"},
        {EventType::DataExport, "DATA_EXPORT"},
        {EventType::ConfigurationChange, "CONFIGURATION_CHANGE"},
        {EventType::PasswordChange, "PASSWORD_CHANGE"},
        {EventType::FirewallChange, "FIREWALL_CHANGE"}
    };

    return names.at(type);
}

string toString(Severity severity) {

    switch (severity) {
        case Severity::Low: return "LOW";
        case Severity::Medium: return "MEDIUM";
        case Severity::High: return "HIGH";
        case Severity::Critical: return "CRITICAL";
    }

    throw logic_error("Unknown severity");
}

string toString(AlertStatus status) {

    switch (status) {
        case AlertStatus::Open: return "OPEN";
        case AlertStatus::Investigating: return "INVESTIGATING";
        case AlertStatus::Resolved: return "RESOLVED";
        case AlertStatus::FalsePositive: return "FALSE_POSITIVE";
    }

    throw logic_error("Unknown alert status");
}

// ============================================================
// SECURITY EVENT
// ============================================================

struct SecurityEvent {

    string id;
    int64_t timestamp;
    EventType type;

    string userId;
    string sourceIP;
    string resource;

    bool success;

    int exportedRecords = 0;
    string targetUser;
    string newRole;

    void validate() const {

        if (id.empty() || userId.empty()) {
            throw invalid_argument("Missing event identifier or user");
        }

        if (sourceIP.empty() || resource.empty()) {
            throw invalid_argument("Missing source IP or resource");
        }

        if (exportedRecords < 0) {
            throw invalid_argument("Negative export count");
        }
    }
};

// ============================================================
// SHA-256 IMPLEMENTATION
// ============================================================

class SHA256 {

private:

    static constexpr array<uint32_t, 64> K = {
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,
        0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,
        0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,
        0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,
        0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,
        0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,
        0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,
        0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,
        0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
    };

    static uint32_t rotateRight(uint32_t value, int count) {
        return (value >> count) | (value << (32 - count));
    }

public:

    static string hash(const string& input) {

        vector<uint8_t> data(input.begin(), input.end());

        uint64_t bitLength =
            static_cast<uint64_t>(data.size()) * 8;

        data.push_back(0x80);

        while (data.size() % 64 != 56) {
            data.push_back(0);
        }

        for (int i = 7; i >= 0; --i) {
            data.push_back(
                static_cast<uint8_t>(bitLength >> (i * 8))
            );
        }

        array<uint32_t, 8> state = {
            0x6a09e667,0xbb67ae85,0x3c6ef372,
            0xa54ff53a,0x510e527f,0x9b05688c,
            0x1f83d9ab,0x5be0cd19
        };

        for (size_t offset = 0; offset < data.size(); offset += 64) {

            array<uint32_t, 64> words{};

            for (int i = 0; i < 16; ++i) {

                size_t position = offset + i * 4;

                words[i] =
                    (static_cast<uint32_t>(data[position]) << 24) |
                    (static_cast<uint32_t>(data[position + 1]) << 16) |
                    (static_cast<uint32_t>(data[position + 2]) << 8) |
                    static_cast<uint32_t>(data[position + 3]);
            }

            for (int i = 16; i < 64; ++i) {

                uint32_t s0 =
                    rotateRight(words[i - 15], 7) ^
                    rotateRight(words[i - 15], 18) ^
                    (words[i - 15] >> 3);

                uint32_t s1 =
                    rotateRight(words[i - 2], 17) ^
                    rotateRight(words[i - 2], 19) ^
                    (words[i - 2] >> 10);

                words[i] =
                    words[i - 16] + s0 +
                    words[i - 7] + s1;
            }

            auto working = state;

            for (int i = 0; i < 64; ++i) {

                uint32_t s1 =
                    rotateRight(working[4], 6) ^
                    rotateRight(working[4], 11) ^
                    rotateRight(working[4], 25);

                uint32_t choice =
                    (working[4] & working[5]) ^
                    (~working[4] & working[6]);

                uint32_t temp1 =
                    working[7] + s1 + choice + K[i] + words[i];

                uint32_t s0 =
                    rotateRight(working[0], 2) ^
                    rotateRight(working[0], 13) ^
                    rotateRight(working[0], 22);

                uint32_t majority =
                    (working[0] & working[1]) ^
                    (working[0] & working[2]) ^
                    (working[1] & working[2]);

                uint32_t temp2 = s0 + majority;

                working[7] = working[6];
                working[6] = working[5];
                working[5] = working[4];
                working[4] = working[3] + temp1;
                working[3] = working[2];
                working[2] = working[1];
                working[1] = working[0];
                working[0] = temp1 + temp2;
            }

            for (int i = 0; i < 8; ++i) {
                state[i] += working[i];
            }
        }

        ostringstream output;
        output << hex << setfill('0');

        for (uint32_t value : state) {
            output << setw(8) << value;
        }

        return output.str();
    }
};

// ============================================================
// ACCESS POLICY
// ============================================================

class AccessPolicy {

private:

    unordered_map<string, set<string>> userRoles;

    unordered_map<string, set<string>> permissions;

public:

    AccessPolicy() {

        userRoles["alice"] = {"developer"};
        userRoles["bob"] = {"administrator"};
        userRoles["carol"] = {"auditor"};
        userRoles["david"] = {"analyst"};

        permissions["/admin"] = {"administrator"};

        permissions["/database"] = {
            "administrator", "developer"
        };

        permissions["/credentials"] = {
            "administrator"
        };

        permissions["/financial-records"] = {
            "administrator", "auditor"
        };

        permissions["/reports"] = {
            "administrator", "auditor", "analyst"
        };

        permissions["/application"] = {
            "administrator", "developer", "analyst"
        };
    }

    bool authorize(
        const string& user,
        const string& resource
    ) const {

        auto userIt = userRoles.find(user);
        auto permissionIt = permissions.find(resource);

        if (
            userIt == userRoles.end() ||
            permissionIt == permissions.end()
        ) {
            return false;
        }

        for (const string& role : userIt->second) {

            if (permissionIt->second.count(role)) {
                return true;
            }
        }

        return false;
    }

    void changeRole(
        const string& user,
        const string& role
    ) {

        if (!userRoles.count(user)) {
            throw invalid_argument("Unknown user");
        }

        static const set<string> allowed = {
            "administrator",
            "developer",
            "auditor",
            "analyst"
        };

        if (!allowed.count(role)) {
            throw invalid_argument("Invalid role");
        }

        userRoles[user] = {role};
    }
};

// ============================================================
// AUDIT LOG
// ============================================================

struct AuditRecord {
    SecurityEvent event;
    string previousHash;
    string hash;
};

class AuditLog {

private:

    vector<AuditRecord> records;
    unordered_set<string> eventIds;

    string lastHash = string(64, '0');

    static string serialize(const SecurityEvent& event) {

        ostringstream out;

        out
            << event.id << '|'
            << event.timestamp << '|'
            << toString(event.type) << '|'
            << event.userId << '|'
            << event.sourceIP << '|'
            << event.resource << '|'
            << event.success << '|'
            << event.exportedRecords << '|'
            << event.targetUser << '|'
            << event.newRole;

        return out.str();
    }

public:

    void append(const SecurityEvent& event) {

        event.validate();

        if (eventIds.count(event.id)) {
            throw invalid_argument("Duplicate audit event");
        }

        string content = serialize(event);

        string currentHash = SHA256::hash(
            lastHash + content
        );

        records.push_back({
            event,
            lastHash,
            currentHash
        });

        eventIds.insert(event.id);
        lastHash = currentHash;
    }

    bool verify() const {

        string previous(64, '0');

        unordered_set<string> identifiers;

        for (const auto& record : records) {

            if (record.previousHash != previous) {
                return false;
            }

            if (identifiers.count(record.event.id)) {
                return false;
            }

            string expected = SHA256::hash(
                previous + serialize(record.event)
            );

            if (expected != record.hash) {
                return false;
            }

            previous = record.hash;
            identifiers.insert(record.event.id);
        }

        return previous == lastHash;
    }

    size_t size() const {
        return records.size();
    }

    const vector<AuditRecord>& getRecords() const {
        return records;
    }
};

// ============================================================
// DETECTION RESULT
// ============================================================

struct DetectionResult {

    double score = 0.0;

    Severity severity = Severity::Low;

    vector<string> anomalies;
};

// ============================================================
// ANOMALY DETECTOR
// ============================================================

class AnomalyDetector {

private:

    deque<SecurityEvent> events;

    int64_t windowSeconds = 600;

    size_t failureThreshold = 5;
    size_t frequencyThreshold = 30;

    int exportThreshold = 1000;

    static bool isSensitive(const string& resource) {

        static const set<string> resources = {
            "/admin",
            "/database",
            "/credentials",
            "/financial-records",
            "/security-configuration"
        };

        return resources.count(resource) > 0;
    }

public:

    AnomalyDetector() = default;

    DetectionResult analyze(const SecurityEvent& event) {

        while (
            !events.empty() &&
            events.front().timestamp <
                event.timestamp - windowSeconds
        ) {
            events.pop_front();
        }

        events.push_back(event);

        vector<const SecurityEvent*> userEvents;

        for (const auto& item : events) {

            if (item.userId == event.userId) {
                userEvents.push_back(&item);
            }
        }

        DetectionResult result;

        size_t failed = 0;

        set<string> ipAddresses;

        for (const auto* item : userEvents) {

            if (item->type == EventType::LoginFailure) {
                ++failed;
            }

            if (
                item->type == EventType::LoginSuccess ||
                item->type == EventType::LoginFailure
            ) {
                ipAddresses.insert(item->sourceIP);
            }
        }

        if (failed >= failureThreshold) {

            result.anomalies.push_back(
                "REPEATED_FAILED_AUTHENTICATION"
            );

            result.score += 0.40;
        }

        if (ipAddresses.size() >= 3) {

            result.anomalies.push_back(
                "MULTIPLE_SOURCE_IP_ADDRESSES"
            );

            result.score += 0.25;
        }

        if (
            event.type == EventType::AccessDenied &&
            isSensitive(event.resource)
        ) {

            result.anomalies.push_back(
                "SENSITIVE_RESOURCE_ACCESS_DENIED"
            );

            result.score += 0.30;
        }

        if (event.type == EventType::PrivilegeChange) {

            result.anomalies.push_back(
                "PRIVILEGE_CHANGE"
            );

            result.score += 0.50;
        }

        if (
            event.type == EventType::DataExport &&
            event.exportedRecords > exportThreshold
        ) {

            result.anomalies.push_back(
                "UNUSUAL_DATA_EXPORT"
            );

            result.score += 0.45;
        }

        if (userEvents.size() > frequencyThreshold) {

            result.anomalies.push_back(
                "HIGH_EVENT_FREQUENCY"
            );

            result.score += 0.30;
        }

        result.score = min(result.score, 1.0);

        if (result.score >= 0.75) {
            result.severity = Severity::Critical;
        } else if (result.score >= 0.50) {
            result.severity = Severity::High;
        } else if (result.score >= 0.25) {
            result.severity = Severity::Medium;
        }

        return result;
    }
};

// ============================================================
// SECURITY ALERT
// ============================================================

struct SecurityAlert {

    string id;

    int64_t timestamp;

    string userId;

    Severity severity;

    AlertStatus status = AlertStatus::Open;

    vector<string> categories;

    vector<string> evidence;

    optional<string> assignedTo;
};

// ============================================================
// SECURITY MONITORING ENGINE
// ============================================================

class SecurityMonitoringEngine {

private:

    AccessPolicy accessPolicy;

    AuditLog auditLog;

    AnomalyDetector detector;

    vector<SecurityAlert> alerts;

    unordered_set<string> processedIds;

    map<EventType, size_t> eventStatistics;

    size_t nextId = 1;

public:

    optional<SecurityAlert> process(
        const SecurityEvent& event
    ) {

        event.validate();

        if (processedIds.count(event.id)) {
            throw invalid_argument("Duplicate event");
        }

        // A successful access event must agree with policy.
        if (
            event.type == EventType::AccessGranted &&
            !accessPolicy.authorize(
                event.userId,
                event.resource
            )
        ) {
            throw runtime_error(
                "Unauthorized access recorded as granted"
            );
        }

        // Record evidence before generating detection results.
        auditLog.append(event);

        processedIds.insert(event.id);

        eventStatistics[event.type]++;

        DetectionResult detection = detector.analyze(event);

        if (detection.anomalies.empty()) {
            return nullopt;
        }

        SecurityAlert alert;

        alert.id = "ALERT-" + to_string(nextId++);

        alert.timestamp = event.timestamp;

        alert.userId = event.userId;

        alert.severity = detection.severity;

        alert.categories = detection.anomalies;

        alert.evidence.push_back(event.id);

        alerts.push_back(alert);

        return alert;
    }

    void updateAlert(
        const string& alertId,
        AlertStatus status,
        optional<string> analyst = nullopt
    ) {

        auto it = find_if(
            alerts.begin(),
            alerts.end(),
            [&](const SecurityAlert& alert) {
                return alert.id == alertId;
            }
        );

        if (it == alerts.end()) {
            throw invalid_argument("Alert not found");
        }

        if (
            it->status == AlertStatus::Resolved ||
            it->status == AlertStatus::FalsePositive
        ) {
            throw logic_error("Alert is already closed");
        }

        if (
            status == AlertStatus::Investigating &&
            (!analyst || analyst->empty())
        ) {
            throw invalid_argument(
                "Investigation requires an analyst"
            );
        }

        it->status = status;

        if (analyst) {
            it->assignedTo = analyst;
        }
    }

    const vector<SecurityAlert>& getAlerts() const {
        return alerts;
    }

    const AuditLog& getAuditLog() const {
        return auditLog;
    }

    const AccessPolicy& getAccessPolicy() const {
        return accessPolicy;
    }

    void printReport() const {

        cout << "\nSECURITY MONITORING REPORT\n";

        cout << "Audit records: "
             << auditLog.size() << '\n';

        cout << "Audit integrity: "
             << (auditLog.verify() ? "VALID" : "INVALID")
             << '\n';

        cout << "Alerts: " << alerts.size() << '\n';

        map<string, int> severityCounts;

        for (const auto& alert : alerts) {
            severityCounts[toString(alert.severity)]++;
        }

        for (const auto& item : severityCounts) {

            cout << item.first
                 << ": "
                 << item.second
                 << '\n';
        }

        cout << "\nEVENT DISTRIBUTION\n";

        for (const auto& item : eventStatistics) {

            cout << toString(item.first)
                 << ": "
                 << item.second
                 << '\n';
        }
    }
};

// ============================================================
// SAMPLE EVENT FACTORY
// ============================================================

SecurityEvent makeEvent(
    string id,
    int64_t timestamp,
    EventType type,
    string user,
    string ip,
    string resource,
    bool success,
    int exported = 0
) {

    return {
        move(id),
        timestamp,
        type,
        move(user),
        move(ip),
        move(resource),
        success,
        exported,
        "",
        ""
    };
}

// ============================================================
// STATISTICAL ANOMALY DETECTION
// ============================================================

vector<size_t> statisticalAnomalies(
    const vector<double>& values,
    double threshold = 2.0
) {

    if (values.size() < 2 || threshold <= 0) {
        throw invalid_argument("Invalid statistical input");
    }

    for (double value : values) {

        if (!isfinite(value)) {
            throw invalid_argument("Non-finite observation");
        }
    }

    double mean = 0;

    for (double value : values) {
        mean += value;
    }

    mean /= values.size();

    double variance = 0;

    for (double value : values) {
        variance += (value - mean) * (value - mean);
    }

    variance /= values.size();

    double deviation = sqrt(variance);

    vector<size_t> result;

    if (deviation == 0) {
        return result;
    }

    for (size_t i = 0; i < values.size(); ++i) {

        double zScore = (values[i] - mean) / deviation;

        if (abs(zScore) > threshold) {
            result.push_back(i);
        }
    }

    return result;
}

// ============================================================
// TESTS
// ============================================================

void runTests() {

    SecurityMonitoringEngine engine;

    const int64_t base = 100000;

    vector<SecurityEvent> events;

    events.push_back(
        makeEvent(
            "E001", base,
            EventType::LoginSuccess,
            "alice", "192.168.1.10",
            "/authentication", true
        )
    );

    events.push_back(
        makeEvent(
            "E002", base + 5,
            EventType::AccessGranted,
            "alice", "192.168.1.10",
            "/application", true
        )
    );

    for (int i = 0; i < 6; ++i) {

        events.push_back(
            makeEvent(
                "E" + to_string(i + 3),
                base + 60 + i,
                EventType::LoginFailure,
                "david", "203.0.113.50",
                "/authentication", false
            )
        );
    }

    events.push_back(
        makeEvent(
            "E009", base + 120,
            EventType::AccessDenied,
            "alice", "192.168.1.10",
            "/credentials", false
        )
    );

    events.push_back(
        makeEvent(
            "E010", base + 180,
            EventType::PrivilegeChange,
            "bob", "192.168.1.20",
            "/admin", true
        )
    );

    events.push_back(
        makeEvent(
            "E011", base + 240,
            EventType::DataExport,
            "david", "203.0.113.50",
            "/financial-records", true, 5000
        )
    );

    for (const auto& event : events) {
        engine.process(event);
    }

    if (engine.getAuditLog().size() != events.size()) {
        throw runtime_error("Audit count test failed");
    }

    if (!engine.getAuditLog().verify()) {
        throw runtime_error("Audit integrity test failed");
    }

    if (engine.getAlerts().size() < 3) {
        throw runtime_error("Alert generation test failed");
    }

    if (
        !engine.getAccessPolicy().authorize(
            "alice", "/application"
        )
    ) {
        throw runtime_error("Access test failed");
    }

    if (
        engine.getAccessPolicy().authorize(
            "alice", "/credentials"
        )
    ) {
        throw runtime_error("Authorization failure test failed");
    }

    bool duplicateRejected = false;

    try {
        engine.process(events.front());
    } catch (const invalid_argument&) {
        duplicateRejected = true;
    }

    if (!duplicateRejected) {
        throw runtime_error("Duplicate event test failed");
    }

    auto anomalies = statisticalAnomalies(
        {10, 11, 10, 12, 100},
        1.5
    );

    if (anomalies.size() != 1 || anomalies.front() != 4) {
        throw runtime_error("Statistical test failed");
    }

    cout << "All C++17 security tests passed.\n";
}

// ============================================================
// MAIN
// ============================================================

int main() {

    try {

        SecurityMonitoringEngine engine;

        const int64_t base = 100000;

        engine.process(
            makeEvent(
                "EVT-001", base,
                EventType::LoginSuccess,
                "alice", "192.168.1.10",
                "/authentication", true
            )
        );

        engine.process(
            makeEvent(
                "EVT-002", base + 5,
                EventType::AccessGranted,
                "alice", "192.168.1.10",
                "/application", true
            )
        );

        for (int i = 0; i < 6; ++i) {

            engine.process(
                makeEvent(
                    "EVT-FAIL-" + to_string(i + 1),
                    base + 60 + i,
                    EventType::LoginFailure,
                    "david", "203.0.113.50",
                    "/authentication", false
                )
            );
        }

        engine.process(
            makeEvent(
                "EVT-003", base + 120,
                EventType::AccessDenied,
                "alice", "192.168.1.10",
                "/credentials", false
            )
        );

        engine.process(
            makeEvent(
                "EVT-004", base + 180,
                EventType::PrivilegeChange,
                "bob", "192.168.1.20",
                "/admin", true
            )
        );

        engine.process(
            makeEvent(
                "EVT-005", base + 240,
                EventType::DataExport,
                "david", "203.0.113.50",
                "/financial-records", true, 5000
            )
        );

        cout << "GENERATED ALERTS\n";

        for (const auto& alert : engine.getAlerts()) {

            cout
                << alert.id
                << " | "
                << toString(alert.severity)
                << " | "
                << alert.userId
                << " | ";

            for (const auto& category : alert.categories) {
                cout << category << " ";
            }

            cout << '\n';
        }

        engine.printReport();

        cout << "\nSTATISTICAL ANOMALIES\n";

        auto results = statisticalAnomalies(
            {12, 13, 11, 12, 14, 13, 90}
        );

        for (size_t index : results) {
            cout << "Anomalous index: " << index << '\n';
        }

        runTests();

    } catch (const exception& error) {

        cerr << "Security monitoring error: "
             << error.what()
             << '\n';

        return 1;
    }

    return 0;
}
