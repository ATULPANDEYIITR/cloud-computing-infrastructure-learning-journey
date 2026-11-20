"use strict";

/**
 * Docker Storage and Volumes
 *
 * Event-driven storage lifecycle and policy engine.
 * Runtime: Node.js 18+
 * Dependencies: None.
 */

const fs = require("node:fs/promises");
const path = require("node:path");
const crypto = require("node:crypto");
const EventEmitter = require("node:events");

const MountType = Object.freeze({
    VOLUME: "volume",
    BIND: "bind",
    TMPFS: "tmpfs"
});

const VolumeState = Object.freeze({
    AVAILABLE: "available",
    IN_USE: "in_use"
});

class StorageError extends Error {}
class ValidationError extends StorageError {}
class NotFoundError extends StorageError {}
class ConflictError extends StorageError {}

function validateName(name) {
    if (
        typeof name !== "string" ||
        !/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$/.test(name)
    ) {
        throw new ValidationError(`Invalid volume name: ${name}`);
    }
}

function validateMount(mount) {
    if (!Object.values(MountType).includes(mount.type)) {
        throw new ValidationError("Unsupported mount type");
    }

    if (
        typeof mount.destination !== "string" ||
        !mount.destination.startsWith("/") ||
        mount.destination.split("/").includes("..")
    ) {
        throw new ValidationError("Invalid container destination");
    }

    if (typeof mount.readOnly !== "boolean") {
        throw new ValidationError("readOnly must be boolean");
    }

    if (mount.type === MountType.VOLUME) {
        validateName(mount.source);
    }

    if (
        mount.type === MountType.BIND &&
        (
            typeof mount.source !== "string" ||
            !path.isAbsolute(mount.source)
        )
    ) {
        throw new ValidationError("Bind source must be absolute");
    }

    if (
        mount.type === MountType.TMPFS &&
        mount.source !== "tmpfs"
    ) {
        throw new ValidationError("Invalid tmpfs source");
    }
}

class StorageManager extends EventEmitter {
    #volumes = new Map();
    #containers = new Map();
    #operationQueue = Promise.resolve();

    constructor() {
        super();
        this.setMaxListeners(100);
    }

    // Serializes mutations within this process.
    #serialize(operation) {
        const result = this.#operationQueue.then(operation);

        this.#operationQueue = result.catch(() => {});
        return result;
    }

    async createVolume(name, options = {}) {
        return this.#serialize(async () => {
            validateName(name);

            if (this.#volumes.has(name)) {
                throw new ConflictError(`Volume exists: ${name}`);
            }

            const volume = {
                id: crypto.randomUUID(),
                name,
                driver: options.driver || "local",
                labels: { ...(options.labels || {}) },
                state: VolumeState.AVAILABLE,
                containers: new Set(),
                data: new Map(),
                createdAt: new Date().toISOString()
            };

            this.#volumes.set(name, volume);

            this.emit("volume.created", {
                name,
                driver: volume.driver
            });

            return this.inspectVolume(name);
        });
    }

    #getVolume(name) {
        const volume = this.#volumes.get(name);

        if (!volume) {
            throw new NotFoundError(`Volume not found: ${name}`);
        }

        return volume;
    }

    async attachContainer(containerId, mounts) {
        return this.#serialize(async () => {
            if (
                typeof containerId !== "string" ||
                !/^[a-zA-Z0-9_-]{1,64}$/.test(containerId)
            ) {
                throw new ValidationError("Invalid container identifier");
            }

            if (this.#containers.has(containerId)) {
                throw new ConflictError("Container already registered");
            }

            if (!Array.isArray(mounts) || mounts.length === 0) {
                throw new ValidationError("At least one mount is required");
            }

            const destinations = new Set();
            const referenced = new Set();

            // Complete validation before changing shared state.
            for (const mount of mounts) {
                validateMount(mount);

                if (destinations.has(mount.destination)) {
                    throw new ConflictError("Duplicate mount destination");
                }

                destinations.add(mount.destination);

                if (mount.type === MountType.VOLUME) {
                    this.#getVolume(mount.source);
                    referenced.add(mount.source);
                }

                if (mount.type === MountType.BIND) {
                    const stat = await fs.stat(mount.source);

                    if (!stat.isDirectory() && !stat.isFile()) {
                        throw new ValidationError("Invalid bind source");
                    }
                }
            }

            const record = {
                id: containerId,
                mounts: mounts.map(m => ({ ...m })),
                running: false
            };

            for (const name of referenced) {
                const volume = this.#getVolume(name);
                volume.containers.add(containerId);
                volume.state = VolumeState.IN_USE;
            }

            this.#containers.set(containerId, record);

            this.emit("container.attached", {
                containerId,
                volumes: [...referenced]
            });

            return record;
        });
    }

    async detachContainer(containerId) {
        return this.#serialize(async () => {
            const container = this.#containers.get(containerId);

            if (!container) {
                throw new NotFoundError("Container not registered");
            }

            const referenced = new Set(
                container.mounts
                    .filter(m => m.type === MountType.VOLUME)
                    .map(m => m.source)
            );

            for (const name of referenced) {
                const volume = this.#getVolume(name);
                volume.containers.delete(containerId);

                if (volume.containers.size === 0) {
                    volume.state = VolumeState.AVAILABLE;
                }
            }

            this.#containers.delete(containerId);

            this.emit("container.detached", { containerId });
        });
    }

    async write(volumeName, key, value, containerId) {
        return this.#serialize(async () => {
            const volume = this.#getVolume(volumeName);

            if (
                typeof key !== "string" ||
                key.length === 0 ||
                key.length > 255 ||
                key.includes("\0")
            ) {
                throw new ValidationError("Invalid data key");
            }

            if (typeof value !== "string") {
                throw new ValidationError("Value must be a string");
            }

            if (containerId) {
                const container = this.#containers.get(containerId);

                if (!container || !volume.containers.has(containerId)) {
                    throw new ConflictError("Container does not own this mount");
                }

                const mounts = container.mounts.filter(
                    m => m.type === MountType.VOLUME &&
                         m.source === volumeName
                );

                if (!mounts.length || mounts.every(m => m.readOnly)) {
                    throw new ConflictError("Read-only mount");
                }
            }

            volume.data.set(key, value);

            this.emit("volume.data_written", {
                volumeName,
                key,
                containerId: containerId || null
            });
        });
    }

    read(volumeName, key) {
        const volume = this.#getVolume(volumeName);

        if (!volume.data.has(key)) {
            throw new NotFoundError(`Missing key: ${key}`);
        }

        return volume.data.get(key);
    }

    inspectVolume(name) {
        const volume = this.#getVolume(name);

        return {
            id: volume.id,
            name: volume.name,
            driver: volume.driver,
            labels: { ...volume.labels },
            state: volume.state,
            containers: [...volume.containers],
            recordCount: volume.data.size,
            createdAt: volume.createdAt
        };
    }

    listVolumes(filter = {}) {
        return [...this.#volumes.values()]
            .filter(volume =>
                !filter.driver || volume.driver === filter.driver
            )
            .filter(volume =>
                !filter.environment ||
                volume.labels.environment === filter.environment
            )
            .map(volume => this.inspectVolume(volume.name));
    }

    async removeVolume(name) {
        return this.#serialize(async () => {
            const volume = this.#getVolume(name);

            if (volume.containers.size > 0) {
                throw new ConflictError("Volume is currently in use");
            }

            this.#volumes.delete(name);

            this.emit("volume.removed", { name });
        });
    }

    async prune(environment) {
        return this.#serialize(async () => {
            const removed = [];

            for (const [name, volume] of this.#volumes) {
                const matches = !environment ||
                    volume.labels.environment === environment;

                if (matches && volume.containers.size === 0) {
                    this.#volumes.delete(name);
                    removed.push(name);
                }
            }

            this.emit("volume.pruned", { removed });
            return removed;
        });
    }

    // Export a consistent snapshot. Production backups also require
    // filesystem/database consistency and encryption.
    async exportBackup(name, filename) {
        const volume = this.#getVolume(name);

        const snapshot = {
            formatVersion: 1,
            name,
            driver: volume.driver,
            createdAt: volume.createdAt,
            data: Object.fromEntries(volume.data)
        };

        const destination = path.resolve(filename);

        await fs.writeFile(
            destination,
            JSON.stringify(snapshot, null, 2),
            { flag: "wx", mode: 0o600 }
        );

        this.emit("backup.created", { name, destination });
        return destination;
    }

    async importBackup(filename, newName) {
        const contents = await fs.readFile(filename, "utf8");
        const snapshot = JSON.parse(contents);

        if (
            snapshot.formatVersion !== 1 ||
            typeof snapshot.data !== "object" ||
            snapshot.data === null ||
            Array.isArray(snapshot.data)
        ) {
            throw new ValidationError("Invalid backup document");
        }

        const volume = await this.createVolume(newName, {
            driver: snapshot.driver || "local"
        });

        return this.#serialize(async () => {
            const target = this.#getVolume(newName);

            for (const [key, value] of Object.entries(snapshot.data)) {
                if (
                    typeof key !== "string" ||
                    typeof value !== "string"
                ) {
                    throw new ValidationError("Invalid backup entry");
                }

                target.data.set(key, value);
            }

            return volume;
        });
    }
}

async function main() {
    const manager = new StorageManager();

    manager.on("volume.created", event => {
        console.log("EVENT volume.created:", event.name);
    });

    manager.on("volume.data_written", event => {
        console.log("EVENT volume.data_written:", event.key);
    });

    await manager.createVolume("application_data", {
        driver: "local",
        labels: {
            environment: "development",
            service: "inventory"
        }
    });

    await manager.write(
        "application_data",
        "database",
        "inventory_db"
    );

    const containerId = "inventory-api";

    await manager.attachContainer(containerId, [
        {
            type: MountType.VOLUME,
            source: "application_data",
            destination: "/var/lib/application",
            readOnly: false
        },
        {
            type: MountType.TMPFS,
            source: "tmpfs",
            destination: "/run/secrets",
            readOnly: true
        }
    ]);

    await manager.write(
        "application_data",
        "status",
        "healthy",
        containerId
    );

    console.log("Inspection:");
    console.log(manager.inspectVolume("application_data"));

    console.log("Read:", manager.read(
        "application_data",
        "database"
    ));

    try {
        await manager.removeVolume("application_data");
    } catch (error) {
        console.log("Expected lifecycle restriction:", error.message);
    }

    await manager.detachContainer(containerId);

    const backupDirectory = await fs.mkdtemp(
        path.join(require("node:os").tmpdir(), "docker-storage-")
    );

    const backupPath = path.join(backupDirectory, "volume-backup.json");

    await manager.exportBackup("application_data", backupPath);

    await manager.importBackup(
        backupPath,
        "application_data_restored"
    );

    console.log("Restored:", manager.inspectVolume(
        "application_data_restored"
    ));

    console.log("All volumes:", manager.listVolumes());

    const removed = await manager.prune("development");
    console.log("Pruned:", removed);

    await fs.rm(backupDirectory, {
        recursive: true,
        force: true
    });
}

main().catch(error => {
    console.error("Storage execution failed:", error.message);
    process.exitCode = 1;
});
