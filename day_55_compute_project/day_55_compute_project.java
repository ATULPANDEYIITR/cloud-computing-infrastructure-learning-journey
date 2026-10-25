import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/**
 * Compute and Storage Project.
 *
 * Models an enterprise application platform containing:
 * compute instances, object storage, load balancing, autoscaling,
 * health management, backups, recovery, and deployment eligibility.
 */
public class ComputeStorageProject {

    enum InstanceState {
        RUNNING,
        UNHEALTHY,
        STOPPED
    }

    enum BackupState {
        AVAILABLE,
        RESTORING,
        FAILED
    }

    static class InfrastructureException extends RuntimeException {
        InfrastructureException(String message) {
            super(message);
        }
    }

    record PlatformConfig(
        int minInstances,
        int maxInstances,
        int requestsPerInstance,
        double scaleUpThreshold,
        double scaleDownThreshold,
        int maxObjectSize,
        int backupRetentionDays
    ) {
        PlatformConfig {
            if (minInstances < 1) {
                throw new IllegalArgumentException(
                    "Minimum instances must be at least one."
                );
            }

            if (minInstances > maxInstances) {
                throw new IllegalArgumentException(
                    "Minimum instances cannot exceed maximum instances."
                );
            }

            if (requestsPerInstance <= 0 || maxObjectSize <= 0) {
                throw new IllegalArgumentException(
                    "Capacity and object size must be positive."
                );
            }

            if (
                scaleDownThreshold < 0 ||
                scaleUpThreshold > 1 ||
                scaleDownThreshold >= scaleUpThreshold
            ) {
                throw new IllegalArgumentException(
                    "Invalid scaling thresholds."
                );
            }
        }
    }

    static final class ComputeInstance {
        private final String id;
        private final int capacity;
        private int activeRequests;
        private InstanceState state;

        ComputeInstance(String id, int capacity) {
            if (id == null || id.isBlank() || capacity <= 0) {
                throw new IllegalArgumentException(
                    "Invalid compute instance."
                );
            }

            this.id = id;
            this.capacity = capacity;
            this.state = InstanceState.RUNNING;
        }

        String id() {
            return id;
        }

        int capacity() {
            return capacity;
        }

        int activeRequests() {
            return activeRequests;
        }

        InstanceState state() {
            return state;
        }

        double utilization() {
            return capacity == 0
                ? 1.0
                : (double) activeRequests / capacity;
        }

        boolean canReceiveTraffic() {
            return state == InstanceState.RUNNING &&
                   activeRequests < capacity;
        }

        void acceptRequest() {
            if (!canReceiveTraffic()) {
                throw new InfrastructureException(
                    "Instance cannot accept traffic: " + id
                );
            }

            activeRequests++;
        }

        void completeRequest() {
            if (activeRequests == 0) {
                throw new InfrastructureException(
                    "No active requests exist on " + id
                );
            }

            activeRequests--;
        }

        void markUnhealthy() {
            if (activeRequests > 0) {
                throw new InfrastructureException(
                    "Instance must drain active requests first."
                );
            }

            state = InstanceState.UNHEALTHY;
        }
    }

    record StoredObject(
        String key,
        byte[] content,
        String checksum,
        Instant createdAt
    ) {
        StoredObject {
            content = content.clone();
        }

        int size() {
            return content.length;
        }
    }

    static final class ObjectStorage {
        private final int maxObjectSize;
        private final Map<String, StoredObject> objects = new HashMap<>();

        ObjectStorage(int maxObjectSize) {
            this.maxObjectSize = maxObjectSize;
        }

        StoredObject put(String key, String content) {
            if (key == null || key.isBlank() || key.startsWith("/")) {
                throw new InfrastructureException(
                    "Storage key must be non-empty and relative."
                );
            }

            byte[] bytes = content.getBytes(StandardCharsets.UTF_8);

            if (bytes.length > maxObjectSize) {
                throw new InfrastructureException(
                    "Object exceeds configured storage limit."
                );
            }

            StoredObject object = new StoredObject(
                key,
                bytes,
                sha256(bytes),
                Instant.now()
            );

            objects.put(key, object);
            return object;
        }

        byte[] get(String key) {
            StoredObject object = objects.get(key);

            if (object == null) {
                throw new InfrastructureException(
                    "Object does not exist: " + key
                );
            }

            if (!sha256(object.content()).equals(object.checksum())) {
                throw new InfrastructureException(
                    "Object integrity verification failed: " + key
                );
            }

            return object.content().clone();
        }

        void delete(String key) {
            if (objects.remove(key) == null) {
                throw new InfrastructureException(
                    "Cannot delete missing object: " + key
                );
            }
        }

        Map<String, StoredObject> snapshot() {
            Map<String, StoredObject> copy = new HashMap<>();

            for (var entry : objects.entrySet()) {
                StoredObject value = entry.getValue();

                copy.put(
                    entry.getKey(),
                    new StoredObject(
                        value.key(),
                        value.content(),
                        value.checksum(),
                        value.createdAt()
                    )
                );
            }

            return copy;
        }

        void restore(Map<String, StoredObject> snapshot) {
            objects.clear();
            objects.putAll(snapshot);
        }

        int objectCount() {
            return objects.size();
        }

        long totalBytes() {
            return objects.values()
                .stream()
                .mapToLong(StoredObject::size)
                .sum();
        }

        private static String sha256(byte[] content) {
            try {
                MessageDigest digest =
                    MessageDigest.getInstance("SHA-256");

                byte[] result = digest.digest(content);
                StringBuilder output = new StringBuilder();

                for (byte value : result) {
                    output.append(String.format("%02x", value));
                }

                return output.toString();
            } catch (NoSuchAlgorithmException exception) {
                throw new IllegalStateException(
                    "SHA-256 is unavailable.",
                    exception
                );
            }
        }
    }

    record Backup(
        String id,
        Instant createdAt,
        Map<String, StoredObject> snapshot,
        BackupState state
    ) {}

    static final class BackupManager {
        private final ObjectStorage storage;
        private final List<Backup> backups = new ArrayList<>();
        private int sequence;

        BackupManager(ObjectStorage storage) {
            this.storage = storage;
        }

        Backup createBackup() {
            sequence++;

            Backup backup = new Backup(
                String.format("backup-%04d", sequence),
                Instant.now(),
                storage.snapshot(),
                BackupState.AVAILABLE
            );

            backups.add(backup);
            return backup;
        }

        void restore(String backupId) {
            Backup backup = backups.stream()
                .filter(item -> item.id().equals(backupId))
                .findFirst()
                .orElseThrow(() ->
                    new InfrastructureException(
                        "Backup not found: " + backupId
                    )
                );

            try {
                storage.restore(backup.snapshot());
            } catch (RuntimeException exception) {
                throw new InfrastructureException(
                    "Backup restoration failed: " +
                    exception.getMessage()
                );
            }
        }

        boolean hasBackup() {
            return !backups.isEmpty();
        }

        int count() {
            return backups.size();
        }
    }

    static final class LoadBalancer {
        private final List<ComputeInstance> instances;

        LoadBalancer(List<ComputeInstance> instances) {
            this.instances = instances;
        }

        ComputeInstance chooseInstance() {
            return instances.stream()
                .filter(ComputeInstance::canReceiveTraffic)
                .min(
                    (left, right) ->
                        Double.compare(
                            left.utilization(),
                            right.utilization()
                        )
                )
                .orElseThrow(() ->
                    new InfrastructureException(
                        "No healthy compute capacity is available."
                    )
                );
        }

        Map<String, Integer> dispatch(int requestCount) {
            if (requestCount < 0) {
                throw new IllegalArgumentException(
                    "Request count cannot be negative."
                );
            }

            Map<String, Integer> distribution = new HashMap<>();

            for (int i = 0; i < requestCount; i++) {
                ComputeInstance instance = chooseInstance();
                instance.acceptRequest();

                distribution.merge(instance.id(), 1, Integer::sum);
            }

            return distribution;
        }

        void complete(int requestCount) {
            if (requestCount < 0) {
                throw new IllegalArgumentException(
                    "Request count cannot be negative."
                );
            }

            int remaining = requestCount;

            List<ComputeInstance> ordered =
                new ArrayList<>(instances);

            ordered.sort(
                (left, right) ->
                    Integer.compare(
                        right.activeRequests(),
                        left.activeRequests()
                    )
            );

            for (ComputeInstance instance : ordered) {
                while (
                    instance.activeRequests() > 0 &&
                    remaining > 0
                ) {
                    instance.completeRequest();
                    remaining--;
                }

                if (remaining == 0) {
                    return;
                }
            }

            if (remaining > 0) {
                throw new InfrastructureException(
                    "Cannot complete more requests than are active."
                );
            }
        }
    }

    record GovernancePolicy(
        int minimumHealthyInstances,
        int minimumCapacity,
        boolean requireBackup
    ) {}

    record EligibilityResult(
        boolean eligible,
        List<String> failures
    ) {}

    interface DeploymentPolicy {
        EligibilityResult evaluate(
            List<ComputeInstance> instances,
            BackupManager backups
        );
    }

    static final class ProductionDeploymentPolicy
        implements DeploymentPolicy {

        private final GovernancePolicy policy;

        ProductionDeploymentPolicy(GovernancePolicy policy) {
            this.policy = Objects.requireNonNull(policy);
        }

        @Override
        public EligibilityResult evaluate(
            List<ComputeInstance> instances,
            BackupManager backups
        ) {
            List<String> failures = new ArrayList<>();

            long healthyCount = instances.stream()
                .filter(
                    instance ->
                        instance.state() == InstanceState.RUNNING
                )
                .count();

            int capacity = instances.stream()
                .filter(
                    instance ->
                        instance.state() == InstanceState.RUNNING
                )
                .mapToInt(ComputeInstance::capacity)
                .sum();

            if (healthyCount < policy.minimumHealthyInstances()) {
                failures.add(
                    "Healthy instance count is below policy minimum."
                );
            }

            if (capacity < policy.minimumCapacity()) {
                failures.add(
                    "Healthy compute capacity is below policy minimum."
                );
            }

            if (policy.requireBackup() && !backups.hasBackup()) {
                failures.add(
                    "A recoverable backup is required."
                );
            }

            return new EligibilityResult(
                failures.isEmpty(),
                List.copyOf(failures)
            );
        }
    }

    static final class ApplicationPlatform {
        private final PlatformConfig config;
        private final List<ComputeInstance> instances =
            new ArrayList<>();
        private final ObjectStorage storage;
        private final BackupManager backups;
        private final LoadBalancer loadBalancer;

        ApplicationPlatform(PlatformConfig config) {
            this.config = config;
            this.storage =
                new ObjectStorage(config.maxObjectSize());
            this.backups =
                new BackupManager(storage);

            for (int i = 1; i <= config.minInstances(); i++) {
                instances.add(
                    new ComputeInstance(
                        String.format("app-%02d", i),
                        config.requestsPerInstance()
                    )
                );
            }

            this.loadBalancer =
                new LoadBalancer(instances);
        }

        ObjectStorage storage() {
            return storage;
        }

        BackupManager backups() {
            return backups;
        }

        LoadBalancer loadBalancer() {
            return loadBalancer;
        }

        List<ComputeInstance> instances() {
            return Collections.unmodifiableList(instances);
        }

        void addInstance() {
            if (instances.size() >= config.maxInstances()) {
                throw new InfrastructureException(
                    "Maximum instance count reached."
                );
            }

            instances.add(
                new ComputeInstance(
                    String.format(
                        "app-%02d",
                        instances.size() + 1
                    ),
                    config.requestsPerInstance()
                )
            );
        }

        void markUnhealthy(String id) {
            ComputeInstance instance = findInstance(id);
            instance.markUnhealthy();
        }

        private ComputeInstance findInstance(String id) {
            return instances.stream()
                .filter(instance -> instance.id().equals(id))
                .findFirst()
                .orElseThrow(() ->
                    new InfrastructureException(
                        "Instance not found: " + id
                    )
                );
        }

        int healthyCapacity() {
            return instances.stream()
                .filter(
                    instance ->
                        instance.state() == InstanceState.RUNNING
                )
                .mapToInt(ComputeInstance::capacity)
                .sum();
        }
    }

    private static void check(
        boolean condition,
        String message
    ) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void runTests() {
        ApplicationPlatform platform =
            new ApplicationPlatform(
                new PlatformConfig(
                    2,
                    4,
                    10,
                    0.70,
                    0.25,
                    1024,
                    7
                )
            );

        platform.storage().put(
            "config/application.json",
            "{\"version\":\"1.0.0\"}"
        );

        check(
            platform.storage()
                .get("config/application.json").length > 0,
            "stored object should be readable"
        );

        Map<String, Integer> traffic =
            platform.loadBalancer().dispatch(15);

        check(
            traffic.values()
                .stream()
                .mapToInt(Integer::intValue)
                .sum() == 15,
            "all requests should be routed"
        );

        platform.loadBalancer().complete(15);

        Backup backup =
            platform.backups().createBackup();

        platform.storage().delete("config/application.json");

        check(
            platform.storage().objectCount() == 0,
            "object should be deleted"
        );

        platform.backups().restore(backup.id());

        check(
            platform.storage().objectCount() == 1,
            "backup should restore the object"
        );

        platform.markUnhealthy("app-01");

        check(
            platform.healthyCapacity() == 10,
            "healthy capacity should fall after failure"
        );
    }

    public static void main(String[] args) {
        try {
            runTests();

            PlatformConfig config =
                new PlatformConfig(
                    2,
                    6,
                    100,
                    0.70,
                    0.25,
                    10 * 1024 * 1024,
                    7
                );

            ApplicationPlatform platform =
                new ApplicationPlatform(config);

            platform.storage().put(
                "releases/v1/config.json",
                "{\"version\":\"1.0.0\",\"environment\":\"production\"}"
            );

            platform.storage().put(
                "releases/v1/index.html",
                "<html><body>Scalable application</body></html>"
            );

            Map<String, Integer> distribution =
                platform.loadBalancer().dispatch(180);

            System.out.println("Request distribution:");

            distribution.forEach(
                (instance, count) ->
                    System.out.println(
                        " " + instance + " -> " + count
                    )
            );

            platform.loadBalancer().complete(180);

            Backup backup =
                platform.backups().createBackup();

            System.out.println(
                "\nCreated backup: " + backup.id()
            );

            DeploymentPolicy policy =
                new ProductionDeploymentPolicy(
                    new GovernancePolicy(
                        2,
                        200,
                        true
                    )
                );

            EligibilityResult beforeFailure =
                policy.evaluate(
                    platform.instances(),
                    platform.backups()
                );

            System.out.println(
                "\nDeployment eligible: " +
                beforeFailure.eligible()
            );

            platform.addInstance();

            System.out.println(
                "Healthy capacity after scale-out: " +
                platform.healthyCapacity()
            );

            platform.markUnhealthy("app-01");

            EligibilityResult afterFailure =
                policy.evaluate(
                    platform.instances(),
                    platform.backups()
                );

            System.out.println(
                "\nDeployment eligible after failure: " +
                afterFailure.eligible()
            );

            if (!afterFailure.eligible()) {
                afterFailure.failures()
                    .forEach(
                        failure ->
                            System.out.println(
                                " - " + failure
                            )
                    );
            }

            System.out.println(
                "\nStored objects: " +
                platform.storage().objectCount()
            );

            System.out.println(
                "Stored bytes: " +
                platform.storage().totalBytes()
            );

            System.out.println(
                "Backups: " +
                platform.backups().count()
            );

        } catch (RuntimeException exception) {
            System.err.println(
                "Infrastructure operation failed: " +
                exception.getMessage()
            );
            System.exit(1);
        }
    }
}
