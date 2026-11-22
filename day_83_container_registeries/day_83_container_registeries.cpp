#include <algorithm>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include <sstream>
#include <functional>

using namespace std;

/*
 * Container Registry Governance and Distribution Engine.
 *
 * C++17 implementation using standard-library containers.
 *
 * Models:
 * - Repositories and image manifests
 * - Digest-addressed image storage
 * - Mutable and immutable tags
 * - User roles and repository permissions
 * - Push and pull operations
 * - Protected release tags
 * - Merge-independent deployment eligibility
 * - Garbage collection and audit records
 *
 * Digest generation is deterministic for this demonstration.
 * Production systems must use a cryptographic SHA-256 implementation.
 */

enum class Role {
    Reader,
    Writer,
    Admin
};

enum class ImageStatus {
    Available,
    Quarantined,
    Deleted
};

enum class RegistryAction {
    Push,
    Pull,
    Delete
};

struct Manifest {
    string configDigest;
    vector<string> layers;
    string architecture;
    string operatingSystem;

    void validate() const {
        if (configDigest.empty()) {
            throw invalid_argument("Missing image configuration digest.");
        }

        if (layers.empty()) {
            throw invalid_argument("Image requires at least one layer.");
        }

        if (
            architecture != "amd64" &&
            architecture != "arm64" &&
            architecture != "arm" &&
            architecture != "386"
        ) {
            throw invalid_argument("Unsupported image architecture.");
        }

        for (const auto& layer : layers) {
            if (layer.empty()) {
                throw invalid_argument("Empty layer reference.");
            }
        }
    }

    string canonical() const {
        vector<string> sortedLayers = layers;
        sort(sortedLayers.begin(), sortedLayers.end());

        ostringstream output;
        output << configDigest << '|'
               << architecture << '|'
               << operatingSystem;

        for (const auto& layer : sortedLayers) {
            output << '|' << layer;
        }

        return output.str();
    }

    string digest() const {
        // FNV-style deterministic demonstration identifier.
        // This is not a cryptographic substitute for SHA-256.
        hash<string> hasher;
        size_t value = hasher(canonical());

        ostringstream output;
        output << "demo:" << hex << value;
        return output.str();
    }
};

struct ImageArtifact {
    Manifest manifest;
    ImageStatus status = ImageStatus::Available;
    size_t pullCount = 0;
};

struct AuditEvent {
    string actor;
    string action;
    string repository;
    string reference;
    bool successful;
};

class User {
public:
    string username;
    string credentialHash;
    bool active = true;
    map<string, Role> permissions;

    User(string name, string credential)
        : username(move(name)),
          credentialHash(move(credential)) {}

    bool authenticate(const string& credential) const {
        return active && credential == credentialHash;
    }
};

class Repository {
public:
    string name;
    bool privateRepository;
    bool immutableTags;
    set<string> protectedTags;
    map<string, string> tags;
    map<string, ImageArtifact> artifacts;

    Repository(
        string repositoryName,
        bool isPrivate,
        bool immutable
    )
        : name(move(repositoryName)),
          privateRepository(isPrivate),
          immutableTags(immutable) {}

    bool validTag(const string& tag) const {
        if (tag.empty() || tag.size() > 128) {
            return false;
        }

        auto validFirst = [](char c) {
            return isalnum(static_cast<unsigned char>(c)) || c == '_';
        };

        auto validOther = [](char c) {
            return isalnum(static_cast<unsigned char>(c)) ||
                   c == '_' || c == '.' || c == '-';
        };

        if (!validFirst(tag.front())) {
            return false;
        }

        return all_of(
            tag.begin() + 1,
            tag.end(),
            validOther
        );
    }

    string resolve(const string& reference) const {
        string digest = reference;

        if (reference.rfind("demo:", 0) != 0) {
            auto it = tags.find(reference);

            if (it == tags.end()) {
                throw runtime_error("Tag not found.");
            }

            digest = it->second;
        }

        auto artifact = artifacts.find(digest);

        if (
            artifact == artifacts.end() ||
            artifact->second.status != ImageStatus::Available
        ) {
            throw runtime_error("Image artifact unavailable.");
        }

        return digest;
    }
};

class Registry {
private:
    string name;
    map<string, User> users;
    map<string, Repository> repositories;
    vector<AuditEvent> audit;

    User& authenticate(
        const string& username,
        const string& credential
    ) {
        auto it = users.find(username);

        if (it == users.end() || !it->second.authenticate(credential)) {
            throw runtime_error("Authentication failed.");
        }

        return it->second;
    }

    Repository& getRepository(const string& name) {
        auto it = repositories.find(name);

        if (it == repositories.end()) {
            throw runtime_error("Repository not found.");
        }

        return it->second;
    }

    void authorize(
        const User& user,
        const Repository& repository,
        RegistryAction action
    ) const {
        if (
            !repository.privateRepository &&
            action == RegistryAction::Pull
        ) {
            return;
        }

        auto permission = user.permissions.find(repository.name);

        if (permission == user.permissions.end()) {
            throw runtime_error("Repository access denied.");
        }

        Role role = permission->second;
        bool allowed = false;

        switch (action) {
            case RegistryAction::Pull:
                allowed = true;
                break;

            case RegistryAction::Push:
                allowed = role == Role::Writer || role == Role::Admin;
                break;

            case RegistryAction::Delete:
                allowed = role == Role::Admin;
                break;
        }

        if (!allowed) {
            throw runtime_error("Insufficient repository permissions.");
        }
    }

    void log(
        const string& actor,
        const string& action,
        const string& repository,
        const string& reference,
        bool successful
    ) {
        audit.push_back({
            actor,
            action,
            repository,
            reference,
            successful
        });
    }

public:
    explicit Registry(string registryName)
        : name(move(registryName)) {
        if (name.empty()) {
            throw invalid_argument("Registry name is required.");
        }
    }

    void addUser(const string& username, const string& credential) {
        if (username.empty() || credential.size() < 12) {
            throw invalid_argument("Invalid user credentials.");
        }

        if (users.count(username)) {
            throw runtime_error("User already exists.");
        }

        users.emplace(
            piecewise_construct,
            forward_as_tuple(username),
            forward_as_tuple(username, credential)
        );
    }

    void createRepository(
        const string& repositoryName,
        bool privateRepository = true,
        bool immutableTags = false
    ) {
        if (
            repositoryName.empty() ||
            repositoryName.find("..") != string::npos
        ) {
            throw invalid_argument("Invalid repository name.");
        }

        if (repositories.count(repositoryName)) {
            throw runtime_error("Repository already exists.");
        }

        repositories.emplace(
            piecewise_construct,
            forward_as_tuple(repositoryName),
            forward_as_tuple(
                repositoryName,
                privateRepository,
                immutableTags
            )
        );
    }

    void grant(
        const string& adminName,
        const string& adminCredential,
        const string& targetName,
        const string& repositoryName,
        Role role
    ) {
        User& admin = authenticate(adminName, adminCredential);
        Repository& repository = getRepository(repositoryName);

        authorize(admin, repository, RegistryAction::Delete);

        auto target = users.find(targetName);

        if (target == users.end()) {
            throw runtime_error("Target user does not exist.");
        }

        target->second.permissions[repositoryName] = role;
    }

    void bootstrapPermission(
        const string& username,
        const string& repositoryName,
        Role role
    ) {
        auto user = users.find(username);
        Repository& repository = getRepository(repositoryName);

        if (user == users.end()) {
            throw runtime_error("User not found.");
        }

        user->second.permissions[repositoryName] = role;
    }

    string push(
        const string& username,
        const string& credential,
        const string& repositoryName,
        const string& tag,
        const Manifest& manifest
    ) {
        try {
            User& user = authenticate(username, credential);
            Repository& repository = getRepository(repositoryName);

            authorize(user, repository, RegistryAction::Push);

            if (!repository.validTag(tag)) {
                throw invalid_argument("Invalid image tag.");
            }

            manifest.validate();

            const string digest = manifest.digest();

            if (
                repository.immutableTags &&
                repository.tags.count(tag) &&
                repository.tags.at(tag) != digest
            ) {
                throw runtime_error("Immutable tag reassignment denied.");
            }

            if (
                repository.protectedTags.count(tag) &&
                repository.tags.count(tag) &&
                repository.tags.at(tag) != digest
            ) {
                throw runtime_error("Protected release tag cannot move.");
            }

            // emplace preserves an existing artifact with the same digest.
            repository.artifacts.emplace(
                digest,
                ImageArtifact{manifest, ImageStatus::Available, 0}
            );

            repository.tags[tag] = digest;

            log(username, "push", repositoryName, tag, true);
            return digest;

        } catch (...) {
            log(username, "push", repositoryName, tag, false);
            throw;
        }
    }

    ImageArtifact pull(
        const string& username,
        const string& credential,
        const string& repositoryName,
        const string& reference
    ) {
        try {
            User& user = authenticate(username, credential);
            Repository& repository = getRepository(repositoryName);

            authorize(user, repository, RegistryAction::Pull);

            string digest = repository.resolve(reference);
            ImageArtifact& artifact = repository.artifacts.at(digest);

            ++artifact.pullCount;

            log(username, "pull", repositoryName, reference, true);
            return artifact;

        } catch (...) {
            log(username, "pull", repositoryName, reference, false);
            throw;
        }
    }

    void protectTag(
        const string& adminName,
        const string& credential,
        const string& repositoryName,
        const string& tag
    ) {
        User& admin = authenticate(adminName, credential);
        Repository& repository = getRepository(repositoryName);

        authorize(admin, repository, RegistryAction::Delete);

        if (!repository.validTag(tag)) {
            throw invalid_argument("Invalid protected tag.");
        }

        repository.protectedTags.insert(tag);
    }

    void deleteTag(
        const string& adminName,
        const string& credential,
        const string& repositoryName,
        const string& tag
    ) {
        User& admin = authenticate(adminName, credential);
        Repository& repository = getRepository(repositoryName);

        authorize(admin, repository, RegistryAction::Delete);

        if (repository.protectedTags.count(tag)) {
            throw runtime_error("Protected tag deletion denied.");
        }

        if (!repository.tags.erase(tag)) {
            throw runtime_error("Tag not found.");
        }

        log(adminName, "delete", repositoryName, tag, true);
    }

    size_t garbageCollect(
        const string& adminName,
        const string& credential,
        const string& repositoryName
    ) {
        User& admin = authenticate(adminName, credential);
        Repository& repository = getRepository(repositoryName);

        authorize(admin, repository, RegistryAction::Delete);

        set<string> referenced;

        for (const auto& [tag, digest] : repository.tags) {
            referenced.insert(digest);
        }

        size_t removed = 0;

        for (auto it = repository.artifacts.begin();
             it != repository.artifacts.end();) {

            if (!referenced.count(it->first)) {
                it = repository.artifacts.erase(it);
                ++removed;
            } else {
                ++it;
            }
        }

        log(adminName, "garbage_collect", repositoryName,
            to_string(removed), true);

        return removed;
    }

    void report(const string& repositoryName) const {
        auto it = repositories.find(repositoryName);

        if (it == repositories.end()) {
            throw runtime_error("Repository not found.");
        }

        const Repository& repository = it->second;

        size_t pulls = 0;

        for (const auto& [digest, artifact] : repository.artifacts) {
            pulls += artifact.pullCount;
        }

        cout << "\nRegistry: " << name
             << "\nRepository: " << repository.name
             << "\nVisibility: "
             << (repository.privateRepository ? "Private" : "Public")
             << "\nArtifacts: " << repository.artifacts.size()
             << "\nTags: " << repository.tags.size()
             << "\nTotal pulls: " << pulls
             << "\n";

        for (const auto& [tag, digest] : repository.tags) {
            cout << "  " << tag << " -> " << digest << '\n';
        }
    }

    void printAudit() const {
        cout << "\nAudit events: " << audit.size() << '\n';

        for (const auto& event : audit) {
            cout << event.actor << " | "
                 << event.action << " | "
                 << event.repository << " | "
                 << event.reference << " | "
                 << (event.successful ? "SUCCESS" : "FAILURE")
                 << '\n';
        }
    }
};

int main() {
    try {
        Registry registry("enterprise-registry");

        registry.addUser("admin", "admin-credential-2026");
        registry.addUser("builder", "builder-credential-2026");
        registry.addUser("runtime", "runtime-credential-2026");

        registry.createRepository(
            "finance/payment-api",
            true,
            false
        );

        registry.bootstrapPermission(
            "admin",
            "finance/payment-api",
            Role::Admin
        );

        registry.grant(
            "admin",
            "admin-credential-2026",
            "builder",
            "finance/payment-api",
            Role::Writer
        );

        registry.grant(
            "admin",
            "admin-credential-2026",
            "runtime",
            "finance/payment-api",
            Role::Reader
        );

        Manifest version1{
            "sha256:config001",
            {"sha256:layer001", "sha256:layer002"},
            "amd64",
            "linux"
        };

        string digest1 = registry.push(
            "builder",
            "builder-credential-2026",
            "finance/payment-api",
            "1.0.0",
            version1
        );

        registry.push(
            "builder",
            "builder-credential-2026",
            "finance/payment-api",
            "stable",
            version1
        );

        registry.protectTag(
            "admin",
            "admin-credential-2026",
            "finance/payment-api",
            "stable"
        );

        ImageArtifact deployed = registry.pull(
            "runtime",
            "runtime-credential-2026",
            "finance/payment-api",
            "stable"
        );

        cout << "Deployment digest: " << deployed.manifest.digest()
             << "\nDigest matches: "
             << boolalpha
             << (deployed.manifest.digest() == digest1)
             << '\n';

        Manifest version2{
            "sha256:config002",
            {"sha256:layer003"},
            "arm64",
            "linux"
        };

        registry.push(
            "builder",
            "builder-credential-2026",
            "finance/payment-api",
            "2.0.0",
            version2
        );

        try {
            registry.deleteTag(
                "admin",
                "admin-credential-2026",
                "finance/payment-api",
                "stable"
            );
        } catch (const exception& error) {
            cout << "Expected protected-tag failure: "
                 << error.what() << '\n';
        }

        try {
            registry.push(
                "runtime",
                "runtime-credential-2026",
                "finance/payment-api",
                "unauthorized",
                version2
            );
        } catch (const exception& error) {
            cout << "Expected permission failure: "
                 << error.what() << '\n';
        }

        registry.report("finance/payment-api");

        size_t removed = registry.garbageCollect(
            "admin",
            "admin-credential-2026",
            "finance/payment-api"
        );

        cout << "\nRemoved unreferenced artifacts: "
             << removed << '\n';

        registry.printAudit();

    } catch (const exception& error) {
        cerr << "Registry failure: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
