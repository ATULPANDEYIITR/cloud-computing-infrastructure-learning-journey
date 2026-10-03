'use strict';

/*
 * Virtual Machines: lifecycle, CPU allocation, memory allocation,
 * virtual disks, and snapshots.
 *
 * This Node.js program models a virtualization control plane. It deliberately
 * does not create real VMs. It demonstrates how a management layer can
 * represent resources, validate changes, emit lifecycle events, calculate
 * weighted CPU allocation, manage virtual disks, and capture/revert snapshots.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');

const VM_STATES = Object.freeze({
  DEFINED: 'defined',
  STOPPED: 'stopped',
  RUNNING: 'running',
  PAUSED: 'paused',
  SUSPENDED: 'suspended',
  ERROR: 'error'
});

const DISK_FORMATS = Object.freeze({
  RAW: 'raw',
  QCOW2: 'qcow2',
  VMDK: 'vmdk'
});

class CPUAllocation {
  constructor({
    vcpus,
    cpuLimitPercent = 100,
    cpuShares = 1024,
    pinning = {}
  }) {
    this.vcpus = vcpus;
    this.cpuLimitPercent = cpuLimitPercent;
    this.cpuShares = cpuShares;
    this.pinning = { ...pinning };
  }

  validate(hostVcpus) {
    if (!Number.isInteger(this.vcpus) || this.vcpus < 1) {
      throw new Error('vCPU count must be a positive integer.');
    }

    if (this.vcpus > hostVcpus) {
      throw new Error(
        `Requested ${this.vcpus} vCPUs but host exposes ${hostVcpus}.`
      );
    }

    if (
      this.cpuLimitPercent < 1 ||
      this.cpuLimitPercent > this.vcpus * 100
    ) {
      throw new Error(
        'CPU limit must be between 1% and vCPU_count * 100%.'
      );
    }

    if (!Number.isInteger(this.cpuShares) || this.cpuShares < 2) {
      throw new Error('CPU shares must be an integer of at least 2.');
    }

    for (const [vcpuText, physicalCpu] of Object.entries(this.pinning)) {
      const vcpu = Number(vcpuText);

      if (
        !Number.isInteger(vcpu) ||
        vcpu < 0 ||
        vcpu >= this.vcpus
      ) {
        throw new Error(`Invalid vCPU pinning index: ${vcpuText}`);
      }

      if (
        !Number.isInteger(physicalCpu) ||
        physicalCpu < 0 ||
        physicalCpu >= hostVcpus
      ) {
        throw new Error(`Invalid physical CPU index: ${physicalCpu}`);
      }
    }
  }

  clone() {
    return new CPUAllocation({
      vcpus: this.vcpus,
      cpuLimitPercent: this.cpuLimitPercent,
      cpuShares: this.cpuShares,
      pinning: { ...this.pinning }
    });
  }
}

class MemoryAllocation {
  constructor({
    memoryMb,
    reservationMb,
    limitMb,
    ballooning = false
  }) {
    this.memoryMb = memoryMb;
    this.reservationMb = reservationMb;
    this.limitMb = limitMb;
    this.ballooning = ballooning;
  }

  validate(hostMemoryMb) {
    if (!Number.isInteger(this.memoryMb) || this.memoryMb <= 0) {
      throw new Error('Configured memory must be a positive integer.');
    }

    if (
      !Number.isInteger(this.reservationMb) ||
      this.reservationMb < 0
    ) {
      throw new Error('Memory reservation cannot be negative.');
    }

    if (this.reservationMb > this.memoryMb) {
      throw new Error(
        'Memory reservation cannot exceed configured VM memory.'
      );
    }

    if (this.limitMb < this.memoryMb) {
      throw new Error(
        'Memory limit cannot be below configured VM memory.'
      );
    }

    if (this.limitMb > hostMemoryMb) {
      throw new Error(
        'Memory limit cannot exceed host physical memory.'
      );
    }
  }

  clone() {
    return new MemoryAllocation({
      memoryMb: this.memoryMb,
      reservationMb: this.reservationMb,
      limitMb: this.limitMb,
      ballooning: this.ballooning
    });
  }
}

class VirtualDisk {
  constructor({
    name,
    capacityGb,
    allocatedGb,
    format = DISK_FORMATS.QCOW2,
    thinProvisioned = true,
    readOnly = false
  }) {
    this.name = name;
    this.capacityGb = capacityGb;
    this.allocatedGb = allocatedGb;
    this.format = format;
    this.thinProvisioned = thinProvisioned;
    this.readOnly = readOnly;
  }

  validate() {
    if (!this.name.trim()) {
      throw new Error('Disk name cannot be empty.');
    }

    if (this.capacityGb <= 0) {
      throw new Error('Disk capacity must be positive.');
    }

    if (this.allocatedGb < 0 || this.allocatedGb > this.capacityGb) {
      throw new Error(
        'Allocated disk space must remain between zero and capacity.'
      );
    }
  }

  write(amountGb) {
    if (this.readOnly) {
      throw new Error(`Disk ${this.name} is read-only.`);
    }

    if (amountGb < 0) {
      throw new Error('Write amount cannot be negative.');
    }

    if (this.allocatedGb + amountGb > this.capacityGb) {
      throw new Error(
        `Write would exceed virtual capacity of disk ${this.name}.`
      );
    }

    this.allocatedGb += amountGb;
  }

  clone() {
    return new VirtualDisk({
      name: this.name,
      capacityGb: this.capacityGb,
      allocatedGb: this.allocatedGb,
      format: this.format,
      thinProvisioned: this.thinProvisioned,
      readOnly: this.readOnly
    });
  }
}

class VirtualMachine {
  constructor({ name, cpu, memory, disks }) {
    this.name = name;
    this.cpu = cpu;
    this.memory = memory;
    this.disks = disks;
    this.state = VM_STATES.DEFINED;
    this.uptimeSeconds = 0;
    this.snapshots = new Map();
  }

  validate(host) {
    this.cpu.validate(host.hostVcpus);
    this.memory.validate(host.hostMemoryMb);

    if (this.disks.length === 0) {
      throw new Error('A VM must contain at least one virtual disk.');
    }

    const names = new Set();

    for (const disk of this.disks) {
      disk.validate();

      if (names.has(disk.name)) {
        throw new Error(`Duplicate disk name: ${disk.name}`);
      }

      names.add(disk.name);
    }
  }

  totalDiskCapacity() {
    return this.disks.reduce(
      (total, disk) => total + disk.capacityGb,
      0
    );
  }

  totalDiskAllocation() {
    return this.disks.reduce(
      (total, disk) => total + disk.allocatedGb,
      0
    );
  }

  findDisk(name) {
    const disk = this.disks.find(candidate => candidate.name === name);

    if (!disk) {
      throw new Error(`Disk ${name} does not exist on ${this.name}.`);
    }

    return disk;
  }

  tick(seconds) {
    if (seconds < 0) {
      throw new Error('Time interval cannot be negative.');
    }

    if (this.state === VM_STATES.RUNNING) {
      this.uptimeSeconds += seconds;
    }
  }
}

class Hypervisor extends require('events').EventEmitter {
  constructor({
    name,
    hostVcpus,
    hostMemoryMb,
    storageCapacityGb
  }) {
    super();

    if (hostVcpus < 1) {
      throw new Error('Host must expose at least one CPU.');
    }

    if (hostMemoryMb < 512) {
      throw new Error('Host memory is too small for this model.');
    }

    if (storageCapacityGb <= 0) {
      throw new Error('Host storage must be positive.');
    }

    this.name = name;
    this.hostVcpus = hostVcpus;
    this.hostMemoryMb = hostMemoryMb;
    this.storageCapacityGb = storageCapacityGb;
    this.vms = new Map();
  }

  usedMemoryReservation(excludeName = null) {
    let total = 0;

    for (const vm of this.vms.values()) {
      if (vm.name !== excludeName && vm.state !== VM_STATES.ERROR) {
        total += vm.memory.reservationMb;
      }
    }

    return total;
  }

  usedStorage(excludeName = null) {
    let total = 0;

    for (const vm of this.vms.values()) {
      if (vm.name !== excludeName) {
        total += vm.totalDiskAllocation();
      }
    }

    return total;
  }

  createVm(vm) {
    if (this.vms.has(vm.name)) {
      throw new Error(`VM ${vm.name} already exists.`);
    }

    vm.validate(this);

    const requestedMemory =
      this.usedMemoryReservation() + vm.memory.reservationMb;

    if (requestedMemory > this.hostMemoryMb) {
      throw new Error(
        `Memory reservation would reach ${requestedMemory} MB, ` +
        `above host capacity of ${this.hostMemoryMb} MB.`
      );
    }

    const requestedStorage =
      this.usedStorage() + vm.totalDiskAllocation();

    if (requestedStorage > this.storageCapacityGb) {
      throw new Error('Host storage capacity would be exceeded.');
    }

    vm.state = VM_STATES.STOPPED;
    this.vms.set(vm.name, vm);
    this.emit('vm-created', { vm: vm.name });
  }

  getVm(name) {
    const vm = this.vms.get(name);

    if (!vm) {
      throw new Error(`Unknown VM: ${name}`);
    }

    return vm;
  }

  startVm(name) {
    const vm = this.getVm(name);

    if (
      vm.state !== VM_STATES.STOPPED &&
      vm.state !== VM_STATES.PAUSED
    ) {
      throw new Error(
        `Cannot start ${name} from state ${vm.state}.`
      );
    }

    if (vm.memory.reservationMb > this.hostMemoryMb) {
      throw new Error('VM memory reservation exceeds host memory.');
    }

    const oldState = vm.state;
    vm.state = VM_STATES.RUNNING;

    this.emit('state-changed', {
      vm: name,
      from: oldState,
      to: vm.state
    });
  }

  stopVm(name) {
    const vm = this.getVm(name);

    if (vm.state === VM_STATES.STOPPED) {
      return;
    }

    if (
      ![
        VM_STATES.RUNNING,
        VM_STATES.PAUSED,
        VM_STATES.SUSPENDED
      ].includes(vm.state)
    ) {
      throw new Error(
        `Cannot stop ${name} from state ${vm.state}.`
      );
    }

    const oldState = vm.state;
    vm.state = VM_STATES.STOPPED;

    this.emit('state-changed', {
      vm: name,
      from: oldState,
      to: vm.state
    });
  }

  pauseVm(name) {
    const vm = this.getVm(name);

    if (vm.state !== VM_STATES.RUNNING) {
      throw new Error('Only running VMs can be paused.');
    }

    vm.state = VM_STATES.PAUSED;
    this.emit('state-changed', {
      vm: name,
      from: VM_STATES.RUNNING,
      to: VM_STATES.PAUSED
    });
  }

  resumeVm(name) {
    const vm = this.getVm(name);

    if (vm.state !== VM_STATES.PAUSED) {
      throw new Error('Only paused VMs can be resumed.');
    }

    vm.state = VM_STATES.RUNNING;
    this.emit('state-changed', {
      vm: name,
      from: VM_STATES.PAUSED,
      to: VM_STATES.RUNNING
    });
  }

  suspendVm(name) {
    const vm = this.getVm(name);

    if (vm.state !== VM_STATES.RUNNING) {
      throw new Error('Only running VMs can be suspended.');
    }

    vm.state = VM_STATES.SUSPENDED;
    this.emit('state-changed', {
      vm: name,
      from: VM_STATES.RUNNING,
      to: VM_STATES.SUSPENDED
    });
  }

  deleteVm(name) {
    const vm = this.getVm(name);

    if (vm.state === VM_STATES.RUNNING) {
      throw new Error('Stop the VM before deleting it.');
    }

    this.vms.delete(name);
    this.emit('vm-deleted', { vm: name });
  }

  allocateCpuTime(durationSeconds) {
    if (durationSeconds < 0) {
      throw new Error('Duration cannot be negative.');
    }

    const running = [...this.vms.values()].filter(
      vm => vm.state === VM_STATES.RUNNING
    );

    if (running.length === 0) {
      return {};
    }

    const totalShares = running.reduce(
      (sum, vm) => sum + vm.cpu.cpuShares,
      0
    );

    const hostCpuSeconds =
      this.hostVcpus * durationSeconds;

    const allocation = {};

    for (const vm of running) {
      const weightedEntitlement =
        hostCpuSeconds *
        (vm.cpu.cpuShares / totalShares);

      const configuredLimit =
        vm.cpu.vcpus *
        durationSeconds *
        (vm.cpu.cpuLimitPercent / 100);

      allocation[vm.name] = Math.min(
        weightedEntitlement,
        configuredLimit
      );
    }

    return allocation;
  }

  resizeMemory(name, {
    memoryMb,
    reservationMb,
    limitMb
  }) {
    const vm = this.getVm(name);

    const next = new MemoryAllocation({
      memoryMb,
      reservationMb:
        reservationMb ?? Math.min(
          vm.memory.reservationMb,
          memoryMb
        ),
      limitMb:
        limitMb ?? Math.max(
          vm.memory.limitMb,
          memoryMb
        ),
      ballooning: vm.memory.ballooning
    });

    next.validate(this.hostMemoryMb);

    const available =
      this.hostMemoryMb -
      this.usedMemoryReservation(name);

    if (next.reservationMb > available) {
      throw new Error(
        `Only ${available} MB is available for this reservation.`
      );
    }

    vm.memory = next;
    this.emit('memory-resized', {
      vm: name,
      memoryMb
    });
  }

  expandDisk(vmName, diskName, newCapacityGb) {
    const vm = this.getVm(vmName);
    const disk = vm.findDisk(diskName);

    if (newCapacityGb <= disk.capacityGb) {
      throw new Error(
        'This operation supports expansion, not shrinking.'
      );
    }

    const physicalIncrease = disk.thinProvisioned
      ? 0
      : newCapacityGb - disk.capacityGb;

    if (
      this.usedStorage(vmName) +
      vm.totalDiskAllocation() +
      physicalIncrease >
      this.storageCapacityGb
    ) {
      throw new Error('Host storage is insufficient.');
    }

    disk.capacityGb = newCapacityGb;

    this.emit('disk-expanded', {
      vm: vmName,
      disk: diskName,
      capacityGb: newCapacityGb
    });
  }

  writeDisk(vmName, diskName, amountGb) {
    const vm = this.getVm(vmName);

    if (vm.state !== VM_STATES.RUNNING) {
      throw new Error(
        'Simulated disk I/O requires a running VM.'
      );
    }

    const disk = vm.findDisk(diskName);

    if (
      disk.thinProvisioned &&
      this.usedStorage() + amountGb >
      this.storageCapacityGb
    ) {
      throw new Error('Thin-provisioned host storage is full.');
    }

    disk.write(amountGb);

    this.emit('disk-write', {
      vm: vmName,
      disk: diskName,
      amountGb
    });
  }

  createSnapshot(vmName, snapshotId, description) {
    const vm = this.getVm(vmName);

    if (vm.snapshots.has(snapshotId)) {
      throw new Error(
        `Snapshot ${snapshotId} already exists.`
      );
    }

    const snapshot = {
      id: snapshotId,
      description,
      state: vm.state,
      cpu: vm.cpu.clone(),
      memory: vm.memory.clone(),
      disks: vm.disks.map(disk => disk.clone()),
      createdAt: new Date().toISOString()
    };

    vm.snapshots.set(snapshotId, snapshot);

    this.emit('snapshot-created', {
      vm: vmName,
      snapshot: snapshotId
    });

    return snapshot;
  }

  revertSnapshot(vmName, snapshotId) {
    const vm = this.getVm(vmName);
    const snapshot = vm.snapshots.get(snapshotId);

    if (!snapshot) {
      throw new Error(
        `Snapshot ${snapshotId} does not exist.`
      );
    }

    if (vm.state === VM_STATES.RUNNING) {
      throw new Error(
        'Stop the VM before reverting this model snapshot.'
      );
    }

    vm.cpu = snapshot.cpu.clone();
    vm.memory = snapshot.memory.clone();
    vm.disks = snapshot.disks.map(disk => disk.clone());
    vm.state = VM_STATES.STOPPED;

    this.emit('snapshot-reverted', {
      vm: vmName,
      snapshot: snapshotId
    });
  }

  deleteSnapshot(vmName, snapshotId) {
    const vm = this.getVm(vmName);

    if (!vm.snapshots.delete(snapshotId)) {
      throw new Error(
        `Snapshot ${snapshotId} does not exist.`
      );
    }

    this.emit('snapshot-deleted', {
      vm: vmName,
      snapshot: snapshotId
    });
  }

  inventory() {
    return [...this.vms.values()].map(vm => ({
      name: vm.name,
      state: vm.state,
      vcpus: vm.cpu.vcpus,
      memoryMb: vm.memory.memoryMb,
      diskCapacityGb: vm.totalDiskCapacity(),
      diskAllocatedGb: vm.totalDiskAllocation(),
      snapshots: [...vm.snapshots.keys()]
    }));
  }
}

function printHeading(title) {
  console.log(`\n${'='.repeat(78)}\n${title}\n${'='.repeat(78)}`);
}

function createDemoHost() {
  const hypervisor = new Hypervisor({
    name: 'node-hypervisor-01',
    hostVcpus: 8,
    hostMemoryMb: 16384,
    storageCapacityGb: 500
  });

  hypervisor.on('state-changed', event => {
    console.log(
      `[event] ${event.vm}: ${event.from} -> ${event.to}`
    );
  });

  hypervisor.on('snapshot-created', event => {
    console.log(
      `[event] snapshot created: ${event.vm}/${event.snapshot}`
    );
  });

  hypervisor.on('disk-write', event => {
    console.log(
      `[event] disk write: ${event.vm}/${event.disk} +${event.amountGb} GB`
    );
  });

  const databaseVm = new VirtualMachine({
    name: 'database',
    cpu: new CPUAllocation({
      vcpus: 4,
      cpuLimitPercent: 90,
      cpuShares: 2048,
      pinning: {
        0: 0,
        1: 1
      }
    }),
    memory: new MemoryAllocation({
      memoryMb: 6144,
      reservationMb: 4096,
      limitMb: 8192,
      ballooning: false
    }),
    disks: [
      new VirtualDisk({
        name: 'os',
        capacityGb: 50,
        allocatedGb: 25,
        format: DISK_FORMATS.QCOW2,
        thinProvisioned: true
      }),
      new VirtualDisk({
        name: 'database',
        capacityGb: 200,
        allocatedGb: 100,
        format: DISK_FORMATS.QCOW2,
        thinProvisioned: true
      })
    ]
  });

  const workerVm = new VirtualMachine({
    name: 'ci-worker',
    cpu: new CPUAllocation({
      vcpus: 2,
      cpuLimitPercent: 100,
      cpuShares: 1024
    }),
    memory: new MemoryAllocation({
      memoryMb: 4096,
      reservationMb: 2048,
      limitMb: 4096
    }),
    disks: [
      new VirtualDisk({
        name: 'os',
        capacityGb: 60,
        allocatedGb: 30,
        format: DISK_FORMATS.RAW,
        thinProvisioned: false
      })
    ]
  });

  hypervisor.createVm(databaseVm);
  hypervisor.createVm(workerVm);

  return hypervisor;
}

function demonstrateLifecycle(hypervisor) {
  printHeading('Event-driven VM lifecycle');

  hypervisor.startVm('database');

  const database = hypervisor.getVm('database');
  database.tick(30);

  console.log(
    `database uptime: ${database.uptimeSeconds} seconds`
  );

  hypervisor.pauseVm('database');
  hypervisor.resumeVm('database');
  hypervisor.suspendVm('database');
  hypervisor.stopVm('database');

  try {
    hypervisor.resumeVm('database');
  } catch (error) {
    console.log(`Expected lifecycle error: ${error.message}`);
  }
}

function demonstrateCpuScheduling(hypervisor) {
  printHeading('Weighted CPU allocation');

  hypervisor.startVm('database');
  hypervisor.startVm('ci-worker');

  const allocation = hypervisor.allocateCpuTime(20);

  for (const [vm, cpuSeconds] of Object.entries(allocation)) {
    console.log(
      `${vm}: ${cpuSeconds.toFixed(2)} CPU-seconds`
    );
  }

  hypervisor.stopVm('database');
  hypervisor.stopVm('ci-worker');
}

function demonstrateMemory(hypervisor) {
  printHeading('Memory allocation');

  hypervisor.resizeMemory('database', {
    memoryMb: 7168,
    reservationMb: 4096,
    limitMb: 8192
  });

  const vm = hypervisor.getVm('database');

  console.log(
    `database memory: ${vm.memory.memoryMb} MB, ` +
    `reservation: ${vm.memory.reservationMb} MB, ` +
    `limit: ${vm.memory.limitMb} MB`
  );

  try {
    hypervisor.resizeMemory('database', {
      memoryMb: 20000,
      reservationMb: 19000,
      limitMb: 22000
    });
  } catch (error) {
    console.log(`Expected memory error: ${error.message}`);
  }
}

function demonstrateDisksAndSnapshots(hypervisor) {
  printHeading('Virtual disks and snapshots');

  hypervisor.expandDisk(
    'database',
    'database',
    250
  );

  hypervisor.startVm('database');
  hypervisor.writeDisk(
    'database',
    'database',
    6
  );

  console.log(
    `Before snapshot: ${
      hypervisor.getVm('database')
        .findDisk('database')
        .allocatedGb
    } GB allocated`
  );

  hypervisor.stopVm('database');

  hypervisor.createSnapshot(
    'database',
    'pre-index-migration',
    'Stable database state before index migration'
  );

  const disk = hypervisor
    .getVm('database')
    .findDisk('database');

  disk.allocatedGb += 15;

  console.log(
    `After simulated change: ${disk.allocatedGb} GB allocated`
  );

  hypervisor.revertSnapshot(
    'database',
    'pre-index-migration'
  );

  console.log(
    `After revert: ${
      hypervisor
        .getVm('database')
        .findDisk('database')
        .allocatedGb
    } GB allocated`
  );

  hypervisor.deleteSnapshot(
    'database',
    'pre-index-migration'
  );
}

function demonstrateFilePersistence(hypervisor) {
  printHeading('Inventory persistence');

  const inventory = hypervisor.inventory();
  const directory = fs.mkdtempSync(
    path.join(os.tmpdir(), 'vm-control-plane-')
  );
  const file = path.join(directory, 'inventory.json');

  fs.writeFileSync(
    file,
    JSON.stringify(inventory, null, 2),
    'utf8'
  );

  console.log(`Inventory written to ${file}`);
  console.log(
    fs.readFileSync(file, 'utf8')
  );

  fs.rmSync(directory, {
    recursive: true,
    force: true
  });
}

function demonstrateValidation(hypervisor) {
  printHeading('Validation and failure conditions');

  try {
    const invalid = new VirtualMachine({
      name: 'oversized',
      cpu: new CPUAllocation({
        vcpus: 16
      }),
      memory: new MemoryAllocation({
        memoryMb: 1024,
        reservationMb: 512,
        limitMb: 2048
      }),
      disks: [
        new VirtualDisk({
          name: 'os',
          capacityGb: 20,
          allocatedGb: 5
        })
      ]
    });

    hypervisor.createVm(invalid);
  } catch (error) {
    console.log(`Expected CPU validation: ${error.message}`);
  }

  try {
    hypervisor.startVm('does-not-exist');
  } catch (error) {
    console.log(`Expected lookup failure: ${error.message}`);
  }
}

function main() {
  const hypervisor = createDemoHost();

  demonstrateLifecycle(hypervisor);
  demonstrateCpuScheduling(hypervisor);
  demonstrateMemory(hypervisor);
  demonstrateDisksAndSnapshots(hypervisor);
  demonstrateValidation(hypervisor);
  demonstrateFilePersistence(hypervisor);

  printHeading('Final inventory');
  console.log(
    JSON.stringify(hypervisor.inventory(), null, 2)
  );
}

main();
