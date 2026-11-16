import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/*
 * Docker Fundamentals: Enterprise Container Platform Model.
 *
 * Java 17 implementation covering:
 * - Docker client and daemon responsibilities
 * - Image construction and immutable layer metadata
 * - Container lifecycle and state transitions
 * - Registry authentication and distribution
 * - Resource allocation and port reservations
 * - Enterprise policy enforcement
 * - Status checks and approval decisions
 * - Audit events and operational reporting
 *
 * Run:
 * javac DockerFundamentals.java
 * java DockerFundamentals
 */

public class DockerFundamentals {

    enum ContainerState {
        CREATED,
        RUNNING,
        STOPPED,
        REMOVED
    }

    enum ReviewState {
        PENDING,
        APPROVED,
        CHANGES_REQUESTED,
        DISMISSED
    }

    enum CheckState {
        PENDING,
        PASSED,
        FAILED
    }

    enum EventType {
        IMAGE_BUILT,
        IMAGE_PUSHED,
        IMAGE_PULLED,
        CONTAINER_CREATED,
        CONTAINER_STARTED,
        CONTAINER_STOPPED,
        CONTAINER_REMOVED
    }

    static class DockerException extends RuntimeException {
        DockerException(String message) {
            super(message);
        }
    }

    static class ValidationException extends DockerException {
        ValidationException(String message) {
            super(message);
        }
    }

    static class ConflictException extends DockerException {
        ConflictException(String message) {
            super(message);
        }
    }

    static class ResourceException extends DockerException {
        ResourceException(String message) {
            super(message);
        }
    }

    record ImageLayer(
        String instruction,
        String digest,
        double sizeMB
    ) {
        ImageLayer {
            Objects.requireNonNull(instruction);
            Objects.requireNonNull(digest);

            if (instruction.isBlank() || sizeMB <= 0) {
                throw new ValidationException("Invalid image layer.");
            }
        }
    }

    record Image(
        String id,
        String repository,
        String tag,
        List<ImageLayer> layers,
        Map<String, String> environment,
        Instant createdAt
    ) {
        Image {
            Objects.requireNonNull(id);
            Objects.requireNonNull(repository);
            Objects.requireNonNull(tag);

            layers = List.copyOf(layers);
            environment = Map.copyOf(environment);

            if (layers.isEmpty()) {
                throw new ValidationException(
                    "An image requires at least one layer."
                );
            }
        }

        String reference() {
            return repository + ":" + tag;
        }

        double sizeMB() {
            return layers.stream()
                .mapToDouble(ImageLayer::sizeMB)
                .sum();
        }
    }

    record ResourceCapacity(
        int memoryMB,
        double cpu
    ) {
        ResourceCapacity {
            if (memoryMB <= 0 || cpu <= 0) {
                throw new ValidationException(
                    "Invalid resource capacity."
                );
            }
        }
    }

    record ResourceAllocation(
        int memoryMB,
        double cpu
    ) {
        ResourceAllocation {
            if (memoryMB <= 0 || cpu <= 0) {
                throw new ValidationException(
                    "Invalid resource allocation."
                );
            }
        }
    }

    record ContainerConfiguration(
        String name,
        String imageReference,
        Map<Integer, Integer> ports,
        Map<String, String> environment,
        int memoryMB,
        double cpu
    ) {
        ContainerConfiguration {
            Objects.requireNonNull(name);
            Objects.requireNonNull(imageReference);

            ports = Map.copyOf(ports);
            environment = Map.copyOf(environment);

            if (memoryMB <= 0 || cpu <= 0) {
                throw new ValidationException(
                    "Invalid container resource request."
                );
            }
        }
    }

    record AuditEvent(
        EventType type,
        String resourceId,
        Instant timestamp,
        String description
    ) {}

    static class Container {
        private final String id;
        private final String name;
        private final Image image;
        private final Map<Integer, Integer> ports;
        private final Map<String, String> environment;
        private final ResourceAllocation resources;
        private final List<String> logs = new ArrayList<>();

        private ContainerState state = ContainerState.CREATED;

        Container(
            String name,
            Image image,
            ContainerConfiguration configuration
        ) {
            this.id = UUID.randomUUID()
                .toString()
                .replace("-", "")
                .substring(0, 12);

            this.name = name;
            this.image = image;
            this.ports = new LinkedHashMap<>(configuration.ports());
            this.environment = Map.copyOf(configuration.environment());

            this.resources = new ResourceAllocation(
                configuration.memoryMB(),
                configuration.cpu()
            );
        }

        String id() {
            return id;
        }

        String name() {
            return name;
        }

        Image image() {
            return image;
        }

        ContainerState state() {
            return state;
        }

        Map<Integer, Integer> ports() {
            return Collections.unmodifiableMap(ports);
        }

        ResourceAllocation resources() {
            return resources;
        }

        List<String> logs() {
            return List.copyOf(logs);
        }

        void transition(ContainerState next) {
            boolean valid = switch (state) {
                case CREATED ->
                    next == ContainerState.RUNNING ||
                    next == ContainerState.REMOVED;

                case RUNNING ->
                    next == ContainerState.STOPPED;

                case STOPPED ->
                    next == ContainerState.RUNNING ||
                    next == ContainerState.REMOVED;

                case REMOVED -> false;
            };

            if (!valid) {
                throw new ConflictException(
                    "Invalid container state transition: " +
                    state + " -> " + next
                );
            }

            state = next;
            logs.add(
                Instant.now() + " State changed to " + next
            );
        }
    }

    static class Registry {
        private final String name;
        private final Map<String, Image> images = new HashMap<>();
        private final Map<String, String> credentials = new HashMap<>();

        Registry(String name) {
            if (name == null || name.isBlank()) {
                throw new ValidationException(
                    "Registry name is required."
                );
            }

            this.name = name;
        }

        void registerUser(String username, String token) {
            if (
                username == null ||
                username.isBlank() ||
                token == null ||
                token.length() < 8
            ) {
                throw new ValidationException(
                    "Invalid registry credentials."
                );
            }

            credentials.put(username, token);
        }

        private void authenticate(String username, String token) {
            String expected = credentials.get(username);

            if (
                expected == null ||
                !java.security.MessageDigest.isEqual(
                    expected.getBytes(java.nio.charset.StandardCharsets.UTF_8),
                    token.getBytes(java.nio.charset.StandardCharsets.UTF_8)
                )
            ) {
                throw new DockerException(
                    "Registry authentication failed."
                );
            }
        }

        void push(
            Image image,
            String username,
            String token
        ) {
            authenticate(username, token);
            images.put(image.reference(), image);
        }

        Image pull(
            String reference,
            String username,
            String token
        ) {
            authenticate(username, token);

            Image image = images.get(reference);

            if (image == null) {
                throw new DockerException(
                    "Image not found in registry."
                );
            }

            return image;
        }

        String name() {
            return name;
        }
    }

    static class ResourceManager {
        private final ResourceCapacity capacity;

        private final Map<String, ResourceAllocation> allocations =
            new HashMap<>();

        ResourceManager(ResourceCapacity capacity) {
            this.capacity = capacity;
        }

        synchronized void reserve(
            String containerId,
            ResourceAllocation allocation
        ) {
            if (allocations.containsKey(containerId)) {
                throw new ConflictException(
                    "Resources already allocated."
                );
            }

            int memoryUsed = allocations.values().stream()
                .mapToInt(ResourceAllocation::memoryMB)
                .sum();

            double cpuUsed = allocations.values().stream()
                .mapToDouble(ResourceAllocation::cpu)
                .sum();

            if (
                memoryUsed + allocation.memoryMB() >
                    capacity.memoryMB() ||
                cpuUsed + allocation.cpu() > capacity.cpu()
            ) {
                throw new ResourceException(
                    "Daemon resource capacity exceeded."
                );
            }

            allocations.put(containerId, allocation);
        }

        synchronized void release(String containerId) {
            allocations.remove(containerId);
        }

        synchronized ResourceAllocation usage() {
            return new ResourceAllocation(
                allocations.values().stream()
                    .mapToInt(ResourceAllocation::memoryMB)
                    .sum(),
                allocations.values().stream()
                    .mapToDouble(ResourceAllocation::cpu)
                    .sum()
            );
        }
    }

    static class DockerDaemon {
        private static final Pattern NAME_PATTERN =
            Pattern.compile(
                "[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}"
            );

        private final Map<String, Image> images = new HashMap<>();
        private final Map<String, String> tags = new HashMap<>();

        private final Map<String, Container> containers =
            new LinkedHashMap<>();

        private final Map<Integer, String> occupiedPorts =
            new HashMap<>();

        private final Map<String, Registry> registries =
            new HashMap<>();

        private final List<AuditEvent> events = new ArrayList<>();

        private final ResourceManager resourceManager;

        private boolean available = true;

        DockerDaemon(ResourceCapacity capacity) {
            resourceManager = new ResourceManager(capacity);
        }

        private void requireAvailable() {
            if (!available) {
                throw new DockerException(
                    "Docker daemon is unavailable."
                );
            }
        }

        void setAvailable(boolean available) {
            this.available = available;
        }

        private void audit(
            EventType type,
            String id,
            String description
        ) {
            events.add(new AuditEvent(
                type,
                id,
                Instant.now(),
                description
            ));
        }

        synchronized void registerRegistry(Registry registry) {
            registries.put(registry.name(), registry);
        }

        synchronized Image buildImage(
            String repository,
            String tag,
            List<String> instructions,
            Map<String, String> environment
        ) {
            requireAvailable();

            if (
                repository == null ||
                !repository.matches("[a-zA-Z0-9._/-]+") ||
                tag == null ||
                !tag.matches("[a-zA-Z0-9_.-]+")
            ) {
                throw new ValidationException(
                    "Invalid image reference."
                );
            }

            if (instructions.isEmpty()) {
                throw new ValidationException(
                    "Image requires at least one layer."
                );
            }

            List<ImageLayer> layers = new ArrayList<>();

            StringBuilder material = new StringBuilder();

            for (String instruction : instructions) {
                if (instruction == null || instruction.isBlank()) {
                    throw new ValidationException(
                        "Empty image instruction."
                    );
                }

                material.append(instruction);

                String digest = "sha256:" + java.util.HexFormat.of()
                    .formatHex(
                        hash(instruction)
                    );

                layers.add(new ImageLayer(
                    instruction,
                    digest,
                    Math.max(0.1, instruction.length() / 1024.0)
                ));
            }

            String id = "sha256:" + java.util.HexFormat.of()
                .formatHex(hash(material.toString()));

            Image image = new Image(
                id,
                repository,
                tag,
                layers,
                environment,
                Instant.now()
            );

            images.put(id, image);
            tags.put(image.reference(), id);

            audit(
                EventType.IMAGE_BUILT,
                id,
                image.reference()
            );

            return image;
        }

        private byte[] hash(String value) {
            try {
                return java.security.MessageDigest
                    .getInstance("SHA-256")
                    .digest(
                        value.getBytes(
                            java.nio.charset.StandardCharsets.UTF_8
                        )
                    );
            } catch (java.security.NoSuchAlgorithmException exception) {
                throw new DockerException(exception.getMessage());
            }
        }

        synchronized Image getImage(String reference) {
            requireAvailable();

            String id = tags.getOrDefault(reference, reference);
            Image image = images.get(id);

            if (image == null) {
                throw new DockerException(
                    "Image not found: " + reference
                );
            }

            return image;
        }

        synchronized void tagImage(
            String source,
            String target
        ) {
            Image image = getImage(source);

            if (
                target == null ||
                !target.matches("[a-zA-Z0-9._/-]+:[a-zA-Z0-9_.-]+")
            ) {
                throw new ValidationException(
                    "Invalid target image reference."
                );
            }

            tags.put(target, image.id());
        }

        synchronized void pushImage(
            String reference,
            String registryName,
            String username,
            String token
        ) {
            requireAvailable();

            Registry registry = registries.get(registryName);

            if (registry == null) {
                throw new DockerException("Registry not found.");
            }

            Image image = getImage(reference);

            registry.push(image, username, token);

            audit(
                EventType.IMAGE_PUSHED,
                image.id(),
                registryName
            );
        }

        synchronized Image pullImage(
            String registryName,
            String reference,
            String username,
            String token
        ) {
            requireAvailable();

            Registry registry = registries.get(registryName);

            if (registry == null) {
                throw new DockerException("Registry not found.");
            }

            Image image = registry.pull(
                reference,
                username,
                token
            );

            images.put(image.id(), image);
            tags.put(image.reference(), image.id());

            audit(
                EventType.IMAGE_PULLED,
                image.id(),
                registryName
            );

            return image;
        }

        synchronized Container createContainer(
            ContainerConfiguration configuration
        ) {
            requireAvailable();

            if (
                !NAME_PATTERN.matcher(configuration.name()).matches()
            ) {
                throw new ValidationException(
                    "Invalid container name."
                );
            }

            boolean duplicate = containers.values().stream()
                .anyMatch(container ->
                    container.name().equals(configuration.name()) &&
                    container.state() != ContainerState.REMOVED
                );

            if (duplicate) {
                throw new ConflictException(
                    "Container name already exists."
                );
            }

            Image image = getImage(configuration.imageReference());

            for (Map.Entry<Integer, Integer> mapping :
                configuration.ports().entrySet()) {

                int host = mapping.getKey();
                int target = mapping.getValue();

                if (
                    host < 1 || host > 65535 ||
                    target < 1 || target > 65535
                ) {
                    throw new ValidationException(
                        "Invalid port mapping."
                    );
                }

                if (occupiedPorts.containsKey(host)) {
                    throw new ConflictException(
                        "Host port already occupied."
                    );
                }
            }

            Container container = new Container(
                configuration.name(),
                image,
                configuration
            );

            containers.put(container.id(), container);

            audit(
                EventType.CONTAINER_CREATED,
                container.id(),
                image.reference()
            );

            return container;
        }

        synchronized void startContainer(String id) {
            requireAvailable();

            Container container = containers.get(id);

            if (container == null) {
                throw new DockerException("Container not found.");
            }

            if (
                container.state() == ContainerState.RUNNING ||
                container.state() == ContainerState.REMOVED
            ) {
                throw new ConflictException(
                    "Invalid container state."
                );
            }

            // Verify ports before making any reservations.
            for (int hostPort : container.ports().keySet()) {
                if (occupiedPorts.containsKey(hostPort)) {
                    throw new ConflictException(
                        "Host port conflict."
                    );
                }
            }

            resourceManager.reserve(
                id,
                container.resources()
            );

            try {
                for (int hostPort : container.ports().keySet()) {
                    occupiedPorts.put(hostPort, id);
                }

                container.transition(ContainerState.RUNNING);

            } catch (RuntimeException exception) {
                resourceManager.release(id);

                for (int hostPort : container.ports().keySet()) {
                    occupiedPorts.remove(hostPort, id);
                }

                throw exception;
            }

            audit(
                EventType.CONTAINER_STARTED,
                id,
                container.name()
            );
        }

        synchronized void stopContainer(String id) {
            requireAvailable();

            Container container = containers.get(id);

            if (
                container == null ||
                container.state() != ContainerState.RUNNING
            ) {
                throw new ConflictException(
                    "Container is not running."
                );
            }

            container.transition(ContainerState.STOPPED);

            for (int hostPort : container.ports().keySet()) {
                occupiedPorts.remove(hostPort, id);
            }

            resourceManager.release(id);

            audit(
                EventType.CONTAINER_STOPPED,
                id,
                container.name()
            );
        }

        synchronized void removeContainer(String id) {
            requireAvailable();

            Container container = containers.get(id);

            if (container == null) {
                throw new DockerException("Container not found.");
            }

            container.transition(ContainerState.REMOVED);

            audit(
                EventType.CONTAINER_REMOVED,
                id,
                container.name()
            );
        }

        synchronized List<Container> listContainers(
            boolean runningOnly
        ) {
            return containers.values().stream()
                .filter(container ->
                    container.state() != ContainerState.REMOVED
                )
                .filter(container ->
                    !runningOnly ||
                    container.state() == ContainerState.RUNNING
                )
                .collect(Collectors.toUnmodifiableList());
        }

        synchronized ResourceAllocation resourceUsage() {
            return resourceManager.usage();
        }

        synchronized List<AuditEvent> events() {
            return List.copyOf(events);
        }
    }

    record ApprovalDecision(
        String reviewer,
        ReviewState state,
        boolean eligible,
        boolean stale,
        boolean dismissed
    ) {}

    record RepositoryPolicy(
        int requiredApprovals,
        Set<String> requiredChecks,
        boolean protectedBranch,
        boolean directPushAllowed,
        boolean forcePushAllowed,
        boolean deletionAllowed,
        boolean requireResolvedConversations,
        boolean requireLinearHistory
    ) {
        RepositoryPolicy {
            if (requiredApprovals < 0) {
                throw new ValidationException(
                    "Invalid approval requirement."
                );
            }

            requiredChecks = Set.copyOf(requiredChecks);
        }
    }

    record PullRequest(
        String id,
        String sourceBranch,
        String targetBranch,
        boolean open,
        boolean draft,
        boolean conflict,
        boolean synchronizedWithTarget,
        boolean linearHistory,
        boolean conversationsResolved,
        List<ApprovalDecision> approvals,
        Map<String, CheckState> checks
    ) {
        PullRequest {
            approvals = List.copyOf(approvals);
            checks = Map.copyOf(checks);
        }
    }

    record MergeDecision(
        boolean eligible,
        List<String> failures
    ) {
        MergeDecision {
            failures = List.copyOf(failures);
        }
    }

    interface EligibilityService {
        MergeDecision evaluate(
            PullRequest pullRequest,
            RepositoryPolicy policy
        );
    }

    static class EnterpriseEligibilityService
        implements EligibilityService {

        @Override
        public MergeDecision evaluate(
            PullRequest pr,
            RepositoryPolicy policy
        ) {
            List<String> failures = new ArrayList<>();

            if (!pr.open()) {
                failures.add("Pull Request is closed.");
            }

            if (pr.draft()) {
                failures.add("Draft Pull Request.");
            }

            if (pr.sourceBranch().equals(pr.targetBranch())) {
                failures.add("Invalid branch relationship.");
            }

            if (pr.conflict()) {
                failures.add("Merge conflict.");
            }

            if (!pr.synchronizedWithTarget()) {
                failures.add("Source branch is not synchronized.");
            }

            if (
                policy.requireLinearHistory() &&
                !pr.linearHistory()
            ) {
                failures.add("Linear history requirement failed.");
            }

            if (
                policy.requireResolvedConversations() &&
                !pr.conversationsResolved()
            ) {
                failures.add("Review conversations remain unresolved.");
            }

            long validApprovals = pr.approvals().stream()
                .filter(ApprovalDecision::eligible)
                .filter(approval ->
                    approval.state() == ReviewState.APPROVED
                )
                .filter(approval -> !approval.stale())
                .filter(approval -> !approval.dismissed())
                .count();

            if (validApprovals < policy.requiredApprovals()) {
                failures.add("Insufficient eligible approvals.");
            }

            for (String required : policy.requiredChecks()) {
                if (
                    pr.checks().get(required) != CheckState.PASSED
                ) {
                    failures.add(
                        "Required check not passed: " + required
                    );
                }
            }

            return new MergeDecision(
                failures.isEmpty(),
                failures
            );
        }
    }

    static class DockerClient {
        private final DockerDaemon daemon;

        DockerClient(DockerDaemon daemon) {
            this.daemon = daemon;
        }

        Container run(ContainerConfiguration configuration) {
            Container container =
                daemon.createContainer(configuration);

            daemon.startContainer(container.id());

            return container;
        }

        void printInventory() {
            System.out.println("\nCONTAINER INVENTORY");

            daemon.listContainers(false).forEach(container ->
                System.out.printf(
                    "%-14s %-20s %-10s %s%n",
                    container.id(),
                    container.name(),
                    container.state(),
                    container.image().reference()
                )
            );
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println("DOCKER FUNDAMENTALS");
            System.out.println("===================");

            DockerDaemon daemon = new DockerDaemon(
                new ResourceCapacity(4096, 4.0)
            );

            DockerClient client = new DockerClient(daemon);

            System.out.println("\n1. IMAGE CONSTRUCTION");

            Image image = daemon.buildImage(
                "company/web-service",
                "1.0",
                List.of(
                    "FROM eclipse-temurin:17-jre",
                    "WORKDIR /app",
                    "COPY application.jar .",
                    "EXPOSE 8080",
                    "ENTRYPOINT java -jar application.jar"
                ),
                Map.of(
                    "APP_ENV", "production"
                )
            );

            System.out.println("Image ID: " + image.id());
            System.out.println("Layers: " + image.layers().size());
            System.out.println("Size: " + image.sizeMB() + " MB");

            System.out.println("\n2. REGISTRY CONFIGURATION");

            Registry registry = new Registry(
                "registry.example.com"
            );

            registry.registerUser(
                "developer",
                "demo-token-2026"
            );

            daemon.registerRegistry(registry);

            daemon.pushImage(
                image.reference(),
                registry.name(),
                "developer",
                "demo-token-2026"
            );

            System.out.println("Image published.");

            System.out.println("\n3. CONTAINER DEPLOYMENT");

            ContainerConfiguration configuration =
                new ContainerConfiguration(
                    "enterprise-service",
                    image.reference(),
                    Map.of(8080, 8080),
                    Map.of("APP_ENV", "production"),
                    512,
                    1.0
                );

            Container container = client.run(configuration);

            System.out.println("Container ID: " + container.id());
            System.out.println("State: " + container.state());

            client.printInventory();

            System.out.println("\n4. RESOURCE REPORT");

            System.out.println(daemon.resourceUsage());

            System.out.println("\n5. PORT CONFLICT TEST");

            try {
                client.run(
                    new ContainerConfiguration(
                        "conflicting-service",
                        image.reference(),
                        Map.of(8080, 9090),
                        Map.of(),
                        512,
                        1.0
                    )
                );
            } catch (DockerException exception) {
                System.out.println(
                    "Expected failure: " + exception.getMessage()
                );
            }

            System.out.println("\n6. LIFECYCLE MANAGEMENT");

            daemon.stopContainer(container.id());
            daemon.startContainer(container.id());
            daemon.stopContainer(container.id());
            daemon.removeContainer(container.id());

            System.out.println("Lifecycle completed.");

            System.out.println("\n7. REGISTRY PULL");

            Image pulled = daemon.pullImage(
                registry.name(),
                image.reference(),
                "developer",
                "demo-token-2026"
            );

            System.out.println(
                "Retrieved: " + pulled.reference()
            );

            System.out.println("\n8. ENTERPRISE GOVERNANCE");

            RepositoryPolicy policy = new RepositoryPolicy(
                2,
                Set.of("build", "tests", "security"),
                true,
                false,
                false,
                false,
                true,
                true
            );

            PullRequest pr = new PullRequest(
                "PR-204",
                "feature/container-deployment",
                "main",
                true,
                false,
                false,
                true,
                true,
                true,
                List.of(
                    new ApprovalDecision(
                        "reviewer-a",
                        ReviewState.APPROVED,
                        true,
                        false,
                        false
                    ),
                    new ApprovalDecision(
                        "reviewer-b",
                        ReviewState.APPROVED,
                        true,
                        false,
                        false
                    )
                ),
                Map.of(
                    "build", CheckState.PASSED,
                    "tests", CheckState.PASSED,
                    "security", CheckState.PASSED
                )
            );

            EligibilityService service =
                new EnterpriseEligibilityService();

            MergeDecision decision = service.evaluate(
                pr,
                policy
            );

            System.out.println(
                "Merge eligible: " + decision.eligible()
            );

            decision.failures().forEach(
                System.out::println
            );

            System.out.println("\n9. AUDIT EVENTS");

            daemon.events().forEach(System.out::println);

            System.out.println("\n10. ASSERTIONS");

            if (!decision.eligible()) {
                throw new DockerException(
                    "Governance assertion failed."
                );
            }

            if (!daemon.listContainers(false).isEmpty()) {
                throw new DockerException(
                    "Container cleanup assertion failed."
                );
            }

            if (daemon.resourceUsage().memoryMB() != 0) {
                throw new DockerException(
                    "Resource cleanup assertion failed."
                );
            }

            System.out.println("All assertions passed.");

        } catch (DockerException exception) {
            System.err.println(
                "Execution failed: " + exception.getMessage()
            );

            System.exit(1);
        }
    }
}
