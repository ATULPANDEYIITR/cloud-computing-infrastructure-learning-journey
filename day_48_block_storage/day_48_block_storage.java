import java.time.Instant;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class BlockStorageEnterpriseDemo {

    enum VolumeType {
        GP3,
        IO2
    }

    enum VolumeState {
        AVAILABLE,
        ATTACHED,
        DETACHING
    }

    enum SnapshotState {
        CREATING,
        COMPLETED
    }

    record Attachment(
        String instanceId,
        String device,
        Instant attachedAt
    ) {}

    record Workload(
        long requestsPerSecond,
        int ioKiB,
        int durationSeconds
    ) {
        Workload {
            if (requestsPerSecond < 0) {
                throw new IllegalArgumentException(
                    "Requests per second cannot be negative"
                );
            }

            if (ioKiB <= 0 || durationSeconds <= 0) {
                throw new IllegalArgumentException(
                    "I/O size and duration must be positive"
                );
            }
        }
    }

    static final class Snapshot {
        private final String id;
        private final String sourceVolumeId;
        private final String parentSnapshotId;
        private final int sizeGiB;
        private SnapshotState state;
        private int progress;

        Snapshot(
            String id,
            String sourceVolumeId,
            String parentSnapshotId,
            int sizeGiB
        ) {
            this.id = id;
            this.sourceVolumeId = sourceVolumeId;
            this.parentSnapshotId = parentSnapshotId;
            this.sizeGiB = sizeGiB;
            this.state = SnapshotState.CREATING;
            this.progress = 0;
        }

        void advance(int amount) {
            progress = Math.min(100, progress + amount);

            if (progress == 100) {
                state = SnapshotState.COMPLETED;
            }
        }

        String id() {
            return id;
        }

        String parentSnapshotId() {
            return parentSnapshotId;
        }

        SnapshotState state() {
            return state;
        }

        int sizeGiB() {
            return sizeGiB;
        }
    }

    static final class BlockVolume {
        private final String id;
        private final int sizeGiB;
        private final VolumeType type;
        private final boolean encrypted;

        private int iops;
        private int throughputMiBs;
        private VolumeState state;
        private Attachment attachment;

        BlockVolume(
            String id,
            int sizeGiB,
            VolumeType type,
            int iops,
            int throughputMiBs,
            boolean encrypted
        ) {
            this.id = Objects.requireNonNull(id);
            this.sizeGiB = sizeGiB;
            this.type = Objects.requireNonNull(type);
            this.iops = iops;
            this.throughputMiBs = throughputMiBs;
            this.encrypted = encrypted;
            this.state = VolumeState.AVAILABLE;

            validate();
        }

        private void validate() {
            if (sizeGiB <= 0) {
                throw new IllegalArgumentException(
                    "Volume size must be positive"
                );
            }

            if (type == VolumeType.GP3) {
                if (iops < 3000 || iops > 16000) {
                    throw new IllegalArgumentException(
                        "gp3 IOPS must be between 3,000 and 16,000"
                    );
                }

                if (throughputMiBs < 125 || throughputMiBs > 1000) {
                    throw new IllegalArgumentException(
                        "gp3 throughput must be between 125 and 1,000 MiB/s"
                    );
                }
            }

            if (type == VolumeType.IO2 && (iops < 100 || iops > 64000)) {
                throw new IllegalArgumentException(
                    "io2 IOPS must be between 100 and 64,000"
                );
            }
        }

        void attach(String instanceId, String device) {
            if (state != VolumeState.AVAILABLE) {
                throw new IllegalStateException(
                    "Volume is already attached or transitioning"
                );
            }

            if (instanceId == null || instanceId.isBlank()) {
                throw new IllegalArgumentException(
                    "Instance ID is required"
                );
            }

            if (!device.startsWith("/dev/")) {
                throw new IllegalArgumentException(
                    "Invalid block-device path"
                );
            }

            attachment = new Attachment(
                instanceId,
                device,
                Instant.now()
            );

            state = VolumeState.ATTACHED;
        }

        void detach() {
            if (state != VolumeState.ATTACHED) {
                throw new IllegalStateException(
                    "Only attached volumes can be detached"
                );
            }

            state = VolumeState.DETACHING;

            /*
             * The explicit DETACHING state matters in an enterprise system:
             * clients should not assume that a control-plane detach request
             * means the operating system has immediately released the device.
             */
            attachment = null;
            state = VolumeState.AVAILABLE;
        }

        void modifyPerformance(int newIops, int newThroughputMiBs) {
            int oldIops = iops;
            int oldThroughput = throughputMiBs;

            iops = newIops;
            throughputMiBs = newThroughputMiBs;

            try {
                validate();
            } catch (RuntimeException exception) {
                iops = oldIops;
                throughputMiBs = oldThroughput;
                throw exception;
            }
        }

        double estimateLatency(Workload workload) {
            double requestedMiBs =
                workload.requestsPerSecond() *
                workload.ioKiB() /
                1024.0;

            double iopsPressure =
                (double) workload.requestsPerSecond() / iops;

            double throughputPressure =
                requestedMiBs / throughputMiBs;

            double pressure =
                Math.max(iopsPressure, throughputPressure);

            if (pressure <= 1.0) {
                return 1.2 * (1.0 + pressure);
            }

            return 1.2 * (1.0 + pressure * pressure * 8.0);
        }

        String id() {
            return id;
        }

        int iops() {
            return iops;
        }

        int throughputMiBs() {
            return throughputMiBs;
        }

        boolean encrypted() {
            return encrypted;
        }

        VolumeState state() {
            return state;
        }

        @Override
        public String toString() {
            return "%s: %d GiB, %s, %d IOPS, %d MiB/s, encrypted=%s, state=%s"
                .formatted(
                    id,
                    sizeGiB,
                    type,
                    iops,
                    throughputMiBs,
                    encrypted,
                    state
                );
        }
    }

    interface StoragePolicy {
        boolean accepts(BlockVolume volume, Workload workload);

        String name();
    }

    static final class ProductionDatabasePolicy implements StoragePolicy {
        private final double maximumLatencyMs;
        private final int minimumIops;
        private final int minimumThroughputMiBs;

        ProductionDatabasePolicy(
            double maximumLatencyMs,
            int minimumIops,
            int minimumThroughputMiBs
        ) {
            this.maximumLatencyMs = maximumLatencyMs;
            this.minimumIops = minimumIops;
            this.minimumThroughputMiBs = minimumThroughputMiBs;
        }

        @Override
        public boolean accepts(BlockVolume volume, Workload workload) {
            return volume.encrypted()
                && volume.iops() >= minimumIops
                && volume.throughputMiBs() >= minimumThroughputMiBs
                && volume.estimateLatency(workload) <= maximumLatencyMs;
        }

        @Override
        public String name() {
            return "production-database-storage";
        }
    }

    static final class StorageService {
        private final Map<String, BlockVolume> volumes = new HashMap<>();
        private final Map<String, Snapshot> snapshots = new HashMap<>();

        private int volumeSequence;
        private int snapshotSequence;

        BlockVolume createVolume(
            int sizeGiB,
            VolumeType type,
            int iops,
            int throughputMiBs,
            boolean encrypted
        ) {
            String id = "vol-%04d".formatted(++volumeSequence);

            BlockVolume volume = new BlockVolume(
                id,
                sizeGiB,
                type,
                iops,
                throughputMiBs,
                encrypted
            );

            volumes.put(id, volume);
            return volume;
        }

        Snapshot createSnapshot(
            String volumeId,
            String parentSnapshotId
        ) {
            BlockVolume volume = requireVolume(volumeId);

            if (
                parentSnapshotId != null &&
                !snapshots.containsKey(parentSnapshotId)
            ) {
                throw new IllegalArgumentException(
                    "Parent snapshot does not exist"
                );
            }

            Snapshot snapshot = new Snapshot(
                "snap-%04d".formatted(++snapshotSequence),
                volumeId,
                parentSnapshotId,
                volume.sizeGiB
            );

            snapshots.put(snapshot.id(), snapshot);

            while (snapshot.state() != SnapshotState.COMPLETED) {
                snapshot.advance(25);
            }

            return snapshot;
        }

        BlockVolume restoreSnapshot(
            String snapshotId,
            VolumeType targetType
        ) {
            Snapshot snapshot = snapshots.get(snapshotId);

            if (snapshot == null) {
                throw new IllegalArgumentException(
                    "Snapshot does not exist"
                );
            }

            if (snapshot.state() != SnapshotState.COMPLETED) {
                throw new IllegalStateException(
                    "Snapshot is not complete"
                );
            }

            return createVolume(
                snapshot.sizeGiB(),
                targetType,
                targetType == VolumeType.GP3 ? 3000 : 10000,
                targetType == VolumeType.GP3 ? 125 : 250,
                true
            );
        }

        private BlockVolume requireVolume(String volumeId) {
            BlockVolume volume = volumes.get(volumeId);

            if (volume == null) {
                throw new IllegalArgumentException(
                    "Volume does not exist: " + volumeId
                );
            }

            return volume;
        }

        List<BlockVolume> inventory() {
            return new ArrayList<>(volumes.values());
        }

        List<String> snapshotLineage(String snapshotId) {
            List<String> lineage = new ArrayList<>();
            Snapshot current = snapshots.get(snapshotId);

            if (current == null) {
                throw new IllegalArgumentException(
                    "Snapshot does not exist"
                );
            }

            while (current != null) {
                lineage.add(current.id());

                if (current.parentSnapshotId() == null) {
                    current = null;
                } else {
                    current = snapshots.get(current.parentSnapshotId());
                }
            }

            return lineage;
        }
    }

    static void databaseStorageScenario() {
        System.out.println("=== Enterprise database storage ===");

        StorageService service = new StorageService();

        BlockVolume database = service.createVolume(
            1024,
            VolumeType.GP3,
            12000,
            500,
            true
        );

        System.out.println(database);

        Workload workload = new Workload(
            18000,
            16,
            60
        );

        StoragePolicy productionPolicy =
            new ProductionDatabasePolicy(
                10.0,
                8000,
                250
            );

        System.out.printf(
            "Estimated workload latency: %.2f ms%n",
            database.estimateLatency(workload)
        );

        System.out.println(
            "Production policy accepted: " +
            productionPolicy.accepts(database, workload)
        );

        database.attach(
            "db-production-01",
            "/dev/sdf"
        );

        try {
            database.attach(
                "db-production-02",
                "/dev/sdg"
            );
        } catch (IllegalStateException exception) {
            System.out.println(
                "Second attachment rejected: " +
                exception.getMessage()
            );
        }

        database.modifyPerformance(
            16000,
            750
        );

        System.out.println("After performance modification:");
        System.out.println(database);

        Snapshot first =
            service.createSnapshot(database.id(), null);

        Snapshot second =
            service.createSnapshot(
                database.id(),
                first.id()
            );

        System.out.println(
            "Snapshot lineage: " +
            service.snapshotLineage(second.id())
        );

        BlockVolume restored =
            service.restoreSnapshot(
                second.id(),
                VolumeType.GP3
            );

        System.out.println(
            "Restored volume: " +
            restored
        );

        database.detach();

        System.out.println(
            "Database volume state: " +
            database.state()
        );
    }

    static void performanceComparison() {
        System.out.println("\n=== Performance dimension comparison ===");

        StorageService service = new StorageService();

        BlockVolume iopsOptimized = service.createVolume(
            500,
            VolumeType.GP3,
            16000,
            125,
            true
        );

        BlockVolume throughputOptimized = service.createVolume(
            500,
            VolumeType.GP3,
            3000,
            1000,
            true
        );

        Workload randomIo = new Workload(
            12000,
            4,
            60
        );

        Workload sequentialIo = new Workload(
            1000,
            512,
            60
        );

        System.out.printf(
            "IOPS-oriented volume, random workload: %.2f ms%n",
            iopsOptimized.estimateLatency(randomIo)
        );

        System.out.printf(
            "Throughput-oriented volume, random workload: %.2f ms%n",
            throughputOptimized.estimateLatency(randomIo)
        );

        System.out.printf(
            "IOPS-oriented volume, sequential workload: %.2f ms%n",
            iopsOptimized.estimateLatency(sequentialIo)
        );

        System.out.printf(
            "Throughput-oriented volume, sequential workload: %.2f ms%n",
            throughputOptimized.estimateLatency(sequentialIo)
        );
    }

    static void invalidConfigurationScenario() {
        System.out.println("\n=== Invalid storage configuration ===");

        StorageService service = new StorageService();

        try {
            service.createVolume(
                100,
                VolumeType.GP3,
                1000,
                125,
                true
            );
        } catch (IllegalArgumentException exception) {
            System.out.println(
                "Configuration rejected: " +
                exception.getMessage()
            );
        }
    }

    public static void main(String[] args) {
        try {
            databaseStorageScenario();
            performanceComparison();
            invalidConfigurationScenario();
        } catch (RuntimeException exception) {
            System.err.println(
                "Storage service failure: " +
                exception.getMessage()
            );
            System.exit(1);
        }
    }
}
