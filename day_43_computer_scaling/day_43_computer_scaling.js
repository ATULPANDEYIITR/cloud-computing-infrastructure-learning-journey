"use strict";

/*
 * Compute Scaling Simulator
 *
 * Demonstrates workload forecasting, vertical and horizontal scaling,
 * event-driven scaling decisions, cooldown behavior, resource bottlenecks,
 * and constrained capacity planning in Node.js.
 *
 * Run with:
 *   node compute-scaling.js
 *
 * Capacities and prices are illustrative. Production sizing requires
 * measurements from the actual application and its dependencies.
 */

const { performance } = require("node:perf_hooks");

class ValidationError extends Error {
  constructor(message) {
    super(message);
    this.name = "ValidationError";
  }
}

function requireFiniteNumber(name, value, minimum = 0) {
  if (!Number.isFinite(value) || value < minimum) {
    throw new ValidationError(
      `${name} must be a finite number greater than or equal to ${minimum}`
    );
  }
}

function percentile(values, q) {
  if (!Array.isArray(values) || values.length === 0) {
    throw new ValidationError("At least one traffic observation is required");
  }
  if (!Number.isFinite(q) || q < 0 || q > 1) {
    throw new ValidationError("Percentile must be between zero and one");
  }

  const sorted = values.map((value) => {
    requireFiniteNumber("traffic observation", value);
    return value;
  }).sort((a, b) => a - b);

  const position = (sorted.length - 1) * q;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  const fraction = position - lower;

  return sorted[lower] + (sorted[upper] - sorted[lower]) * fraction;
}

class WorkloadProfile {
  constructor({
    name,
    rps,
    cpuCoresPerRequest,
    memoryGiBPerReplica,
    connectionsPerReplica,
    networkGbpsPerReplica,
  }) {
    if (!name || !name.trim()) {
      throw new ValidationError("Workload name is required");
    }

    requireFiniteNumber("rps", rps);
    requireFiniteNumber("cpuCoresPerRequest", cpuCoresPerRequest, Number.EPSILON);
    requireFiniteNumber("memoryGiBPerReplica", memoryGiBPerReplica, Number.EPSILON);
    requireFiniteNumber("connectionsPerReplica", connectionsPerReplica);
    requireFiniteNumber("networkGbpsPerReplica", networkGbpsPerReplica);

    Object.assign(this, {
      name,
      rps,
      cpuCoresPerRequest,
      memoryGiBPerReplica,
      connectionsPerReplica,
      networkGbpsPerReplica,
    });

    Object.freeze(this);
  }
}

class ComputeInstance {
  constructor({
    name,
    vcpus,
    memoryGiB,
    maxConnections,
    networkGbps,
    hourlyCost,
  }) {
    if (!name || !name.trim()) {
      throw new ValidationError("Instance name is required");
    }

    requireFiniteNumber("vcpus", vcpus, 1);
    requireFiniteNumber("memoryGiB", memoryGiB, Number.EPSILON);
    requireFiniteNumber("maxConnections", maxConnections, 1);
    requireFiniteNumber("networkGbps", networkGbps, Number.EPSILON);
    requireFiniteNumber("hourlyCost", hourlyCost);

    Object.assign(this, {
      name,
      vcpus,
      memoryGiB,
      maxConnections,
      networkGbps,
      hourlyCost,
    });

    Object.freeze(this);
  }
}

const PROFILE = Object.freeze({
  cpuTarget: 0.65,
  memoryTarget: 0.75,
  connectionTarget: 0.70,
  networkTarget: 0.70,
  requestsPerCoreSecond: 1.0,
  safetyFactor: 1.25,
});

const CATALOG = Object.freeze([
  new ComputeInstance({
    name: "api-small",
    vcpus: 2,
    memoryGiB: 4,
    maxConnections: 500,
    networkGbps: 1,
    hourlyCost: 0.08,
  }),
  new ComputeInstance({
    name: "api-medium",
    vcpus: 4,
    memoryGiB: 8,
    maxConnections: 1500,
    networkGbps: 2,
    hourlyCost: 0.16,
  }),
  new ComputeInstance({
    name: "api-large",
    vcpus: 8,
    memoryGiB: 16,
    maxConnections: 3000,
    networkGbps: 5,
    hourlyCost: 0.32,
  }),
  new ComputeInstance({
    name: "api-xlarge",
    vcpus: 16,
    memoryGiB: 32,
    maxConnections: 6000,
    networkGbps: 10,
    hourlyCost: 0.64,
  }),
]);

function forecastWorkload(observations, growthRate, safetyFactor = 1.2) {
  requireFiniteNumber("growthRate", growthRate);
  if (!Number.isFinite(safetyFactor) || safetyFactor < 1) {
    throw new ValidationError("Safety factor must be at least one");
  }

  const mean = observations.reduce((sum, value) => {
    requireFiniteNumber("traffic observation", value);
    return sum + value;
  }, 0) / observations.length;

  const p95 = percentile(observations, 0.95);
  const peak = Math.max(...observations);

  return Object.freeze({
    meanRps: mean,
    p95Rps: p95,
    peakRps: peak,
    growthAdjustedP95Rps: p95 * (1 + growthRate),
    planningRps: p95 * (1 + growthRate) * safetyFactor,
  });
}

function instanceCapacity(instance, profile = PROFILE) {
  const limits = {
    cpu: (
      instance.vcpus
      * profile.requestsPerCoreSecond
      * profile.cpuTarget
    ),
    memory: (
      instance.memoryGiB
      * profile.memoryTarget
    ),
    connections: instance.maxConnections * profile.connectionTarget,
    network: instance.networkGbps * profile.networkTarget,
  };

  return Object.freeze({
    limits,
    bottleneck: Object.keys(limits).filter(
      (key) => limits[key] === Math.min(...Object.values(limits))
    ),
  });
}

function evaluate(instance, replicas, workload, profile = PROFILE) {
  if (!Number.isInteger(replicas) || replicas < 1) {
    throw new ValidationError("Replicas must be a positive integer");
  }

  const rawCapacity = instanceCapacity(instance, profile);
  const limits = {
    cpu: rawCapacity.limits.cpu / (
      workload.cpuCoresPerRequest * profile.safetyFactor
    ),
    memory: rawCapacity.limits.memory / workload.memoryGiBPerReplica,
    connections: rawCapacity.limits.connections / Math.max(
      workload.connectionsPerReplica, 1
    ),
    network: rawCapacity.limits.network / Math.max(
      workload.networkGbpsPerReplica, 0.001
    ),
  };

  const perReplicaRps = Math.min(...Object.values(limits));
  const totalCapacity = perReplicaRps * replicas;

  const cpuDemand = workload.rps * workload.cpuCoresPerRequest;
  const cpuUtilization = cpuDemand / (instance.vcpus * replicas);
  const memoryUtilization = (
    workload.memoryGiBPerReplica / instance.memoryGiB
  );
  const connectionUtilization = (
    workload.connectionsPerReplica / instance.maxConnections
  );
  const networkUtilization = (
    workload.networkGbpsPerReplica / instance.networkGbps
  );

  const failures = [];
  if (workload.rps > totalCapacity) failures.push("throughput");
  if (cpuUtilization > profile.cpuTarget) failures.push("cpu");
  if (memoryUtilization > profile.memoryTarget) failures.push("memory");
  if (connectionUtilization > profile.connectionTarget) failures.push("connections");
  if (networkUtilization > profile.networkTarget) failures.push("network");

  return Object.freeze({
    instance: instance.name,
    replicas,
    requestedRps: workload.rps,
    capacityRps: totalCapacity,
    hourlyCost: instance.hourlyCost * replicas,
    monthlyComputeCost: instance.hourlyCost * replicas * 730,
    utilization: {
      cpu: cpuUtilization,
      memory: memoryUtilization,
      connections: connectionUtilization,
      network: networkUtilization,
    },
    bottlenecks: rawCapacity.bottleneck,
    failures,
    feasible: failures.length === 0,
  });
}

function planVertical(workload, currentReplicas, catalog = CATALOG) {
  // Vertical scaling changes per-instance resources while preserving replicas.
  const ordered = [...catalog].sort((a, b) => a.hourlyCost - b.hourlyCost);

  return ordered
    .map((instance) => evaluate(instance, currentReplicas, workload))
    .find((decision) => decision.feasible) ?? null;
}

function planHorizontal(workload, instance, minReplicas = 2, maxReplicas = 20) {
  if (!Number.isInteger(minReplicas) || minReplicas < 1) {
    throw new ValidationError("Minimum replicas must be a positive integer");
  }
  if (!Number.isInteger(maxReplicas) || maxReplicas < minReplicas) {
    throw new ValidationError("Maximum replicas must be at least the minimum");
  }

  // Horizontal scaling changes instance count without requiring a larger type.
  for (let replicas = minReplicas; replicas <= maxReplicas; replicas += 1) {
    const decision = evaluate(instance, replicas, workload);
    if (decision.feasible) return decision;
  }
  return null;
}

class ScalingController {
  #replicas;
  #lastActionAt = -Infinity;
  #listeners = new Map();

  constructor({
    replicas = 2,
    minimum = 2,
    maximum = 20,
    scaleOut = 0.70,
    scaleIn = 0.30,
    cooldownMs = 120_000,
  } = {}) {
    if (!Number.isInteger(replicas) || replicas < minimum || replicas > maximum) {
      throw new ValidationError("Initial replicas must be within configured limits");
    }
    if (!(0 < scaleIn && scaleIn < scaleOut && scaleOut <= 1)) {
      throw new ValidationError("Invalid scale-in and scale-out thresholds");
    }
    requireFiniteNumber("cooldownMs", cooldownMs);

    Object.assign(this, { minimum, maximum, scaleOut, scaleIn, cooldownMs });
    this.#replicas = replicas;
  }

  get replicas() {
    return this.#replicas;
  }

  on(eventName, listener) {
    if (typeof listener !== "function") {
      throw new ValidationError("Event listener must be a function");
    }
    const listeners = this.#listeners.get(eventName) ?? new Set();
    listeners.add(listener);
    this.#listeners.set(eventName, listeners);

    // Return an unsubscribe function so monitoring subscriptions do not leak.
    return () => listeners.delete(listener);
  }

  #emit(eventName, detail) {
    for (const listener of this.#listeners.get(eventName) ?? []) {
      listener(Object.freeze(detail));
    }
  }

  observe({ utilization, timestampMs }) {
    requireFiniteNumber("utilization", utilization);
    requireFiniteNumber("timestampMs", timestampMs);

    if (timestampMs < this.#lastActionAt) {
      throw new ValidationError("Observations cannot move backward in time");
    }

    if (timestampMs - this.#lastActionAt < this.cooldownMs) {
      return "cooldown";
    }

    let action = "stable";

    if (utilization > this.scaleOut && this.#replicas < this.maximum) {
      this.#replicas += 1;
      action = "scale-out";
    } else if (
      utilization < this.scaleIn
      && this.#replicas > this.minimum
    ) {
      this.#replicas -= 1;
      action = "scale-in";
    } else if (utilization > this.scaleOut) {
      action = "maximum-reached";
    } else if (utilization < this.scaleIn) {
      action = "minimum-reached";
    }

    if (action === "scale-out" || action === "scale-in") {
      this.#lastActionAt = timestampMs;
      this.#emit("scaled", {
        action,
        replicas: this.#replicas,
        utilization,
        timestampMs,
      });
    }

    return action;
  }
}

async function runConcurrentLoadSimulation({
  requests,
  concurrency,
  serviceTimeMs,
}) {
  if (!Number.isInteger(requests) || requests < 0) {
    throw new ValidationError("Requests must be a non-negative integer");
  }
  if (!Number.isInteger(concurrency) || concurrency < 1) {
    throw new ValidationError("Concurrency must be a positive integer");
  }
  requireFiniteNumber("serviceTimeMs", serviceTimeMs);

  let completed = 0;
  const startedAt = performance.now();

  // A bounded worker pool prevents an unbounded Promise.all allocation.
  async function worker() {
    while (true) {
      const requestNumber = completed;
      completed += 1;
      if (requestNumber >= requests) return;

      await new Promise((resolve) => setTimeout(resolve, serviceTimeMs));
    }
  }

  const workerCount = Math.min(concurrency, requests);
  await Promise.all(Array.from({ length: workerCount }, () => worker()));

  const elapsedSeconds = (performance.now() - startedAt) / 1000;
  return {
    completed: Math.min(completed, requests),
    elapsedSeconds,
    measuredRps: elapsedSeconds > 0 ? requests / elapsedSeconds : 0,
  };
}

function printDecision(title, decision) {
  console.log(`\n${title}`);
  if (!decision) {
    console.log("No feasible deployment within the configured limits.");
    return;
  }

  console.log(JSON.stringify(decision, null, 2));
}

async function main() {
  const traffic = [
    100, 110, 120, 150, 190, 220, 260, 300,
    350, 390, 420, 480, 520, 500, 460, 400,
    360, 320, 280, 240, 200, 170, 140, 120,
  ];

  const forecast = forecastWorkload(traffic, 0.25, 1.2);
  console.log("Traffic forecast");
  console.log(JSON.stringify(forecast, null, 2));

  const workload = new WorkloadProfile({
    name: "inventory-api",
    rps: forecast.planningRps,
    cpuCoresPerRequest: 0.06,
    memoryGiBPerReplica: 1.5,
    connectionsPerReplica: 250,
    networkGbpsPerReplica: 0.12,
  });

  printDecision("Vertical scaling", planVertical(workload, 2));
  printDecision("Horizontal scaling", planHorizontal(workload, CATALOG[1]));

  console.log("\nEvent-driven autoscaling");
  const controller = new ScalingController({
    replicas: 3,
    minimum: 2,
    maximum: 8,
    cooldownMs: 60_000,
  });

  const unsubscribe = controller.on("scaled", (event) => {
    console.log("Scaling event:", event);
  });

  for (const [timestampMs, utilization] of [
    [0, 0.80],
    [30_000, 0.92],
    [65_000, 0.91],
    [130_000, 0.15],
    [200_000, 0.12],
  ]) {
    const action = controller.observe({ utilization, timestampMs });
    console.log({ timestampMs, utilization, action, replicas: controller.replicas });
  }

  unsubscribe();

  console.log("\nBounded asynchronous load simulation");
  const simulation = await runConcurrentLoadSimulation({
    requests: 20,
    concurrency: 4,
    serviceTimeMs: 5,
  });
  console.log(simulation);

  console.log("\nAssertions");
  const tinyWorkload = new WorkloadProfile({
    name: "tiny-api",
    rps: 1,
    cpuCoresPerRequest: 0.01,
    memoryGiBPerReplica: 0.5,
    connectionsPerReplica: 10,
    networkGbpsPerReplica: 0.01,
  });

  if (!planVertical(tinyWorkload, 1)) {
    throw new Error("Expected a feasible vertical plan");
  }
  if (percentile([10, 20, 30], 0) !== 10) {
    throw new Error("Minimum percentile calculation failed");
  }
  if (percentile([10, 20, 30], 1) !== 30) {
    throw new Error("Maximum percentile calculation failed");
  }

  const impossible = new WorkloadProfile({
    name: "impossible-api",
    rps: 1_000_000,
    cpuCoresPerRequest: 1,
    memoryGiBPerReplica: 1000,
    connectionsPerReplica: 1_000_000,
    networkGbpsPerReplica: 1000,
  });

  if (planVertical(impossible, 1) !== null) {
    throw new Error("An impossible vertical plan should not be returned");
  }
  if (planHorizontal(impossible, CATALOG[0], 2, 3) !== null) {
    throw new Error("An impossible horizontal plan should not be returned");
  }

  console.log("All assertions passed.");
}

main().catch((error) => {
  console.error(`${error.name}: ${error.message}`);
  process.exitCode = 1;
});
