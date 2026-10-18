"use strict";

/*
 * Block-storage control-plane simulation.
 *
 * The implementation deliberately models the relationships among:
 * volumes, disk attachment, snapshots, IOPS, and throughput.
 *
 * It uses event-driven JavaScript to represent lifecycle transitions and
 * asynchronous snapshot creation, rather than translating the Python model.
 */

const EventEmitter = require("node:events");

const VolumeType = Object.freeze({
  GP3: "gp3",
  IO2: "io2"
});

const VolumeState = Object.freeze({
  AVAILABLE: "available",
  ATTACHED: "attached",
  DETACHING: "detaching"
});

const SnapshotState = Object.freeze({
  CREATING: "creating",
  COMPLETED: "completed"
});

class StorageError extends Error {
  constructor(message, code) {
    super(message);
    this.name = "StorageError";
    this.code = code;
  }
}

class BlockVolume {
  constructor({
    id,
    sizeGiB,
    type,
    iops,
    throughputMiBs,
    encrypted = true
  }) {
    this.id = id;
    this.sizeGiB = sizeGiB;
    this.type = type;
    this.iops = iops;
    this.throughputMiBs = throughputMiBs;
    this.encrypted = encrypted;
    this.state = VolumeState.AVAILABLE;
    this.attachment = null;

    this.validate();
  }

  validate() {
    if (!Number.isInteger(this.sizeGiB) || this.sizeGiB <= 0) {
      throw new StorageError("Volume size must be a positive integer", "INVALID_SIZE");
    }

    if (!Object.values(VolumeType).includes(this.type)) {
      throw new StorageError("Unsupported volume type", "INVALID_TYPE");
    }

    if (this.type === VolumeType.GP3) {
      if (this.iops < 3000 || this.iops > 16000) {
        throw new StorageError("gp3 IOPS must be between 3,000 and 16,000", "INVALID_IOPS");
      }

      if (this.throughputMiBs < 125 || this.throughputMiBs > 1000) {
        throw new StorageError(
          "gp3 throughput must be between 125 and 1,000 MiB/s",
          "INVALID_THROUGHPUT"
        );
      }
    }

    if (this.type === VolumeType.IO2 && (this.iops < 100 || this.iops > 64000)) {
      throw new StorageError(
        "io2 IOPS must be between 100 and 64,000",
        "INVALID_IOPS"
      );
    }
  }

  configurePerformance(iops, throughputMiBs) {
    const old = {
      iops: this.iops,
      throughputMiBs: this.throughputMiBs
    };

    this.iops = iops;
    this.throughputMiBs = throughputMiBs;

    try {
      this.validate();
    } catch (error) {
      this.iops = old.iops;
      this.throughputMiBs = old.throughputMiBs;
      throw error;
    }
  }

  performancePressure(requestsPerSecond, ioKiB) {
    const requestedMiBs = requestsPerSecond * ioKiB / 1024;

    return {
      requestedMiBs,
      iopsPressure: requestsPerSecond / this.iops,
      throughputPressure: requestedMiBs / this.throughputMiBs
    };
  }
}

class Snapshot {
  constructor(id, volumeId, sizeGiB, parentId = null) {
    this.id = id;
    this.volumeId = volumeId;
    this.sizeGiB = sizeGiB;
    this.parentId = parentId;
    this.state = SnapshotState.CREATING;
    this.progress = 0;
  }

  advance(percent) {
    this.progress = Math.min(100, this.progress + percent);

    if (this.progress === 100) {
      this.state = SnapshotState.COMPLETED;
    }
  }
}

class StorageControlPlane extends EventEmitter {
  constructor() {
    super();

    this.volumes = new Map();
    this.snapshots = new Map();
    this.nextVolumeId = 1;
    this.nextSnapshotId = 1;
  }

  createVolume(config) {
    const volume = new BlockVolume({
      ...config,
      id: `vol-${String(this.nextVolumeId++).padStart(4, "0")}`
    });

    this.volumes.set(volume.id, volume);
    this.emit("volume.created", volume);

    return volume;
  }

  attach(volumeId, instanceId, device) {
    const volume = this.requireVolume(volumeId);

    if (volume.state !== VolumeState.AVAILABLE) {
      throw new StorageError(
        `${volumeId} is not available for attachment`,
        "ATTACHMENT_CONFLICT"
      );
    }

    if (!/^\/dev\/[a-z]+$/.test(device)) {
      throw new StorageError(
        "Device must use a Linux-style /dev/<name> path",
        "INVALID_DEVICE"
      );
    }

    volume.state = VolumeState.ATTACHED;
    volume.attachment = {
      instanceId,
      device,
      attachedAt: new Date()
    };

    this.emit("volume.attached", {
      volumeId,
      instanceId,
      device
    });

    return volume.attachment;
  }

  detach(volumeId) {
    const volume = this.requireVolume(volumeId);

    if (volume.state !== VolumeState.ATTACHED) {
      throw new StorageError(
        `${volumeId} is not attached`,
        "NOT_ATTACHED"
      );
    }

    volume.state = VolumeState.DETACHING;
    this.emit("volume.detaching", volumeId);

    // A real provider exposes asynchronous attachment state. The simulation
    // uses a short timer so consumers can observe the lifecycle event.
    return new Promise((resolve) => {
      setTimeout(() => {
        volume.state = VolumeState.AVAILABLE;
        const previousAttachment = volume.attachment;
        volume.attachment = null;

        this.emit("volume.detached", {
          volumeId,
          previousAttachment
        });

        resolve(previousAttachment);
      }, 25);
    });
  }

  async createSnapshot(volumeId, parentId = null) {
    const volume = this.requireVolume(volumeId);

    if (parentId !== null && !this.snapshots.has(parentId)) {
      throw new StorageError(
        "Snapshot parent does not exist",
        "INVALID_PARENT"
      );
    }

    const snapshot = new Snapshot(
      `snap-${String(this.nextSnapshotId++).padStart(4, "0")}`,
      volume.id,
      volume.sizeGiB,
      parentId
    );

    this.snapshots.set(snapshot.id, snapshot);
    this.emit("snapshot.created", snapshot);

    // The timer models an asynchronous control-plane operation.
    while (snapshot.state !== SnapshotState.COMPLETED) {
      await new Promise((resolve) => setTimeout(resolve, 5));
      snapshot.advance(25);
      this.emit("snapshot.progress", {
        id: snapshot.id,
        progress: snapshot.progress
      });
    }

    this.emit("snapshot.completed", snapshot);
    return snapshot;
  }

  restore(snapshotId, type = VolumeType.GP3) {
    const snapshot = this.snapshots.get(snapshotId);

    if (!snapshot) {
      throw new StorageError("Snapshot not found", "SNAPSHOT_NOT_FOUND");
    }

    if (snapshot.state !== SnapshotState.COMPLETED) {
      throw new StorageError(
        "Only completed snapshots can be restored",
        "SNAPSHOT_INCOMPLETE"
      );
    }

    return this.createVolume({
      sizeGiB: snapshot.sizeGiB,
      type,
      iops: type === VolumeType.GP3 ? 3000 : 10000,
      throughputMiBs: type === VolumeType.GP3 ? 125 : 250
    });
  }

  evaluateWorkload(volumeId, {
    requestsPerSecond,
    ioKiB = 16,
    durationSeconds = 60
  }) {
    const volume = this.requireVolume(volumeId);

    if (requestsPerSecond < 0 || ioKiB <= 0 || durationSeconds <= 0) {
      throw new StorageError("Invalid workload parameters", "INVALID_WORKLOAD");
    }

    const pressure = volume.performancePressure(requestsPerSecond, ioKiB);
    const maximumIopsFromThroughput =
      volume.throughputMiBs * 1024 / ioKiB;

    const sustainableIops = Math.min(
      volume.iops,
      maximumIopsFromThroughput
    );

    const completedIops = Math.min(
      requestsPerSecond,
      sustainableIops
    );

    const requestedRequests = requestsPerSecond * durationSeconds;
    const completedRequests = Math.floor(completedIops * durationSeconds);

    const bottleneck =
      pressure.iopsPressure >= pressure.throughputPressure
        ? "IOPS"
        : "throughput";

    return {
      requestedRequests,
      completedRequests,
      rejectedRequests: requestedRequests - completedRequests,
      requestedMiBs: pressure.requestedMiBs,
      bottleneck,
      iopsPressure: pressure.iopsPressure,
      throughputPressure: pressure.throughputPressure
    };
  }

  requireVolume(volumeId) {
    const volume = this.volumes.get(volumeId);

    if (!volume) {
      throw new StorageError(
        `Volume ${volumeId} does not exist`,
        "VOLUME_NOT_FOUND"
      );
    }

    return volume;
  }
}

function attachEventLogging(controlPlane) {
  controlPlane.on("volume.created", (volume) => {
    console.log(
      `[volume.created] ${volume.id} ${volume.sizeGiB} GiB ${volume.type}`
    );
  });

  controlPlane.on("volume.attached", (event) => {
    console.log(
      `[volume.attached] ${event.volumeId} -> ${event.instanceId} (${event.device})`
    );
  });

  controlPlane.on("volume.detaching", (volumeId) => {
    console.log(`[volume.detaching] ${volumeId}`);
  });

  controlPlane.on("volume.detached", (event) => {
    console.log(`[volume.detached] ${event.volumeId}`);
  });

  controlPlane.on("snapshot.progress", (event) => {
    console.log(`[snapshot.progress] ${event.id}: ${event.progress}%`);
  });

  controlPlane.on("snapshot.completed", (snapshot) => {
    console.log(`[snapshot.completed] ${snapshot.id}`);
  });
}

async function demonstrateDatabaseStorage() {
  const storage = new StorageControlPlane();
  attachEventLogging(storage);

  console.log("\n=== Production database volume ===");

  const databaseVolume = storage.createVolume({
    sizeGiB: 500,
    type: VolumeType.GP3,
    iops: 12000,
    throughputMiBs: 500
  });

  storage.attach(
    databaseVolume.id,
    "db-production-01",
    "/dev/sdf"
  );

  const workload = storage.evaluateWorkload(databaseVolume.id, {
    requestsPerSecond: 18000,
    ioKiB: 16,
    durationSeconds: 60
  });

  console.table(workload);

  console.log("\n=== Snapshot lifecycle ===");

  const snapshot = await storage.createSnapshot(databaseVolume.id);

  console.log({
    snapshotId: snapshot.id,
    sourceVolume: snapshot.volumeId,
    state: snapshot.state,
    parent: snapshot.parentId
  });

  console.log("\n=== Restore to a separate volume ===");

  const restoredVolume = storage.restore(snapshot.id);
  console.log(restoredVolume);

  console.log("\n=== Performance modification ===");

  databaseVolume.configurePerformance(16000, 750);
  console.log({
    iops: databaseVolume.iops,
    throughputMiBs: databaseVolume.throughputMiBs
  });

  await storage.detach(databaseVolume.id);
}

async function demonstrateFailureConditions() {
  console.log("\n=== Validation failures ===");

  const storage = new StorageControlPlane();

  try {
    storage.createVolume({
      sizeGiB: 100,
      type: VolumeType.GP3,
      iops: 1000,
      throughputMiBs: 125
    });
  } catch (error) {
    console.log(`${error.code}: ${error.message}`);
  }

  const volume = storage.createVolume({
    sizeGiB: 100,
    type: VolumeType.GP3,
    iops: 3000,
    throughputMiBs: 125
  });

  storage.attach(volume.id, "app-01", "/dev/sdg");

  try {
    storage.attach(volume.id, "app-02", "/dev/sdh");
  } catch (error) {
    console.log(`${error.code}: ${error.message}`);
  }

  await storage.detach(volume.id);

  try {
    await storage.createSnapshot("vol-9999");
  } catch (error) {
    console.log(`${error.code}: ${error.message}`);
  }
}

async function demonstrateSnapshotLineage() {
  console.log("\n=== Incremental snapshot lineage ===");

  const storage = new StorageControlPlane();

  const volume = storage.createVolume({
    sizeGiB: 250,
    type: VolumeType.GP3,
    iops: 6000,
    throughputMiBs: 250
  });

  const first = await storage.createSnapshot(volume.id);
  const second = await storage.createSnapshot(volume.id, first.id);
  const third = await storage.createSnapshot(volume.id, second.id);

  const lineage = [];
  let current = third;

  while (current) {
    lineage.push(current.id);
    current = current.parentId
      ? storage.snapshots.get(current.parentId)
      : null;
  }

  console.log(lineage.join(" -> "));
}

async function main() {
  await demonstrateDatabaseStorage();
  await demonstrateFailureConditions();
  await demonstrateSnapshotLineage();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
