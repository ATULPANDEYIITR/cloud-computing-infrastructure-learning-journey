#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace fs = std::filesystem;

enum class BackupType {
    Full,
    Incremental,
    Snapshot
};

enum class ReviewStatus {
    Running,
    Completed,
    Failed,
    Expired
};

struct FileFingerprint {
    std::string relativePath;
    std::uintmax_t size{};
    std::uint64_t checksum{};
};

struct BackupRecord {
    std::string id;
    BackupType type;
    ReviewStatus status;
    fs::path destination;
    std::vector<FileFingerprint> files;
    std::optional<std::string> parentId;
    std::string error;
    std::chrono::system_clock::time_point createdAt;
};

class BackupException : public std::runtime_error {
public:
    explicit BackupException(const std::string& message)
        : std::runtime_error(message) {}
};

class BackupEngine {
private:
    fs::path source_;
    fs::path repository_;
    std::map<std::string, BackupRecord> catalog_;

    static std::uint64_t hashFile(const fs::path& path) {
        std::ifstream input(path, std::ios::binary);

        if (!input) {
            throw BackupException(
                "Cannot read file: " + path.string()
            );
        }

        /*
         * std::hash is used here as a dependency-free integrity fingerprint.
         * Production backup repositories should use a cryptographic hash such
         * as SHA-256 from a vetted cryptographic implementation.
         */
        std::uint64_t hash = 1469598103934665603ULL;
        char byte;

        while (input.get(byte)) {
            hash ^= static_cast<unsigned char>(byte);
            hash *= 1099511628211ULL;
        }

        return hash;
    }

    static std::string typeName(BackupType type) {
        switch (type) {
            case BackupType::Full:
                return "full";
            case BackupType::Incremental:
                return "incremental";
            case BackupType::Snapshot:
                return "snapshot";
        }

        return "unknown";
    }

    static std::string timestamp() {
        const auto now = std::chrono::system_clock::now();
        const std::time_t time =
            std::chrono::system_clock::to_time_t(now);

        std::tm utc{};

#ifdef _WIN32
        gmtime_s(&utc, &time);
#else
        gmtime_r(&time, &utc);
#endif

        std::ostringstream output;
        output << std::put_time(&utc, "%Y%m%dT%H%M%SZ");
        return output.str();
    }

    std::string makeId(BackupType type) const {
        static std::random_device random;
        std::ostringstream output;

        output << typeName(type)
               << "-"
               << timestamp()
               << "-"
               << std::hex
               << random();

        return output.str();
    }

    std::map<std::string, FileFingerprint> inventory() const {
        std::map<std::string, FileFingerprint> result;

        for (const auto& entry :
             fs::recursive_directory_iterator(source_)) {
            if (!entry.is_regular_file()) {
                continue;
            }

            const auto relative =
                fs::relative(entry.path(), source_).generic_string();

            result.emplace(
                relative,
                FileFingerprint{
                    relative,
                    entry.file_size(),
                    hashFile(entry.path())
                }
            );
        }

        return result;
    }

    void copyFile(
        const std::string& relativePath,
        const fs::path& destination
    ) const {
        const fs::path sourceFile =
            source_ / fs::path(relativePath);

        const fs::path destinationFile =
            destination / fs::path(relativePath);

        fs::create_directories(destinationFile.parent_path());

        fs::copy_file(
            sourceFile,
            destinationFile,
            fs::copy_options::overwrite_existing
        );
    }

public:
    BackupEngine(
        fs::path source,
        fs::path repository
    )
        : source_(fs::absolute(std::move(source))),
          repository_(fs::absolute(std::move(repository))) {

        if (!fs::exists(source_) ||
            !fs::is_directory(source_)) {
            throw BackupException(
                "Backup source does not exist"
            );
        }

        fs::create_directories(repository_);
    }

    BackupRecord createFull() {
        return create(BackupType::Full);
    }

    BackupRecord createSnapshot() {
        return create(BackupType::Snapshot);
    }

    BackupRecord createIncremental() {
        std::optional<std::string> parent;

        for (const auto& [id, record] : catalog_) {
            if (record.status == ReviewStatus::Completed) {
                parent = id;
            }
        }

        if (!parent) {
            return createFull();
        }

        return create(BackupType::Incremental, parent);
    }

    BackupRecord create(
        BackupType type,
        std::optional<std::string> parent = std::nullopt
    ) {
        const std::string id = makeId(type);
        const fs::path destination = repository_ / id;

        fs::create_directories(destination);

        BackupRecord record{
            id,
            type,
            ReviewStatus::Running,
            destination,
            {},
            parent,
            "",
            std::chrono::system_clock::now()
        };

        try {
            const auto current = inventory();
            std::vector<FileFingerprint> selected;

            if (type == BackupType::Full ||
                type == BackupType::Snapshot) {
                for (const auto& [path, fingerprint] : current) {
                    selected.push_back(fingerprint);
                }
            } else {
                if (!parent) {
                    throw BackupException(
                        "Incremental backup requires a parent"
                    );
                }

                const auto parentIt = catalog_.find(*parent);

                if (parentIt == catalog_.end()) {
                    throw BackupException(
                        "Parent backup does not exist"
                    );
                }

                std::unordered_map<
                    std::string,
                    FileFingerprint
                > previous;

                for (const auto& item :
                     parentIt->second.files) {
                    previous[item.relativePath] = item;
                }

                for (const auto& [path, fingerprint] : current) {
                    auto old = previous.find(path);

                    if (old == previous.end() ||
                        old->second.size != fingerprint.size ||
                        old->second.checksum != fingerprint.checksum) {
                        selected.push_back(fingerprint);
                    }
                }
            }

            for (const auto& fingerprint : selected) {
                copyFile(
                    fingerprint.relativePath,
                    destination
                );
            }

            record.files = selected;
            record.status = ReviewStatus::Completed;
            catalog_[id] = record;

            return record;
        } catch (const std::exception& error) {
            record.status = ReviewStatus::Failed;
            record.error = error.what();
            catalog_[id] = record;

            fs::remove_all(destination);

            throw BackupException(
                "Backup failed: " + std::string(error.what())
            );
        }
    }

    bool verify(
        const std::string& backupId,
        std::vector<std::string>& failures
    ) const {
        auto it = catalog_.find(backupId);

        if (it == catalog_.end()) {
            failures.push_back("Unknown backup");
            return false;
        }

        const BackupRecord& record = it->second;

        if (record.status != ReviewStatus::Completed) {
            failures.push_back("Backup is not completed");
            return false;
        }

        for (const auto& expected : record.files) {
            const fs::path file =
                record.destination /
                fs::path(expected.relativePath);

            if (!fs::exists(file)) {
                failures.push_back(
                    "Missing: " + expected.relativePath
                );
                continue;
            }

            if (fs::file_size(file) != expected.size) {
                failures.push_back(
                    "Size mismatch: " + expected.relativePath
                );
                continue;
            }

            if (hashFile(file) != expected.checksum) {
                failures.push_back(
                    "Checksum mismatch: " +
                    expected.relativePath
                );
            }
        }

        return failures.empty();
    }

    void restore(
        const std::string& backupId,
        const fs::path& destination
    ) const {
        auto it = catalog_.find(backupId);

        if (it == catalog_.end()) {
            throw BackupException(
                "Unknown backup: " + backupId
            );
        }

        if (fs::absolute(destination) == source_) {
            throw BackupException(
                "Restore cannot overwrite live source"
            );
        }

        std::vector<const BackupRecord*> chain;
        const BackupRecord* current = &it->second;

        while (true) {
            chain.push_back(current);

            if (current->type == BackupType::Full) {
                break;
            }

            if (!current->parentId) {
                throw BackupException(
                    "Incomplete incremental chain"
                );
            }

            auto parent = catalog_.find(*current->parentId);

            if (parent == catalog_.end()) {
                throw BackupException(
                    "Missing parent backup"
                );
            }

            current = &parent->second;
        }

        std::reverse(chain.begin(), chain.end());
        fs::create_directories(destination);

        for (const BackupRecord* backup : chain) {
            for (const auto& item : backup->files) {
                const fs::path sourceFile =
                    backup->destination /
                    fs::path(item.relativePath);

                const fs::path targetFile =
                    destination /
                    fs::path(item.relativePath);

                fs::create_directories(
                    targetFile.parent_path()
                );

                fs::copy_file(
                    sourceFile,
                    targetFile,
                    fs::copy_options::overwrite_existing
                );
            }
        }
    }

    std::vector<std::string> applyRetention(
        std::size_t keepFull,
        std::chrono::hours keepDuration
    ) {
        if (keepFull == 0 ||
            keepDuration.count() <= 0) {
            throw BackupException(
                "Retention values must be positive"
            );
        }

        std::vector<std::string> fullIds;

        for (const auto& [id, record] : catalog_) {
            if (record.type == BackupType::Full &&
                record.status == ReviewStatus::Completed) {
                fullIds.push_back(id);
            }
        }

        std::sort(fullIds.begin(), fullIds.end());

        const std::size_t firstRetained =
            fullIds.size() > keepFull
                ? fullIds.size() - keepFull
                : 0;

        std::vector<std::string> expired;
        const auto cutoff =
            std::chrono::system_clock::now() - keepDuration;

        for (auto& [id, record] : catalog_) {
            if (record.status != ReviewStatus::Completed) {
                continue;
            }

            const bool recent =
                record.createdAt >= cutoff;

            const bool retainedFull =
                record.type == BackupType::Full &&
                std::find(
                    fullIds.begin() + firstRetained,
                    fullIds.end(),
                    id
                ) != fullIds.end();

            if (!recent && !retainedFull) {
                fs::remove_all(record.destination);
                record.status = ReviewStatus::Expired;
                expired.push_back(id);
            }
        }

        return expired;
    }
};

void createDemoData(const fs::path& source) {
    fs::create_directories(source / "database");
    fs::create_directories(source / "application");

    std::ofstream(source / "database" / "records.txt")
        << "customer-001\ncustomer-002\n";

    std::ofstream(source / "application" / "config.txt")
        << "environment=production\n"
        << "backup=true\n";
}

int main() {
    try {
        const fs::path workspace =
            fs::temp_directory_path() /
            "backup_architecture_cpp";

        fs::remove_all(workspace);

        const fs::path source =
            workspace / "live-data";

        const fs::path repository =
            workspace / "backup-repository";

        createDemoData(source);

        BackupEngine engine(source, repository);

        const BackupRecord full =
            engine.createFull();

        std::vector<std::string> failures;

        std::cout
            << "FULL "
            << full.id
            << " verified="
            << std::boolalpha
            << engine.verify(full.id, failures)
            << '\n';

        std::ofstream(source / "database" / "records.txt")
            << "customer-001\n"
            << "customer-002\n"
            << "customer-003\n";

        std::ofstream(source / "application" / "audit.log")
            << "backup-test-event\n";

        const BackupRecord incremental =
            engine.createIncremental();

        std::cout
            << "INCREMENTAL "
            << incremental.id
            << " changed-files="
            << incremental.files.size()
            << '\n';

        const BackupRecord snapshot =
            engine.createSnapshot();

        std::cout
            << "SNAPSHOT "
            << snapshot.id
            << " files="
            << snapshot.files.size()
            << '\n';

        const fs::path restored =
            workspace / "restored";

        engine.restore(incremental.id, restored);

        std::ifstream restoredFile(
            restored / "database" / "records.txt"
        );

        std::string line;
        std::cout << "RESTORED:\n";

        while (std::getline(restoredFile, line)) {
            std::cout << line << '\n';
        }

        const auto expired =
            engine.applyRetention(
                1,
                std::chrono::hours(24)
            );

        std::cout
            << "EXPIRED="
            << expired.size()
            << '\n';

        fs::remove_all(workspace);
    } catch (const std::exception& error) {
        std::cerr
            << "ERROR: "
            << error.what()
            << '\n';

        return 1;
    }

    return 0;
}
