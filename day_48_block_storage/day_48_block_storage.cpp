#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

enum class VolumeType {
    GP3,
    IO2
};

enum class VolumeState {
    Available,
    Attached,
    Detaching
};

struct StatusCheck {
    std::string name;
    bool passed;
};

struct Workload {
    long long requestsPerSecond;
    int ioKiB;
    int durationSeconds;
};

class StorageException : public std::runtime_error {
public:
    explicit StorageException(const std::string& message)
        : std::runtime_error(message) {}
};

class BlockVolume {
private:
    std::string id_;
    int sizeGiB_;
    VolumeType type_;
    int iops_;
    int throughputMiBs_;
    bool encrypted_;
    VolumeState state_;
    std::optional<std::string> instanceId_;
    std::optional<std::string> device_;

public:
    BlockVolume(
        std::string id,
        int sizeGiB,
        VolumeType type,
        int iops,
        int throughputMiBs,
        bool encrypted
    )
        : id_(std::move(id)),
          sizeGiB_(sizeGiB),
          type_(type),
          iops_(iops),
          throughputMiBs_(throughputMiBs),
          encrypted_(encrypted),
          state_(VolumeState::Available) {
        validate();
    }

    void validate() const {
        if (sizeGiB_ <= 0) {
            throw StorageException("Volume size must be positive");
        }

        if (type_ == VolumeType::GP3) {
            if (iops_ < 3000 || iops_ > 16000) {
                throw StorageException("gp3 IOPS must be between 3000 and 16000");
            }

            if (throughputMiBs_ < 125 || throughputMiBs_ > 1000) {
                throw StorageException(
                    "gp3 throughput must be between 125 and 1000 MiB/s"
                );
            }
        }

        if (type_ == VolumeType::IO2) {
            if (iops_ < 100 || iops_ > 64000) {
                throw StorageException(
                    "io2 IOPS must be between 100 and 64000"
                );
            }
        }
    }

    const std::string& id() const {
        return id_;
    }

    int iops() const {
        return iops_;
    }

    int throughputMiBs() const {
        return throughputMiBs_;
    }

    int sizeGiB() const {
        return sizeGiB_;
    }

    VolumeState state() const {
        return state_;
    }

    bool encrypted() const {
        return encrypted_;
    }

    void attach(const std::string& instanceId, const std::string& device) {
        if (state_ != VolumeState::Available) {
            throw StorageException("Volume is not available for attachment");
        }

        if (device.rfind("/dev/", 0) != 0) {
            throw StorageException("Invalid block device path");
        }

        instanceId_ = instanceId;
        device_ = device;
        state_ = VolumeState::Attached;
    }

    void detach() {
        if (state_ != VolumeState::Attached) {
            throw StorageException("Volume is not attached");
        }

        state_ = VolumeState::Detaching;

        // A real storage platform may expose an asynchronous detach state.
        // The case study completes it after the control-plane transition.
        instanceId_.reset();
        device_.reset();
        state_ = VolumeState::Available;
    }

    void modifyPerformance(int newIops, int newThroughputMiBs) {
        int oldIops = iops_;
        int oldThroughput = throughputMiBs_;

        iops_ = newIops;
        throughputMiBs_ = newThroughputMiBs;

        try {
            validate();
        } catch (...) {
            iops_ = oldIops;
            throughputMiBs_ = oldThroughput;
            throw;
        }
    }

    double estimatedLatencyMs(const Workload& workload) const {
        const double requestedMiBs =
            static_cast<double>(workload.requestsPerSecond * workload.ioKiB) /
            1024.0;

        const double iopsPressure =
            static_cast<double>(workload.requestsPerSecond) / iops_;

        const double throughputPressure =
            requestedMiBs / throughputMiBs_;

        const double pressure =
            std::max(iopsPressure, throughputPressure);

        if (pressure <= 1.0) {
            return 1.2 * (1.0 + pressure);
        }

        return 1.2 * (1.0 + pressure * pressure * 8.0);
    }

    void print() const {
        std::cout
            << id_
            << " | "
            << sizeGiB_
            << " GiB | "
            << iops_
            << " IOPS | "
            << throughputMiBs_
            << " MiB/s | encrypted="
            << std::boolalpha
            << encrypted_
            << '\n';
    }
};

struct Snapshot {
    std::string id;
    std::string sourceVolumeId;
    std::optional<std::string> parentSnapshotId;
    int progress;
    bool completed;
};

class RepositoryStoragePolicy {
private:
    int maximumDatabaseLatencyMs_;
    int minimumRequiredIops_;
    int minimumRequiredThroughput_;

public:
    RepositoryStoragePolicy(
        int maximumDatabaseLatencyMs,
        int minimumRequiredIops,
        int minimumRequiredThroughput
    )
        : maximumDatabaseLatencyMs_(maximumDatabaseLatencyMs),
          minimumRequiredIops_(minimumRequiredIops),
          minimumRequiredThroughput_(minimumRequiredThroughput) {}

    bool accepts(
        const BlockVolume& volume,
        const Workload& workload
    ) const {
        if (!volume.encrypted()) {
            return false;
        }

        if (volume.iops() < minimumRequiredIops_) {
            return false;
        }

        if (volume.throughputMiBs() < minimumRequiredThroughput_) {
            return false;
        }

        return volume.estimatedLatencyMs(workload) <= maximumDatabaseLatencyMs_;
    }
};

class StorageGovernanceEngine {
private:
    std::map<std::string, BlockVolume> volumes_;
    std::map<std::string, Snapshot> snapshots_;
    int nextVolumeId_ = 1;
    int nextSnapshotId_ = 1;

public:
    BlockVolume& createVolume(
        int sizeGiB,
        VolumeType type,
        int iops,
        int throughputMiBs,
        bool encrypted = true
    ) {
        std::string id =
            "vol-" + std::to_string(nextVolumeId_++);

        auto [iterator, inserted] = volumes_.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(id),
            std::forward_as_tuple(
                id,
                sizeGiB,
                type,
                iops,
                throughputMiBs,
                encrypted
            )
        );

        if (!inserted) {
            throw StorageException("Volume identifier collision");
        }

        return iterator->second;
    }

    Snapshot& createSnapshot(
        const std::string& volumeId,
        std::optional<std::string> parent = std::nullopt
    ) {
        if (!volumes_.contains(volumeId)) {
            throw StorageException("Snapshot source volume does not exist");
        }

        if (parent.has_value() && !snapshots_.contains(*parent)) {
            throw StorageException("Snapshot parent does not exist");
        }

        std::string id =
            "snap-" + std::to_string(nextSnapshotId_++);

        Snapshot snapshot{
            id,
            volumeId,
            parent,
            0,
            false
        };

        auto [iterator, inserted] = snapshots_.emplace(id, snapshot);

        if (!inserted) {
            throw StorageException("Snapshot identifier collision");
        }

        // The loop models asynchronous snapshot progress while retaining a
        // deterministic program suitable for a technical case study.
        for (int progress = 25; progress <= 100; progress += 25) {
            iterator->second.progress = progress;
        }

        iterator->second.completed = true;
        return iterator->second;
    }

    void printSnapshotLineage(const std::string& snapshotId) const {
        auto iterator = snapshots_.find(snapshotId);

        if (iterator == snapshots_.end()) {
            throw StorageException("Snapshot does not exist");
        }

        std::cout << "Snapshot lineage: ";

        bool first = true;
        while (iterator != snapshots_.end()) {
            if (!first) {
                std::cout << " -> ";
            }

            std::cout << iterator->second.id;
            first = false;

            if (!iterator->second.parentSnapshotId.has_value()) {
                break;
            }

            iterator = snapshots_.find(
                *iterator->second.parentSnapshotId
            );
        }

        std::cout << '\n';
    }

    const BlockVolume& volume(const std::string& id) const {
        auto iterator = volumes_.find(id);

        if (iterator == volumes_.end()) {
            throw StorageException("Volume does not exist");
        }

        return iterator->second;
    }
};

void runPerformanceCaseStudy() {
    std::cout << "=== Database storage performance case study ===\n";

    StorageGovernanceEngine engine;

    BlockVolume& database = engine.createVolume(
        1024,
        VolumeType::GP3,
        12000,
        500,
        true
    );

    database.print();

    Workload randomReadWorkload{
        18000,
        16,
        60
    };

    std::cout << std::fixed << std::setprecision(2);
    std::cout
        << "Estimated latency for random I/O: "
        << database.estimatedLatencyMs(randomReadWorkload)
        << " ms\n";

    RepositoryStoragePolicy productionPolicy(
        10,
        8000,
        250
    );

    std::cout
        << "Meets production storage policy: "
        << std::boolalpha
        << productionPolicy.accepts(database, randomReadWorkload)
        << '\n';

    database.attach("db-production-01", "/dev/sdf");

    try {
        database.attach("db-production-02", "/dev/sdg");
    } catch (const StorageException& exception) {
        std::cout
            << "Attachment rejected: "
            << exception.what()
            << '\n';
    }

    database.modifyPerformance(16000, 750);

    std::cout << "After performance modification:\n";
    database.print();

    const Snapshot& backup = engine.createSnapshot(database.id());
    const Snapshot& secondBackup =
        engine.createSnapshot(database.id(), backup.id);

    std::cout
        << "Completed snapshots: "
        << backup.id
        << ", "
        << secondBackup.id
        << '\n';

    engine.printSnapshotLineage(secondBackup.id);

    database.detach();

    std::cout
        << "Volume state after detach: "
        << (database.state() == VolumeState::Available
                ? "available"
                : "unexpected")
        << '\n';
}

void demonstrateIopsAndThroughputTradeoff() {
    std::cout << "\n=== IOPS versus throughput ===\n";

    StorageGovernanceEngine engine;

    BlockVolume& highIops = engine.createVolume(
        500,
        VolumeType::GP3,
        16000,
        125
    );

    BlockVolume& highThroughput = engine.createVolume(
        500,
        VolumeType::GP3,
        3000,
        1000
    );

    Workload randomWorkload{12000, 4, 60};
    Workload sequentialWorkload{1000, 512, 60};

    std::cout
        << "High-IOPS volume, random workload latency: "
        << highIops.estimatedLatencyMs(randomWorkload)
        << " ms\n";

    std::cout
        << "High-throughput volume, random workload latency: "
        << highThroughput.estimatedLatencyMs(randomWorkload)
        << " ms\n";

    std::cout
        << "High-IOPS volume, sequential workload latency: "
        << highIops.estimatedLatencyMs(sequentialWorkload)
        << " ms\n";

    std::cout
        << "High-throughput volume, sequential workload latency: "
        << highThroughput.estimatedLatencyMs(sequentialWorkload)
        << " ms\n";

    /*
     * IOPS measures completed I/O operations per second. Throughput measures
     * bytes transferred per second. A workload can saturate either dimension
     * first, so increasing one does not automatically remove the bottleneck.
     */
}

void demonstrateInvalidConfiguration() {
    std::cout << "\n=== Invalid configuration handling ===\n";

    try {
        StorageGovernanceEngine engine;

        engine.createVolume(
            100,
            VolumeType::GP3,
            1000,
            125
        );
    } catch (const StorageException& exception) {
        std::cout
            << "Invalid volume rejected: "
            << exception.what()
            << '\n';
    }
}

int main() {
    try {
        runPerformanceCaseStudy();
        demonstrateIopsAndThroughputTradeoff();
        demonstrateInvalidConfiguration();
    } catch (const std::exception& exception) {
        std::cerr
            << "Fatal storage error: "
            << exception.what()
            << '\n';

        return 1;
    }

    return 0;
}
