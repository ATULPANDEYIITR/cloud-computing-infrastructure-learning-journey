"use strict";

/*
 * Storage performance policy evaluator.
 *
 * This Node.js program uses an event-driven workload simulator to demonstrate:
 * - latency-sensitive versus throughput-sensitive workloads
 * - cache behavior
 * - storage-tier selection
 * - cost constraints
 * - asynchronous request processing
 * - validation and failure handling
 */

const readline = require("node:readline");

const STORAGE_TIERS = Object.freeze([
  Object.freeze({
    name: "HDD",
    iops: 180,
    throughputMbps: 220,
    latencyMs: 8.0,
    costPerGbMonth: 0.02
  }),
  Object.freeze({
    name: "SATA SSD",
    iops: 75000,
    throughputMbps: 550,
    latencyMs: 0.10,
    costPerGbMonth: 0.08
  }),
  Object.freeze({
    name: "NVMe SSD",
    iops: 800000,
    throughputMbps: 7000,
    latencyMs: 0.025,
    costPerGbMonth: 0.15
  })
]);

class LruCache {
  constructor(capacity) {
    if (!Number.isInteger(capacity) || capacity <= 0) {
      throw new RangeError("Cache capacity must be a positive integer");
    }
    this.capacity = capacity;
    this.entries = new Map();
  }

  get(key) {
    if (!this.entries.has(key)) {
      return undefined;
    }

    const value = this.entries.get(key);
    this.entries.delete(key);
    this.entries.set(key, value);
    return value;
  }

  set(key, value) {
    if (this.entries.has(key)) {
      this.entries.delete(key);
    }

    if (this.entries.size >= this.capacity) {
      const oldest = this.entries.keys().next().value;
      this.entries.delete(oldest);
    }

    this.entries.set(key, value);
  }
}

class StoragePolicy {
  static validateWorkload({ iops, throughputMbps, capacityGb }) {
    if (!Number.isFinite(iops) || iops < 0) {
      throw new TypeError("IOPS must be a non-negative number");
    }

    if (!Number.isFinite(throughputMbps) || throughputMbps < 0) {
      throw new TypeError("Throughput must be a non-negative number");
    }

    if (!Number.isFinite(capacityGb) || capacityGb <= 0) {
      throw new TypeError("Capacity must be positive");
    }
  }

  static selectTier(requirements, maxMonthlyCost = Infinity) {
    this.validateWorkload(requirements);

    const candidates = STORAGE_TIERS.filter((tier) => {
      const monthlyCost = tier.costPerGbMonth * requirements.capacityGb;

      return (
        tier.iops >= requirements.iops &&
        tier.throughputMbps >= requirements.throughputMbps &&
        monthlyCost <= maxMonthlyCost
      );
    });

    if (candidates.length === 0) {
      throw new Error("No storage tier satisfies the supplied constraints");
    }

    return candidates.reduce((best, tier) =>
      tier.costPerGbMonth < best.costPerGbMonth ? tier : best
    );
  }

  static sustainableIops(tier, requestSizeKb) {
    if (!Number.isFinite(requestSizeKb) || requestSizeKb <= 0) {
      throw new RangeError("Request size must be positive");
    }

    const throughputLimited =
      (tier.throughputMbps * 1024) / requestSizeKb;

    return Math.min(tier.iops, throughputLimited);
  }
}

class StorageDevice {
  constructor(tier, cacheCapacity = 32) {
    this.tier = tier;
    this.cache = new LruCache(cacheCapacity);
    this.metrics = {
      requests: 0,
      reads: 0,
      writes: 0,
      cacheHits: 0,
      cacheMisses: 0,
      totalLatencyMs: 0,
      totalBytes: 0
    };
  }

  validateRequest(request) {
    if (!Number.isInteger(request.sizeKb) || request.sizeKb <= 0) {
      throw new RangeError("I/O size must be a positive integer");
    }

    if (!["read", "write"].includes(request.type)) {
      throw new TypeError("Request type must be read or write");
    }

    if (typeof request.key !== "string" || request.key.length === 0) {
      throw new TypeError("Storage key cannot be empty");
    }

    if (request.key.length > 256) {
      throw new RangeError("Storage key is too long");
    }
  }

  latencyFor(sizeKb) {
    const transferMs =
      ((sizeKb / 1024) / this.tier.throughputMbps) * 1000;

    return this.tier.latencyMs + transferMs;
  }

  async process(request) {
    this.validateRequest(request);

    this.metrics.requests += 1;
    this.metrics.totalBytes += request.sizeKb * 1024;

    if (request.type === "read") {
      this.metrics.reads += 1;

      if (this.cache.get(request.key) !== undefined) {
        this.metrics.cacheHits += 1;
        const latency = Math.max(0.05, this.tier.latencyMs * 0.10);
        this.metrics.totalLatencyMs += latency;
        return { ...request, cache: "hit", latencyMs: latency };
      }

      this.metrics.cacheMisses += 1;
      const latency = this.latencyFor(request.sizeKb);
      this.cache.set(request.key, true);
      this.metrics.totalLatencyMs += latency;

      return { ...request, cache: "miss", latencyMs: latency };
    }

    this.metrics.writes += 1;
    const latency = this.latencyFor(request.sizeKb);

    // Write-through keeps cached data consistent with the persisted object.
    this.cache.set(request.key, true);
    this.metrics.totalLatencyMs += latency;

    return { ...request, cache: "write-through", latencyMs: latency };
  }
}

function createWorkload(count) {
  if (!Number.isInteger(count) || count <= 0) {
    throw new RangeError("Workload count must be positive");
  }

  const hotKeys = Array.from({ length: 10 }, (_, i) => `customer:${i}`);
  const coldKeys = Array.from({ length: 100 }, (_, i) => `archive:${i}`);

  return Array.from({ length: count }, (_, id) => {
    const hot = Math.random() < 0.75;
    const type = Math.random() < 0.80 ? "read" : "write";
    const sizes = [4, 8, 16, 32, 64, 128];
    const sizeKb = sizes[Math.floor(Math.random() * sizes.length)];

    return {
      id,
      type,
      sizeKb,
      key: (hot ? hotKeys : coldKeys)[
        Math.floor(Math.random() * (hot ? hotKeys : coldKeys).length)
      ]
    };
  });
}

async function run() {
  const requirements = {
    iops: 120000,
    throughputMbps: 1500,
    capacityGb: 2000
  };

  const tier = StoragePolicy.selectTier(requirements);
  const monthlyCost = tier.costPerGbMonth * requirements.capacityGb;

  console.log("Selected tier:", tier.name);
  console.log(`Estimated monthly cost: $${monthlyCost.toFixed(2)}`);

  const device = new StorageDevice(tier, 32);
  const workload = createWorkload(2000);

  // Promise scheduling models independent I/O completion without introducing
  // artificial real-time delays into the educational benchmark.
  await Promise.all(workload.map((request) => device.process(request)));

  const m = device.metrics;
  const averageLatency =
    m.requests === 0 ? 0 : m.totalLatencyMs / m.requests;

  const throughput =
    m.totalLatencyMs === 0
      ? 0
      : m.totalBytes / 1024 / 1024 / (m.totalLatencyMs / 1000);

  const hitRatio =
    m.cacheHits + m.cacheMisses === 0
      ? 0
      : m.cacheHits / (m.cacheHits + m.cacheMisses);

  console.log("\nWorkload metrics");
  console.log("Requests:", m.requests);
  console.log("Reads:", m.reads);
  console.log("Writes:", m.writes);
  console.log("Cache hit ratio:", `${(hitRatio * 100).toFixed(2)}%`);
  console.log("Average latency:", `${averageLatency.toFixed(4)} ms`);
  console.log("Modeled throughput:", `${throughput.toFixed(2)} MB/s`);

  for (const sizeKb of [4, 64, 256]) {
    console.log(
      `Sustainable IOPS at ${sizeKb} KB:`,
      Math.floor(StoragePolicy.sustainableIops(tier, sizeKb))
    );
  }

  console.log("\nOperational guidance");
  console.log(
    hitRatio >= 0.70
      ? "High locality: caching is likely to reduce storage pressure."
      : "Low locality: increasing cache size may not substantially improve performance."
  );

  console.log(
    "Measure real workloads because synthetic concurrency can hide queueing and device contention."
  );
}

run().catch((error) => {
  console.error("Storage evaluation failed:", error.message);
  process.exitCode = 1;
});
