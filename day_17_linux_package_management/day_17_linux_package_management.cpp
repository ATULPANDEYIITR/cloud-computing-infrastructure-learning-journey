#include <algorithm>
#include <cctype>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

/*
 * Linux Package Management Case Study
 *
 * Scenario:
 *   A fleet-management component needs to determine whether a server can
 *   install an application and, if so, produce a safe package transaction.
 *
 * The program models concepts found in apt/dnf/yum:
 *   - repositories
 *   - packages
 *   - versions
 *   - dependencies
 *   - installed package database
 *   - repository trust
 *   - dependency resolution
 *   - transaction planning
 *   - installation and removal
 *   - conflict detection
 *   - edge cases
 *
 * This is a simulation. It does not invoke apt, dnf, yum, rpm, or dpkg and
 * does not modify the host operating system.
 *
 * Compile:
 *   g++ -std=c++17 -Wall -Wextra -pedantic package_manager.cpp -o package_manager
 */

using namespace std;


// ---------------------------------------------------------------------------
// Version handling
// ---------------------------------------------------------------------------

vector<string> tokenizeVersion(const string& version) {
    vector<string> tokens;
    string current;

    auto flush = [&]() {
        if (!current.empty()) {
            tokens.push_back(current);
            current.clear();
        }
    };

    for (char character : version) {
        if (isdigit(static_cast<unsigned char>(character))) {
            flush();
            current += character;
        } else if (isalpha(static_cast<unsigned char>(character))) {
            flush();
            current += static_cast<char>(
                tolower(static_cast<unsigned char>(character))
            );
        } else {
            flush();
        }
    }

    flush();
    return tokens;
}

int compareVersions(const string& left, const string& right) {
    /*
     * Simplified comparison for educational purposes.
     *
     * Debian dpkg and RPM use more sophisticated distribution-specific
     * algorithms. This function is not intended to replace them.
     */
    const auto a = tokenizeVersion(left);
    const auto b = tokenizeVersion(right);

    const size_t length = max(a.size(), b.size());

    for (size_t index = 0; index < length; ++index) {
        if (index >= a.size()) return -1;
        if (index >= b.size()) return 1;

        const string& x = a[index];
        const string& y = b[index];

        const bool xNumber = all_of(
            x.begin(), x.end(),
            [](char c) { return isdigit(static_cast<unsigned char>(c)); }
        );

        const bool yNumber = all_of(
            y.begin(), y.end(),
            [](char c) { return isdigit(static_cast<unsigned char>(c)); }
        );

        if (xNumber && yNumber) {
            long long xi = stoll(x);
            long long yi = stoll(y);

            if (xi != yi) {
                return xi < yi ? -1 : 1;
            }
        } else if (x != y) {
            return x < y ? -1 : 1;
        }
    }

    return 0;
}


// ---------------------------------------------------------------------------
// Dependency model
// ---------------------------------------------------------------------------

struct Package;

struct Dependency {
    string name;
    string operatorSymbol;
    string requiredVersion;

    bool isSatisfiedBy(const Package& package) const;
};


// ---------------------------------------------------------------------------
// Package model
// ---------------------------------------------------------------------------

struct Package {
    string name;
    string version;
    string architecture = "amd64";
    string repository;
    string description;
    vector<Dependency> dependencies;
    double sizeMB = 1.0;
    bool essential = false;

    string identifier() const {
        return name + "=" + version + ":" + architecture;
    }
};

bool Dependency::isSatisfiedBy(const Package& package) const {
    if (package.name != name) {
        return false;
    }

    if (operatorSymbol.empty()) {
        return true;
    }

    const int comparison =
        compareVersions(package.version, requiredVersion);

    if (operatorSymbol == ">") return comparison > 0;
    if (operatorSymbol == ">=") return comparison >= 0;
    if (operatorSymbol == "<") return comparison < 0;
    if (operatorSymbol == "<=") return comparison <= 0;
    if (operatorSymbol == "=") return comparison == 0;

    throw runtime_error(
        "Unsupported dependency operator: " + operatorSymbol
    );
}


// ---------------------------------------------------------------------------
// Repository
// ---------------------------------------------------------------------------

class Repository {
private:
    string name_;
    string url_;
    bool enabled_;
    bool trusted_;
    vector<Package> packages_;

public:
    Repository(
        string name,
        string url,
        bool enabled = true,
        bool trusted = true
    )
        : name_(move(name)),
          url_(move(url)),
          enabled_(enabled),
          trusted_(trusted) {}

    void addPackage(Package package) {
        packages_.push_back(move(package));
    }

    const string& name() const {
        return name_;
    }

    const string& url() const {
        return url_;
    }

    bool enabled() const {
        return enabled_;
    }

    bool trusted() const {
        return trusted_;
    }

    vector<Package> candidates(const string& packageName) const {
        vector<Package> result;

        if (!enabled_ || !trusted_) {
            return result;
        }

        for (const Package& package : packages_) {
            if (package.name == packageName) {
                result.push_back(package);
            }
        }

        sort(
            result.begin(),
            result.end(),
            [](const Package& left, const Package& right) {
                return compareVersions(
                    left.version,
                    right.version
                ) > 0;
            }
        );

        return result;
    }

    vector<Package> search(const string& term) const {
        vector<Package> result;

        for (const Package& package : packages_) {
            if (
                package.name.find(term) != string::npos ||
                package.description.find(term) != string::npos
            ) {
                result.push_back(package);
            }
        }

        return result;
    }
};


// ---------------------------------------------------------------------------
// Installed package database
// ---------------------------------------------------------------------------

class InstalledDatabase {
private:
    map<string, Package> packages_;

public:
    optional<Package> get(const string& name) const {
        auto iterator = packages_.find(name);

        if (iterator == packages_.end()) {
            return nullopt;
        }

        return iterator->second;
    }

    bool contains(const string& name) const {
        return packages_.find(name) != packages_.end();
    }

    void install(const Package& package) {
        packages_[package.name] = package;
    }

    Package remove(const string& name) {
        auto iterator = packages_.find(name);

        if (iterator == packages_.end()) {
            throw runtime_error(
                "Package is not installed: " + name
            );
        }

        Package package = iterator->second;
        packages_.erase(iterator);
        return package;
    }

    vector<Package> all() const {
        vector<Package> result;

        for (const auto& [name, package] : packages_) {
            result.push_back(package);
        }

        return result;
    }
};


// ---------------------------------------------------------------------------
// Transaction operation
// ---------------------------------------------------------------------------

enum class OperationType {
    Install,
    Upgrade
};

struct Operation {
    OperationType type;
    Package package;
    optional<Package> previous;
};


// ---------------------------------------------------------------------------
// Dependency resolver
// ---------------------------------------------------------------------------

class DependencyResolver {
private:
    const vector<Repository>& repositories_;
    const InstalledDatabase& installed_;

    optional<Package> findCandidate(
        const Dependency& dependency
    ) const {
        vector<Package> candidates;

        for (const Repository& repository : repositories_) {
            vector<Package> repositoryCandidates =
                repository.candidates(dependency.name);

            candidates.insert(
                candidates.end(),
                repositoryCandidates.begin(),
                repositoryCandidates.end()
            );
        }

        sort(
            candidates.begin(),
            candidates.end(),
            [](const Package& left, const Package& right) {
                return compareVersions(
                    left.version,
                    right.version
                ) > 0;
            }
        );

        for (const Package& candidate : candidates) {
            if (dependency.isSatisfiedBy(candidate)) {
                return candidate;
            }
        }

        return nullopt;
    }

public:
    DependencyResolver(
        const vector<Repository>& repositories,
        const InstalledDatabase& installed
    )
        : repositories_(repositories),
          installed_(installed) {}

    vector<Package> resolve(const string& rootName) const {
        map<string, Package> selected;
        set<string> visiting;

        function<void(const Dependency&)> visit =
            [&](const Dependency& dependency) {
                auto selectedIterator =
                    selected.find(dependency.name);

                if (selectedIterator != selected.end()) {
                    if (
                        !dependency.isSatisfiedBy(
                            selectedIterator->second
                        )
                    ) {
                        throw runtime_error(
                            "Dependency conflict for " +
                            dependency.name
                        );
                    }

                    return;
                }

                if (visiting.contains(dependency.name)) {
                    throw runtime_error(
                        "Circular dependency detected at " +
                        dependency.name
                    );
                }

                const optional<Package> installed =
                    installed_.get(dependency.name);

                if (
                    installed.has_value() &&
                    dependency.isSatisfiedBy(installed.value())
                ) {
                    selected[dependency.name] =
                        installed.value();
                    return;
                }

                const optional<Package> candidate =
                    findCandidate(dependency);

                if (!candidate.has_value()) {
                    throw runtime_error(
                        "No compatible package found for " +
                        dependency.name
                    );
                }

                visiting.insert(dependency.name);
                selected[dependency.name] = candidate.value();

                for (
                    const Dependency& child :
                    candidate->dependencies
                ) {
                    visit(child);
                }

                visiting.erase(dependency.name);
            };

        visit(Dependency{rootName, "", ""});

        vector<Package> result;

        for (const auto& [name, package] : selected) {
            result.push_back(package);
        }

        /*
         * A real dependency solver may use a sophisticated graph algorithm.
         * Here we perform a simple ordering pass so dependencies are usually
         * installed before packages that require them.
         */
        sort(
            result.begin(),
            result.end(),
            [](const Package& left, const Package& right) {
                return left.name < right.name;
            }
        );

        return result;
    }
};


// ---------------------------------------------------------------------------
// Package manager service
// ---------------------------------------------------------------------------

class PackageManager {
private:
    vector<Repository> repositories_;
    InstalledDatabase installed_;

public:
    explicit PackageManager(vector<Repository> repositories)
        : repositories_(move(repositories)) {}

    void refreshMetadata() const {
        cout << "\nRefreshing repository metadata:\n";

        for (const Repository& repository : repositories_) {
            cout
                << "  "
                << repository.name()
                << " | "
                << (repository.enabled() ? "enabled" : "disabled")
                << " | "
                << (repository.trusted() ? "trusted" : "untrusted")
                << '\n';
        }

        cout << "Metadata refresh completed in simulation.\n";
    }

    void search(const string& term) const {
        cout << "\nSearch results for: " << term << '\n';

        bool found = false;

        for (const Repository& repository : repositories_) {
            if (!repository.enabled() || !repository.trusted()) {
                continue;
            }

            for (const Package& package : repository.search(term)) {
                cout
                    << "  "
                    << package.identifier()
                    << " - "
                    << package.description
                    << '\n';

                found = true;
            }
        }

        if (!found) {
            cout << "  No results.\n";
        }
    }

    void show(const string& name) const {
        cout << "\nPackage information: " << name << '\n';

        const optional<Package> installed =
            installed_.get(name);

        if (installed.has_value()) {
            cout
                << "  Installed: "
                << installed->identifier()
                << '\n';
        } else {
            cout << "  Installed: no\n";
        }

        for (const Repository& repository : repositories_) {
            if (!repository.enabled()) {
                continue;
            }

            for (const Package& package :
                 repository.candidates(name)) {
                cout
                    << "  Available: "
                    << package.identifier()
                    << '\n';

                cout
                    << "    Repository: "
                    << package.repository
                    << '\n';

                cout
                    << "    Description: "
                    << package.description
                    << '\n';

                if (!package.dependencies.empty()) {
                    cout << "    Dependencies:\n";

                    for (
                        const Dependency& dependency :
                        package.dependencies
                    ) {
                        cout
                            << "      "
                            << dependency.name
                            << ' '
                            << dependency.operatorSymbol
                            << ' '
                            << dependency.requiredVersion
                            << '\n';
                    }
                }
            }
        }
    }

    void install(const string& name) {
        cout << "\nInstall request: " << name << '\n';

        DependencyResolver resolver(
            repositories_,
            installed_
        );

        try {
            const vector<Package> resolved =
                resolver.resolve(name);

            vector<Operation> operations;

            for (const Package& package : resolved) {
                const optional<Package> current =
                    installed_.get(package.name);

                if (!current.has_value()) {
                    operations.push_back({
                        OperationType::Install,
                        package,
                        nullopt
                    });
                } else if (
                    compareVersions(
                        package.version,
                        current->version
                    ) > 0
                ) {
                    operations.push_back({
                        OperationType::Upgrade,
                        package,
                        current
                    });
                }
            }

            if (operations.empty()) {
                cout << "  Nothing to do.\n";
                return;
            }

            cout << "  Proposed transaction:\n";

            for (const Operation& operation : operations) {
                if (operation.type == OperationType::Install) {
                    cout
                        << "    INSTALL "
                        << operation.package.identifier()
                        << '\n';
                } else {
                    cout
                        << "    UPGRADE "
                        << operation.previous->identifier()
                        << " -> "
                        << operation.package.identifier()
                        << '\n';
                }
            }

            /*
             * In a production package manager, this is the point at which
             * transaction scripts, file conflicts, disk space, signatures,
             * triggers, locks, service restarts, and other policies matter.
             */
            for (const Operation& operation : operations) {
                installed_.install(operation.package);
            }

            cout << "  Transaction committed.\n";
        } catch (const exception& error) {
            cout
                << "  Transaction rejected: "
                << error.what()
                << '\n';
        }
    }

    void remove(const string& name) {
        cout << "\nRemove request: " << name << '\n';

        const optional<Package> package =
            installed_.get(name);

        if (!package.has_value()) {
            cout << "  Package is not installed.\n";
            return;
        }

        vector<string> dependents;

        for (const Package& installed :
             installed_.all()) {
            if (installed.name == name) {
                continue;
            }

            for (const Dependency& dependency :
                 installed.dependencies) {
                if (dependency.name == name) {
                    dependents.push_back(installed.name);
                }
            }
        }

        if (!dependents.empty()) {
            cout << "  Removal blocked. Required by: ";

            for (size_t index = 0;
                 index < dependents.size();
                 ++index) {
                if (index > 0) {
                    cout << ", ";
                }

                cout << dependents[index];
            }

            cout << '\n';
            return;
        }

        installed_.remove(name);

        cout
            << "  Removed "
            << package->identifier()
            << '\n';
    }

    void listInstalled() const {
        cout << "\nInstalled packages:\n";

        const vector<Package> packages =
            installed_.all();

        if (packages.empty()) {
            cout << "  none\n";
            return;
        }

        for (const Package& package : packages) {
            cout
                << "  "
                << package.identifier()
                << '\n';
        }
    }

    void upgradeAll() {
        cout << "\nChecking for upgrades...\n";

        size_t upgrades = 0;

        for (const Package& installed :
             installed_.all()) {
            vector<Package> candidates;

            for (const Repository& repository :
                 repositories_) {
                vector<Package> found =
                    repository.candidates(installed.name);

                candidates.insert(
                    candidates.end(),
                    found.begin(),
                    found.end()
                );
            }

            for (const Package& candidate : candidates) {
                if (
                    compareVersions(
                        candidate.version,
                        installed.version
                    ) > 0
                ) {
                    cout
                        << "  "
                        << installed.identifier()
                        << " -> "
                        << candidate.identifier()
                        << '\n';

                    installed_.install(candidate);
                    ++upgrades;
                    break;
                }
            }
        }

        cout
            << "Upgrade count: "
            << upgrades
            << '\n';
    }
};


// ---------------------------------------------------------------------------
// Repository construction
// ---------------------------------------------------------------------------

vector<Repository> createRepositories() {
    Repository mainRepository(
        "ubuntu-main",
        "https://archive.ubuntu.com/ubuntu"
    );

    Repository securityRepository(
        "ubuntu-security",
        "https://security.ubuntu.com/ubuntu"
    );

    mainRepository.addPackage(Package{
        "libc",
        "2.38",
        "amd64",
        "ubuntu-main",
        "Core C library",
        {},
        8.0,
        true
    });

    mainRepository.addPackage(Package{
        "libssl",
        "3.0.13",
        "amd64",
        "ubuntu-main",
        "TLS and cryptographic library",
        {Dependency{"libc", ">=", "2.38"}},
        4.0,
        false
    });

    mainRepository.addPackage(Package{
        "webserver",
        "1.4.0",
        "amd64",
        "ubuntu-main",
        "HTTP server",
        {
            Dependency{"libc", ">=", "2.38"},
            Dependency{"libssl", ">=", "3.0"}
        },
        12.0,
        false
    });

    mainRepository.addPackage(Package{
        "database-client",
        "16.2",
        "amd64",
        "ubuntu-main",
        "Database client",
        {Dependency{"libssl", ">=", "3.0"}},
        10.0,
        false
    });

    securityRepository.addPackage(Package{
        "libssl",
        "3.0.14",
        "amd64",
        "ubuntu-security",
        "TLS security update",
        {Dependency{"libc", ">=", "2.38"}},
        4.2,
        false
    });

    return {
        move(mainRepository),
        move(securityRepository)
    };
}


// ---------------------------------------------------------------------------
// Dependency graph visualization
// ---------------------------------------------------------------------------

void printDependencyGraph(
    const vector<Repository>& repositories,
    const string& root
) {
    cout
        << "\nDependency graph for "
        << root
        << ":\n";

    InstalledDatabase emptyDatabase;

    DependencyResolver resolver(
        repositories,
        emptyDatabase
    );

    set<string> visited;

    function<void(const string&, int)> walk =
        [&](const string& name, int depth) {
            if (visited.contains(name)) {
                cout
                    << string(depth, ' ')
                    << name
                    << " (already visited)\n";
                return;
            }

            const Dependency dependency{
                name,
                "",
                ""
            };

            /*
             * Reuse the repository data directly here because the graph
             * should display the newest available candidate.
             */
            optional<Package> newest;

            for (const Repository& repository :
                 repositories) {
                for (const Package& package :
                     repository.candidates(name)) {
                    if (
                        !newest.has_value() ||
                        compareVersions(
                            package.version,
                            newest->version
                        ) > 0
                    ) {
                        newest = package;
                    }
                }
            }

            if (!newest.has_value()) {
                cout
                    << string(depth, ' ')
                    << name
                    << " (missing)\n";
                return;
            }

            visited.insert(name);

            cout
                << string(depth, ' ')
                << newest->name
                << ' '
                << newest->version
                << '\n';

            for (const Dependency& child :
                 newest->dependencies) {
                cout
                    << string(depth + 2, ' ')
                    << "requires "
                    << child.name
                    << ' '
                    << child.operatorSymbol
                    << ' '
                    << child.requiredVersion
                    << '\n';

                walk(child.name, depth + 4);
            }
        };

    walk(root, 0);
}


// ---------------------------------------------------------------------------
// Command reference
// ---------------------------------------------------------------------------

void printCommandReference() {
    cout << R"(
Real package-manager commands:

Debian/Ubuntu:
  sudo apt update
  apt search nginx
  apt show nginx
  sudo apt install nginx
  sudo apt remove nginx
  sudo apt purge nginx
  sudo apt upgrade
  sudo apt full-upgrade
  apt list --installed
  apt policy nginx
  sudo apt autoremove

Low-level Debian:
  dpkg -l
  dpkg -s nginx
  dpkg -L nginx
  dpkg -S /usr/bin/example
  sudo dpkg -i package.deb

RPM-family:
  sudo dnf check-update
  sudo dnf search nginx
  dnf info nginx
  sudo dnf install nginx
  sudo dnf remove nginx
  sudo dnf upgrade
  sudo dnf autoremove
  sudo dnf clean all

Low-level RPM:
  rpm -q nginx
  rpm -qi nginx
  rpm -ql nginx
  rpm -qf /usr/bin/example
  sudo rpm -Uvh package.rpm

YUM:
  sudo yum install nginx
  sudo yum update
  sudo yum remove nginx

APT uses dpkg as its low-level package database/tool.
DNF/YUM operate in the RPM ecosystem, with rpm as the lower-level tool.

These commands are documentation only and are not executed by this program.
)";
}


// ---------------------------------------------------------------------------
// Edge-case demonstration
// ---------------------------------------------------------------------------

void demonstrateEdgeCases() {
    cout << R"(
Important edge cases:

1. Missing dependencies
   A required dependency may not exist in any enabled repository.

2. Version conflicts
   Two packages may require incompatible versions of the same dependency.

3. Circular dependencies
   Dependency graphs can contain cycles that a resolver must detect.

4. Disabled repositories
   An available package may become unavailable when its repository is disabled.

5. Untrusted repositories
   Repository provenance and package signatures are security boundaries.

6. Architecture mismatches
   amd64 and arm64 packages are not interchangeable.

7. Removal dependencies
   Removing a library can break installed applications.

8. Configuration files
   Package removal and configuration-file cleanup are distinct concepts.

9. Interrupted transactions
   Failed maintainer scripts, disk errors, or interruptions may require
   package-database recovery.

10. Downgrades
    Older versions can introduce compatibility and security issues.

11. Distribution upgrades
    A distribution release upgrade is substantially broader than an
    ordinary package upgrade.

12. Kernel updates
    Multiple installed kernels may be intentionally retained to provide
    fallback boot options.
)";
}


// ---------------------------------------------------------------------------
// Main case study
// ---------------------------------------------------------------------------

int main() {
    cout
        << "============================================================\n"
        << "LINUX PACKAGE MANAGEMENT CASE STUDY\n"
        << "============================================================\n";

    vector<Repository> repositories =
        createRepositories();

    PackageManager packageManager(
        move(repositories)
    );

    packageManager.refreshMetadata();

    packageManager.search("ssl");

    packageManager.show("webserver");

    /*
     * Recreate repositories for graph inspection because the manager owns
     * its repository collection after move.
     */
    vector<Repository> graphRepositories =
        createRepositories();

    printDependencyGraph(
        graphRepositories,
        "webserver"
    );

    packageManager.install("webserver");
    packageManager.listInstalled();

    /*
     * database-client shares libssl with webserver. The package database
     * therefore illustrates why removing a dependency must consider
     * dependent packages.
     */
    packageManager.install("database-client");
    packageManager.listInstalled();

    packageManager.remove("libssl");

    packageManager.upgradeAll();
    packageManager.listInstalled();

    /*
     * Remove applications first, then the shared dependency.
     */
    packageManager.remove("database-client");
    packageManager.remove("webserver");
    packageManager.remove("libssl");
    packageManager.remove("libc");

    packageManager.listInstalled();

    demonstrateEdgeCases();
    printCommandReference();

    cout << R"(
Production design considerations:

- Package repositories should be authenticated and trusted.
- Package signatures should be verified by the package-management system.
- Administrative operations should follow least-privilege practices.
- Production transactions should be tested and reviewed.
- Backups and recovery procedures are required before high-risk changes.
- Repository release mixing should be avoided unless explicitly supported.
- Automation should account for noninteractive operation and idempotency.
- Package changes can restart services or alter configuration behavior.
- Monitoring should verify application health after package transactions.
- Audit records should identify what changed and when.

Complexity considerations:

Let P be the number of candidate packages and E the number of dependency
relationships examined.

Repository search can be approximately O(P) in this simple implementation.

Sorting candidates costs approximately O(P log P).

Dependency traversal is approximately O(V + E) once candidates have been
selected, where V is the number of packages in the dependency graph.

Real package managers use more sophisticated metadata indexes, dependency
solvers, repository policies, transaction checks, and package databases.
)";
    
    return 0;
}
