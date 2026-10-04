#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

/*
 * Enterprise Storage Virtualization Case Study
 *
 * Scenario:
 * A virtualization cluster exposes virtual disks to application servers.
 * The servers must not depend on the physical identity of the underlying
 * storage devices.
 *
 * Architecture:
 *
 *   Application VM
 *        |
 *   Virtual Disk
 *        |
 *   Logical Volume
 *        |
 *   Storage Pool
 *        |
 *   Extent Mapper
 *        |
 *   Physical Devices
 *
 * The program demonstrates allocation, logical-to-physical translation,
 * thin provisioning, snapshot metadata, device failure, validation,
 * and merge-like reconstruction of the storage state.
 */

enum class DeviceState {
    Online,
    Degraded,
    Failed
};

enum class VolumeMode {
    Thick,
    Thin
};

struct PhysicalDevice {
    std::string id;
    std::size_t capacityGB;
    std::size_t usedGB{0};
    DeviceState state{DeviceState::Online};

    std::size_t freeGB() const {
        return capacityGB - usedGB;
    }
};

struct Extent {
    std::size_t id;
    std::string deviceId;
    std::size_t sizeGB;
    std::string volumeName;
};

struct LogicalBlock {
    std::size_t block;
    std::string payload;
    std::size_t generation;
};

struct Snapshot {
    std::string name;
    std::string volumeName;
    std::size_t generation;
    std::map<std::size_t, std::string> blockHashes;
};

class StorageException : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class CapacityException : public StorageException {
public:
    using StorageException::StorageException;
};

class ValidationException : public StorageException {
public:
    using StorageException::StorageException;
};

class StoragePool {
private:
    std::string name_;
    std::size_t extentSizeGB_;
    std::size_t nextExtentId_{1};
    std::size_t generation_{0};

    std::map<std::string, PhysicalDevice> devices_;
    std::map<std::size_t, Extent> extents_;

    struct Volume {
        std::string name;
        std::size_t virtualCapacityGB;
        VolumeMode mode;
        std::vector<std::size_t> extentIds;
        std::map<std::size_t, LogicalBlock> blocks;
    };

    std::map<std::string, Volume> volumes_;
    std::map<std::string, Snapshot> snapshots_;

    static std::string pseudoHash(const std::string& value) {
        /*
         * The case study needs deterministic integrity metadata without
         * requiring a third-party cryptographic library. This is not intended
         * as a production cryptographic hash.
         */
        std::size_t hash = std::hash<std::string>{}(value);
        return std::to_string(hash);
    }

    PhysicalDevice& chooseDevice() {
        auto candidate = devices_.end();

        for (auto it = devices_.begin(); it != devices_.end(); ++it) {
            if (it->second.state == DeviceState::Failed ||
                it->second.freeGB() < extentSizeGB_) {
                continue;
            }

            if (candidate == devices_.end()) {
                candidate = it;
                continue;
            }

            const double currentUtilization =
                static_cast<double>(it->second.usedGB) /
                static_cast<double>(it->second.capacityGB);

            const double candidateUtilization =
                static_cast<double>(candidate->second.usedGB) /
                static_cast<double>(candidate->second.capacityGB);

            if (currentUtilization < candidateUtilization) {
                candidate = it;
            }
        }

        if (candidate == devices_.end()) {
            throw CapacityException(
                "The storage pool cannot allocate another extent."
            );
        }

        return candidate->second;
    }

public:
    StoragePool(std::string name, std::size_t extentSizeGB)
        : name_(std::move(name)), extentSizeGB_(extentSizeGB) {
        if (extentSizeGB_ == 0) {
            throw ValidationException("Extent size cannot be zero.");
        }
    }

    void addDevice(const std::string& id, std::size_t capacityGB) {
        if (capacityGB == 0) {
            throw ValidationException("Physical capacity must be positive.");
        }

        if (devices_.contains(id)) {
            throw ValidationException("Duplicate physical device: " + id);
        }

        devices_.emplace(id, PhysicalDevice{id, capacityGB});
    }

    std::size_t physicalCapacityGB() const {
        std::size_t total = 0;
        for (const auto& [_, device] : devices_) {
            total += device.capacityGB;
        }
        return total;
    }

    std::size_t physicalUsedGB() const {
        std::size_t total = 0;
        for (const auto& [_, device] : devices_) {
            total += device.usedGB;
        }
        return total;
    }

    std::size_t physicalFreeGB() const {
        return physicalCapacityGB() - physicalUsedGB();
    }

    std::size_t allocateExtent(const std::string& volumeName) {
        PhysicalDevice& device = chooseDevice();

        if (device.freeGB() < extentSizeGB_) {
            throw CapacityException("Selected device has insufficient space.");
        }

        device.usedGB += extentSizeGB_;

        const std::size_t extentId = nextExtentId_++;

        extents_.emplace(
            extentId,
            Extent{
                extentId,
                device.id,
                extentSizeGB_,
                volumeName
            }
        );

        return extentId;
    }

    void createVolume(
        const std::string& name,
        std::size_t virtualCapacityGB,
        VolumeMode mode
    ) {
        if (virtualCapacityGB == 0) {
            throw ValidationException(
                "Logical volume capacity must be positive."
            );
        }

        if (volumes_.contains(name)) {
            throw ValidationException("Duplicate logical volume: " + name);
        }

        if (mode == VolumeMode::Thick &&
            virtualCapacityGB > physicalFreeGB()) {
            throw CapacityException(
                "Insufficient physical capacity for thick provisioning."
            );
        }

        volumes_.emplace(
            name,
            Volume{
                name,
                virtualCapacityGB,
                mode,
                {},
                {}
            }
        );

        if (mode == VolumeMode::Thick) {
            for (std::size_t i = 0; i < virtualCapacityGB; ++i) {
                volumes_.at(name).extentIds.push_back(
                    allocateExtent(name)
                );
            }
        }
    }

    void write(
        const std::string& volumeName,
        std::size_t logicalBlock,
        const std::string& payload
    ) {
        auto volumeIt = volumes_.find(volumeName);

        if (volumeIt == volumes_.end()) {
            throw ValidationException("Unknown logical volume.");
        }

        Volume& volume = volumeIt->second;

        /*
         * Sixteen logical blocks are mapped to one one-GB extent in this
         * simplified model. Real systems use much smaller physical sectors,
         * pages, chunks, or extents.
         */
        const std::size_t maximumBlocks =
            volume.virtualCapacityGB * 16;

        if (logicalBlock >= maximumBlocks) {
            throw ValidationException(
                "Logical block is outside the virtual disk."
            );
        }

        if (volume.mode == VolumeMode::Thin) {
            const std::size_t requiredExtent =
                logicalBlock / 16;

            while (volume.extentIds.size() <= requiredExtent) {
                if (volume.extentIds.size() >= volume.virtualCapacityGB) {
                    throw CapacityException(
                        "Thin volume reached its configured virtual capacity."
                    );
                }

                volume.extentIds.push_back(
                    allocateExtent(volumeName)
                );
            }
        }

        ++generation_;

        volume.blocks[logicalBlock] = LogicalBlock{
            logicalBlock,
            payload,
            generation_
        };
    }

    std::optional<std::string> read(
        const std::string& volumeName,
        std::size_t logicalBlock
    ) const {
        auto volumeIt = volumes_.find(volumeName);

        if (volumeIt == volumes_.end()) {
            throw ValidationException("Unknown logical volume.");
        }

        const Volume& volume = volumeIt->second;

        if (logicalBlock >= volume.virtualCapacityGB * 16) {
            throw ValidationException("Logical block is outside volume.");
        }

        auto blockIt = volume.blocks.find(logicalBlock);

        if (blockIt == volume.blocks.end()) {
            /*
             * Sparse blocks in a thin volume do not require physical storage
             * until written. Returning nullopt distinguishes "unwritten"
             * from an actual empty string stored by the guest.
             */
            return std::nullopt;
        }

        return blockIt->second.payload;
    }

    void createSnapshot(
        const std::string& snapshotName,
        const std::string& volumeName
    ) {
        if (snapshots_.contains(snapshotName)) {
            throw ValidationException("Duplicate snapshot.");
        }

        auto volumeIt = volumes_.find(volumeName);

        if (volumeIt == volumes_.end()) {
            throw ValidationException("Unknown volume.");
        }

        Snapshot snapshot{
            snapshotName,
            volumeName,
            generation_,
            {}
        };

        for (const auto& [blockNumber, block] : volumeIt->second.blocks) {
            snapshot.blockHashes[blockNumber] = pseudoHash(block.payload);
        }

        snapshots_.emplace(snapshotName, std::move(snapshot));
    }

    bool verifySnapshot(const std::string& snapshotName) const {
        auto snapshotIt = snapshots_.find(snapshotName);

        if (snapshotIt == snapshots_.end()) {
            throw ValidationException("Unknown snapshot.");
        }

        const Snapshot& snapshot = snapshotIt->second;
        const Volume& volume = volumes_.at(snapshot.volumeName);

        for (const auto& [blockNumber, expectedHash] :
             snapshot.blockHashes) {

            auto blockIt = volume.blocks.find(blockNumber);

            if (blockIt == volume.blocks.end()) {
                return false;
            }

            if (pseudoHash(blockIt->second.payload) != expectedHash) {
                return false;
            }
        }

        return true;
    }

    void failDevice(const std::string& deviceId) {
        auto it = devices_.find(deviceId);

        if (it == devices_.end()) {
            throw ValidationException("Unknown physical device.");
        }

        it->second.state = DeviceState::Failed;
    }

    std::string volumeHealth(const std::string& volumeName) const {
        const Volume& volume = volumes_.at(volumeName);

        bool failed = false;

        for (std::size_t extentId : volume.extentIds) {
            const std::string& deviceId =
                extents_.at(extentId).deviceId;

            if (devices_.at(deviceId).state == DeviceState::Failed) {
                failed = true;
                break;
            }
        }

        return failed ? "DEGRADED" : "HEALTHY";
    }

    void printArchitecture() const {
        std::cout << "\nStorage Pool: " << name_ << "\n";
        std::cout << "Physical capacity: "
                  << physicalCapacityGB() << " GB\n";
        std::cout << "Physical used: "
                  << physicalUsedGB() << " GB\n";
        std::cout << "Physical free: "
                  << physicalFreeGB() << " GB\n";

        std::cout << "\nPhysical devices\n";

        for (const auto& [id, device] : devices_) {
            std::cout
                << "  " << id
                << " capacity=" << device.capacityGB
                << "GB used=" << device.usedGB
                << "GB state=";

            switch (device.state) {
                case DeviceState::Online:
                    std::cout << "online";
                    break;
                case DeviceState::Degraded:
                    std::cout << "degraded";
                    break;
                case DeviceState::Failed:
                    std::cout << "failed";
                    break;
            }

            std::cout << "\n";
        }

        std::cout << "\nLogical volumes\n";

        for (const auto& [name, volume] : volumes_) {
            std::cout
                << "  " << name
                << " virtual=" << volume.virtualCapacityGB
                << "GB allocated=" << volume.extentIds.size()
                << "GB mode="
                << (volume.mode == VolumeMode::Thin ? "thin" : "thick")
                << " health=" << volumeHealth(name)
                << "\n";
        }
    }
};

int main() {
    try {
        StoragePool pool("enterprise-vm-pool", 1);

        pool.addDevice("nvme-01", 10);
        pool.addDevice("nvme-02", 14);
        pool.addDevice("ssd-archive", 20);

        /*
         * Thick provisioning reserves the requested physical capacity
         * immediately. The virtual capacity and physical allocation are
         * therefore approximately equal in this simplified extent model.
         */
        pool.createVolume(
            "database",
            8,
            VolumeMode::Thick
        );

        /*
         * Thin provisioning advertises 12 GB to the consumer but initially
         * consumes no physical extents. Physical allocation follows writes.
         */
        pool.createVolume(
            "analytics",
            12,
            VolumeMode::Thin
        );

        pool.write(
            "database",
            0,
            "database-superblock"
        );

        pool.write(
            "database",
            1,
            "transaction-log-metadata"
        );

        pool.write(
            "analytics",
            48,
            "2026-quarterly-analytics"
        );

        pool.createSnapshot(
            "database-before-upgrade",
            "database"
        );

        pool.write(
            "database",
            1,
            "transaction-log-metadata-v2"
        );

        std::cout << "Database block 0: ";
        auto databaseBlock = pool.read("database", 0);

        if (databaseBlock.has_value()) {
            std::cout << *databaseBlock << "\n";
        }

        std::cout
            << "Snapshot verification after modification: "
            << std::boolalpha
            << pool.verifySnapshot("database-before-upgrade")
            << "\n";

        pool.printArchitecture();

        /*
         * Failing a device demonstrates why virtualization separates the
         * consumer-facing identity from physical placement. The virtual
         * volume can remain addressable even though its health changes.
         */
        pool.failDevice("nvme-01");

        std::cout
            << "\nDatabase health after nvme-01 failure: "
            << pool.volumeHealth("database")
            << "\n";

        try {
            pool.write(
                "database",
                100000,
                "invalid-block"
            );
        } catch (const StorageException& error) {
            std::cout
                << "Expected validation failure: "
                << error.what()
                << "\n";
        }

        try {
            pool.createVolume(
                "oversized",
                1000,
                VolumeMode::Thick
            );
        } catch (const StorageException& error) {
            std::cout
                << "Expected capacity failure: "
                << error.what()
                << "\n";
        }

        pool.printArchitecture();
    }
    catch (const std::exception& error) {
        std::cerr
            << "Storage virtualization engine error: "
            << error.what()
            << "\n";
        return 1;
    }

    return 0;
}
