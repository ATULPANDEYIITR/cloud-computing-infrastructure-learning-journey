import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

/*
 * Docker Compose Enterprise Deployment Management
 *
 * Java 17 implementation:
 * - Immutable configuration records
 * - Service lifecycle state machine
 * - Dependency policy evaluation
 * - Environment validation
 * - Network and volume governance
 * - Resource capacity validation
 * - Deployment audit events
 * - Failure recovery
 *
 * Compile:
 * javac DockerComposeEnterprise.java
 *
 * Run:
 * java DockerComposeEnterprise
 */

public class DockerComposeEnterprise {

    enum State {
        CREATED,
        STARTING,
        RUNNING,
        HEALTHY,
        UNHEALTHY,
        FAILED,
        STOPPED
    }

    enum Condition {
        SERVICE_STARTED,
        SERVICE_HEALTHY,
        SERVICE_COMPLETED_SUCCESSFULLY
    }

    enum RestartPolicy {
        NO,
        ALWAYS,
        UNLESS_STOPPED,
        ON_FAILURE
    }

    enum VolumeType {
        PERSISTENT,
        TEMPORARY
    }

    static class DeploymentException extends RuntimeException {
        DeploymentException(String message) {
            super(message);
        }
    }

    static class ConfigurationException extends DeploymentException {
        ConfigurationException(String message) {
            super(message);
        }
    }

    static class DependencyException extends DeploymentException {
        DependencyException(String message) {
            super(message);
        }
    }

    record Dependency(
        String service,
        Condition condition
    ) {
        Dependency {
            Objects.requireNonNull(service);
            Objects.requireNonNull(condition);
        }
    }

    record PortMapping(
        int hostPort,
        int containerPort
    ) {
        PortMapping {
            if (hostPort < 1 || hostPort > 65535 ||
                containerPort < 1 || containerPort > 65535) {
                throw new ConfigurationException(
                    "Invalid port mapping."
                );
            }
        }
    }

    record Network(
        String name,
        boolean internal
    ) {
        Network {
            if (name == null || name.isBlank()) {
                throw new ConfigurationException(
                    "Network name is required."
                );
            }
        }
    }

    record Volume(
        String name,
        VolumeType type,
        boolean readOnly
    ) {
        Volume {
            if (name == null || name.isBlank()) {
                throw new ConfigurationException(
                    "Volume name is required."
                );
            }

            Objects.requireNonNull(type);
        }
    }

    record Environment(
        Map<String, String> variables,
        Set<String> required
    ) {
        Environment {
            variables = Map.copyOf(variables);
            required = Set.copyOf(required);

            for (String key : required) {
                if (variables.get(key) == null ||
                    variables.get(key).isBlank()) {
                    throw new ConfigurationException(
                        "Missing required environment variable: " + key
                    );
                }
            }

            for (Map.Entry<String, String> entry :
                 variables.entrySet()) {

                if (!entry.getKey().matches(
                    "[A-Za-z_][A-Za-z0-9_]*"
                )) {
                    throw new ConfigurationException(
                        "Invalid environment variable: " +
                        entry.getKey()
                    );
                }

                if (entry.getValue() == null ||
                    entry.getValue().contains("\0")) {
                    throw new ConfigurationException(
                        "Invalid environment value."
                    );
                }
            }
        }
    }

    record ServiceDefinition(
        String name,
        String image,
        List<Dependency> dependencies,
        Set<String> networks,
        List<Volume> volumes,
        List<PortMapping> ports,
        Environment environment,
        int memoryMB,
        double cpu,
        boolean healthcheck,
        RestartPolicy restartPolicy
    ) {
        ServiceDefinition {
            if (name == null ||
                !name.matches("[a-zA-Z0-9][a-zA-Z0-9_-]*")) {
                throw new ConfigurationException(
                    "Invalid service name."
                );
            }

            if (image == null || image.isBlank() ||
                image.chars().anyMatch(Character::isWhitespace)) {
                throw new ConfigurationException(
                    "Invalid image reference."
                );
            }

            dependencies = List.copyOf(dependencies);
            networks = Set.copyOf(networks);
            volumes = List.copyOf(volumes);
            ports = List.copyOf(ports);

            Objects.requireNonNull(environment);
            Objects.requireNonNull(restartPolicy);

            if (memoryMB <= 0 ||
                !Double.isFinite(cpu) ||
                cpu <= 0) {
                throw new ConfigurationException(
                    "Invalid resource configuration."
                );
            }
        }
    }

    record AuditEvent(
        String id,
        Instant timestamp,
        String service,
        String action,
        String details
    ) {}

    interface HealthPolicy {
        boolean evaluate(ServiceDefinition service);
    }

    static class DefaultHealthPolicy implements HealthPolicy {
        private final Set<String> failedServices;

        DefaultHealthPolicy(Set<String> failedServices) {
            this.failedServices = failedServices;
        }

        @Override
        public boolean evaluate(ServiceDefinition service) {
            return !failedServices.contains(service.name());
        }
    }

    static class ServiceRuntime {
        private final ServiceDefinition definition;
        private State state = State.CREATED;
        private final AtomicInteger restartCount =
            new AtomicInteger();

        ServiceRuntime(ServiceDefinition definition) {
            this.definition = definition;
        }

        ServiceDefinition definition() {
            return definition;
        }

        State state() {
            return state;
        }

        void transition(State next) {
            boolean valid = switch (state) {
                case CREATED -> next == State.STARTING ||
                                next == State.STOPPED;

                case STARTING -> next == State.RUNNING ||
                                 next == State.FAILED;

                case RUNNING -> next == State.HEALTHY ||
                                next == State.UNHEALTHY ||
                                next == State.FAILED ||
                                next == State.STOPPED;

                case HEALTHY -> next == State.UNHEALTHY ||
                                next == State.FAILED ||
                                next == State.STOPPED;

                case UNHEALTHY -> next == State.HEALTHY ||
                                  next == State.FAILED ||
                                  next == State.STOPPED;

                case FAILED -> next == State.CREATED ||
                               next == State.STOPPED;

                case STOPPED -> next == State.CREATED;
            };

            if (!valid) {
                throw new DeploymentException(
                    "Invalid state transition for " +
                    definition.name() + ": " +
                    state + " -> " + next
                );
            }

            state = next;
        }

        int incrementRestartCount() {
            return restartCount.incrementAndGet();
        }
    }

    static class DeploymentService {
        private final Map<String, ServiceRuntime> services =
            new LinkedHashMap<>();

        private final Map<String, Network> networks =
            new LinkedHashMap<>();

        private final Map<String, Volume> volumes =
            new LinkedHashMap<>();

        private final List<AuditEvent> events =
            new ArrayList<>();

        private final HealthPolicy healthPolicy;

        private final int availableMemoryMB;
        private final double availableCPU;

        DeploymentService(
            List<ServiceDefinition> definitions,
            List<Network> networkDefinitions,
            List<Volume> volumeDefinitions,
            HealthPolicy healthPolicy,
            int availableMemoryMB,
            double availableCPU
        ) {
            this.healthPolicy = healthPolicy;
            this.availableMemoryMB = availableMemoryMB;
            this.availableCPU = availableCPU;

            if (availableMemoryMB <= 0 ||
                !Double.isFinite(availableCPU) ||
                availableCPU <= 0) {
                throw new ConfigurationException(
                    "Invalid host capacity."
                );
            }

            networkDefinitions.forEach(network ->
                networks.put(network.name(), network)
            );

            volumeDefinitions.forEach(volume ->
                volumes.put(volume.name(), volume)
            );

            for (ServiceDefinition definition : definitions) {
                if (services.putIfAbsent(
                    definition.name(),
                    new ServiceRuntime(definition)
                ) != null) {
                    throw new ConfigurationException(
                        "Duplicate service: " + definition.name()
                    );
                }
            }

            validateConfiguration();
        }

        private void audit(
            String service,
            String action,
            String details
        ) {
            events.add(new AuditEvent(
                UUID.randomUUID().toString(),
                Instant.now(),
                service,
                action,
                details
            ));
        }

        private void validateConfiguration() {
            if (services.isEmpty()) {
                throw new ConfigurationException(
                    "No services configured."
                );
            }

            Set<Integer> ports = new HashSet<>();

            for (ServiceRuntime runtime : services.values()) {
                ServiceDefinition definition =
                    runtime.definition();

                for (String network : definition.networks()) {
                    if (!networks.containsKey(network)) {
                        throw new ConfigurationException(
                            definition.name() +
                            " references unknown network " +
                            network
                        );
                    }
                }

                for (Volume volume : definition.volumes()) {
                    if (!volumes.containsKey(volume.name())) {
                        throw new ConfigurationException(
                            definition.name() +
                            " references unknown volume " +
                            volume.name()
                        );
                    }
                }

                for (PortMapping port : definition.ports()) {
                    if (!ports.add(port.hostPort())) {
                        throw new ConfigurationException(
                            "Host port collision: " +
                            port.hostPort()
                        );
                    }
                }

                for (Dependency dependency :
                     definition.dependencies()) {

                    if (!services.containsKey(dependency.service())) {
                        throw new DependencyException(
                            "Unknown dependency: " +
                            dependency.service()
                        );
                    }

                    if (dependency.service().equals(
                        definition.name()
                    )) {
                        throw new DependencyException(
                            "Self-dependency detected."
                        );
                    }
                }
            }

            startupOrder();
            validateResources();
        }

        private void validateResources() {
            long requiredMemory = services.values()
                .stream()
                .mapToLong(s -> s.definition().memoryMB())
                .sum();

            double requiredCPU = services.values()
                .stream()
                .mapToDouble(s -> s.definition().cpu())
                .sum();

            if (requiredMemory > availableMemoryMB ||
                requiredCPU > availableCPU) {
                throw new ConfigurationException(
                    "Configured service limits exceed host capacity."
                );
            }
        }

        List<String> startupOrder() {
            Map<String, Integer> indegree = new HashMap<>();
            Map<String, List<String>> graph = new HashMap<>();

            services.keySet().forEach(name -> {
                indegree.put(name, 0);
                graph.put(name, new ArrayList<>());
            });

            for (ServiceRuntime runtime : services.values()) {
                String name = runtime.definition().name();

                for (Dependency dependency :
                     runtime.definition().dependencies()) {

                    graph.get(dependency.service()).add(name);

                    indegree.put(
                        name,
                        indegree.get(name) + 1
                    );
                }
            }

            List<String> ready = indegree.entrySet()
                .stream()
                .filter(entry -> entry.getValue() == 0)
                .map(Map.Entry::getKey)
                .sorted()
                .collect(Collectors.toCollection(ArrayList::new));

            List<String> order = new ArrayList<>();

            while (!ready.isEmpty()) {
                String current = ready.remove(0);
                order.add(current);

                for (String next : graph.get(current)) {
                    int degree = indegree.merge(
                        next, -1, Integer::sum
                    );

                    if (degree == 0) {
                        ready.add(next);
                        ready.sort(Comparator.naturalOrder());
                    }
                }
            }

            if (order.size() != services.size()) {
                throw new DependencyException(
                    "Circular dependency detected."
                );
            }

            return List.copyOf(order);
        }

        private boolean dependencySatisfied(
            Dependency dependency
        ) {
            State state = services.get(
                dependency.service()
            ).state();

            return switch (dependency.condition()) {
                case SERVICE_STARTED ->
                    state == State.RUNNING ||
                    state == State.HEALTHY;

                case SERVICE_HEALTHY ->
                    state == State.HEALTHY;

                case SERVICE_COMPLETED_SUCCESSFULLY ->
                    state == State.STOPPED;
            };
        }

        private void startService(String name) {
            ServiceRuntime runtime = services.get(name);

            if (runtime.state() == State.RUNNING ||
                runtime.state() == State.HEALTHY) {
                return;
            }

            for (Dependency dependency :
                 runtime.definition().dependencies()) {

                if (!dependencySatisfied(dependency)) {
                    throw new DependencyException(
                        name + " cannot start because " +
                        dependency.service() +
                        " has not satisfied " +
                        dependency.condition()
                    );
                }
            }

            runtime.transition(State.STARTING);

            audit(name, "STARTING", runtime.definition().image());

            runtime.transition(State.RUNNING);

            audit(name, "RUNNING", "Container started");

            if (runtime.definition().healthcheck()) {
                boolean healthy = healthPolicy.evaluate(
                    runtime.definition()
                );

                runtime.transition(
                    healthy ? State.HEALTHY : State.UNHEALTHY
                );

                audit(
                    name,
                    "HEALTHCHECK",
                    healthy ? "healthy" : "unhealthy"
                );
            }
        }

        void deploy() {
            for (String name : startupOrder()) {
                startService(name);
            }
        }

        void failService(String name) {
            ServiceRuntime runtime = requireService(name);

            if (runtime.state() != State.RUNNING &&
                runtime.state() != State.HEALTHY &&
                runtime.state() != State.UNHEALTHY) {
                throw new DeploymentException(
                    "Service cannot fail from current state."
                );
            }

            runtime.transition(State.FAILED);
            audit(name, "FAILED", "Service failure recorded");
        }

        void restartService(String name) {
            ServiceRuntime runtime = requireService(name);

            RestartPolicy policy =
                runtime.definition().restartPolicy();

            if (policy == RestartPolicy.NO) {
                throw new DeploymentException(
                    "Restart is disabled."
                );
            }

            int attempt = runtime.incrementRestartCount();

            runtime.transition(State.CREATED);

            audit(
                name,
                "RESTART",
                "Attempt " + attempt
            );

            startService(name);
        }

        private ServiceRuntime requireService(String name) {
            ServiceRuntime runtime = services.get(name);

            if (runtime == null) {
                throw new DeploymentException(
                    "Unknown service: " + name
                );
            }

            return runtime;
        }

        List<String> networkPeers(String name) {
            ServiceRuntime runtime = requireService(name);

            return services.values()
                .stream()
                .filter(other ->
                    !other.definition().name().equals(name)
                )
                .filter(other ->
                    !Collections.disjoint(
                        runtime.definition().networks(),
                        other.definition().networks()
                    )
                )
                .map(other -> other.definition().name())
                .sorted()
                .toList();
        }

        void shutdown() {
            List<String> order = new ArrayList<>(startupOrder());
            Collections.reverse(order);

            for (String name : order) {
                ServiceRuntime runtime = services.get(name);

                if (runtime.state() != State.STOPPED) {
                    runtime.transition(State.STOPPED);
                    audit(name, "STOPPED", "Graceful shutdown");
                }
            }
        }

        void printReport() {
            System.out.println("\nDEPLOYMENT REPORT");

            for (ServiceRuntime runtime : services.values()) {
                ServiceDefinition definition =
                    runtime.definition();

                System.out.printf(
                    "%-12s %-20s %-12s Memory=%dMB CPU=%.1f%n",
                    definition.name(),
                    definition.image(),
                    runtime.state(),
                    definition.memoryMB(),
                    definition.cpu()
                );
            }

            System.out.println(
                "\nAUDIT EVENTS: " + events.size()
            );

            events.forEach(event ->
                System.out.printf(
                    "%s | %s | %s%n",
                    event.timestamp(),
                    event.service(),
                    event.action()
                )
            );
        }
    }

    public static void main(String[] args) {
        try {
            Environment databaseEnvironment = new Environment(
                Map.of(
                    "POSTGRES_DB", "application",
                    "POSTGRES_USER", "appuser",
                    "POSTGRES_PASSWORD", "development-secret"
                ),
                Set.of(
                    "POSTGRES_DB",
                    "POSTGRES_USER",
                    "POSTGRES_PASSWORD"
                )
            );

            Environment apiEnvironment = new Environment(
                Map.of(
                    "DATABASE_HOST", "database",
                    "CACHE_HOST", "cache"
                ),
                Set.of("DATABASE_HOST")
            );

            Environment webEnvironment = new Environment(
                Map.of(
                    "API_URL", "http://api:8080"
                ),
                Set.of("API_URL")
            );

            List<Network> networks = List.of(
                new Network("frontend", false),
                new Network("backend", true)
            );

            List<Volume> volumes = List.of(
                new Volume(
                    "postgres_data",
                    VolumeType.PERSISTENT,
                    false
                ),
                new Volume(
                    "cache_data",
                    VolumeType.PERSISTENT,
                    false
                )
            );

            List<ServiceDefinition> definitions = List.of(
                new ServiceDefinition(
                    "database",
                    "postgres:18",
                    List.of(),
                    Set.of("backend"),
                    List.of(volumes.get(0)),
                    List.of(),
                    databaseEnvironment,
                    1024,
                    2.0,
                    true,
                    RestartPolicy.UNLESS_STOPPED
                ),

                new ServiceDefinition(
                    "cache",
                    "redis:7-alpine",
                    List.of(),
                    Set.of("backend"),
                    List.of(volumes.get(1)),
                    List.of(),
                    new Environment(Map.of(), Set.of()),
                    256,
                    0.5,
                    true,
                    RestartPolicy.ALWAYS
                ),

                new ServiceDefinition(
                    "api",
                    "example/api:1.0",
                    List.of(
                        new Dependency(
                            "database",
                            Condition.SERVICE_HEALTHY
                        ),
                        new Dependency(
                            "cache",
                            Condition.SERVICE_STARTED
                        )
                    ),
                    Set.of("frontend", "backend"),
                    List.of(),
                    List.of(new PortMapping(8080, 8080)),
                    apiEnvironment,
                    512,
                    1.5,
                    true,
                    RestartPolicy.ON_FAILURE
                ),

                new ServiceDefinition(
                    "web",
                    "example/web:1.0",
                    List.of(
                        new Dependency(
                            "api",
                            Condition.SERVICE_HEALTHY
                        )
                    ),
                    Set.of("frontend"),
                    List.of(),
                    List.of(new PortMapping(3000, 3000)),
                    webEnvironment,
                    256,
                    1.0,
                    false,
                    RestartPolicy.NO
                )
            );

            DeploymentService deployment =
                new DeploymentService(
                    definitions,
                    networks,
                    volumes,
                    new DefaultHealthPolicy(Set.of()),
                    4096,
                    8.0
                );

            System.out.println("STARTUP ORDER");
            deployment.startupOrder().forEach(System.out::println);

            System.out.println("\nDEPLOYMENT");
            deployment.deploy();

            System.out.println(
                "\nDATABASE NETWORK PEERS: " +
                deployment.networkPeers("database")
            );

            System.out.println("\nFAILURE RECOVERY");
            deployment.failService("api");
            deployment.restartService("api");

            deployment.printReport();

            System.out.println("\nSHUTDOWN");
            deployment.shutdown();

        } catch (DeploymentException exception) {
            System.err.println(
                "DEPLOYMENT FAILED: " + exception.getMessage()
            );

            System.exit(1);
        }
    }
}
