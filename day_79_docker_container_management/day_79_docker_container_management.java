import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;

/**
 * Enterprise-oriented Docker container management model.
 *
 * Java 17.
 *
 * This implementation models container management operations.
 * It does not create actual operating-system containers.
 */
public class DockerContainerManager {

    enum ContainerState {
        CREATED,
        RUNNING,
        PAUSED,
        STOPPED,
        EXITED,
        REMOVING
    }

    enum RestartPolicy {
        NO,
        ALWAYS,
        ON_FAILURE,
        UNLESS_STOPPED
    }

    enum LogLevel {
        INFO,
        WARN,
        ERROR
    }

    static class ContainerException extends RuntimeException {
        ContainerException(String message) {
            super(message);
        }
    }

    static class ValidationException extends ContainerException {
        ValidationException(String message) {
            super(message);
        }
    }

    static class LifecycleException extends ContainerException {
        LifecycleException(String message) {
            super(message);
        }
    }

    static class ResourceNotFoundException extends ContainerException {
        ResourceNotFoundException(String message) {
            super(message);
        }
    }

    record LogEntry(
        Instant timestamp,
        LogLevel level,
        String message
    ) {}

    record ResourceLimits(
        int memoryMB,
        double cpuLimit
    ) {
        ResourceLimits {
            if (memoryMB < 16) {
                throw new ValidationException(
                    "Memory must be at least 16 MB."
                );
            }

            if (
                !Double.isFinite(cpuLimit) ||
                cpuLimit < 0.1 ||
                cpuLimit > 64
            ) {
                throw new ValidationException("Invalid CPU limit.");
            }
        }
    }

    record ContainerConfiguration(
        String image,
        List<String> command,
        Map<String, String> environment,
        Map<String, String> labels,
        ResourceLimits resources,
        RestartPolicy restartPolicy
    ) {
        private static final Pattern IMAGE_PATTERN =
            Pattern.compile("[A-Za-z0-9._/:@-]+");

        private static final Pattern ENV_PATTERN =
            Pattern.compile("[A-Za-z_][A-Za-z0-9_]*");

        ContainerConfiguration {
            if (
                image == null ||
                !IMAGE_PATTERN.matcher(image).matches()
            ) {
                throw new ValidationException("Invalid image reference.");
            }

            Objects.requireNonNull(resources);
            Objects.requireNonNull(restartPolicy);

            command = List.copyOf(
                command == null ? List.of() : command
            );

            Map<String, String> safeEnvironment = new HashMap<>();

            if (environment != null) {
                environment.forEach((key, value) -> {
                    if (
                        key == null ||
                        !ENV_PATTERN.matcher(key).matches() ||
                        value == null ||
                        value.indexOf('\0') >= 0
                    ) {
                        throw new ValidationException(
                            "Invalid environment configuration."
                        );
                    }

                    safeEnvironment.put(key, value);
                });
            }

            environment = Collections.unmodifiableMap(safeEnvironment);

            labels = Collections.unmodifiableMap(
                new HashMap<>(labels == null ? Map.of() : labels)
            );
        }
    }

    static class Container {
        private final String id;
        private final String name;
        private final ContainerConfiguration configuration;
        private final Instant createdAt;

        private final List<LogEntry> logs = new ArrayList<>();

        private ContainerState state = ContainerState.CREATED;
        private Instant startedAt;
        private Instant finishedAt;
        private Integer exitCode;
        private int restartCount;

        Container(
            String name,
            ContainerConfiguration configuration
        ) {
            this.id = UUID.randomUUID()
                .toString()
                .replace("-", "")
                .substring(0, 12);

            this.name = name;
            this.configuration = configuration;
            this.createdAt = Instant.now();

            log(LogLevel.INFO, "Container created.");
        }

        void log(LogLevel level, String message) {
            logs.add(new LogEntry(
                Instant.now(),
                level,
                message
            ));
        }

        public String id() {
            return id;
        }

        public String name() {
            return name;
        }

        public ContainerState state() {
            return state;
        }

        public List<LogEntry> logs() {
            return List.copyOf(logs);
        }
    }

    interface LifecycleObserver {
        void onStateChanged(
            String containerName,
            ContainerState previous,
            ContainerState current
        );
    }

    record Inspection(
        String id,
        String name,
        String image,
        ContainerState state,
        Instant createdAt,
        Instant startedAt,
        Instant finishedAt,
        Integer exitCode,
        int restartCount,
        Map<String, String> environment,
        ResourceLimits resources,
        RestartPolicy restartPolicy,
        Map<String, String> labels
    ) {}

    record CommandResult(
        List<String> command,
        String output,
        int exitCode
    ) {}

    static class RestartPolicyEvaluator {

        boolean shouldRestart(
            Container container,
            boolean manuallyStopped
        ) {
            if (container.state != ContainerState.EXITED) {
                return false;
            }

            return switch (
                container.configuration.restartPolicy()
            ) {
                case NO -> false;
                case ALWAYS -> true;
                case UNLESS_STOPPED -> !manuallyStopped;
                case ON_FAILURE ->
                    container.exitCode != null &&
                    container.exitCode != 0;
            };
        }
    }

    static class ContainerManagementService {

        private final Map<String, Container> containers =
            new ConcurrentHashMap<>();

        private final Map<String, String> names =
            new ConcurrentHashMap<>();

        private final List<LifecycleObserver> observers =
            new ArrayList<>();

        private final RestartPolicyEvaluator policyEvaluator =
            new RestartPolicyEvaluator();

        private final int maximumContainers;

        private static final Set<String> ALLOWED_COMMANDS =
            Set.of("echo", "printenv", "hostname", "date");

        ContainerManagementService(int maximumContainers) {
            if (maximumContainers < 1) {
                throw new ValidationException(
                    "Container capacity must be positive."
                );
            }

            this.maximumContainers = maximumContainers;
        }

        synchronized void addObserver(LifecycleObserver observer) {
            observers.add(Objects.requireNonNull(observer));
        }

        private Container resolve(String identifier) {
            String id = names.getOrDefault(identifier, identifier);
            Container container = containers.get(id);

            if (container == null) {
                throw new ResourceNotFoundException(
                    "Container not found: " + identifier
                );
            }

            return container;
        }

        private void transition(
            Container container,
            Set<ContainerState> allowed,
            ContainerState next,
            String message
        ) {
            if (!allowed.contains(container.state)) {
                throw new LifecycleException(
                    "Invalid transition from " +
                    container.state + " to " + next
                );
            }

            ContainerState previous = container.state;
            container.state = next;

            container.log(LogLevel.INFO, message);

            for (LifecycleObserver observer : observers) {
                observer.onStateChanged(
                    container.name,
                    previous,
                    next
                );
            }
        }

        synchronized String create(
            String name,
            ContainerConfiguration configuration
        ) {
            Objects.requireNonNull(configuration);

            if (
                name == null ||
                !name.matches("[A-Za-z0-9][A-Za-z0-9_.-]{0,62}")
            ) {
                throw new ValidationException("Invalid container name.");
            }

            if (names.containsKey(name)) {
                throw new ValidationException(
                    "Container name already exists."
                );
            }

            if (containers.size() >= maximumContainers) {
                throw new ContainerException(
                    "Container capacity reached."
                );
            }

            Container container = new Container(
                name,
                configuration
            );

            containers.put(container.id, container);
            names.put(name, container.id);

            container.log(
                LogLevel.INFO,
                "Image: " + configuration.image()
            );

            return container.id;
        }

        synchronized Inspection start(String identifier) {
            Container container = resolve(identifier);

            transition(
                container,
                Set.of(
                    ContainerState.CREATED,
                    ContainerState.STOPPED,
                    ContainerState.EXITED
                ),
                ContainerState.RUNNING,
                "Container started."
            );

            container.startedAt = Instant.now();
            container.finishedAt = null;
            container.exitCode = null;

            return inspect(identifier);
        }

        synchronized Inspection pause(String identifier) {
            Container container = resolve(identifier);

            transition(
                container,
                Set.of(ContainerState.RUNNING),
                ContainerState.PAUSED,
                "Container paused."
            );

            return inspect(identifier);
        }

        synchronized Inspection unpause(String identifier) {
            Container container = resolve(identifier);

            transition(
                container,
                Set.of(ContainerState.PAUSED),
                ContainerState.RUNNING,
                "Container resumed."
            );

            return inspect(identifier);
        }

        synchronized Inspection stop(
            String identifier,
            int exitCode
        ) {
            Container container = resolve(identifier);

            if (exitCode < 0 || exitCode > 255) {
                throw new ValidationException("Invalid exit code.");
            }

            transition(
                container,
                Set.of(
                    ContainerState.RUNNING,
                    ContainerState.PAUSED
                ),
                ContainerState.STOPPED,
                "Container stopped."
            );

            container.exitCode = exitCode;
            container.finishedAt = Instant.now();

            return inspect(identifier);
        }

        synchronized Inspection simulateExit(
            String identifier,
            int exitCode
        ) {
            Container container = resolve(identifier);

            if (exitCode < 0 || exitCode > 255) {
                throw new ValidationException("Invalid exit code.");
            }

            transition(
                container,
                Set.of(ContainerState.RUNNING),
                ContainerState.EXITED,
                "Main process exited."
            );

            container.exitCode = exitCode;
            container.finishedAt = Instant.now();

            container.log(
                exitCode == 0 ? LogLevel.INFO : LogLevel.ERROR,
                "Process exit code: " + exitCode
            );

            return inspect(identifier);
        }

        synchronized Inspection restart(String identifier) {
            Container container = resolve(identifier);

            transition(
                container,
                Set.of(
                    ContainerState.RUNNING,
                    ContainerState.PAUSED,
                    ContainerState.STOPPED,
                    ContainerState.EXITED
                ),
                ContainerState.STOPPED,
                "Restart stopping phase."
            );

            transition(
                container,
                Set.of(ContainerState.STOPPED),
                ContainerState.RUNNING,
                "Container restarted."
            );

            container.restartCount++;
            container.startedAt = Instant.now();
            container.finishedAt = null;
            container.exitCode = null;

            return inspect(identifier);
        }

        synchronized boolean applyRestartPolicy(
            String identifier,
            boolean manuallyStopped
        ) {
            Container container = resolve(identifier);

            if (
                !policyEvaluator.shouldRestart(
                    container,
                    manuallyStopped
                )
            ) {
                return false;
            }

            restart(identifier);
            return true;
        }

        CommandResult execute(
            String identifier,
            List<String> command
        ) {
            Container container = resolve(identifier);

            if (container.state != ContainerState.RUNNING) {
                throw new LifecycleException(
                    "Container must be running."
                );
            }

            if (command == null || command.isEmpty()) {
                throw new ValidationException("Command is required.");
            }

            String executable = command.get(0);

            if (!ALLOWED_COMMANDS.contains(executable)) {
                throw new SecurityException(
                    "Command rejected: " + executable
                );
            }

            String output;

            switch (executable) {
                case "echo" ->
                    output = String.join(
                        " ",
                        command.subList(1, command.size())
                    );

                case "hostname" ->
                    output = container.name;

                case "date" ->
                    output = Instant.now().toString();

                case "printenv" -> {
                    Map<String, String> env =
                        container.configuration.environment();

                    if (command.size() > 1) {
                        output = env.getOrDefault(command.get(1), "");
                    } else {
                        output = env.entrySet()
                            .stream()
                            .sorted(Map.Entry.comparingByKey())
                            .map(entry ->
                                entry.getKey() + "=" + entry.getValue()
                            )
                            .reduce("", (a, b) ->
                                a.isEmpty() ? b : a + "\n" + b
                            );
                    }
                }

                default -> throw new SecurityException(
                    "Unsupported command."
                );
            }

            container.log(
                LogLevel.INFO,
                "Command executed: " + executable
            );

            return new CommandResult(
                List.copyOf(command),
                output,
                0
            );
        }

        Inspection inspect(String identifier) {
            Container container = resolve(identifier);

            return new Inspection(
                container.id,
                container.name,
                container.configuration.image(),
                container.state,
                container.createdAt,
                container.startedAt,
                container.finishedAt,
                container.exitCode,
                container.restartCount,
                container.configuration.environment(),
                container.configuration.resources(),
                container.configuration.restartPolicy(),
                container.configuration.labels()
            );
        }

        List<Inspection> list(
            Optional<ContainerState> stateFilter
        ) {
            return containers.values()
                .stream()
                .filter(container ->
                    stateFilter.isEmpty() ||
                    container.state == stateFilter.get()
                )
                .sorted(Comparator.comparing(c -> c.name))
                .map(container -> inspect(container.id))
                .toList();
        }

        List<LogEntry> logs(
            String identifier,
            int tail,
            Optional<LogLevel> level
        ) {
            Container container = resolve(identifier);

            if (tail < 0) {
                throw new ValidationException(
                    "Tail must not be negative."
                );
            }

            List<LogEntry> filtered = container.logs.stream()
                .filter(entry ->
                    level.isEmpty() ||
                    entry.level() == level.get()
                )
                .toList();

            int start = Math.max(0, filtered.size() - tail);

            return List.copyOf(filtered.subList(start, filtered.size()));
        }

        synchronized void remove(
            String identifier,
            boolean force
        ) {
            Container container = resolve(identifier);

            if (
                (
                    container.state == ContainerState.RUNNING ||
                    container.state == ContainerState.PAUSED
                ) &&
                !force
            ) {
                throw new LifecycleException(
                    "Stop container before removal or use force."
                );
            }

            container.state = ContainerState.REMOVING;

            containers.remove(container.id);
            names.remove(container.name);

            container.log(LogLevel.INFO, "Container removed.");
        }
    }

    public static void main(String[] args) {

        ContainerManagementService service =
            new ContainerManagementService(100);

        service.addObserver((name, previous, current) ->
            System.out.printf(
                "[EVENT] %s: %s -> %s%n",
                name,
                previous,
                current
            )
        );

        ContainerConfiguration configuration =
            new ContainerConfiguration(
                "postgres:18-alpine",
                List.of("postgres"),
                Map.of(
                    "POSTGRES_DB", "orders",
                    "POSTGRES_USER", "application",
                    "APP_ENV", "production"
                ),
                Map.of(
                    "team", "platform",
                    "service", "database"
                ),
                new ResourceLimits(2048, 2.0),
                RestartPolicy.ON_FAILURE
            );

        System.out.println("\n1. Container creation");

        String id = service.create(
            "orders-database",
            configuration
        );

        System.out.println("Container ID: " + id);

        System.out.println("\n2. Start and inspect");

        System.out.println(service.start(id));

        System.out.println("\n3. Environment and commands");

        System.out.println(
            service.execute(
                id,
                List.of("printenv", "APP_ENV")
            )
        );

        System.out.println(
            service.execute(
                id,
                List.of("hostname")
            )
        );

        System.out.println("\n4. Pause and resume");

        service.pause(id);
        service.unpause(id);

        System.out.println("\n5. Logs");

        service.logs(id, 5, Optional.empty())
            .forEach(System.out::println);

        System.out.println("\n6. Failure and restart policy");

        service.simulateExit(id, 1);

        boolean restarted = service.applyRestartPolicy(
            id,
            false
        );

        System.out.println("Restarted: " + restarted);
        System.out.println(service.inspect(id));

        System.out.println("\n7. Running container inventory");

        service.list(Optional.of(ContainerState.RUNNING))
            .forEach(System.out::println);

        System.out.println("\n8. Security failure");

        try {
            service.execute(
                id,
                List.of("rm", "-rf", "/")
            );
        } catch (SecurityException exception) {
            System.out.println(
                "Command rejected: " + exception.getMessage()
            );
        }

        System.out.println("\n9. Lifecycle validation");

        try {
            service.pause(id);
            service.pause(id);
        } catch (LifecycleException exception) {
            System.out.println(
                "Invalid operation: " + exception.getMessage()
            );
        }

        System.out.println("\n10. Stop and remove");

        service.stop(id, 0);
        service.remove(id, false);

        List<Inspection> remaining =
            service.list(Optional.empty());

        System.out.println("Remaining containers: " + remaining.size());

        if (!remaining.isEmpty()) {
            throw new IllegalStateException(
                "Final inventory assertion failed."
            );
        }

        System.out.println("\nAll enterprise workflow checks passed.");
    }
}
