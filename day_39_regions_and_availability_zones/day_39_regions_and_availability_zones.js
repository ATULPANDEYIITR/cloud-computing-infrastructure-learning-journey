"use strict";

/*
 * Event-driven model of regional infrastructure, zone failures, and failover.
 * Execute with Node.js 18 or later. No external packages are required.
 */

const { EventEmitter } = require("node:events");
const assert = require("node:assert/strict");

const ZoneStatus = Object.freeze({
  HEALTHY: "healthy",
  DEGRADED: "degraded",
  DOWN: "down"
});

class AvailabilityZone {
  constructor({ id, regionId, failureDomain, capacity = 100, latencyMs = 5 }) {
    if (!id || !regionId || !failureDomain) {
      throw new TypeError("Zone identity, region, and failure domain are required.");
    }
    if (!Number.isInteger(capacity) || capacity < 0) {
      throw new RangeError("Capacity must be a non-negative integer.");
    }
    if (!Number.isFinite(latencyMs) || latencyMs < 0) {
      throw new RangeError("Latency must be a finite non-negative number.");
    }

    this.id = id;
    this.regionId = regionId;
    this.failureDomain = failureDomain;
    this.capacity = capacity;
    this.latencyMs = latencyMs;
    this.status = ZoneStatus.HEALTHY;
    this.allocations = new Map();
  }

  get usedCapacity() {
    return [...this.allocations.values()].reduce((sum, count) => sum + count, 0);
  }

  get availableCapacity() {
    if (this.status === ZoneStatus.DOWN) return 0;
    const free = Math.max(0, this.capacity - this.usedCapacity);
    return this.status === ZoneStatus.DEGRADED ? Math.floor(free / 2) : free;
  }

  allocate(workloadId, replicas) {
    if (this.status !== ZoneStatus.HEALTHY) {
      throw new Error(`Cannot allocate workload to non-healthy zone ${this.id}.`);
    }
    if (!Number.isInteger(replicas) || replicas < 1) {
      throw new RangeError("Replica allocation must be a positive integer.");
    }
    if (replicas > this.availableCapacity) {
      throw new Error(`Insufficient capacity in ${this.id}.`);
    }
    this.allocations.set(
      workloadId,
      (this.allocations.get(workloadId) || 0) + replicas
    );
  }

  setStatus(status) {
    if (!Object.values(ZoneStatus).includes(status)) {
      throw new TypeError(`Unknown zone status: ${status}`);
    }
    this.status = status;
  }
}

class Region {
  constructor({ id, name, residencyGroup }) {
    if (!id || !name || !residencyGroup) {
      throw new TypeError("Region fields cannot be empty.");
    }
    this.id = id;
    this.name = name;
    this.residencyGroup = residencyGroup;
    this.zones = new Map();
  }

  addZone(zone) {
    if (zone.regionId !== this.id) {
      throw new Error("A zone cannot be registered in a different region.");
    }
    if (this.zones.has(zone.id)) {
      throw new Error(`Duplicate zone: ${zone.id}`);
    }
    this.zones.set(zone.id, zone);
  }
}

class Workload {
  constructor({ id, replicaCount, minimumHealthy, regionId }) {
    if (!id || !regionId) throw new TypeError("Workload identity is required.");
    if (!Number.isInteger(replicaCount) || replicaCount < 1) {
      throw new RangeError("replicaCount must be positive.");
    }
    if (!Number.isInteger(minimumHealthy) ||
        minimumHealthy < 1 ||
        minimumHealthy > replicaCount) {
      throw new RangeError("minimumHealthy must be between one and replicaCount.");
    }

    this.id = id;
    this.replicaCount = replicaCount;
    this.minimumHealthy = minimumHealthy;
    this.regionId = regionId;
    this.placements = new Map();
  }

  healthyReplicas(zoneLookup) {
    let healthy = 0;
    for (const [zoneId, count] of this.placements) {
      const zone = zoneLookup(zoneId);
      if (zone && zone.status === ZoneStatus.HEALTHY) healthy += count;
    }
    return healthy;
  }

  isAvailable(zoneLookup) {
    return this.healthyReplicas(zoneLookup) >= this.minimumHealthy;
  }
}

class RegionalControlPlane extends EventEmitter {
  constructor() {
    super();
    this.regions = new Map();
    this.workloads = new Map();
    this.auditLog = [];
  }

  addRegion(region) {
    if (this.regions.has(region.id)) throw new Error("Duplicate region.");
    this.regions.set(region.id, region);
  }

  findZone(zoneId) {
    for (const region of this.regions.values()) {
      if (region.zones.has(zoneId)) return region.zones.get(zoneId);
    }
    return undefined;
  }

  addWorkload(workload) {
    if (this.workloads.has(workload.id)) throw new Error("Duplicate workload.");
    if (!this.regions.has(workload.regionId)) {
      throw new Error("Workload region is not registered.");
    }
    this.workloads.set(workload.id, workload);
  }

  place(workloadId, zoneIds) {
    const workload = this.workloads.get(workloadId);
    if (!workload) throw new Error("Unknown workload.");
    if (!Array.isArray(zoneIds) || zoneIds.length !== workload.replicaCount) {
      throw new Error("Placement must contain the configured number of replicas.");
    }
    if (new Set(zoneIds).size !== zoneIds.length) {
      throw new Error("Each replica must use a distinct zone.");
    }

    const zones = zoneIds.map((id) => {
      const zone = this.findZone(id);
      if (!zone) throw new Error(`Unknown zone: ${id}`);
      if (zone.regionId !== workload.regionId) {
        throw new Error("Regional placement cannot cross region boundaries.");
      }
      if (zone.status !== ZoneStatus.HEALTHY) {
        throw new Error(`Zone ${id} is not healthy.`);
      }
      return zone;
    });

    // Preflight every capacity check before applying allocations.
    if (zones.some((zone) => zone.availableCapacity < 1)) {
      throw new Error("One or more zones lack capacity.");
    }

    zones.forEach((zone) => zone.allocate(workloadId, 1));
    workload.placements = new Map(zoneIds.map((id) => [id, 1]));

    this.record("placement_completed", {
      workloadId,
      zones: [...zoneIds]
    });
  }

  record(type, details) {
    const event = Object.freeze({
      type,
      details: structuredClone(details),
      timestamp: new Date().toISOString()
    });
    this.auditLog.push(event);
    this.emit(type, event);
  }

  async changeZoneStatus(zoneId, status) {
    const zone = this.findZone(zoneId);
    if (!zone) throw new Error(`Unknown zone: ${zoneId}`);

    const previous = zone.status;
    zone.setStatus(status);
    this.record("zone_status_changed", {
      zoneId,
      previous,
      current: status
    });

    const affected = [];
    for (const workload of this.workloads.values()) {
      if (workload.placements.has(zoneId)) {
        const healthy = workload.healthyReplicas((id) => this.findZone(id));
        const available = workload.isAvailable((id) => this.findZone(id));
        const result = { workloadId: workload.id, healthy, available };
        affected.push(result);

        // In production, failover would include readiness checks, fencing,
        // traffic draining, idempotency, and capacity reservations.
        if (!available) {
          this.record("workload_availability_lost", result);
        }
      }
    }

    return { zoneId, status, affected };
  }

  selectFailoverZones(regionId, count, excludedIds = new Set()) {
    const region = this.regions.get(regionId);
    if (!region) throw new Error(`Unknown region: ${regionId}`);
    if (!Number.isInteger(count) || count < 1) {
      throw new RangeError("Requested zone count must be positive.");
    }

    const candidates = [...region.zones.values()]
      .filter((zone) =>
        zone.status === ZoneStatus.HEALTHY &&
        zone.availableCapacity > 0 &&
        !excludedIds.has(zone.id)
      )
      .sort((a, b) => a.latencyMs - b.latencyMs);

    const selected = [];
    const usedDomains = new Set();

    for (const zone of candidates) {
      // Avoid known shared failure domains when choosing replicas.
      if (usedDomains.has(zone.failureDomain)) continue;
      selected.push(zone);
      usedDomains.add(zone.failureDomain);
      if (selected.length === count) return selected;
    }

    throw new Error("Insufficient independent healthy zones for placement.");
  }

  report() {
    return {
      regions: [...this.regions.values()].map((region) => ({
        id: region.id,
        name: region.name,
        zones: [...region.zones.values()].map((zone) => ({
          id: zone.id,
          status: zone.status,
          capacity: zone.capacity,
          usedCapacity: zone.usedCapacity,
          failureDomain: zone.failureDomain,
          latencyMs: zone.latencyMs
        }))
      })),
      workloads: [...this.workloads.values()].map((workload) => ({
        id: workload.id,
        placements: Object.fromEntries(workload.placements),
        healthyReplicas: workload.healthyReplicas((id) => this.findZone(id)),
        available: workload.isAvailable((id) => this.findZone(id))
      }))
    };
  }
}

function createExample() {
  const control = new RegionalControlPlane();
  const india = new Region({
    id: "ap-south",
    name: "South Asia",
    residencyGroup: "IN"
  });

  [
    { id: "zone-a", failureDomain: "power-a", latencyMs: 4 },
    { id: "zone-b", failureDomain: "power-b", latencyMs: 6 },
    { id: "zone-c", failureDomain: "power-c", latencyMs: 8 }
  ].forEach((configuration) => {
    india.addZone(new AvailabilityZone({
      ...configuration,
      regionId: india.id,
      capacity: 12
    }));
  });

  control.addRegion(india);
  control.addWorkload(new Workload({
    id: "checkout-service",
    replicaCount: 3,
    minimumHealthy: 2,
    regionId: "ap-south"
  }));

  const selected = control.selectFailoverZones("ap-south", 3);
  control.place("checkout-service", selected.map((zone) => zone.id));
  return control;
}

async function main() {
  const control = createExample();

  control.on("workload_availability_lost", (event) => {
    process.stderr.write(`ALERT ${JSON.stringify(event.details)}\n`);
  });

  console.log("Initial topology");
  console.log(JSON.stringify(control.report(), null, 2));

  console.log("\nZone outage simulation");
  console.log(JSON.stringify(
    await control.changeZoneStatus("zone-a", ZoneStatus.DOWN),
    null,
    2
  ));

  console.log("\nRecovery");
  await control.changeZoneStatus("zone-a", ZoneStatus.HEALTHY);
  console.log(JSON.stringify(control.report(), null, 2));

  assert.equal(
    control.workloads.get("checkout-service")
      .healthyReplicas((id) => control.findZone(id)),
    3
  );

  assert.throws(
    () => control.place("checkout-service", ["zone-a", "zone-a", "zone-c"]),
    /distinct zone/
  );

  console.log(`\nAudit events recorded: ${control.auditLog.length}`);
  console.log("Validation passed.");
}

main().catch((error) => {
  console.error(`Infrastructure simulation failed: ${error.message}`);
  process.exitCode = 1;
});
