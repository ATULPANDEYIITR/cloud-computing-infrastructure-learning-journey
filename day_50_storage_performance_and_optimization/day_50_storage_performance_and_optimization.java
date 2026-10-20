import java.util.ArrayList;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class StorageOptimization {

    enum AccessType {
        READ,
        WRITE
    }

    record StorageTier(
            String name,
            double maxIops,
            double maxThroughputMbps,
            double latencyMs,
            double monthlyCostPerGb) {

        StorageTier {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Tier name is required");
            }
            if (maxIops <= 0 ||
                maxThroughputMbps <= 0 ||
                latencyMs <= 0 ||
                monthlyCostPerGb < 0) {
                throw new IllegalArgumentException(
                        "Storage tier metrics are invalid");
            }
        }

        double monthlyCost(double capacityGb) {
            if (capacityGb <= 0) {
                throw new IllegalArgumentException(
                        "Capacity must be positive");
            }
            return monthlyCostPerGb * capacityGb;
        }

        double sustainableIops(int requestSizeKb) {
            if (requestSizeKb <= 0) {
                throw new IllegalArgumentException(
                        "Request size must be positive");
            }

            double throughputLimited =
                    maxThroughputMbps * 1024.0 / requestSizeKb;

            return Math.min(maxIops, throughputLimited);
        }
    }

    record IoRequest(
            long id,
            AccessType type,
            int sizeKb,
            String key) {

        IoRequest {
            Objects.requireNonNull(type, "Access type is required");

            if (id < 0) {
                throw new IllegalArgumentException(
                        "Request ID cannot be negative");
            }

            if (sizeKb <= 0 || sizeKb > 1024 * 1024) {
                throw new IllegalArgumentException(
                        "I/O size is outside the permitted range");
            }

            if (key == null || key.isBlank() || key.length() > 256) {
                throw new IllegalArgumentException(
                        "Storage key is invalid");
            }
        }
    }

    record WorkloadPolicy(
            double requiredIops,
            double requiredThroughputMbps,
            double capacityGb,
            double maximumMonthlyCost) {

        WorkloadPolicy {
            if (requiredIops < 0 ||
                requiredThroughputMbps < 0 ||
                capacityGb <= 0 ||
                maximumMonthlyCost < 0) {
                throw new IllegalArgumentException(
                        "Invalid workload policy");
            }
        }
    }

    static final class LruCache<K, V>
            extends LinkedHashMap<K, V> {

        private final int capacity;

        LruCache(int capacity) {
            super(capacity, 0.75f, true);

            if (capacity <= 0) {
                throw new IllegalArgumentException(
                        "Cache capacity must be positive");
            }

            this.capacity = capacity;
        }

        @Override
        protected boolean removeEldestEntry(
                Map.Entry<K, V> eldest) {
            return size() > capacity;
        }
    }

    static final class Metrics {
        private long requests;
        private long reads;
        private long writes;
        private long cacheHits;
        private long cacheMisses;
        private double totalLatencyMs;
        private long totalBytes;

        void recordBytes(long bytes) {
            totalBytes += bytes;
            requests++;
        }

        double averageLatencyMs() {
            return requests == 0
                    ? 0.0
                    : totalLatencyMs / requests;
        }

        double cacheHitRatio() {
            long accesses = cacheHits + cacheMisses;
            return accesses == 0
                    ? 0.0
                    : (double) cacheHits / accesses;
        }

        double modeledThroughputMbps() {
            if (totalLatencyMs <= 0) {
                return 0.0;
            }

            return totalBytes / 1024.0 / 1024.0 /
                    (totalLatencyMs / 1000.0);
        }
    }

    interface StoragePolicy {
        StorageTier select(WorkloadPolicy policy);
    }

    static final class CostAwareStoragePolicy
            implements StoragePolicy {

        private final List<StorageTier> tiers;

        CostAwareStoragePolicy(List<StorageTier> tiers) {
            if (tiers == null || tiers.isEmpty()) {
                throw new IllegalArgumentException(
                        "At least one storage tier is required");
            }
            this.tiers = List.copyOf(tiers);
        }

        @Override
        public StorageTier select(WorkloadPolicy policy) {
            StorageTier selected = null;

            for (StorageTier tier : tiers) {
                boolean performanceSatisfied =
                        tier.maxIops() >= policy.requiredIops()
                                && tier.maxThroughputMbps()
                                >= policy.requiredThroughputMbps();

                boolean costSatisfied =
                        tier.monthlyCost(policy.capacityGb())
                                <= policy.maximumMonthlyCost();

                if (performanceSatisfied && costSatisfied &&
                        (selected == null ||
                         tier.monthlyCostPerGb()
                                < selected.monthlyCostPerGb())) {
                    selected = tier;
                }
            }

            if (selected == null) {
                throw new IllegalStateException(
                        "No tier satisfies both performance and cost policy");
            }

            return selected;
        }
    }

    static final class StorageService {
        private final StorageTier tier;
        private final LruCache<String, Boolean> cache;
        private final Metrics metrics = new Metrics();

        StorageService(StorageTier tier, int cacheCapacity) {
            this.tier = Objects.requireNonNull(tier);
            this.cache = new LruCache<>(cacheCapacity);
        }

        private double storageLatencyMs(int sizeKb) {
            double transfer =
                    (sizeKb / 1024.0) /
                    tier.maxThroughputMbps() * 1000.0;

            return tier.latencyMs() + transfer;
        }

        void execute(IoRequest request) {
            Objects.requireNonNull(request);

            metrics.recordBytes(request.sizeKb() * 1024L);

            if (request.type() == AccessType.READ) {
                metrics.reads++;

                if (cache.containsKey(request.key())) {
                    metrics.cacheHits++;
                    metrics.totalLatencyMs +=
                            Math.max(
                                    0.05,
                                    tier.latencyMs() * 0.10);
                } else {
                    metrics.cacheMisses++;
                    metrics.totalLatencyMs +=
                            storageLatencyMs(request.sizeKb());

                    cache.put(request.key(), Boolean.TRUE);
                }
            } else {
                metrics.writes++;
                metrics.totalLatencyMs +=
                        storageLatencyMs(request.sizeKb());

                // Write-through keeps cached state consistent.
                cache.put(request.key(), Boolean.TRUE);
            }
        }

        Metrics metrics() {
            return metrics;
        }
    }

    private static List<IoRequest> buildWorkload() {
        List<IoRequest> requests = new ArrayList<>();

        for (int i = 0; i < 2000; i++) {
            boolean hot = i % 4 != 0;
            boolean read = i % 5 != 0;

            String key = hot
                    ? "customer:" + (i % 12)
                    : "archive:" + (i % 200);

            int sizeKb = switch (i % 6) {
                case 0 -> 4;
                case 1 -> 8;
                case 2 -> 16;
                case 3 -> 32;
                case 4 -> 64;
                default -> 128;
            };

            requests.add(new IoRequest(
                    i,
                    read ? AccessType.READ : AccessType.WRITE,
                    sizeKb,
                    key));
        }

        return List.copyOf(requests);
    }

    public static void main(String[] args) {
        List<StorageTier> tiers = List.of(
                new StorageTier(
                        "HDD", 180, 220, 8.0, 0.02),
                new StorageTier(
                        "SATA SSD", 75_000, 550, 0.10, 0.08),
                new StorageTier(
                        "NVMe SSD", 800_000, 7_000, 0.025, 0.15)
        );

        WorkloadPolicy policy = new WorkloadPolicy(
                120_000,
                1_500,
                2_000,
                1_000.00
        );

        StoragePolicy selectionPolicy =
                new CostAwareStoragePolicy(tiers);

        StorageTier selected = selectionPolicy.select(policy);

        System.out.println("Enterprise storage decision");
        System.out.println("Selected tier: " + selected.name());
        System.out.printf(
                "Monthly cost: $%.2f%n",
                selected.monthlyCost(policy.capacityGb()));

        StorageService service =
                new StorageService(selected, 32);

        for (IoRequest request : buildWorkload()) {
            service.execute(request);
        }

        Metrics metrics = service.metrics();

        System.out.println("\nWorkload metrics");
        System.out.println("Requests: " + metrics.requests);
        System.out.println("Reads: " + metrics.reads);
        System.out.println("Writes: " + metrics.writes);
        System.out.printf(
                "Cache hit ratio: %.2f%%%n",
                metrics.cacheHitRatio() * 100);
        System.out.printf(
                "Average latency: %.4f ms%n",
                metrics.averageLatencyMs());
        System.out.printf(
                "Modeled throughput: %.2f MB/s%n",
                metrics.modeledThroughputMbps());

        System.out.println("\nRequest-size sensitivity");

        for (int sizeKb : List.of(4, 64, 256)) {
            System.out.printf(
                    "%d KB sustainable IOPS: %.0f%n",
                    sizeKb,
                    selected.sustainableIops(sizeKb));
        }

        System.out.println("\nPolicy observations");
        System.out.println(
                "Latency-sensitive random workloads benefit from "
                        + "low-latency media and sufficient IOPS.");
        System.out.println(
                "Large sequential workloads can become throughput-limited "
                        + "before reaching the device IOPS ceiling.");
        System.out.println(
                "Caching improves effective latency when access locality "
                        + "is high, but consumes memory and requires "
                        + "coherency and eviction policies.");
    }
}
