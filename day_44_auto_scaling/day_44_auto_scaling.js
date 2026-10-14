"use strict";

/*
 * Event-driven auto scaling simulator.
 *
 * Demonstrates metric ingestion, asynchronous metric collection, scaling-group
 * lifecycle events, target tracking, cooldowns, rolling windows, scheduled
 * capacity changes, policy evaluation, and an append-only audit trail.
 *
 * Run with Node.js 18 or later:
 *     node autoscaling_lab.js
 *
 * All infrastructure and metrics are simulated locally.
 */

const { EventEmitter } = require("node:events");
const { performance } = require("node:perf_hooks");

const InstanceStatus = Object.freeze({
  WARMING: "warming",
  READY: "ready",
  UNHEALTHY: "unhealthy",
});

function requireFiniteNumber(value, name, min = 0, max = Infinity) {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    value < min ||
    value > max
  ) {
    throw new RangeError(`${name} must be between ${min} and ${max}.`);
  }
  return value;
}

function normalizeMetric(raw) {
  const metric = {
    timestamp: new Date(raw.timestamp),
    cpuPercent: requireFiniteNumber(raw.cpuPercent, "CPU", 0, 100),
    requestsPerSecond: requireFiniteNumber(
      raw.requestsPerSecond,
      "request rate"
    ),
    p95LatencyMs: requireFiniteNumber(raw.p95LatencyMs, "p95 latency"),
    errorRatePercent: requireFiniteNumber(
      raw.errorRatePercent ?? 0,
      "error rate",
      0,
      100
    ),
  };

  if (Number.isNaN(metric.timestamp.getTime())) {
    throw new TypeError("Metric timestamp must be a valid date.");
  }

  return Object.freeze(metric);
}

class AuditTrail {
  #events = [];

  append(type, details, timestamp) {
    this.#events.push(
      Object.freeze({
        sequence: this.#events.length + 1,
        type,
        timestamp: timestamp.toISOString(),
        details: Object.freeze({ ...details }),
      })
    );
  }

  get events() {
    return this.#events.map((event) => ({
      ...event,
      details: { ...event.details },
    }));
  }

  filterByType(type) {
    return this.events.filter((event) => event.type === type);
  }
}

class MetricCollector extends EventEmitter {
  #lastTimestamp = null;

  ingest(rawMetric) {
    const metric = normalizeMetric(rawMetric);

    if (
      this.#lastTimestamp &&
      metric.timestamp.getTime() < this.#lastTimestamp.getTime()
    ) {
      throw new Error("Out-of-order metrics are not accepted.");
    }

    this.#lastTimestamp = metric.timestamp;
    this.emit("metric", metric);
    return metric;
  }

  // A real collector would poll a monitoring API. This deterministic method
  // models asynchronous collection without external services.
  async collectFromProvider(provider) {
    if (typeof provider !== "function") {
      throw new TypeError("Provider must be a function.");
    }

    const rawMetric = await provider();
    return this.ingest(rawMetric);
  }
}

class ScalingGroup extends EventEmitter {
  #instances = new Map();
  #nextInstanceId = 1;
  #desired;
  #lastOut = null;
  #lastIn = null;

  constructor({
    name,
    min,
    max,
    desired,
    warmupMs = 60_000,
    scaleInProtection = false,
  }) {
    super();

    if (!name || !name.trim()) {
      throw new Error("Scaling group name is required.");
    }
    if (
      !Number.isInteger(min) ||
      !Number.isInteger(max) ||
      !Number.isInteger(desired) ||
      min < 0 ||
      max < min ||
      desired < min ||
      desired > max
    ) {
      throw new RangeError("Invalid minimum, maximum, or desired capacity.");
    }
    requireFiniteNumber(warmupMs, "warm-up duration");

    this.name = name;
    this.min = min;
    this.max = max;
    this.warmupMs = warmupMs;
    this.defaultScaleInProtection = scaleInProtection;
    this.#desired = desired;
    this.audit = new AuditTrail();
  }

  get desired() {
    return this.#desired;
  }

  get actual() {
    return this.#instances.size;
  }

  get ready() {
    return [...this.#instances.values()].filter(
      (instance) => instance.status === InstanceStatus.READY
    ).length;
  }

  snapshot() {
    const counts = Object.fromEntries(
      Object.values(InstanceStatus).map((status) => [status, 0])
    );

    for (const instance of this.#instances.values()) {
      counts[instance.status] += 1;
    }

    return Object.freeze({
      name: this.name,
      min: this.min,
      max: this.max,
      desired: this.#desired,
      actual: this.actual,
      ready: this.ready,
      ...counts,
    });
  }

  reconcile(now) {
    const timestamp = new Date(now);

    for (const instance of this.#instances.values()) {
      if (
        instance.status === InstanceStatus.WARMING &&
        timestamp.getTime() >= instance.readyAt
      ) {
        instance.status = InstanceStatus.READY;
        this.audit.append(
          "instance_ready",
          { instanceId: instance.id },
          timestamp
        );
        this.emit("instanceReady", { ...instance });
      }
    }

    while (this.#instances.size < this.#desired) {
      const id = `${this.name}-${String(this.#nextInstanceId++).padStart(4, "0")}`;
      const readyAt = timestamp.getTime() + this.warmupMs;

      const instance = {
        id,
        status:
          this.warmupMs === 0
            ? InstanceStatus.READY
            : InstanceStatus.WARMING,
        launchedAt: timestamp.getTime(),
        readyAt,
        protectedFromScaleIn: this.defaultScaleInProtection,
      };

      this.#instances.set(id, instance);
      this.audit.append(
        "instance_launched",
        { instanceId: id, status: instance.status },
        timestamp
      );
      this.emit("instanceLaunched", { ...instance });
    }

    while (this.#instances.size > this.#desired) {
      const candidates = [...this.#instances.values()]
        .filter((instance) => !instance.protectedFromScaleIn)
        .sort((a, b) => a.launchedAt - b.launchedAt);

      if (candidates.length === 0) {
        this.emit("capacityBlocked", {
          reason: "all instances are protected from scale-in",
        });
        break;
      }

      const victim = candidates[0];
      this.#instances.delete(victim.id);
      this.audit.append(
        "instance_terminated",
        { instanceId: victim.id },
        timestamp
      );
      this.emit("instanceTerminated", { ...victim });
    }
  }

  setScaleInProtection(instanceId, protectedState) {
    if (typeof protectedState !== "boolean") {
      throw new TypeError("Protection state must be boolean.");
    }
    const instance = this.#instances.get(instanceId);
    if (!instance) {
      throw new Error(`Instance not found: ${instanceId}`);
    }
    instance.protectedFromScaleIn = protectedState;
  }

  markUnhealthy(instanceId, now) {
    const instance = this.#instances.get(instanceId);
    if (!instance) {
      throw new Error(`Instance not found: ${instanceId}`);
    }

    instance.status = InstanceStatus.UNHEALTHY;
    this.audit.append(
      "instance_unhealthy",
      { instanceId },
      new Date(now)
    );
    this.emit("instanceUnhealthy", { ...instance });

    this.#instances.delete(instanceId);
    // Desired capacity is unchanged, so reconciliation launches a replacement.
    this.reconcile(now);
  }

  changeCapacity(delta, now, reason) {
    if (!Number.isInteger(delta)) {
      throw new TypeError("Capacity changes must be integers.");
    }

    const oldCapacity = this.#desired;
    const nextCapacity = Math.min(
      this.max,
      Math.max(this.min, oldCapacity + delta)
    );

    if (nextCapacity === oldCapacity) {
      this.audit.append(
        "capacity_unchanged",
        { capacity: oldCapacity, reason },
        new Date(now)
      );
      return false;
    }

    this.#desired = nextCapacity;
    const action = nextCapacity > oldCapacity ? "scale_out" : "scale_in";
    const timestamp = new Date(now);

    if (action === "scale_out") {
      this.#lastOut = timestamp.getTime();
    } else {
      this.#lastIn = timestamp.getTime();
    }

    const event = {
      action,
      oldCapacity,
      newCapacity: nextCapacity,
      reason,
      timestamp: timestamp.toISOString(),
    };

    this.audit.append(action, event, timestamp);
    this.emit("capacityChanged", event);
    this.reconcile(timestamp);
    return true;
  }

  cooldownActive(direction, now, durationMs) {
    const last =
      direction === "out" ? this.#lastOut : this.#lastIn;

    return last !== null && now.getTime() - last < durationMs;
  }
}

class TargetTrackingPolicy {
  constructor({
    name,
    metric,
    target,
    scaleOutThreshold = 1.10,
    scaleInThreshold = 0.75,
    scaleOutCooldownMs = 120_000,
    scaleInCooldownMs = 180_000,
    scaleInStep = 1,
    maximumScaleOutStep = 4,
    evaluationPeriods = 2,
    windowSize = 3,
  }) {
    if (!name || !metric) {
      throw new Error("Policy name and metric are required.");
    }
    requireFiniteNumber(target, "target", Number.MIN_VALUE);
    if (!(scaleInThreshold > 0 && scaleInThreshold < 1)) {
      throw new RangeError("Scale-in threshold must be between zero and one.");
    }
    if (!(scaleOutThreshold > 1)) {
      throw new RangeError("Scale-out threshold must exceed one.");
    }
    if (
      !Number.isInteger(evaluationPeriods) ||
      evaluationPeriods < 1 ||
      !Number.isInteger(windowSize) ||
      windowSize < 1
    ) {
      throw new RangeError("Evaluation periods and window size must be positive.");
    }

    this.name = name;
    this.metric = metric;
    this.target = target;
    this.scaleOutThreshold = scaleOutThreshold;
    this.scaleInThreshold = scaleInThreshold;
    this.scaleOutCooldownMs = scaleOutCooldownMs;
    this.scaleInCooldownMs = scaleInCooldownMs;
    this.scaleInStep = scaleInStep;
    this.maximumScaleOutStep = maximumScaleOutStep;
    this.evaluationPeriods = evaluationPeriods;
    this.windowSize = windowSize;
    this.samples = [];
    this.outBreaches = 0;
    this.inBreaches = 0;
  }

  evaluate(metric, group) {
    const metricKey = {
      cpu: "cpuPercent",
      requests: "requestsPerSecond",
      latency: "p95LatencyMs",
      errors: "errorRatePercent",
    }[this.metric];

    if (!metricKey) {
      throw new Error(`Unsupported policy metric: ${this.metric}`);
    }

    this.samples.push(metric[metricKey]);
    if (this.samples.length > this.windowSize) {
      this.samples.shift();
    }

    const average =
      this.samples.reduce((sum, value) => sum + value, 0) /
      this.samples.length;
    const ratio = average / this.target;
    const now = metric.timestamp;

    if (ratio >= this.scaleOutThreshold) {
      this.outBreaches += 1;
      this.inBreaches = 0;
    } else if (ratio <= this.scaleInThreshold) {
      this.inBreaches += 1;
      this.outBreaches = 0;
    } else {
      this.outBreaches = 0;
      this.inBreaches = 0;
      return { decision: "hold", average, ratio };
    }

    if (this.outBreaches >= this.evaluationPeriods) {
      if (
        group.cooldownActive("out", now, this.scaleOutCooldownMs)
      ) {
        return { decision: "cooldown", direction: "out", average, ratio };
      }

      const delta = Math.min(
        this.maximumScaleOutStep,
        Math.max(1, Math.ceil(group.desired * (ratio - 1)))
      );
      this.outBreaches = 0;
      group.changeCapacity(
        delta,
        now,
        `${this.name}: average ${this.metric} ratio ${ratio.toFixed(2)}`
      );
      return { decision: "scale_out", delta, average, ratio };
    }

    if (this.inBreaches >= this.evaluationPeriods) {
      if (
        group.cooldownActive("in", now, this.scaleInCooldownMs)
      ) {
        return { decision: "cooldown", direction: "in", average, ratio };
      }

      this.inBreaches = 0;
      const changed = group.changeCapacity(
        -this.scaleInStep,
        now,
        `${this.name}: sustained low ${this.metric}`
      );
      return {
        decision: changed ? "scale_in" : "capacity_limit",
        average,
        ratio,
      };
    }

    return { decision: "evaluate_again", average, ratio };
  }
}

class ScheduledScalingPolicy {
  constructor(actions) {
    this.actions = [...actions]
      .map((action) => ({
        ...action,
        at: new Date(action.at),
      }))
      .sort((a, b) => a.at.getTime() - b.at.getTime());

    for (const action of this.actions) {
      if (
        Number.isNaN(action.at.getTime()) ||
        !Number.isInteger(action.desired) ||
        typeof action.name !== "string"
      ) {
        throw new TypeError("Invalid scheduled scaling action.");
      }
    }

    this.executed = new Set();
  }

  applyDueActions(group, now) {
    const timestamp = new Date(now);
    const results = [];

    for (const action of this.actions) {
      if (
        !this.executed.has(action.name) &&
        timestamp >= action.at
      ) {
        if (action.desired < group.min || action.desired > group.max) {
          results.push({ action: action.name, result: "invalid_capacity" });
          continue;
        }

        group.changeCapacity(
          action.desired - group.desired,
          timestamp,
          `scheduled: ${action.name}`
        );
        this.executed.add(action.name);
        results.push({ action: action.name, result: "applied" });
      }
    }

    return results;
  }
}

function estimateMonthlyComputeCost(instanceHours, hourlyRate) {
  requireFiniteNumber(instanceHours, "instance hours");
  requireFiniteNumber(hourlyRate, "hourly rate");
  return instanceHours * hourlyRate;
}

function displaySnapshot(group, decision, metric) {
  const snapshot = group.snapshot();
  console.log(
    `${metric.timestamp.toISOString()} | CPU=${metric.cpuPercent}% | ` +
    `p95=${metric.p95LatencyMs}ms | desired=${snapshot.desired} | ` +
    `ready=${snapshot.ready} | decision=${decision.decision}`
  );
}

async function main() {
  const started = performance.now();
  const now = new Date("2026-10-14T08:00:00.000Z");

  const group = new ScalingGroup({
    name: "orders-service",
    min: 2,
    max: 12,
    desired: 2,
    warmupMs: 60_000,
  });

  group.on("capacityChanged", (event) => {
    console.log(
      `  CAPACITY EVENT: ${event.oldCapacity} -> ${event.newCapacity}; ` +
      `${event.reason}`
    );
  });

  group.on("instanceReady", (instance) => {
    console.log(`  INSTANCE READY: ${instance.id}`);
  });

  group.reconcile(now);

  const collector = new MetricCollector();
  const policy = new TargetTrackingPolicy({
    name: "orders-cpu-target",
    metric: "cpu",
    target: 55,
    evaluationPeriods: 2,
    windowSize: 2,
  });

  collector.on("metric", (metric) => {
    group.reconcile(metric.timestamp);
    const decision = policy.evaluate(metric, group);
    displaySnapshot(group, decision, metric);
  });

  const scheduled = new ScheduledScalingPolicy([
    {
      name: "business-hours-capacity",
      at: "2026-10-14T09:00:00.000Z",
      desired: 5,
    },
  ]);

  console.log("EVENT-DRIVEN AUTO SCALING SIMULATION");
  console.log("===================================");

  const samples = [
    { seconds: 0, cpu: 40, requests: 140, latency: 150 },
    { seconds: 60, cpu: 64, requests: 230, latency: 240 },
    { seconds: 120, cpu: 76, requests: 320, latency: 350 },
    { seconds: 180, cpu: 83, requests: 390, latency: 410 },
    { seconds: 240, cpu: 51, requests: 240, latency: 230 },
    { seconds: 300, cpu: 35, requests: 150, latency: 150 },
    { seconds: 360, cpu: 29, requests: 110, latency: 115 },
    { seconds: 420, cpu: 25, requests: 90, latency: 100 },
  ];

  for (const sample of samples) {
    const timestamp = new Date(now.getTime() + sample.seconds * 1000);

    scheduled.applyDueActions(group, timestamp);

    // The asynchronous provider models a monitoring service returning a sample.
    await collector.collectFromProvider(async () => ({
      timestamp,
      cpuPercent: sample.cpu,
      requestsPerSecond: sample.requests,
      p95LatencyMs: sample.latency,
      errorRatePercent: sample.cpu > 80 ? 1.5 : 0.2,
    }));
  }

  console.log("\nScheduled action execution");
  console.log(
    scheduled.applyDueActions(group, new Date("2026-10-14T09:01:00.000Z"))
  );

  console.log("\nHealth replacement");
  const failedInstance = `orders-service-0001`;
  if (group.snapshot().actual > 0) {
    group.markUnhealthy(
      failedInstance,
      new Date("2026-10-14T09:02:00.000Z")
    );
  }

  console.log("\nFinal state");
  console.log(JSON.stringify(group.snapshot(), null, 2));

  console.log("\nAudit event counts");
  for (const type of [
    "scale_out",
    "scale_in",
    "instance_launched",
    "instance_ready",
    "instance_unhealthy",
    "instance_terminated",
  ]) {
    console.log(`${type}: ${group.audit.filterByType(type).length}`);
  }

  const illustrativeMonthlyCost = estimateMonthlyComputeCost(
    group.actual * 24 * 30,
    0.048
  );
  console.log(
    `Illustrative monthly compute cost: $${illustrativeMonthlyCost.toFixed(2)}`
  );
  console.log(`Simulation duration: ${(performance.now() - started).toFixed(2)} ms`);

  try {
    normalizeMetric({
      timestamp: "not-a-date",
      cpuPercent: 150,
      requestsPerSecond: -5,
      p95LatencyMs: 100,
    });
  } catch (error) {
    console.log(`Validation example: ${error.message}`);
  }
}

main().catch((error) => {
  console.error("Simulation failed:", error.message);
  process.exitCode = 1;
});
