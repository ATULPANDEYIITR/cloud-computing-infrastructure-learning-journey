/*
 * Storage Virtualization Laboratory
 *
 * Node.js 18+ compatible.
 *
 * This implementation uses an event-driven storage controller to model:
 * physical devices -> storage pool -> logical volume -> virtual disk.
 *
 * It deliberately uses JavaScript's event and Promise model to demonstrate
 * how asynchronous I/O requests can pass through an abstraction layer.
 */

"use strict";

const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");

class StorageError extends Error {}
class CapacityError extends StorageError {}
class InvalidOperationError extends StorageError {}

const DeviceState = Object.freeze({
    ONLINE: "online",
    DEGRADED: "degraded",
    FAILED: "failed"
});

const VolumeState = Object.freeze({
    ONLINE: "online",
    READ_ONLY: "read-only",
    OFFLINE: "offline"
});

class PhysicalDevice {
    constructor(id, capacityGB, latencyMs = 2) {
        if (!id || capacityGB <= 0) {
            throw new TypeError("A device requires a positive capacity.");
        }

        this.id = id;
        this.capacityGB = capacityGB;
        this.usedGB = 0;
        this.latencyMs = latencyMs;
        this.state = DeviceState.ONLINE;
    }

    get freeGB() {
        return this.capacityGB - this.usedGB;
    }

    allocate(sizeGB) {
        if (this.state === DeviceState.FAILED) {
            throw new InvalidOperationError(
                `${this.id} is failed and cannot accept allocations.`
            );
        }

        if (sizeGB > this.freeGB) {
            throw new CapacityError(
                `${this.id} has ${this.freeGB} GB available.`
            );
        }

        this.usedGB += sizeGB;
    }

    fail() {
        this.state = DeviceState.FAILED;
    }
}

class StoragePool extends EventEmitter {
    constructor(name, extentSizeGB = 1) {
        super();

        if (extentSizeGB <= 0) {
            throw new TypeError("Extent size must be positive.");
        }

        this.name = name;
        this.extentSizeGB = extentSizeGB;
        this.devices = new Map();
        this.volumes = new Map();
        this.extents = new Map();
        this.snapshots = new Map();
        this.nextExtentId = 1;
        this.generation = 0;
    }

    addDevice(device) {
        if (this.devices.has(device.id)) {
            throw new InvalidOperationError(
                `Device ${device.id} already exists.`
            );
        }

        this.devices.set(device.id, device);

        this.emit("deviceAdded", {
            deviceId: device.id,
            capacityGB: device.capacityGB
        });
    }

    get physicalCapacityGB() {
        return [...this.devices.values()]
            .reduce((sum, device) => sum + device.capacityGB, 0);
    }

    get physicalUsedGB() {
        return [...this.devices.values()]
            .reduce((sum, device) => sum + device.usedGB, 0);
    }

    get physicalFreeGB() {
        return this.physicalCapacityGB - this.physicalUsedGB;
    }

    selectDevice() {
        const candidates = [...this.devices.values()]
            .filter(
                device =>
                    device.state !== DeviceState.FAILED &&
                    device.freeGB >= this.extentSizeGB
            )
            .sort((a, b) => {
                const utilizationA = a.usedGB / a.capacityGB;
                const utilizationB = b.usedGB / b.capacityGB;
                return utilizationA - utilizationB || a.id.localeCompare(b.id);
            });

        if (candidates.length === 0) {
            throw new CapacityError("No device can allocate an extent.");
        }

        return candidates[0];
    }

    allocateExtent(volumeName) {
        const device = this.selectDevice();
        device.allocate(this.extentSizeGB);

        const extent = {
            id: this.nextExtentId++,
            deviceId: device.id,
            sizeGB: this.extentSizeGB,
            volumeName
        };

        this.extents.set(extent.id, extent);
        return extent;
    }

    createVolume(name, virtualSizeGB, thin = false) {
        if (this.volumes.has(name)) {
            throw new InvalidOperationError(`Volume ${name} already exists.`);
        }

        if (!Number.isInteger(virtualSizeGB) || virtualSizeGB <= 0) {
            throw new TypeError("Virtual volume size must be a positive integer.");
        }

        if (!thin && virtualSizeGB > this.physicalFreeGB) {
            throw new CapacityError(
                `Cannot reserve ${virtualSizeGB} GB from ${this.physicalFreeGB} GB.`
            );
        }

        const volume = {
            name,
            virtualSizeGB,
            thin,
            state: VolumeState.ONLINE,
            extents: [],
            blocks: new Map()
        };

        this.volumes.set(name, volume);

        if (!thin) {
            for (let i = 0; i < virtualSizeGB; i++) {
                volume.extents.push(this.allocateExtent(name).id);
            }
        }

        this.emit("volumeCreated", {
            name,
            virtualSizeGB,
            thin
        });

        return volume;
    }

    validateBlock(volume, block) {
        if (!Number.isInteger(block) || block < 0 || block >= volume.virtualSizeGB * 16) {
            throw new InvalidOperationError(
                `Logical block ${block} is outside ${volume.name}.`
            );
        }
    }

    ensureThinExtent(volume, block) {
        const blocksPerExtent = 16;
        const requiredExtent = Math.floor(block / blocksPerExtent);

        while (volume.extents.length <= requiredExtent) {
            if (volume.extents.length >= volume.virtualSizeGB) {
                throw new CapacityError(
                    `Virtual capacity exceeded for ${volume.name}.`
                );
            }

            volume.extents.push(this.allocateExtent(volume.name).id);
        }
    }

    write(volumeName, block, data) {
        const volume = this.volumes.get(volumeName);

        if (!volume) {
            throw new InvalidOperationError(`Unknown volume ${volumeName}.`);
        }

        if (volume.state !== VolumeState.ONLINE) {
            throw new InvalidOperationError(
                `Volume ${volumeName} is not writable.`
            );
        }

        this.validateBlock(volume, block);

        if (volume.thin) {
            this.ensureThinExtent(volume, block);
        }

        if (typeof data !== "string") {
            throw new TypeError("Block data must be a string.");
        }

        volume.blocks.set(block, data);
        this.generation += 1;

        this.emit("write", {
            volumeName,
            block,
            generation: this.generation
        });
    }

    read(volumeName, block) {
        const volume = this.volumes.get(volumeName);

        if (!volume) {
            throw new InvalidOperationError(`Unknown volume ${volumeName}.`);
        }

        this.validateBlock(volume, block);
        return volume.blocks.get(block) ?? "";
    }

    snapshot(snapshotName, volumeName) {
        if (this.snapshots.has(snapshotName)) {
            throw new InvalidOperationError(
                `Snapshot ${snapshotName} already exists.`
            );
        }

        const volume = this.volumes.get(volumeName);

        if (!volume) {
            throw new InvalidOperationError(`Unknown volume ${volumeName}.`);
        }

        const blocks = new Map();

        for (const [block, data] of volume.blocks) {
            blocks.set(
                block,
                crypto.createHash("sha256").update(data).digest("hex")
            );
        }

        const snapshot = {
            name: snapshotName,
            source: volumeName,
            generation: this.generation,
            blocks
        };

        this.snapshots.set(snapshotName, snapshot);
        this.emit("snapshotCreated", snapshot);
        return snapshot;
    }

    verifySnapshot(snapshotName) {
        const snapshot = this.snapshots.get(snapshotName);

        if (!snapshot) {
            throw new InvalidOperationError(
                `Unknown snapshot ${snapshotName}.`
            );
        }

        const volume = this.volumes.get(snapshot.source);
        const result = new Map();

        for (const [block, expectedHash] of snapshot.blocks) {
            const current = volume.blocks.get(block) ?? "";
            const currentHash = crypto
                .createHash("sha256")
                .update(current)
                .digest("hex");

            result.set(block, currentHash === expectedHash);
        }

        return result;
    }

    failDevice(deviceId) {
        const device = this.devices.get(deviceId);

        if (!device) {
            throw new InvalidOperationError(`Unknown device ${deviceId}.`);
        }

        device.fail();

        for (const volume of this.volumes.values()) {
            const affected = volume.extents.some(
                extentId => this.extents.get(extentId)?.deviceId === deviceId
            );

            if (affected) {
                volume.state = VolumeState.READ_ONLY;
            }
        }

        this.emit("deviceFailed", { deviceId });
    }

    report() {
        return {
            pool: this.name,
            physicalCapacityGB: this.physicalCapacityGB,
            physicalUsedGB: this.physicalUsedGB,
            physicalFreeGB: this.physicalFreeGB,
            volumes: [...this.volumes.values()].map(volume => ({
                name: volume.name,
                virtualSizeGB: volume.virtualSizeGB,
                allocatedGB: volume.extents.length,
                thin: volume.thin,
                state: volume.state
            }))
        };
    }
}

class VirtualDisk {
    constructor(id, pool, volumeName) {
        this.id = id;
        this.pool = pool;
        this.volumeName = volumeName;
    }

    async write(block, data) {
        await new Promise(resolve => setTimeout(resolve, 1));
        this.pool.write(this.volumeName, block, data);
    }

    async read(block) {
        await new Promise(resolve => setTimeout(resolve, 1));
        return this.pool.read(this.volumeName, block);
    }
}

class StorageController extends EventEmitter {
    constructor(pool) {
        super();
        this.pool = pool;
        this.disks = new Map();

        this.pool.on("deviceFailed", event => this.emit("alert", {
            severity: "critical",
            message: `Storage device ${event.deviceId} failed.`
        }));

        this.pool.on("write", event => this.emit("audit", {
            operation: "WRITE",
            ...event
        }));
    }

    exposeDisk(id, volumeName) {
        if (this.disks.has(id)) {
            throw new InvalidOperationError(`Disk ${id} already exists.`);
        }

        const disk = new VirtualDisk(id, this.pool, volumeName);
        this.disks.set(id, disk);
        return disk;
    }
}

async function run() {
    const pool = new StoragePool("enterprise-pool");

    pool.addDevice(new PhysicalDevice("nvme-a", 8, 1));
    pool.addDevice(new PhysicalDevice("nvme-b", 8, 1));
    pool.addDevice(new PhysicalDevice("ssd-c", 16, 4));

    const controller = new StorageController(pool);

    controller.on("audit", record => {
        console.log(
            `[AUDIT] ${record.operation} volume=${record.volumeName} block=${record.block}`
        );
    });

    controller.on("alert", alert => {
        console.log(`[ALERT] ${alert.severity}: ${alert.message}`);
    });

    pool.createVolume("vm-data", 6, false);
    pool.createVolume("logs", 10, true);

    const disk = controller.exposeDisk("vDisk-01", "vm-data");
    await disk.write(0, "filesystem-superblock");
    await disk.write(1, "database-metadata");

    console.log("Virtual disk block:", await disk.read(1));

    pool.write("logs", 32, "application-event-2026");
    console.log("Pool report:", pool.report());

    pool.snapshot("vm-data-before-maintenance", "vm-data");
    await disk.write(1, "database-metadata-updated");

    console.log(
        "Snapshot verification:",
        [...pool.verifySnapshot("vm-data-before-maintenance")]
    );

    pool.failDevice("nvme-a");

    try {
        await disk.write(2, "write-after-device-failure");
    } catch (error) {
        console.log("Expected write failure:", error.message);
    }

    console.log("Final report:", pool.report());
}

run().catch(error => {
    console.error("Storage controller stopped:", error.message);
    process.exitCode = 1;
});
