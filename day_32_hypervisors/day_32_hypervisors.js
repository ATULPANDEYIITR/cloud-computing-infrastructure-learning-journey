'use strict';

/*
 * Hypervisors: Type 1 and Type 2 virtualization architecture.
 *
 * This Node.js program uses an event-driven VM manager to model:
 *   - Type 1 and Type 2 architecture
 *   - VM creation and lifecycle events
 *   - virtual CPU scheduling
 *   - guest-to-host memory mapping
 *   - virtual network devices
 *   - reviewable resource policies
 *   - snapshots
 *   - failures and isolation boundaries
 *
 * It is an architectural simulation rather than a hardware hypervisor.
 * A real hypervisor relies on CPU virtualization extensions, privileged
 * execution, interrupt virtualization, IOMMUs, nested page tables, device
 * models, and kernel/firmware integration.
 */

const { EventEmitter } = require('node:events');
const crypto = require('node:crypto');

const HypervisorType = Object.freeze({
    TYPE_1: 'Type 1 / bare-metal',
    TYPE_2: 'Type 2 / hosted'
});

const VMState = Object.freeze({
    CREATED: 'created',
    RUNNING: 'running',
    PAUSED: 'paused',
    STOPPED: 'stopped',
    FAILED: 'failed'
});

class ResourceError extends Error {}
class LifecycleError extends Error {}
class ValidationError extends Error {}

function assertPositiveInteger(value, fieldName) {
    if (!Number.isInteger(value) || value <= 0) {
        throw new ValidationError(`${fieldName} must be a positive integer.`);
    }
}

function deterministicMac(vmId) {
    const digest = crypto.createHash('sha256').update(vmId).digest();
    return `02:00:${digest[0].toString(16).padStart(2, '0')}:` +
        `${digest[1].toString(16).padStart(2, '0')}:` +
        `${digest[2].toString(16).padStart(2, '0')}:` +
        `${digest[3].toString(16).padStart(2, '0')}`;
}

class Host {
    constructor({
        name,
        physicalCpus,
        memoryMiB,
        storageGiB,
        hostOs = null,
        type = HypervisorType.TYPE_1
    }) {
        assertPositiveInteger(physicalCpus, 'physicalCpus');
        assertPositiveInteger(memoryMiB, 'memoryMiB');
        assertPositiveInteger(storageGiB, 'storageGiB');

        this.name = name;
        this.physicalCpus = physicalCpus;
        this.memoryMiB = memoryMiB;
        this.storageGiB = storageGiB;
        this.hostOs = hostOs;
        this.type = type;
    }

    architecture() {
        if (this.type === HypervisorType.TYPE_1) {
            return 'hardware -> Type 1 hypervisor -> virtual machines';
        }

        return 'hardware -> host OS -> Type 2 hypervisor -> virtual machines';
    }
}

class VirtualDisk {
    constructor(sizeGiB) {
        assertPositiveInteger(sizeGiB, 'disk size');
        this.sizeGiB = sizeGiB;
        this.usedGiB = 0;
    }

    write(amountGiB) {
        assertPositiveInteger(amountGiB, 'write amount');

        if (this.usedGiB + amountGiB > this.sizeGiB) {
            throw new ResourceError(
                `Virtual disk capacity exceeded: ${this.sizeGiB - this.usedGiB} GiB remains.`
            );
        }

        this.usedGiB += amountGiB;
    }
}

class VirtualNic {
    constructor(vmId) {
        this.name = `${vmId}-nic`;
        this.macAddress = deterministicMac(vmId);
        this.connected = true;
        this.sentPackets = 0;
        this.receivedPackets = 0;
    }

    send(packetCount) {
        assertPositiveInteger(packetCount, 'packetCount');

        if (!this.connected) {
            throw new LifecycleError(`${this.name} is disconnected.`);
        }

        this.sentPackets += packetCount;
    }
}

class VirtualMachine {
    constructor({ id, name, vcpus, memoryMiB, diskGiB }) {
        if (!id || !name) {
            throw new ValidationError('VM id and name are required.');
        }

        assertPositiveInteger(vcpus, 'vcpus');
        assertPositiveInteger(memoryMiB, 'memoryMiB');
        assertPositiveInteger(diskGiB, 'diskGiB');

        this.id = id;
        this.name = name;
        this.vcpus = vcpus;
        this.memoryMiB = memoryMiB;
        this.memoryUsedMiB = 0;
        this.disk = new VirtualDisk(diskGiB);
        this.nic = new VirtualNic(id);
        this.state = VMState.CREATED;
        this.cpuTimeMs = 0;
        this.snapshot = null;
        this.guestPageMappings = new Map();
    }

    allocateMemory(amountMiB) {
        assertPositiveInteger(amountMiB, 'memory amount');

        if (this.memoryUsedMiB + amountMiB > this.memoryMiB) {
            throw new ResourceError(
                `${this.name} cannot allocate ${amountMiB} MiB; ` +
                `${this.memoryMiB - this.memoryUsedMiB} MiB remains.`
            );
        }

        this.memoryUsedMiB += amountMiB;
    }

    runCpu(milliseconds) {
        if (this.state !== VMState.RUNNING) {
            throw new LifecycleError(`${this.name} is not running.`);
        }

        assertPositiveInteger(milliseconds, 'CPU quantum');
        this.cpuTimeMs += milliseconds;
    }

    snapshotState() {
        this.snapshot = {
            state: this.state,
            memoryUsedMiB: this.memoryUsedMiB,
            diskUsedGiB: this.disk.usedGiB,
            cpuTimeMs: this.cpuTimeMs,
            mappings: [...this.guestPageMappings.entries()]
        };
    }

    restoreState() {
        if (!this.snapshot) {
            throw new LifecycleError(`${this.name} has no snapshot.`);
        }

        const snapshot = this.snapshot;
        this.state = snapshot.state;
        this.memoryUsedMiB = snapshot.memoryUsedMiB;
        this.disk.usedGiB = snapshot.diskUsedGiB;
        this.cpuTimeMs = snapshot.cpuTimeMs;
        this.guestPageMappings = new Map(snapshot.mappings);
    }
}

class MemoryMapper {
    constructor(hostFrameCount) {
        assertPositiveInteger(hostFrameCount, 'hostFrameCount');
        this.freeFrames = Array.from({ length: hostFrameCount }, (_, i) => i);
    }

    map(vm, guestFrame) {
        assertPositiveInteger(guestFrame + 1, 'guestFrame');

        if (vm.guestPageMappings.has(guestFrame)) {
            return vm.guestPageMappings.get(guestFrame);
        }

        if (this.freeFrames.length === 0) {
            throw new ResourceError('Host memory frames are exhausted.');
        }

        const hostFrame = this.freeFrames.shift();
        const mapping = {
            guestFrame,
            hostFrame,
            writable: true
        };

        vm.guestPageMappings.set(guestFrame, mapping);
        return mapping;
    }
}

class CpuScheduler {
    constructor(host) {
        this.host = host;
        this.readyQueue = [];
        this.virtualCpus = new Map();
    }

    register(vm) {
        for (let index = 0; index < vm.vcpus; index += 1) {
            const vcpu = {
                id: `${vm.id}-vcpu-${index}`,
                vm,
                instructions: 0
            };

            this.virtualCpus.set(vcpu.id, vcpu);
            this.readyQueue.push(vcpu);
        }
    }

    tick(quantumMs = 10) {
        assertPositiveInteger(quantumMs, 'quantumMs');

        const executions = [];
        const nextQueue = [];

        for (let core = 0; core < this.host.physicalCpus; core += 1) {
            const vcpu = this.readyQueue.shift();

            if (!vcpu) {
                break;
            }

            if (vcpu.vm.state !== VMState.RUNNING) {
                continue;
            }

            vcpu.instructions += quantumMs * 1000;
            vcpu.vm.runCpu(quantumMs);

            executions.push({
                core,
                vcpu: vcpu.id,
                vm: vcpu.vm.name,
                quantumMs
            });

            nextQueue.push(vcpu);
        }

        this.readyQueue.push(...nextQueue);
        return executions;
    }
}

class Hypervisor extends EventEmitter {
    constructor(host, { allowOvercommit = false } = {}) {
        super();

        this.host = host;
        this.allowOvercommit = allowOvercommit;
        this.vms = new Map();

        // Four KiB is represented as one logical frame in this simulation.
        this.memoryMapper = new MemoryMapper(
            Math.max(1, Math.floor(host.memoryMiB / 4))
        );

        this.scheduler = new CpuScheduler(host);
        this.allocations = {
            vcpus: 0,
            memoryMiB: 0,
            storageGiB: 0
        };
    }

    createVm(config) {
        if (this.vms.has(config.id)) {
            throw new ValidationError(`VM ${config.id} already exists.`);
        }

        const projected = {
            vcpus: this.allocations.vcpus + config.vcpus,
            memoryMiB: this.allocations.memoryMiB + config.memoryMiB,
            storageGiB: this.allocations.storageGiB + config.diskGiB
        };

        if (!this.allowOvercommit) {
            if (projected.vcpus > this.host.physicalCpus) {
                throw new ResourceError('vCPU allocation exceeds host capacity.');
            }

            if (projected.memoryMiB > this.host.memoryMiB) {
                throw new ResourceError('Memory allocation exceeds host capacity.');
            }

            if (projected.storageGiB > this.host.storageGiB) {
                throw new ResourceError('Storage allocation exceeds host capacity.');
            }
        }

        const vm = new VirtualMachine(config);
        this.vms.set(vm.id, vm);

        this.allocations = projected;
        this.emit('vm-created', vm);

        return vm;
    }

    start(vmId) {
        const vm = this.getVm(vmId);

        if (vm.state === VMState.RUNNING) {
            throw new LifecycleError(`${vm.name} is already running.`);
        }

        if (vm.state === VMState.FAILED) {
            throw new LifecycleError(`${vm.name} must be repaired first.`);
        }

        vm.state = VMState.RUNNING;
        this.scheduler.register(vm);
        this.emit('vm-started', vm);
    }

    pause(vmId) {
        const vm = this.getVm(vmId);

        if (vm.state !== VMState.RUNNING) {
            throw new LifecycleError('Only a running VM can be paused.');
        }

        vm.state = VMState.PAUSED;
        this.emit('vm-paused', vm);
    }

    stop(vmId) {
        const vm = this.getVm(vmId);
        vm.state = VMState.STOPPED;
        this.emit('vm-stopped', vm);
    }

    getVm(vmId) {
        const vm = this.vms.get(vmId);

        if (!vm) {
            throw new LifecycleError(`Unknown VM: ${vmId}`);
        }

        return vm;
    }

    tick(quantumMs = 10) {
        const executions = this.scheduler.tick(quantumMs);

        for (const execution of executions) {
            this.emit('cpu-scheduled', execution);
        }

        return executions;
    }

    policyReport() {
        const runningVms = [...this.vms.values()]
            .filter(vm => vm.state === VMState.RUNNING)
            .map(vm => vm.name);

        return {
            architecture: this.host.architecture(),
            type: this.host.type,
            overcommit: this.allowOvercommit,
            physicalCpus: this.host.physicalCpus,
            allocatedVcpus: this.allocations.vcpus,
            allocatedMemoryMiB: this.allocations.memoryMiB,
            allocatedStorageGiB: this.allocations.storageGiB,
            runningVms
        };
    }
}

function demonstrateArchitectures() {
    console.log('\n=== Virtualization Architecture ===');

    const bareMetal = new Host({
        name: 'datacenter-node',
        physicalCpus: 16,
        memoryMiB: 65536,
        storageGiB: 2000,
        type: HypervisorType.TYPE_1
    });

    const hosted = new Host({
        name: 'developer-laptop',
        physicalCpus: 8,
        memoryMiB: 32768,
        storageGiB: 1000,
        hostOs: 'Windows 11',
        type: HypervisorType.TYPE_2
    });

    console.log(`${bareMetal.name}: ${bareMetal.architecture()}`);
    console.log(`${hosted.name}: ${hosted.architecture()}`);

    console.log(
        'Type 1 controls virtualization directly at the hardware boundary; ' +
        'Type 2 operates as software hosted by a conventional operating system.'
    );
}

function demonstrateEventDrivenLifecycle() {
    console.log('\n=== Event-Driven VM Lifecycle ===');

    const host = new Host({
        name: 'compute-node-01',
        physicalCpus: 4,
        memoryMiB: 16384,
        storageGiB: 500
    });

    const hypervisor = new Hypervisor(host);

    hypervisor.on('vm-created', vm =>
        console.log(`created: ${vm.name}`)
    );

    hypervisor.on('vm-started', vm =>
        console.log(`started: ${vm.name}`)
    );

    hypervisor.on('cpu-scheduled', event =>
        console.log(
            `scheduled ${event.vcpu} for ${event.quantumMs} ms on core ${event.core}`
        )
    );

    const apiVm = hypervisor.createVm({
        id: 'api',
        name: 'api-server',
        vcpus: 2,
        memoryMiB: 4096,
        diskGiB: 40
    });

    const workerVm = hypervisor.createVm({
        id: 'worker',
        name: 'worker-server',
        vcpus: 1,
        memoryMiB: 2048,
        diskGiB: 30
    });

    hypervisor.start(apiVm.id);
    hypervisor.start(workerVm.id);

    apiVm.allocateMemory(1024);
    apiVm.disk.write(5);
    apiVm.nic.send(250);

    for (let tick = 0; tick < 3; tick += 1) {
        hypervisor.tick(10);
    }

    hypervisor.pause(workerVm.id);
    console.log(`worker state: ${workerVm.state}`);
    hypervisor.start(apiVm.id); // Demonstrates lifecycle validation.
}

function demonstrateMemoryTranslation() {
    console.log('\n=== Guest-to-Host Memory Translation ===');

    const host = new Host({
        name: 'memory-node',
        physicalCpus: 4,
        memoryMiB: 8192,
        storageGiB: 500
    });

    const hypervisor = new Hypervisor(host);

    const vm = hypervisor.createVm({
        id: 'memory-vm',
        name: 'memory-test',
        vcpus: 1,
        memoryMiB: 2048,
        diskGiB: 20
    });

    hypervisor.start(vm.id);

    for (const guestFrame of [0, 1, 2, 3]) {
        const mapping = hypervisor.memoryMapper.map(vm, guestFrame);
        console.log(
            `guest frame ${mapping.guestFrame} -> ` +
            `host frame ${mapping.hostFrame}`
        );
    }

    const sameMapping = hypervisor.memoryMapper.map(vm, 2);
    console.log(
        `repeated lookup preserved host frame ${sameMapping.hostFrame}`
    );

    console.log(
        'The mapping models the conceptual role of nested page translation: ' +
        'a guest address must resolve to memory owned by the correct VM.'
    );
}

function demonstrateSnapshotAndFailure() {
    console.log('\n=== Snapshot and Failure Handling ===');

    const host = new Host({
        name: 'snapshot-node',
        physicalCpus: 2,
        memoryMiB: 8192,
        storageGiB: 200
    });

    const hypervisor = new Hypervisor(host);

    const vm = hypervisor.createVm({
        id: 'snapshot-vm',
        name: 'transaction-service',
        vcpus: 1,
        memoryMiB: 2048,
        diskGiB: 30
    });

    hypervisor.start(vm.id);
    vm.allocateMemory(512);
    vm.disk.write(4);
    vm.snapshotState();

    vm.allocateMemory(256);
    vm.disk.write(3);

    console.log(
        `before restore: memory=${vm.memoryUsedMiB} MiB, ` +
        `disk=${vm.disk.usedGiB} GiB`
    );

    vm.restoreState();

    console.log(
        `after restore: memory=${vm.memoryUsedMiB} MiB, ` +
        `disk=${vm.disk.usedGiB} GiB`
    );

    vm.nic.connected = false;

    try {
        vm.nic.send(1);
    } catch (error) {
        console.log(`device failure handled: ${error.message}`);
    }

    try {
        vm.disk.write(100);
    } catch (error) {
        console.log(`storage failure handled: ${error.message}`);
    }
}

function demonstrateType2TradeOff() {
    console.log('\n=== Type 2 Resource Path ===');

    const workstation = new Host({
        name: 'engineering-workstation',
        physicalCpus: 8,
        memoryMiB: 32768,
        storageGiB: 1000,
        hostOs: 'Linux',
        type: HypervisorType.TYPE_2
    });

    const hypervisor = new Hypervisor(workstation);

    hypervisor.createVm({
        id: 'test-linux',
        name: 'linux-test-vm',
        vcpus: 4,
        memoryMiB: 8192,
        diskGiB: 80
    });

    console.log(workstation.architecture());
    console.log(
        'The host OS remains responsible for ordinary desktop hardware and ' +
        'process management, while the hosted hypervisor creates the VM boundary.'
    );

    console.log(JSON.stringify(hypervisor.policyReport(), null, 2));
}

function main() {
    demonstrateArchitectures();

    try {
        demonstrateEventDrivenLifecycle();
    } catch (error) {
        console.log(`expected lifecycle validation: ${error.message}`);
    }

    demonstrateMemoryTranslation();
    demonstrateSnapshotAndFailure();
    demonstrateType2TradeOff();

    console.log('\n=== Security Boundary ===');
    console.log(
        'A production hypervisor must enforce isolation across CPU execution, ' +
        'memory mappings, devices, storage, interrupts, and management interfaces.'
    );

    console.log('\nSimulation completed.');
}

main();
