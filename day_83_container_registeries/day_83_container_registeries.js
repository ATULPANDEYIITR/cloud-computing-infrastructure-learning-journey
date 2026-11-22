"use strict";

/*
 * Container Registry Distribution and Policy Engine
 *
 * Node.js 18+
 * Standard library only.
 *
 * Demonstrates asynchronous image publishing, event-driven distribution,
 * access policies, immutable releases, digest verification, and lifecycle
 * controls.
 */

const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");

class RegistryError extends Error {
    constructor(message, code = "REGISTRY_ERROR") {
        super(message);
        this.name = "RegistryError";
        this.code = code;
    }
}

const Role = Object.freeze({
    READER: "reader",
    WRITER: "writer",
    ADMIN: "admin"
});

const State = Object.freeze({
    ACTIVE: "active",
    QUARANTINED: "quarantined",
    DELETED: "deleted"
});

const Action = Object.freeze({
    PUSH: "push",
    PULL: "pull",
    DELETE: "delete"
});

function sha256(value) {
    return "sha256:" +
        crypto.createHash("sha256").update(value).digest("hex");
}

function validateRepository(name) {
    if (
        typeof name !== "string" ||
        !/^[a-z0-9]+(?:[._/-][a-z0-9]+)*$/.test(name)
    ) {
        throw new RegistryError(
            "Invalid repository name.",
            "INVALID_REPOSITORY"
        );
    }
}

function validateTag(tag) {
    if (
        typeof tag !== "string" ||
        !/^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$/.test(tag)
    ) {
        throw new RegistryError("Invalid image tag.", "INVALID_TAG");
    }
}

function canonicalManifest(input) {
    if (
        !input ||
        !Array.isArray(input.layers) ||
        input.layers.length === 0 ||
        !input.configDigest ||
        !/^sha256:[a-f0-9]{64}$/.test(input.configDigest)
    ) {
        throw new RegistryError(
            "Manifest must contain valid layers and config digest.",
            "INVALID_MANIFEST"
        );
    }

    const normalized = {
        schemaVersion: 2,
        mediaType: "application/vnd.oci.image.manifest.v1+json",
        configDigest: input.configDigest,
        layers: [...input.layers].sort(),
        architecture: input.architecture || "amd64",
        operatingSystem: input.operatingSystem || "linux"
    };

    if (!["amd64", "arm64", "arm", "386"].includes(
        normalized.architecture
    )) {
        throw new RegistryError(
            "Unsupported architecture.",
            "INVALID_ARCHITECTURE"
        );
    }

    return normalized;
}

class RegistryPolicy {
    constructor({
        privateRepository = true,
        immutableTags = false,
        allowedArchitectures = ["amd64", "arm64"],
        requireVerifiedImage = true
    } = {}) {
        this.privateRepository = privateRepository;
        this.immutableTags = immutableTags;
        this.allowedArchitectures = new Set(allowedArchitectures);
        this.requireVerifiedImage = requireVerifiedImage;
    }

    evaluate(action, user, repository, image = null) {
        const role = user.permissions.get(repository.name);

        if (
            this.privateRepository &&
            !role
        ) {
            throw new RegistryError(
                "Private repository access denied.",
                "ACCESS_DENIED"
            );
        }

        const permissions = {
            [Action.PULL]: [Role.READER, Role.WRITER, Role.ADMIN],
            [Action.PUSH]: [Role.WRITER, Role.ADMIN],
            [Action.DELETE]: [Role.ADMIN]
        };

        if (
            !permissions[action] ||
            !permissions[action].includes(role)
        ) {
            throw new RegistryError(
                `Role ${role || "none"} cannot perform ${action}.`,
                "POLICY_DENIED"
            );
        }

        if (
            action === Action.PUSH &&
            image &&
            !this.allowedArchitectures.has(image.architecture)
        ) {
            throw new RegistryError(
                "Image architecture violates registry policy.",
                "ARCHITECTURE_POLICY"
            );
        }

        if (
            action === Action.PUSH &&
            image &&
            this.requireVerifiedImage &&
            !image.verified
        ) {
            throw new RegistryError(
                "Image verification is required.",
                "VERIFICATION_REQUIRED"
            );
        }
    }
}

class RegistryRepository {
    constructor(name, policy) {
        validateRepository(name);

        this.name = name;
        this.policy = policy;
        this.tags = new Map();
        this.manifests = new Map();
        this.pullMetrics = new Map();
        this.createdAt = new Date();
    }

    resolve(reference) {
        const digest = reference.startsWith("sha256:")
            ? reference
            : this.tags.get(reference);

        if (!digest) {
            throw new RegistryError(
                "Image reference does not exist.",
                "IMAGE_NOT_FOUND"
            );
        }

        const image = this.manifests.get(digest);

        if (!image || image.state !== State.ACTIVE) {
            throw new RegistryError(
                "Image is unavailable.",
                "IMAGE_UNAVAILABLE"
            );
        }

        return image;
    }
}

class ContainerRegistry extends EventEmitter {
    constructor(name) {
        super();

        if (!name || !name.trim()) {
            throw new RegistryError("Registry name is required.");
        }

        this.name = name;
        this.repositories = new Map();
        this.users = new Map();
        this.audit = [];
        this.serial = Promise.resolve();
    }

    addUser(username, token) {
        if (!username || !token || token.length < 12) {
            throw new RegistryError(
                "Invalid user credentials.",
                "INVALID_USER"
            );
        }

        if (this.users.has(username)) {
            throw new RegistryError(
                "User already exists.",
                "USER_EXISTS"
            );
        }

        this.users.set(username, {
            username,
            tokenHash: sha256(token),
            permissions: new Map(),
            active: true
        });
    }

    authenticate(username, token) {
        const user = this.users.get(username);

        if (
            !user ||
            !user.active ||
            user.tokenHash !== sha256(token)
        ) {
            throw new RegistryError(
                "Authentication failed.",
                "AUTHENTICATION_FAILED"
            );
        }

        return user;
    }

    createRepository(name, options = {}) {
        validateRepository(name);

        if (this.repositories.has(name)) {
            throw new RegistryError(
                "Repository already exists.",
                "REPOSITORY_EXISTS"
            );
        }

        const policy = new RegistryPolicy(options);
        const repository = new RegistryRepository(name, policy);

        this.repositories.set(name, repository);
        return repository;
    }

    grant(adminUsername, adminToken, username, repositoryName, role) {
        const admin = this.authenticate(adminUsername, adminToken);
        const target = this.users.get(username);
        const repository = this.repositories.get(repositoryName);

        if (
            !target ||
            !repository ||
            !Object.values(Role).includes(role)
        ) {
            throw new RegistryError(
                "Invalid permission assignment.",
                "INVALID_GRANT"
            );
        }

        const adminRole = admin.permissions.get(repositoryName);

        if (adminRole !== Role.ADMIN) {
            throw new RegistryError(
                "Administrative permission required.",
                "ADMIN_REQUIRED"
            );
        }

        target.permissions.set(repositoryName, role);
    }

    record(event) {
        this.audit.push({
            timestamp: new Date().toISOString(),
            ...event
        });

        this.emit("audit", event);
    }

    /*
     * Serialize writes to avoid two concurrent pushes assigning the same
     * mutable tag in an unpredictable order.
     */
    async serializeWrite(task) {
        const result = this.serial.then(task);
        this.serial = result.catch(() => undefined);
        return result;
    }

    async push(username, token, repositoryName, tag, manifestInput, options = {}) {
        return this.serializeWrite(async () => {
            const user = this.authenticate(username, token);
            const repository = this.repositories.get(repositoryName);

            if (!repository) {
                throw new RegistryError(
                    "Repository not found.",
                    "REPOSITORY_NOT_FOUND"
                );
            }

            validateTag(tag);

            const manifest = canonicalManifest(manifestInput);
            const image = {
                manifest,
                digest: sha256(JSON.stringify(manifest)),
                architecture: manifest.architecture,
                verified: options.verified === true,
                state: State.ACTIVE,
                pushedAt: new Date(),
                pullCount: 0
            };

            repository.policy.evaluate(
                Action.PUSH,
                user,
                repository,
                image
            );

            const existingDigest = repository.tags.get(tag);

            if (
                repository.policy.immutableTags &&
                existingDigest &&
                existingDigest !== image.digest
            ) {
                throw new RegistryError(
                    "Tag cannot be reassigned.",
                    "IMMUTABLE_TAG"
                );
            }

            // Digest-addressed storage deduplicates identical content.
            if (!repository.manifests.has(image.digest)) {
                repository.manifests.set(image.digest, image);
            }

            repository.tags.set(tag, image.digest);

            this.record({
                operation: Action.PUSH,
                repository: repositoryName,
                tag,
                digest: image.digest,
                actor: username,
                outcome: "success"
            });

            this.emit("image:pushed", {
                repository: repositoryName,
                tag,
                digest: image.digest
            });

            return image.digest;
        });
    }

    async pull(username, token, repositoryName, reference) {
        const user = this.authenticate(username, token);
        const repository = this.repositories.get(repositoryName);

        if (!repository) {
            throw new RegistryError(
                "Repository not found.",
                "REPOSITORY_NOT_FOUND"
            );
        }

        repository.policy.evaluate(Action.PULL, user, repository);

        const image = repository.resolve(reference);

        image.pullCount += 1;
        repository.pullMetrics.set(
            image.digest,
            (repository.pullMetrics.get(image.digest) || 0) + 1
        );

        this.record({
            operation: Action.PULL,
            repository: repositoryName,
            reference,
            digest: image.digest,
            actor: username,
            outcome: "success"
        });

        return {
            digest: image.digest,
            architecture: image.architecture,
            manifest: image.manifest,
            pullCount: image.pullCount
        };
    }

    async deleteTag(username, token, repositoryName, tag) {
        return this.serializeWrite(async () => {
            const user = this.authenticate(username, token);
            const repository = this.repositories.get(repositoryName);

            if (!repository) {
                throw new RegistryError(
                    "Repository not found.",
                    "REPOSITORY_NOT_FOUND"
                );
            }

            repository.policy.evaluate(
                Action.DELETE,
                user,
                repository
            );

            if (!repository.tags.delete(tag)) {
                throw new RegistryError(
                    "Tag not found.",
                    "TAG_NOT_FOUND"
                );
            }

            this.record({
                operation: Action.DELETE,
                repository: repositoryName,
                tag,
                actor: username,
                outcome: "success"
            });
        });
    }

    garbageCollect(username, token, repositoryName) {
        const user = this.authenticate(username, token);
        const repository = this.repositories.get(repositoryName);

        if (!repository) {
            throw new RegistryError("Repository not found.");
        }

        repository.policy.evaluate(
            Action.DELETE,
            user,
            repository
        );

        const referenced = new Set(repository.tags.values());
        let removed = 0;

        for (const digest of repository.manifests.keys()) {
            if (!referenced.has(digest)) {
                repository.manifests.delete(digest);
                removed++;
            }
        }

        this.record({
            operation: "garbage_collect",
            repository: repositoryName,
            actor: username,
            removed,
            outcome: "success"
        });

        return removed;
    }

    report(repositoryName) {
        const repository = this.repositories.get(repositoryName);

        if (!repository) {
            throw new RegistryError("Repository not found.");
        }

        const images = [...repository.manifests.values()];

        return {
            registry: this.name,
            repository: repositoryName,
            tags: Object.fromEntries(repository.tags),
            manifestCount: images.length,
            totalPulls: images.reduce(
                (total, image) => total + image.pullCount,
                0
            ),
            architectures: [
                ...new Set(images.map(image => image.architecture))
            ].sort()
        };
    }
}

async function main() {
    const registry = new ContainerRegistry("enterprise-registry");

    registry.on("image:pushed", event => {
        console.log(
            `[EVENT] Published ${event.repository}:${event.tag}`
        );
    });

    registry.on("audit", event => {
        if (event.outcome === "success") {
            console.log(
                `[AUDIT] ${event.actor}: ${event.operation}`
            );
        }
    });

    registry.addUser("admin", "admin-access-token-2026");
    registry.addUser("builder", "builder-access-token-2026");
    registry.addUser("runtime", "runtime-access-token-2026");

    const repository = registry.createRepository(
        "payments/service",
        {
            privateRepository: true,
            immutableTags: false,
            allowedArchitectures: ["amd64", "arm64"],
            requireVerifiedImage: true
        }
    );

    registry.users.get("admin").permissions.set(
        repository.name,
        Role.ADMIN
    );

    registry.grant(
        "admin",
        "admin-access-token-2026",
        "builder",
        repository.name,
        Role.WRITER
    );

    registry.grant(
        "admin",
        "admin-access-token-2026",
        "runtime",
        repository.name,
        Role.READER
    );

    const configDigest = sha256("payments-config-v1");

    const manifest = {
        configDigest,
        layers: [
            sha256("application-layer"),
            sha256("runtime-layer")
        ],
        architecture: "amd64",
        operatingSystem: "linux"
    };

    const digest = await registry.push(
        "builder",
        "builder-access-token-2026",
        repository.name,
        "1.0.0",
        manifest,
        { verified: true }
    );

    await registry.push(
        "builder",
        "builder-access-token-2026",
        repository.name,
        "latest",
        manifest,
        { verified: true }
    );

    const deployment = await registry.pull(
        "runtime",
        "runtime-access-token-2026",
        repository.name,
        "latest"
    );

    console.log("Deployment digest:", deployment.digest);
    console.log("Digest verification:", digest === deployment.digest);

    // A tag is a mutable reference. The original digest remains stable.
    const secondManifest = {
        configDigest: sha256("payments-config-v2"),
        layers: [sha256("application-layer-v2")],
        architecture: "arm64",
        operatingSystem: "linux"
    };

    await registry.push(
        "builder",
        "builder-access-token-2026",
        repository.name,
        "2.0.0",
        secondManifest,
        { verified: true }
    );

    console.log(
        "Repository report:",
        JSON.stringify(registry.report(repository.name), null, 2)
    );

    try {
        await registry.push(
            "builder",
            "builder-access-token-2026",
            repository.name,
            "3.0.0",
            secondManifest,
            { verified: false }
        );
    } catch (error) {
        console.log("Expected policy rejection:", error.code);
    }

    await registry.deleteTag(
        "admin",
        "admin-access-token-2026",
        repository.name,
        "2.0.0"
    );

    console.log(
        "Garbage-collected manifests:",
        registry.garbageCollect(
            "admin",
            "admin-access-token-2026",
            repository.name
        )
    );
}

main().catch(error => {
    console.error("Registry operation failed:", error.message);
    process.exitCode = 1;
});
