"use strict";

/*
 * Cloud storage fundamentals using Node.js standard-library features.
 *
 * Run:
 *   node cloud_storage_fundamentals.js
 *
 * All prices, delays, and failure probabilities are illustrative.
 * This event-driven model explores storage lifecycle policies, retryable
 * replication, integrity verification, and availability-aware reads.
 */

const { createHash, randomUUID } = require("node:crypto");
const { EventEmitter } = require("node:events");

const STORAGE_CLASSES = Object.freeze({
  STANDARD: Object.freeze({
    name: "STANDARD",
    monthlyPerGb: 0.023,
    retrievalPerGb: 0,
    minimumRetentionDays: 0,
    retrievalDelayMs: 10,
  }),
  INFREQUENT: Object.freeze({
    name: "INFREQUENT",
    monthlyPerGb: 0.0125,
    retrievalPerGb: 0.01,
    minimumRetentionDays: 30,
    retrievalDelayMs: 30,
  }),
  ARCHIVE: Object.freeze({
    name: "ARCHIVE",
    monthlyPerGb: 0.004,
    retrievalPerGb: 0.03,
    minimumRetentionDays: 90,
    retrievalDelayMs: 100,
  }),
});

class StorageError extends Error {}
class RegionUnavailableError extends StorageError {}
class ObjectMissingError extends StorageError {}
class IntegrityError extends StorageError {}
class RetentionPolicyError extends StorageError {}

function sha256(content) {
  return createHash("sha256").update(content).digest("hex");
}

function validateObjectKey(key) {
  if (typeof key !== "string" || key.trim() === "") {
    throw new TypeError("Object key must be a non-empty string");
  }
  if (key.length > 1024) {
    throw new RangeError("Object key exceeds the configured length limit");
  }
}

function calculateMonthlyCost({
  sizeGb,
  retrievedGb = 0,
  storageClass,
  objectCount = 1,
  copies = 1,
}) {
  const policy = STORAGE_CLASSES[storageClass];

  if (!policy) throw new TypeError(`Unknown storage class: ${storageClass}`);
  if (!Number.isFinite(sizeGb) || sizeGb < 0) {
    throw new RangeError("Storage size must be a finite non-negative number");
  }
  if (!Number.isFinite(retrievedGb) || retrievedGb < 0) {
    throw new RangeError("Retrieval size must be non-negative");
  }
  if (!Number.isInteger(objectCount) || objectCount < 1) {
    throw new RangeError("Object count must be a positive integer");
  }
  if (!Number.isInteger(copies) || copies < 1) {
    throw new RangeError("Copy count must be a positive integer");
  }

  return (
    sizeGb * policy.monthlyPerGb * copies +
    retrievedGb * policy.retrievalPerGb +
    objectCount * 0.0004
  );
}

class StorageRegion {
  constructor(name) {
    if (!name || typeof name !== "string") {
      throw new TypeError("Region name is required");
    }
    this.name = name;
    this.available = true;
    this.objects = new Map();
  }
}

class ReplicationJob {
  constructor(object, targetRegion) {
    this.id = randomUUID();
    this.key = object.key;
    this.version = object.version;
    this.targetRegion = targetRegion;
    this.status = "PENDING";
    this.attempts = 0;
    this.lastError = null;
  }
}

class ObjectStorageService extends EventEmitter {
  constructor(regionNames, { mode = "ASYNC" } = {}) {
    super();

    if (!Array.isArray(regionNames) || regionNames.length === 0) {
      throw new TypeError("At least one region is required");
    }
    if (new Set(regionNames).size !== regionNames.length) {
      throw new TypeError("Region names must be unique");
    }
    if (!["SINGLE", "SYNC", "ASYNC"].includes(mode)) {
      throw new TypeError("Mode must be SINGLE, SYNC, or ASYNC");
    }

    this.regions = new Map(
      regionNames.map((name) => [name, new StorageRegion(name)])
    );
    this.primaryRegion = regionNames[0];
    this.mode = mode;
    this.jobs = [];
    this.versions = new Map();
    this.lifecycleHistory = [];
  }

  put({ key, content, storageClass = "STANDARD", day = 0 }) {
    validateObjectKey(key);

    if (!Buffer.isBuffer(content) && typeof content !== "string") {
      throw new TypeError("Content must be a Buffer or string");
    }
    if (!STORAGE_CLASSES[storageClass]) {
      throw new TypeError(`Unsupported storage class: ${storageClass}`);
    }
    if (!Number.isInteger(day) || day < 0) {
      throw new RangeError("Day must be a non-negative integer");
    }

    const primary = this.regions.get(this.primaryRegion);
    if (!primary.available) {
      throw new RegionUnavailableError("Primary region is unavailable");
    }

    const targets = [...this.regions.values()].filter(
      (region) => region.name !== this.primaryRegion
    );

    // Synchronous replication rejects a write if any required destination
    // is down, preserving the configured write acknowledgement policy.
    if (
      this.mode === "SYNC" &&
      targets.some((region) => !region.available)
    ) {
      throw new RegionUnavailableError(
        "Synchronous replication cannot reach every required region"
      );
    }

    const version = (this.versions.get(key) || 0) + 1;
    const payload = Buffer.isBuffer(content)
      ? Buffer.from(content)
      : Buffer.from(content, "utf8");

    const object = Object.freeze({
      key,
      content: payload,
      checksum: sha256(payload),
      sizeBytes: payload.length,
      storageClass,
      createdDay: day,
      version,
      etag: randomUUID(),
    });

    primary.objects.set(key, object);
    this.versions.set(key, version);
    this.emit("object:stored", { key, version, region: primary.name });

    if (this.mode === "SYNC") {
      for (const target of targets) {
        target.objects.set(key, object);
        this.emit("replication:completed", {
          key,
          version,
          region: target.name,
        });
      }
    } else if (this.mode === "ASYNC") {
      for (const target of targets) {
        this.jobs.push(new ReplicationJob(object, target.name));
      }
    }

    return object;
  }

  setRegionAvailability(regionName, available) {
    const region = this.regions.get(regionName);
    if (!region) throw new TypeError(`Unknown region: ${regionName}`);
    region.available = Boolean(available);
    this.emit("region:availability", {
      region: regionName,
      available: region.available,
    });
  }

  async processReplicationJobs({ maxAttempts = 3 } = {}) {
    if (!Number.isInteger(maxAttempts) || maxAttempts < 1) {
      throw new RangeError("maxAttempts must be positive");
    }

    for (const job of this.jobs) {
      if (job.status === "COMPLETED" || job.status === "FAILED") continue;

      const target = this.regions.get(job.targetRegion);
      job.attempts += 1;

      if (!target.available) {
        job.lastError = "Destination region is unavailable";
        this.emit("replication:retry", {
          jobId: job.id,
          attempt: job.attempts,
          region: target.name,
        });

        if (job.attempts >= maxAttempts) {
          job.status = "FAILED";
          this.emit("replication:failed", {
            jobId: job.id,
            key: job.key,
            region: target.name,
          });
        }
        continue;
      }

      const source = this.regions.get(this.primaryRegion);
      const latestSource = source.objects.get(job.key);

      // Do not overwrite a newer replica with an older queued event.
      if (latestSource && latestSource.version > job.version) {
        const existing = target.objects.get(job.key);
        if (!existing || existing.version < latestSource.version) {
          target.objects.set(job.key, latestSource);
        }
        job.status = "COMPLETED";
        this.emit("replication:completed", {
          key: job.key,
          version: latestSource.version,
          region: target.name,
          coalesced: true,
        });
        continue;
      }

      const current = target.objects.get(job.key);
      const candidate = latestSource || {
        key: job.key,
        version: job.version,
      };

      if (!current || current.version <= candidate.version) {
        target.objects.set(job.key, candidate);
      }

      job.status = "COMPLETED";
      this.emit("replication:completed", {
        key: job.key,
        version: candidate.version,
        region: target.name,
      });
    }

    return this.jobs.map((job) => ({
      id: job.id,
      key: job.key,
      region: job.targetRegion,
      status: job.status,
      attempts: job.attempts,
    }));
  }

  read(key, { preferredRegion = null } = {}) {
    validateObjectKey(key);

    const candidates = preferredRegion
      ? [this.regions.get(preferredRegion)]
      : [...this.regions.values()];

    if (candidates.some((region) => !region)) {
      throw new TypeError("Unknown preferred region");
    }

    for (const region of candidates) {
      if (!region.available) continue;

      const object = region.objects.get(key);
      if (!object) continue;

      if (sha256(object.content) !== object.checksum) {
        throw new IntegrityError(`Checksum mismatch for ${key}`);
      }

      this.emit("object:read", {
        key,
        version: object.version,
        region: region.name,
      });
      return object;
    }

    throw new ObjectMissingError(`No accessible copy of ${key}`);
  }

  evaluateLifecycle(key, day, targetClass) {
    const object = this.read(key);
    const targetPolicy = STORAGE_CLASSES[targetClass];

    if (!targetPolicy) throw new TypeError("Unknown target storage class");
    if (!Number.isInteger(day) || day < object.createdDay) {
      throw new RangeError("Evaluation day precedes object creation");
    }

    const age = day - object.createdDay;
    const currentPolicy = STORAGE_CLASSES[object.storageClass];

    if (age < currentPolicy.minimumRetentionDays) {
      throw new RetentionPolicyError(
        `${object.storageClass} requires ${currentPolicy.minimumRetentionDays} days`
      );
    }

    const transition = {
      key,
      from: object.storageClass,
      to: targetClass,
      ageDays: age,
      retrievalDelayMs: targetPolicy.retrievalDelayMs,
    };

    this.lifecycleHistory.push(transition);
    this.emit("lifecycle:transition-evaluated", transition);
    return transition;
  }
}

function availabilityWithIndependentCopies(singleCopyAvailability, copies) {
  if (
    !Number.isFinite(singleCopyAvailability) ||
    singleCopyAvailability < 0 ||
    singleCopyAvailability > 1
  ) {
    throw new RangeError("Availability must be between zero and one");
  }
  if (!Number.isInteger(copies) || copies < 1) {
    throw new RangeError("Copies must be a positive integer");
  }
  return 1 - (1 - singleCopyAvailability) ** copies;
}

async function main() {
  console.log("Cloud Storage Fundamentals");

  const storage = new ObjectStorageService(
    ["ap-south-1", "ap-southeast-1", "eu-west-1"],
    { mode: "ASYNC" }
  );

  storage.on("object:stored", (event) => {
    console.log(
      `Stored ${event.key} version ${event.version} in ${event.region}`
    );
  });

  storage.on("replication:completed", (event) => {
    console.log(
      `Replica ready: ${event.key} v${event.version} in ${event.region}`
    );
  });

  storage.on("replication:retry", (event) => {
    console.log(`Replication retry ${event.attempt} for ${event.region}`);
  });

  storage.on("region:availability", (event) => {
    console.log(
      `Region ${event.region} available=${event.available}`
    );
  });

  storage.put({
    key: "telemetry/plant-07/2026-10-16.json",
    content: JSON.stringify({
      plant: "plant-07",
      temperatureC: 42.6,
      inspectedAt: "2026-10-16T10:30:00Z",
    }),
    storageClass: "STANDARD",
    day: 0,
  });

  const jobs = await storage.processReplicationJobs();
  console.log("Replication job states:", jobs.map((job) => job.status));

  storage.setRegionAvailability("ap-south-1", false);
  const recovered = storage.read(
    "telemetry/plant-07/2026-10-16.json",
    { preferredRegion: "ap-southeast-1" }
  );
  console.log(
    `Read during regional outage: v${recovered.version}, ${recovered.sizeBytes} bytes`
  );

  storage.setRegionAvailability("ap-south-1", true);

  try {
    storage.evaluateLifecycle(
      "telemetry/plant-07/2026-10-16.json",
      10,
      "ARCHIVE"
    );
  } catch (error) {
    console.log(`Lifecycle evaluation rejected: ${error.message}`);
  }

  console.log("\nMonthly cost examples");
  for (const storageClass of Object.keys(STORAGE_CLASSES)) {
    const cost = calculateMonthlyCost({
      sizeGb: 500,
      retrievedGb: 20,
      storageClass,
      objectCount: 100,
      copies: 2,
    });
    console.log(`${storageClass}: $${cost.toFixed(2)}`);
  }

  console.log("\nAvailability model");
  for (const copies of [1, 2, 3]) {
    console.log(
      `${copies} independent copies: ${(
        availabilityWithIndependentCopies(0.999, copies) * 100
      ).toFixed(5)}%`
    );
  }

  // Redundancy cannot prevent logical corruption or an authorized deletion
  // that propagates to every replica. Independent versioned backups and
  // restore tests are separate controls.
  console.log(
    "Regional replication, integrity checks, and recoverable backups serve different purposes."
  );
}

main().catch((error) => {
  console.error("Storage demonstration failed:", error.message);
  process.exitCode = 1;
});
