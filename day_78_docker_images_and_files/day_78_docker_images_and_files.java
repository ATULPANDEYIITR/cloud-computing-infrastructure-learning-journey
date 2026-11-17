import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/*
 * Docker Images and Dockerfiles
 *
 * Enterprise-oriented Docker build governance system.
 *
 * Java 17
 * No third-party dependencies.
 *
 * Features:
 * - Immutable domain records
 * - Dockerfile instruction validation
 * - Multi-stage image modeling
 * - Layer dependency calculation
 * - SHA-256 build-cache keys
 * - Security policies
 * - Build lifecycle management
 * - Registry publication controls
 * - Image optimization analysis
 */

public class DockerEnterprise {

    enum InstructionType {
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
        SHELL
    }

    enum FindingSeverity {
        INFO,
        WARNING,
        ERROR
    }

    enum BuildState {
        CREATED,
        VALIDATED,
        BUILDING,
        BUILT,
        FAILED,
        PUBLISHED
    }

    enum LayerStatus {
        BUILT,
        CACHED
    }

    record Instruction(
        int line,
        InstructionType type,
        String arguments
    ) {
        Instruction {
            Objects.requireNonNull(type);
            Objects.requireNonNull(arguments);

            if (arguments.isBlank()) {
                throw new IllegalArgumentException(
                    "Instruction arguments cannot be empty."
                );
            }
        }
    }

    record Finding(
        FindingSeverity severity,
        String code,
        String message,
        int line
    ) {}

    record ImageLayer(
        int index,
        int stage,
        Instruction instruction,
        String cacheKey,
        long estimatedSizeBytes,
        LayerStatus status
    ) {}

    record BuildMetrics(
        int layerCount,
        long totalSizeBytes,
        int cacheHits,
        int cacheMisses
    ) {}

    record BuildReport(
        String imageName,
        String dockerfileHash,
        List<ImageLayer> layers,
        List<Finding> findings,
        List<String> recommendations,
        BuildMetrics metrics
    ) {
        BuildReport {
            layers = List.copyOf(layers);
            findings = List.copyOf(findings);
            recommendations = List.copyOf(recommendations);

            if (imageName == null || imageName.isBlank()) {
                throw new IllegalArgumentException(
                    "Image name is required."
                );
            }
        }

        boolean hasErrors() {
            return findings.stream().anyMatch(
                finding ->
                    finding.severity() == FindingSeverity.ERROR
            );
        }
    }

    record BuildRequest(
        String imageName,
        String dockerfileContent,
        boolean allowWarnings
    ) {
        BuildRequest {
            if (imageName == null || imageName.isBlank()) {
                throw new IllegalArgumentException(
                    "Image name cannot be empty."
                );
            }

            if (dockerfileContent == null ||
                dockerfileContent.isBlank()) {
                throw new IllegalArgumentException(
                    "Dockerfile content cannot be empty."
                );
            }
        }
    }

    static class DockerException extends RuntimeException {
        DockerException(String message) {
            super(message);
        }
    }

    static class PolicyViolationException
        extends DockerException {

        PolicyViolationException(String message) {
            super(message);
        }
    }

    static class DockerfileParser {

        private static final Map<String, InstructionType> TYPES =
            new HashMap<>();

        static {
            for (InstructionType type : InstructionType.values()) {
                TYPES.put(type.name(), type);
            }
        }

        List<Instruction> parse(String source) {
            Objects.requireNonNull(source);

            List<String> logicalLines = new ArrayList<>();
            StringBuilder buffer = new StringBuilder();

            for (String raw : source.split("\\R")) {
                String line = raw.trim();

                if (line.isEmpty() || line.startsWith("#")) {
                    continue;
                }

                if (line.endsWith("\\")) {
                    buffer.append(
                        line.substring(0, line.length() - 1)
                    ).append(" ");

                    continue;
                }

                buffer.append(line);

                logicalLines.add(buffer.toString().trim());

                buffer.setLength(0);
            }

            if (!buffer.isEmpty()) {
                throw new DockerException(
                    "Incomplete Dockerfile continuation."
                );
            }

            List<Instruction> instructions = new ArrayList<>();

            for (int i = 0; i < logicalLines.size(); i++) {
                String line = logicalLines.get(i);

                String[] parts = line.split("\\s+", 2);

                if (parts.length != 2) {
                    throw new DockerException(
                        "Invalid instruction at line " + (i + 1)
                    );
                }

                String command = parts[0].toUpperCase();

                InstructionType type = TYPES.get(command);

                if (type == null) {
                    throw new DockerException(
                        "Unsupported instruction: " + command
                    );
                }

                instructions.add(
                    new Instruction(
                        i + 1,
                        type,
                        parts[1].trim()
                    )
                );
            }

            if (instructions.isEmpty() ||
                instructions.get(0).type() != InstructionType.FROM) {
                throw new DockerException(
                    "The first instruction must be FROM."
                );
            }

            return List.copyOf(instructions);
        }
    }

    static class SecurityPolicy {

        private final boolean requireNonRoot;
        private final boolean requireStartCommand;
        private final boolean rejectSecrets;

        SecurityPolicy(
            boolean requireNonRoot,
            boolean requireStartCommand,
            boolean rejectSecrets
        ) {
            this.requireNonRoot = requireNonRoot;
            this.requireStartCommand = requireStartCommand;
            this.rejectSecrets = rejectSecrets;
        }

        List<Finding> evaluate(
            List<Instruction> instructions
        ) {
            List<Finding> findings = new ArrayList<>();

            boolean hasUser = false;
            boolean hasStart = false;

            for (Instruction instruction : instructions) {
                String args = instruction.arguments();

                if (
                    instruction.type() == InstructionType.FROM &&
                    Pattern.compile(
                        ":latest(?:\\s|$)",
                        Pattern.CASE_INSENSITIVE
                    ).matcher(args).find()
                ) {
                    findings.add(new Finding(
                        FindingSeverity.WARNING,
                        "MUTABLE_BASE_IMAGE",
                        "Pin the base image to a controlled version or digest.",
                        instruction.line()
                    ));
                }

                if (
                    rejectSecrets &&
                    instruction.type() == InstructionType.ENV &&
                    Pattern.compile(
                        "(PASSWORD|SECRET|TOKEN|API_KEY)",
                        Pattern.CASE_INSENSITIVE
                    ).matcher(args).find()
                ) {
                    findings.add(new Finding(
                        FindingSeverity.ERROR,
                        "SECRET_IN_ENV",
                        "Credentials must not be embedded in ENV instructions.",
                        instruction.line()
                    ));
                }

                if (instruction.type() == InstructionType.USER) {
                    hasUser = true;

                    if (args.equalsIgnoreCase("root") ||
                        args.equals("0")) {
                        findings.add(new Finding(
                            FindingSeverity.ERROR,
                            "ROOT_RUNTIME",
                            "The runtime must not execute as root.",
                            instruction.line()
                        ));
                    }
                }

                if (
                    instruction.type() == InstructionType.CMD ||
                    instruction.type() == InstructionType.ENTRYPOINT
                ) {
                    hasStart = true;
                }

                if (instruction.type() == InstructionType.ADD) {
                    findings.add(new Finding(
                        FindingSeverity.INFO,
                        "ADD_REVIEW",
                        "Use COPY unless ADD-specific behavior is required.",
                        instruction.line()
                    ));
                }

                if (
                    instruction.type() == InstructionType.RUN &&
                    Pattern.compile(
                        "(curl|wget).*\\|\\s*(sh|bash)",
                        Pattern.CASE_INSENSITIVE
                    ).matcher(args).find()
                ) {
                    findings.add(new Finding(
                        FindingSeverity.WARNING,
                        "UNVERIFIED_REMOTE_SCRIPT",
                        "Verify downloaded scripts before execution.",
                        instruction.line()
                    ));
                }

                if (
                    instruction.type() == InstructionType.RUN &&
                    args.contains("apt-get update") &&
                    !args.contains("rm -rf /var/lib/apt/lists")
                ) {
                    findings.add(new Finding(
                        FindingSeverity.WARNING,
                        "PACKAGE_CACHE",
                        "Clean package metadata after installation.",
                        instruction.line()
                    ));
                }
            }

            if (requireNonRoot && !hasUser) {
                findings.add(new Finding(
                    FindingSeverity.ERROR,
                    "MISSING_RUNTIME_USER",
                    "An explicit non-root runtime user is required.",
                    0
                ));
            }

            if (requireStartCommand && !hasStart) {
                findings.add(new Finding(
                    FindingSeverity.ERROR,
                    "MISSING_START_COMMAND",
                    "Specify CMD or ENTRYPOINT.",
                    0
                ));
            }

            return List.copyOf(findings);
        }
    }

    static class OptimizationPolicy {

        List<String> evaluate(
            List<Instruction> instructions
        ) {
            List<String> recommendations = new ArrayList<>();

            long runCount = instructions.stream()
                .filter(i -> i.type() == InstructionType.RUN)
                .count();

            long stageCount = instructions.stream()
                .filter(i -> i.type() == InstructionType.FROM)
                .count();

            boolean hasCopy = instructions.stream()
                .anyMatch(i -> i.type() == InstructionType.COPY);

            boolean hasRun = runCount > 0;

            if (runCount > 5) {
                recommendations.add(
                    "Review related RUN instructions for safe consolidation."
                );
            }

            if (stageCount == 1) {
                recommendations.add(
                    "Consider multi-stage builds to exclude build dependencies from the runtime image."
                );
            }

            if (hasCopy && hasRun) {
                recommendations.add(
                    "Copy dependency manifests before frequently changing source files."
                );
            }

            if (instructions.stream().anyMatch(
                i -> i.type() == InstructionType.ADD
            )) {
                recommendations.add(
                    "Review ADD instructions and replace unnecessary usage with COPY."
                );
            }

            if (instructions.stream().anyMatch(
                i -> i.type() == InstructionType.RUN &&
                     i.arguments().contains("apt-get update")
            )) {
                recommendations.add(
                    "Combine package-index updates, installation, and cleanup in one RUN instruction."
                );
            }

            recommendations.add(
                "Maintain a .dockerignore file to reduce build-context size."
            );

            recommendations.add(
                "Use digest-pinned base images for reproducible builds."
            );

            return List.copyOf(recommendations);
        }
    }

    static class BuildCache {

        private final Map<String, Long> layers =
            new HashMap<>();

        synchronized Optional<Long> get(String key) {
            return Optional.ofNullable(layers.get(key));
        }

        synchronized void put(String key, long size) {
            layers.putIfAbsent(key, size);
        }

        synchronized int size() {
            return layers.size();
        }
    }

    static class LayerPlanner {

        private final BuildCache cache;

        private final Map<InstructionType, Long> sizeEstimates =
            new EnumMap<>(InstructionType.class);

        LayerPlanner(BuildCache cache) {
            this.cache = cache;

            sizeEstimates.put(InstructionType.FROM, 125_000_000L);
            sizeEstimates.put(InstructionType.RUN, 15_000_000L);
            sizeEstimates.put(InstructionType.COPY, 10_000_000L);
            sizeEstimates.put(InstructionType.ADD, 10_000_000L);
        }

        List<ImageLayer> plan(
            List<Instruction> instructions
        ) {
            List<ImageLayer> layers = new ArrayList<>();

            String parent = "empty-base";

            int stage = -1;

            for (Instruction instruction : instructions) {
                if (instruction.type() == InstructionType.FROM) {
                    stage++;
                }

                boolean createsLayer =
                    instruction.type() == InstructionType.FROM ||
                    instruction.type() == InstructionType.RUN ||
                    instruction.type() == InstructionType.COPY ||
                    instruction.type() == InstructionType.ADD;

                if (!createsLayer) {
                    continue;
                }

                String key = sha256(
                    parent + "|" +
                    instruction.type() + "|" +
                    instruction.arguments()
                );

                boolean cacheable =
                    !instruction.arguments().contains("--no-cache");

                Optional<Long> cached = cache.get(key);

                long size;
                LayerStatus status;

                if (cacheable && cached.isPresent()) {
                    size = cached.get();
                    status = LayerStatus.CACHED;
                } else {
                    size = sizeEstimates.getOrDefault(
                        instruction.type(),
                        0L
                    );

                    status = LayerStatus.BUILT;

                    if (cacheable) {
                        cache.put(key, size);
                    }
                }

                layers.add(new ImageLayer(
                    layers.size() + 1,
                    stage,
                    instruction,
                    key,
                    size,
                    status
                ));

                parent = key;
            }

            return List.copyOf(layers);
        }

        private static String sha256(String input) {
            try {
                MessageDigest digest =
                    MessageDigest.getInstance("SHA-256");

                byte[] hash = digest.digest(
                    input.getBytes(StandardCharsets.UTF_8)
                );

                StringBuilder result = new StringBuilder();

                for (byte value : hash) {
                    result.append(
                        String.format("%02x", value)
                    );
                }

                return result.toString();

            } catch (NoSuchAlgorithmException exception) {
                throw new IllegalStateException(
                    "SHA-256 is unavailable.",
                    exception
                );
            }
        }
    }

    static class BuildLifecycle {

        private final Map<String, BuildState> states =
            new LinkedHashMap<>();

        synchronized void transition(
            String image,
            BuildState next
        ) {
            BuildState current = states.get(image);

            boolean valid = switch (current == null
                ? BuildState.CREATED
                : current) {

                case CREATED ->
                    next == BuildState.VALIDATED ||
                    next == BuildState.FAILED;

                case VALIDATED ->
                    next == BuildState.BUILDING ||
                    next == BuildState.FAILED;

                case BUILDING ->
                    next == BuildState.BUILT ||
                    next == BuildState.FAILED;

                case BUILT ->
                    next == BuildState.PUBLISHED ||
                    next == BuildState.FAILED;

                case PUBLISHED, FAILED ->
                    false;
            };

            if (!valid) {
                throw new DockerException(
                    "Invalid build transition: " +
                    current + " -> " + next
                );
            }

            states.put(image, next);
        }

        synchronized BuildState get(String image) {
            return states.get(image);
        }
    }

    static class ImageRegistry {

        private final Map<String, BuildReport> images =
            new LinkedHashMap<>();

        synchronized void publish(BuildReport report) {
            if (images.containsKey(report.imageName())) {
                throw new DockerException(
                    "Image tag already exists."
                );
            }

            if (report.hasErrors()) {
                throw new PolicyViolationException(
                    "Publication blocked by security policy."
                );
            }

            images.put(report.imageName(), report);
        }

        synchronized Optional<BuildReport> find(
            String imageName
        ) {
            return Optional.ofNullable(images.get(imageName));
        }

        synchronized int size() {
            return images.size();
        }
    }

    static class BuildService {

        private final DockerfileParser parser =
            new DockerfileParser();

        private final SecurityPolicy security =
            new SecurityPolicy(true, true, true);

        private final OptimizationPolicy optimization =
            new OptimizationPolicy();

        private final BuildCache cache =
            new BuildCache();

        private final LayerPlanner planner =
            new LayerPlanner(cache);

        private final BuildLifecycle lifecycle =
            new BuildLifecycle();

        BuildReport execute(BuildRequest request) {
            lifecycle.transition(
                request.imageName(),
                BuildState.VALIDATED
            );

            try {
                List<Instruction> instructions =
                    parser.parse(request.dockerfileContent());

                List<Finding> findings =
                    security.evaluate(instructions);

                boolean hasErrors = findings.stream().anyMatch(
                    finding ->
                        finding.severity() == FindingSeverity.ERROR
                );

                if (hasErrors) {
                    throw new PolicyViolationException(
                        "Dockerfile failed security validation."
                    );
                }

                if (
                    !request.allowWarnings() &&
                    findings.stream().anyMatch(
                        finding ->
                            finding.severity() == FindingSeverity.WARNING
                    )
                ) {
                    throw new PolicyViolationException(
                        "Build rejected because warnings are not permitted."
                    );
                }

                lifecycle.transition(
                    request.imageName(),
                    BuildState.BUILDING
                );

                List<ImageLayer> layers =
                    planner.plan(instructions);

                long size = layers.stream()
                    .mapToLong(ImageLayer::estimatedSizeBytes)
                    .sum();

                int hits = (int) layers.stream()
                    .filter(l -> l.status() == LayerStatus.CACHED)
                    .count();

                int misses = layers.size() - hits;

                BuildMetrics metrics = new BuildMetrics(
                    layers.size(),
                    size,
                    hits,
                    misses
                );

                String dockerfileHash = sha256(
                    request.dockerfileContent()
                );

                BuildReport report = new BuildReport(
                    request.imageName(),
                    dockerfileHash,
                    layers,
                    findings,
                    optimization.evaluate(instructions),
                    metrics
                );

                lifecycle.transition(
                    request.imageName(),
                    BuildState.BUILT
                );

                return report;

            } catch (RuntimeException exception) {
                if (
                    lifecycle.get(request.imageName()) !=
                    BuildState.FAILED
                ) {
                    lifecycle.transition(
                        request.imageName(),
                        BuildState.FAILED
                    );
                }

                throw exception;
            }
        }

        void markPublished(String imageName) {
            lifecycle.transition(
                imageName,
                BuildState.PUBLISHED
            );
        }

        BuildState state(String imageName) {
            return lifecycle.get(imageName);
        }

        int cachedLayers() {
            return cache.size();
        }

        private static String sha256(String input) {
            try {
                byte[] hash = MessageDigest
                    .getInstance("SHA-256")
                    .digest(
                        input.getBytes(StandardCharsets.UTF_8)
                    );

                StringBuilder output = new StringBuilder();

                for (byte value : hash) {
                    output.append(
                        String.format("%02x", value)
                    );
                }

                return output.toString();

            } catch (NoSuchAlgorithmException exception) {
                throw new IllegalStateException(exception);
            }
        }
    }

    static final String SAMPLE_DOCKERFILE = """
        FROM node:22-alpine AS builder

        WORKDIR /app

        COPY package.json package-lock.json ./

        RUN npm ci

        COPY . .

        RUN npm run build

        FROM node:22-alpine AS runtime

        ENV NODE_ENV=production

        WORKDIR /app

        COPY --from=builder /app/dist ./dist

        COPY --from=builder /app/node_modules ./node_modules

        USER node

        EXPOSE 3000

        CMD ["node", "dist/server.js"]
        """;

    static void printReport(BuildReport report) {
        System.out.println("\nBUILD REPORT");
        System.out.println("================================");

        System.out.println(
            "Image: " + report.imageName()
        );

        System.out.println(
            "Dockerfile SHA-256: " + report.dockerfileHash()
        );

        System.out.println(
            "Layers: " + report.metrics().layerCount()
        );

        System.out.println(
            "Estimated size: " +
            report.metrics().totalSizeBytes() / 1_000_000.0 +
            " MB"
        );

        System.out.println(
            "Cache hits: " + report.metrics().cacheHits()
        );

        System.out.println(
            "Cache misses: " + report.metrics().cacheMisses()
        );

        System.out.println("\nLAYER DETAILS");

        report.layers().forEach(layer ->
            System.out.printf(
                "Layer %d | Stage %d | %s | %.2f MB | %s%n",
                layer.index(),
                layer.stage(),
                layer.instruction().type(),
                layer.estimatedSizeBytes() / 1_000_000.0,
                layer.status()
            )
        );

        System.out.println("\nSECURITY FINDINGS");

        report.findings().forEach(finding ->
            System.out.println(
                "[" + finding.severity() + "] " +
                finding.code() + ": " +
                finding.message()
            )
        );

        System.out.println("\nOPTIMIZATION RECOMMENDATIONS");

        report.recommendations().forEach(
            recommendation ->
                System.out.println("- " + recommendation)
        );
    }

    public static void main(String[] args) {
        BuildService service = new BuildService();
        ImageRegistry registry = new ImageRegistry();

        try {
            System.out.println(
                "DOCKER ENTERPRISE BUILD GOVERNANCE"
            );

            BuildRequest request = new BuildRequest(
                "inventory-api:1.0",
                SAMPLE_DOCKERFILE,
                true
            );

            BuildReport report = service.execute(request);

            printReport(report);

            registry.publish(report);

            service.markPublished(request.imageName());

            System.out.println("\nREGISTRY");

            System.out.println(
                "Published images: " + registry.size()
            );

            System.out.println(
                "Build state: " +
                service.state(request.imageName())
            );

            BuildRequest repeatedRequest = new BuildRequest(
                "inventory-api:1.1",
                SAMPLE_DOCKERFILE,
                true
            );

            BuildReport repeated =
                service.execute(repeatedRequest);

            System.out.println("\nREPEATED BUILD");

            System.out.println(
                "Cache hits: " +
                repeated.metrics().cacheHits()
            );

            System.out.println(
                "Cache misses: " +
                repeated.metrics().cacheMisses()
            );

            System.out.println("\nUNSAFE IMAGE TEST");

            BuildRequest unsafe = new BuildRequest(
                "unsafe-api:1.0",
                """
                FROM node:latest
                ENV API_KEY=secret
                USER root
                CMD ["node", "app.js"]
                """,
                true
            );

            try {
                service.execute(unsafe);

            } catch (PolicyViolationException exception) {
                System.out.println(
                    "Rejected: " + exception.getMessage()
                );
            }

            System.out.println("\nCACHE ENTRIES");

            System.out.println(service.cachedLayers());

        } catch (DockerException exception) {
            System.err.println(
                "BUILD ERROR: " + exception.getMessage()
            );

            System.exit(1);
        }
    }
}
