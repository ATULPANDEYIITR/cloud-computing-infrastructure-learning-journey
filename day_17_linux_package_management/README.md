# Linux package management: apt, yum, and dnf

## Topic introduction

Linux package management is the system used to discover, install, remove, upgrade, verify, and maintain software packages on a Linux distribution.

A package is more than an executable file. It normally contains software files together with metadata describing its name, version, architecture, dependencies, configuration behavior, maintainer information, and other properties required by the operating system's package infrastructure.

A package manager connects several components:

- package repositories
- repository metadata
- package archives
- dependency relationships
- an installed-package database
- version-selection rules
- transaction planning
- package installation and removal mechanisms
- configuration-file handling
- package verification and trust mechanisms

Two major Linux packaging ecosystems are represented in this study:

| Ecosystem | Common distributions | Package format | Lower-level package tool | Higher-level manager |
|---|---|---|---|---|
| Debian | Debian, Ubuntu and derivatives | `.deb` | `dpkg` | `apt` |
| RPM | Fedora, RHEL-family distributions and related systems | `.rpm` | `rpm` | `dnf`, historically `yum` |

The names `apt`, `yum`, and `dnf` refer to package-management interfaces rather than interchangeable commands for every Linux distribution.

The implementations in this repository model package repositories, package metadata, dependencies, dependency resolution, transactions, upgrades, removals, version comparison, and operational considerations without modifying the host operating system.

## Fundamental concepts

### Package

A package is a structured software distribution unit.

A package may contain:

- executables
- shared libraries
- configuration files
- documentation
- service definitions
- metadata
- dependency information
- installation or removal scripts

On Debian-based systems, packages commonly use the `.deb` format.

On RPM-based systems, packages commonly use the `.rpm` format.

A package normally has at least:

- package name
- version
- architecture
- package format
- dependency metadata
- repository or provenance information

The examples model a package with fields such as `name`, `version`, `architecture`, `dependencies`, `repository`, and `description`.

### Package repository

A repository is a managed source of package metadata and package artifacts.

A system may use several repositories at once. For example, a Debian-based system can obtain packages from different repository components, while an RPM-based system can have multiple enabled repositories providing different software collections.

Repository metadata allows the package manager to determine:

- which packages exist
- which versions are available
- package dependencies
- architecture information
- repository provenance
- package checksums or signatures
- other metadata needed for package selection

Repository configuration is therefore an important part of system administration.

### Installed package database

A Linux system needs to know what packages are installed.

On Debian systems, `dpkg` maintains package state used by higher-level tools such as APT.

In the RPM ecosystem, the RPM database records installed package information, while DNF or compatible interfaces provide higher-level dependency and repository management.

The Python and C++ implementations model this database with dictionaries or maps.

### Dependency

A dependency expresses a requirement between packages.

For example:

`webserver` may require `libssl >= 3.0`.

This means that installing the web server requires a compatible version of the TLS library.

Dependencies can form a graph:

`webserver -> libssl -> libc`

The graph can be much larger in a real operating system.

### Transaction

A transaction is a coordinated package operation.

Examples include:

- install one package
- install a package and several dependencies
- upgrade several packages
- remove a package
- replace one version with another

A transaction is different from simply copying a file into a directory. The package manager must maintain consistent package state while considering dependencies, conflicts, configuration files, scripts, architecture, repository policy, and other constraints.

## Core relationship between package tools

A useful conceptual model is:

`dpkg <- apt`

for Debian-based systems, and:

`rpm <- dnf/yum`

for RPM-based systems.

The lower-level tools understand the package format and installed package database.

The higher-level tools provide repository-aware dependency management and transaction planning.

This distinction is important.

For example, installing an individual `.deb` with `dpkg -i` does not provide the same repository-aware dependency resolution behavior as installing the package through APT.

Likewise, `rpm` and `dnf` have different responsibilities even though both operate in the RPM ecosystem.

## apt

APT is the higher-level package-management system commonly used on Debian and Ubuntu systems.

### Refreshing metadata

`sudo apt update`

The word `update` here primarily means refreshing package metadata.

It does not mean that every installed package is automatically upgraded.

This distinction is one of the most important concepts for beginners.

### Searching

`apt search nginx`

This searches package metadata for matching packages.

### Inspecting a package

`apt show nginx`

This displays package metadata such as:

- description
- version
- dependencies
- package size
- architecture
- repository information

### Installing

`sudo apt install nginx`

APT resolves required dependencies and proposes a package transaction.

The proposed transaction should be reviewed before confirmation, especially on production systems.

### Removing

`sudo apt remove nginx`

This removes the package while generally treating configuration-file handling differently from a purge operation.

### Purging

`sudo apt purge nginx`

Purging is more aggressive about package-managed configuration files than ordinary removal.

The exact files affected depend on package behavior and the distribution's package-management rules.

### Upgrading

`sudo apt upgrade`

This upgrades installed packages according to the transaction rules supported by the distribution.

A broader operation is:

`sudo apt full-upgrade`

A full upgrade can make dependency changes that involve installing or removing packages when required by the overall upgrade.

### Listing installed packages

`apt list --installed`

This queries installed package information.

### Candidate versions

`apt policy nginx`

This is useful for understanding:

- installed version
- candidate version
- available repository versions
- repository priorities

### Automatically installed dependencies

`sudo apt autoremove`

This can remove packages that were installed as dependencies and are no longer considered required.

It should still be reviewed before confirmation.

## dpkg

`dpkg` is the lower-level package management tool associated with Debian packages.

Useful commands include:

`dpkg -l`

Lists package states.

`dpkg -s nginx`

Shows status information for a package.

`dpkg -L nginx`

Lists files installed by a package.

`dpkg -S /usr/bin/example`

Searches for the package that owns a file.

`sudo dpkg -i package.deb`

Installs an individual Debian package archive.

APT and dpkg should not be considered interchangeable.

A useful mental model is that APT handles repository-oriented dependency management while dpkg handles lower-level Debian package operations.

## dnf

DNF is the modern package-management interface used widely in the Fedora and modern RPM ecosystem.

### Checking updates

`sudo dnf check-update`

Checks whether updates are available.

The command's exit status can also have special meanings when used in automation, so scripts should not blindly interpret every non-zero result as an operational failure.

### Searching

`sudo dnf search nginx`

Searches package metadata.

### Package information

`dnf info nginx`

Displays package information.

### Installing

`sudo dnf install nginx`

Installs the requested package and resolves dependencies.

### Removing

`sudo dnf remove nginx`

Removes a package and evaluates the resulting dependency transaction.

### Upgrading

`sudo dnf upgrade`

Upgrades installed packages according to repository and dependency rules.

### Automatic dependency cleanup

`sudo dnf autoremove`

Can remove dependencies that are no longer required, subject to DNF's package-state logic.

### Cache cleanup

`sudo dnf clean all`

Clears cached repository information and package data.

## yum

YUM is historically associated with RPM-based Linux distributions.

Common commands include:

`sudo yum install nginx`

`sudo yum update`

`sudo yum remove nginx`

`yum info nginx`

Modern RPM-based distributions may provide `yum` as a compatibility interface associated with DNF.

The exact implementation and behavior depend on the distribution release.

It is therefore important to determine what a particular operating system actually provides instead of assuming that historical YUM behavior applies unchanged.

## rpm

RPM is the lower-level package tool and package format associated with the RPM ecosystem.

Examples include:

`rpm -q nginx`

Queries whether a package is installed.

`rpm -qi nginx`

Displays detailed installed-package information.

`rpm -ql nginx`

Lists files owned by an installed package.

`rpm -qf /usr/bin/example`

Determines which installed package owns a file.

`sudo rpm -Uvh package.rpm`

Performs a low-level RPM package operation.

DNF provides functionality above this level, including repository metadata and dependency resolution.

## Python implementation

The Python program provides a complete simulated package-management environment.

### Package representation

The `Package` class represents package metadata.

Important fields include:

- `name`
- `version`
- `architecture`
- `dependencies`
- `description`
- `repository`
- `size_mb`
- `essential`

The `identifier` property produces a readable package identifier such as:

`webserver=1.4.0:amd64`

### Dependency representation

The `Dependency` class stores a package requirement.

For example:

`Dependency("libssl", ">=3.0")`

represents a requirement for a compatible version of `libssl`.

The `satisfied_by()` method evaluates whether a package satisfies the requirement.

### Repository model

The `Repository` class contains packages and repository metadata.

The model distinguishes:

- enabled repositories
- disabled repositories
- trusted repositories
- package candidates

A real package manager performs substantially more validation than this educational implementation.

### Installed database

`InstalledDatabase` stores currently installed packages.

Its main operations are:

- `install()`
- `remove()`
- `get()`
- `all()`

This illustrates the difference between available packages and installed packages.

### Dependency resolver

`DependencyResolver` constructs a dependency solution.

The resolver:

1. receives a root package
2. checks installed packages
3. searches enabled and trusted repositories
4. selects compatible candidates
5. recursively processes dependencies
6. detects circular traversal
7. reports missing or incompatible dependencies

This models the fundamental reason a package manager is more complex than a file downloader.

### Transaction

The `PackageManager.install()` method first resolves dependencies and then creates a transaction.

It distinguishes:

- new installation
- upgrade
- already satisfied state

The program prints the transaction before applying it.

That reflects an important operational principle: the administrator should understand what a real package manager proposes before confirming a potentially large change.

## JavaScript implementation

The JavaScript program approaches the same domain from an application and event-driven perspective.

### Classes

The implementation contains:

- `Dependency`
- `Package`
- `Repository`
- `RepositoryClient`
- `PackageDatabase`
- `DependencyResolver`
- `TransactionPlanner`
- `SimulatedPackageManager`

The separation demonstrates modular application design.

### Asynchronous repository operations

`RepositoryClient` contains asynchronous methods for metadata refresh and searching.

`Promise.all()` allows multiple repository operations to be modeled as concurrent operations.

This is relevant because package management often involves several repositories and network requests.

The simulation does not contact actual repositories.

### Map

JavaScript `Map` is used for package storage.

This gives direct key-based lookup by package name.

It models an important property of package databases: efficient lookup by package identity.

### Set

A `Set` tracks dependency nodes currently being resolved.

This supports cycle detection.

A dependency graph containing:

`A -> B -> C -> A`

would otherwise produce unbounded recursive traversal.

### Transaction planner

`TransactionPlanner` separates dependency resolution from transaction planning.

This is an important architectural distinction.

Resolution determines which packages are required.

Planning determines which installed packages must be installed or upgraded.

Execution is a separate phase.

## C++ case study

The C++ program models a server software deployment system.

The scenario assumes that an administrator wants to install an HTTP server while the system automatically determines its dependencies.

The package graph is approximately:

`webserver -> libssl -> libc`

A second package, `database-client`, also depends on `libssl`.

This creates a shared dependency.

### Repository architecture

The `Repository` class stores:

- repository name
- repository URL
- enabled status
- trust status
- package records

The implementation refuses repository candidates from disabled or untrusted repositories.

This demonstrates why repository state affects dependency resolution.

### Package database

`InstalledDatabase` uses `std::map`.

It provides:

- lookup
- membership checks
- installation
- removal
- enumeration

The map models the installed package database.

### Dependency resolver

`DependencyResolver` searches all eligible repositories and chooses compatible package candidates.

It considers:

- package name
- version constraint
- installed state
- repository availability
- dependency relationships
- circular dependencies

The resolver uses a set named `visiting` to detect dependency cycles.

### Transaction planning

The program generates explicit operations:

- `Install`
- `Upgrade`

Before applying them, the transaction is printed.

This separation is valuable because production package systems must validate a transaction before modifying system state.

### Removal validation

The C++ case study does not blindly remove a package.

Before removing a package, it searches installed packages for dependents.

For example, removing `libssl` while `webserver` still requires it is rejected.

This models an important package-management invariant:

> An installed package should not be removed when doing so would leave required dependencies unsatisfied.

Real package managers may solve the situation by proposing removal of dependent packages, replacement packages, or another dependency-compatible transaction.

## Dependency graphs

Dependency resolution is naturally modeled as a graph.

A package is a vertex.

A dependency is a directed edge.

For example:

`webserver -> libssl`

means that `webserver` depends on `libssl`.

A larger graph might look conceptually like:

`application -> framework -> runtime -> libc`

and:

`application -> crypto-library -> libc`

The shared `libc` dependency demonstrates why package managers must consider the entire transaction rather than independently processing each package.

### Cycles

A graph can contain:

`A -> B -> C -> A`

A naive recursive implementation would continue indefinitely.

The implementations use a visiting set to identify cycles.

### Missing dependencies

Suppose:

`application -> libexample >= 4.0`

but all repositories only contain versions below `4.0`.

The dependency is unsatisfied.

A package manager must reject the transaction or find another valid solution.

## Version selection

The example implementations contain simplified version comparison logic.

For teaching purposes, versions are split into numeric and alphabetic components.

Real package management is more complicated.

Debian package versions use the comparison rules implemented by Debian's packaging tools.

RPM uses its own version-release semantics, including the Epoch-Version-Release model.

A generic string comparison should therefore not be used to determine the real upgrade order of Linux packages.

The Python, JavaScript, and C++ functions are deliberately educational rather than replacements for `dpkg` or RPM version algorithms.

## Repository selection

A system can have multiple repositories.

A package may exist in:

- a base repository
- a security repository
- an update repository
- a vendor repository
- an internal enterprise repository
- a third-party repository

Package managers therefore need repository policy.

Factors can include:

- enabled status
- trust
- repository priority
- architecture
- package version
- distribution release
- dependency compatibility

Adding repositories is not merely a convenience operation. It changes the software supply chain and trust boundary of the system.

## Security considerations

### Package signatures

Repository packages and metadata can be cryptographically authenticated.

Package signatures help protect against unauthorized modification and provide provenance guarantees when the trust configuration is correct.

HTTPS provides transport security but should not be treated as the only security mechanism.

### Repository trust

Administrators should understand:

- who operates a repository
- which signing keys are trusted
- which packages it provides
- which distribution release it targets
- how updates are maintained

Randomly mixing repositories can produce dependency conflicts and unsupported system states.

### Supply-chain risk

Package management is part of the software supply chain.

Relevant threats include:

- compromised repositories
- compromised signing infrastructure
- malicious packages
- stolen or misused signing keys
- dependency confusion
- malicious third-party repositories
- compromised package mirrors

### Least privilege

Package installation usually requires administrative privileges.

Commands such as:

`sudo apt install package`

or:

`sudo dnf install package`

should be used deliberately.

The administrative portion should be limited to the operation that requires elevated privileges.

## Configuration files

Package installation frequently creates configuration files.

Package removal and configuration cleanup are not necessarily identical operations.

On Debian-based systems, the distinction between `remove` and `purge` is particularly important.

Configuration handling also creates a common administrative issue: a package update can encounter an existing locally modified configuration file.

The package manager may need to determine whether to:

- retain the administrator's version
- install the package's version
- create a separate copy
- request administrator input

Automated systems must handle these situations deliberately.

## Updates and upgrades

A package-management update has several distinct meanings.

For APT:

`apt update`

refreshes repository metadata.

`apt upgrade`

changes installed packages.

These operations should not be confused.

A distribution release upgrade is broader than an ordinary package upgrade.

It may involve:

- thousands of package changes
- repository changes
- configuration changes
- dependency transitions
- service restarts
- kernel changes
- removal of obsolete packages

A release upgrade therefore requires more planning than routine security patching.

## Automatic dependencies

A package can be installed explicitly or as a dependency.

For example:

`webserver`

may explicitly be requested by an administrator, while:

`libssl`

may have been installed because `webserver` requires it.

When the explicit package is removed, the dependency may become unused.

Commands such as:

`sudo apt autoremove`

or:

`sudo dnf autoremove`

can identify candidates for removal.

Such transactions should still be reviewed because dependency relationships can be more complicated than they initially appear.

## Common mistakes

### Confusing `apt update` and `apt upgrade`

`apt update` refreshes package metadata.

`apt upgrade` upgrades installed packages.

Running only `apt update` does not perform the ordinary package upgrade operation.

### Treating dpkg as a complete replacement for APT

`dpkg` handles low-level Debian package operations.

APT adds repository-aware dependency resolution and package selection.

### Mixing distribution releases

Repositories intended for different releases can contain incompatible libraries and dependencies.

Repository configuration should match the supported operating-system release.

### Adding untrusted repositories

A third-party repository expands the system's software trust boundary.

Repository provenance should be evaluated before enabling it.

### Removing libraries blindly

A library can have many dependents.

Removing a shared dependency can break several applications.

### Assuming package names are universal

A package name on Ubuntu may not exist under the same name on Fedora or RHEL.

Package availability depends on the distribution and repository ecosystem.

### Ignoring architecture

A package built for `amd64` is not automatically suitable for `arm64`.

### Assuming successful installation means application health

A package transaction can succeed while an application later fails because of:

- invalid configuration
- missing external services
- port conflicts
- permissions
- firewall rules
- incompatible data
- application-specific errors

Package installation and application health are separate concerns.

## Edge cases

### Missing dependency

A package requires another package that is unavailable.

The resolver must report a failure or find another valid candidate.

### Conflicting dependencies

Package A may require:

`library >= 3`

while package B requires:

`library < 3`

The transaction cannot simply select an arbitrary version.

### Circular dependency

A cycle must be detected during graph traversal.

### Disabled repository

A package may exist in repository metadata that is not currently enabled.

The package is therefore not necessarily an available candidate for the current transaction.

### Untrusted repository

A repository that is not trusted should not be treated as an ordinary package source.

### Held or excluded packages

Administrative policies can prevent selected packages from being upgraded.

Such policies can change dependency resolution.

### Downgrades

A downgrade is different from an upgrade.

It can be required for compatibility but can also reintroduce vulnerabilities or incompatible behavior.

### Interrupted transactions

Failures can occur because of:

- disk exhaustion
- filesystem errors
- interrupted package scripts
- power loss
- dependency conflicts
- configuration conflicts

Recovery procedures depend on the package ecosystem and system state.

## Performance considerations

Package management includes several potentially expensive activities.

### Repository metadata

Repository metadata may be large.

Package managers cache metadata to reduce repeated network transfers.

### Dependency resolution

A real dependency graph can contain thousands of packages.

Let:

- `V` be the number of package nodes
- `E` be the number of dependency relationships

A graph traversal is commonly described in terms of:

`O(V + E)`

The simple implementations use additional sorting and candidate searching, so their total behavior is more expensive than a specialized production solver.

### Package downloads

Large upgrades consume:

- network bandwidth
- disk space
- CPU
- I/O

### Transaction size

A transaction involving hundreds or thousands of packages has a larger operational impact than installing a single isolated application.

### Automation

Automated build systems can benefit from package caches.

Caching improves speed but introduces the need to handle stale metadata and package availability correctly.

## Implementation considerations

### Python

Python is useful for:

- rapid modeling
- dependency graph experiments
- educational tooling
- administrative automation
- parsing package metadata
- prototyping package-management workflows

The Python implementation uses:

- `dataclass`
- dictionaries
- sets
- lists
- recursive dependency resolution
- custom exceptions
- command-line argument parsing

### JavaScript

JavaScript is useful for:

- web-based administration interfaces
- asynchronous repository applications
- package metadata dashboards
- API-backed management systems
- event-driven operational tools

The JavaScript implementation demonstrates:

- classes
- `Map`
- `Set`
- promises
- `async` and `await`
- `Promise.all()`
- validation
- error handling
- transaction planning

### C++

C++ is appropriate when a system needs:

- explicit data structures
- deterministic resource management
- high performance
- low-level systems integration
- strong compile-time type checking

The C++ case study uses:

- classes
- structures
- `std::map`
- `std::set`
- `std::vector`
- `std::optional`
- lambdas
- recursive graph traversal
- exception handling
- explicit transaction structures

## Real-world applications

Linux package management is fundamental to:

- server administration
- cloud virtual machines
- container images
- developer workstations
- continuous integration systems
- security patch management
- enterprise Linux environments
- scientific computing systems
- edge devices
- infrastructure automation
- software deployment

A typical server lifecycle may include:

`repository configuration -> metadata refresh -> package selection -> dependency resolution -> transaction planning -> installation -> service configuration -> health verification`

Package management is therefore closely connected to system administration, security, infrastructure engineering, DevOps, and software supply-chain management.

## Production considerations

Production package management should account for:

- operating-system release
- repository provenance
- package signatures
- architecture
- dependency compatibility
- transaction scope
- service restarts
- configuration changes
- backups
- rollback or recovery procedures
- maintenance windows
- monitoring
- auditability
- automation behavior

A package manager manages software state, but it does not automatically guarantee application availability.

A successful package transaction should be followed by appropriate application and service verification when the change affects production workloads.

## Important distinctions

| Concept | Meaning |
|---|---|
| Package | Software distribution unit with metadata |
| Repository | Source of package metadata and package artifacts |
| Dependency | Requirement on another package or capability |
| Transaction | Coordinated set of package changes |
| Package database | Record of installed package state |
| apt | High-level package manager for Debian-family systems |
| dpkg | Lower-level Debian package tool |
| dnf | High-level RPM-family package manager |
| yum | Historical and compatibility-oriented RPM-family interface |
| rpm | Lower-level RPM package tool |
| `apt update` | Refreshes repository metadata |
| `apt upgrade` | Upgrades installed packages |
| `apt remove` | Removes a package |
| `apt purge` | Removes a package with stronger configuration cleanup behavior |
| `apt autoremove` | Removes packages considered no longer required |

## Running the Python study program

The Python file can be executed directly with:

`python3 package_manager.py`

The program runs a safe simulation and does not invoke real package-management commands.

A package search can be demonstrated with:

`python3 package_manager.py --search ssl`

Package information can be queried with:

`python3 package_manager.py --show webserver`

A simulated installation can be requested with:

`python3 package_manager.py --install webserver`

A command can be interpreted without execution:

`python3 package_manager.py --command "sudo apt install nginx"`

The command-analysis mode tokenizes the command and explains its package-management operation.

## Running the JavaScript implementation

The JavaScript program can be executed with:

`node package_manager.js`

It performs an asynchronous repository simulation, dependency resolution, installation, removal, and transaction demonstration.

An interactive simulated environment can be started with:

`node package_manager.js --interactive`

The interactive commands include:

`update`

`search ssl`

`install webserver`

`remove webserver`

`list`

`exit`

These commands operate only on the in-memory simulation.

## Compiling the C++ case study

The C++ program targets C++17.

A typical compilation command is:

`g++ -std=c++17 -Wall -Wextra -pedantic package_manager.cpp -o package_manager`

The executable can then be run with:

`./package_manager`

On Windows environments, the executable name and invocation depend on the installed C++ toolchain.

The program does not invoke `apt`, `yum`, `dnf`, `rpm`, or `dpkg`.

## Scope and limitations

The implementations are educational models rather than replacements for Linux package managers.

They simplify several areas, including:

- version semantics
- repository metadata
- package signatures
- cryptographic verification
- dependency solving
- package conflicts
- file ownership
- file conflicts
- package scripts
- triggers
- service management
- configuration-file merging
- transaction rollback
- disk-space checks
- architecture policy
- repository priority
- package pinning
- distribution-specific dependency rules

The simplified version comparison algorithms are especially important to understand. Debian and RPM have established package-version semantics that should be delegated to their native package-management infrastructure rather than recreated with generic string comparison.

The simulations are intentionally safe: they model package-management behavior without changing the Linux installation on which they are executed.
