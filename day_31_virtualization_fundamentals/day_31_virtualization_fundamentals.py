"""
Virtualization Fundamentals
============================

A self-contained executable model of physical servers, virtual machines,
resource abstraction, allocation, isolation, consolidation, overcommitment,
and virtualization benefits.

The simulation deliberately models virtualization concepts rather than
attempting to emulate a real hypervisor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math


@dataclass
class PhysicalServer:
    """Represents a physical host and the resources exposed by its hardware."""

    name: str
    cpu_cores: int
    memory_gb: float
    storage_gb: float
    network_gbps: float
    power_watts: float
    vms: Dict[str, "VirtualMachine"] = field(default_factory=dict)

    def allocated_cpu(self) -> float:
        return sum(vm.vcpu for vm in self.vms.values())

    def allocated_memory(self) -> float:
        return sum(vm.memory_gb for vm in self.vms.values())

    def allocated_storage(self) -> float:
        return sum(vm.storage_gb for vm in self.vms.values())

    def available_cpu(self) -> float:
        return self.cpu_cores - self.allocated_cpu()

    def available_memory(self) -> float:
        return self.memory_gb - self.allocated_memory()

    def available_storage(self) -> float:
        return self.storage_gb - self.allocated_storage()

    def utilization(self) -> Dict[str, float]:
        return {
            "cpu": self.allocated_cpu() / self.cpu_cores if self.cpu_cores else 0,
            "memory": self.allocated_memory() / self.memory_gb if self.memory_gb else 0,
            "storage": (
                self.allocated_storage() / self.storage_gb
                if self.storage_gb
                else 0
            ),
        }

    def can_allocate(self, vm: "VirtualMachine") -> Tuple[bool, str]:
        """Check whether the host has enough physical resources for a VM."""

        if vm.vcpu <= 0 or vm.memory_gb <= 0 or vm.storage_gb <= 0:
            return False, "VM resources must be positive."

        if vm.vcpu > self.available_cpu():
            return False, f"Insufficient CPU on {self.name}."

        if vm.memory_gb > self.available_memory():
            return False, f"Insufficient memory on {self.name}."

        if vm.storage_gb > self.available_storage():
            return False, f"Insufficient storage on {self.name}."

        return True, "Resources available."

    def deploy(self, vm: "VirtualMachine") -> None:
        allowed, reason = self.can_allocate(vm)
        if not allowed:
            raise ValueError(reason)

        self.vms[vm.name] = vm
        vm.host = self.name

    def remove_vm(self, vm_name: str) -> "VirtualMachine":
        if vm_name not in self.vms:
            raise KeyError(f"VM {vm_name!r} is not hosted by {self.name}.")
        vm = self.vms.pop(vm_name)
        vm.host = None
        return vm


@dataclass
class VirtualMachine:
    """
    Represents a VM's logical hardware allocation.

    A VM sees virtual CPUs, virtual memory, and virtual storage rather than
    directly managing the physical server's hardware resources.
    """

    name: str
    operating_system: str
    vcpu: int
    memory_gb: float
    storage_gb: float
    workload: str
    host: Optional[str] = None
    running: bool = False

    def start(self) -> None:
        if self.host is None:
            raise RuntimeError(f"{self.name} has no physical host.")
        self.running = True

    def stop(self) -> None:
        self.running = False


class Hypervisor:
    """
    Resource abstraction layer between physical hardware and VMs.

    This is a conceptual scheduler, not a real type-1 or type-2 hypervisor.
    """

    def __init__(self, name: str):
        self.name = name
        self.hosts: Dict[str, PhysicalServer] = {}

    def register_host(self, host: PhysicalServer) -> None:
        if host.name in self.hosts:
            raise ValueError(f"Host {host.name!r} is already registered.")
        self.hosts[host.name] = host

    def find_host(self, vm: VirtualMachine) -> Optional[PhysicalServer]:
        """
        Select a host using a simple best-fit strategy.

        The strategy prefers the host that will have the lowest combined
        CPU and memory utilization after deployment.
        """

        candidates = []

        for host in self.hosts.values():
            allowed, _ = host.can_allocate(vm)
            if allowed:
                future_cpu = (
                    host.allocated_cpu() + vm.vcpu
                ) / host.cpu_cores
                future_memory = (
                    host.allocated_memory() + vm.memory_gb
                ) / host.memory_gb

                score = future_cpu + future_memory
                candidates.append((score, host))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def deploy_vm(self, vm: VirtualMachine) -> PhysicalServer:
        host = self.find_host(vm)

        if host is None:
            raise RuntimeError(
                f"No physical server can currently host VM {vm.name}."
            )

        host.deploy(vm)
        return host

    def migrate_vm(
        self,
        vm_name: str,
        source_host_name: str,
        destination_host_name: str,
    ) -> None:
        """
        Move a VM between hosts.

        Real hypervisors may support live migration, but this simulation
        models only the resource and placement decision.
        """

        if source_host_name not in self.hosts:
            raise KeyError(f"Unknown source host: {source_host_name}")

        if destination_host_name not in self.hosts:
            raise KeyError(
                f"Unknown destination host: {destination_host_name}"
            )

        source = self.hosts[source_host_name]
        destination = self.hosts[destination_host_name]

        if vm_name not in source.vms:
            raise KeyError(
                f"VM {vm_name!r} is not hosted on {source_host_name}."
            )

        vm = source.vms[vm_name]
        allowed, reason = destination.can_allocate(vm)

        if not allowed:
            raise RuntimeError(f"Migration rejected: {reason}")

        source.remove_vm(vm_name)
        destination.deploy(vm)


def format_gb(value: float) -> str:
    return f"{value:.1f} GB"


def print_host_report(host: PhysicalServer) -> None:
    usage = host.utilization()

    print(f"\nHost: {host.name}")
    print(
        f"  Hardware: {host.cpu_cores} CPU cores, "
        f"{format_gb(host.memory_gb)} RAM, "
        f"{format_gb(host.storage_gb)} storage"
    )
    print(
        f"  Allocated: {host.allocated_cpu():.1f} vCPU, "
        f"{format_gb(host.allocated_memory())} RAM, "
        f"{format_gb(host.allocated_storage())} storage"
    )
    print(
        f"  Utilization: CPU={usage['cpu']:.0%}, "
        f"RAM={usage['memory']:.0%}, "
        f"Storage={usage['storage']:.0%}"
    )

    for vm in host.vms.values():
        state = "running" if vm.running else "stopped"
        print(
            f"    - {vm.name}: {vm.operating_system}, "
            f"{vm.vcpu} vCPU, {format_gb(vm.memory_gb)}, "
            f"{format_gb(vm.storage_gb)}, {state}"
        )


def demonstrate_resource_abstraction() -> None:
    print("\n=== Resource Abstraction ===")

    host = PhysicalServer(
        name="physical-host-01",
        cpu_cores=16,
        memory_gb=64,
        storage_gb=1000,
        network_gbps=10,
        power_watts=500,
    )

    web_vm = VirtualMachine(
        name="web-vm",
        operating_system="Linux",
        vcpu=4,
        memory_gb=8,
        storage_gb=100,
        workload="Web server",
    )

    database_vm = VirtualMachine(
        name="database-vm",
        operating_system="Linux",
        vcpu=6,
        memory_gb=16,
        storage_gb=300,
        workload="Database",
    )

    host.deploy(web_vm)
    host.deploy(database_vm)

    web_vm.start()
    database_vm.start()

    print(
        "The applications inside the VMs request virtual resources. "
        "The physical host owns the actual CPU, memory, and storage."
    )

    print_host_report(host)


def demonstrate_consolidation() -> None:
    print("\n=== Server Consolidation ===")

    hosts = [
        PhysicalServer(
            "host-A",
            cpu_cores=16,
            memory_gb=64,
            storage_gb=2000,
            network_gbps=10,
            power_watts=500,
        ),
        PhysicalServer(
            "host-B",
            cpu_cores=16,
            memory_gb=64,
            storage_gb=2000,
            network_gbps=10,
            power_watts=500,
        ),
        PhysicalServer(
            "host-C",
            cpu_cores=16,
            memory_gb=64,
            storage_gb=2000,
            network_gbps=10,
            power_watts=500,
        ),
    ]

    hypervisor = Hypervisor("training-hypervisor")

    for host in hosts:
        hypervisor.register_host(host)

    workloads = [
        ("web-01", 4, 8, 150, "Web"),
        ("web-02", 2, 6, 100, "Web"),
        ("api-01", 4, 8, 120, "API"),
        ("db-01", 6, 20, 400, "Database"),
        ("worker-01", 3, 10, 200, "Background worker"),
        ("monitor-01", 1, 4, 80, "Monitoring"),
    ]

    for name, cpu, memory, storage, workload in workloads:
        vm = VirtualMachine(
            name=name,
            operating_system="Linux",
            vcpu=cpu,
            memory_gb=memory,
            storage_gb=storage,
            workload=workload,
        )
        hypervisor.deploy_vm(vm)
        vm.start()

    for host in hosts:
        print_host_report(host)

    total_power = sum(
        host.power_watts
        for host in hosts
        if host.vms
    )

    print(f"\nEstimated active-host power budget: {total_power} W")
    print(
        "Virtualization allows several logical servers to share physical "
        "hardware instead of requiring one physical server per workload."
    )


def demonstrate_isolation() -> None:
    print("\n=== Logical Isolation ===")

    host = PhysicalServer(
        "isolation-host",
        cpu_cores=8,
        memory_gb=32,
        storage_gb=500,
        network_gbps=5,
        power_watts=300,
    )

    vm_a = VirtualMachine(
        "tenant-a",
        "Linux",
        2,
        4,
        50,
        "Application A",
    )

    vm_b = VirtualMachine(
        "tenant-b",
        "Linux",
        2,
        4,
        50,
        "Application B",
    )

    host.deploy(vm_a)
    host.deploy(vm_b)

    print(f"{vm_a.name} owns logical memory allocation: {vm_a.memory_gb} GB")
    print(f"{vm_b.name} owns logical memory allocation: {vm_b.memory_gb} GB")
    print(
        "The VM abstraction prevents ordinary guest applications from "
        "treating the host's complete physical memory as their own."
    )

    print(
        "Isolation is not absolute security by definition: hypervisor "
        "vulnerabilities, incorrect configuration, device passthrough, "
        "or shared infrastructure can create additional risk."
    )


def demonstrate_validation_and_failure() -> None:
    print("\n=== Resource Validation and Failure Conditions ===")

    host = PhysicalServer(
        "small-host",
        cpu_cores=4,
        memory_gb=8,
        storage_gb=100,
        network_gbps=1,
        power_watts=150,
    )

    oversized_vm = VirtualMachine(
        "oversized-vm",
        "Linux",
        8,
        16,
        50,
        "Invalid workload",
    )

    allowed, reason = host.can_allocate(oversized_vm)
    print(f"Allocation allowed: {allowed}")
    print(f"Reason: {reason}")

    try:
        host.deploy(oversized_vm)
    except ValueError as exc:
        print(f"Deployment failed safely: {exc}")

    invalid_vm = VirtualMachine(
        "invalid-vm",
        "Linux",
        0,
        4,
        20,
        "Invalid CPU request",
    )

    try:
        host.deploy(invalid_vm)
    except ValueError as exc:
        print(f"Validation rejected invalid VM: {exc}")


def demonstrate_migration() -> None:
    print("\n=== VM Migration ===")

    hypervisor = Hypervisor("migration-hypervisor")

    source = PhysicalServer(
        "source-host",
        16,
        64,
        1000,
        10,
        500,
    )

    destination = PhysicalServer(
        "destination-host",
        16,
        64,
        1000,
        10,
        500,
    )

    hypervisor.register_host(source)
    hypervisor.register_host(destination)

    vm = VirtualMachine(
        "analytics-vm",
        "Linux",
        6,
        16,
        250,
        "Analytics",
    )

    source.deploy(vm)
    vm.start()

    print(f"Before migration: {vm.name} -> {vm.host}")

    hypervisor.migrate_vm(
        "analytics-vm",
        "source-host",
        "destination-host",
    )

    print(f"After migration: {vm.name} -> {vm.host}")


def demonstrate_capacity_planning() -> None:
    print("\n=== Capacity Planning ===")

    host = PhysicalServer(
        "capacity-host",
        cpu_cores=32,
        memory_gb=128,
        storage_gb=4000,
        network_gbps=25,
        power_watts=900,
    )

    vm_profiles = [
        ("frontend", 4, 8),
        ("backend", 6, 16),
        ("database", 8, 32),
        ("cache", 4, 8),
        ("worker", 4, 16),
    ]

    for name, cpu, memory in vm_profiles:
        vm = VirtualMachine(
            name=name,
            operating_system="Linux",
            vcpu=cpu,
            memory_gb=memory,
            storage_gb=100,
            workload=name,
        )

        if host.can_allocate(vm)[0]:
            host.deploy(vm)
        else:
            print(f"Capacity limit reached before deploying {name}.")
            break

    print_host_report(host)

    print(
        "\nAllocated CPU can be interpreted differently from actual CPU "
        "consumption. A hypervisor can schedule VMs dynamically, and some "
        "platforms permit CPU overcommitment. Memory and storage overcommit "
        "also have platform-specific mechanisms and risks."
    )


def demonstrate_benefits() -> None:
    print("\n=== Virtualization Benefits ===")

    physical_servers_for_workloads = 6
    virtualized_hosts = 2

    traditional_power = physical_servers_for_workloads * 500
    virtualized_power = virtualized_hosts * 700

    print(
        f"Traditional deployment estimate: "
        f"{physical_servers_for_workloads} physical servers"
    )
    print(
        f"Consolidated deployment estimate: "
        f"{virtualized_hosts} physical hosts"
    )
    print(f"Illustrative traditional power: {traditional_power} W")
    print(f"Illustrative virtualized power: {virtualized_power} W")

    print(
        "\nThe numerical values are only a capacity-planning example. "
        "Real savings depend on workload utilization, hardware efficiency, "
        "licensing, storage, network requirements, cooling, and availability."
    )


def main() -> None:
    print("VIRTUALIZATION FUNDAMENTALS")
    print("===========================")
    print(
        "A physical server supplies hardware resources. A hypervisor "
        "abstracts those resources into virtual machines."
    )

    demonstrate_resource_abstraction()
    demonstrate_consolidation()
    demonstrate_isolation()
    demonstrate_validation_and_failure()
    demonstrate_migration()
    demonstrate_capacity_planning()
    demonstrate_benefits()


if __name__ == "__main__":
    main()
