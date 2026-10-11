"use strict";

/*
 * Cloud compute sizing and lifecycle model.
 * Run with Node.js 18 or later. No cloud credentials or dependencies required.
 */

const { EventEmitter } = require("node:events");
const { randomUUID } = require("node:crypto");

const InstanceState = Object.freeze({
  STOPPED: "stopped",
  RUNNING: "running",
  TERMINATED: "terminated",
});

const instanceCatalog = Object.freeze([
  Object.freeze({
    name: "general.small",
    family: "general",
    vcpus: 2,
    memoryGiB: 4,
    architecture: "x86_64",
    networkGbps: 1,
    hourlyRate: 0.025,
    workloads: ["web", "general"],
    burstable: false,
  }),
  Object.freeze({
    name: "compute.large",
    family: "compute",
    vcpus: 8,
    memoryGiB: 16,
    architecture: "x86_64",
    networkGbps: 10,
    hourlyRate: 0.12,
    workloads: ["compute", "general"],
    burstable: false,
  }),
  Object.freeze({
    name: "memory.large",
    family: "memory",
    vcpus: 4,
    memoryGiB: 32,
    architecture: "x86_64",
    networkGbps: 10,
    hourlyRate: 0.15,
    workloads: ["memory", "general"],
    burstable: false,
  }),
  Object.freeze({
    name: "arm.compute",
    family: "compute",
    vcpus: 8,
    memoryGiB: 16,
    architecture: "arm64",
    networkGbps: 10,
    hourlyRate: 0.095,
    workloads: ["compute", "general"],
    burstable: false,
  }),
  Object.freeze({
    name: "general.burst",
    family: "general",
    vcpus: 2,
    memoryGiB: 4,
    architecture: "x86_64",
    networkGbps: 1,
    hourlyRate: 0.012,
    workloads: ["web", "general"],
    burstable: true,
  }),
]);

function validateWorkload(workload) {
  if (!workload || typeof workload !== "object") {
    throw new TypeError("A workload object is required.");
  }
  if (!Number.isInteger(workload.vcpus) || workload.vcpus < 1) {
    throw new RangeError("Workload vCPU requirement must be a positive integer.");
  }
  if (!Number.isFinite(workload.memoryGiB) || workload.memoryGiB <= 0) {
    throw new RangeError("Workload memory must be positive and finite.");
  }
  if (!Number.isFinite(workload.minimumNetworkGbps ?? 0)
      || (workload.minimumNetworkGbps ?? 0) < 0) {
    throw new RangeError("Minimum network throughput cannot be negative.");
  }
  if (!["x86_64", "arm64"].includes(workload.architecture)) {
    throw new RangeError("Unsupported workload architecture.");
  }
}

function recommendInstanceTypes(workload, catalog = instanceCatalog) {
  validateWorkload(workload);

  return catalog
    .filter((item) =>
      item.architecture === workload.architecture
      && item.workloads.includes(workload.kind)
      && item.vcpus >= workload.vcpus
      && item.memoryGiB >= workload.memoryGiB
      && item.networkGbps >= (workload.minimumNetworkGbps ?? 0)
      && (!item.burstable || workload.allowBurstable === true)
      && (workload.maximumHourlyRate === undefined
        || item.hourlyRate <= workload.maximumHourlyRate))
    .toSorted((a, b) =>
      a.hourlyRate - b.hourlyRate
      || a.memoryGiB - b.memoryGiB
      || a.vcpus - b.vcpus);
}

function estimateMonthlyCost(hourlyRate, hoursPerDay = 24, days = 30) {
  if (!Number.isFinite(hourlyRate) || hourlyRate < 0) {
    throw new RangeError("Hourly rate must be finite and nonnegative.");
  }
  if (!Number.isFinite(hoursPerDay) || hoursPerDay < 0 || hoursPerDay > 24) {
    throw new RangeError("Hours per day must be between zero and 24.");
  }
  if (!Number.isInteger(days) || days < 1 || days > 366) {
    throw new RangeError("Days must be an integer between 1 and 366.");
  }

  return hourlyRate * hoursPerDay * days;
}

function validateImage(image) {
  if (!image || !image.id || !image.owner) {
    throw new TypeError("Image ID and owner are required.");
  }
  if (!["x86_64", "arm64"].includes(image.architecture)) {
    throw new RangeError("Unsupported image architecture.");
  }
  if (!Number.isInteger(image.rootDiskGiB) || image.rootDiskGiB < 8) {
    throw new RangeError("Image root disk must be at least 8 GiB.");
  }
  if (image.trusted !== true || image.encrypted !== true) {
    throw new Error("Image must be trusted and encrypted.");
  }
}

class Instance extends EventEmitter {
  #state = InstanceState.STOPPED;

  constructor(instanceType, image, tags = {}) {
    super();
    if (!instanceType || !image) {
      throw new TypeError("Instance type and machine image are required.");
    }

    this.id = `i-${randomUUID()}`;
    this.type = instanceType;
    this.image = Object.freeze({ ...image });
    this.tags = Object.freeze({ ...tags });
  }

  get state() {
    return this.#state;
  }

  #transition(nextState) {
    const previousState = this.#state;
    this.#state = nextState;

    // Event listeners can observe state changes without controlling transitions.
    this.emit("stateChanged", {
      instanceId: this.id,
      previousState,
      nextState,
      occurredAt: new Date().toISOString(),
    });
  }

  start() {
    if (this.#state === InstanceState.TERMINATED) {
      throw new Error("Terminated instances cannot be started.");
    }
    if (this.#state === InstanceState.RUNNING) {
      return false;
    }

    validateImage(this.image);
    if (this.type.architecture !== this.image.architecture) {
      throw new Error("Machine image and instance architecture do not match.");
    }

    this.#transition(InstanceState.RUNNING);
    return true;
  }

  stop() {
    if (this.#state !== InstanceState.RUNNING) {
      throw new Error("Only running instances can be stopped.");
    }

    this.#transition(InstanceState.STOPPED);
  }

  terminate() {
    if (this.#state === InstanceState.TERMINATED) {
      throw new Error("Instance is already terminated.");
    }

    this.#transition(InstanceState.TERMINATED);
  }
}

function demonstrateAsyncProvisioning(workload, image) {
  return new Promise((resolve, reject) => {
    // Queue provisioning work asynchronously, as a cloud control-plane client might.
    setImmediate(() => {
      try {
        const recommendations = recommendInstanceTypes(workload);
        if (recommendations.length === 0) {
          throw new Error("No compatible instance type is available.");
        }

        const instance = new Instance(recommendations[0], image, {
          service: workload.name,
          managedBy: "capacity-planner",
        });

        instance.on("stateChanged", (event) => {
          console.log(
            `Event: ${event.instanceId} ${event.previousState} -> ${event.nextState}`,
          );
        });

        instance.start();
        resolve({ instance, recommendations });
      } catch (error) {
        reject(error);
      }
    });
  });
}

async function main() {
  console.log("Cloud compute capacity planner");
  console.log("==============================");

  const workload = {
    name: "monthly-report-service",
    kind: "compute",
    vcpus: 4,
    memoryGiB: 8,
    minimumNetworkGbps: 2,
    architecture: "x86_64",
    allowBurstable: false,
  };

  const image = {
    id: "img-linux-2026-10",
    owner: "organization-image-team",
    architecture: "x86_64",
    rootDiskGiB: 30,
    trusted: true,
    encrypted: true,
  };

  const recommendations = recommendInstanceTypes(workload);
  console.log("\nCompatible instance types:");
  for (const item of recommendations) {
    console.log(
      `${item.name}: ${item.vcpus} vCPU, ${item.memoryGiB} GiB, `
      + `${item.networkGbps} Gbps, $${item.hourlyRate.toFixed(3)}/hour`,
    );
  }

  if (recommendations.length > 0) {
    console.log(
      `Monthly compute estimate: $${estimateMonthlyCost(
        recommendations[0].hourlyRate,
      ).toFixed(2)}`,
    );
  }

  const burstableWorkload = {
    ...workload,
    name: "development-preview",
    kind: "web",
    vcpus: 1,
    memoryGiB: 2,
    allowBurstable: true,
  };
  console.log("\nBurstable development choices:");
  console.log(
    recommendInstanceTypes(burstableWorkload).map((item) => item.name).join(", ")
      || "No compatible types",
  );

  const { instance } = await demonstrateAsyncProvisioning(workload, image);
  console.log(`\nInstance ${instance.id} is ${instance.state}.`);
  instance.stop();
  instance.start();
  instance.terminate();
  console.log(`Final state: ${instance.state}`);

  try {
    instance.start();
  } catch (error) {
    console.log(`Expected lifecycle error: ${error.message}`);
  }

  try {
    validateImage({ ...image, architecture: "arm64" });
    const incompatible = new Instance(recommendations[0], {
      ...image,
      architecture: "arm64",
    });
    incompatible.start();
  } catch (error) {
    console.log(`Expected image validation error: ${error.message}`);
  }

  try {
    estimateMonthlyCost(0.12, 25, 30);
  } catch (error) {
    console.log(`Expected billing validation error: ${error.message}`);
  }

  console.log("\nCapacity planning distinctions:");
  console.log("- vCPU count describes virtual compute capacity, not fixed performance.");
  console.log("- Memory-intensive workloads need RAM headroom, not just more CPU.");
  console.log("- Machine images determine boot software and architecture compatibility.");
  console.log("- Catalog prices are illustrative; actual prices vary by region and contract.");
}

main().catch((error) => {
  console.error(`Provisioning demonstration failed: ${error.message}`);
  process.exitCode = 1;
});
