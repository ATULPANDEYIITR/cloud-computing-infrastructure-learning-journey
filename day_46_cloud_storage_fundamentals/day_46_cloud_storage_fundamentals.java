import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import java.util.zip.CRC32;
import java.nio.charset.StandardCharsets;

public class CloudStorageFundamentals {

    enum StorageClass {
        STANDARD,
        INFREQUENT_ACCESS,
        ARCHIVE
    }

    enum ReplicationMode {
        SINGLE_REGION,
        SYNCHRONOUS,
        ASYNCHRONOUS
    }

    enum ReplicaState {
        HEALTHY,
        UNAVAILABLE
    }

    record StoragePolicy(
        double monthlyCostPerGb,
        double retrievalCostPerGb,
        int minimumRetentionDays,
        long retrievalLatencyMillis
    ) {
        StoragePolicy {
            if (monthlyCostPerGb < 0 || retrievalCostPerGb < 0
                    || minimumRetentionDays < 0 || retrievalLatencyMillis < 0) {
                throw new IllegalArgumentException("Invalid storage policy");
            }
        }
    }

    record ObjectVersion(
        String key,
        byte[] content,
        long version,
        long createdDay,
        StorageClass storageClass,
        String checksum,
        String etag
    ) {
        ObjectVersion {
            if (key == null || key.isBlank()) {
                throw new IllegalArgumentException("Object key is required");
            }
            if (content == null || content.length == 0) {
                throw new IllegalArgumentException("Object content cannot be empty");
            }
            if (version < 1 || createdDay < 0) {
                throw new IllegalArgumentException("Invalid object version or creation day");
            }
            Objects.requireNonNull(storageClass, "Storage class is required");
            Objects.requireNonNull(checksum, "Checksum is required");
            Objects.requireNonNull(etag, "ETag is required");
            content = content.clone();
        }

        @Override
        public byte[] content() {
            return content.clone();
        }
    }

    static final class StorageException extends RuntimeException {
        StorageException(String message) {
            super(message);
        }
    }

    static final class Region {
        private final String name;
        private ReplicaState state = ReplicaState.HEALTHY;
        private final Map<String, ObjectVersion> objects = new HashMap<>();

        Region(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Region name is required");
            }
            this.name = name;
        }

        String name() {
            return name;
        }

        boolean available() {
            return state == ReplicaState.HEALTHY;
        }

        void setAvailable(boolean available) {
            state = available ? ReplicaState.HEALTHY : ReplicaState.UNAVAILABLE;
        }
    }

    record ReplicationTask(String regionName, ObjectVersion object) {}

    static final class StorageClassCatalog {
        private final EnumMap<StorageClass, StoragePolicy> policies =
            new EnumMap<>(StorageClass.class);

        StorageClassCatalog() {
            policies.put(StorageClass.STANDARD,
                new StoragePolicy(0.023, 0.0, 0, 50));
            policies.put(StorageClass.INFREQUENT_ACCESS,
                new StoragePolicy(0.0125, 0.01, 30, 100));
            policies.put(StorageClass.ARCHIVE,
                new StoragePolicy(0.004, 0.03, 90, 3_600_000));
        }

        StoragePolicy policy(StorageClass storageClass) {
            StoragePolicy result = policies.get(storageClass);
            if (result == null) {
                throw new IllegalArgumentException("Unknown storage class");
            }
            return result;
        }

        double monthlyEstimate(
            double sizeGb,
            double retrievedGb,
            int copies,
            StorageClass storageClass
        ) {
            if (sizeGb < 0 || retrievedGb < 0 || copies < 1) {
                throw new IllegalArgumentException("Invalid billing quantities");
            }
            StoragePolicy policy = policy(storageClass);
            return sizeGb * policy.monthlyCostPerGb() * copies
                + retrievedGb * policy.retrievalCostPerGb();
        }
    }

    static final class ObjectStorageService {
        private final Map<String, Region> regions = new LinkedHashMap<>();
        private final List<ReplicationTask> queue = new ArrayList<>();
        private final Map<String, AtomicLong> versionCounters = new HashMap<>();
        private final ReplicationMode mode;
        private String primaryRegion;

        ObjectStorageService(List<String> regionNames, ReplicationMode mode) {
            if (regionNames == null || regionNames.isEmpty()) {
                throw new IllegalArgumentException("At least one region is required");
            }
            if (regionNames.stream().distinct().count() != regionNames.size()) {
                throw new IllegalArgumentException("Region names must be unique");
            }
            this.mode = Objects.requireNonNull(mode);

            for (String name : regionNames) {
                regions.put(name, new Region(name));
            }
            primaryRegion = regionNames.get(0);
        }

        synchronized ObjectVersion put(
            String key,
            String content,
            StorageClass storageClass,
            long day
        ) {
            if (key == null || key.isBlank() || content == null || content.isEmpty()) {
                throw new IllegalArgumentException("Key and content are required");
            }
            if (day < 0) throw new IllegalArgumentException("Day cannot be negative");

            Region primary = regions.get(primaryRegion);
            if (!primary.available()) {
                throw new StorageException("Primary region is unavailable");
            }

            List<Region> destinations = regions.values().stream()
                .filter(region -> !region.name().equals(primaryRegion))
                .toList();

            if (mode == ReplicationMode.SYNCHRONOUS
                    && destinations.stream().anyMatch(region -> !region.available())) {
                throw new StorageException(
                    "Synchronous write cannot satisfy the replication policy"
                );
            }

            long version = versionCounters
                .computeIfAbsent(key, ignored -> new AtomicLong())
                .incrementAndGet();

            byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
            ObjectVersion object = new ObjectVersion(
                key,
                bytes,
                version,
                day,
                storageClass,
                checksum(bytes),
                UUID.randomUUID().toString()
            );

            primary.objects.put(key, object);

            if (mode == ReplicationMode.SYNCHRONOUS) {
                destinations.forEach(region -> region.objects.put(key, object));
            } else if (mode == ReplicationMode.ASYNCHRONOUS) {
                destinations.forEach(region ->
                    queue.add(new ReplicationTask(region.name(), object))
                );
            }

            return object;
        }

        synchronized int deliverReplication() {
            int delivered = 0;

            for (ReplicationTask task : queue) {
                Region target = regions.get(task.regionName());
                if (!target.available()) continue;

                ObjectVersion candidate = task.object();
                ObjectVersion current = target.objects.get(candidate.key());

                // A delayed older task must never replace a newer stored version.
                if (current == null || current.version() < candidate.version()) {
                    target.objects.put(candidate.key(), candidate);
                }
                delivered++;
            }

            queue.clear();
            return delivered;
        }

        synchronized Optional<ObjectVersion> read(
            String key,
            Optional<String> preferredRegion
        ) {
            List<Region> candidates;

            if (preferredRegion.isPresent()) {
                Region preferred = regions.get(preferredRegion.get());
                if (preferred == null) {
                    throw new IllegalArgumentException("Unknown preferred region");
                }
                candidates = List.of(preferred);
            } else {
                candidates = new ArrayList<>(regions.values());
                candidates.sort((left, right) -> {
                    if (left.name().equals(primaryRegion)) return -1;
                    if (right.name().equals(primaryRegion)) return 1;
                    return left.name().compareTo(right.name());
                });
            }

            for (Region region : candidates) {
                if (!region.available()) continue;

                ObjectVersion object = region.objects.get(key);
                if (object == null) continue;

                if (!checksum(object.content()).equals(object.checksum())) {
                    throw new StorageException("Object integrity verification failed");
                }
                return Optional.of(object);
            }

            return Optional.empty();
        }

        synchronized void setRegionAvailability(String name, boolean available) {
            Region region = regions.get(name);
            if (region == null) {
                throw new IllegalArgumentException("Unknown region: " + name);
            }
            region.setAvailable(available);
        }

        synchronized void promoteRegion(String name) {
            Region candidate = regions.get(name);
            if (candidate == null || !candidate.available()) {
                throw new StorageException("Failover target is unavailable or unknown");
            }
            if (candidate.objects.isEmpty()) {
                throw new StorageException("Failover target has no stored objects");
            }
            primaryRegion = name;
        }

        synchronized long availableCopies(String key) {
            return regions.values().stream()
                .filter(Region::available)
                .filter(region -> region.objects.containsKey(key))
                .count();
        }

        synchronized List<String> pendingTasks() {
            List<String> descriptions = new ArrayList<>();
            for (ReplicationTask task : queue) {
                descriptions.add(
                    task.object().key() + " v" + task.object().version()
                        + " -> " + task.regionName()
                );
            }
            return Collections.unmodifiableList(descriptions);
        }

        String primaryRegion() {
            return primaryRegion;
        }
    }

    static String checksum(byte[] bytes) {
        CRC32 crc = new CRC32();
        crc.update(bytes);
        return Long.toHexString(crc.getValue());
    }

    static double redundantAvailability(double availability, int copies) {
        if (availability < 0 || availability > 1 || copies < 1) {
            throw new IllegalArgumentException("Invalid reliability parameters");
        }
        return 1.0 - Math.pow(1.0 - availability, copies);
    }

    static void demonstrateRetention(
        ObjectVersion object,
        long evaluationDay,
        StorageClass target,
        StorageClassCatalog catalog
    ) {
        if (evaluationDay < object.createdDay()) {
            throw new IllegalArgumentException("Evaluation predates object creation");
        }

        StoragePolicy current = catalog.policy(object.storageClass());
        long age = evaluationDay - object.createdDay();

        if (age < current.minimumRetentionDays()) {
            throw new StorageException(
                "Minimum retention not met: age=" + age
                    + ", required=" + current.minimumRetentionDays()
            );
        }

        System.out.println(
            "Eligible transition: " + object.storageClass()
                + " -> " + target + ", object age=" + age + " days"
        );
    }

    public static void main(String[] args) {
        StorageClassCatalog catalog = new StorageClassCatalog();

        ObjectStorageService service = new ObjectStorageService(
            List.of("ap-south-1", "ap-southeast-1", "eu-west-1"),
            ReplicationMode.ASYNCHRONOUS
        );

        ObjectVersion object = service.put(
            "compliance/inspection-2026-10.json",
            "{\"inspection\":\"passed\",\"site\":\"plant-07\"}",
            StorageClass.INFREQUENT_ACCESS,
            0
        );

        System.out.println("Stored version: " + object.version());
        System.out.println("Copies before replication: "
            + service.availableCopies(object.key()));
        System.out.println("Queued tasks: " + service.pendingTasks());

        service.setRegionAvailability("eu-west-1", false);
        System.out.println("Delivered tasks: " + service.deliverReplication());
        System.out.println("Remaining queued tasks: " + service.pendingTasks());

        service.setRegionAvailability("eu-west-1", true);
        service.deliverReplication();

        service.setRegionAvailability("ap-south-1", false);
        Optional<ObjectVersion> recovered = service.read(
            object.key(),
            Optional.of("ap-southeast-1")
        );

        if (recovered.isPresent()) {
            System.out.println("Recovered version: " + recovered.get().version());
            service.promoteRegion("ap-southeast-1");
            System.out.println("New primary: " + service.primaryRegion());
        } else {
            System.out.println("No accessible replica is available");
        }

        System.out.println("\nMonthly storage estimates for 500 GB");
        for (StorageClass storageClass : StorageClass.values()) {
            double cost = catalog.monthlyEstimate(
                500, 20, 2, storageClass
            );
            StoragePolicy policy = catalog.policy(storageClass);

            System.out.printf(
                "%s: $%.2f, retrieval latency=%d ms, minimum retention=%d days%n",
                storageClass,
                cost,
                policy.retrievalLatencyMillis(),
                policy.minimumRetentionDays()
            );
        }

        System.out.println("\nIndependent availability estimates");
        for (int copies : List.of(1, 2, 3)) {
            System.out.printf(
                "%d copies: %.6f%%%n",
                copies,
                redundantAvailability(0.999, copies) * 100
            );
        }

        try {
            demonstrateRetention(object, 10, StorageClass.ARCHIVE, catalog);
        } catch (StorageException exception) {
            System.out.println("Lifecycle transition rejected: " + exception.getMessage());
        }

        // CRC32 is used here to demonstrate an integrity check, not to provide
        // cryptographic collision resistance. Production systems should use a
        // cryptographic digest and authenticated access controls.
        System.out.println(
            "\nDurability, service availability, integrity, and recoverability "
                + "must be measured and controlled separately."
        );
    }
}
