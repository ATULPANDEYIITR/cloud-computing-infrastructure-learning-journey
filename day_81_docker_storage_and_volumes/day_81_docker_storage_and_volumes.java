import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * Docker Storage and Volumes
 *
 * Enterprise-oriented storage lifecycle and policy implementation.
 * Java 17, no external dependencies.
 */
public class DockerStorageEnterprise {

    enum MountType {
        VOLUME, BIND, TMPFS
    }

    enum VolumeState {
        AVAILABLE, IN_USE
    }

    enum Operation {
        READ, WRITE, DELETE
    }

    static class StorageException extends RuntimeException {
        StorageException(String message) {
            super(message);
        }
    }

    static class ValidationException extends StorageException {
        ValidationException(String message) {
            super(message);
        }
    }

    record StoragePolicy(
        boolean allowBindMounts,
        boolean allowTmpfs,
        boolean requireReadOnlyBindMounts,
        boolean allowPrivilegedDeletion
    ) {}

    record Mount(
        MountType type,
        String source,
        String destination,
        boolean readOnly
    ) {
        Mount {
            Objects.requireNonNull(type);
            Objects.requireNonNull(source);
            Objects.requireNonNull(destination);

            if (
                !destination.startsWith("/") ||
                destination.contains("/../") ||
                destination.endsWith("/..")
            ) {
                throw new ValidationException(
                    "Invalid container destination"
                );
            }

            if (
                type == MountType.VOLUME &&
                !source.matches("[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}")
            ) {
                throw new ValidationException("Invalid volume name");
            }

            if (
                type == MountType.BIND &&
                !source.startsWith("/")
            ) {
                throw new ValidationException(
                    "Bind source must be absolute"
                );
            }

            if (type == MountType.TMPFS && !source.equals("tmpfs")) {
                throw new ValidationException("Invalid tmpfs source");
            }
        }
    }

    record StorageAuditEvent(
        Instant timestamp,
        String actor,
        String operation,
        String resource,
        String outcome
    ) {}

    static class Volume {
        private final String id;
        private final String name;
        private final String driver;
        private final Instant createdAt;
        private final Map<String, String> labels;
        private final Map<String, String> data = new HashMap<>();
        private final Set<String> containers = new HashSet<>();

        private VolumeState state = VolumeState.AVAILABLE;

        Volume(
            String name,
            String driver,
            Map<String, String> labels
        ) {
            this.id = UUID.randomUUID().toString();
            this.name = name;
            this.driver = driver;
            this.labels = Map.copyOf(labels);
            this.createdAt = Instant.now();
        }

        String name() {
            return name;
        }

        String driver() {
            return driver;
        }

        VolumeState state() {
            return state;
        }

        int recordCount() {
            return data.size();
        }

        Set<String> containers() {
            return Collections.unmodifiableSet(containers);
        }
    }

    static class Container {
        private final String id;
        private final List<Mount> mounts;
        private boolean running;

        Container(String id, List<Mount> mounts) {
            if (
                id == null ||
                !id.matches("[a-zA-Z0-9_-]{1,64}")
            ) {
                throw new ValidationException("Invalid container ID");
            }

            if (mounts == null || mounts.isEmpty()) {
                throw new ValidationException("Mount list is empty");
            }

            Set<String> destinations = new HashSet<>();

            for (Mount mount : mounts) {
                if (!destinations.add(mount.destination())) {
                    throw new ValidationException(
                        "Duplicate mount destination"
                    );
                }
            }

            this.id = id;
            this.mounts = List.copyOf(mounts);
        }
    }

    static class AuditService {
        private final List<StorageAuditEvent> events =
            new ArrayList<>();

        void record(
            String actor,
            String operation,
            String resource,
            String outcome
        ) {
            events.add(new StorageAuditEvent(
                Instant.now(),
                actor,
                operation,
                resource,
                outcome
            ));
        }

        List<StorageAuditEvent> getEvents() {
            return List.copyOf(events);
        }

        long countFailures() {
            return events.stream()
                .filter(e -> e.outcome().equals("DENIED"))
                .count();
        }
    }

    static class StorageRepository {
        private final Map<String, Volume> volumes =
            new LinkedHashMap<>();

        private final Map<String, Container> containers =
            new HashMap<>();

        synchronized Volume create(
            String name,
            String driver,
            Map<String, String> labels
        ) {
            if (
                name == null ||
                !name.matches("[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}")
            ) {
                throw new ValidationException("Invalid volume name");
            }

            if (driver == null || driver.isBlank()) {
                throw new ValidationException("Invalid volume driver");
            }

            if (volumes.containsKey(name)) {
                throw new StorageException("Duplicate volume");
            }

            Volume volume = new Volume(name, driver, labels);
            volumes.put(name, volume);
            return volume;
        }

        synchronized Volume find(String name) {
            Volume volume = volumes.get(name);

            if (volume == null) {
                throw new StorageException("Volume not found: " + name);
            }

            return volume;
        }

        synchronized void register(Container container) {
            if (containers.containsKey(container.id)) {
                throw new StorageException("Duplicate container");
            }

            Set<String> references = container.mounts.stream()
                .filter(m -> m.type() == MountType.VOLUME)
                .map(Mount::source)
                .collect(Collectors.toSet());

            // Validate all volume references before mutation.
            references.forEach(this::find);

            for (Mount mount : container.mounts) {
                if (mount.type() == MountType.BIND) {
                    throw new ValidationException(
                        "Bind source requires host filesystem verification"
                    );
                }
            }

            references.forEach(name -> {
                Volume volume = find(name);
                volume.containers.add(container.id);
                volume.state = VolumeState.IN_USE;
            });

            containers.put(container.id, container);
        }

        synchronized void detach(String containerId) {
            Container container = containers.get(containerId);

            if (container == null) {
                throw new StorageException("Container not found");
            }

            Set<String> references = container.mounts.stream()
                .filter(m -> m.type() == MountType.VOLUME)
                .map(Mount::source)
                .collect(Collectors.toSet());

            for (String name : references) {
                Volume volume = find(name);
                volume.containers.remove(containerId);

                if (volume.containers.isEmpty()) {
                    volume.state = VolumeState.AVAILABLE;
                }
            }

            containers.remove(containerId);
        }

        synchronized void remove(String name) {
            Volume volume = find(name);

            if (!volume.containers.isEmpty()) {
                throw new StorageException("Volume is in use");
            }

            volumes.remove(name);
        }

        synchronized List<Volume> list() {
            return List.copyOf(volumes.values());
        }

        synchronized Map<String, Volume> snapshot() {
            return Collections.unmodifiableMap(
                new LinkedHashMap<>(volumes)
            );
        }

        synchronized void write(
            String volumeName,
            String key,
            String value,
            String containerId
        ) {
            Volume volume = find(volumeName);

            if (key == null || key.isBlank() || key.length() > 255) {
                throw new ValidationException("Invalid data key");
            }

            if (value == null) {
                throw new ValidationException("Null values prohibited");
            }

            if (containerId != null) {
                Container container = containers.get(containerId);

                if (
                    container == null ||
                    !volume.containers.contains(containerId)
                ) {
                    throw new StorageException(
                        "Container does not reference volume"
                    );
                }

                boolean writable = container.mounts.stream()
                    .anyMatch(m ->
                        m.type() == MountType.VOLUME &&
                        m.source().equals(volumeName) &&
                        !m.readOnly()
                    );

                if (!writable) {
                    throw new StorageException("Read-only mount");
                }
            }

            volume.data.put(key, value);
        }

        synchronized String read(String volumeName, String key) {
            Volume volume = find(volumeName);

            if (!volume.data.containsKey(key)) {
                throw new StorageException("Data not found");
            }

            return volume.data.get(key);
        }

        synchronized List<String> prune(String environment) {
            List<String> removed = new ArrayList<>();

            var iterator = volumes.entrySet().iterator();

            while (iterator.hasNext()) {
                var entry = iterator.next();
                Volume volume = entry.getValue();

                boolean environmentMatches =
                    environment == null ||
                    environment.equals(volume.labels.get("environment"));

                if (
                    environmentMatches &&
                    volume.containers.isEmpty()
                ) {
                    removed.add(entry.getKey());
                    iterator.remove();
                }
            }

            return removed;
        }
    }

    static class StorageService {
        private final StorageRepository repository;
        private final StoragePolicy policy;
        private final AuditService audit;

        StorageService(
            StorageRepository repository,
            StoragePolicy policy,
            AuditService audit
        ) {
            this.repository = repository;
            this.policy = policy;
            this.audit = audit;
        }

        Volume createVolume(
            String actor,
            String name,
            Map<String, String> labels
        ) {
            try {
                Volume volume = repository.create(
                    name,
                    "local",
                    labels
                );

                audit.record(
                    actor, "CREATE", name, "SUCCESS"
                );

                return volume;
            } catch (RuntimeException exception) {
                audit.record(actor, "CREATE", name, "DENIED");
                throw exception;
            }
        }

        void attach(String actor, Container container) {
            try {
                for (Mount mount : container.mounts) {
                    if (
                        mount.type() == MountType.BIND &&
                        !policy.allowBindMounts()
                    ) {
                        throw new StorageException(
                            "Bind mounts prohibited by policy"
                        );
                    }

                    if (
                        mount.type() == MountType.BIND &&
                        policy.requireReadOnlyBindMounts() &&
                        !mount.readOnly()
                    ) {
                        throw new StorageException(
                            "Writable bind mounts prohibited"
                        );
                    }

                    if (
                        mount.type() == MountType.TMPFS &&
                        !policy.allowTmpfs()
                    ) {
                        throw new StorageException(
                            "Tmpfs prohibited by policy"
                        );
                    }
                }

                repository.register(container);

                audit.record(
                    actor, "ATTACH", container.id, "SUCCESS"
                );
            } catch (RuntimeException exception) {
                audit.record(
                    actor, "ATTACH", container.id, "DENIED"
                );
                throw exception;
            }
        }

        void write(
            String actor,
            String volumeName,
            String key,
            String value,
            String containerId
        ) {
            try {
                repository.write(
                    volumeName, key, value, containerId
                );

                audit.record(
                    actor, "WRITE", volumeName, "SUCCESS"
                );
            } catch (RuntimeException exception) {
                audit.record(
                    actor, "WRITE", volumeName, "DENIED"
                );
                throw exception;
            }
        }

        void deleteVolume(String actor, String name) {
            try {
                if (!policy.allowPrivilegedDeletion()) {
                    throw new StorageException(
                        "Deletion prohibited by policy"
                    );
                }

                repository.remove(name);

                audit.record(
                    actor, "DELETE", name, "SUCCESS"
                );
            } catch (RuntimeException exception) {
                audit.record(
                    actor, "DELETE", name, "DENIED"
                );
                throw exception;
            }
        }

        List<Volume> inventory() {
            return repository.list();
        }

        List<String> prune(String actor, String environment) {
            List<String> removed = repository.prune(environment);

            audit.record(
                actor,
                "PRUNE",
                String.valueOf(removed.size()),
                "SUCCESS"
            );

            return removed;
        }
    }

    public static void main(String[] args) {
        StorageRepository repository = new StorageRepository();

        StoragePolicy policy = new StoragePolicy(
            true,
            true,
            true,
            true
        );

        AuditService audit = new AuditService();

        StorageService service = new StorageService(
            repository,
            policy,
            audit
        );

        try {
            service.createVolume(
                "admin",
                "postgres_data",
                Map.of(
                    "environment", "production",
                    "service", "postgres"
                )
            );

            service.createVolume(
                "admin",
                "temporary_logs",
                Map.of("environment", "development")
            );

            service.write(
                "admin",
                "postgres_data",
                "database",
                "inventory",
                null
            );

            Container database = new Container(
                "postgres-container",
                List.of(
                    new Mount(
                        MountType.VOLUME,
                        "postgres_data",
                        "/var/lib/postgresql/data",
                        false
                    ),
                    new Mount(
                        MountType.TMPFS,
                        "tmpfs",
                        "/run/cache",
                        true
                    )
                )
            );

            service.attach("admin", database);

            service.write(
                "postgres-service",
                "postgres_data",
                "status",
                "healthy",
                "postgres-container"
            );

            System.out.println("Persistent value: " +
                repository.read("postgres_data", "database"));

            System.out.println("\nStorage inventory:");

            for (Volume volume : service.inventory()) {
                System.out.printf(
                    "%s | driver=%s | state=%s | records=%d%n",
                    volume.name(),
                    volume.driver(),
                    volume.state(),
                    volume.recordCount()
                );
            }

            try {
                service.deleteVolume(
                    "admin",
                    "postgres_data"
                );
            } catch (StorageException exception) {
                System.out.println(
                    "Expected deletion restriction: " +
                    exception.getMessage()
                );
            }

            repository.detach("postgres-container");

            System.out.println("\nPruned development volumes: " +
                service.prune("admin", "development"));

            System.out.println(
                "\nAudit failures: " + audit.countFailures()
            );

            System.out.println("\nAudit history:");

            audit.getEvents().forEach(System.out::println);

        } catch (RuntimeException exception) {
            System.err.println(
                "Storage service failure: " + exception.getMessage()
            );
            System.exit(1);
        }
    }
}
