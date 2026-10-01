"use strict";

/*
 * Virtualization Fundamentals
 *
 * This Node.js program models virtualization from the perspective of a
 * hypervisor: physical hosts provide resources, VMs consume abstracted
 * resources, and a scheduler decides where workloads can run.
 *
 * Run with:
 *   node virtualization_fundamentals.js
 */

class PhysicalServer {
    constructor({
        name,
        cpuCores,
        memoryGB,
        storageGB,
        networkGbps,
        powerWatts
    }) {
        if (!Number.isInteger(cpuCores) || cpuCores <= 0) {
            throw new Error("Physical CPU core count must be a positive integer.");
        }

        if (memoryGB <= 0 || storageGB <= 0) {
            throw new Error("Physical memory and storage must be positive.");
        }

        this.name = name;
        this.cpuCores = cpuCores;
        this.memoryGB = memoryGB;
        this.storageGB = storageGB;
        this.networkGbps = networkGbps;
        this.powerWatts = powerWatts;
        this.vms = new Map();
    }

    allocatedCPU() {
        let total = 0;

        for (const vm of this.vms.values()) {
            total += vm.vCPU;
        }

        return total;
    }

    allocatedMemory() {
        let total = 0;

        for (const vm of this.vms.values()) {
            total += vm.memoryGB;
        }

        return total;
    }

    allocatedStorage() {
        let total = 0;

        for (const vm of this.vms.values()) {
            total += vm.storageGB;
        }

        return total;
    }

    utilization() {
        return {
            cpu: this.allocatedCPU() / this.cpuCores,
            memory: this.allocatedMemory() / this.memoryGB,
            storage: this.allocatedStorage() / this.storageGB
        };
    }

    canHost(vm) {
        if (vm.vCPU <= 0 || vm.memoryGB <= 0 || vm.storageGB <= 0) {
            return {
                allowed: false,
                reason: "VM resource requests must be positive."
            };
        }

        if (vm.vCPU > this.cpuCores - this.allocatedCPU()) {
            return {
                allowed: false,
                reason: `Insufficient CPU on ${this.name}.`
            };
        }

        if (vm.memoryGB > this.memoryGB - this.allocatedMemory()) {
            return {
                allowed: false,
                reason: `Insufficient memory on ${this.name}.`
            };
        }

        if (vm.storageGB > this.storageGB - this.allocatedStorage()) {
            return {
                allowed: false,
                reason: `Insufficient storage on ${this.name}.`
            };
        }

        return {
            allowed: true,
            reason: "Resources available."
        };
    }

    deploy(vm) {
        const result = this.canHost(vm);

        if (!result.allowed) {
            throw new Error(result.reason);
        }

        if (this.vms.has(vm.name)) {
            throw new Error(`VM ${vm.name} already exists on ${this.name}.`);
        }

        this.vms.set(vm.name, vm);
        vm.host = this.name;
    }

    remove(vmName) {
        if (!this.vms.has(vmName)) {
            throw new Error(`${vmName} is not hosted on ${this.name}.`);
        }

        const vm = this.vms.get(vmName);
        this.vms.delete(vmName);
        vm.host = null;

        return vm;
    }
}


class VirtualMachine {
    constructor({
        name,
        operatingSystem,
        vCPU,
        memoryGB,
        storageGB,
        workload
    }) {
        this.name = name;
        this.operatingSystem = operatingSystem;
        this.vCPU = vCPU;
        this.memoryGB = memoryGB;
        this.storageGB = storageGB;
        this.workload = workload;
        this.host = null;
        this.running = false;
    }

    start() {
        if (!this.host) {
            throw new Error(`${this.name} cannot start without a host.`);
        }

        this.running = true;
    }

    stop() {
        this.running = false;
    }
}


class Hypervisor {
    constructor(name) {
        this.name = name;
        this.hosts = new Map();
    }

    addHost(host) {
        if (this.hosts.has(host.name)) {
            throw new Error(`Host ${host.name} already exists.`);
        }

        this.hosts.set(host.name, host);
    }

    chooseHost(vm) {
        const candidates = [];

        for (const host of this.hosts.values()) {
            const result = host.canHost(vm);

            if (!result.allowed) {
                continue;
            }

            const futureCPU =
                (host.allocatedCPU() + vm.vCPU) / host.cpuCores;

            const futureMemory =
                (host.allocatedMemory() + vm.memoryGB) / host.memoryGB;

            /*
             * The scheduler chooses a host with the smallest combined
             * projected CPU and memory utilization. This is a simplified
             * placement policy, not a production hypervisor algorithm.
             */
            candidates.push({
                host,
                score: futureCPU + futureMemory
            });
        }

        candidates.sort((a, b) => a.score - b.score);

        return candidates.length > 0 ? candidates[0].host : null;
    }

    deploy(vm) {
        const host = this.chooseHost(vm);

        if (!host) {
            throw new Error(`No host can accommodate VM ${vm.name}.`);
        }

        host.deploy(vm);
        return host;
    }

    migrate(vmName, sourceName, destinationName) {
        const source = this.hosts.get(sourceName);
        const destination = this.hosts.get(destinationName);

        if (!source || !destination) {
            throw new Error("Migration references an unknown host.");
        }

        const vm = source.vms.get(vmName);

        if (!vm) {
            throw new Error(
                `${vmName} is not present on ${sourceName}.`
            );
        }

        const capacity = destination.canHost(vm);

        if (!capacity.allowed) {
            throw new Error(
                `Migration rejected: ${capacity.reason}`
            );
        }

        source.remove(vmName);
        destination.deploy(vm);
    }
}


function printHost(host) {
    const utilization = host.utilization();

    console.log(`\nHost: ${host.name}`);
    console.log(
        `Hardware: ${host.cpuCores} CPU cores, ` +
        `${host.memoryGB} GB RAM, ${host.storageGB} GB storage`
    );

    console.log(
        `Allocated: ${host.allocatedCPU()} vCPU, ` +
        `${host.allocatedMemory()} GB RAM, ` +
        `${host.allocatedStorage()} GB storage`
    );

    console.log(
        `Utilization: CPU=${(utilization.cpu * 100).toFixed(0)}%, ` +
        `RAM=${(utilization.memory * 100).toFixed(0)}%, ` +
        `Storage=${(utilization.storage * 100).toFixed(0)}%`
    );

    for (const vm of host.vms.values()) {
        console.log(
            `  ${vm.name}: ${vm.operatingSystem}, ` +
            `${vm.vCPU} vCPU, ${vm.memoryGB} GB RAM, ` +
            `${vm.storageGB} GB storage, ` +
            `${vm.running ? "running" : "stopped"}`
        );
    }
}


async function simulateMonitoring(hypervisor) {
    /*
     * JavaScript's event loop makes periodic monitoring a natural example
     * of event-driven infrastructure tooling.
     */
    return new Promise((resolve) => {
        let sample = 0;

        const timer = setInterval(() => {
            sample++;

            console.log(`\nMonitoring sample ${sample}`);

            for (const host of hypervisor.hosts.values()) {
                const utilization = host.utilization();

                console.log(
                    `${host.name}: ` +
                    `CPU ${(utilization.cpu * 100).toFixed(1)}%, ` +
                    `RAM ${(utilization.memory * 100).toFixed(1)}%`
                );
            }

            if (sample === 2) {
                clearInterval(timer);
                resolve();
            }
        }, 100);
    });
}


function demonstrateAbstraction() {
    console.log("\n=== Resource Abstraction ===");

    const host = new PhysicalServer({
        name: "physical-host-01",
        cpuCores: 16,
        memoryGB: 64,
        storageGB: 1000,
        networkGbps: 10,
        powerWatts: 500
    });

    const applicationVM = new VirtualMachine({
        name: "application-vm",
        operatingSystem: "Linux",
        vCPU: 4,
        memoryGB: 8,
        storageGB: 100,
        workload: "Application server"
    });

    const databaseVM = new VirtualMachine({
        name: "database-vm",
        operatingSystem: "Linux",
        vCPU: 6,
        memoryGB: 20,
        storageGB: 300,
        workload: "Database server"
    });

    host.deploy(applicationVM);
    host.deploy(databaseVM);

    applicationVM.start();
    databaseVM.start();

    printHost(host);

    console.log(
        "\nThe guest sees vCPUs and virtual memory. " +
        "The host owns the underlying physical resources."
    );
}


function demonstrateConsolidation() {
    console.log("\n=== Consolidation ===");

    const hypervisor = new Hypervisor("node-hypervisor");

    hypervisor.addHost(
        new PhysicalServer({
            name: "node-01",
            cpuCores: 16,
            memoryGB: 64,
            storageGB: 2000,
            networkGbps: 10,
            powerWatts: 500
        })
    );

    hypervisor.addHost(
        new PhysicalServer({
            name: "node-02",
            cpuCores: 16,
            memoryGB: 64,
            storageGB: 2000,
            networkGbps: 10,
            powerWatts: 500
        })
    );

    const workloads = [
        ["web-01", 4, 8, 100],
        ["web-02", 4, 8, 100],
        ["api-01", 4, 12, 150],
        ["database-01", 6, 20, 400],
        ["worker-01", 2, 8, 150]
    ];

    for (const [name, cpu, memory, storage] of workloads) {
        const vm = new VirtualMachine({
            name,
            operatingSystem: "Linux",
            vCPU: cpu,
            memoryGB: memory,
            storageGB: storage,
            workload: "Production workload"
        });

        hypervisor.deploy(vm).name;
        vm.start();
    }

    for (const host of hypervisor.hosts.values()) {
        printHost(host);
    }

    return hypervisor;
}


function demonstrateFailureHandling() {
    console.log("\n=== Capacity Validation ===");

    const host = new PhysicalServer({
        name: "small-host",
        cpuCores: 4,
        memoryGB: 8,
        storageGB: 100,
        networkGbps: 1,
        powerWatts: 150
    });

    const oversizedVM = new VirtualMachine({
        name: "oversized-vm",
        operatingSystem: "Linux",
        vCPU: 8,
        memoryGB: 16,
        storageGB: 20,
        workload: "Invalid workload"
    });

    const decision = host.canHost(oversizedVM);

    console.log(`Allowed: ${decision.allowed}`);
    console.log(`Reason: ${decision.reason}`);

    try {
        host.deploy(oversizedVM);
    } catch (error) {
        console.log(`Deployment rejected safely: ${error.message}`);
    }
}


async function main() {
    console.log("VIRTUALIZATION FUNDAMENTALS");
    console.log("===========================");

    demonstrateAbstraction();

    const hypervisor = demonstrateConsolidation();

    demonstrateFailureHandling();

    console.log("\n=== VM Migration ===");

    const hosts = [...hypervisor.hosts.values()];
    const vm = hosts[0].vms.values().next().value;

    if (vm) {
        console.log(`Before migration: ${vm.name} -> ${vm.host}`);

        const destination =
            hosts.find((host) => host.name !== vm.host);

        if (destination) {
            hypervisor.migrate(
                vm.name,
                vm.host,
                destination.name
            );

            console.log(`After migration: ${vm.name} -> ${vm.host}`);
        }
    }

    console.log("\n=== Event-Driven Monitoring ===");
    await simulateMonitoring(hypervisor);

    console.log("\n=== Virtualization Benefits ===");
    console.log(
        "Resource pooling can increase utilization by allowing multiple " +
        "workloads to share the same physical host."
    );
    console.log(
        "The abstraction also enables workload mobility and centralized " +
        "resource management, while introducing hypervisor overhead and " +
        "additional operational complexity."
    );
}


main().catch((error) => {
    console.error(`Fatal simulation error: ${error.message}`);
    process.exitCode = 1;
});
