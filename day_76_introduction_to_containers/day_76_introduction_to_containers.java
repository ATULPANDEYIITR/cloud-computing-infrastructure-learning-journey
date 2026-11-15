import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/*
 * Enterprise Container Management System
 *
 * Java 17
 *
 * Models:
 * - Container images and immutable layers
 * - Image registry
 * - Runtime lifecycle
 * - Resource admission control
 * - Isolation configuration
 * - Deployment policy
 * - Health monitoring
 * - Restart decisions
 * - Audit events
 *
 * This is a control-plane simulation. It does not implement
 * Linux namespaces, cgroups or an OCI runtime.
 */

public class ContainerEnterprise {

    enum ContainerState {
        CREATED,
        RUNNING,
        PAUSED,
        STOPPED,
        FAILED,
        REMOVED
    }

    enum RestartPolicy {
        NEVER,
        ON_FAILURE,
        ALWAYS
    }

    enum IsolationNamespace {
        PID,
        NETWORK,
        MOUNT,
        USER,
        IPC,
        UTS,
        CGROUP
    }

    enum HealthStatus {
        UNKNOWN,
        HEALTHY,
        UNHEALTHY
    }

    static class ContainerException extends RuntimeException {
        ContainerException(String message) {
            super(message);
        }
    }

    record ResourceLimits(
        double cpuCores,
        int memoryMB,
        int diskMB,
        int processLimit
    ) {
        ResourceLimits {
            if (!Double.isFinite(cpuCores) ||
                cpuCores <= 0 || cpuCores > 128) {
                throw new IllegalArgumentException("Invalid CPU limit.");
            }

            if (memoryMB < 16 || memoryMB > 1048576) {
                throw new IllegalArgumentException("Invalid memory limit.");
            }

            if (diskMB < 16 || diskMB > 10485760) {
                throw new IllegalArgumentException("Invalid disk limit.");
            }

            if (processLimit < 1 || processLimit > 100000) {
                throw new IllegalArgumentException("Invalid process limit.");
            }
        }
    }

    record ImageLayer(
        String name,
        String content
    ) {
        ImageLayer {
            if (name == null || name.isBlank() ||
                content == null || content.isBlank()) {
                throw new IllegalArgumentException("Invalid image layer.");
            }
        }
    }

    static final class ContainerImage {
        private final String name;
        private final String version;
        private final String entrypoint;
        private final List<ImageLayer> layers;
        private final Set<Integer> exposedPorts;

        ContainerImage(
            String name,
            String version,
            String entrypoint,
            List<ImageLayer> layers,
            Set<Integer> exposedPorts
        ) {
            if (name == null ||
                !name.matches("[a-zA-Z0-9][a-zA-Z0-9._/-]{0,127}")) {
                throw new IllegalArgumentException("Invalid image name.");
            }

            if (version == null || version.isBlank()) {
                throw new IllegalArgumentException("Invalid image version.");
            }

            if (entrypoint == null || entrypoint.isBlank()) {
                throw new IllegalArgumentException("Entrypoint is required.");
            }

            if (layers == null || layers.isEmpty()) {
                throw new IllegalArgumentException("Image needs layers.");
            }

            for (int port : exposedPorts) {
                if (port < 1 || port > 65535) {
                    throw new IllegalArgumentException("Invalid image port.");
                }
            }

            this.name = name;
            this.version = version;
            this.entrypoint = entrypoint;
            this.layers = List.copyOf(layers);
            this.exposedPorts = Set.copyOf(exposedPorts);
        }

        String reference() {
            return name + ":" + version;
        }

        List<ImageLayer> layers() {
            return layers;
        }

        String entrypoint() {
            return entrypoint;
        }
    }

    interface ImageSource {
        ContainerImage pull(String reference);
    }

    static final class ImageRegistry implements ImageSource {
        private final Map<String, ContainerImage> images =
            new HashMap<>();

        public void push(ContainerImage image) {
            Objects.requireNonNull(image);
            images.put(image.reference(), image);
        }

        @Override
        public ContainerImage pull(String reference) {
            ContainerImage image = images.get(reference);

            if (image == null) {
                throw new ContainerException(
                    "Image not found: " + reference
                );
            }

            return image;
        }
    }

    record ResourceUsage(
        double cpuCores,
        int memoryMB,
        int diskMB,
        int processCount
    ) {
        ResourceUsage {
            if (!Double.isFinite(cpuCores) ||
                cpuCores < 0 ||
                memoryMB < 0 ||
                diskMB < 0 ||
                processCount < 0) {
                throw new IllegalArgumentException("Invalid resource usage.");
            }
        }
    }

    static final class HostResourceManager {
        private final ResourceLimits capacity;
        private final Map<String, ResourceLimits> allocations =
            new HashMap<>();

        HostResourceManager(ResourceLimits capacity) {
            this.capacity = capacity;
        }

        synchronized void allocate(
            String containerId,
            ResourceLimits requested
        ) {
            if (allocations.containsKey(containerId)) {
                throw new ContainerException("Duplicate allocation.");
            }

            double cpu = allocations.values().stream()
                .mapToDouble(ResourceLimits::cpuCores)
                .sum();

            int memory = allocations.values().stream()
                .mapToInt(ResourceLimits::memoryMB)
                .sum();

            int disk = allocations.values().stream()
                .mapToInt(ResourceLimits::diskMB)
                .sum();

            if (cpu + requested.cpuCores() > capacity.cpuCores() ||
                memory + requested.memoryMB() > capacity.memoryMB() ||
                disk + requested.diskMB() > capacity.diskMB()) {
                throw new ContainerException(
                    "Insufficient host resources."
                );
            }

            allocations.put(containerId, requested);
        }

        synchronized void release(String containerId) {
            allocations.remove(containerId);
        }

        synchronized int allocationCount() {
            return allocations.size();
        }
    }

    static final class Container {
        private final String id;
        private final String name;
        private final ContainerImage image;
        private final ResourceLimits limits;
        private final RestartPolicy restartPolicy;
        private final Map<String, String> environment;

        private final Set<IsolationNamespace> isolation =
            EnumSet.allOf(IsolationNamespace.class);

        private ContainerState state = ContainerState.CREATED;
        private HealthStatus health = HealthStatus.UNKNOWN;

        private ResourceUsage usage =
            new ResourceUsage(0, 0, 0, 0);

        private int restartCount;
        private int exitCode;

        private final Instant createdAt = Instant.now();
        private Instant startedAt;

        Container(
            String id,
            String name,
            ContainerImage image,
            ResourceLimits limits,
            RestartPolicy restartPolicy,
            Map<String, String> environment
        ) {
            this.id = id;
            this.name = name;
            this.image = image;
            this.limits = limits;
            this.restartPolicy = restartPolicy;
            this.environment = Map.copyOf(environment);
        }

        String id() {
            return id;
        }

        String name() {
            return name;
        }

        ContainerState state() {
            return state;
        }

        HealthStatus health() {
            return health;
        }

        int restartCount() {
            return restartCount;
        }

        String imageReference() {
            return image.reference();
        }

        Instant createdAt() {
            return createdAt;
        }

        Instant startedAt() {
            return startedAt;
        }

        Set<IsolationNamespace> isolation() {
            return Collections.unmodifiableSet(isolation);
        }
    }

    static final class DeploymentPolicy {
        private final int maximumRestarts;

        DeploymentPolicy(int maximumRestarts) {
            if (maximumRestarts < 0 || maximumRestarts > 100) {
                throw new IllegalArgumentException("Invalid restart limit.");
            }

            this.maximumRestarts = maximumRestarts;
        }

        boolean mayRestart(Container container, int exitCode) {
            if (container.restartCount >= maximumRestarts) {
                return false;
            }

            return switch (container.restartPolicy) {
                case NEVER -> false;
                case ALWAYS -> true;
                case ON_FAILURE -> exitCode != 0;
            };
        }
    }

    static final class AuditService {
        private final List<String> events = new ArrayList<>();

        synchronized void record(String event, String containerId) {
            events.add(
                Instant.now() + " | " + event + " | " + containerId
            );
        }

        synchronized List<String> getEvents() {
            return List.copyOf(events);
        }
    }

    static final class ContainerRuntime {
        private final ImageSource imageSource;
        private final HostResourceManager host;
        private final DeploymentPolicy policy;
        private final AuditService audit;

        private final Map<String, Container> containers =
            new HashMap<>();

        private final Set<String> names = new HashSet<>();

        ContainerRuntime(
            ImageSource imageSource,
            HostResourceManager host,
            DeploymentPolicy policy,
            AuditService audit
        ) {
            this.imageSource = imageSource;
            this.host = host;
            this.policy = policy;
            this.audit = audit;
        }

        synchronized Container create(
            String imageReference,
            String name,
            ResourceLimits limits,
            RestartPolicy restartPolicy,
            Map<String, String> environment
        ) {
            if (name == null ||
                !name.matches("[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}")) {
                throw new IllegalArgumentException("Invalid container name.");
            }

            if (names.contains(name)) {
                throw new ContainerException("Container name exists.");
            }

            if (environment.size() > 128) {
                throw new IllegalArgumentException("Environment too large.");
            }

            environment.forEach((key, value) -> {
                if (key == null ||
                    !key.matches("[A-Z_][A-Z0-9_]{0,63}") ||
                    value == null ||
                    value.length() > 4096) {
                    throw new IllegalArgumentException(
                        "Invalid environment variable."
                    );
                }
            });

            ContainerImage image = imageSource.pull(imageReference);

            String id = UUID.randomUUID().toString();

            host.allocate(id, limits);

            try {
                Container container = new Container(
                    id,
                    name,
                    image,
                    limits,
                    restartPolicy,
                    environment
                );

                containers.put(id, container);
                names.add(name);

                audit.record("CREATED", id);

                return container;

            } catch (RuntimeException exception) {
                host.release(id);
                throw exception;
            }
        }

        private Container get(String id) {
            Container container = containers.get(id);

            if (container == null) {
                throw new ContainerException("Container not found.");
            }

            return container;
        }

        synchronized void start(String id) {
            Container container = get(id);

            if (container.state != ContainerState.CREATED &&
                container.state != ContainerState.STOPPED) {
                throw new ContainerException("Invalid start transition.");
            }

            container.state = ContainerState.RUNNING;
            container.startedAt = Instant.now();
            container.health = HealthStatus.UNKNOWN;

            audit.record("STARTED", id);
        }

        synchronized void pause(String id) {
            Container container = get(id);

            if (container.state != ContainerState.RUNNING) {
                throw new ContainerException("Container is not running.");
            }

            container.state = ContainerState.PAUSED;
            audit.record("PAUSED", id);
        }

        synchronized void resume(String id) {
            Container container = get(id);

            if (container.state != ContainerState.PAUSED) {
                throw new ContainerException("Container is not paused.");
            }

            container.state = ContainerState.RUNNING;
            audit.record("RESUMED", id);
        }

        synchronized void stop(String id, int exitCode) {
            Container container = get(id);

            if (container.state != ContainerState.RUNNING &&
                container.state != ContainerState.PAUSED) {
                throw new ContainerException("Invalid stop transition.");
            }

            container.state = ContainerState.STOPPED;
            container.exitCode = exitCode;

            audit.record("STOPPED", id);
        }

        synchronized void updateUsage(
            String id,
            ResourceUsage usage
        ) {
            Container container = get(id);

            if (container.state != ContainerState.RUNNING) {
                throw new ContainerException("Container is not running.");
            }

            if (usage.cpuCores() > container.limits.cpuCores() ||
                usage.memoryMB() > container.limits.memoryMB() ||
                usage.diskMB() > container.limits.diskMB() ||
                usage.processCount() > container.limits.processLimit()) {

                container.health = HealthStatus.UNHEALTHY;

                audit.record("RESOURCE_LIMIT_EXCEEDED", id);

                throw new ContainerException(
                    "Container exceeded resource limits."
                );
            }

            container.usage = usage;
            container.health = HealthStatus.HEALTHY;

            audit.record("HEALTHY", id);
        }

        synchronized void fail(String id, int exitCode) {
            Container container = get(id);

            if (container.state != ContainerState.RUNNING) {
                throw new ContainerException("Container is not running.");
            }

            container.state = ContainerState.FAILED;
            container.health = HealthStatus.UNHEALTHY;
            container.exitCode = exitCode;

            audit.record("FAILED", id);

            if (policy.mayRestart(container, exitCode)) {
                container.restartCount++;
                container.state = ContainerState.RUNNING;
                container.startedAt = Instant.now();
                container.health = HealthStatus.UNKNOWN;

                audit.record("RESTARTED", id);
            }
        }

        synchronized void remove(String id) {
            Container container = get(id);

            if (container.state == ContainerState.RUNNING ||
                container.state == ContainerState.PAUSED) {
                throw new ContainerException("Stop before removal.");
            }

            container.state = ContainerState.REMOVED;

            names.remove(container.name);
            containers.remove(id);

            host.release(id);

            audit.record("REMOVED", id);
        }

        synchronized List<Map<String, Object>> inventory() {
            return containers.values().stream()
                .map(container -> {
                    Map<String, Object> row = new HashMap<>();

                    row.put("id", container.id);
                    row.put("name", container.name);
                    row.put("image", container.image.reference());
                    row.put("state", container.state);
                    row.put("health", container.health);
                    row.put("restarts", container.restartCount);
                    row.put("memoryMB", container.usage.memoryMB());

                    return Map.copyOf(row);
                })
                .collect(Collectors.toList());
        }
    }

    private static void runTests() {
        ResourceLimits hostLimits =
            new ResourceLimits(4, 4096, 8192, 1000);

        ImageRegistry registry = new ImageRegistry();

        registry.push(new ContainerImage(
            "test/service",
            "1.0",
            "service",
            List.of(new ImageLayer("base", "linux")),
            Set.of(8080)
        ));

        HostResourceManager host =
            new HostResourceManager(hostLimits);

        AuditService audit = new AuditService();

        ContainerRuntime runtime = new ContainerRuntime(
            registry,
            host,
            new DeploymentPolicy(3),
            audit
        );

        Container container = runtime.create(
            "test/service:1.0",
            "test-service",
            new ResourceLimits(1, 512, 1024, 64),
            RestartPolicy.ON_FAILURE,
            Map.of("APP_ENV", "test")
        );

        runtime.start(container.id());

        try {
            runtime.start(container.id());
            throw new AssertionError("Invalid transition accepted.");
        } catch (ContainerException expected) {
            // Expected state validation.
        }

        runtime.updateUsage(
            container.id(),
            new ResourceUsage(0.5, 128, 200, 5)
        );

        runtime.fail(container.id(), 1);

        if (container.restartCount() != 1) {
            throw new AssertionError("Restart policy failed.");
        }

        runtime.stop(container.id(), 0);
        runtime.remove(container.id());

        if (host.allocationCount() != 0) {
            throw new AssertionError("Resource allocation leaked.");
        }

        System.out.println("Java 17 tests passed.");
    }

    public static void main(String[] args) {
        try {
            runTests();

            ImageRegistry registry = new ImageRegistry();

            registry.push(new ContainerImage(
                "enterprise/inventory",
                "2.0",
                "java -jar inventory.jar",
                List.of(
                    new ImageLayer("base", "linux-rootfs"),
                    new ImageLayer("runtime", "java-17"),
                    new ImageLayer("application", "inventory-service")
                ),
                Set.of(8080, 9090)
            ));

            HostResourceManager host = new HostResourceManager(
                new ResourceLimits(8, 8192, 50000, 10000)
            );

            AuditService audit = new AuditService();

            ContainerRuntime runtime = new ContainerRuntime(
                registry,
                host,
                new DeploymentPolicy(3),
                audit
            );

            Container api = runtime.create(
                "enterprise/inventory:2.0",
                "inventory-api",
                new ResourceLimits(2, 1024, 2048, 100),
                RestartPolicy.ON_FAILURE,
                Map.of(
                    "APP_ENV", "production",
                    "LOG_LEVEL", "INFO"
                )
            );

            runtime.start(api.id());

            runtime.updateUsage(
                api.id(),
                new ResourceUsage(0.75, 320, 500, 12)
            );

            System.out.println("\nContainer inventory:");

            runtime.inventory().forEach(System.out::println);

            runtime.fail(api.id(), 137);

            System.out.println("\nAfter automatic restart:");

            runtime.inventory().forEach(System.out::println);

            runtime.pause(api.id());
            runtime.resume(api.id());
            runtime.stop(api.id(), 0);
            runtime.remove(api.id());

            System.out.println("\nAudit events:");

            audit.getEvents().forEach(System.out::println);

            System.out.println(
                "\nRemaining host allocations: " +
                host.allocationCount()
            );

        } catch (Exception exception) {
            System.err.println(
                "Container management error: " +
                exception.getMessage()
            );

            System.exit(1);
        }
    }
}
