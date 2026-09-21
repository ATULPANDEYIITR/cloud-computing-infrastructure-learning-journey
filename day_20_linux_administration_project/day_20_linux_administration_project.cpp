/*
 * Linux Administration Project
 *
 * C++17 technical case study:
 * Secure Linux Application Server Health and Configuration Auditor
 *
 * The program models an industry-style administrative utility that:
 *
 *   1. Loads a server configuration.
 *   2. Validates identity, SSH, service, network, and storage settings.
 *   3. Inspects selected Linux system information.
 *   4. Evaluates file permission policy.
 *   5. Produces structured audit findings.
 *   6. Calculates SHA-256-like file integrity using a deterministic standard-
 *      library-friendly demonstration hash. The implementation deliberately
 *      identifies this as a teaching hash rather than a cryptographic SHA-256.
 *   7. Demonstrates complexity and separation of concerns.
 *
 * Compile:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic linux_admin_project.cpp -o linux_admin_project
 *
 * Run:
 *   ./linux_admin_project
 *
 * The program is read-only with respect to real service state. It does not
 * create users, modify SSH configuration, restart services, or alter firewall
 * rules.
 */

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <regex>
#include <sstream>
#include <string>
#include <vector>

#ifdef __linux__
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace fs = std::filesystem;

// ---------------------------------------------------------------------------
// 1. Configuration data structures
// ---------------------------------------------------------------------------

struct ServerConfig {
    std::string hostname;
    int sshPort = 22;
    bool permitRootLogin = false;
    bool passwordAuthentication = false;
    bool publicKeyAuthentication = true;
    bool emptyPasswords = false;
    int maxAuthTries = 5;

    std::vector<std::string> requiredServices;
    std::vector<std::string> allowedTcpPorts;

    unsigned int minimumFreeDiskPercent = 15;
};

struct Finding {
    std::string category;
    std::string severity;
    std::string message;
};

class AuditReport {
private:
    std::vector<Finding> findings;

public:
    void add(
        const std::string& category,
        const std::string& severity,
        const std::string& message
    ) {
        findings.push_back({category, severity, message});
    }

    std::size_t size() const {
        return findings.size();
    }

    void print() const {
        std::cout << "\nAUDIT FINDINGS\n";
        std::cout << std::string(90, '=') << "\n";

        if (findings.empty()) {
            std::cout << "No findings were generated.\n";
            return;
        }

        for (const auto& finding : findings) {
            std::cout
                << "[" << finding.severity << "] "
                << finding.category << ": "
                << finding.message << "\n";
        }
    }
};


// ---------------------------------------------------------------------------
// 2. Validation utilities
// ---------------------------------------------------------------------------

bool validPort(int port) {
    return port >= 1 && port <= 65535;
}

bool validUsername(const std::string& username) {
    if (username.empty() || username.size() > 32) {
        return false;
    }

    if (!(std::islower(static_cast<unsigned char>(username[0])) ||
          username[0] == '_')) {
        return false;
    }

    for (char character : username) {
        if (!(std::islower(static_cast<unsigned char>(character)) ||
              std::isdigit(static_cast<unsigned char>(character)) ||
              character == '_' ||
              character == '-')) {
            return false;
        }
    }

    return true;
}

bool validHostname(const std::string& hostname) {
    if (hostname.empty() || hostname.size() > 253) {
        return false;
    }

    /*
     * A production implementation may use a more complete hostname parser.
     * This expression covers the ordinary DNS hostname form used by this
     * case study.
     */
    const std::regex pattern(
        R"(^([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$)"
    );

    return std::regex_match(hostname, pattern);
}


// ---------------------------------------------------------------------------
// 3. Linux user inventory
// ---------------------------------------------------------------------------

struct UserRecord {
    std::string username;
    unsigned long uid{};
    unsigned long gid{};
    std::string home;
    std::string shell;
};

std::vector<UserRecord> readPasswdFile(
    const std::string& filename = "/etc/passwd"
) {
    std::vector<UserRecord> users;
    std::ifstream file(filename);

    if (!file) {
        return users;
    }

    std::string line;

    while (std::getline(file, line)) {
        if (line.empty() || line[0] == '#') {
            continue;
        }

        std::vector<std::string> fields;
        std::stringstream stream(line);
        std::string field;

        while (std::getline(stream, field, ':')) {
            fields.push_back(field);
        }

        if (fields.size() != 7) {
            continue;
        }

        try {
            UserRecord user;
            user.username = fields[0];
            user.uid = std::stoul(fields[2]);
            user.gid = std::stoul(fields[3]);
            user.home = fields[5];
            user.shell = fields[6];

            users.push_back(user);
        } catch (const std::exception&) {
            // Malformed records are skipped rather than terminating the audit.
        }
    }

    return users;
}

std::string classifyUser(const UserRecord& user) {
    if (user.uid == 0) {
        return "root";
    }

    if (user.uid < 1000) {
        return "system/service";
    }

    return "regular";
}

void printUserInventory() {
    const auto users = readPasswdFile();

    std::cout << "\nUSER INVENTORY\n";
    std::cout << std::string(90, '=') << "\n";

    std::cout
        << std::left
        << std::setw(22) << "USERNAME"
        << std::setw(10) << "UID"
        << std::setw(10) << "GID"
        << std::setw(18) << "TYPE"
        << "SHELL\n";

    std::cout << std::string(90, '-') << "\n";

    const std::size_t limit = std::min<std::size_t>(users.size(), 25);

    for (std::size_t i = 0; i < limit; ++i) {
        const auto& user = users[i];

        std::cout
            << std::setw(22) << user.username
            << std::setw(10) << user.uid
            << std::setw(10) << user.gid
            << std::setw(18) << classifyUser(user)
            << user.shell << "\n";
    }
}


// ---------------------------------------------------------------------------
// 4. Permission model
// ---------------------------------------------------------------------------

int permissionDigit(char read, char write, char execute) {
    int value = 0;

    if (read == 'r') value += 4;
    if (write == 'w') value += 2;
    if (execute == 'x') value += 1;

    return value;
}

std::optional<int> symbolicPermissionToNumber(
    const std::string& permissions
) {
    if (permissions.size() != 9) {
        return std::nullopt;
    }

    for (char character : permissions) {
        if (character != 'r' &&
            character != 'w' &&
            character != 'x' &&
            character != '-') {
            return std::nullopt;
        }
    }

    const int owner = permissionDigit(
        permissions[0],
        permissions[1],
        permissions[2]
    );

    const int group = permissionDigit(
        permissions[3],
        permissions[4],
        permissions[5]
    );

    const int other = permissionDigit(
        permissions[6],
        permissions[7],
        permissions[8]
    );

    return owner * 100 + group * 10 + other;
}

std::string permissionFromMode(unsigned int mode) {
    std::string result;

    const std::vector<unsigned int> masks = {
        0400, 0200, 0100,
        0040, 0020, 0010,
        0004, 0002, 0001
    };

    const std::string symbols = "rwx";

    for (std::size_t i = 0; i < masks.size(); ++i) {
        if (mode & masks[i]) {
            result += symbols[i % 3];
        } else {
            result += '-';
        }
    }

    return result;
}

void demonstratePermissions(AuditReport& report) {
    std::cout << "\nPERMISSION ANALYSIS\n";
    std::cout << std::string(90, '=') << "\n";

    const std::vector<std::string> examples = {
        "rw-------",
        "rw-r-----",
        "rwxr-x---",
        "rw-r--r--",
        "rwxrwxrwx"
    };

    for (const auto& permission : examples) {
        const auto numeric = symbolicPermissionToNumber(permission);

        std::cout
            << permission
            << " -> ";

        if (numeric.has_value()) {
            std::cout << *numeric;
        } else {
            std::cout << "invalid";
        }

        std::cout << "\n";

        /*
         * The final "other write" bit is the ninth character in a symbolic
         * representation. World-writable resources deserve explicit review.
         */
        if (permission.size() == 9 && permission[7] == 'w') {
            report.add(
                "permissions",
                "HIGH",
                "An example resource grants write access to other users."
            );
        }
    }
}


// ---------------------------------------------------------------------------
// 5. SSH security policy
// ---------------------------------------------------------------------------

void auditSshPolicy(
    const ServerConfig& config,
    AuditReport& report
) {
    if (!validPort(config.sshPort)) {
        report.add(
            "SSH",
            "CRITICAL",
            "SSH port is outside the valid network port range."
        );
    }

    if (config.permitRootLogin) {
        report.add(
            "SSH",
            "HIGH",
            "Direct root SSH login is enabled."
        );
    }

    if (config.passwordAuthentication) {
        report.add(
            "SSH",
            "MEDIUM",
            "Password authentication is enabled."
        );
    }

    if (!config.publicKeyAuthentication) {
        report.add(
            "SSH",
            "HIGH",
            "Public-key authentication is disabled."
        );
    }

    if (config.emptyPasswords) {
        report.add(
            "SSH",
            "CRITICAL",
            "Empty-password SSH authentication is enabled."
        );
    }

    if (config.maxAuthTries < 1 || config.maxAuthTries > 10) {
        report.add(
            "SSH",
            "MEDIUM",
            "MaxAuthTries falls outside the selected policy range."
        );
    }
}


// ---------------------------------------------------------------------------
// 6. Service state model
// ---------------------------------------------------------------------------

enum class ServiceState {
    Active,
    Inactive,
    Failed,
    Unknown
};

std::string serviceStateToString(ServiceState state) {
    switch (state) {
        case ServiceState::Active:
            return "active";
        case ServiceState::Inactive:
            return "inactive";
        case ServiceState::Failed:
            return "failed";
        default:
            return "unknown";
    }
}

struct Service {
    std::string name;
    ServiceState state;
    bool enabledAtBoot;
};

class ServiceRegistry {
private:
    std::map<std::string, Service> services;

public:
    void addService(const Service& service) {
        services[service.name] = service;
    }

    std::optional<Service> find(const std::string& name) const {
        auto iterator = services.find(name);

        if (iterator == services.end()) {
            return std::nullopt;
        }

        return iterator->second;
    }

    void audit(
        const std::vector<std::string>& requiredServices,
        AuditReport& report
    ) const {
        for (const auto& required : requiredServices) {
            const auto service = find(required);

            if (!service.has_value()) {
                report.add(
                    "services",
                    "HIGH",
                    "Required service is not known to the service registry: " +
                    required
                );
                continue;
            }

            if (service->state != ServiceState::Active) {
                report.add(
                    "services",
                    "HIGH",
                    "Required service is not active: " + required
                );
            }

            if (!service->enabledAtBoot) {
                report.add(
                    "services",
                    "MEDIUM",
                    "Required service is not configured to start automatically: " +
                    required
                );
            }
        }
    }

    void print() const {
        std::cout << "\nSERVICE INVENTORY\n";
        std::cout << std::string(90, '=') << "\n";

        for (const auto& [name, service] : services) {
            std::cout
                << std::left
                << std::setw(25) << name
                << std::setw(12) << serviceStateToString(service.state)
                << "enabled-at-boot="
                << (service.enabledAtBoot ? "yes" : "no")
                << "\n";
        }
    }
};


// ---------------------------------------------------------------------------
// 7. Disk capacity
// ---------------------------------------------------------------------------

struct DiskUsage {
    std::uintmax_t capacityBytes{};
    std::uintmax_t freeBytes{};
};

std::optional<DiskUsage> getDiskUsage(const fs::path& directory) {
    std::error_code error;

    const auto space = fs::space(directory, error);

    if (error) {
        return std::nullopt;
    }

    return DiskUsage{
        space.capacity,
        space.available
    };
}

double freeDiskPercentage(const DiskUsage& disk) {
    if (disk.capacityBytes == 0) {
        return 0.0;
    }

    return
        static_cast<double>(disk.freeBytes) /
        static_cast<double>(disk.capacityBytes) *
        100.0;
}

void auditDisk(
    const fs::path& directory,
    unsigned int minimumFreePercent,
    AuditReport& report
) {
    const auto usage = getDiskUsage(directory);

    if (!usage.has_value()) {
        report.add(
            "storage",
            "WARNING",
            "Unable to inspect disk space for " + directory.string()
        );
        return;
    }

    const double freePercent = freeDiskPercentage(*usage);

    std::cout
        << "\nSTORAGE STATUS\n"
        << std::string(90, '=') << "\n"
        << "Path: " << directory << "\n"
        << "Capacity: " << usage->capacityBytes << " bytes\n"
        << "Free: " << usage->freeBytes << " bytes\n"
        << std::fixed << std::setprecision(2)
        << "Free percentage: " << freePercent << "%\n";

    if (freePercent < minimumFreePercent) {
        report.add(
            "storage",
            "HIGH",
            "Free disk capacity is below the configured threshold."
        );
    }
}


// ---------------------------------------------------------------------------
// 8. Configuration file and backup concepts
// ---------------------------------------------------------------------------

bool writeTextFile(
    const fs::path& filename,
    const std::string& content
) {
    std::ofstream file(filename);

    if (!file) {
        return false;
    }

    file << content;
    return static_cast<bool>(file);
}

std::string readTextFile(const fs::path& filename) {
    std::ifstream file(filename);

    if (!file) {
        return {};
    }

    std::ostringstream buffer;
    buffer << file.rdbuf();

    return buffer.str();
}

bool createBackup(
    const fs::path& source,
    const fs::path& destination
) {
    std::error_code error;

    fs::copy_file(
        source,
        destination,
        fs::copy_options::overwrite_existing,
        error
    );

    return !error;
}


// ---------------------------------------------------------------------------
// 9. Educational integrity hashing
// ---------------------------------------------------------------------------

/*
 * This is NOT SHA-256.
 *
 * C++17's standard library does not provide a cryptographic SHA-256 function.
 * Rather than introducing an external cryptographic dependency, the case
 * study uses four 64-bit FNV-1a-style accumulators to demonstrate file
 * integrity concepts.
 *
 * In a production security system, use a vetted cryptographic library for
 * SHA-256 or SHA-512 and do not implement cryptography casually.
 */

std::string educationalIntegrityHash(const std::string& content) {
    std::uint64_t h1 = 14695981039346656037ULL;
    std::uint64_t h2 = 1099511628211ULL;
    std::uint64_t h3 = 7809847782465536322ULL;
    std::uint64_t h4 = 9650029242287828579ULL;

    for (unsigned char byte : content) {
        h1 ^= byte;
        h1 *= 1099511628211ULL;

        h2 ^= static_cast<std::uint64_t>(byte) + 0x9e3779b9ULL;
        h2 *= 14029467366897019727ULL;

        h3 ^= static_cast<std::uint64_t>(byte) + 0x517cc1b727220a95ULL;
        h3 *= 1099511628211ULL;

        h4 ^= static_cast<std::uint64_t>(byte) + 0x94d049bb133111ebULL;
        h4 *= 14029467366897019727ULL;
    }

    std::ostringstream output;
    output
        << std::hex
        << std::setw(16) << std::setfill('0') << h1
        << std::setw(16) << h2
        << std::setw(16) << h3
        << std::setw(16) << h4;

    return output.str();
}


// ---------------------------------------------------------------------------
// 10. Idempotent configuration management
// ---------------------------------------------------------------------------

bool ensureConfiguration(
    const fs::path& filename,
    const std::string& desiredContent
) {
    /*
     * Idempotent automation checks current state before writing.
     * Repeating the operation therefore does not append duplicates.
     */
    const std::string current = readTextFile(filename);

    if (current == desiredContent) {
        return false;
    }

    return writeTextFile(filename, desiredContent);
}


// ---------------------------------------------------------------------------
// 11. Network policy
// ---------------------------------------------------------------------------

bool portIsAllowed(
    const std::vector<std::string>& allowedPorts,
    int port
) {
    const std::string target = std::to_string(port);

    return std::find(
        allowedPorts.begin(),
        allowedPorts.end(),
        target
    ) != allowedPorts.end();
}

void auditNetworkPolicy(
    const ServerConfig& config,
    AuditReport& report
) {
    if (!portIsAllowed(config.allowedTcpPorts, config.sshPort)) {
        report.add(
            "network",
            "HIGH",
            "Configured SSH port is not present in the allowed TCP policy."
        );
    }

    for (const auto& port : config.allowedTcpPorts) {
        try {
            const int numericPort = std::stoi(port);

            if (!validPort(numericPort)) {
                report.add(
                    "network",
                    "MEDIUM",
                    "Allowed-port list contains an invalid port: " + port
                );
            }
        } catch (const std::exception&) {
            report.add(
                "network",
                "MEDIUM",
                "Allowed-port list contains a non-numeric value: " + port
            );
        }
    }
}


// ---------------------------------------------------------------------------
// 12. Complete server audit
// ---------------------------------------------------------------------------

class ServerAuditor {
private:
    ServerConfig config;
    AuditReport report;

public:
    explicit ServerAuditor(ServerConfig serverConfig)
        : config(std::move(serverConfig)) {}

    void validateIdentity() {
        if (!validHostname(config.hostname)) {
            report.add(
                "identity",
                "HIGH",
                "Hostname does not satisfy the selected hostname policy."
            );
        }

        if (!validUsername("deploy_user")) {
            report.add(
                "identity",
                "CRITICAL",
                "Expected deployment account name is invalid."
            );
        }
    }

    void run(
        const fs::path& monitoredPath,
        const ServiceRegistry& services
    ) {
        validateIdentity();
        auditSshPolicy(config, report);
        auditNetworkPolicy(config, report);
        services.audit(config.requiredServices, report);
        auditDisk(
            monitoredPath,
            config.minimumFreeDiskPercent,
            report
        );
    }

    const AuditReport& getReport() const {
        return report;
    }
};


// ---------------------------------------------------------------------------
// 13. Performance comparison
// ---------------------------------------------------------------------------

void demonstrateAlgorithmicComplexity() {
    std::cout << "\nALGORITHMIC CONSIDERATIONS\n";
    std::cout << std::string(90, '=') << "\n";

    std::cout
        << "Vector search for a service name: O(n) average.\n"
        << "Map lookup by service name:        O(log n).\n"
        << "Hash-table lookup in unordered_map: "
        << "approximately O(1) average.\n"
        << "Recursive directory traversal:     O(n) entries visited.\n"
        << "Reading a file of size n:           O(n) data processed.\n"
        << "\nThe appropriate data structure depends on workload, ordering needs,\n"
        << "memory constraints, and predictable performance requirements.\n";
}


// ---------------------------------------------------------------------------
// 14. Full case study
// ---------------------------------------------------------------------------

void runCaseStudy() {
    std::cout << std::string(90, '=') << "\n";
    std::cout << "LINUX SERVER ADMINISTRATION C++ CASE STUDY\n";
    std::cout << std::string(90, '=') << "\n";

    /*
     * In an actual server deployment this configuration could come from a
     * validated configuration file, environment, orchestration system, or
     * management database. It is represented directly here so the program
     * remains self-contained.
     */
    ServerConfig config;
    config.hostname = "app-server-01.example.internal";
    config.sshPort = 22;
    config.permitRootLogin = false;
    config.passwordAuthentication = false;
    config.publicKeyAuthentication = true;
    config.emptyPasswords = false;
    config.maxAuthTries = 5;
    config.requiredServices = {
        "sshd",
        "application",
        "logging"
    };
    config.allowedTcpPorts = {
        "22",
        "443"
    };
    config.minimumFreeDiskPercent = 10;

    std::cout << "\nSERVER CONFIGURATION\n";
    std::cout << std::string(90, '-') << "\n";
    std::cout << "Hostname: " << config.hostname << "\n";
    std::cout << "SSH port: " << config.sshPort << "\n";
    std::cout
        << "Root SSH login: "
        << (config.permitRootLogin ? "enabled" : "disabled")
        << "\n";
    std::cout
        << "Password authentication: "
        << (config.passwordAuthentication ? "enabled" : "disabled")
        << "\n";
    std::cout
        << "Public-key authentication: "
        << (config.publicKeyAuthentication ? "enabled" : "disabled")
        << "\n";

    ServiceRegistry services;

    services.addService({
        "sshd",
        ServiceState::Active,
        true
    });

    services.addService({
        "application",
        ServiceState::Active,
        true
    });

    services.addService({
        "logging",
        ServiceState::Active,
        true
    });

    services.addService({
        "unused-development-service",
        ServiceState::Inactive,
        false
    });

    services.print();

    ServerAuditor auditor(config);
    auditor.run(".", services);

    demonstratePermissions(const_cast<AuditReport&>(
        auditor.getReport()
    ));

    auditor.getReport().print();

    /*
     * Temporary configuration demonstration.
     *
     * It remains inside the operating system's temporary directory and is
     * removed after this function finishes.
     */
    const fs::path labDirectory =
        fs::temp_directory_path() / "linux_admin_cpp_lab";

    std::error_code error;
    fs::create_directories(labDirectory, error);

    if (!error) {
        const fs::path configuration =
            labDirectory / "application.conf";

        const fs::path backup =
            labDirectory / "application.conf.bak";

        const std::string desiredConfiguration =
            "environment=production\n"
            "debug=false\n"
            "listen_address=127.0.0.1\n"
            "listen_port=8080\n";

        const bool firstChange =
            ensureConfiguration(
                configuration,
                desiredConfiguration
            );

        const bool secondChange =
            ensureConfiguration(
                configuration,
                desiredConfiguration
            );

        std::cout << "\nAUTOMATION TEST\n";
        std::cout << std::string(90, '-') << "\n";
        std::cout
            << "First configuration application changed state: "
            << (firstChange ? "yes" : "no")
            << "\n";

        std::cout
            << "Second configuration application changed state: "
            << (secondChange ? "yes" : "no")
            << "\n";

        if (createBackup(configuration, backup)) {
            const std::string original =
                readTextFile(configuration);

            const std::string copied =
                readTextFile(backup);

            const std::string originalHash =
                educationalIntegrityHash(original);

            const std::string backupHash =
                educationalIntegrityHash(copied);

            std::cout
                << "Backup created: " << backup << "\n"
                << "Original integrity hash: " << originalHash << "\n"
                << "Backup integrity hash:   " << backupHash << "\n"
                << "Integrity matches: "
                << (originalHash == backupHash ? "yes" : "no")
                << "\n";
        }

        fs::remove_all(labDirectory, error);
    }

    printUserInventory();
    demonstrateAlgorithmicComplexity();

    std::cout << "\nCASE STUDY COMPLETE\n";
    std::cout << std::string(90, '=') << "\n";
}


// ---------------------------------------------------------------------------
// 15. Main
// ---------------------------------------------------------------------------

int main() {
    try {
        runCaseStudy();
        return 0;
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << "\n";

        return 1;
    }
}
