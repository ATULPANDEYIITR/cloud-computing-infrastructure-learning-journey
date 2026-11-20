#include <algorithm>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

using namespace std;

enum class MountType {
    Volume,
    Bind,
    Tmpfs
};

enum class VolumeState {
    Available,
    InUse
};

struct Mount {
    MountType type;
    string source;
    string destination;
    bool readOnly = false;
};

struct Volume {
    string name;
    string driver = "local";
    VolumeState state = VolumeState::Available;
    unordered_set<string> containers;
    map<string, string> data;
    map<string, string> labels;
};

struct Container {
    string id;
    vector<Mount> mounts;
};

class StorageException : public runtime_error {
public:
    explicit StorageException(const string& message)
        : runtime_error(message) {}
};

class ValidationException : public StorageException {
public:
    explicit ValidationException(const string& message)
        : StorageException(message) {}
};

class StorageEngine {
private:
    unordered_map<string, Volume> volumes;
    unordered_map<string, Container> containers;

    static bool validName(const string& name) {
        if (name.empty() || name.size() > 64) return false;

        if (!isalnum(static_cast<unsigned char>(name.front()))) {
            return false;
        }

        return all_of(name.begin(), name.end(), [](unsigned char c) {
            return isalnum(c) || c == '_' || c == '-' || c == '.';
        });
    }

    static void validateMount(const Mount& mount) {
        if (
            mount.destination.empty() ||
            mount.destination.front() != '/' ||
            mount.destination.find("/../") != string::npos ||
            mount.destination.ends_with("/..")
        ) {
            throw ValidationException("Invalid container destination");
        }

        if (mount.type == MountType::Volume) {
            if (!validName(mount.source)) {
                throw ValidationException("Invalid volume name");
            }
        } else if (mount.type == MountType::Bind) {
            if (
                mount.source.empty() ||
                mount.source.front() != '/'
            ) {
                throw ValidationException("Bind path must be absolute");
            }
        } else if (
            mount.type == MountType::Tmpfs &&
            mount.source != "tmpfs"
        ) {
            throw ValidationException("Invalid tmpfs source");
        }
    }

    Volume& getVolume(const string& name) {
        auto it = volumes.find(name);

        if (it == volumes.end()) {
            throw StorageException("Volume not found: " + name);
        }

        return it->second;
    }

public:
    void createVolume(
        const string& name,
        const string& driver = "local",
        map<string, string> labels = {}
    ) {
        if (!validName(name) || driver.empty()) {
            throw ValidationException("Invalid volume configuration");
        }

        if (volumes.count(name)) {
            throw StorageException("Volume already exists");
        }

        Volume volume;
        volume.name = name;
        volume.driver = driver;
        volume.labels = move(labels);

        volumes.emplace(name, move(volume));

        cout << "Created volume: " << name << '\n';
    }

    void attachContainer(const Container& container) {
        if (
            container.id.empty() ||
            container.id.size() > 64 ||
            containers.count(container.id)
        ) {
            throw ValidationException("Invalid or duplicate container");
        }

        if (container.mounts.empty()) {
            throw ValidationException("Container requires mounts");
        }

        set<string> destinations;
        set<string> references;

        // Validate the full operation before mutating volume references.
        for (const auto& mount : container.mounts) {
            validateMount(mount);

            if (!destinations.insert(mount.destination).second) {
                throw ValidationException("Duplicate mount destination");
            }

            if (mount.type == MountType::Volume) {
                getVolume(mount.source);
                references.insert(mount.source);
            }
        }

        for (const auto& name : references) {
            Volume& volume = getVolume(name);
            volume.containers.insert(container.id);
            volume.state = VolumeState::InUse;
        }

        containers.emplace(container.id, container);

        cout << "Attached container: " << container.id << '\n';
    }

    void detachContainer(const string& containerId) {
        auto it = containers.find(containerId);

        if (it == containers.end()) {
            throw StorageException("Container not found");
        }

        set<string> references;

        for (const auto& mount : it->second.mounts) {
            if (mount.type == MountType::Volume) {
                references.insert(mount.source);
            }
        }

        for (const auto& name : references) {
            Volume& volume = getVolume(name);
            volume.containers.erase(containerId);

            if (volume.containers.empty()) {
                volume.state = VolumeState::Available;
            }
        }

        containers.erase(it);
        cout << "Detached container: " << containerId << '\n';
    }

    void write(
        const string& volumeName,
        const string& key,
        const string& value,
        const optional<string>& containerId = nullopt
    ) {
        Volume& volume = getVolume(volumeName);

        if (key.empty() || key.size() > 255) {
            throw ValidationException("Invalid storage key");
        }

        if (containerId.has_value()) {
            const string& id = *containerId;

            if (!volume.containers.count(id)) {
                throw StorageException("Container has no volume reference");
            }

            const Container& container = containers.at(id);

            bool writable = false;

            for (const auto& mount : container.mounts) {
                if (
                    mount.type == MountType::Volume &&
                    mount.source == volumeName &&
                    !mount.readOnly
                ) {
                    writable = true;
                }
            }

            if (!writable) {
                throw StorageException("Read-only mount");
            }
        }

        volume.data[key] = value;
    }

    string read(const string& volumeName, const string& key) {
        Volume& volume = getVolume(volumeName);
        auto it = volume.data.find(key);

        if (it == volume.data.end()) {
            throw StorageException("Data key not found");
        }

        return it->second;
    }

    void inspect(const string& name) {
        const Volume& volume = getVolume(name);

        cout << "\nVolume: " << volume.name << '\n';
        cout << "Driver: " << volume.driver << '\n';

        cout << "State: "
             << (volume.state == VolumeState::InUse
                 ? "IN_USE" : "AVAILABLE") << '\n';

        cout << "Attached containers: ";

        for (const auto& id : volume.containers) {
            cout << id << " ";
        }

        cout << "\nStored records: " << volume.data.size() << '\n';

        for (const auto& [key, value] : volume.data) {
            cout << "  " << key << " = " << value << '\n';
        }
    }

    void removeVolume(const string& name) {
        Volume& volume = getVolume(name);

        if (!volume.containers.empty()) {
            throw StorageException("Cannot remove volume in use");
        }

        volumes.erase(name);
        cout << "Removed volume: " << name << '\n';
    }

    vector<string> prune(
        const optional<string>& environment = nullopt
    ) {
        vector<string> removed;

        for (auto it = volumes.begin(); it != volumes.end();) {
            const bool unused = it->second.containers.empty();

            const bool matches =
                !environment.has_value() ||
                (
                    it->second.labels.count("environment") &&
                    it->second.labels.at("environment") == *environment
                );

            if (unused && matches) {
                removed.push_back(it->first);
                it = volumes.erase(it);
            } else {
                ++it;
            }
        }

        return removed;
    }

    void listVolumes() const {
        cout << "\nVolume inventory\n";

        for (const auto& [name, volume] : volumes) {
            cout << name
                 << " | " << volume.driver
                 << " | "
                 << (volume.state == VolumeState::InUse
                     ? "IN_USE" : "AVAILABLE")
                 << " | references=" << volume.containers.size()
                 << '\n';
        }
    }
};

int main() {
    try {
        StorageEngine engine;

        engine.createVolume(
            "postgres_data",
            "local",
            {
                {"environment", "development"},
                {"service", "postgres"}
            }
        );

        engine.createVolume(
            "application_logs",
            "local",
            {{"environment", "development"}}
        );

        engine.write("postgres_data", "database", "inventory");

        Container database{
            "postgres-container",
            {
                {
                    MountType::Volume,
                    "postgres_data",
                    "/var/lib/postgresql/data",
                    false
                },
                {
                    MountType::Tmpfs,
                    "tmpfs",
                    "/run/cache",
                    true
                }
            }
        };

        engine.attachContainer(database);

        engine.write(
            "postgres_data",
            "connection",
            "healthy",
            string("postgres-container")
        );

        engine.inspect("postgres_data");

        try {
            engine.removeVolume("postgres_data");
        } catch (const StorageException& error) {
            cout << "\nExpected removal restriction: "
                 << error.what() << '\n';
        }

        Container reader{
            "reporting-container",
            {
                {
                    MountType::Volume,
                    "postgres_data",
                    "/data",
                    true
                }
            }
        };

        engine.attachContainer(reader);

        try {
            engine.write(
                "postgres_data",
                "unauthorized",
                "blocked",
                string("reporting-container")
            );
        } catch (const StorageException& error) {
            cout << "Expected read-only failure: "
                 << error.what() << '\n';
        }

        cout << "\nPersistent data: "
             << engine.read("postgres_data", "database") << '\n';

        engine.detachContainer("reporting-container");
        engine.detachContainer("postgres-container");

        engine.listVolumes();

        const auto removed = engine.prune("development");

        cout << "\nPruned volumes:\n";

        for (const auto& name : removed) {
            cout << name << '\n';
        }

        engine.listVolumes();

    } catch (const exception& error) {
        cerr << "Storage engine failure: "
             << error.what() << '\n';
        return 1;
    }

    return 0;
}
