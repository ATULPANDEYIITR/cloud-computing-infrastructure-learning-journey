'use strict';

/*
 * Server Virtualization: Event-Driven Host and VM Lifecycle Model
 *
 * This Node.js-compatible program complements the Python resource simulator
 * by focusing on event-driven host management, VM lifecycle transitions,
 * asynchronous workload collection, isolation policy, and merge-like
 * admission decisions for virtualization operations.
 *
 * No external npm packages are required.
 */

const EventEmitter = require('events');

const VMState = Object.freeze({
    STOPPED: 'stopped',
    RUNNING: 'running',
    PAUSED: 'paused',
    FAILED: 'failed'
});

class ValidationError extends Error {
    constructor(message) {
        super(message);
        this.name = 'ValidationError';
    }
}

class AdmissionError extends Error {
    constructor(message) {
        super(message);
        this.name = 'AdmissionError';
    }
}

class IsolationPolicy {
    constructor() {
        this.networkSegments = new Map();
        this.allowedPairs = new Set();
    }

    register(vm) {
        if (!this.networkSegments.has(vm.networkSegment)) {
            this.networkSegments.set(vm.networkSegment, new Set());
        }
        this.networkSegments.get(vm.networkSegment).add(vm.id);
    }

    allowExplicitCommunication(sourceId, targetId) {
        this.allowedPairs.add(`${sourceId}->${targetId}`);
    }

    canCommunicate(source, target) {
        if (source.id === target.id) {
            return true;
        }

        return this.allowedPairs.has(`${source.id}->${target.id}`);
    }

    describe(vm) {
        return {
            vm: vm.id,
            segment: vm.networkSegment,
            explicitlyAllowedPeers: [...this.allowedPairs]
                .filter(pair => pair.startsWith(`${vm.id}->`))
                .map(pair => pair.split('->')[1])
        };
    }
}

class VirtualMachine {
    constructor({
        id,
        vcpus,
        memoryGB,
        storageGB,
        networkGbps,
        cpuShares = 100,
        cpuReservation = 0,
        memoryReservationGB = 0,
        cpuLimit = null,
        memoryLimitGB = null,
        networkSegment = 'isolated'
    }) {
        if (!id || typeof id !== 'string') {
            throw new ValidationError('VM id must be a non-empty string.');
        }

        if (!Number.isInteger(vcpus) || vcpus <= 0) {
            throw new ValidationError(`${id}: vCPUs must be a positive integer.`);
        }

        if (memoryGB <= 0 || storageGB <= 0) {
            throw new ValidationError(
                `${id}: memory and storage must be positive.`
            );
        }

        if (cpuShares <= 0) {
            throw new ValidationError(`${id}: CPU shares must be positive.`);
        }

        if (cpuReservation < 0 || cpuReservation > vcpus) {
            throw new ValidationError(`${id}: invalid CPU reservation.`);
        }

        if (
            memoryReservationGB < 0 ||
            memoryReservationGB > memoryGB
        ) {
            throw new ValidationError(`${id}: invalid memory reservation.`);
        }

        if (cpuLimit !== null && cpuLimit < cpuReservation) {
            throw new ValidationError(
                `${id}: CPU limit cannot be below reservation.`
            );
        }

        if (
            memoryLimitGB !== null &&
            memoryLimitGB < memoryReservationGB
        ) {
            throw new ValidationError(
                `${id}: memory limit cannot be below reservation.`
            );
        }

        this.id = id;
        this.vcpus = vcpus;
        this.memoryGB = memoryGB;
        this.storageGB = storageGB;
        this.networkGbps = networkGbps;
        this.cpuShares = cpuShares;
        this.cpuReservation = cpuReservation;
        this.memoryReservationGB = memoryReservationGB;
        this.cpuLimit = cpuLimit;
        this.memoryLimitGB = memoryLimitGB;
        this.networkSegment = networkSegment;

        this.state = VMState.STOPPED;
        this.cpuDemand = 0;
        this.memoryDemandGB = 0;
        this.balloonedMemoryGB = 0;
        this.metrics = [];
    }

    get effectiveCpuLimit() {
        return this.cpuLimit ?? this.vcpus;
    }

    get effectiveMemoryLimitGB() {
        return this.memoryLimitGB ?? this.memoryGB;
    }

    transition(nextState) {
        const validTransitions = {
            [VMState.STOPPED]: [VMState.RUNNING],
            [VMState.RUNNING]: [VMState.STOPPED, VMState.PAUSED, VMState.FAILED],
            [VMState.PAUSED]: [VMState.RUNNING, VMState.STOPPED, VMState.FAILED],
            [VMState.FAILED]: [VMState.STOPPED]
        };

        if (!validTransitions[this.state].includes(nextState)) {
            throw new Error(
                `Invalid VM transition: ${this.state} -> ${nextState}`
            );
        }

        this.state = nextState;
    }

    setWorkload(cpu, memoryGB) {
        if (cpu < 0 || memoryGB < 0) {
            throw new ValidationError('Workload demand cannot be negative.');
        }

        this.cpuDemand = Math.min(cpu, this.effectiveCpuLimit);
        this.memoryDemandGB = Math.min(
            memoryGB,
            this.effectiveMemoryLimitGB
        );
    }

    recordMetric(metric) {
        this.metrics.push({
            timestamp: new Date().toISOString(),
            ...metric
        });

        if (this.metrics.length > 100) {
            this.metrics.shift();
        }
    }
}

class VirtualizationHost extends EventEmitter {
    constructor({
        id,
        cpuCores,
        memoryGB,
        storageGB,
        networkGbps,
        allowCpuOvercommit = true,
        allowMemoryOvercommit = true
    }) {
        super();

        if (cpuCores <= 0 || memoryGB <= 0) {
            throw new ValidationError(
                'Host CPU and memory must be positive.'
            );
        }

        this.id = id;
        this.cpuCores = cpuCores;
        this.memoryGB = memoryGB;
        this.storageGB = storageGB;
        this.networkGbps = networkGbps;

        this.allowCpuOvercommit = allowCpuOvercommit;
        this.allowMemoryOvercommit = allowMemoryOvercommit;

        this.vms = new Map();
        this.isolation = new IsolationPolicy();
        this.operationLog = [];
    }

    log(operation, details = {}) {
        const entry = {
            timestamp: new Date().toISOString(),
            host: this.id,
            operation,
            ...details
        };

        this.operationLog.push(entry);
        this.emit('operation', entry);
    }

    allocation() {
        const vms = [...this.vms.values()];

        return {
            vcpus: vms.reduce((sum, vm) => sum + vm.vcpus, 0),
            memoryGB: vms.reduce((sum, vm) => sum + vm.memoryGB, 0),
            storageGB: vms.reduce((sum, vm) => sum + vm.storageGB, 0),
            networkGbps: vms.reduce((sum, vm) => sum + vm.networkGbps, 0)
        };
    }

    ratios() {
        const allocation = this.allocation();

        return {
            cpu: allocation.vcpus / this.cpuCores,
            memory: allocation.memoryGB / this.memoryGB,
            storage: allocation.storageGB / this.storageGB,
            network: allocation.networkGbps / this.networkGbps
        };
    }

    admit(vm) {
        if (this.vms.has(vm.id)) {
            throw new AdmissionError(
                `VM ${vm.id} already exists on ${this.id}.`
            );
        }

        const current = this.allocation();

        const projected = {
            vcpus: current.vcpus + vm.vcpus,
            memoryGB: current.memoryGB + vm.memoryGB,
            storageGB: current.storageGB + vm.storageGB,
            networkGbps: current.networkGbps + vm.networkGbps
        };

        if (projected.storageGB > this.storageGB) {
            throw new AdmissionError(
                `Storage admission failed for ${vm.id}.`
            );
        }

        if (projected.networkGbps > this.networkGbps) {
            throw new AdmissionError(
                `Network admission failed for ${vm.id}.`
            );
        }

        if (
            projected.vcpus > this.cpuCores &&
            !this.allowCpuOvercommit
        ) {
            throw new AdmissionError(
                `CPU overcommitment is disabled on ${this.id}.`
            );
        }

        if (
            projected.memoryGB > this.memoryGB &&
            !this.allowMemoryOvercommit
        ) {
            throw new AdmissionError(
                `Memory overcommitment is disabled on ${this.id}.`
            );
        }

        this.vms.set(vm.id, vm);
        this.isolation.register(vm);

        this.log('vm-admitted', {
            vm: vm.id,
            projected
        });

        this.emit('vm-admitted', vm);
    }

    remove(vmId) {
        const vm = this.vms.get(vmId);

        if (!vm) {
            throw new Error(`Unknown VM ${vmId}.`);
        }

        if (vm.state === VMState.RUNNING) {
            throw new Error(
                `VM ${vmId} must be stopped before removal.`
            );
        }

        this.vms.delete(vmId);
        this.log('vm-removed', { vm: vmId });
    }

    start(vmId) {
        const vm = this.requireVM(vmId);
        vm.transition(VMState.RUNNING);

        this.log('vm-started', { vm: vmId });
        this.emit('vm-started', vm);
    }

    stop(vmId) {
        const vm = this.requireVM(vmId);

        if (vm.state === VMState.PAUSED) {
            vm.transition(VMState.STOPPED);
        } else if (vm.state === VMState.RUNNING) {
            vm.transition(VMState.STOPPED);
        }

        vm.balloonedMemoryGB = 0;

        this.log('vm-stopped', { vm: vmId });
        this.emit('vm-stopped', vm);
    }

    requireVM(vmId) {
        const vm = this.vms.get(vmId);

        if (!vm) {
            throw new Error(`Unknown VM ${vmId}.`);
        }

        return vm;
    }

    runningVMs() {
        return [...this.vms.values()].filter(
            vm => vm.state === VMState.RUNNING
        );
    }

    scheduleCPU() {
        const running = this.runningVMs();
        const allocation = new Map();

        for (const vm of running) {
            allocation.set(
                vm.id,
                Math.min(vm.cpuDemand, vm.cpuReservation)
            );
        }

        let remaining =
            this.cpuCores -
            [...allocation.values()].reduce(
                (sum, value) => sum + value,
                0
            );

        let active = running.filter(
            vm => vm.cpuDemand > allocation.get(vm.id)
        );

        while (remaining > 0.000001 && active.length > 0) {
            const totalShares = active.reduce(
                (sum, vm) => sum + vm.cpuShares,
                0
            );

            let distributed = 0;

            for (const vm of active) {
                const current = allocation.get(vm.id);
                const demand = vm.cpuDemand - current;
                const limit = vm.effectiveCpuLimit - current;

                const proportional =
                    remaining * vm.cpuShares / totalShares;

                const grant = Math.min(
                    proportional,
                    demand,
                    limit
                );

                allocation.set(vm.id, current + grant);
                distributed += grant;
            }

            if (distributed <= 0.000001) {
                break;
            }

            remaining -= distributed;

            active = active.filter(vm => {
                const current = allocation.get(vm.id);
                return (
                    vm.cpuDemand - current > 0.000001 &&
                    vm.effectiveCpuLimit - current > 0.000001
                );
            });
        }

        return allocation;
    }

    reclaimMemory() {
        const running = this.runningVMs();
        const totalDemand = running.reduce(
            (sum, vm) => sum + vm.memoryDemandGB,
            0
        );

        for (const vm of running) {
            vm.balloonedMemoryGB = 0;
        }

        if (totalDemand <= this.memoryGB) {
            return new Map(running.map(vm => [vm.id, 0]));
        }

        const deficit = totalDemand - this.memoryGB;

        const reclaimable = running.map(vm => ({
            vm,
            amount: Math.max(
                0,
                vm.memoryDemandGB - vm.memoryReservationGB
            )
        }));

        const totalReclaimable = reclaimable.reduce(
            (sum, item) => sum + item.amount,
            0
        );

        if (totalReclaimable <= 0) {
            for (const vm of running) {
                vm.transition(VMState.FAILED);
            }

            throw new Error(
                'Host has insufficient memory and cannot reclaim any non-reserved memory.'
            );
        }

        const result = new Map();

        for (const item of reclaimable) {
            const proportional =
                deficit * item.amount / totalReclaimable;

            const reclaim = Math.min(
                proportional,
                Math.max(
                    0,
                    item.vm.memoryGB - item.vm.memoryReservationGB
                )
            );

            item.vm.balloonedMemoryGB = reclaim;
            result.set(item.vm.id, reclaim);
        }

        return result;
    }

    schedule() {
        const cpu = this.scheduleCPU();
        const memoryReclaimed = this.reclaimMemory();

        const result = [];

        for (const vm of this.runningVMs()) {
            const cpuAllocated = cpu.get(vm.id) || 0;
            const reclaimed = memoryReclaimed.get(vm.id) || 0;

            const memoryAllocated = Math.max(
                0,
                vm.memoryDemandGB - reclaimed
            );

            const record = {
                vm: vm.id,
                cpuDemand: vm.cpuDemand,
                cpuAllocated,
                cpuThrottled:
                    cpuAllocated + 0.000001 < vm.cpuDemand,
                memoryDemandGB: vm.memoryDemandGB,
                memoryAllocatedGB: memoryAllocated,
                memoryReclaimedGB: reclaimed,
                memoryPressure:
                    reclaimed / vm.memoryGB
            };

            vm.recordMetric(record);
            result.push(record);
        }

        this.log('resource-cycle', {
            allocations: result
        });

        this.emit('resource-cycle', result);

        return result;
    }

    health() {
        const running = this.runningVMs();

        const cpuDemand = running.reduce(
            (sum, vm) => sum + vm.cpuDemand,
            0
        );

        const memoryDemand = running.reduce(
            (sum, vm) => sum + vm.memoryDemandGB,
            0
        );

        const ratios = this.ratios();

        return {
            host: this.id,
            runningVMs: running.length,
            cpuUtilization: Math.min(1, cpuDemand / this.cpuCores),
            memoryUtilization: Math.min(
                1,
                memoryDemand / this.memoryGB
            ),
            cpuOvercommitRatio: ratios.cpu,
            memoryOvercommitRatio: ratios.memory,
            warnings: [
                ...(ratios.cpu > 1
                    ? ['CPU overcommitment is active.']
                    : []),
                ...(ratios.memory > 1
                    ? ['Memory overcommitment is active.']
                    : []),
                ...(memoryDemand / this.memoryGB >= 0.9
                    ? ['Memory demand is approaching physical capacity.']
                    : []),
                ...(cpuDemand / this.cpuCores >= 0.9
                    ? ['CPU demand is approaching physical capacity.']
                    : [])
            ]
        };
    }

    canMigrateTo(vmId, destination) {
        const vm = this.requireVM(vmId);

        const current = destination.allocation();

        if (
            current.storageGB + vm.storageGB >
            destination.storageGB
        ) {
            return {
                allowed: false,
                reason: 'Destination storage is insufficient.'
            };
        }

        if (
            current.networkGbps + vm.networkGbps >
            destination.networkGbps
        ) {
            return {
                allowed: false,
                reason: 'Destination network capacity is insufficient.'
            };
        }

        if (
            current.vcpus + vm.vcpus > destination.cpuCores &&
            !destination.allowCpuOvercommit
        ) {
            return {
                allowed: false,
                reason: 'Destination rejects CPU overcommitment.'
            };
        }

        if (
            current.memoryGB + vm.memoryGB > destination.memoryGB &&
            !destination.allowMemoryOvercommit
        ) {
            return {
                allowed: false,
                reason: 'Destination rejects memory overcommitment.'
            };
        }

        return {
            allowed: true,
            reason: 'Destination admission checks passed.'
        };
    }
}

function printHeader(title) {
    console.log(`\n=== ${title} ===`);
}

function printResourceTable(rows) {
    console.table(
        rows.map(row => ({
            VM: row.vm,
            'CPU demand': row.cpuDemand.toFixed(2),
            'CPU allocated': row.cpuAllocated.toFixed(2),
            'CPU throttled': row.cpuThrottled,
            'RAM demand GB': row.memoryDemandGB.toFixed(2),
            'RAM allocated GB': row.memoryAllocatedGB.toFixed(2),
            'RAM reclaimed GB': row.memoryReclaimedGB.toFixed(2),
            'Memory pressure': `${(row.memoryPressure * 100).toFixed(1)}%`
        }))
    );
}

async function collectWorkload(vm, interval) {
    /*
     * Promise-based collection models asynchronous monitoring without adding
     * a package. Real host agents would retrieve counters from hypervisor APIs,
     * operating-system interfaces, or telemetry services.
     */
    await new Promise(resolve => setTimeout(resolve, 15));

    const wave = Math.sin(interval / 2 + vm.id.length);
    const cpuFactor = Math.max(0.25, 0.65 + wave * 0.3);
    const memoryFactor = Math.max(
        0.35,
        0.70 + Math.cos(interval / 3 + vm.id.length) * 0.15
    );

    vm.setWorkload(
        vm.vcpus * cpuFactor,
        vm.memoryGB * memoryFactor
    );

    return {
        vm: vm.id,
        cpuDemand: vm.cpuDemand,
        memoryDemandGB: vm.memoryDemandGB
    };
}

async function runMonitoringCycle(host, interval) {
    const running = host.runningVMs();

    await Promise.all(
        running.map(vm => collectWorkload(vm, interval))
    );

    return host.schedule();
}

async function demonstrateEventDrivenHostManagement() {
    printHeader('Event-Driven Host Management');

    const host = new VirtualizationHost({
        id: 'hv-node-a',
        cpuCores: 8,
        memoryGB: 32,
        storageGB: 1000,
        networkGbps: 20
    });

    host.on('operation', entry => {
        console.log(
            `[event] ${entry.operation}`,
            entry.vm ? `vm=${entry.vm}` : ''
        );
    });

    host.on('vm-admitted', vm => {
        console.log(
            `[event] VM ${vm.id} admitted into ${host.id}.`
        );
    });

    host.on('resource-cycle', allocations => {
        const constrained = allocations.filter(
            item =>
                item.cpuThrottled ||
                item.memoryReclaimedGB > 0
        );

        if (constrained.length > 0) {
            console.log(
                `[event] ${constrained.length} VM(s) experienced resource contention.`
            );
        }
    });

    const vms = [
        new VirtualMachine({
            id: 'web-tier',
            vcpus: 3,
            memoryGB: 8,
            storageGB: 80,
            networkGbps: 2,
            cpuShares: 200,
            networkSegment: 'frontend'
        }),
        new VirtualMachine({
            id: 'transaction-tier',
            vcpus: 4,
            memoryGB: 14,
            storageGB: 150,
            networkGbps: 4,
            cpuShares: 500,
            cpuReservation: 2,
            memoryReservationGB: 8,
            networkSegment: 'application'
        }),
        new VirtualMachine({
            id: 'analytics-tier',
            vcpus: 4,
            memoryGB: 12,
            storageGB: 200,
            networkGbps: 3,
            cpuShares: 100,
            networkSegment: 'analytics'
        })
    ];

    for (const vm of vms) {
        host.admit(vm);
        host.start(vm.id);
    }

    for (let interval = 1; interval <= 5; interval++) {
        const allocations = await runMonitoringCycle(
            host,
            interval
        );

        console.log(`\nMonitoring interval ${interval}`);
        printResourceTable(allocations);
    }

    console.log('\nHost health');
    console.table(host.health());
}

function demonstrateIsolationPolicy() {
    printHeader('Isolation Policy');

    const host = new VirtualizationHost({
        id: 'hv-secure',
        cpuCores: 4,
        memoryGB: 16,
        storageGB: 500,
        networkGbps: 10
    });

    const tenantA = new VirtualMachine({
        id: 'tenant-a',
        vcpus: 1,
        memoryGB: 4,
        storageGB: 40,
        networkGbps: 1,
        networkSegment: 'tenant-a'
    });

    const tenantB = new VirtualMachine({
        id: 'tenant-b',
        vcpus: 1,
        memoryGB: 4,
        storageGB: 40,
        networkGbps: 1,
        networkSegment: 'tenant-b'
    });

    host.admit(tenantA);
    host.admit(tenantB);

    console.log(
        'Before explicit policy:',
        host.isolation.canCommunicate(tenantA, tenantB)
    );

    host.isolation.allowExplicitCommunication(
        tenantA.id,
        tenantB.id
    );

    console.log(
        'After explicit policy:',
        host.isolation.canCommunicate(tenantA, tenantB)
    );

    console.log(
        'Isolation record:',
        host.isolation.describe(tenantA)
    );
}

function demonstrateAdmissionFailure() {
    printHeader('Admission Control Failure');

    const host = new VirtualizationHost({
        id: 'hv-conservative',
        cpuCores: 4,
        memoryGB: 8,
        storageGB: 200,
        networkGbps: 5,
        allowCpuOvercommit: false,
        allowMemoryOvercommit: false
    });

    host.admit(
        new VirtualMachine({
            id: 'vm-one',
            vcpus: 4,
            memoryGB: 8,
            storageGB: 50,
            networkGbps: 1
        })
    );

    try {
        host.admit(
            new VirtualMachine({
                id: 'vm-two',
                vcpus: 2,
                memoryGB: 4,
                storageGB: 50,
                networkGbps: 1
            })
        );
    } catch (error) {
        if (error instanceof AdmissionError) {
            console.log(
                `Expected admission rejection: ${error.message}`
            );
        } else {
            throw error;
        }
    }
}

function demonstrateMigrationAdmission() {
    printHeader('Migration Admission');

    const source = new VirtualizationHost({
        id: 'hv-source',
        cpuCores: 8,
        memoryGB: 32,
        storageGB: 500,
        networkGbps: 10
    });

    const destination = new VirtualizationHost({
        id: 'hv-destination',
        cpuCores: 8,
        memoryGB: 32,
        storageGB: 500,
        networkGbps: 10,
        allowCpuOvercommit: false,
        allowMemoryOvercommit: false
    });

    const vm = new VirtualMachine({
        id: 'migration-candidate',
        vcpus: 4,
        memoryGB: 12,
        storageGB: 100,
        networkGbps: 2,
        memoryReservationGB: 8
    });

    source.admit(vm);

    const decision = source.canMigrateTo(
        vm.id,
        destination
    );

    console.log(decision);
}

async function main() {
    console.log(
        'SERVER VIRTUALIZATION: EVENT-DRIVEN RESOURCE MANAGEMENT'
    );

    demonstrateIsolationPolicy();
    demonstrateAdmissionFailure();
    demonstrateMigrationAdmission();
    await demonstrateEventDrivenHostManagement();

    printHeader('Operational Boundary');

    console.log(
        'The host owns physical capacity and admission decisions. ' +
        'Each VM owns a virtual hardware contract and workload demand. ' +
        'The isolation policy prevents implicit cross-VM access. ' +
        'The scheduler shares constrained CPU and memory, while overcommitment ' +
        'allows virtual allocation to exceed physical capacity only when the ' +
        'host policy permits it.'
    );
}

main().catch(error => {
    console.error(`Fatal virtualization-management error: ${error.message}`);
    process.exitCode = 1;
});
