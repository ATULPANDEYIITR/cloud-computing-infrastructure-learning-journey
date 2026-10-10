"use strict";

/*
 * Virtual Infrastructure Project
 *
 * An event-driven control-plane model for virtual machine provisioning,
 * network allocation, storage attachment, access control, and environment
 * isolation.
 *
 * Run with:
 *   node virtual-infrastructure.js
 *
 * This program simulates infrastructure operations. It does not invoke
 * a real hypervisor, cloud provider, or network controller.
 */

const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");
const assert = require("node:assert/strict");

class InfrastructureError extends Error {}
class AuthorizationError extends InfrastructureError {}
class CapacityError extends InfrastructureError {}
class InvalidStateError extends InfrastructureError {}
class NotFoundError extends InfrastructureError {}

const VMState = Object.freeze({
  PROVISIONING: "provisioning",
  STOPPED: "stopped",
  RUNNING: "running",
  SUSPENDED: "suspended",
  TERMINATED: "terminated",
});

const Role = Object.freeze({
  VIEWER: "viewer",
  OPERATOR: "operator",
  ADMIN: "admin",
});

const Permissions = Object.freeze({
  [Role.VIEWER]: new Set(["read"]),
  [Role.OPERATOR]: new Set(["read", "operate"]),
  [Role.ADMIN]: new Set(["read", "operate", "admin"]),
});

function validateIdentifier(value, field = "identifier") {
  if (
    typeof value !== "string" ||
    !/^[A-Za-z][A-Za-z0-9_-]{1,62}$/.test(value)
  ) {
    throw new TypeError(`${field} must be a valid infrastructure identifier`);
  }
  return value;
}

function requirePositiveInteger(value, field) {
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new TypeError(`${field} must be a positive safe integer`);
  }
}

class AsyncMutex {
  constructor() {
    this.tail = Promise.resolve();
  }

  /*
   * Serializing asynchronous mutations prevents two concurrent provisioning
   * operations from both observing the same available capacity.
   *
   * This is process-local coordination, not a distributed lock.
   */
  async runExclusive(operation) {
    const previous = this.tail;
    let release;
    this.tail = new Promise((resolve) => {
      release = resolve;
    });

    await previous;
    try {
      return await operation();
    } finally {
      release();
    }
  }
}

class InfrastructureEnvironment {
  constructor({ id, name, quota }) {
    this.id = validateIdentifier(id, "environment id");
    this.name = name;
    this.quota = Object.freeze({ ...quota });
    this.vmIds = new Set();
    this.networkIds = new Set();
    this.poolIds = new Set();
    this.state = "active";

    for (const field of ["maxVMs", "maxVcpus", "maxMemoryMB", "maxStorageGB"]) {
      requirePositiveInteger(this.quota[field], field);
    }
  }
}

class VirtualNetwork {
  constructor({ id, environmentId, cidr, gateway, vlanId }) {
    this.id = validateIdentifier(id, "network id");
    this.environmentId = environmentId;
    this.cidr = cidr;
    this.gateway = gateway;
    this.vlanId = vlanId;
    this.allocations = new Map();
    this.reservedAddresses = new Set([gateway]);

    if (!/^(\d{1,3}\.){3}\d{1,3}\/\d{1,2}$/.test(cidr)) {
      throw new TypeError("This demonstration accepts IPv4 CIDR notation");
    }
    if (!Number.isInteger(vlanId) || vlanId < 1 || vlanId > 4094) {
      throw new RangeError("VLAN ID must be between 1 and 4094");
    }

    this.subnet = parseIPv4Cidr(cidr);
    if (!containsIPv4(this.subnet, gateway)) {
      throw new RangeError("Gateway must belong to the subnet");
    }
  }

  allocate(vmId) {
    if (this.allocations.has(vmId)) {
      return this.allocations.get(vmId);
    }

    const { network, broadcast } = this.subnet;
    for (let address = network + 1; address < broadcast; address += 1) {
      const candidate = ipv4FromNumber(address);
      if (
        candidate !== this.gateway &&
        !this.reservedAddresses.has(candidate) &&
        ![...this.allocations.values()].includes(candidate)
      ) {
        this.allocations.set(vmId, candidate);
        return candidate;
      }
    }

    throw new CapacityError(`Network ${this.id} has no free host addresses`);
  }

  release(vmId) {
    this.allocations.delete(vmId);
  }
}

function parseIPv4Cidr(cidr) {
  const [address, prefixText] = cidr.split("/");
  const octets = address.split(".").map(Number);
  const prefix = Number(prefixText);

  if (
    octets.length !== 4 ||
    octets.some((part) => !Number.isInteger(part) || part < 0 || part > 255) ||
    !Number.isInteger(prefix) ||
    prefix < 16 ||
    prefix > 30
  ) {
    throw new RangeError("CIDR must be a valid IPv4 subnet with prefix /16 to /30");
  }

  const ip = octets.reduce((result, part) => result * 256 + part, 0);
  const size = 2 ** (32 - prefix);
  const network = Math.floor(ip / size) * size;

  if (ip !== network) {
    throw new RangeError("CIDR address must identify the subnet boundary");
  }

  return { network, broadcast: network + size - 1, prefix };
}

function containsIPv4(subnet, address) {
  const number = address.split(".").map(Number).reduce(
    (result, part) => result * 256 + part,
    0
  );
  return (
    number > subnet.network &&
    number < subnet.broadcast &&
    address.split(".").length === 4
  );
}

function ipv4FromNumber(number) {
  return [
    Math.floor(number / 16777216) % 256,
    Math.floor(number / 65536) % 256,
    Math.floor(number / 256) % 256,
    number % 256,
  ].join(".");
}

class StoragePool {
  constructor({ id, environmentId, capacityGB }) {
    requirePositiveInteger(capacityGB, "capacityGB");
    this.id = validateIdentifier(id, "storage pool id");
    this.environmentId = environmentId;
    this.capacityGB = capacityGB;
    this.volumes = new Map();
  }

  get usedGB() {
    return [...this.volumes.values()].reduce((sum, volume) => sum + volume.sizeGB, 0);
  }

  get availableGB() {
    return this.capacityGB - this.usedGB;
  }
}

class VirtualMachine {
  constructor({ id, environmentId, name, vcpus, memoryMB, image, networkId, ip }) {
    this.id = validateIdentifier(id, "VM id");
    this.environmentId = environmentId;
    this.name = name;
    this.vcpus = vcpus;
    this.memoryMB = memoryMB;
    this.image = image;
    this.networkId = networkId;
    this.ip = ip;
    this.state = VMState.STOPPED;
    this.volumeIds = new Set();
    this.createdAt = new Date().toISOString();
  }

  transition(action) {
    const transitions = {
      start: {
        from: [VMState.STOPPED, VMState.SUSPENDED],
        to: VMState.RUNNING,
      },
      stop: {
        from: [VMState.RUNNING],
        to: VMState.STOPPED,
      },
      suspend: {
        from: [VMState.RUNNING],
        to: VMState.SUSPENDED,
      },
      terminate: {
        from: [VMState.STOPPED, VMState.RUNNING, VMState.SUSPENDED],
        to: VMState.TERMINATED,
      },
    };

    const transition = transitions[action];
    if (!transition || !transition.from.includes(this.state)) {
      throw new InvalidStateError(
        `Cannot ${action} VM ${this.id} from ${this.state}`
      );
    }

    const previousState = this.state;
    this.state = transition.to;
    return { previousState, newState: this.state };
  }
}

class InfrastructureController extends EventEmitter {
  constructor() {
    super();
    this.users = new Map();
    this.environments = new Map();
    this.networks = new Map();
    this.pools = new Map();
    this.vms = new Map();
    this.volumes = new Map();
    this.audit = [];
    this.mutex = new AsyncMutex();

    // Event listeners receive immutable snapshots, not mutable internal objects.
    this.on("infrastructure.audit", (event) => {
      this.audit.push(Object.freeze({ ...event }));
    });
  }

  record(actor, action, resourceId, outcome, details = {}) {
    this.emit("infrastructure.audit", {
      timestamp: new Date().toISOString(),
      actor,
      action,
      resourceId,
      outcome,
      details: Object.freeze({ ...details }),
    });
  }

  addUser(username, role) {
    validateIdentifier(username, "username");
    if (!Object.hasOwn(Permissions, role)) {
      throw new TypeError("Unsupported role");
    }
    if (this.users.has(username)) {
      throw new InfrastructureError("User already exists");
    }

    this.users.set(username, {
      username,
      role,
      enabled: true,
      environmentIds: new Set(),
    });
  }

  authorize(actor, permission, environmentId = null) {
    const user = this.users.get(actor);
    if (!user || !user.enabled) {
      throw new AuthorizationError("Unknown or disabled user");
    }
    if (!Permissions[user.role].has(permission)) {
      throw new AuthorizationError(
        `${user.role} does not have ${permission} permission`
      );
    }
    if (
      environmentId &&
      !user.environmentIds.has(environmentId) &&
      user.role !== Role.ADMIN
    ) {
      throw new AuthorizationError("User is not authorized for this environment");
    }
    return user;
  }

  createEnvironment(actor, configuration) {
    this.authorize(actor, "admin");
    const environment = new InfrastructureEnvironment(configuration);

    if (this.environments.has(environment.id)) {
      throw new InfrastructureError("Environment already exists");
    }

    this.environments.set(environment.id, environment);
    this.users.get(actor).environmentIds.add(environment.id);
    this.record(actor, "create_environment", environment.id, "success");
    return environment;
  }

  grantAccess(actor, username, environmentId) {
    this.authorize(actor, "admin");
    const user = this.users.get(username);
    const environment = this.environments.get(environmentId);

    if (!user || !environment) {
      throw new NotFoundError("User or environment not found");
    }

    user.environmentIds.add(environmentId);
    this.record(actor, "grant_access", environmentId, "success", { username });
  }

  createNetwork(actor, configuration) {
    this.authorize(actor, "admin", configuration.environmentId);
    const environment = this.environments.get(configuration.environmentId);
    if (!environment || environment.state !== "active") {
      throw new NotFoundError("Active environment not found");
    }

    const network = new VirtualNetwork(configuration);
    if (this.networks.has(network.id)) {
      throw new InfrastructureError("Network already exists");
    }

    for (const existing of this.networks.values()) {
      if (existing.subnet.prefix === network.subnet.prefix) {
        // Compare full subnet ranges, not just textual CIDR equality.
        if (
          existing.subnet.network <= network.subnet.broadcast &&
          network.subnet.network <= existing.subnet.broadcast
        ) {
          throw new InfrastructureError("Network overlaps an existing subnet");
        }
      } else if (
        existing.subnet.network <= network.subnet.broadcast &&
        network.subnet.network <= existing.subnet.broadcast
      ) {
        throw new InfrastructureError("Network overlaps an existing subnet");
      }
    }

    this.networks.set(network.id, network);
    environment.networkIds.add(network.id);
    this.record(actor, "create_network", network.id, "success");
    return network;
  }

  createStoragePool(actor, configuration) {
    this.authorize(actor, "admin", configuration.environmentId);
    const environment = this.environments.get(configuration.environmentId);
    if (!environment || environment.state !== "active") {
      throw new NotFoundError("Active environment not found");
    }

    const pool = new StoragePool(configuration);
    if (this.pools.has(pool.id)) {
      throw new InfrastructureError("Storage pool already exists");
    }

    const allocated = [...environment.poolIds].reduce(
      (total, id) => total + this.pools.get(id).capacityGB,
      0
    );
    if (allocated + pool.capacityGB > environment.quota.maxStorageGB) {
      throw new CapacityError("Environment storage quota exceeded");
    }

    this.pools.set(pool.id, pool);
    environment.poolIds.add(pool.id);
    this.record(actor, "create_storage_pool", pool.id, "success");
    return pool;
  }

  async createVM(actor, configuration) {
    return this.mutex.runExclusive(async () => {
      const {
        environmentId, id, name, vcpus, memoryMB, image, networkId,
      } = configuration;

      this.authorize(actor, "operate", environmentId);
      const environment = this.environments.get(environmentId);
      const network = this.networks.get(networkId);

      if (!environment || environment.state !== "active") {
        throw new NotFoundError("Active environment not found");
      }
      if (!network || !environment.networkIds.has(networkId)) {
        throw new InfrastructureError("Network belongs to another environment");
      }
      if (this.vms.has(id)) {
        throw new InfrastructureError("VM ID already exists");
      }

      requirePositiveInteger(vcpus, "vcpus");
      requirePositiveInteger(memoryMB, "memoryMB");
      if (vcpus > 128 || memoryMB < 128) {
        throw new RangeError("VM resources are outside supported limits");
      }
      if (typeof image !== "string" || !image.trim() || image.length > 256) {
        throw new TypeError("Invalid VM image reference");
      }

      const liveVMs = [...environment.vmIds]
        .map((vmId) => this.vms.get(vmId))
        .filter((vm) => vm && vm.state !== VMState.TERMINATED);

      if (liveVMs.length >= environment.quota.maxVMs) {
        throw new CapacityError("VM quota exceeded");
      }
      if (liveVMs.reduce((total, vm) => total + vm.vcpus, 0) + vcpus >
          environment.quota.maxVcpus) {
        throw new CapacityError("vCPU quota exceeded");
      }
      if (liveVMs.reduce((total, vm) => total + vm.memoryMB, 0) + memoryMB >
          environment.quota.maxMemoryMB) {
        throw new CapacityError("Memory quota exceeded");
      }

      let ip;
      try {
        ip = network.allocate(id);
        const vm = new VirtualMachine({
          ...configuration,
          ip,
        });

        this.vms.set(id, vm);
        environment.vmIds.add(id);
        this.record(actor, "create_vm", id, "success", { ip });
        return vm;
      } catch (error) {
        network.release(id);
        this.record(actor, "create_vm", id, "failure", {
          message: error.message,
        });
        throw error;
      }
    });
  }

  changeVMState(actor, vmId, action) {
    const vm = this.vms.get(vmId);
    if (!vm) {
      throw new NotFoundError(`VM ${vmId} does not exist`);
    }

    this.authorize(actor, "operate", vm.environmentId);
    const result = vm.transition(action);

    if (action === "terminate") {
      this.networks.get(vm.networkId).release(vm.id);
      vm.ip = null;
      for (const volumeId of vm.volumeIds) {
        const volume = this.volumes.get(volumeId);
        if (volume) volume.attachedVMId = null;
      }
      vm.volumeIds.clear();
    }

    this.record(actor, action, vmId, "success", result);
    return result;
  }

  async createVolume(actor, configuration) {
    return this.mutex.runExclusive(async () => {
      this.authorize(actor, "operate", configuration.environmentId);
      const environment = this.environments.get(configuration.environmentId);
      const pool = this.pools.get(configuration.poolId);

      if (!environment || !pool || !environment.poolIds.has(pool.id)) {
        throw new InfrastructureError("Storage pool is outside the environment");
      }
      if (this.volumes.has(configuration.id)) {
        throw new InfrastructureError("Volume ID already exists");
      }

      requirePositiveInteger(configuration.sizeGB, "sizeGB");

      const currentVolumes = [...this.volumes.values()].filter(
        (volume) => volume.environmentId === environment.id
      );
      const used = [...environment.poolIds].reduce(
        (total, id) => total + this.pools.get(id).usedGB,
        0
      );

      if (used + configuration.sizeGB > environment.quota.maxStorageGB) {
        throw new CapacityError("Environment storage quota exceeded");
      }
      if (configuration.sizeGB > pool.availableGB) {
        throw new CapacityError("Storage pool capacity exceeded");
      }

      const volume = {
        id: validateIdentifier(configuration.id, "volume id"),
        environmentId: environment.id,
        poolId: pool.id,
        sizeGB: configuration.sizeGB,
        encrypted: configuration.encrypted !== false,
        attachedVMId: null,
        createdAt: new Date().toISOString(),
      };

      pool.volumes.set(volume.id, volume);
      this.volumes.set(volume.id, volume);
      this.record(actor, "create_volume", volume.id, "success", {
        sizeGB: volume.sizeGB,
        existingVolumes: currentVolumes.length,
      });
      return volume;
    });
  }

  attachVolume(actor, vmId, volumeId) {
    const vm = this.vms.get(vmId);
    const volume = this.volumes.get(volumeId);

    if (!vm || !volume) {
      throw new NotFoundError("VM or volume not found");
    }
    this.authorize(actor, "operate", vm.environmentId);

    if (vm.state === VMState.TERMINATED) {
      throw new InvalidStateError("Cannot attach a volume to a terminated VM");
    }
    if (vm.environmentId !== volume.environmentId) {
      throw new AuthorizationError("Cross-environment attachment is prohibited");
    }
    if (volume.attachedVMId !== null) {
      throw new InfrastructureError("Volume is already attached");
    }

    volume.attachedVMId = vmId;
    vm.volumeIds.add(volumeId);
    this.record(actor, "attach_volume", volumeId, "success", { vmId });
  }

  deleteVolume(actor, volumeId) {
    const volume = this.volumes.get(volumeId);
    if (!volume) throw new NotFoundError("Volume not found");

    this.authorize(actor, "operate", volume.environmentId);
    if (volume.attachedVMId !== null) {
      throw new InvalidStateError("Detach the volume before deleting it");
    }

    this.pools.get(volume.poolId).volumes.delete(volumeId);
    this.volumes.delete(volumeId);
    this.record(actor, "delete_volume", volumeId, "success");
  }

  inventory(actor, environmentId) {
    this.authorize(actor, "read", environmentId);
    const environment = this.environments.get(environmentId);
    if (!environment) throw new NotFoundError("Environment not found");

    const vms = [...environment.vmIds]
      .map((id) => this.vms.get(id))
      .filter((vm) => vm && vm.state !== VMState.TERMINATED);

    return {
      environment: environment.name,
      vms: vms.map((vm) => ({
        id: vm.id,
        name: vm.name,
        state: vm.state,
        vcpus: vm.vcpus,
        memoryMB: vm.memoryMB,
        networkId: vm.networkId,
        ip: vm.ip,
        volumeIds: [...vm.volumeIds],
      })),
      runningVMs: vms.filter((vm) => vm.state === VMState.RUNNING).length,
      allocatedVcpus: vms.reduce((total, vm) => total + vm.vcpus, 0),
      allocatedMemoryMB: vms.reduce((total, vm) => total + vm.memoryMB, 0),
      storage: [...environment.poolIds].map((id) => {
        const pool = this.pools.get(id);
        return {
          id,
          capacityGB: pool.capacityGB,
          usedGB: pool.usedGB,
          availableGB: pool.availableGB,
        };
      }),
    };
  }
}

async function runTests() {
  const controller = new InfrastructureController();
  controller.addUser("cloud_admin", Role.ADMIN);
  controller.addUser("developer", Role.OPERATOR);
  controller.addUser("auditor", Role.VIEWER);

  controller.createEnvironment("cloud_admin", {
    id: "engineering",
    name: "Engineering Sandbox",
    quota: {
      maxVMs: 8,
      maxVcpus: 24,
      maxMemoryMB: 32768,
      maxStorageGB: 300,
    },
  });

  controller.grantAccess("cloud_admin", "developer", "engineering");
  controller.grantAccess("cloud_admin", "auditor", "engineering");

  controller.createNetwork("cloud_admin", {
    id: "engineering_net",
    environmentId: "engineering",
    cidr: "10.40.1.0/24",
    gateway: "10.40.1.1",
    vlanId: 140,
  });

  controller.createStoragePool("cloud_admin", {
    id: "engineering_pool",
    environmentId: "engineering",
    capacityGB: 200,
  });

  const vm = await controller.createVM("developer", {
    id: "api_vm",
    environmentId: "engineering",
    name: "API Service",
    vcpus: 4,
    memoryMB: 8192,
    image: "ubuntu-24.04",
    networkId: "engineering_net",
  });

  const volume = await controller.createVolume("developer", {
    id: "api_disk",
    environmentId: "engineering",
    poolId: "engineering_pool",
    sizeGB: 40,
    encrypted: true,
  });

  controller.attachVolume("developer", vm.id, volume.id);
  controller.changeVMState("developer", vm.id, "start");

  assert.equal(vm.state, VMState.RUNNING);
  assert.equal(volume.attachedVMId, vm.id);
  assert.throws(
    () => controller.attachVolume("developer", vm.id, volume.id),
    InfrastructureError
  );
  assert.throws(
    () => controller.deleteVolume("developer", volume.id),
    InvalidStateError
  );
  assert.throws(
    () => controller.changeVMState("developer", vm.id, "stop") && null,
    () => false
  );

  controller.changeVMState("developer", vm.id, "stop");
  controller.changeVMState("developer", vm.id, "terminate");

  assert.equal(vm.state, VMState.TERMINATED);
  assert.equal(vm.ip, null);
  assert.equal(volume.attachedVMId, null);

  assert.throws(
    () => controller.inventory("developer", "unknown_env"),
    AuthorizationError
  );
  assert.throws(
    () => controller.createNetwork("cloud_admin", {
      id: "overlap_net",
      environmentId: "engineering",
      cidr: "10.40.1.128/25",
      gateway: "10.40.1.129",
      vlanId: 141,
    }),
    InfrastructureError
  );

  console.log("All virtual infrastructure assertions passed.");
  console.log(JSON.stringify(controller.inventory("auditor", "engineering"), null, 2));
  console.log(`Audit records: ${controller.audit.length}`);
}

runTests().catch((error) => {
  console.error("Infrastructure simulation failed:", error.message);
  process.exitCode = 1;
});
