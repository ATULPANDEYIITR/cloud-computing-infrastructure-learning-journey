import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/*
 * Enterprise Storage Virtualization Model
 *
 * The domain separates:
 *
 * PhysicalDevice -> StoragePool -> LogicalVolume -> VirtualDisk
 *
 * Storage policies are explicit Java types rather than scattered conditional
 * statements. This makes allocation and merge-like policy decisions easier
 * to test and change.
 */
public class StorageVirtualizationEnterprise {

    enum DeviceState {
        ONLINE,
        DEGRADED,
        FAILED
    }

    enum VolumeMode {
        THICK,
        THIN
    }

    enum VolumeState {
        ONLINE,
        READ_ONLY,
        OFFLINE
    }

    static class StorageException extends RuntimeException {
        StorageException(String message) {
            super(message);
        }
    }

    static class CapacityException extends StorageException {
        CapacityException(String message) {
            super(message);
        }
    }

    static class InvalidStateException extends StorageException {
        InvalidStateException(String message) {
            super(message);
        }
    }

    record PhysicalDevice(
        String id,
        int capacityGB,
        int usedGB,
        DeviceState state
    ) {
        PhysicalDevice {
            Objects.requireNonNull(id);
            if (capacityGB <= 0 || usedGB < 0 || usedGB > capacityGB) {
                throw new IllegalArgumentException(
                    "Invalid physical device capacity."
                );
            }
        }

        int freeGB() {
            return capacityGB - usedGB;
        }

        PhysicalDevice allocate(int amountGB) {
            if (state == DeviceState.FAILED) {
                throw new InvalidStateException(
                    "Failed device " + id + " cannot allocate storage."
                );
            }

            if (amountGB > freeGB()) {
                throw new CapacityException(
                    "Device " + id + " has insufficient capacity."
                );
            }

            return new PhysicalDevice(
                id,
                capacityGB,
                usedGB + amountGB,
                state
            );
        }

        PhysicalDevice fail() {
            return new PhysicalDevice(
                id,
                capacityGB,
                usedGB,
                DeviceState.FAILED
            );
        }
    }

    record Extent(
        long id,
        String deviceId,
        int sizeGB,
        String volumeName
    ) {}

    record BlockData(
        long generation,
        String value
    ) {}

    record Snapshot(
        String name,
        String volumeName,
        long generation,
        Map<Integer, String> blockHashes
    ) {
        Snapshot {
            blockHashes = Map.copyOf(blockHashes);
        }
    }

    interface AllocationPolicy {
        PhysicalDevice choose(List<PhysicalDevice> devices, int extentSizeGB);
    }

    /*
     * Least-used allocation spreads new extents toward the device with the
     * lowest relative utilization. This is intentionally different from a
     * simple largest-free-space policy.
     */
    static class LeastUsedPolicy implements AllocationPolicy {
        @Override
        public PhysicalDevice choose(
            List<PhysicalDevice> devices,
            int extentSizeGB
        ) {
            return devices.stream()
                .filter(device ->
                    device.state() != DeviceState.FAILED &&
                    device.freeGB() >= extentSizeGB
                )
                .min(
                    Comparator
                        .comparingDouble(
                            device ->
                                (double) device.usedGB()
                                / device.capacityGB()
                        )
                        .thenComparing(PhysicalDevice::id)
                )
                .orElseThrow(() ->
                    new CapacityException(
                        "No physical device can accept an extent."
                    )
                );
        }
    }

    static class LogicalVolume {
        private final String name;
        private final int virtualCapacityGB;
        private final VolumeMode mode;
        private VolumeState state = VolumeState.ONLINE;

        private final List<Long> extentIds = new ArrayList<>();
        private final Map<Integer, BlockData> blocks = new HashMap<>();

        LogicalVolume(
            String name,
            int virtualCapacityGB,
            VolumeMode mode
        ) {
            if (virtualCapacityGB <= 0) {
                throw new IllegalArgumentException(
                    "Virtual capacity must be positive."
                );
            }

            this.name = Objects.requireNonNull(name);
            this.virtualCapacityGB = virtualCapacityGB;
            this.mode = Objects.requireNonNull(mode);
        }

        String name() {
            return name;
        }

        int virtualCapacityGB() {
            return virtualCapacityGB;
        }

        VolumeMode mode() {
            return mode;
        }

        VolumeState state() {
            return state;
        }

        void setState(VolumeState state) {
            this.state = Objects.requireNonNull(state);
        }

        List<Long> extentIds() {
            return List.copyOf(extentIds);
        }

        Map<Integer, BlockData> blocks() {
            return blocks;
        }

        void addExtent(long extentId) {
            extentIds.add(extentId);
        }
    }

    static class StoragePool {
        private final String name;
        private final int extentSizeGB;
        private final AllocationPolicy allocationPolicy;

        private final Map<String, PhysicalDevice> devices =
            new HashMap<>();

        private final Map<String, LogicalVolume> volumes =
            new HashMap<>();

        private final Map<Long, Extent> extents =
            new HashMap<>();

        private final Map<String, Snapshot> snapshots =
            new HashMap<>();

        private long nextExtentId = 1;
        private long generation = 0;

        StoragePool(
            String name,
            int extentSizeGB,
            AllocationPolicy allocationPolicy
        ) {
            if (extentSizeGB <= 0) {
                throw new IllegalArgumentException(
                    "Extent size must be positive."
                );
            }

            this.name = Objects.requireNonNull(name);
            this.extentSizeGB = extentSizeGB;
            this.allocationPolicy =
                Objects.requireNonNull(allocationPolicy);
        }

        void addDevice(PhysicalDevice device) {
            if (devices.containsKey(device.id())) {
                throw new InvalidStateException(
                    "Duplicate device " + device.id()
                );
            }

            devices.put(device.id(), device);
        }

        int physicalCapacityGB() {
            return devices.values().stream()
                .mapToInt(PhysicalDevice::capacityGB)
                .sum();
        }

        int physicalUsedGB() {
            return devices.values().stream()
                .mapToInt(PhysicalDevice::usedGB)
                .sum();
        }

        int physicalFreeGB() {
            return physicalCapacityGB() - physicalUsedGB();
        }

        private long allocateExtent(String volumeName) {
            PhysicalDevice selected =
                allocationPolicy.choose(
                    new ArrayList<>(devices.values()),
                    extentSizeGB
                );

            PhysicalDevice updated =
                selected.allocate(extentSizeGB);

            devices.put(updated.id(), updated);

            long id = nextExtentId++;

            extents.put(
                id,
                new Extent(
                    id,
                    updated.id(),
                    extentSizeGB,
                    volumeName
                )
            );

            return id;
        }

        LogicalVolume createVolume(
            String name,
            int capacityGB,
            VolumeMode mode
        ) {
            if (volumes.containsKey(name)) {
                throw new InvalidStateException(
                    "Duplicate volume " + name
                );
            }

            if (mode == VolumeMode.THICK &&
                capacityGB > physicalFreeGB()) {
                throw new CapacityException(
                    "Insufficient capacity for thick volume " + name
                );
            }

            LogicalVolume volume =
                new LogicalVolume(name, capacityGB, mode);

            volumes.put(name, volume);

            if (mode == VolumeMode.THICK) {
                for (int i = 0; i < capacityGB; i++) {
                    volume.addExtent(
                        allocateExtent(name)
                    );
                }
            }

            return volume;
        }

        private LogicalVolume requireVolume(String name) {
            LogicalVolume volume = volumes.get(name);

            if (volume == null) {
                throw new InvalidStateException(
                    "Unknown volume " + name
                );
            }

            return volume;
        }

        private void validateBlock(
            LogicalVolume volume,
            int block
        ) {
            int maximumBlocks =
                volume.virtualCapacityGB() * 16;

            if (block < 0 || block >= maximumBlocks) {
                throw new InvalidStateException(
                    "Block " + block +
                    " is outside virtual volume " +
                    volume.name()
                );
            }
        }

        private void ensureThinCapacity(
            LogicalVolume volume,
            int block
        ) {
            int requiredExtent = block / 16;

            while (volume.extentIds().size() <= requiredExtent) {
                if (volume.extentIds().size() >=
                    volume.virtualCapacityGB()) {
                    throw new CapacityException(
                        "Thin volume reached virtual capacity."
                    );
                }

                volume.addExtent(
                    allocateExtent(volume.name())
                );
            }
        }

        void write(
            String volumeName,
            int block,
            String value
        ) {
            LogicalVolume volume =
                requireVolume(volumeName);

            if (volume.state() != VolumeState.ONLINE) {
                throw new InvalidStateException(
                    "Volume is not writable: " + volumeName
                );
            }

            validateBlock(volume, block);

            if (volume.mode() == VolumeMode.THIN) {
                ensureThinCapacity(volume, block);
            }

            generation++;

            volume.blocks().put(
                block,
                new BlockData(generation, value)
            );
        }

        Optional<String> read(
            String volumeName,
            int block
        ) {
            LogicalVolume volume =
                requireVolume(volumeName);

            validateBlock(volume, block);

            BlockData data =
                volume.blocks().get(block);

            return data == null
                ? Optional.empty()
                : Optional.of(data.value());
        }

        void createSnapshot(
            String snapshotName,
            String volumeName
        ) {
            if (snapshots.containsKey(snapshotName)) {
                throw new InvalidStateException(
                    "Duplicate snapshot."
                );
            }

            LogicalVolume volume =
                requireVolume(volumeName);

            Map<Integer, String> hashes =
                new HashMap<>();

            for (Map.Entry<Integer, BlockData> entry :
                 volume.blocks().entrySet()) {

                hashes.put(
                    entry.getKey(),
                    Integer.toHexString(
                        entry.getValue().value().hashCode()
                    )
                );
            }

            snapshots.put(
                snapshotName,
                new Snapshot(
                    snapshotName,
                    volumeName,
                    generation,
                    hashes
                )
            );
        }

        boolean verifySnapshot(String snapshotName) {
            Snapshot snapshot =
                snapshots.get(snapshotName);

            if (snapshot == null) {
                throw new InvalidStateException(
                    "Unknown snapshot."
                );
            }

            LogicalVolume volume =
                requireVolume(snapshot.volumeName());

            for (Map.Entry<Integer, String> entry :
                 snapshot.blockHashes().entrySet()) {

                BlockData current =
                    volume.blocks().get(entry.getKey());

                if (current == null) {
                    return false;
                }

                String currentHash =
                    Integer.toHexString(
                        current.value().hashCode()
                    );

                if (!currentHash.equals(entry.getValue())) {
                    return false;
                }
            }

            return true;
        }

        void failDevice(String deviceId) {
            PhysicalDevice device =
                devices.get(deviceId);

            if (device == null) {
                throw new InvalidStateException(
                    "Unknown device."
                );
            }

            devices.put(
                deviceId,
                device.fail()
            );

            for (LogicalVolume volume : volumes.values()) {
                boolean affected =
                    volume.extentIds().stream()
                        .map(extents::get)
                        .filter(Objects::nonNull)
                        .anyMatch(
                            extent ->
                                extent.deviceId()
                                    .equals(deviceId)
                        );

                if (affected) {
                    volume.setState(
                        VolumeState.READ_ONLY
                    );
                }
            }
        }

        void printReport() {
            System.out.println(
                "\nPool: " + name
            );

            System.out.println(
                "Physical capacity: " +
                physicalCapacityGB() + " GB"
            );

            System.out.println(
                "Physical used: " +
                physicalUsedGB() + " GB"
            );

            System.out.println(
                "Physical free: " +
                physicalFreeGB() + " GB"
            );

            System.out.println("\nVolumes:");

            volumes.values().stream()
                .sorted(Comparator.comparing(LogicalVolume::name))
                .forEach(volume ->
                    System.out.printf(
                        "  %s virtual=%dGB allocated=%dGB " +
                        "mode=%s state=%s%n",
                        volume.name(),
                        volume.virtualCapacityGB(),
                        volume.extentIds().size(),
                        volume.mode(),
                        volume.state()
                    )
                );
        }
    }

    static class VirtualDisk {
        private final String diskId;
        private final StoragePool pool;
        private final String volumeName;

        VirtualDisk(
            String diskId,
            StoragePool pool,
            String volumeName
        ) {
            this.diskId = Objects.requireNonNull(diskId);
            this.pool = Objects.requireNonNull(pool);
            this.volumeName = Objects.requireNonNull(volumeName);
        }

        void write(int block, String value) {
            pool.write(volumeName, block, value);
        }

        Optional<String> read(int block) {
            return pool.read(volumeName, block);
        }

        String diskId() {
            return diskId;
        }
    }

    public static void main(String[] args) {
        StoragePool pool =
            new StoragePool(
                "enterprise-pool",
                1,
                new LeastUsedPolicy()
            );

        pool.addDevice(
            new PhysicalDevice(
                "nvme-01",
                12,
                0,
                DeviceState.ONLINE
            )
        );

        pool.addDevice(
            new PhysicalDevice(
                "nvme-02",
                16,
                0,
                DeviceState.ONLINE
            )
        );

        pool.addDevice(
            new PhysicalDevice(
                "ssd-archive",
                24,
                0,
                DeviceState.ONLINE
            )
        );

        pool.createVolume(
            "production-db",
            8,
            VolumeMode.THICK
        );

        pool.createVolume(
            "event-stream",
            14,
            VolumeMode.THIN
        );

        VirtualDisk databaseDisk =
            new VirtualDisk(
                "vdisk-db-01",
                pool,
                "production-db"
            );

        databaseDisk.write(
            0,
            "database-superblock"
        );

        databaseDisk.write(
            1,
            "database-catalog"
        );

        pool.write(
            "event-stream",
            64,
            "event-2026-10-05"
        );

        pool.createSnapshot(
            "db-before-schema-change",
            "production-db"
        );

        databaseDisk.write(
            1,
            "database-catalog-v2"
        );

        System.out.println(
            "Read through virtual disk " +
            databaseDisk.diskId() +
            ": " +
            databaseDisk.read(0).orElse("<unwritten>")
        );

        System.out.println(
            "Snapshot valid after current-volume change: " +
            pool.verifySnapshot(
                "db-before-schema-change"
            )
        );

        pool.printReport();

        pool.failDevice("nvme-01");

        pool.printReport();

        try {
            databaseDisk.write(
                5000,
                "invalid"
            );
        } catch (StorageException exception) {
            System.out.println(
                "Expected validation error: " +
                exception.getMessage()
            );
        }

        try {
            pool.createVolume(
                "oversized-volume",
                1000,
                VolumeMode.THICK
            );
        } catch (StorageException exception) {
            System.out.println(
                "Expected capacity error: " +
                exception.getMessage()
            );
        }
    }
}
