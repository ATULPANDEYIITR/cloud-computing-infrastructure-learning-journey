'use strict';

/*
 * Containers vs Virtual Machines
 *
 * This Node.js program models infrastructure decisions using JavaScript's
 * object-oriented and event-driven features.
 *
 * It focuses on:
 *   - isolation
 *   - performance
 *   - portability
 *   - resource utilization
 *   - workload placement
 *
 * Run with:
 *   node containers-vs-vms.js
 */

const EventEmitter = require('node:events');

const WorkloadType = Object.freeze({
    WEB_API: 'web-api',
    DATABASE: 'database',
    LEGACY: 'legacy-application',
    BATCH: 'batch-job',
    MICROSERVICE: 'microservice'
});

function assertPositive(value, fieldName) {
    if (!Number.isFinite(value) || value <= 0) {
        throw new TypeError(`${fieldName} must be a positive number`);
    }
}

class Workload {
    constructor({
        name,
        type,
        cpu,
        memoryGb,
        storageGb,
        requiresCustomKernel = false,
        architecture = 'x86_64'
    }) {
        if (!name || typeof name !== 'string') {
            throw new TypeError('Workload name is required');
        }

        assertPositive(cpu, 'CPU request');
        assertPositive(memoryGb, 'Memory request');
        if (!Number.isFinite(storageGb) || storageGb < 0) {
            throw new TypeError('Storage must be zero or greater');
        }

        this.name = name;
        this.type = type;
        this.cpu = cpu;
        this.memoryGb = memoryGb;
        this.storageGb = storageGb;
        this.requiresCustomKernel = requiresCustomKernel;
        this.architecture = architecture;
    }
}

class RuntimeInstance extends EventEmitter {
    constructor(name, workload, limits) {
        super();

        assertPositive(limits.cpu, 'CPU limit');
        assertPositive(limits.memoryGb, 'Memory limit');

        if (limits.cpu < workload.cpu) {
            throw new RangeError(
                `${name}: CPU limit is smaller than workload request`
            );
        }

        if (limits.memoryGb < workload.memoryGb) {
            throw new RangeError(
                `${name}: memory limit is smaller than workload request`
            );
        }

        this.name = name;
        this.workload = workload;
        this.cpuLimit = limits.cpu;
        this.memoryLimitGb = limits.memoryGb;
        this.running = false;
        this.host = null;
    }

    start() {
        if (this.running) {
            throw new Error(`${this.name} is already running`);
        }

        this.running = true;
        this.emit('started', {
            name: this.name,
            timestamp: new Date().toISOString()
        });
    }

    stop(reason = 'normal shutdown') {
        if (!this.running) {
            return;
        }

        this.running = false;
        this.emit('stopped', {
            name: this.name,
            reason,
            timestamp: new Date().toISOString()
        });
    }
}

class Container extends RuntimeInstance {
    constructor(name, workload, limits) {
        super(name, workload, limits);

        this.kind = 'container';
        this.kernelBoundary = 'shared-host-kernel';
        this.startupMs = 700;
        this.memoryOverheadGb = 0.08;
        this.cpuOverhead = 0.02;
        this.isolationScore = 0.72;
        this.portabilityScore = 0.95;
    }

    canRunOn(host) {
        return host.supportsContainerRuntime &&
            host.architecture === this.workload.architecture;
    }
}

class VirtualMachine extends RuntimeInstance {
    constructor(name, workload, limits, guestOs = 'Linux') {
        super(name, workload, limits);

        this.kind = 'virtual-machine';
        this.guestOs = guestOs;
        this.kernelBoundary = 'guest-kernel';
        this.startupMs = 22000;
        this.memoryOverheadGb = 0.65;
        this.cpuOverhead = 0.20;
        this.isolationScore = 0.96;
        this.portabilityScore = 0.82;
    }

    canRunOn(host) {
        return host.supportsHypervisor &&
            host.architecture === this.workload.architecture;
    }
}

class ComputeHost extends EventEmitter {
    constructor({
        name,
        cpu,
        memoryGb,
        storageGb,
        architecture = 'x86_64',
        supportsContainerRuntime = true,
        supportsHypervisor = true
    }) {
        super();

        assertPositive(cpu, 'Host CPU');
        assertPositive(memoryGb, 'Host memory');
        assertPositive(storageGb, 'Host storage');

        this.name = name;
        this.cpu = cpu;
        this.memoryGb = memoryGb;
        this.storageGb = storageGb;
        this.architecture = architecture;
        this.supportsContainerRuntime = supportsContainerRuntime;
        this.supportsHypervisor = supportsHypervisor;
        this.instances = new Map();
    }

    get allocatedCpu() {
        return [...this.instances.values()]
            .reduce((sum, instance) => sum + instance.cpuLimit, 0);
    }

    get allocatedMemoryGb() {
        return [...this.instances.values()]
            .reduce((sum, instance) => sum + instance.memoryLimitGb, 0);
    }

    get allocatedStorageGb() {
        return [...this.instances.values()]
            .reduce(
                (sum, instance) => sum + instance.workload.storageGb,
                0
            );
    }

    deploy(instance) {
        if (this.instances.has(instance.name)) {
            throw new Error(`Duplicate instance name: ${instance.name}`);
        }

        if (!instance.canRunOn(this)) {
            throw new Error(
                `${instance.name} cannot run on ${this.name}: incompatible runtime`
            );
        }

        const cpuAfter = this.allocatedCpu + instance.cpuLimit;
        const memoryAfter =
            this.allocatedMemoryGb + instance.memoryLimitGb;
        const storageAfter =
            this.allocatedStorageGb + instance.workload.storageGb;

        if (cpuAfter > this.cpu) {
            throw new Error(
                `CPU capacity exceeded on ${this.name}: ` +
                `${cpuAfter}/${this.cpu}`
            );
        }

        if (memoryAfter > this.memoryGb) {
            throw new Error(
                `Memory capacity exceeded on ${this.name}: ` +
                `${memoryAfter}/${this.memoryGb} GB`
            );
        }

        if (storageAfter > this.storageGb) {
            throw new Error(
                `Storage capacity exceeded on ${this.name}: ` +
                `${storageAfter}/${this.storageGb} GB`
            );
        }

        this.instances.set(instance.name, instance);
        instance.host = this.name;

        this.emit('deployed', {
            host: this.name,
            instance: instance.name,
            kind: instance.kind
        });
    }

    utilization() {
        return {
            cpu: this.allocatedCpu / this.cpu,
            memory: this.allocatedMemoryGb / this.memoryGb,
            storage: this.allocatedStorageGb / this.storageGb
        };
    }
}

class PlacementPolicy {
    static evaluate(workload) {
        if (workload.requiresCustomKernel) {
            return {
                recommendation: 'virtual-machine',
                reason:
                    'The workload needs kernel independence from the host.'
            };
        }

        if (workload.type === WorkloadType.LEGACY) {
            return {
                recommendation: 'virtual-machine',
                reason:
                    'Legacy software may depend on a complete guest OS.'
            };
        }

        if (
            workload.type === WorkloadType.WEB_API ||
            workload.type === WorkloadType.BATCH ||
            workload.type === WorkloadType.MICROSERVICE
        ) {
            return {
                recommendation: 'container',
                reason:
                    'Application workloads benefit from low overhead and rapid startup.'
            };
        }

        if (workload.type === WorkloadType.DATABASE) {
            return {
                recommendation: 'depends',
                reason:
                    'Database placement depends on storage, kernel, ' +
                    'isolation, operational, and performance requirements.'
            };
        }

        return {
            recommendation: 'depends',
            reason: 'The workload requires additional analysis.'
        };
    }
}

function wait(milliseconds) {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
}

async function demonstrateEventDrivenLifecycle() {
    console.log('\n=== Event-driven lifecycle ===');

    const workload = new Workload({
        name: 'payments-api',
        type: WorkloadType.WEB_API,
        cpu: 1,
        memoryGb: 0.75,
        storageGb: 3
    });

    const container = new Container(
        'payments-api-container',
        workload,
        { cpu: 1, memoryGb: 0.75 }
    );

    container.on('started', event => {
        console.log(
            `${event.name} emitted started at ${event.timestamp}`
        );
    });

    container.on('stopped', event => {
        console.log(
            `${event.name} emitted stopped: ${event.reason}`
        );
    });

    container.start();
    await wait(50);
    container.stop('health-check demonstration');
}

function compareRuntimeModels() {
    console.log('\n=== Runtime comparison ===');

    const workload = new Workload({
        name: 'catalog-service',
        type: WorkloadType.MICROSERVICE,
        cpu: 1,
        memoryGb: 1,
        storageGb: 5
    });

    const container = new Container(
        'catalog-container',
        workload,
        { cpu: 1, memoryGb: 1 }
    );

    const vm = new VirtualMachine(
        'catalog-vm',
        workload,
        { cpu: 1, memoryGb: 1 }
    );

    const rows = [
        {
            property: 'Kernel boundary',
            container: container.kernelBoundary,
            vm: vm.kernelBoundary
        },
        {
            property: 'Startup',
            container: `${container.startupMs} ms`,
            vm: `${vm.startupMs} ms`
        },
        {
            property: 'Memory overhead',
            container: `${container.memoryOverheadGb} GB`,
            vm: `${vm.memoryOverheadGb} GB`
        },
        {
            property: 'Isolation score',
            container: container.isolationScore,
            vm: vm.isolationScore
        },
        {
            property: 'Portability score',
            container: container.portabilityScore,
            vm: vm.portabilityScore
        }
    ];

    console.table(rows);
}

function demonstrateResourcePacking() {
    console.log('\n=== Resource packing ===');

    const host = new ComputeHost({
        name: 'node-01',
        cpu: 16,
        memoryGb: 32,
        storageGb: 500
    });

    for (let index = 1; index <= 12; index += 1) {
        const workload = new Workload({
            name: `web-${index}`,
            type: WorkloadType.WEB_API,
            cpu: 1,
            memoryGb: 1,
            storageGb: 4
        });

        const container = new Container(
            `container-${index}`,
            workload,
            { cpu: 1, memoryGb: 1 }
        );

        host.deploy(container);
    }

    console.log('Container host utilization:', host.utilization());
}

function demonstrateWorkloadPolicies() {
    console.log('\n=== Workload placement policy ===');

    const workloads = [
        new Workload({
            name: 'customer-api',
            type: WorkloadType.WEB_API,
            cpu: 1,
            memoryGb: 1,
            storageGb: 5
        }),
        new Workload({
            name: 'old-reporting-system',
            type: WorkloadType.LEGACY,
            cpu: 2,
            memoryGb: 4,
            storageGb: 20,
            requiresCustomKernel: true
        }),
        new Workload({
            name: 'warehouse-database',
            type: WorkloadType.DATABASE,
            cpu: 4,
            memoryGb: 16,
            storageGb: 300
        })
    ];

    for (const workload of workloads) {
        const decision = PlacementPolicy.evaluate(workload);

        console.log(
            `${workload.name}: ${decision.recommendation} -> ${decision.reason}`
        );
    }
}

function demonstrateFailureAndSecurity() {
    console.log('\n=== Failure and security considerations ===');

    const workload = new Workload({
        name: 'untrusted-job',
        type: WorkloadType.BATCH,
        cpu: 1,
        memoryGb: 1,
        storageGb: 2
    });

    const container = new Container(
        'untrusted-job-container',
        workload,
        { cpu: 1, memoryGb: 1 }
    );

    const vm = new VirtualMachine(
        'untrusted-job-vm',
        workload,
        { cpu: 1, memoryGb: 1 }
    );

    console.log(
        `Container kernel boundary: ${container.kernelBoundary}`
    );
    console.log(`VM kernel boundary: ${vm.kernelBoundary}`);

    console.log(
        'A container should not be treated as an automatic security boundary ' +
        'equivalent to a separate kernel. Capabilities, namespaces, seccomp, ' +
        'read-only filesystems, resource limits, and image provenance matter.'
    );

    console.log(
        'A VM adds a guest OS boundary, but hypervisor vulnerabilities, host ' +
        'configuration, exposed devices, and management-plane compromise remain risks.'
    );
}

async function main() {
    console.log('Containers vs Virtual Machines');
    console.log('=============================');

    compareRuntimeModels();
    demonstrateResourcePacking();
    demonstrateWorkloadPolicies();
    demonstrateFailureAndSecurity();
    await demonstrateEventDrivenLifecycle();

    console.log('\n=== Architectural conclusion ===');
    console.log(
        'Containers and VMs are complementary isolation mechanisms. ' +
        'Containers optimize application packaging, startup speed, and density. ' +
        'VMs provide stronger guest operating-system isolation and support workloads ' +
        'that require independent kernels.'
    );
}

main().catch(error => {
    console.error(`Execution failed: ${error.message}`);
    process.exitCode = 1;
});
