#!/usr/bin/env node
"use strict";

/*
 * Linux Package Management: apt, yum, and dnf
 *
 * This executable JavaScript study file complements the Python laboratory.
 * It focuses on:
 *   - package metadata modeling
 *   - dependency graphs
 *   - semantic package operations
 *   - transaction planning
 *   - asynchronous repository simulation
 *   - validation and error handling
 *   - immutable-style state updates
 *   - command interpretation
 *
 * No real operating-system package commands are executed.
 */

const readline = require("readline");

// ---------------------------------------------------------------------------
// Package and dependency models
// ---------------------------------------------------------------------------

class Dependency {
    constructor(name, constraint = null) {
        this.name = name;
        this.constraint = constraint;
    }

    isSatisfiedBy(pkg) {
        if (!pkg || pkg.name !== this.name) {
            return false;
        }

        if (!this.constraint) {
            return true;
        }

        const match = this.constraint.match(/^(>=|<=|=|>|<)\s*(.+)$/);

        if (!match) {
            throw new Error(`Unsupported constraint: ${this.constraint}`);
        }

        const [, operator, requiredVersion] = match;
        const comparison = compareVersions(pkg.version, requiredVersion);

        switch (operator) {
            case ">":
                return comparison > 0;
            case ">=":
                return comparison >= 0;
            case "<":
                return comparison < 0;
            case "<=":
                return comparison <= 0;
            case "=":
                return comparison === 0;
            default:
                return false;
        }
    }
}


class Package {
    constructor({
        name,
        version,
        architecture = "amd64",
        dependencies = [],
        repository = "main",
        description = "",
        sizeMB = 1
    }) {
        this.name = name;
        this.version = version;
        this.architecture = architecture;
        this.dependencies = dependencies;
        this.repository = repository;
        this.description = description;
        this.sizeMB = sizeMB;
    }

    get identifier() {
        return `${this.name}=${this.version}:${this.architecture}`;
    }
}


// ---------------------------------------------------------------------------
// Version comparison
// ---------------------------------------------------------------------------

function tokenizeVersion(version) {
    return version.match(/\d+|[A-Za-z]+/g) || [];
}

function compareVersions(left, right) {
    /*
     * This is a simplified educational comparison.
     *
     * Debian and RPM have their own detailed version semantics. A production
     * application should not substitute this function for dpkg/rpm version
     * comparison rules.
     */
    const a = tokenizeVersion(left);
    const b = tokenizeVersion(right);

    const length = Math.max(a.length, b.length);

    for (let index = 0; index < length; index += 1) {
        if (index >= a.length) return -1;
        if (index >= b.length) return 1;

        const leftPart = a[index];
        const rightPart = b[index];

        const leftNumber = /^\d+$/.test(leftPart);
        const rightNumber = /^\d+$/.test(rightPart);

        if (leftNumber && rightNumber) {
            const x = Number(leftPart);
            const y = Number(rightPart);

            if (x !== y) {
                return x < y ? -1 : 1;
            }
        } else {
            const x = leftPart.toLowerCase();
            const y = rightPart.toLowerCase();

            if (x !== y) {
                return x < y ? -1 : 1;
            }
        }
    }

    return 0;
}


// ---------------------------------------------------------------------------
// Repository
// ---------------------------------------------------------------------------

class Repository {
    constructor(name, url, enabled = true, trusted = true) {
        this.name = name;
        this.url = url;
        this.enabled = enabled;
        this.trusted = trusted;
        this.packages = new Map();
    }

    addPackage(pkg) {
        if (!this.packages.has(pkg.name)) {
            this.packages.set(pkg.name, []);
        }

        this.packages.get(pkg.name).push(pkg);
    }

    findCandidates(name) {
        if (!this.enabled || !this.trusted) {
            return [];
        }

        return this.packages.get(name) || [];
    }

    search(term) {
        const normalized = term.toLowerCase();
        const results = [];

        for (const versions of this.packages.values()) {
            for (const pkg of versions) {
                if (
                    pkg.name.toLowerCase().includes(normalized) ||
                    pkg.description.toLowerCase().includes(normalized)
                ) {
                    results.push(pkg);
                }
            }
        }

        return results;
    }
}


// ---------------------------------------------------------------------------
// Asynchronous repository client
// ---------------------------------------------------------------------------

class RepositoryClient {
    constructor(repository) {
        this.repository = repository;
    }

    async refreshMetadata() {
        /*
         * Real package managers download and process repository metadata.
         * The timeout represents network/disk work without contacting a real
         * package repository.
         */
        await new Promise(resolve => setTimeout(resolve, 50));

        return {
            repository: this.repository.name,
            packages: [...this.repository.packages.values()]
                .reduce((total, versions) => total + versions.length, 0),
            refreshed: true
        };
    }

    async search(term) {
        await new Promise(resolve => setTimeout(resolve, 20));
        return this.repository.search(term);
    }
}


// ---------------------------------------------------------------------------
// Package database
// ---------------------------------------------------------------------------

class PackageDatabase {
    constructor() {
        this.installed = new Map();
    }

    get(name) {
        return this.installed.get(name) || null;
    }

    has(name) {
        return this.installed.has(name);
    }

    install(pkg) {
        this.installed.set(pkg.name, pkg);
    }

    remove(name) {
        if (!this.installed.has(name)) {
            throw new Error(`Package is not installed: ${name}`);
        }

        const pkg = this.installed.get(name);
        this.installed.delete(name);
        return pkg;
    }

    list() {
        return [...this.installed.values()]
            .sort((a, b) => a.name.localeCompare(b.name));
    }
}


// ---------------------------------------------------------------------------
// Dependency resolver
// ---------------------------------------------------------------------------

class DependencyResolver {
    constructor(repositories, database) {
        this.repositories = repositories;
        this.database = database;
    }

    candidates(name) {
        const result = [];

        for (const repository of this.repositories) {
            result.push(...repository.findCandidates(name));
        }

        return result.sort((a, b) =>
            compareVersions(b.version, a.version)
        );
    }

    resolve(rootName) {
        const selected = new Map();
        const visiting = new Set();

        const visit = dependency => {
            if (visiting.has(dependency.name)) {
                throw new Error(
                    `Circular dependency detected involving ${dependency.name}`
                );
            }

            if (selected.has(dependency.name)) {
                const selectedPackage = selected.get(dependency.name);

                if (!dependency.isSatisfiedBy(selectedPackage)) {
                    throw new Error(
                        `Conflicting requirements for ${dependency.name}`
                    );
                }

                return;
            }

            const installed = this.database.get(dependency.name);

            if (installed && dependency.isSatisfiedBy(installed)) {
                selected.set(dependency.name, installed);
                return;
            }

            const candidate = this.candidates(dependency.name)
                .find(pkg => dependency.isSatisfiedBy(pkg));

            if (!candidate) {
                throw new Error(
                    `No compatible candidate for ${dependency.name}`
                );
            }

            visiting.add(candidate.name);
            selected.set(candidate.name, candidate);

            for (const child of candidate.dependencies) {
                visit(child);
            }

            visiting.delete(candidate.name);
        };

        visit(new Dependency(rootName));

        return [...selected.values()];
    }
}


// ---------------------------------------------------------------------------
// Transaction planner
// ---------------------------------------------------------------------------

class TransactionPlanner {
    constructor(database) {
        this.database = database;
    }

    plan(packages) {
        const operations = [];

        for (const pkg of packages) {
            const installed = this.database.get(pkg.name);

            if (!installed) {
                operations.push({
                    type: "install",
                    package: pkg
                });
                continue;
            }

            if (compareVersions(pkg.version, installed.version) > 0) {
                operations.push({
                    type: "upgrade",
                    from: installed,
                    package: pkg
                });
            }
        }

        return operations;
    }
}


// ---------------------------------------------------------------------------
// Package manager
// ---------------------------------------------------------------------------

class SimulatedPackageManager {
    constructor(repositories) {
        this.repositories = repositories;
        this.database = new PackageDatabase();
        this.resolver = new DependencyResolver(
            repositories,
            this.database
        );
        this.planner = new TransactionPlanner(this.database);
    }

    async update() {
        console.log("\nRefreshing repository metadata...");

        const clients = this.repositories
            .filter(repository => repository.enabled)
            .map(repository => new RepositoryClient(repository));

        const metadata = await Promise.all(
            clients.map(client => client.refreshMetadata())
        );

        for (const item of metadata) {
            console.log(
                `  ${item.repository}: ${item.packages} packages`
            );
        }
    }

    async search(term) {
        const clients = this.repositories
            .filter(repository => repository.enabled)
            .map(repository => new RepositoryClient(repository));

        const resultSets = await Promise.all(
            clients.map(client => client.search(term))
        );

        const unique = new Map();

        for (const results of resultSets) {
            for (const pkg of results) {
                unique.set(pkg.identifier, pkg);
            }
        }

        console.log(`\nSearch: ${term}`);

        for (const pkg of unique.values()) {
            console.log(`  ${pkg.identifier} - ${pkg.description}`);
        }

        if (unique.size === 0) {
            console.log("  No packages found.");
        }
    }

    install(name) {
        console.log(`\nPlanning installation of ${name}...`);

        try {
            const resolved = this.resolver.resolve(name);
            const operations = this.planner.plan(resolved);

            if (operations.length === 0) {
                console.log("Nothing to do.");
                return;
            }

            console.log("\nTransaction:");

            for (const operation of operations) {
                if (operation.type === "install") {
                    console.log(
                        `  install ${operation.package.identifier}`
                    );
                } else {
                    console.log(
                        `  upgrade ${operation.from.identifier} -> ` +
                        `${operation.package.identifier}`
                    );
                }
            }

            for (const operation of operations) {
                this.database.install(operation.package);
            }

            console.log("Transaction completed.");
        } catch (error) {
            console.error(`Transaction failed: ${error.message}`);
        }
    }

    remove(name) {
        const installed = this.database.get(name);

        if (!installed) {
            console.log(`\n${name} is not installed.`);
            return;
        }

        const dependents = this.database.list()
            .filter(pkg =>
                pkg.name !== name &&
                pkg.dependencies.some(dep => dep.name === name)
            );

        if (dependents.length > 0) {
            console.log(
                `\nCannot remove ${name}; required by ` +
                dependents.map(pkg => pkg.name).join(", ")
            );
            return;
        }

        this.database.remove(name);
        console.log(`\nRemoved ${installed.identifier}`);
    }

    listInstalled() {
        console.log("\nInstalled packages:");

        const packages = this.database.list();

        if (packages.length === 0) {
            console.log("  none");
            return;
        }

        for (const pkg of packages) {
            console.log(`  ${pkg.identifier}`);
        }
    }
}


// ---------------------------------------------------------------------------
// Repository data
// ---------------------------------------------------------------------------

function createRepositories() {
    const main = new Repository(
        "ubuntu-main",
        "https://archive.ubuntu.com/ubuntu"
    );

    const security = new Repository(
        "ubuntu-security",
        "https://security.ubuntu.com/ubuntu"
    );

    main.addPackage(new Package({
        name: "libc",
        version: "2.38",
        description: "Core C library",
        sizeMB: 8
    }));

    main.addPackage(new Package({
        name: "libssl",
        version: "3.0.13",
        dependencies: [
            new Dependency("libc", ">=2.38")
        ],
        description: "TLS and cryptographic library",
        sizeMB: 4
    }));

    main.addPackage(new Package({
        name: "runtime",
        version: "3.11.8",
        dependencies: [
            new Dependency("libc", ">=2.38")
        ],
        description: "Language runtime",
        sizeMB: 25
    }));

    main.addPackage(new Package({
        name: "webserver",
        version: "1.4.0",
        dependencies: [
            new Dependency("libc", ">=2.38"),
            new Dependency("libssl", ">=3.0")
        ],
        description: "HTTP server",
        sizeMB: 12
    }));

    security.addPackage(new Package({
        name: "libssl",
        version: "3.0.14",
        dependencies: [
            new Dependency("libc", ">=2.38")
        ],
        repository: "ubuntu-security",
        description: "TLS security update",
        sizeMB: 4.2
    }));

    return [main, security];
}


// ---------------------------------------------------------------------------
// Dependency graph
// ---------------------------------------------------------------------------

function printDependencyGraph(repositories, root) {
    console.log(`\nDependency graph: ${root}`);

    const resolver = new DependencyResolver(
        repositories,
        new PackageDatabase()
    );

    const visited = new Set();

    function walk(name, indentation) {
        if (visited.has(name)) {
            console.log(`${indentation}${name} (visited)`);
            return;
        }

        const candidates = resolver.candidates(name);

        if (candidates.length === 0) {
            console.log(`${indentation}${name} (missing)`);
            return;
        }

        const pkg = candidates[0];
        visited.add(name);

        console.log(
            `${indentation}${pkg.name} ${pkg.version}`
        );

        for (const dependency of pkg.dependencies) {
            const requirement = dependency.constraint
                ? ` ${dependency.constraint}`
                : "";

            console.log(
                `${indentation}  requires ${dependency.name}${requirement}`
            );

            walk(
                dependency.name,
                `${indentation}    `
            );
        }
    }

    walk(root, "");
}


// ---------------------------------------------------------------------------
// Real command reference
// ---------------------------------------------------------------------------

function printCommandReference() {
    console.log(`
Real commands, shown for study only:

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

Low-level Debian package operations:
  dpkg -l
  dpkg -s nginx
  dpkg -L nginx
  dpkg -S /usr/bin/example
  sudo dpkg -i package.deb

RPM-family systems:
  sudo dnf check-update
  sudo dnf search nginx
  dnf info nginx
  sudo dnf install nginx
  sudo dnf remove nginx
  sudo dnf upgrade
  sudo dnf autoremove
  sudo dnf clean all

Low-level RPM operations:
  rpm -q nginx
  rpm -qi nginx
  rpm -ql nginx
  rpm -qf /usr/bin/example
  sudo rpm -Uvh package.rpm

YUM:
  sudo yum install nginx
  sudo yum update
  sudo yum remove nginx

Important distinction:
  apt update refreshes package metadata.
  apt upgrade changes installed packages.
  dnf similarly separates metadata/update concepts from the actual
  transaction.

Modern yum implementations may be compatibility interfaces backed by dnf.
`);
}


// ---------------------------------------------------------------------------
// Command parser
// ---------------------------------------------------------------------------

function explainCommand(command) {
    const tokens = command.trim().split(/\s+/).filter(Boolean);

    console.log("\nCommand analysis:");
    console.log(`  Original: ${command}`);

    tokens.forEach((token, index) => {
        console.log(`  token[${index}]: ${token}`);
    });

    if (tokens.includes("apt") && tokens.includes("install")) {
        console.log("  Operation: APT installation request.");
    } else if (
        tokens.includes("dnf") &&
        tokens.includes("install")
    ) {
        console.log("  Operation: DNF installation request.");
    } else if (
        tokens.includes("yum") &&
        tokens.includes("install")
    ) {
        console.log("  Operation: YUM installation request.");
    } else {
        console.log("  Operation: not classified by this teaching parser.");
    }
}


// ---------------------------------------------------------------------------
// Interactive demonstration
// ---------------------------------------------------------------------------

async function main() {
    console.log("=".repeat(72));
    console.log("LINUX PACKAGE MANAGEMENT: JAVASCRIPT STUDY LAB");
    console.log("=".repeat(72));

    const repositories = createRepositories();
    const manager = new SimulatedPackageManager(repositories);

    await manager.update();
    await manager.search("ssl");

    printDependencyGraph(repositories, "webserver");

    manager.install("webserver");
    manager.listInstalled();

    manager.install("runtime");
    manager.listInstalled();

    manager.remove("libssl");

    manager.remove("runtime");
    manager.remove("webserver");
    manager.remove("libssl");

    manager.listInstalled();

    printCommandReference();

    explainCommand("sudo apt install nginx");

    console.log(`
JavaScript-specific implementation points:

- Promise.all models parallel repository metadata requests.
- Classes represent packages, repositories, databases, resolvers, and
  transactions.
- Map provides explicit key/value package storage.
- Set is used to detect circular dependency traversal.
- Exceptions provide transaction failure paths.
- Array methods such as filter, map, find, and sort support data processing.

No command in this file invokes sudo, apt, yum, dnf, rpm, or dpkg.
`);
}


// ---------------------------------------------------------------------------
// Optional interactive mode
// ---------------------------------------------------------------------------

async function interactiveMode() {
    const manager = new SimulatedPackageManager(createRepositories());

    const interfaceInstance = readline.createInterface({
        input: process.stdin,
        output: process.stdout
    });

    console.log(`
Interactive simulated package manager.
Commands:
  update
  search <term>
  install <package>
  remove <package>
  list
  exit
`);

    const prompt = () => {
        interfaceInstance.question("pkg-lab> ", async input => {
            const parts = input.trim().split(/\s+/);
            const command = parts[0];

            try {
                switch (command) {
                    case "update":
                        await manager.update();
                        break;

                    case "search":
                        if (!parts[1]) {
                            console.log("Usage: search <term>");
                        } else {
                            await manager.search(parts.slice(1).join(" "));
                        }
                        break;

                    case "install":
                        if (!parts[1]) {
                            console.log("Usage: install <package>");
                        } else {
                            manager.install(parts[1]);
                        }
                        break;

                    case "remove":
                        if (!parts[1]) {
                            console.log("Usage: remove <package>");
                        } else {
                            manager.remove(parts[1]);
                        }
                        break;

                    case "list":
                        manager.listInstalled();
                        break;

                    case "exit":
                        interfaceInstance.close();
                        return;

                    default:
                        console.log("Unknown command.");
                }
            } catch (error) {
                console.error(`Error: ${error.message}`);
            }

            prompt();
        });
    };

    prompt();
}


// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

const args = process.argv.slice(2);

if (args.includes("--interactive")) {
    interactiveMode().catch(error => {
        console.error(error);
        process.exitCode = 1;
    });
} else {
    main().catch(error => {
        console.error(error);
        process.exitCode = 1;
    });
}
