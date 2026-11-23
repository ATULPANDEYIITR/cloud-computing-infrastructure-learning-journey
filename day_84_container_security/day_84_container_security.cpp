#include <algorithm>
#include <array>
#include <chrono>
#include <cctype>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

/*
 * Container Security and Repository Admission Engine
 *
 * C++17
 *
 * Implements:
 * - Container image inventory
 * - CVE severity evaluation
 * - Minimal image controls
 * - Signature and provenance checks
 * - Non-root enforcement
 * - Secret exposure detection
 * - Runtime security events
 * - Branch-independent deployment admission
 */

enum class Severity {
    Critical = 5,
    High = 4,
    Medium = 3,
    Low = 2,
    Unknown = 1
};

enum class Decision {
    Allow,
    Deny,
    Review
};

enum class RuntimeEventType {
    ProcessExecution,
    ShellExecution,
    PrivilegedExecution,
    SecretAccess,
    FilesystemWrite,
    NetworkConnection
};

std::string toString(Severity severity) {
    switch (severity) {
        case Severity::Critical: return "CRITICAL";
        case Severity::High: return "HIGH";
        case Severity::Medium: return "MEDIUM";
        case Severity::Low: return "LOW";
        default: return "UNKNOWN";
    }
}

std::string toString(Decision decision) {
    switch (decision) {
        case Decision::Allow: return "ALLOW";
        case Decision::Deny: return "DENY";
        default: return "REVIEW";
    }
}

class Vulnerability {
public:
    std::string cveId;
    std::string package;
    std::string installedVersion;
    std::optional<std::string> fixedVersion;
    Severity severity;
    bool exploitable;

    Vulnerability(
        std::string id,
        std::string packageName,
        std::string version,
        std::optional<std::string> fix,
        Severity level,
        bool isExploitable = false
    )
        : cveId(std::move(id)),
          package(std::move(packageName)),
          installedVersion(std::move(version)),
          fixedVersion(std::move(fix)),
          severity(level),
          exploitable(isExploitable) {

        static const std::regex cvePattern(
            R"(CVE-[0-9]{4}-[0-9]{4,})"
        );

        if (!std::regex_match(cveId, cvePattern)) {
            throw std::invalid_argument("Invalid CVE identifier");
        }

        if (package.empty() || installedVersion.empty()) {
            throw std::invalid_argument("Invalid package metadata");
        }
    }
};

struct ContainerImage {
    std::string name;
    std::string tag;
    std::string digest;
    std::string baseImage;

    std::vector<std::string> packages;
    std::vector<Vulnerability> vulnerabilities;
    std::vector<std::string> secrets;

    int userId = 10001;
    double sizeMB = 50.0;

    bool privileged = false;
    bool containsShell = false;
    bool signatureVerified = false;

    void validate() const {
        static const std::regex digestPattern(
            R"(sha256:[a-f0-9]{64})"
        );

        if (name.empty() || tag.empty()) {
            throw std::invalid_argument(
                "Image name and tag are required"
            );
        }

        if (!std::regex_match(digest, digestPattern)) {
            throw std::invalid_argument("Invalid image digest");
        }

        if (userId < 0 || sizeMB <= 0) {
            throw std::invalid_argument("Invalid image configuration");
        }
    }
};

struct SecurityPolicy {
    int maxCritical = 0;
    int maxHigh = 0;
    int maxMedium = 5;

    double maxImageSizeMB = 200;

    bool requireNonRoot = true;
    bool forbidPrivileged = true;
    bool forbidShell = false;
    bool requireSignature = true;
    bool requireNoSecrets = true;
    bool requireFixedVulnerabilities = false;
    bool blockUnknownSeverity = true;
};

struct Finding {
    std::string control;
    Severity severity;
    std::string description;
    std::string remediation;
};

struct ScanReport {
    std::string imageName;
    std::map<Severity, int> counts;
    std::vector<Finding> findings;
    Decision decision = Decision::Allow;
};

class ImageScanner {
private:
    SecurityPolicy policy;

    void add(
        ScanReport& report,
        const std::string& control,
        Severity severity,
        const std::string& description,
        const std::string& remediation
    ) const {
        report.findings.push_back({
            control,
            severity,
            description,
            remediation
        });
    }

public:
    explicit ImageScanner(SecurityPolicy p)
        : policy(std::move(p)) {

        if (
            policy.maxCritical < 0 ||
            policy.maxHigh < 0 ||
            policy.maxMedium < 0 ||
            policy.maxImageSizeMB <= 0
        ) {
            throw std::invalid_argument("Invalid security policy");
        }
    }

    ScanReport scan(const ContainerImage& image) const {
        image.validate();

        ScanReport report;
        report.imageName = image.name;

        for (const auto& vulnerability : image.vulnerabilities) {
            report.counts[vulnerability.severity]++;

            std::string remediation =
                vulnerability.fixedVersion.has_value()
                ? "Upgrade to " + vulnerability.fixedVersion.value()
                : "Investigate mitigation or package replacement";

            add(
                report,
                "CVE",
                vulnerability.severity,
                vulnerability.cveId + ": " + vulnerability.package,
                remediation
            );

            if (
                policy.requireFixedVulnerabilities &&
                !vulnerability.fixedVersion.has_value()
            ) {
                add(
                    report,
                    "UNFIXED_CVE",
                    vulnerability.severity,
                    "No known fix for " + vulnerability.cveId,
                    "Apply mitigation or replace the vulnerable package"
                );
            }

            if (
                policy.blockUnknownSeverity &&
                vulnerability.severity == Severity::Unknown
            ) {
                add(
                    report,
                    "UNKNOWN_SEVERITY",
                    Severity::High,
                    vulnerability.cveId,
                    "Investigate vulnerability classification"
                );
            }
        }

        if (policy.requireNonRoot && image.userId == 0) {
            add(
                report,
                "NON_ROOT",
                Severity::High,
                "Container executes as root",
                "Configure a dedicated non-root UID"
            );
        }

        if (policy.forbidPrivileged && image.privileged) {
            add(
                report,
                "PRIVILEGED",
                Severity::Critical,
                "Privileged execution enabled",
                "Remove privileged mode and restrict capabilities"
            );
        }

        if (policy.forbidShell && image.containsShell) {
            add(
                report,
                "MINIMAL_IMAGE",
                Severity::Medium,
                "Runtime image contains a shell",
                "Use a shell-free minimal runtime image"
            );
        }

        if (image.sizeMB > policy.maxImageSizeMB) {
            add(
                report,
                "IMAGE_SIZE",
                Severity::Medium,
                "Image exceeds size policy",
                "Remove unnecessary packages and build artifacts"
            );
        }

        if (policy.requireSignature && !image.signatureVerified) {
            add(
                report,
                "SIGNATURE",
                Severity::High,
                "Image signature verification failed",
                "Verify image provenance and publisher identity"
            );
        }

        if (policy.requireNoSecrets && !image.secrets.empty()) {
            add(
                report,
                "SECRET_EXPOSURE",
                Severity::Critical,
                "Potential secrets embedded in image",
                "Rotate exposed credentials and rebuild image"
            );
        }

        const std::map<Severity, int> thresholds = {
            {Severity::Critical, policy.maxCritical},
            {Severity::High, policy.maxHigh},
            {Severity::Medium, policy.maxMedium}
        };

        for (const auto& [severity, maximum] : thresholds) {
            const int actual = report.counts[severity];

            if (actual > maximum) {
                add(
                    report,
                    "CVE_THRESHOLD",
                    severity,
                    std::to_string(actual) + " " +
                        toString(severity) + " vulnerabilities",
                    "Patch or mitigate affected packages"
                );
            }
        }

        const std::set<std::string> denyControls = {
            "NON_ROOT",
            "PRIVILEGED",
            "SIGNATURE",
            "SECRET_EXPOSURE",
            "UNKNOWN_SEVERITY",
            "UNFIXED_CVE"
        };

        bool denied = false;

        for (const auto& finding : report.findings) {
            if (denyControls.count(finding.control)) {
                denied = true;
                break;
            }

            if (
                finding.control == "CVE_THRESHOLD" &&
                (
                    finding.severity == Severity::Critical ||
                    finding.severity == Severity::High
                )
            ) {
                denied = true;
                break;
            }
        }

        if (denied) {
            report.decision = Decision::Deny;
        } else if (!report.findings.empty()) {
            report.decision = Decision::Review;
        }

        return report;
    }
};

struct RuntimeEvent {
    std::string containerId;
    RuntimeEventType type;
    std::string process;
    int userId;
};

class RuntimeSecurityEngine {
private:
    std::set<std::string> blockedProcesses = {
        "nc",
        "ncat",
        "socat",
        "tcpdump"
    };

    std::vector<std::pair<RuntimeEvent, Decision>> history;

    static std::string basename(const std::string& process) {
        const auto position = process.find_last_of("/\\");

        if (position == std::string::npos) {
            return process;
        }

        return process.substr(position + 1);
    }

public:
    Decision evaluate(const RuntimeEvent& event) {
        if (event.containerId.empty() || event.process.empty()) {
            throw std::invalid_argument("Malformed runtime event");
        }

        Decision decision = Decision::Allow;

        const std::string process = basename(event.process);

        if (
            event.userId == 0 ||
            event.type == RuntimeEventType::ShellExecution ||
            event.type == RuntimeEventType::PrivilegedExecution ||
            blockedProcesses.count(process)
        ) {
            decision = Decision::Deny;
        } else if (
            event.type == RuntimeEventType::SecretAccess ||
            event.type == RuntimeEventType::FilesystemWrite
        ) {
            decision = Decision::Review;
        }

        history.emplace_back(event, decision);

        return decision;
    }

    std::size_t eventCount() const {
        return history.size();
    }

    void printHistory() const {
        for (const auto& entry : history) {
            std::cout
                << entry.first.containerId
                << " | "
                << entry.first.process
                << " | "
                << toString(entry.second)
                << '\n';
        }
    }
};

class SecretDetector {
public:
    std::vector<std::string> scan(
        const std::string& content
    ) const {
        static const std::map<std::string, std::regex> patterns = {
            {
                "AWS_ACCESS_KEY",
                std::regex(R"(\bAKIA[0-9A-Z]{16}\b)")
            },
            {
                "PRIVATE_KEY",
                std::regex(
                    R"(-----BEGIN (?:RSA |EC )?PRIVATE KEY-----)"
                )
            },
            {
                "GITHUB_TOKEN",
                std::regex(R"(\bgh[pousr]_[A-Za-z0-9]{30,}\b)")
            },
            {
                "PASSWORD",
                std::regex(
                    R"((password|passwd|secret)\s*[:=]\s*['"]?[^'"\s]{8,})",
                    std::regex::icase
                )
            }
        };

        std::vector<std::string> findings;

        for (const auto& [name, pattern] : patterns) {
            if (std::regex_search(content, pattern)) {
                findings.push_back(name);
            }
        }

        return findings;
    }
};

class AdmissionController {
private:
    const ImageScanner& scanner;
    std::set<std::string> deployedDigests;

public:
    explicit AdmissionController(const ImageScanner& s)
        : scanner(s) {}

    Decision admit(const ContainerImage& image) {
        ScanReport report = scanner.scan(image);

        std::cout
            << "\nImage: " << report.imageName
            << "\nDecision: " << toString(report.decision)
            << "\nFindings: " << report.findings.size()
            << '\n';

        for (const auto& finding : report.findings) {
            std::cout
                << finding.control << " | "
                << toString(finding.severity) << " | "
                << finding.description << '\n';
        }

        if (report.decision != Decision::Allow) {
            throw std::runtime_error(
                "Admission denied by security policy"
            );
        }

        deployedDigests.insert(image.digest);

        return Decision::Allow;
    }
};

ContainerImage createImage() {
    ContainerImage image;

    image.name = "orders-api";
    image.tag = "1.5.0";
    image.digest = "sha256:" + std::string(64, 'c');
    image.baseImage = "distroless/runtime";

    image.packages = {
        "runtime",
        "application-library"
    };

    image.vulnerabilities.emplace_back(
        "CVE-2024-12345",
        "example-library",
        "1.0.0",
        std::string("1.0.2"),
        Severity::Low
    );

    image.userId = 10001;
    image.sizeMB = 60;
    image.privileged = false;
    image.containsShell = false;
    image.signatureVerified = true;

    return image;
}

int main() {
    try {
        SecurityPolicy policy;

        policy.maxCritical = 0;
        policy.maxHigh = 0;
        policy.maxMedium = 3;
        policy.maxImageSizeMB = 100;
        policy.requireNonRoot = true;
        policy.forbidPrivileged = true;
        policy.forbidShell = true;
        policy.requireSignature = true;

        ImageScanner scanner(policy);
        AdmissionController admission(scanner);

        std::cout << "CONTAINER SECURITY ENGINE\n";

        ContainerImage image = createImage();

        admission.admit(image);

        std::cout << "\nNEGATIVE ADMISSION TEST\n";

        ContainerImage compromised = createImage();
        compromised.name = "untrusted-api";
        compromised.userId = 0;
        compromised.privileged = true;
        compromised.secrets.push_back("PRIVATE_KEY");
        compromised.signatureVerified = false;

        try {
            admission.admit(compromised);
        } catch (const std::exception& error) {
            std::cout << "Rejected: " << error.what() << '\n';
        }

        std::cout << "\nRUNTIME SECURITY\n";

        RuntimeSecurityEngine runtime;

        std::vector<RuntimeEvent> events = {
            {
                "container-001",
                RuntimeEventType::ProcessExecution,
                "application",
                10001
            },
            {
                "container-001",
                RuntimeEventType::ShellExecution,
                "/bin/sh",
                10001
            },
            {
                "container-001",
                RuntimeEventType::SecretAccess,
                "application",
                10001
            },
            {
                "container-001",
                RuntimeEventType::ProcessExecution,
                "nc",
                10001
            }
        };

        for (const auto& event : events) {
            std::cout
                << event.process << ": "
                << toString(runtime.evaluate(event))
                << '\n';
        }

        runtime.printHistory();

        std::cout << "\nSECRET DETECTION\n";

        SecretDetector detector;

        auto secrets = detector.scan(
            "password=ExampleSecret123456"
        );

        for (const auto& finding : secrets) {
            std::cout << finding << '\n';
        }

        if (secrets.empty()) {
            std::cout << "No matching patterns found\n";
        }

        std::cout << "\nVALIDATION\n";

        if (scanner.scan(image).decision != Decision::Allow) {
            throw std::runtime_error("Valid image was unexpectedly rejected");
        }

        if (runtime.eventCount() != 4) {
            throw std::runtime_error("Runtime event count mismatch");
        }

        std::cout << "All checks passed\n";

        return 0;

    } catch (const std::exception& error) {
        std::cerr << "Security engine error: "
                  << error.what() << '\n';
        return 1;
    }
}
