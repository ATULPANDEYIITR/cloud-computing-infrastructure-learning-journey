#!/usr/bin/env python3
"""
Linux Package Management: apt, yum, and dnf

A self-contained study and demonstration program covering:
- Packages and package repositories
- Package metadata
- Installation, removal, upgrade, and downgrade concepts
- Dependencies and dependency resolution
- apt, apt-get, yum, and dnf
- Repositories and repository metadata
- Package queries
- Transactions
- Configuration files
- Package verification
- Cache management
- Version comparison
- Dependency graphs
- Security and operational considerations
- A complete simulated package manager for experimentation

The program intentionally does not modify the host operating system.
Real package-manager commands are displayed as examples and are never
executed automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cmp_to_key
from typing import Dict, Iterable, List, Optional, Set, Tuple
import argparse
import re
import shlex
import sys


# ---------------------------------------------------------------------------
# 1. Fundamental terminology
# ---------------------------------------------------------------------------

TERMINOLOGY = {
    "package": (
        "A distributable unit containing software, metadata, files, and "
        "dependency information."
    ),
    "repository": (
        "A trusted collection of package metadata and package artifacts "
        "from which software can be obtained."
    ),
    "dependency": (
        "Another package or capability required by a package."
    ),
    "transaction": (
        "A coordinated package-management operation such as installing, "
        "removing, or upgrading packages."
    ),
    "package_manager": (
        "Software that resolves dependencies and performs package "
        "transactions."
    ),
    "package_format": (
        "The packaging representation. Debian-based systems commonly use "
        ".deb, while Red Hat-family systems commonly use .rpm."
    ),
}


def show_terminology() -> None:
    print("\n=== Fundamental terminology ===")
    for name, description in TERMINOLOGY.items():
        print(f"{name:18} {description}")


# ---------------------------------------------------------------------------
# 2. Version comparison
# ---------------------------------------------------------------------------

def split_version(version: str) -> List[Tuple[int, str]]:
    """
    Convert a version into comparable numeric/text components.

    This is intentionally a teaching implementation rather than a complete
    reproduction of Debian's dpkg version algorithm or RPM's EVR algorithm.
    Real package managers have distribution-specific version semantics.
    """
    parts = re.findall(r"\d+|[A-Za-z]+", version)
    result: List[Tuple[int, str]] = []

    for part in parts:
        if part.isdigit():
            result.append((0, part.zfill(20)))
        else:
            result.append((1, part.lower()))

    return result


def compare_versions(left: str, right: str) -> int:
    """Return -1 if left < right, 0 if equal, and 1 if left > right."""
    a = split_version(left)
    b = split_version(right)

    for x, y in zip(a, b):
        if x[0] != y[0]:
            return -1 if x[0] < y[0] else 1

        if x[1] != y[1]:
            return -1 if x[1] < y[1] else 1

    if len(a) == len(b):
        return 0

    return -1 if len(a) < len(b) else 1


def demonstrate_versions() -> None:
    print("\n=== Version comparison ===")

    examples = [
        ("1.0", "2.0"),
        ("2.10", "2.9"),
        ("1.2.3", "1.2.3"),
        ("3.0", "3.0.1"),
    ]

    for left, right in examples:
        result = compare_versions(left, right)
        symbol = "<" if result < 0 else "=" if result == 0 else ">"
        print(f"{left} {symbol} {right}")


# ---------------------------------------------------------------------------
# 3. Package model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Dependency:
    """
    A dependency expression.

    Examples:
        Dependency("libssl")
        Dependency("python", ">=3.11")
    """

    name: str
    constraint: Optional[str] = None

    def satisfied_by(self, package: "Package") -> bool:
        if package.name != self.name:
            return False

        if self.constraint is None:
            return True

        match = re.match(r"(>=|<=|=|>|<)\s*(.+)", self.constraint)
        if not match:
            raise ValueError(f"Unsupported constraint: {self.constraint}")

        operator, required_version = match.groups()
        comparison = compare_versions(package.version, required_version)

        return {
            ">": comparison > 0,
            ">=": comparison >= 0,
            "<": comparison < 0,
            "<=": comparison <= 0,
            "=": comparison == 0,
        }[operator]


@dataclass
class Package:
    name: str
    version: str
    architecture: str = "amd64"
    dependencies: List[Dependency] = field(default_factory=list)
    description: str = ""
    repository: str = "main"
    size_mb: float = 1.0
    essential: bool = False
    installed: bool = False

    @property
    def identifier(self) -> str:
        return f"{self.name}={self.version}:{self.architecture}"

    def short_description(self) -> str:
        return (
            f"{self.name} {self.version} [{self.architecture}] "
            f"from {self.repository}"
        )


# ---------------------------------------------------------------------------
# 4. Repository model
# ---------------------------------------------------------------------------

@dataclass
class Repository:
    name: str
    url: str
    packages: List[Package] = field(default_factory=list)
    enabled: bool = True
    trusted: bool = True

    def add(self, package: Package) -> None:
        self.packages.append(package)

    def search(self, term: str) -> List[Package]:
        term = term.lower()
        return [
            package
            for package in self.packages
            if term in package.name.lower()
            or term in package.description.lower()
        ]

    def candidates(self, package_name: str) -> List[Package]:
        return [
            package
            for package in self.packages
            if package.name == package_name
        ]


# ---------------------------------------------------------------------------
# 5. Installed package database
# ---------------------------------------------------------------------------

class InstalledDatabase:
    """
    A simplified representation of a package database.

    Debian systems maintain package state through dpkg. RPM-family systems
    maintain package state through the RPM database. apt and dnf/yum operate
    at a higher dependency-management level.
    """

    def __init__(self) -> None:
        self.packages: Dict[str, Package] = {}

    def install(self, package: Package) -> None:
        package.installed = True
        self.packages[package.name] = package

    def remove(self, name: str) -> Package:
        if name not in self.packages:
            raise KeyError(f"Package is not installed: {name}")

        package = self.packages.pop(name)
        package.installed = False
        return package

    def get(self, name: str) -> Optional[Package]:
        return self.packages.get(name)

    def all(self) -> List[Package]:
        return sorted(self.packages.values(), key=lambda p: p.name)


# ---------------------------------------------------------------------------
# 6. Dependency resolution
# ---------------------------------------------------------------------------

class DependencyError(Exception):
    """Raised when dependencies cannot be resolved."""


class DependencyResolver:
    def __init__(
        self,
        repositories: Iterable[Repository],
        installed: InstalledDatabase,
    ) -> None:
        self.repositories = list(repositories)
        self.installed = installed

    def available_candidates(self, name: str) -> List[Package]:
        candidates: List[Package] = []

        for repository in self.repositories:
            if not repository.enabled:
                continue
            if not repository.trusted:
                continue
            candidates.extend(repository.candidates(name))

        candidates.sort(
            key=cmp_to_key(
                lambda a, b: compare_versions(a.version, b.version)
            ),
            reverse=True,
        )

        return candidates

    def select_candidate(
        self,
        dependency: Dependency,
        selected: Dict[str, Package],
    ) -> Package:
        if dependency.name in selected:
            package = selected[dependency.name]
            if dependency.satisfied_by(package):
                return package
            raise DependencyError(
                f"Selected {package.identifier} does not satisfy "
                f"{dependency.name} {dependency.constraint or ''}"
            )

        installed = self.installed.get(dependency.name)
        if installed and dependency.satisfied_by(installed):
            selected[dependency.name] = installed
            return installed

        candidates = [
            package
            for package in self.available_candidates(dependency.name)
            if dependency.satisfied_by(package)
        ]

        if not candidates:
            raise DependencyError(
                f"No available candidate satisfies "
                f"{dependency.name} {dependency.constraint or ''}"
            )

        selected[dependency.name] = candidates[0]
        return candidates[0]

    def resolve(self, root: str) -> List[Package]:
        selected: Dict[str, Package] = {}
        visiting: Set[str] = set()

        def visit(dependency: Dependency) -> None:
            if dependency.name in visiting:
                raise DependencyError(
                    f"Circular dependency detected at {dependency.name}"
                )

            package = self.select_candidate(dependency, selected)

            if package.name in visiting:
                return

            visiting.add(package.name)

            for child in package.dependencies:
                visit(child)

            visiting.remove(package.name)

        visit(Dependency(root))

        # Dependencies appear before packages that require them.
        return list(selected.values())


# ---------------------------------------------------------------------------
# 7. Simulated package manager
# ---------------------------------------------------------------------------

class PackageManager:
    """
    Educational package manager simulation.

    The simulation models the important ideas behind apt/dnf/yum without
    changing the real operating system.
    """

    def __init__(self, repositories: List[Repository]) -> None:
        self.repositories = repositories
        self.installed = InstalledDatabase()
        self.resolver = DependencyResolver(repositories, self.installed)

    def refresh_metadata(self) -> None:
        print("\nRefreshing repository metadata...")
        for repository in self.repositories:
            state = "enabled" if repository.enabled else "disabled"
            print(f"  {repository.name}: {state}")
        print("Repository metadata refresh completed in simulation.")

    def search(self, term: str) -> None:
        print(f"\nSearch results for: {term}")

        found = False
        for repository in self.repositories:
            if not repository.enabled:
                continue

            for package in repository.search(term):
                print(f"  {package.short_description()}")
                found = True

        if not found:
            print("  No matching packages.")

    def show(self, name: str) -> None:
        candidates: List[Package] = []

        for repository in self.repositories:
            if repository.enabled:
                candidates.extend(repository.candidates(name))

        installed = self.installed.get(name)

        print(f"\nPackage information: {name}")

        if installed:
            print(f"  Installed: {installed.identifier}")
        else:
            print("  Installed: no")

        for candidate in sorted(
            candidates,
            key=cmp_to_key(
                lambda a, b: compare_versions(a.version, b.version)
            ),
            reverse=True,
        ):
            print(f"  Available: {candidate.identifier}")
            if candidate.dependencies:
                dependencies = ", ".join(
                    dependency.name
                    for dependency in candidate.dependencies
                )
                print(f"    Depends: {dependencies}")
            if candidate.description:
                print(f"    Description: {candidate.description}")

    def install(self, name: str) -> None:
        print(f"\nInstalling: {name}")

        try:
            packages = self.resolver.resolve(name)
        except DependencyError as error:
            print(f"ERROR: {error}")
            return

        transaction: List[Package] = []

        for package in packages:
            installed = self.installed.get(package.name)

            if installed is None:
                transaction.append(package)
            elif compare_versions(
                package.version, installed.version
            ) > 0:
                transaction.append(package)

        if not transaction:
            print("Nothing to do; requested package is already satisfied.")
            return

        print("Transaction:")
        for package in transaction:
            action = "upgrade" if self.installed.get(package.name) else "install"
            print(f"  {action:8} {package.identifier}")

        for package in transaction:
            self.installed.install(package)

        print("Transaction completed successfully.")

    def remove(self, name: str) -> None:
        print(f"\nRemoving: {name}")

        package = self.installed.get(name)

        if package is None:
            print("Package is not installed.")
            return

        dependents = [
            installed.name
            for installed in self.installed.all()
            if installed.name != name
            and any(
                dependency.name == name
                for dependency in installed.dependencies
            )
        ]

        if dependents:
            print(
                "Removal blocked because installed packages depend on it: "
                + ", ".join(dependents)
            )
            return

        if package.essential:
            print("Removal blocked: package is marked essential.")
            return

        self.installed.remove(name)
        print(f"Removed {package.identifier}")

    def upgrade_all(self) -> None:
        print("\nChecking installed packages for upgrades...")

        upgrades = 0

        for installed in list(self.installed.all()):
            candidates = self.resolver.available_candidates(installed.name)

            if not candidates:
                continue

            newest = candidates[0]

            if compare_versions(newest.version, installed.version) > 0:
                print(
                    f"  upgrade {installed.identifier} -> "
                    f"{newest.identifier}"
                )
                self.installed.install(newest)
                upgrades += 1

        if upgrades == 0:
            print("All installed packages are current in the simulation.")
        else:
            print(f"Upgraded {upgrades} package(s).")

    def list_installed(self) -> None:
        print("\nInstalled packages:")

        packages = self.installed.all()

        if not packages:
            print("  No packages installed.")
            return

        for package in packages:
            print(f"  {package.identifier}")


# ---------------------------------------------------------------------------
# 8. Repository construction
# ---------------------------------------------------------------------------

def build_demo_repositories() -> List[Repository]:
    """
    Build a small repository ecosystem.

    It deliberately contains multiple versions so upgrade behavior can be
    demonstrated.
    """

    base = Repository(
        name="ubuntu-main",
        url="https://archive.ubuntu.com/ubuntu",
    )

    security = Repository(
        name="ubuntu-security",
        url="https://security.ubuntu.com/ubuntu",
    )

    base.add(
        Package(
            name="libc",
            version="2.38",
            description="Core C library",
            size_mb=8,
            essential=True,
        )
    )

    base.add(
        Package(
            name="libssl",
            version="3.0.13",
            dependencies=[Dependency("libc", ">=2.38")],
            description="TLS and cryptographic library",
            size_mb=4,
        )
    )

    base.add(
        Package(
            name="python3",
            version="3.11.8",
            dependencies=[Dependency("libc", ">=2.38")],
            description="Python programming language runtime",
            size_mb=25,
        )
    )

    base.add(
        Package(
            name="webserver",
            version="1.4.0",
            dependencies=[
                Dependency("libc", ">=2.38"),
                Dependency("libssl", ">=3.0"),
            ],
            description="HTTP server",
            size_mb=12,
        )
    )

    base.add(
        Package(
            name="database-client",
            version="16.2",
            dependencies=[Dependency("libssl", ">=3.0")],
            description="Relational database client",
            size_mb=10,
        )
    )

    security.add(
        Package(
            name="libssl",
            version="3.0.14",
            dependencies=[Dependency("libc", ">=2.38")],
            description="Security update for TLS library",
            repository="ubuntu-security",
            size_mb=4.2,
        )
    )

    security.add(
        Package(
            name="python3",
            version="3.11.9",
            dependencies=[Dependency("libc", ">=2.38")],
            description="Security update for Python runtime",
            repository="ubuntu-security",
            size_mb=25.5,
        )
    )

    return [base, security]


# ---------------------------------------------------------------------------
# 9. Real package-manager command reference
# ---------------------------------------------------------------------------

def print_real_commands() -> None:
    print(
        """
=== Real Linux package-manager commands ===

Debian/Ubuntu with apt:
  sudo apt update
      Refresh repository metadata.

  apt search nginx
      Search package metadata.

  apt show nginx
      Display package metadata.

  sudo apt install nginx
      Install nginx and resolve dependencies.

  sudo apt remove nginx
      Remove nginx while normally retaining some configuration files.

  sudo apt purge nginx
      Remove nginx and its package-managed configuration files.

  sudo apt upgrade
      Upgrade installed packages without normally removing packages.

  sudo apt full-upgrade
      Perform a broader upgrade that may install/remove packages to satisfy
      dependency changes.

  apt list --installed
      List installed packages.

  apt policy nginx
      Show installed and candidate versions and repository priorities.

  sudo apt autoremove
      Remove packages that were installed as dependencies and are no longer
      required.

  sudo apt clean
      Remove downloaded package files from the local cache.

  sudo apt autoclean
      Remove cached package files that can no longer be downloaded.

Low-level Debian package tool:
  dpkg -l
  dpkg -s nginx
  dpkg -L nginx
  dpkg -S /usr/bin/example
  sudo dpkg -i package.deb

  dpkg installs individual .deb packages but does not provide the complete
  dependency-solving behavior of apt.

Red Hat Enterprise Linux / Fedora family with dnf:
  sudo dnf check-update
      Check whether updates are available.

  sudo dnf search nginx
      Search package metadata.

  dnf info nginx
      Display package information.

  sudo dnf install nginx
      Install a package and dependencies.

  sudo dnf remove nginx
      Remove a package.

  sudo dnf upgrade
      Upgrade installed packages.

  sudo dnf autoremove
      Remove no-longer-needed dependencies when appropriate.

  sudo dnf clean all
      Clear cached repository data.

  rpm -q nginx
  rpm -qi nginx
  rpm -ql nginx
  rpm -qf /usr/bin/example
  sudo rpm -Uvh package.rpm

  rpm is the lower-level package database/package tool; dnf provides
  repository-aware dependency management.

yum:
  sudo yum install nginx
  sudo yum update
  sudo yum remove nginx
  yum info nginx

  On modern systems, yum may be a compatibility interface backed by dnf.
  Exact behavior depends on the distribution and release.

Important operational rule:
  Read the transaction before confirming a real installation, upgrade,
  removal, or distribution upgrade. Package managers can change many
  packages in a single transaction.
"""
    )


# ---------------------------------------------------------------------------
# 10. Dependency graph demonstration
# ---------------------------------------------------------------------------

def print_dependency_graph(
    repositories: List[Repository],
    root: str,
) -> None:
    print(f"\n=== Dependency graph for {root} ===")

    resolver = DependencyResolver(repositories, InstalledDatabase())

    visited: Set[str] = set()

    def walk(name: str, indent: int) -> None:
        if name in visited:
            print(" " * indent + f"{name} (already visited)")
            return

        candidates = resolver.available_candidates(name)

        if not candidates:
            print(" " * indent + f"{name} (missing)")
            return

        package = candidates[0]
        visited.add(name)

        print(" " * indent + f"{package.name} {package.version}")

        for dependency in package.dependencies:
            constraint = (
                f" {dependency.constraint}"
                if dependency.constraint
                else ""
            )
            print(" " * (indent + 2) + f"requires {dependency.name}{constraint}")
            walk(dependency.name, indent + 4)

    walk(root, 0)


# ---------------------------------------------------------------------------
# 11. Package-manager comparison
# ---------------------------------------------------------------------------

def compare_managers() -> None:
    print(
        """
=== apt vs yum vs dnf ===

apt:
  Typical ecosystem: Debian and Ubuntu
  Primary package format: .deb
  Low-level package database/tool: dpkg
  Repository configuration commonly lives under /etc/apt/
  Common metadata operation: apt update

dnf:
  Typical ecosystem: Fedora, modern RHEL-family systems
  Primary package format: .rpm
  Low-level package database/tool: rpm
  Repository configuration commonly lives under /etc/yum.repos.d/
  Common metadata operation: dnf check-update or automatic metadata refresh

yum:
  Historical and compatibility-oriented interface in the RPM ecosystem
  Modern distributions may provide yum through dnf compatibility behavior.

The commands are not interchangeable simply because they solve similar
problems. Package names, repository layouts, dependency metadata, version
rules, configuration files, and transaction behavior can differ.
"""
    )


# ---------------------------------------------------------------------------
# 12. Edge cases and failure modes
# ---------------------------------------------------------------------------

def demonstrate_edge_cases() -> None:
    print(
        """
=== Important edge cases ===

1. Missing dependency
   A package cannot be safely installed when a required dependency has no
   compatible candidate in the enabled repositories.

2. Dependency conflict
   Package A may require library X >= 3 while package B requires X < 3.
   The resolver must determine whether a compatible transaction exists.

3. Circular dependency
   A requires B while B requires A. Package systems can represent complex
   relationships, but a resolver must detect cycles rather than recurse
   forever.

4. Held or excluded packages
   Administrators can sometimes prevent particular packages from changing.
   This can affect upgrade resolution.

5. Multiple repositories
   More than one repository can provide different versions of the same
   package. Repository priorities and policy determine the candidate.

6. Disabled repositories
   A package may appear to be unavailable even though it exists in a
   repository that is currently disabled.

7. Configuration-file handling
   Removing a package does not necessarily mean that every configuration
   file is deleted. Purge behavior is different from ordinary removal on
   Debian-based systems.

8. Partial transactions
   Power loss, filesystem errors, interrupted scripts, or other failures
   can leave package state requiring recovery.

9. Architecture
   A package for amd64 is not automatically interchangeable with an arm64
   package.

10. Downgrades
    Installing an older version can introduce compatibility or security
    problems and should be treated as an explicit administrative operation.

11. Kernel packages
    Linux distributions can retain older kernels so that a previous kernel
    remains available if a newer kernel has a problem.

12. Third-party repositories
    A repository can provide useful software but also changes the trust and
    maintenance boundary of the system. Repository provenance matters.
"""
    )


# ---------------------------------------------------------------------------
# 13. Security and production considerations
# ---------------------------------------------------------------------------

def print_security_guidance() -> None:
    print(
        """
=== Security and production considerations ===

Repository trust:
  Packages should come from repositories whose signing keys and provenance
  are trusted. HTTPS transport alone is not a substitute for package
  signature verification.

Least privilege:
  Package installation normally requires administrative privileges.
  Use sudo for the specific administrative command rather than operating an
  entire interactive session as root when that is unnecessary.

Patch management:
  Security updates should be applied through a controlled process suitable
  for the system's role and availability requirements.

Change control:
  Production upgrades should be tested and reviewed. Read the proposed
  transaction and identify package removals, replacements, service restarts,
  and configuration changes.

Reproducibility:
  Record distribution release, repository configuration, package versions,
  architecture, and relevant configuration state when reproducibility
  matters.

Supply-chain security:
  Repository compromise, malicious packages, signing-key compromise, and
  dependency confusion are relevant threats.

Operational recovery:
  Keep appropriate backups and recovery procedures before significant
  package changes. A package manager cannot substitute for system backups.

Containers:
  Containers still need package management during image construction.
  Keeping images minimal reduces unnecessary software and attack surface.

Automation:
  Automation should be idempotent, explicit about versions when required,
  and designed to handle noninteractive behavior correctly.
"""
    )


# ---------------------------------------------------------------------------
# 14. Safe practice lab
# ---------------------------------------------------------------------------

def run_lab() -> None:
    repositories = build_demo_repositories()
    manager = PackageManager(repositories)

    print("\n=== Safe package-management simulation ===")
    print("No real packages or system files will be modified.")

    manager.refresh_metadata()

    manager.search("ssl")
    manager.show("webserver")

    print_dependency_graph(repositories, "webserver")

    manager.install("webserver")
    manager.list_installed()

    print("\nInstalling a second package that shares dependencies:")
    manager.install("database-client")
    manager.list_installed()

    print("\nSimulating repository refresh with a newer security version:")
    manager.upgrade_all()
    manager.list_installed()

    print("\nAttempting to remove a dependency still in use:")
    manager.remove("libssl")

    print("\nRemoving the dependent application first:")
    manager.remove("database-client")
    manager.remove("webserver")

    print("\nRemoving a now-unused library:")
    manager.remove("libssl")

    manager.list_installed()


# ---------------------------------------------------------------------------
# 15. Package-file and command interpretation
# ---------------------------------------------------------------------------

def parse_command(command: str) -> None:
    """
    Explain a package-manager command without executing it.

    This is useful for understanding command structure:
        sudo apt install nginx
    """
    print(f"\n=== Command interpretation ===")
    print(f"Input: {command}")

    try:
        tokens = shlex.split(command)
    except ValueError as error:
        print(f"Invalid shell syntax: {error}")
        return

    if not tokens:
        print("No command supplied.")
        return

    for index, token in enumerate(tokens):
        print(f"  token[{index}] = {token!r}")

    if "apt" in tokens and "install" in tokens:
        print("Meaning: request installation through the APT frontend.")
    elif "dnf" in tokens and "install" in tokens:
        print("Meaning: request installation through DNF.")
    elif "yum" in tokens and "install" in tokens:
        print("Meaning: request installation through the YUM interface.")
    else:
        print("This program provides token-level analysis only.")


# ---------------------------------------------------------------------------
# 16. Common mistakes
# ---------------------------------------------------------------------------

def print_common_mistakes() -> None:
    print(
        """
=== Common mistakes ===

- Running apt install without first understanding the transaction.
- Confusing apt update with apt upgrade.
- Assuming apt update installs available upgrades.
- Treating dpkg -i as a complete replacement for apt.
- Mixing repositories intended for different distribution releases.
- Adding random third-party repositories without evaluating provenance.
- Removing a library without checking dependent packages.
- Assuming package names are identical across Debian and RPM ecosystems.
- Using old yum documentation as though all behavior is identical on modern
  dnf-based systems.
- Deleting package-manager databases or repository metadata manually.
- Ignoring held packages, exclusions, architecture, or repository priorities.
- Performing major distribution upgrades without backups and recovery plans.
- Assuming a successful package transaction means an application is healthy.
  Services can still fail due to configuration, ports, permissions, or data.
"""
    )


# ---------------------------------------------------------------------------
# 17. Performance considerations
# ---------------------------------------------------------------------------

def print_performance() -> None:
    print(
        """
=== Performance considerations ===

Repository metadata:
  Refreshing metadata requires network and local processing. Package managers
  cache metadata to avoid unnecessary repeated downloads.

Dependency resolution:
  Real dependency resolution can involve many packages and constraints.
  Repository metadata structures and solver strategies affect performance.

Download bandwidth:
  Large upgrades can consume substantial network bandwidth.

Disk usage:
  Package archives, metadata caches, installed files, logs, and multiple
  kernels can consume disk space.

Transaction size:
  Large transactions can be operationally riskier because they affect more
  components simultaneously.

Automation:
  In CI/CD environments, caching package metadata and downloaded packages
  can reduce build time, while stale caches must be handled carefully.
"""
    )


# ---------------------------------------------------------------------------
# 18. Main study flow
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Linux package management educational laboratory"
    )

    parser.add_argument(
        "--command",
        help="Explain a package-manager command without executing it.",
    )

    parser.add_argument(
        "--search",
        help="Search the simulated repositories.",
    )

    parser.add_argument(
        "--install",
        help="Install a package in the simulated environment.",
    )

    parser.add_argument(
        "--show",
        help="Show simulated package information.",
    )

    parser.add_argument(
        "--remove",
        help="Remove a package from the simulated environment.",
    )

    args = parser.parse_args()

    if args.command:
        parse_command(args.command)

    repositories = build_demo_repositories()
    manager = PackageManager(repositories)

    if args.search:
        manager.search(args.search)

    if args.show:
        manager.show(args.show)

    if args.install:
        manager.install(args.install)

    if args.remove:
        manager.remove(args.remove)

    if any(
        [
            args.command,
            args.search,
            args.show,
            args.install,
            args.remove,
        ]
    ):
        manager.list_installed()
        return

    print("=" * 72)
    print("LINUX PACKAGE MANAGEMENT STUDY LAB")
    print("=" * 72)

    show_terminology()
    demonstrate_versions()
    compare_managers()
    run_lab()
    demonstrate_edge_cases()
    print_security_guidance()
    print_performance()
    print_common_mistakes()
    print_real_commands()

    print(
        """
=== Key conceptual distinction ===

A package is software plus metadata and relationships.

A package database records installed state.

A repository supplies package metadata and artifacts.

A low-level package tool manages package-format operations.

A higher-level package manager combines repositories, dependency resolution,
transactions, and policy.

Examples:
  Debian/Ubuntu:     dpkg <- apt
  RPM ecosystem:     rpm  <- dnf/yum

The exact architecture and behavior varies by distribution release, so the
local system documentation and package-manager output should be treated as
the authoritative operational source for a real host.
"""
    )


if __name__ == "__main__":
    main()
