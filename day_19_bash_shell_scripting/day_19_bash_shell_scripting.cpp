#include <algorithm>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Bash Shell Scripting: C++ Automation Case Study
 *
 * This program models a realistic backup-and-health-check automation system.
 *
 * It demonstrates concepts that are central to Bash scripting:
 *
 *   - variables and configuration
 *   - conditions
 *   - loops
 *   - functions
 *   - command-line arguments
 *   - validation
 *   - filesystem operations
 *   - logging
 *   - retries
 *   - dry-run execution
 *   - idempotency
 *   - exit-status design
 *   - dependency checks
 *   - error handling
 *   - data structures
 *   - performance considerations
 *   - security considerations
 *
 * The program is intentionally implemented with the C++ standard library.
 * It does not invoke arbitrary shell commands.
 *
 * Build:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic bash_automation_case_study.cpp -o automation
 *
 * Run:
 *   ./automation
 *   ./automation --source ./input --destination ./backup --dry-run
 */

namespace fs = std::filesystem;

// -----------------------------------------------------------------------------
// Logging
// -----------------------------------------------------------------------------

enum class LogLevel {
    INFO,
    WARNING,
    ERROR
};

class Logger {
public:
    void log(LogLevel level, const std::string& message) const {
        std::string label;

        switch (level) {
            case LogLevel::INFO:
                label = "INFO";
                break;
            case LogLevel::WARNING:
                label = "WARN";
                break;
            case LogLevel::ERROR:
                label = "ERROR";
                break;
        }

        std::cerr << "[" << label << "] " << message << '\n';
    }

    void info(const std::string& message) const {
        log(LogLevel::INFO, message);
    }

    void warning(const std::string& message) const {
        log(LogLevel::WARNING, message);
    }

    void error(const std::string& message) const {
        log(LogLevel::ERROR, message);
    }
};

// -----------------------------------------------------------------------------
// Configuration
// -----------------------------------------------------------------------------

struct Configuration {
    fs::path sourceDirectory;
    fs::path destinationDirectory;
    bool dryRun = false;
    unsigned int maxRetries = 3;
};

struct BackupResult {
    std::size_t copiedFiles = 0;
    std::size_t skippedFiles = 0;
    std::size_t failedFiles = 0;
    std::uintmax_t bytesProcessed = 0;
};

// -----------------------------------------------------------------------------
// Argument parsing
// -----------------------------------------------------------------------------

class ArgumentParser {
public:
    static Configuration parse(int argc, char* argv[]) {
        Configuration configuration;

        for (int index = 1; index < argc; ++index) {
            const std::string argument = argv[index];

            if (argument == "--source") {
                configuration.sourceDirectory =
                    requireValue(argc, argv, index, "--source");
            } else if (argument == "--destination") {
                configuration.destinationDirectory =
                    requireValue(argc, argv, index, "--destination");
            } else if (argument == "--dry-run") {
                configuration.dryRun = true;
            } else if (argument == "--retries") {
                const std::string value =
                    requireValue(argc, argv, index, "--retries");

                try {
                    const unsigned long parsed =
                        std::stoul(value);

                    if (parsed == 0 || parsed > 100) {
                        throw std::out_of_range("retry count");
                    }

                    configuration.maxRetries =
                        static_cast<unsigned int>(parsed);
                } catch (const std::exception&) {
                    throw std::invalid_argument(
                        "Invalid value for --retries: " + value
                    );
                }
            } else if (argument == "--help") {
                printHelp();
                std::exit(0);
            } else {
                throw std::invalid_argument(
                    "Unknown argument: " + argument
                );
            }
        }

        return configuration;
    }

private:
    static std::string requireValue(
        int argc,
        char* argv[],
        int& index,
        const std::string& option
    ) {
        if (index + 1 >= argc) {
            throw std::invalid_argument(
                "Missing value for " + option
            );
        }

        ++index;
        return argv[index];
    }

    static void printHelp() {
        std::cout
            << "Bash-style automation case study\n\n"
            << "Options:\n"
            << "  --source <directory>       Source directory\n"
            << "  --destination <directory> Backup destination\n"
            << "  --dry-run                 Do not write files\n"
            << "  --retries <number>        Maximum retries\n"
            << "  --help                    Show this help\n";
    }
};

// -----------------------------------------------------------------------------
// Validation
// -----------------------------------------------------------------------------

class Validator {
public:
    static void validateConfiguration(const Configuration& configuration) {
        if (configuration.maxRetries == 0) {
            throw std::invalid_argument(
                "Retry count must be greater than zero."
            );
        }

        if (configuration.sourceDirectory.empty()) {
            throw std::invalid_argument(
                "A source directory is required."
            );
        }

        if (configuration.destinationDirectory.empty()) {
            throw std::invalid_argument(
                "A destination directory is required."
            );
        }

        if (!fs::exists(configuration.sourceDirectory)) {
            throw std::runtime_error(
                "Source directory does not exist: " +
                configuration.sourceDirectory.string()
            );
        }

        if (!fs::is_directory(configuration.sourceDirectory)) {
            throw std::runtime_error(
                "Source path is not a directory: " +
                configuration.sourceDirectory.string()
            );
        }

        if (configuration.sourceDirectory ==
            configuration.destinationDirectory) {
            throw std::invalid_argument(
                "Source and destination must be different."
            );
        }
    }

    static bool isSafeSimpleFilename(const std::string& filename) {
        if (filename.empty() || filename == "." || filename == "..") {
            return false;
        }

        if (filename.find('/') != std::string::npos ||
            filename.find('\\') != std::string::npos) {
            return false;
        }

        return true;
    }
};

// -----------------------------------------------------------------------------
// Generic retry utility
// -----------------------------------------------------------------------------

template <typename Operation>
bool retryOperation(
    Operation operation,
    unsigned int maximumAttempts,
    const Logger& logger
) {
    for (unsigned int attempt = 1;
         attempt <= maximumAttempts;
         ++attempt) {

        try {
            if (operation()) {
                return true;
            }

            logger.warning(
                "Operation returned failure on attempt " +
                std::to_string(attempt)
            );
        } catch (const std::exception& error) {
            logger.warning(
                "Operation failed on attempt " +
                std::to_string(attempt) +
                ": " + error.what()
            );
        }

        if (attempt < maximumAttempts) {
            // A real production system might use exponential backoff:
            // delay = base * 2^(attempt-1), optionally with jitter.
            std::this_thread::sleep_for(
                std::chrono::milliseconds(25)
            );
        }
    }

    return false;
}

// -----------------------------------------------------------------------------
// File discovery
// -----------------------------------------------------------------------------

class FileDiscoverer {
public:
    explicit FileDiscoverer(const Logger& logger)
        : logger_(logger) {}

    std::vector<fs::path> discover(
        const fs::path& source
    ) const {
        std::vector<fs::path> files;

        std::error_code error;

        fs::recursive_directory_iterator iterator(
            source,
            fs::directory_options::skip_permission_denied,
            error
        );

        const fs::recursive_directory_iterator end;

        while (iterator != end) {
            if (error) {
                logger_.warning(
                    "Directory traversal error: " +
                    error.message()
                );
                error.clear();
                iterator.increment(error);
                continue;
            }

            if (iterator->is_regular_file(error)) {
                files.push_back(iterator->path());
            }

            iterator.increment(error);
        }

        std::sort(files.begin(), files.end());

        return files;
    }

private:
    const Logger& logger_;
};

// -----------------------------------------------------------------------------
// Backup engine
// -----------------------------------------------------------------------------

class BackupEngine {
public:
    BackupEngine(
        Configuration configuration,
        Logger logger
    )
        : configuration_(std::move(configuration)),
          logger_(std::move(logger)),
          discoverer_(logger_) {}

    BackupResult execute() {
        Validator::validateConfiguration(configuration_);

        const std::vector<fs::path> files =
            discoverer_.discover(
                configuration_.sourceDirectory
            );

        logger_.info(
            "Discovered " +
            std::to_string(files.size()) +
            " regular file(s)."
        );

        BackupResult result;

        for (const fs::path& source : files) {
            const fs::path destination =
                destinationFor(source);

            processFile(source, destination, result);
        }

        return result;
    }

private:
    fs::path destinationFor(
        const fs::path& source
    ) const {
        const fs::path relative =
            fs::relative(
                source,
                configuration_.sourceDirectory
            );

        return configuration_.destinationDirectory /
               relative;
    }

    void processFile(
        const fs::path& source,
        const fs::path& destination,
        BackupResult& result
    ) {
        std::error_code sourceError;

        const std::uintmax_t sourceSize =
            fs::file_size(source, sourceError);

        if (sourceError) {
            logger_.error(
                "Cannot inspect " +
                source.string() +
                ": " +
                sourceError.message()
            );

            ++result.failedFiles;
            return;
        }

        // Idempotency:
        // If an existing destination has the same size, this educational
        // implementation considers it synchronized. A production backup
        // system would normally use stronger comparison rules.
        if (fs::exists(destination)) {
            std::error_code destinationError;

            const std::uintmax_t destinationSize =
                fs::file_size(destination, destinationError);

            if (!destinationError &&
                destinationSize == sourceSize) {

                logger_.info(
                    "Skipping already synchronized file: " +
                    source.string()
                );

                ++result.skippedFiles;
                return;
            }
        }

        if (configuration_.dryRun) {
            logger_.info(
                "[DRY-RUN] COPY " +
                source.string() +
                " -> " +
                destination.string()
            );

            ++result.copiedFiles;
            result.bytesProcessed += sourceSize;
            return;
        }

        const bool success = retryOperation(
            [&]() {
                std::error_code directoryError;

                fs::create_directories(
                    destination.parent_path(),
                    directoryError
                );

                if (directoryError) {
                    throw std::runtime_error(
                        "Cannot create destination directory: " +
                        directoryError.message()
                    );
                }

                std::error_code copyError;

                fs::copy_file(
                    source,
                    destination,
                    fs::copy_options::overwrite_existing,
                    copyError
                );

                if (copyError) {
                    throw std::runtime_error(
                        "Copy failed: " +
                        copyError.message()
                    );
                }

                return true;
            },
            configuration_.maxRetries,
            logger_
        );

        if (success) {
            ++result.copiedFiles;
            result.bytesProcessed += sourceSize;

            logger_.info(
                "Copied: " + source.string()
            );
        } else {
            ++result.failedFiles;

            logger_.error(
                "Unable to copy: " +
                source.string()
            );
        }
    }

    Configuration configuration_;
    Logger logger_;
    FileDiscoverer discoverer_;
};

// -----------------------------------------------------------------------------
// Service health model
// -----------------------------------------------------------------------------

struct Service {
    std::string name;
    std::uint16_t port;
    bool enabled;
};

class HealthChecker {
public:
    explicit HealthChecker(Logger logger)
        : logger_(std::move(logger)) {}

    bool check(const Service& service) const {
        if (!service.enabled) {
            logger_.warning(
                service.name +
                " is disabled."
            );
            return false;
        }

        if (service.port == 0) {
            logger_.error(
                service.name +
                " has an invalid port."
            );
            return false;
        }

        logger_.info(
            "Validated service " +
            service.name +
            " on port " +
            std::to_string(service.port)
        );

        return true;
    }

private:
    Logger logger_;
};

// -----------------------------------------------------------------------------
// Demonstration of Bash-like conditions, loops, arrays and mappings
// -----------------------------------------------------------------------------

void demonstrateLanguageConcepts() {
    std::cout << "\n";
    std::cout << "Language concept demonstration\n";
    std::cout << "==============================\n";

    // C++ variables correspond to the broader programming concept of storing
    // state. Bash variables do this with syntax such as name="value".
    std::string applicationName = "automation-lab";
    int retryCount = 3;
    bool dryRun = true;

    std::cout << "Application: " << applicationName << '\n';
    std::cout << "Retries:     " << retryCount << '\n';
    std::cout << "Dry run:     " << std::boolalpha << dryRun << '\n';

    // A vector is similar in purpose to a Bash indexed array.
    std::vector<std::string> services = {
        "api",
        "database",
        "worker",
        "frontend"
    };

    std::cout << "\nServices:\n";

    for (std::size_t index = 0;
         index < services.size();
         ++index) {
        std::cout
            << "  [" << index << "] "
            << services[index] << '\n';
    }

    // A map is similar in purpose to a Bash associative array.
    std::map<std::string, int> ports = {
        {"api", 8080},
        {"database", 5432},
        {"worker", 9000}
    };

    std::cout << "\nService ports:\n";

    for (const auto& [service, port] : ports) {
        std::cout
            << "  "
            << service
            << " -> "
            << port
            << '\n';
    }

    std::cout << "\nCondition example:\n";

    if (retryCount > 0 && dryRun) {
        std::cout
            << "Automation can run safely in dry-run mode.\n";
    } else {
        std::cout
            << "Automation configuration requires review.\n";
    }

    std::cout << "\nWhile-loop example:\n";

    int remaining = 3;

    while (remaining > 0) {
        std::cout
            << "Remaining: "
            << remaining
            << '\n';

        --remaining;
    }
}

// -----------------------------------------------------------------------------
// Main
// -----------------------------------------------------------------------------

int main(int argc, char* argv[]) {
    Logger logger;

    try {
        std::cout
            << "Bash Shell Scripting Automation Case Study\n"
            << "===========================================\n";

        demonstrateLanguageConcepts();

        Configuration configuration =
            ArgumentParser::parse(argc, argv);

        logger.info("Validating configuration.");

        Validator::validateConfiguration(configuration);

        logger.info(
            std::string("Dry-run mode: ") +
            (configuration.dryRun ? "enabled" : "disabled")
        );

        // The health-check model demonstrates conditions, structured records,
        // loops, and validation in a system-oriented scenario.
        HealthChecker healthChecker(logger);

        std::vector<Service> services = {
            {"api", 8080, true},
            {"database", 5432, true},
            {"worker", 9000, false},
            {"invalid-service", 0, true}
        };

        std::size_t healthyConfigurationCount = 0;

        for (const Service& service : services) {
            if (healthChecker.check(service)) {
                ++healthyConfigurationCount;
            }
        }

        logger.info(
            "Valid service configurations: " +
            std::to_string(healthyConfigurationCount)
        );

        BackupEngine engine(
            configuration,
            logger
        );

        const BackupResult result =
            engine.execute();

        std::cout << "\nBackup result\n";
        std::cout << "-------------\n";
        std::cout
            << "Copied files:   "
            << result.copiedFiles
            << '\n';

        std::cout
            << "Skipped files:  "
            << result.skippedFiles
            << '\n';

        std::cout
            << "Failed files:   "
            << result.failedFiles
            << '\n';

        std::cout
            << "Bytes processed:"
            << std::setw(10)
            << result.bytesProcessed
            << '\n';

        /*
         * Exit-status mapping:
         *
         * Bash convention:
         *     0 = success
         *     nonzero = failure
         *
         * Returning a nonzero value allows a scheduler, CI system, or another
         * script to detect that automation failed.
         */
        if (result.failedFiles > 0) {
            logger.error(
                "Automation completed with failures."
            );
            return 2;
        }

        logger.info(
            "Automation completed successfully."
        );

        return 0;
    } catch (const std::invalid_argument& error) {
        logger.error(
            std::string("Invalid input: ") +
            error.what()
        );

        return 64;
    } catch (const std::exception& error) {
        logger.error(
            std::string("Automation failure: ") +
            error.what()
        );

        return 1;
    }
}
