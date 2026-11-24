import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

/**
 * Enterprise Docker deployment governance model.
 *
 * Models:
 * - Multi-service application architecture
 * - Container configuration validation
 * - Dependency management
 * - Health and readiness
 * - Persistent storage
 * - Network isolation
 * - Deployment state transitions
 * - Restart policies
 */
public class DockerGovernance {

    enum ServiceType {
        FRONTEND,
        BACKEND,
        DATABASE
    }

    enum DeploymentState {
        CREATED,
        STARTING,
        HEALTHY,
        UNHEALTHY,
        FAILED,
        STOPPED
    }

    enum RestartPolicy {
        NO,
        ALWAYS,
        UNLESS_STOPPED,
        ON_FAILURE
    }

    record ResourceLimits(
        long memoryMb,
        double cpuCores
    ) {
        ResourceLimits {
            if (memoryMb <= 0 || cpuCores <= 0) {
                throw new IllegalArgumentException(
                    "Resource limits must be positive."
                );
            }
        }
    }

    record NetworkConfiguration(
        Set<String> networks,
        boolean publicExposure
    ) {
        NetworkConfiguration {
            networks = Set.copyOf(networks);

            if (networks.isEmpty()) {
                throw new IllegalArgumentException(
                    "Every service requires a network."
                );
            }
        }
    }

    record ServiceDefinition(
        String name,
        ServiceType type,
        Set<String> dependencies,
        NetworkConfiguration network,
        ResourceLimits resources,
        RestartPolicy restartPolicy,
        boolean persistentStorage,
        boolean healthcheckEnabled
    ) {
        ServiceDefinition {
            Objects.requireNonNull(name);
            Objects.requireNonNull(type);
            Objects.requireNonNull(network);
            Objects.requireNonNull(resources);
            Objects.requireNonNull(restartPolicy);

            dependencies = Set.copyOf(dependencies);

            if (!name.matches("[a-z][a-z0-9-]{1,40}")) {
                throw new IllegalArgumentException(
                    "Invalid service name: " + name
                );
            }

            if (dependencies.contains(name)) {
                throw new IllegalArgumentException(
                    "A service cannot depend on itself."
                );
            }
        }
    }

    static class GovernanceException extends RuntimeException {
        GovernanceException(String message) {
            super(message);
        }
    }

    static class ServiceRuntime {
        private final ServiceDefinition definition;
        private DeploymentState state = DeploymentState.CREATED;
        private int restartCount;
        private Instant lastTransition;

        ServiceRuntime(ServiceDefinition definition) {
            this.definition = definition;
            this.lastTransition = Instant.now();
        }

        synchronized void transition(DeploymentState next) {
            boolean valid = switch (state) {
                case CREATED ->
                    next == DeploymentState.STARTING ||
                    next == DeploymentState.STOPPED;
                case STARTING ->
                    next == DeploymentState.HEALTHY ||
                    next == DeploymentState.UNHEALTHY ||
                    next == DeploymentState.FAILED;
                case HEALTHY ->
                    next == DeploymentState.UNHEALTHY ||
                    next == DeploymentState.STOPPED;
                case UNHEALTHY ->
                    next == DeploymentState.STARTING ||
                    next == DeploymentState.FAILED ||
                    next == DeploymentState.STOPPED;
                case FAILED ->
                    next == DeploymentState.STARTING ||
                    next == DeploymentState.STOPPED;
                case STOPPED ->
                    next == DeploymentState.STARTING;
            };

            if (!valid) {
                throw new GovernanceException(
                    "Invalid transition: " + state + " -> " + next
                );
            }

            state = next;
            lastTransition = Instant.now();

            if (next == DeploymentState.STARTING &&
                restartCount >= 0 &&
                state != DeploymentState.CREATED) {
                restartCount++;
            }
        }

        synchronized void restart() {
            if (definition.restartPolicy() == RestartPolicy.NO) {
                throw new GovernanceException(
                    "Restart is prohibited by policy."
                );
            }

            if (state != DeploymentState.UNHEALTHY &&
                state != DeploymentState.FAILED) {
                throw new GovernanceException(
                    "Only failed or unhealthy services can restart."
                );
            }

            transition(DeploymentState.STARTING);
        }

        DeploymentState state() {
            return state;
        }

        ServiceDefinition definition() {
            return definition;
        }

        int restartCount() {
            return restartCount;
        }
    }

    static class DeploymentService {
        private final Map<String, ServiceRuntime> services =
            new ConcurrentHashMap<>();

        private final Map<String, Set<String>> networkMembership =
            new HashMap<>();

        void register(ServiceDefinition definition) {
            if (services.containsKey(definition.name())) {
                throw new GovernanceException(
                    "Duplicate service: " + definition.name()
                );
            }

            services.put(
                definition.name(),
                new ServiceRuntime(definition)
            );

            for (String network : definition.network().networks()) {
                networkMembership
                    .computeIfAbsent(network, key -> new HashSet<>())
                    .add(definition.name());
            }
        }

        List<String> validateAndOrder() {
            validateRequiredServices();
            validateDependencies();
            validateNetworkBoundaries();

            Map<String, Integer> colors = new HashMap<>();
            List<String> order = new ArrayList<>();

            for (String service : services.keySet()) {
                visit(service, colors, order);
            }

            return List.copyOf(order);
        }

        private void validateRequiredServices() {
            Set<ServiceType> types = services.values()
                .stream()
                .map(runtime -> runtime.definition().type())
                .collect(Collectors.toSet());

            if (!types.containsAll(Set.of(
                ServiceType.FRONTEND,
                ServiceType.BACKEND,
                ServiceType.DATABASE
            ))) {
                throw new GovernanceException(
                    "Frontend, backend and database are mandatory."
                );
            }
        }

        private void validateDependencies() {
            for (ServiceRuntime runtime : services.values()) {
                ServiceDefinition definition = runtime.definition();

                for (String dependency : definition.dependencies()) {
                    if (!services.containsKey(dependency)) {
                        throw new GovernanceException(
                            definition.name() +
                            " has missing dependency " + dependency
                        );
                    }
                }

                if (definition.type() == ServiceType.DATABASE &&
                    !definition.persistentStorage()) {
                    throw new GovernanceException(
                        "Database persistence is mandatory."
                    );
                }
            }
        }

        private void validateNetworkBoundaries() {
            ServiceDefinition frontend =
                findByType(ServiceType.FRONTEND);

            ServiceDefinition backend =
                findByType(ServiceType.BACKEND);

            ServiceDefinition database =
                findByType(ServiceType.DATABASE);

            if (frontend.network().networks()
                .stream()
                .noneMatch(backend.network().networks()::contains)) {
                throw new GovernanceException(
                    "Frontend and backend require a shared network."
                );
            }

            if (backend.network().networks()
                .stream()
                .noneMatch(database.network().networks()::contains)) {
                throw new GovernanceException(
                    "Backend and database require a shared network."
                );
            }

            if (database.network().publicExposure()) {
                throw new GovernanceException(
                    "Database must not be publicly exposed."
                );
            }
        }

        private ServiceDefinition findByType(ServiceType type) {
            return services.values()
                .stream()
                .map(ServiceRuntime::definition)
                .filter(definition -> definition.type() == type)
                .findFirst()
                .orElseThrow(() ->
                    new GovernanceException("Missing service type: " + type)
                );
        }

        private void visit(
            String name,
            Map<String, Integer> colors,
            List<String> order
        ) {
            int color = colors.getOrDefault(name, 0);

            if (color == 1) {
                throw new GovernanceException(
                    "Circular dependency involving " + name
                );
            }

            if (color == 2) {
                return;
            }

            colors.put(name, 1);

            for (String dependency :
                services.get(name).definition().dependencies()) {
                visit(dependency, colors, order);
            }

            colors.put(name, 2);
            order.add(name);
        }

        void deploy(Map<String, Boolean> healthResults) {
            List<String> order = validateAndOrder();

            for (String name : order) {
                ServiceRuntime runtime = services.get(name);

                for (String dependency :
                    runtime.definition().dependencies()) {
                    if (services.get(dependency).state()
                        != DeploymentState.HEALTHY) {
                        throw new GovernanceException(
                            "Dependency not healthy: " + dependency
                        );
                    }
                }

                runtime.transition(DeploymentState.STARTING);

                boolean healthy = healthResults.getOrDefault(name, true);

                if (!healthy && runtime.definition().healthcheckEnabled()) {
                    runtime.transition(DeploymentState.UNHEALTHY);
                    throw new GovernanceException(
                        "Healthcheck failed: " + name
                    );
                }

                runtime.transition(DeploymentState.HEALTHY);

                System.out.println(name + " is healthy.");
            }
        }

        void report() {
            System.out.println("\nENTERPRISE DEPLOYMENT REPORT");

            services.forEach((name, runtime) -> {
                System.out.printf(
                    "%s | %s | restart=%d | storage=%s%n",
                    name,
                    runtime.state(),
                    runtime.restartCount(),
                    runtime.definition().persistentStorage()
                );
            });
        }

        boolean isReady() {
            return !services.isEmpty() &&
                services.values().stream().allMatch(
                    runtime -> runtime.state() == DeploymentState.HEALTHY
                );
        }
    }

    private static DeploymentService createDeployment() {
        DeploymentService deployment = new DeploymentService();

        deployment.register(new ServiceDefinition(
            "db",
            ServiceType.DATABASE,
            Set.of(),
            new NetworkConfiguration(
                Set.of("backend-network"),
                false
            ),
            new ResourceLimits(512, 0.5),
            RestartPolicy.UNLESS_STOPPED,
            true,
            true
        ));

        deployment.register(new ServiceDefinition(
            "backend",
            ServiceType.BACKEND,
            Set.of("db"),
            new NetworkConfiguration(
                Set.of("backend-network", "frontend-network"),
                false
            ),
            new ResourceLimits(768, 1.0),
            RestartPolicy.ON_FAILURE,
            false,
            true
        ));

        deployment.register(new ServiceDefinition(
            "frontend",
            ServiceType.FRONTEND,
            Set.of("backend"),
            new NetworkConfiguration(
                Set.of("frontend-network"),
                true
            ),
            new ResourceLimits(256, 0.5),
            RestartPolicy.UNLESS_STOPPED,
            false,
            true
        ));

        return deployment;
    }

    public static void main(String[] args) {
        DeploymentService deployment = createDeployment();

        try {
            List<String> order = deployment.validateAndOrder();

            System.out.println("Startup order: " + order);

            deployment.deploy(Map.of(
                "db", true,
                "backend", true,
                "frontend", true
            ));

            deployment.report();

            System.out.println(
                "Application ready: " + deployment.isReady()
            );

        } catch (GovernanceException exception) {
            System.err.println(
                "Deployment rejected: " + exception.getMessage()
            );

            deployment.report();
            System.exitCode = 1;
        }
    }
}
