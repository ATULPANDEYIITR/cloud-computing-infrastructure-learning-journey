"use strict";

/*
 * Event-driven cloud VM deployment workflow.
 * Run with Node.js 18 or later: node cloud-vm-deployment.js
 *
 * This is a local simulation. It does not call a cloud provider or create
 * actual infrastructure.
 */

const { EventEmitter } = require("node:events");
const { createHash, randomUUID } = require("node:crypto");

const STATES = Object.freeze({
  PENDING: "pending",
  RUNNING: "running",
  STOPPED: "stopped",
  FAILED: "failed",
  TERMINATED: "terminated",
});

const TRANSITIONS = Object.freeze({
  pending: new Set(["running", "failed", "terminated"]),
  running: new Set(["stopped", "failed", "terminated"]),
  stopped: new Set(["running", "terminated"]),
  failed: new Set(["terminated"]),
  terminated: new Set(),
});

class DeploymentError extends Error {}
class PolicyViolation extends DeploymentError {}
class InvalidTransition extends DeploymentError {}

function assertNonEmpty(value, field) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new PolicyViolation(`${field} must be a non-empty string.`);
  }
}

function validateImage(image, architecture, diskGiB) {
  if (!image || image.status !== "available" || !image.trusted) {
    throw new PolicyViolation("The selected image is unavailable or untrusted.");
  }
  if (image.architecture !== architecture) {
    throw new PolicyViolation("Machine and image architectures differ.");
  }
  if (!Number.isInteger(diskGiB) || diskGiB < image.minimumDiskGiB) {
    throw new PolicyViolation("The root disk is too small.");
  }
}

function parseCidr(cidr) {
  const match = /^(\d{1,3}(?:\.\d{1,3}){3})\/(\d|[12]\d|3[0-2])$/.exec(cidr);
  if (!match) throw new PolicyViolation(`Invalid IPv4 CIDR: ${cidr}`);

  const octets = match[1].split(".").map(Number);
  if (octets.some((octet) => octet < 0 || octet > 255)) {
    throw new PolicyViolation(`Invalid IPv4 address: ${match[1]}`);
  }

  const address = octets.reduce((value, octet) => (value * 256 + octet) >>> 0, 0);
  const prefix = Number(match[2]);
  const mask = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0;

  return { network: address & mask, mask, prefix };
}

function ipInCidr(ip, cidr) {
  const parsed = parseCidr(cidr);
  const octets = ip.split(".").map(Number);
  if (
    octets.length !== 4 ||
    octets.some((part) => !Number.isInteger(part) || part < 0 || part > 255)
  ) {
    return false;
  }

  const address = octets.reduce((value, octet) => (value * 256 + octet) >>> 0, 0);
  return (address & parsed.mask) === parsed.network;
}

class SecurityGroup {
  constructor(name, rules = []) {
    assertNonEmpty(name, "Security group name");
    this.name = name;
    this.rules = [...rules];
    this.validate();
  }

  validate() {
    for (const rule of this.rules) {
      if (!["tcp", "udp"].includes(rule.protocol)) {
        throw new PolicyViolation("Only TCP and UDP rules are supported here.");
      }
      if (
        !Number.isInteger(rule.fromPort) ||
        !Number.isInteger(rule.toPort) ||
        rule.fromPort < 1 ||
        rule.toPort > 65535 ||
        rule.fromPort > rule.toPort
      ) {
        throw new PolicyViolation("Invalid port range.");
      }
      parseCidr(rule.cidr);

      // Prevent accidentally exposing SSH to all IPv4 addresses.
      const network = parseCidr(rule.cidr);
      if (
        rule.protocol === "tcp" &&
        rule.fromPort <= 22 &&
        rule.toPort >= 22 &&
        network.prefix === 0
      ) {
        throw new PolicyViolation("SSH must not be open to 0.0.0.0/0.");
      }
    }
  }

  allows(protocol, port, sourceIp) {
    return this.rules.some(
      (rule) =>
        rule.protocol === protocol &&
        port >= rule.fromPort &&
        port <= rule.toPort &&
        ipInCidr(sourceIp, rule.cidr)
    );
  }
}

class AuditLog {
  constructor() {
    this.entries = [];
  }

  append(event) {
    // Structured records make operational failures queryable and testable.
    this.entries.push(Object.freeze({
      id: randomUUID(),
      timestamp: new Date().toISOString(),
      ...event,
    }));
  }

  findByInstance(instanceId) {
    return this.entries.filter((entry) => entry.instanceId === instanceId);
  }
}

class VirtualMachine extends EventEmitter {
  constructor(configuration) {
    super();
    this.id = `vm-${randomUUID().slice(0, 12)}`;
    this.name = configuration.name;
    this.region = configuration.region;
    this.imageId = configuration.image.id;
    this.machineType = configuration.machineType;
    this.diskGiB = configuration.diskGiB;
    this.sshKeyFingerprint = configuration.sshKeyFingerprint;
    this.securityGroup = configuration.securityGroup;
    this.tags = Object.freeze({ ...configuration.tags });
    this.state = STATES.PENDING;
    this.publicIp = null;
    this.revision = 0;
    this.createdAt = new Date().toISOString();
  }

  transition(target, details = {}) {
    const permitted = TRANSITIONS[this.state];
    if (!permitted || !permitted.has(target)) {
      throw new InvalidTransition(`Cannot transition ${this.state} to ${target}.`);
    }

    const previous = this.state;
    this.state = target;
    this.revision += 1;

    // Consumers can react to lifecycle events without coupling provisioning
    // logic to billing, notifications, or audit persistence.
    this.emit("stateChanged", {
      instanceId: this.id,
      previous,
      current: target,
      revision: this.revision,
      ...details,
    });
  }
}

class CloudDeploymentService extends EventEmitter {
  constructor() {
    super();
    this.images = new Map();
    this.keys = new Map();
    this.groups = new Map();
    this.instances = new Map();
    this.audit = new AuditLog();
  }

  registerImage(image) {
    assertNonEmpty(image.id, "Image ID");
    if (this.images.has(image.id)) throw new PolicyViolation("Duplicate image ID.");
    this.images.set(image.id, Object.freeze({ ...image }));
  }

  registerPublicKey(name, publicKey) {
    assertNonEmpty(name, "SSH key name");
    const fields = publicKey.trim().split(/\s+/);
    if (
      fields.length < 2 ||
      !["ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256"].includes(fields[0])
    ) {
      throw new PolicyViolation("Malformed or unsupported SSH public key.");
    }

    // Store a fingerprint rather than requiring the deployment service to
    // retain or transmit private key material.
    const fingerprint = createHash("sha256")
      .update(fields[1], "base64")
      .digest("hex");

    if (this.keys.has(name) && this.keys.get(name) !== fingerprint) {
      throw new PolicyViolation("SSH key name is already registered.");
    }
    this.keys.set(name, fingerprint);
  }

  registerSecurityGroup(group) {
    group.validate();
    this.groups.set(group.name, group);
  }

  record(instance, action, details = {}) {
    const event = {
      instanceId: instance.id,
      action,
      state: instance.state,
      revision: instance.revision,
      details,
    };
    this.audit.append(event);
    this.emit("audit", event);
  }

  async create(configuration) {
    assertNonEmpty(configuration.name, "Instance name");
    assertNonEmpty(configuration.region, "Region");

    if (!/^[a-zA-Z][a-zA-Z0-9-]{0,39}$/.test(configuration.name)) {
      throw new PolicyViolation("Invalid instance name.");
    }
    if (!Number.isInteger(configuration.diskGiB) || configuration.diskGiB < 8) {
      throw new PolicyViolation("Root disk must be at least 8 GiB.");
    }

    const image = this.images.get(configuration.imageId);
    const fingerprint = this.keys.get(configuration.sshKeyName);
    const group = this.groups.get(configuration.securityGroupName);

    if (!image) throw new PolicyViolation("Unknown image.");
    if (!fingerprint) throw new PolicyViolation("Unknown SSH key.");
    if (!group) throw new PolicyViolation("Unknown security group.");

    validateImage(image, configuration.machineType.architecture, configuration.diskGiB);

    const duplicate = [...this.instances.values()].some(
      (vm) => vm.name === configuration.name && vm.state !== STATES.TERMINATED
    );
    if (duplicate) throw new PolicyViolation("An active instance has this name.");

    const vm = new VirtualMachine({
      ...configuration,
      image,
      sshKeyFingerprint: fingerprint,
      securityGroup: group,
    });

    vm.on("stateChanged", (event) => {
      this.record(vm, "state_changed", event);
    });
    this.instances.set(vm.id, vm);
    this.record(vm, "creation_requested");

    // Yield to the event loop to model asynchronous provisioning.
    await new Promise((resolve) => setImmediate(resolve));

    if (configuration.simulateBootFailure) {
      vm.transition(STATES.FAILED, { reason: "image_boot_failure" });
      return vm;
    }

    vm.publicIp = "192.0.2.20"; // Reserved documentation address, not a real host.
    vm.transition(STATES.RUNNING, { reason: "boot_completed" });
    return vm;
  }

  getInstance(id) {
    const vm = this.instances.get(id);
    if (!vm) throw new PolicyViolation("Instance not found.");
    return vm;
  }

  stop(id) {
    const vm = this.getInstance(id);
    vm.transition(STATES.STOPPED);
    vm.publicIp = null;
    return vm;
  }

  async start(id) {
    const vm = this.getInstance(id);
    vm.transition(STATES.RUNNING, { reason: "start_requested" });
    await new Promise((resolve) => setImmediate(resolve));
    vm.publicIp = "192.0.2.21";
    return vm;
  }

  terminate(id) {
    const vm = this.getInstance(id);
    vm.transition(STATES.TERMINATED);
    vm.publicIp = null;
    return vm;
  }

  monthlyComputeEstimate(id, hours = 730) {
    const vm = this.getInstance(id);
    if (!Number.isFinite(hours) || hours < 0) {
      throw new PolicyViolation("Hours must be a non-negative finite number.");
    }
    // Stopped-instance compute billing is zero in this simplified model.
    return vm.state === STATES.RUNNING
      ? Number((vm.machineType.hourlyCost * hours).toFixed(2))
      : 0;
  }
}

async function main() {
  const service = new CloudDeploymentService();

  service.on("audit", (event) => {
    console.log(`[audit] ${event.action}: ${event.instanceId} (${event.state})`);
  });

  service.registerImage({
    id: "ubuntu-2404",
    status: "available",
    trusted: true,
    architecture: "x86_64",
    minimumDiskGiB: 8,
  });

  service.registerPublicKey(
    "platform-admin",
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGV4YW1wbGVwdWJsaWNrZXlkYXRh admin"
  );

  service.registerSecurityGroup(new SecurityGroup("staging-web", [
    { protocol: "tcp", fromPort: 22, toPort: 22, cidr: "203.0.113.8/32" },
    { protocol: "tcp", fromPort: 443, toPort: 443, cidr: "0.0.0.0/0" },
  ]));

  const vm = await service.create({
    name: "staging-api",
    region: "us-east-1",
    imageId: "ubuntu-2404",
    machineType: { name: "general.small", architecture: "x86_64", hourlyCost: 0.0416 },
    diskGiB: 20,
    sshKeyName: "platform-admin",
    securityGroupName: "staging-web",
    tags: { environment: "staging", owner: "platform" },
  });

  console.log("Running:", vm.state);
  console.log("SSH from approved address:",
    vm.securityGroup.allows("tcp", 22, "203.0.113.8"));
  console.log("SSH from other address:",
    vm.securityGroup.allows("tcp", 22, "198.51.100.9"));
  console.log("Estimated compute cost:", service.monthlyComputeEstimate(vm.id));

  service.stop(vm.id);
  console.log("Stopped:", vm.state);
  await service.start(vm.id);
  console.log("Restarted:", vm.state);
  service.terminate(vm.id);
  console.log("Terminated:", vm.state);

  try {
    service.stop(vm.id);
  } catch (error) {
    console.log("Expected lifecycle rejection:", error.message);
  }

  try {
    new SecurityGroup("unsafe", [
      { protocol: "tcp", fromPort: 22, toPort: 22, cidr: "0.0.0.0/0" },
    ]);
  } catch (error) {
    console.log("Expected security-policy rejection:", error.message);
  }

  console.log("Audit events for VM:", service.audit.findByInstance(vm.id).length);
}

main().catch((error) => {
  console.error("Deployment failed:", error.message);
  process.exitCode = 1;
});
