#include <algorithm>
#include <cctype>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Docker Images and Dockerfiles
 *
 * C++17 implementation of a Dockerfile analysis and image
 * construction planning engine.
 *
 * Features:
 * - Dockerfile parsing
 * - Instruction classification
 * - Image-stage modeling
 * - Layer dependency tracking
 * - Content-addressed cache simulation
 * - Security policy evaluation
 * - Optimization recommendations
 * - Build metrics and reporting
 *
 * No external libraries.
 */

enum class InstructionType {
    FROM,
    RUN,
    COPY,
    ADD,
    WORKDIR,
    ENV,
    ARG,
    EXPOSE,
    USER,
    CMD,
    ENTRYPOINT,
    LABEL,
    HEALTHCHECK,
    VOLUME,
    SHELL,
    UNKNOWN
};

enum class Severity {
    INFO,
    WARNING,
    ERROR
};

enum class BuildStatus {
    PLANNED,
    BUILT,
    CACHED,
    FAILED
};

std::string toUpper(std::string value) {
    std::transform(
        value.begin(),
        value.end(),
        value.begin(),
        [](unsigned char c) {
            return static_cast<char>(std::toupper(c));
        }
    );

    return value;
}

std::string trim(const std::string& value) {
    const auto first = value.find_first_not_of(" \t\r\n");

    if (first == std::string::npos) {
        return "";
    }

    const auto last = value.find_last_not_of(" \t\r\n");

    return value.substr(first, last - first + 1);
}

InstructionType classify(const std::string& command) {
    static const std::map<std::string, InstructionType> mapping = {
        {"FROM", InstructionType::FROM},
        {"RUN", InstructionType::RUN},
        {"COPY", InstructionType::COPY},
        {"ADD", InstructionType::ADD},
        {"WORKDIR", InstructionType::WORKDIR},
        {"ENV", InstructionType::ENV},
        {"ARG", InstructionType::ARG},
        {"EXPOSE", InstructionType::EXPOSE},
        {"USER", InstructionType::USER},
        {"CMD", InstructionType::CMD},
        {"ENTRYPOINT", InstructionType::ENTRYPOINT},
        {"LABEL", InstructionType::LABEL},
        {"HEALTHCHECK", InstructionType::HEALTHCHECK},
        {"VOLUME", InstructionType::VOLUME},
        {"SHELL", InstructionType::SHELL}
    };

    auto it = mapping.find(command);

    return it == mapping.end()
        ? InstructionType::UNKNOWN
        : it->second;
}

std::string toString(InstructionType type) {
    static const std::map<InstructionType, std::string> names = {
        {InstructionType::FROM, "FROM"},
        {InstructionType::RUN, "RUN"},
        {InstructionType::COPY, "COPY"},
        {InstructionType::ADD, "ADD"},
        {InstructionType::WORKDIR, "WORKDIR"},
        {InstructionType::ENV, "ENV"},
        {InstructionType::ARG, "ARG"},
        {InstructionType::EXPOSE, "EXPOSE"},
        {InstructionType::USER, "USER"},
        {InstructionType::CMD, "CMD"},
        {InstructionType::ENTRYPOINT, "ENTRYPOINT"},
        {InstructionType::LABEL, "LABEL"},
        {InstructionType::HEALTHCHECK, "HEALTHCHECK"},
        {InstructionType::VOLUME, "VOLUME"},
        {InstructionType::SHELL, "SHELL"},
        {InstructionType::UNKNOWN, "UNKNOWN"}
    };

    return names.at(type);
}

std::string toString(Severity severity) {
    switch (severity) {
        case Severity::INFO:
            return "INFO";
        case Severity::WARNING:
            return "WARNING";
        case Severity::ERROR:
            return "ERROR";
    }

    return "UNKNOWN";
}

struct Instruction {
    int line;
    InstructionType type;
    std::string arguments;
};

struct Finding {
    Severity severity;
    std::string code;
    std::string message;
    int line = 0;
};

struct ImageLayer {
    int index;
    int stage;
    Instruction instruction;
    std::string cacheKey;
    double estimatedSizeMB;
    BuildStatus status;
};

struct BuildMetrics {
    double estimatedSizeMB = 0.0;
    std::size_t cacheHits = 0;
    std::size_t cacheMisses = 0;
    std::size_t layerCount = 0;
};

struct BuildReport {
    std::string imageName;
    std::vector<ImageLayer> layers;
    std::vector<Finding> findings;
    std::vector<std::string> recommendations;
    BuildMetrics metrics;
};

class DockerfileParser {
public:
    std::vector<Instruction> parse(
        const std::string& source
    ) const {
        if (trim(source).empty()) {
            throw std::invalid_argument(
                "Dockerfile content cannot be empty."
            );
        }

        std::vector<std::string> logicalLines;
        std::stringstream stream(source);

        std::string line;
        std::string buffer;

        while (std::getline(stream, line)) {
            line = trim(line);

            if (line.empty() || line[0] == '#') {
                continue;
            }

            if (!line.empty() && line.back() == '\\') {
                line.pop_back();
                buffer += line + " ";
                continue;
            }

            buffer += line;
            logicalLines.push_back(trim(buffer));
            buffer.clear();
        }

        if (!trim(buffer).empty()) {
            throw std::invalid_argument(
                "Incomplete line continuation."
            );
        }

        std::vector<Instruction> instructions;

        for (std::size_t i = 0; i < logicalLines.size(); ++i) {
            const std::string& current = logicalLines[i];

            std::istringstream parser(current);

            std::string command;
            parser >> command;

            std::string arguments;
            std::getline(parser, arguments);

            command = toUpper(command);
            arguments = trim(arguments);

            const auto type = classify(command);

            if (type == InstructionType::UNKNOWN) {
                throw std::invalid_argument(
                    "Unsupported instruction: " + command
                );
            }

            if (arguments.empty()) {
                throw std::invalid_argument(
                    "Missing arguments for " + command
                );
            }

            instructions.push_back({
                static_cast<int>(i + 1),
                type,
                arguments
            });
        }

        if (instructions.empty() ||
            instructions.front().type != InstructionType::FROM) {
            throw std::invalid_argument(
                "The first instruction must be FROM."
            );
        }

        return instructions;
    }
};

class SecurityAnalyzer {
private:
    static bool contains(
        const std::string& value,
        const std::string& pattern
    ) {
        return std::regex_search(
            value,
            std::regex(pattern, std::regex::icase)
        );
    }

public:
    std::vector<Finding> analyze(
        const std::vector<Instruction>& instructions
    ) const {
        std::vector<Finding> findings;

        bool hasUser = false;
        bool hasStart = false;

        for (const auto& instruction : instructions) {
            const std::string& args = instruction.arguments;

            if (instruction.type == InstructionType::FROM &&
                contains(args, ":latest(?:\\s|$)")) {
                findings.push_back({
                    Severity::WARNING,
                    "MUTABLE_BASE_IMAGE",
                    "Avoid mutable latest image tags.",
                    instruction.line
                });
            }

            if (instruction.type == InstructionType::ENV &&
                contains(
                    args,
                    "(PASSWORD|SECRET|TOKEN|API_KEY)"
                )) {
                findings.push_back({
                    Severity::ERROR,
                    "SECRET_IN_ENV",
                    "Credentials must not be embedded in ENV instructions.",
                    instruction.line
                });
            }

            if (instruction.type == InstructionType::ADD) {
                findings.push_back({
                    Severity::INFO,
                    "ADD_REVIEW",
                    "Use COPY unless ADD-specific behavior is needed.",
                    instruction.line
                });
            }

            if (instruction.type == InstructionType::RUN &&
                contains(
                    args,
                    "(curl|wget).*\\|\\s*(sh|bash)"
                )) {
                findings.push_back({
                    Severity::WARNING,
                    "UNVERIFIED_SCRIPT",
                    "Verify downloaded scripts before executing them.",
                    instruction.line
                });
            }

            if (instruction.type == InstructionType::RUN &&
                contains(args, "apt-get update") &&
                !contains(args, "rm -rf /var/lib/apt/lists")) {
                findings.push_back({
                    Severity::WARNING,
                    "PACKAGE_CACHE",
                    "Clean package-manager metadata.",
                    instruction.line
                });
            }

            if (instruction.type == InstructionType::USER) {
                hasUser = true;

                if (args == "root" || args == "0") {
                    findings.push_back({
                        Severity::ERROR,
                        "ROOT_RUNTIME",
                        "The runtime should not execute as root.",
                        instruction.line
                    });
                }
            }

            if (instruction.type == InstructionType::CMD ||
                instruction.type == InstructionType::ENTRYPOINT) {
                hasStart = true;
            }
        }

        if (!hasUser) {
            findings.push_back({
                Severity::WARNING,
                "MISSING_USER",
                "Define a non-root runtime user.",
                0
            });
        }

        if (!hasStart) {
            findings.push_back({
                Severity::WARNING,
                "MISSING_START_COMMAND",
                "Define CMD or ENTRYPOINT.",
                0
            });
        }

        return findings;
    }
};

class ImageCache {
private:
    std::unordered_map<std::string, double> entries;

public:
    std::optional<double> find(
        const std::string& key
    ) const {
        auto it = entries.find(key);

        if (it == entries.end()) {
            return std::nullopt;
        }

        return it->second;
    }

    void insert(
        const std::string& key,
        double size
    ) {
        entries.emplace(key, size);
    }

    std::size_t size() const {
        return entries.size();
    }
};

class OptimizationAnalyzer {
public:
    std::vector<std::string> analyze(
        const std::vector<Instruction>& instructions
    ) const {
        std::vector<std::string> recommendations;

        int runCount = 0;
        int fromCount = 0;

        bool packageUpdate = false;
        bool packageCleanup = false;
        bool copyExists = false;
        bool runExists = false;

        for (const auto& instruction : instructions) {
            if (instruction.type == InstructionType::RUN) {
                ++runCount;
                runExists = true;

                if (instruction.arguments.find(
                    "apt-get update"
                ) != std::string::npos) {
                    packageUpdate = true;
                }

                if (instruction.arguments.find(
                    "rm -rf /var/lib/apt/lists"
                ) != std::string::npos) {
                    packageCleanup = true;
                }
            }

            if (instruction.type == InstructionType::FROM) {
                ++fromCount;
            }

            if (instruction.type == InstructionType::COPY) {
                copyExists = true;
            }
        }

        if (runCount > 5) {
            recommendations.push_back(
                "Combine related RUN operations where practical."
            );
        }

        if (packageUpdate && !packageCleanup) {
            recommendations.push_back(
                "Remove package indexes after installation."
            );
        }

        if (fromCount == 1) {
            recommendations.push_back(
                "Evaluate a multi-stage build."
            );
        }

        if (copyExists && runExists) {
            recommendations.push_back(
                "Copy dependency manifests before frequently changing source files."
            );
        }

        recommendations.push_back(
            "Use .dockerignore to reduce build-context transfer."
        );

        recommendations.push_back(
            "Pin base images to controlled versions or verified digests."
        );

        return recommendations;
    }
};

class DockerBuildEngine {
private:
    ImageCache cache;

    static double estimateSize(
        InstructionType type
    ) {
        switch (type) {
            case InstructionType::FROM:
                return 120.0;
            case InstructionType::RUN:
                return 15.0;
            case InstructionType::COPY:
                return 10.0;
            case InstructionType::ADD:
                return 10.0;
            default:
                return 0.0;
        }
    }

    static std::string hash(
        const std::string& value
    ) {
        // FNV-1a provides a compact deterministic educational cache key.
        // Production content-addressed systems should use a cryptographic hash.
        std::uint64_t result = 14695981039346656037ULL;

        for (unsigned char c : value) {
            result ^= c;
            result *= 1099511628211ULL;
        }

        std::ostringstream output;

        output << std::hex << result;

        return output.str();
    }

public:
    BuildReport build(
        const std::vector<Instruction>& instructions,
        const std::string& imageName
    ) {
        if (imageName.empty()) {
            throw std::invalid_argument(
                "Image name cannot be empty."
            );
        }

        BuildReport report;
        report.imageName = imageName;

        std::string parentKey = "empty-base";
        int layerIndex = 0;
        int stage = -1;

        for (const auto& instruction : instructions) {
            if (instruction.type == InstructionType::FROM) {
                ++stage;
            }

            const bool createsLayer =
                instruction.type == InstructionType::FROM ||
                instruction.type == InstructionType::RUN ||
                instruction.type == InstructionType::COPY ||
                instruction.type == InstructionType::ADD;

            if (!createsLayer) {
                continue;
            }

            ++layerIndex;

            const std::string material =
                parentKey + "|" +
                toString(instruction.type) + "|" +
                instruction.arguments;

            const std::string key = hash(material);

            const bool cacheable =
                instruction.arguments.find("--no-cache") ==
                std::string::npos;

            double size = estimateSize(instruction.type);
            BuildStatus status = BuildStatus::BUILT;

            auto cached = cache.find(key);

            if (cacheable && cached.has_value()) {
                size = cached.value();
                status = BuildStatus::CACHED;
                ++report.metrics.cacheHits;
            } else {
                ++report.metrics.cacheMisses;

                if (cacheable) {
                    cache.insert(key, size);
                }
            }

            report.layers.push_back({
                layerIndex,
                stage,
                instruction,
                key,
                size,
                status
            });

            report.metrics.estimatedSizeMB += size;
            parentKey = key;
        }

        report.metrics.layerCount = report.layers.size();

        report.findings =
            SecurityAnalyzer().analyze(instructions);

        report.recommendations =
            OptimizationAnalyzer().analyze(instructions);

        return report;
    }

    std::size_t cacheSize() const {
        return cache.size();
    }
};

class DockerImageRegistry {
private:
    std::map<std::string, BuildReport> images;

public:
    void publish(BuildReport report) {
        if (report.imageName.empty()) {
            throw std::invalid_argument(
                "An image must have a valid name."
            );
        }

        if (images.find(report.imageName) != images.end()) {
            throw std::runtime_error(
                "Image tag already exists in this registry model."
            );
        }

        const bool securityErrors = std::any_of(
            report.findings.begin(),
            report.findings.end(),
            [](const Finding& finding) {
                return finding.severity == Severity::ERROR;
            }
        );

        if (securityErrors) {
            throw std::runtime_error(
                "Publication rejected because security errors exist."
            );
        }

        images.emplace(
            report.imageName,
            std::move(report)
        );
    }

    const BuildReport& get(
        const std::string& imageName
    ) const {
        auto it = images.find(imageName);

        if (it == images.end()) {
            throw std::out_of_range(
                "Image not found."
            );
        }

        return it->second;
    }

    std::size_t count() const {
        return images.size();
    }
};

void printReport(const BuildReport& report) {
    std::cout << "\nIMAGE BUILD REPORT\n";
    std::cout << "==============================\n";

    std::cout << "Image: "
              << report.imageName << "\n";

    std::cout << "Layers: "
              << report.metrics.layerCount << "\n";

    std::cout << "Estimated size: "
              << report.metrics.estimatedSizeMB
              << " MB\n";

    std::cout << "Cache hits: "
              << report.metrics.cacheHits << "\n";

    std::cout << "Cache misses: "
              << report.metrics.cacheMisses << "\n";

    std::cout << "\nLAYER DETAILS\n";

    for (const auto& layer : report.layers) {
        std::cout
            << "Layer " << layer.index
            << " | Stage " << layer.stage
            << " | " << toString(layer.instruction.type)
            << " | " << layer.estimatedSizeMB << " MB"
            << " | "
            << (
                layer.status == BuildStatus::CACHED
                ? "CACHED"
                : "BUILT"
            )
            << "\n";
    }

    std::cout << "\nSECURITY FINDINGS\n";

    for (const auto& finding : report.findings) {
        std::cout
            << "[" << toString(finding.severity) << "] "
            << finding.code << ": "
            << finding.message << "\n";
    }

    std::cout << "\nOPTIMIZATION RECOMMENDATIONS\n";

    for (const auto& recommendation :
         report.recommendations) {
        std::cout << "- " << recommendation << "\n";
    }
}

const std::string SAMPLE_DOCKERFILE = R"(
FROM golang:1.23-alpine AS builder

WORKDIR /src

COPY go.mod go.sum ./

RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -o /app/server ./cmd/server

FROM alpine:3.21

RUN addgroup -S app && adduser -S app -G app

COPY --from=builder /app/server /usr/local/bin/server

USER app

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/server"]
)";

int main() {
    try {
        std::cout << std::fixed << std::setprecision(2);

        std::cout
            << "DOCKER IMAGE AND DOCKERFILE ENGINE\n"
            << "==================================\n";

        DockerfileParser parser;

        const auto instructions = parser.parse(
            SAMPLE_DOCKERFILE
        );

        std::cout << "\nPARSED INSTRUCTIONS\n";

        for (const auto& instruction : instructions) {
            std::cout
                << std::setw(2) << instruction.line
                << " | "
                << std::setw(12)
                << toString(instruction.type)
                << " | "
                << instruction.arguments
                << "\n";
        }

        DockerBuildEngine engine;

        BuildReport first = engine.build(
            instructions,
            "inventory-service:1.0"
        );

        printReport(first);

        std::cout << "\nREPEATED BUILD\n";

        BuildReport second = engine.build(
            instructions,
            "inventory-service:1.1"
        );

        std::cout
            << "Cache hits: "
            << second.metrics.cacheHits
            << "\n";

        std::cout
            << "Cache misses: "
            << second.metrics.cacheMisses
            << "\n";

        std::cout << "\nREGISTRY PUBLICATION\n";

        DockerImageRegistry registry;

        registry.publish(first);

        std::cout
            << "Published images: "
            << registry.count()
            << "\n";

        std::cout
            << "Registered image: "
            << registry.get(
                "inventory-service:1.0"
            ).imageName
            << "\n";

        std::cout << "\nSECURITY REJECTION TEST\n";

        const std::string unsafeDockerfile = R"(
FROM node:latest
ENV API_KEY=supersecret
USER root
CMD ["node", "app.js"]
)";

        const auto unsafeInstructions = parser.parse(
            unsafeDockerfile
        );

        BuildReport unsafe = engine.build(
            unsafeInstructions,
            "unsafe-service:1.0"
        );

        try {
            registry.publish(unsafe);
        } catch (const std::runtime_error& error) {
            std::cout
                << "Publication rejected: "
                << error.what()
                << "\n";
        }

        std::cout << "\nCACHE CAPACITY\n";

        std::cout
            << "Cached entries: "
            << engine.cacheSize()
            << "\n";

        std::cout
            << "\nAnalysis completed successfully.\n";

    } catch (const std::exception& error) {
        std::cerr
            << "ERROR: "
            << error.what()
            << "\n";

        return 1;
    }

    return 0;
}
