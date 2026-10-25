#!/usr/bin/env node

"use strict";

/*
 * Compute and Storage Project
 *
 * Event-driven simulation of:
 * - compute instances
 * - load balancing
 * - horizontal scaling
 * - object storage
 * - health checks
 * - backups
 * - restore
 * - merge-like policy evaluation for infrastructure operations
 *
 * No external npm dependencies are required.
 */

const crypto = require("crypto");
const { EventEmitter } = require("events");

class InfrastructureError extends Error {}

class Instance {
    constructor(id, capacity) {
        if (!id || capacity <= 0) {
            throw new InfrastructureError("Invalid compute instance.");
        }

        this.id = id;
        this.capacity = capacity;
        this.activeRequests = 0;
        this.healthy = true;
    }

    get utilization() {
        return this.capacity === 0
            ? 1
            : this.activeRequests / this.capacity;
    }

    canReceiveTraffic() {
        return this.healthy && this.activeRequests < this.capacity;
    }
}

class ObjectStorage {
    constructor(maxObjectSize) {
        if (!Number.isInteger(maxObjectSize) || maxObjectSize <= 0) {
            throw new InfrastructureError("Invalid object-size limit.");
        }

        this.maxObjectSize = maxObjectSize;
        this.objects = new Map();
    }

    put(key, content) {
        if (!key || key.startsWith("/")) {
            throw new InfrastructureError("Object key must be relative.");
        }

        const buffer = Buffer.isBuffer(content)
            ? Buffer.from(content)
            : Buffer.from(String(content), "utf8");

        if (buffer.length > this.maxObjectSize) {
            throw new InfrastructureError(
                `Object '${key}' exceeds the storage limit.`
            );
        }

        const checksum = crypto
            .createHash("sha256")
            .update(buffer)
            .digest("hex");

        const object = {
            key,
            data: buffer,
            size: buffer.length,
            checksum,
            createdAt: new Date().toISOString(),
        };

        this.objects.set(key, object);
        return object;
    }

    get(key) {
        const object = this.objects.get(key);

        if (!object) {
            throw new InfrastructureError(`Object '${key}' does not exist.`);
        }

        const checksum = crypto
            .createHash("sha256")
            .update(object.data)
            .digest("hex");

        if (checksum !== object.checksum) {
            throw new InfrastructureError(
                `Integrity verification failed for '${key}'.`
            );
        }

        return Buffer.from(object.data);
    }

    remove(key) {
        if (!this.objects.has(key)) {
            throw new InfrastructureError(`Object '${key}' does not exist.`);
        }

        this.objects.delete(key);
    }

    snapshot() {
        return new Map(
            [...this.objects.entries()].map(([key, value]) => [
                key,
                {
                    key: value.key,
                    data: Buffer.from(value.data),
                    size: value.size,
                    checksum: value.checksum,
                    createdAt: value.createdAt,
                },
            ])
        );
    }

    restore(snapshot) {
        this.objects = new Map(
            [...snapshot.entries()].map(([key, value]) => [
                key,
                {
                    ...value,
                    data: Buffer.from(value.data),
                },
            ])
        );
    }
}

class LoadBalancer {
    constructor(instances) {
        this.instances = instances;
    }

    chooseInstance() {
        const candidates = this.instances.filter((i) =>
            i.canReceiveTraffic()
        );

        if (candidates.length === 0) {
            throw new InfrastructureError(
                "No healthy instance has available capacity."
            );
        }

        return candidates.reduce((best, current) =>
            current.utilization < best.utilization ? current : best
        );
    }

    async handleRequests(requestCount) {
        if (!Number.isInteger(requestCount) || requestCount < 0) {
            throw new InfrastructureError("Request count must be non-negative.");
        }

        const distribution = new Map();

        for (let request = 0; request < requestCount; request++) {
            const instance = this.chooseInstance();
            instance.activeRequests++;

            distribution.set(
                instance.id,
                (distribution.get(instance.id) || 0) + 1
            );

            // Promise.resolve keeps request processing asynchronous without
            // requiring a third-party HTTP framework.
            await Promise.resolve();
        }

        return distribution;
    }

    completeRequests(requestCount) {
        if (!Number.isInteger(requestCount) || requestCount < 0) {
            throw new InfrastructureError(
                "Completed request count is invalid."
            );
        }

        let remaining = requestCount;

        const instances = [...this.instances].sort(
            (a, b) => b.activeRequests - a.activeRequests
        );

        for (const instance of instances) {
            const completed = Math.min(
                instance.activeRequests,
                remaining
            );

            instance.activeRequests -= completed;
            remaining -= completed;

            if (remaining === 0) {
                return;
            }
        }

        if (remaining > 0) {
            throw new InfrastructureError(
                "Cannot complete more requests than are active."
            );
        }
    }
}

class BackupManager {
    constructor(storage, retentionDays) {
        this.storage = storage;
        this.retentionDays = retentionDays;
        this.backups = new Map();
        this.sequence = 0;
    }

    createBackup() {
        this.sequence++;

        const id = `backup-${String(this.sequence).padStart(4, "0")}`;

        const backup = {
            id,
            createdAt: new Date(),
            snapshot: this.storage.snapshot(),
            state: "available",
        };

        this.backups.set(id, backup);
        return backup;
    }

    restore(id) {
        const backup = this.backups.get(id);

        if (!backup) {
            throw new InfrastructureError(`Backup '${id}' was not found.`);
        }

        backup.state = "restoring";

        try {
            this.storage.restore(backup.snapshot);
            backup.state = "available";
        } catch (error) {
            backup.state = "failed";
            throw error;
        }
    }

    expire(now = new Date()) {
        const cutoff =
            now.getTime() - this.retentionDays * 24 * 60 * 60 * 1000;

        for (const [id, backup] of this.backups) {
            if (backup.createdAt.getTime() < cutoff) {
                this.backups.delete(id);
            }
        }
    }
}

class AutoScaler extends EventEmitter {
    constructor(config, platform) {
        super();
        this.config = config;
        this.platform = platform;
    }

    averageUtilization() {
        const active = this.platform.instances.filter((i) => i.healthy);

        if (active.length === 0) {
            return 1;
        }

        return (
            active.reduce((sum, instance) => sum + instance.utilization, 0) /
            active.length
        );
    }

    evaluate() {
        const utilization = this.averageUtilization();

        if (
            utilization >= this.config.scaleUpThreshold &&
            this.platform.instances.length < this.config.maxInstances
        ) {
            const instance = this.platform.addInstance();
            this.emit("scaled", {
                action: "scale_up",
                instance: instance.id,
                utilization,
            });
            return "scale_up";
        }

        if (
            utilization <= this.config.scaleDownThreshold &&
            this.platform.instances.length > this.config.minInstances
        ) {
            const removable = [...this.platform.instances]
                .reverse()
                .find(
                    (instance) =>
                        instance.healthy &&
                        instance.activeRequests === 0
                );

            if (removable) {
                this.platform.removeInstance(removable.id);
                this.emit("scaled", {
                    action: "scale_down",
                    instance: removable.id,
                    utilization,
                });
                return "scale_down";
            }
        }

        this.emit("unchanged", { utilization });
        return "unchanged";
    }
}

class ApplicationPlatform extends EventEmitter {
    constructor(config) {
        super();

        if (config.minInstances < 1) {
            throw new InfrastructureError(
                "At least one instance is required."
            );
        }

        if (config.minInstances > config.maxInstances) {
            throw new InfrastructureError(
                "Minimum instances cannot exceed maximum instances."
            );
        }

        this.config = config;
        this.instances = [];

        for (let i = 1; i <= config.minInstances; i++) {
            this.instances.push(
                new Instance(
                    `app-${String(i).padStart(2, "0")}`,
                    config.requestsPerInstance
                )
            );
        }

        this.storage = new ObjectStorage(config.maxObjectSize);
        this.loadBalancer = new LoadBalancer(this.instances);
        this.backups = new BackupManager(
            this.storage,
            config.backupRetentionDays
        );

        this.scaler = new AutoScaler(config, this);

        this.scaler.on("scaled", (event) => this.emit("scaling", event));
    }

    addInstance() {
        if (this.instances.length >= this.config.maxInstances) {
            throw new InfrastructureError("Maximum instance count reached.");
        }

        const id = `app-${String(this.instances.length + 1).padStart(2, "0")}`;
        const instance = new Instance(
            id,
            this.config.requestsPerInstance
        );

        this.instances.push(instance);
        this.loadBalancer.instances = this.instances;

        return instance;
    }

    removeInstance(id) {
        const index = this.instances.findIndex((i) => i.id === id);

        if (index === -1) {
            throw new InfrastructureError(`Instance '${id}' not found.`);
        }

        const instance = this.instances[index];

        if (instance.activeRequests !== 0) {
            throw new InfrastructureError(
                "An active instance cannot be removed."
            );
        }

        if (this.instances.length <= this.config.minInstances) {
            throw new InfrastructureError(
                "Minimum instance count would be violated."
            );
        }

        this.instances.splice(index, 1);
        this.loadBalancer.instances = this.instances;
    }

    markUnhealthy(id) {
        const instance = this.instances.find((i) => i.id === id);

        if (!instance) {
            throw new InfrastructureError(`Instance '${id}' not found.`);
        }

        if (instance.activeRequests !== 0) {
            throw new InfrastructureError(
                "Drain active requests before marking an instance unhealthy."
            );
        }

        instance.healthy = false;
        this.emit("healthChanged", {
            instance: id,
            healthy: false,
        });
    }

    replaceUnhealthyInstances() {
        const unhealthy = this.instances.filter((i) => !i.healthy);

        for (const instance of unhealthy) {
            this.instances = this.instances.filter(
                (candidate) => candidate.id !== instance.id
            );
        }

        this.loadBalancer.instances = this.instances;

        while (this.instances.length < this.config.minInstances) {
            this.addInstance();
        }

        return unhealthy.length;
    }

    capacityReport() {
        const healthy = this.instances.filter((i) => i.healthy);
        const capacity = healthy.reduce(
            (sum, instance) => sum + instance.capacity,
            0
        );
        const active = healthy.reduce(
            (sum, instance) => sum + instance.activeRequests,
            0
        );

        return {
            instances: this.instances.length,
            healthyInstances: healthy.length,
            capacity,
            activeRequests: active,
            utilization: capacity === 0 ? 1 : active / capacity,
            storedObjects: this.storage.objects.size,
            storedBytes: [...this.storage.objects.values()].reduce(
                (sum, object) => sum + object.size,
                0
            ),
            backups: this.backups.backups.size,
        };
    }
}

async function runTests() {
    const platform = new ApplicationPlatform({
        minInstances: 2,
        maxInstances: 4,
        requestsPerInstance: 10,
        scaleUpThreshold: 0.7,
        scaleDownThreshold: 0.25,
        maxObjectSize: 1024,
        backupRetentionDays: 7,
    });

    const object = platform.storage.put(
        "config/application.json",
        JSON.stringify({ version: 1, region: "primary" })
    );

    console.assert(object.size > 0);
    console.assert(platform.storage.get("config/application.json").length > 0);

    const distribution = await platform.loadBalancer.handleRequests(15);
    console.assert(
        [...distribution.values()].reduce((a, b) => a + b, 0) === 15
    );

    platform.loadBalancer.completeRequests(15);

    const backup = platform.backups.createBackup();

    platform.storage.remove("config/application.json");
    console.assert(platform.storage.objects.size === 0);

    platform.backups.restore(backup.id);

    console.assert(platform.storage.objects.size === 1);

    platform.markUnhealthy(platform.instances[0].id);
    const replaced = platform.replaceUnhealthyInstances();

    console.assert(replaced === 1);
    console.assert(platform.instances.length >= 2);
}

async function main() {
    await runTests();

    const platform = new ApplicationPlatform({
        minInstances: 2,
        maxInstances: 6,
        requestsPerInstance: 100,
        scaleUpThreshold: 0.7,
        scaleDownThreshold: 0.25,
        maxObjectSize: 10 * 1024 * 1024,
        backupRetentionDays: 7,
    });

    platform.on("scaling", (event) => {
        console.log("Scaling event:", event);
    });

    platform.on("healthChanged", (event) => {
        console.log("Health event:", event);
    });

    platform.storage.put(
        "releases/v1/config.json",
        JSON.stringify({
            version: "1.0.0",
            region: "primary",
        })
    );

    platform.storage.put(
        "releases/v1/index.html",
        "<html><body>Scalable application</body></html>"
    );

    const traffic = await platform.loadBalancer.handleRequests(180);

    console.log("Request distribution:");
    console.log(Object.fromEntries(traffic));

    console.log("\nBefore scaling:");
    console.log(platform.capacityReport());

    console.log("\nScaling decision:", platform.scaler.evaluate());

    platform.loadBalancer.completeRequests(180);

    const backup = platform.backups.createBackup();
    console.log("\nCreated backup:", backup.id);

    console.log("\nCapacity after traffic completion:");
    console.log(platform.capacityReport());

    platform.markUnhealthy(platform.instances[0].id);
    platform.replaceUnhealthyInstances();

    console.log("\nAfter health recovery:");
    console.log(platform.capacityReport());
}

main().catch((error) => {
    console.error("Infrastructure operation failed:", error.message);
    process.exitCode = 1;
});
