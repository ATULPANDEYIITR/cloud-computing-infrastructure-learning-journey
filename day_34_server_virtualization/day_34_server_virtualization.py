#!/usr/bin/env python3
"""
Server Virtualization: Resource Sharing, VM Isolation, Overcommitment, and Host Management

A self-contained educational simulator for a small virtualization host.

The program models:
- Physical host resources
- Virtual machines and virtual hardware allocations
- CPU and memory resource sharing
- CPU and memory overcommitment
- VM isolation boundaries
- Host admission control
- Memory pressure and ballooning
- CPU scheduling using weighted shares
- VM lifecycle and migration checks
- Host health monitoring
- Resource reservation and limits
- Failure and validation conditions

This is a simulation. It does not create real virtual machines or interact
with a hypervisor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import math
import random
import statistics


class VMState(Enum):
    """Lifecycle states used by the simulator."""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"


@dataclass
class HostResources:
    """Physical resources available to a virtualization host."""

    cpu_cores: int
    memory_gb: float
    storage_gb: float
    network_gbps: float

    def validate(self) -> None:
        if self.cpu_cores <= 0:
            raise ValueError("Host must contain at least one CPU core.")
        if self.memory_gb <= 0:
            raise ValueError("Host memory must be positive.")
        if self.storage_gb <= 0:
            raise ValueError("Host storage must be positive.")
        if self.network_gbps <= 0:
            raise ValueError("Host network capacity must be positive.")


@dataclass
class VM:
    """
    Represents a virtual machine and its virtual hardware contract.

    reservation values are guaranteed resources that the host promises to
    preserve for the VM when sufficient physical resources exist.

    limits prevent the VM from consuming more than its configured ceiling.
    """

    name: str
    vcpus: int
    memory_gb: float
    storage_gb: float
    network_gbps: float
    cpu_reservation: int = 0
    memory_reservation_gb: float = 0.0
    cpu_limit: Optional[int] = None
    memory_limit_gb: Optional[float] = None
    cpu_shares: int = 100
    state: VMState = VMState.STOPPED
    cpu_demand: float = 0.0
    memory_demand_gb: float = 0.0
    ballooned_memory_gb: float = 0.0
    isolation_group: str = "default"
    trusted: bool = False

    def __post_init__(self) -> None:
        if self.vcpus <= 0:
            raise ValueError(f"{self.name}: vCPUs must be positive.")
        if self.memory_gb <= 0:
            raise ValueError(f"{self.name}: memory must be positive.")
        if self.storage_gb <= 0:
            raise ValueError(f"{self.name}: storage must be positive.")
        if self.network_gbps < 0:
            raise ValueError(f"{self.name}: network capacity cannot be negative.")
        if self.cpu_reservation < 0 or self.cpu_reservation > self.vcpus:
            raise ValueError(f"{self.name}: invalid CPU reservation.")
        if self.memory_reservation_gb < 0 or self.memory_reservation_gb > self.memory_gb:
            raise ValueError(f"{self.name}: invalid memory reservation.")
        if self.cpu_limit is not None and self.cpu_limit < self.cpu_reservation:
            raise ValueError(f"{self.name}: CPU limit is below CPU reservation.")
        if (
            self.memory_limit_gb is not None
            and self.memory_limit_gb < self.memory_reservation_gb
        ):
            raise ValueError(f"{self.name}: memory limit is below reservation.")
        if self.cpu_shares <= 0:
            raise ValueError(f"{self.name}: CPU shares must be positive.")

    @property
    def effective_cpu_limit(self) -> int:
        """Return the highest CPU allocation permitted to this VM."""
        return self.cpu_limit if self.cpu_limit is not None else self.vcpus

    @property
    def effective_memory_limit(self) -> float:
        """Return the highest memory allocation permitted to this VM."""
        return (
            self.memory_limit_gb
            if self.memory_limit_gb is not None
            else self.memory_gb
        )

    @property
    def usable_memory_gb(self) -> float:
        """Memory remaining after simulated balloon reclamation."""
        return max(0.0, self.memory_gb - self.ballooned_memory_gb)

    def start(self) -> None:
        if self.state == VMState.FAILED:
            raise RuntimeError(f"{self.name} cannot start while failed.")
        if self.state == VMState.RUNNING:
            return
        self.state = VMState.RUNNING

    def stop(self) -> None:
        self.state = VMState.STOPPED
        self.cpu_demand = 0.0
        self.memory_demand_gb = 0.0
        self.ballooned_memory_gb = 0.0

    def pause(self) -> None:
        if self.state != VMState.RUNNING:
            raise RuntimeError(f"{self.name} must be running before it can be paused.")
        self.state = VMState.PAUSED

    def set_demand(self, cpu: float, memory_gb: float) -> None:
        """
        Set workload demand.

        Demand may exceed configured virtual hardware. The scheduler later
        applies reservations, limits, and host capacity.
        """
        if cpu < 0 or memory_gb < 0:
            raise ValueError("Workload demand cannot be negative.")
        self.cpu_demand = min(cpu, float(self.effective_cpu_limit))
        self.memory_demand_gb = min(
            memory_gb,
            self.effective_memory_limit,
        )


@dataclass
class Allocation:
    """Result of resource allocation for one VM."""

    vm_name: str
    cpu_allocated: float
    memory_allocated_gb: float
    memory_pressure: float
    cpu_throttled: bool
    memory_reclaimed_gb: float


@dataclass
class HostHealth:
    """Aggregated host health information."""

    cpu_utilization: float
    memory_utilization: float
    memory_overcommit_ratio: float
    cpu_overcommit_ratio: float
    running_vms: int
    warnings: List[str] = field(default_factory=list)


class IsolationManager:
    """
    Models isolation boundaries conceptually.

    A real hypervisor enforces isolation through hardware virtualization,
    virtual address translation, device mediation, I/O controls, and other
    mechanisms. This simulator models policy-level isolation decisions.
    """

    def __init__(self) -> None:
        self.allowed_groups: Dict[str, List[str]] = {}

    def register_vm(self, vm: VM) -> None:
        self.allowed_groups.setdefault(vm.isolation_group, []).append(vm.name)

    def can_access(self, source: VM, target: VM) -> bool:
        """
        VMs are isolated by default.

        Sharing an isolation group does not automatically grant arbitrary
        memory or storage access. It represents a policy domain only.
        """
        if source.name == target.name:
            return True
        return False

    def validate_isolation(self, vms: List[VM]) -> List[str]:
        violations: List[str] = []
        names = {vm.name for vm in vms}

        for vm in vms:
            if vm.name not in names:
                violations.append(f"Unknown VM identity: {vm.name}")

        return violations


class Host:
    """A simplified virtualization host with admission and scheduling logic."""

    def __init__(self, name: str, resources: HostResources) -> None:
        resources.validate()
        self.name = name
        self.resources = resources
        self.vms: Dict[str, VM] = {}
        self.isolation = IsolationManager()
        self.overcommit_memory_enabled = True
        self.overcommit_cpu_enabled = True
        self.safe_memory_pressure = 0.10
        self.critical_memory_pressure = 0.20

    def add_vm(self, vm: VM, allow_overcommit: bool = True) -> None:
        """Perform admission control before placing a VM on the host."""
        if vm.name in self.vms:
            raise ValueError(f"VM '{vm.name}' already exists.")

        projected_cpu = self.allocated_vcpus() + vm.vcpus
        projected_memory = self.allocated_memory() + vm.memory_gb
        projected_storage = self.allocated_storage() + vm.storage_gb
        projected_network = self.allocated_network() + vm.network_gbps

        cpu_ok = projected_cpu <= self.resources.cpu_cores
        memory_ok = projected_memory <= self.resources.memory_gb
        storage_ok = projected_storage <= self.resources.storage_gb
        network_ok = projected_network <= self.resources.network_gbps

        if not storage_ok:
            raise RuntimeError(
                f"Cannot place {vm.name}: storage capacity would be exceeded."
            )

        if not network_ok:
            raise RuntimeError(
                f"Cannot place {vm.name}: network allocation would be exceeded."
            )

        if not cpu_ok and not self.overcommit_cpu_enabled:
            raise RuntimeError(
                f"Cannot place {vm.name}: CPU overcommitment is disabled."
            )

        if not memory_ok and not self.overcommit_memory_enabled:
            raise RuntimeError(
                f"Cannot place {vm.name}: memory overcommitment is disabled."
            )

        if not allow_overcommit and (not cpu_ok or not memory_ok):
            raise RuntimeError(
                f"Cannot place {vm.name}: requested resources exceed physical capacity."
            )

        self.vms[vm.name] = vm
        self.isolation.register_vm(vm)

    def remove_vm(self, name: str) -> None:
        if name not in self.vms:
            raise KeyError(f"Unknown VM: {name}")
        if self.vms[name].state == VMState.RUNNING:
            raise RuntimeError("A running VM must be stopped before removal.")
        del self.vms[name]

    def allocated_vcpus(self) -> int:
        return sum(vm.vcpus for vm in self.vms.values())

    def allocated_memory(self) -> float:
        return sum(vm.memory_gb for vm in self.vms.values())

    def allocated_storage(self) -> float:
        return sum(vm.storage_gb for vm in self.vms.values())

    def allocated_network(self) -> float:
        return sum(vm.network_gbps for vm in self.vms.values())

    def cpu_overcommit_ratio(self) -> float:
        return self.allocated_vcpus() / self.resources.cpu_cores

    def memory_overcommit_ratio(self) -> float:
        return self.allocated_memory() / self.resources.memory_gb

    def reservations_satisfied(self) -> bool:
        reserved_cpu = sum(vm.cpu_reservation for vm in self.vms.values())
        reserved_memory = sum(
            vm.memory_reservation_gb for vm in self.vms.values()
        )
        return (
            reserved_cpu <= self.resources.cpu_cores
            and reserved_memory <= self.resources.memory_gb
        )

    def running_vms(self) -> List[VM]:
        return [vm for vm in self.vms.values() if vm.state == VMState.RUNNING]

    def schedule_cpu(self) -> Dict[str, float]:
        """
        Allocate physical CPU based on reservations and weighted shares.

        Reservations are satisfied first. Remaining CPU is distributed among
        VMs that still have demand according to their configured shares.
        """
        running = self.running_vms()
        if not running:
            return {}

        allocations = {vm.name: 0.0 for vm in running}
        remaining = float(self.resources.cpu_cores)

        for vm in running:
            guaranteed = min(
                float(vm.cpu_reservation),
                vm.cpu_demand,
                float(vm.effective_cpu_limit),
            )
            allocations[vm.name] = guaranteed
            remaining -= guaranteed

        if remaining <= 0:
            return allocations

        active = [
            vm for vm in running
            if vm.cpu_demand > allocations[vm.name]
        ]

        while active and remaining > 1e-9:
            total_shares = sum(vm.cpu_shares for vm in active)
            if total_shares <= 0:
                break

            distributed = 0.0
            next_active: List[VM] = []

            for vm in active:
                share = remaining * vm.cpu_shares / total_shares
                need = max(0.0, vm.cpu_demand - allocations[vm.name])
                room = max(0.0, vm.effective_cpu_limit - allocations[vm.name])
                grant = min(share, need, room)

                allocations[vm.name] += grant
                distributed += grant

                if need - grant > 1e-9 and room - grant > 1e-9:
                    next_active.append(vm)

            if distributed <= 1e-9:
                break

            remaining -= distributed
            active = next_active

        return allocations

    def manage_memory(self) -> Dict[str, float]:
        """
        Reclaim memory through simulated ballooning when active demand exceeds
        physical memory.

        Reserved memory is protected during normal reclamation.
        """
        running = self.running_vms()
        if not running:
            return {}

        total_demand = sum(vm.memory_demand_gb for vm in running)

        if total_demand <= self.resources.memory_gb:
            for vm in running:
                vm.ballooned_memory_gb = 0.0
            return {vm.name: 0.0 for vm in running}

        deficit = total_demand - self.resources.memory_gb

        reclaimable = {
            vm.name: max(
                0.0,
                min(
                    vm.memory_demand_gb - vm.memory_reservation_gb,
                    vm.usable_memory_gb - vm.memory_reservation_gb,
                ),
            )
            for vm in running
        }

        total_reclaimable = sum(reclaimable.values())

        if total_reclaimable <= 0:
            raise MemoryError(
                "Physical memory is exhausted and no reclaimable VM memory remains."
            )

        for vm in running:
            proportional = (
                deficit * reclaimable[vm.name] / total_reclaimable
                if total_reclaimable
                else 0.0
            )
            vm.ballooned_memory_gb = min(
                proportional,
                max(0.0, vm.memory_gb - vm.memory_reservation_gb),
            )

        return {
            vm.name: vm.ballooned_memory_gb
            for vm in running
        }

    def allocate_resources(self) -> List[Allocation]:
        """
        Run a complete scheduling cycle.

        CPU is allocated independently from memory because CPU contention and
        memory pressure have different physical failure modes.
        """
        running = self.running_vms()
        cpu = self.schedule_cpu()

        try:
            reclaimed = self.manage_memory()
        except MemoryError:
            for vm in running:
                vm.state = VMState.FAILED
            raise

        allocations: List[Allocation] = []

        for vm in running:
            memory_allocated = max(
                0.0,
                min(
                    vm.memory_demand_gb - reclaimed.get(vm.name, 0.0),
                    vm.memory_gb - reclaimed.get(vm.name, 0.0),
                ),
            )

            cpu_allocated = cpu.get(vm.name, 0.0)
            cpu_throttled = cpu_allocated + 1e-9 < vm.cpu_demand

            pressure = (
                reclaimed.get(vm.name, 0.0) / vm.memory_gb
                if vm.memory_gb
                else 0.0
            )

            allocations.append(
                Allocation(
                    vm_name=vm.name,
                    cpu_allocated=cpu_allocated,
                    memory_allocated_gb=memory_allocated,
                    memory_pressure=pressure,
                    cpu_throttled=cpu_throttled,
                    memory_reclaimed_gb=reclaimed.get(vm.name, 0.0),
                )
            )

        return allocations

    def health(self) -> HostHealth:
        running = self.running_vms()

        cpu_demand = sum(vm.cpu_demand for vm in running)
        memory_demand = sum(vm.memory_demand_gb for vm in running)

        cpu_utilization = min(
            1.0,
            cpu_demand / self.resources.cpu_cores
            if self.resources.cpu_cores
            else 0.0,
        )
        memory_utilization = min(
            1.0,
            memory_demand / self.resources.memory_gb
            if self.resources.memory_gb
            else 0.0,
        )

        warnings: List[str] = []

        if self.cpu_overcommit_ratio() > 1.0:
            warnings.append(
                "Allocated vCPUs exceed physical CPU cores; scheduling contention is possible."
            )

        if self.memory_overcommit_ratio() > 1.0:
            warnings.append(
                "Allocated VM memory exceeds physical RAM; reclamation or swapping may be required."
            )

        if memory_utilization >= 0.90:
            warnings.append("Memory demand is near host capacity.")

        if cpu_utilization >= 0.90:
            warnings.append("CPU demand is near host capacity.")

        if not self.reservations_satisfied():
            warnings.append(
                "Configured VM reservations cannot all be guaranteed simultaneously."
            )

        return HostHealth(
            cpu_utilization=cpu_utilization,
            memory_utilization=memory_utilization,
            memory_overcommit_ratio=self.memory_overcommit_ratio(),
            cpu_overcommit_ratio=self.cpu_overcommit_ratio(),
            running_vms=len(running),
            warnings=warnings,
        )

    def can_migrate_vm_to(self, vm_name: str, destination: "Host") -> Tuple[bool, str]:
        """
        Check whether a VM can be placed on another host.

        A production migration system would also check CPU compatibility,
        storage accessibility, network configuration, device state, NUMA
        constraints, encryption requirements, and migration protocol state.
        """
        if vm_name not in self.vms:
            return False, f"VM {vm_name} does not exist on {self.name}."

        vm = self.vms[vm_name]

        if vm.state not in {VMState.RUNNING, VMState.PAUSED, VMState.STOPPED}:
            return False, f"VM {vm_name} is in an invalid migration state."

        if destination.allocated_storage() + vm.storage_gb > destination.resources.storage_gb:
            return False, "Destination lacks storage capacity."

        if (
            destination.allocated_memory() + vm.memory_gb
            > destination.resources.memory_gb
            and not destination.overcommit_memory_enabled
        ):
            return False, "Destination memory policy rejects the VM."

        if (
            destination.allocated_vcpus() + vm.vcpus
            > destination.resources.cpu_cores
            and not destination.overcommit_cpu_enabled
        ):
            return False, "Destination CPU policy rejects the VM."

        return True, "Migration admission checks passed."

    def describe(self) -> None:
        print(f"\nHost: {self.name}")
        print(
            f"Physical CPU: {self.resources.cpu_cores} cores | "
            f"RAM: {self.resources.memory_gb:.1f} GB | "
            f"Storage: {self.resources.storage_gb:.1f} GB | "
            f"Network: {self.resources.network_gbps:.1f} Gbps"
        )
        print(
            f"Allocated vCPU: {self.allocated_vcpus()} "
            f"({self.cpu_overcommit_ratio():.2f}x)"
        )
        print(
            f"Allocated memory: {self.allocated_memory():.1f} GB "
            f"({self.memory_overcommit_ratio():.2f}x)"
        )

        for vm in self.vms.values():
            print(
                f"  {vm.name:12} state={vm.state.value:7} "
                f"vCPU={vm.vcpus:2} RAM={vm.memory_gb:5.1f}GB "
                f"reservation={vm.memory_reservation_gb:4.1f}GB "
                f"shares={vm.cpu_shares}"
            )


def print_allocations(allocations: List[Allocation]) -> None:
    print("\nResource allocation cycle")
    print(
        f"{'VM':12} {'CPU':>8} {'RAM':>10} "
        f"{'Reclaimed':>11} {'Pressure':>10} {'CPU limited':>12}"
    )
    print("-" * 70)

    for item in allocations:
        print(
            f"{item.vm_name:12} "
            f"{item.cpu_allocated:8.2f} "
            f"{item.memory_allocated_gb:10.2f} "
            f"{item.memory_reclaimed_gb:11.2f} "
            f"{item.memory_pressure:9.1%} "
            f"{str(item.cpu_throttled):>12}"
        )


def demonstrate_basic_resource_sharing() -> None:
    print("\n=== Resource Sharing ===")

    host = Host(
        "compute-01",
        HostResources(
            cpu_cores=8,
            memory_gb=32,
            storage_gb=500,
            network_gbps=10,
        ),
    )

    host.add_vm(
        VM(
            name="web-01",
            vcpus=2,
            memory_gb=6,
            storage_gb=40,
            network_gbps=1,
            cpu_shares=200,
        )
    )

    host.add_vm(
        VM(
            name="api-01",
            vcpus=4,
            memory_gb=10,
            storage_gb=80,
            network_gbps=2,
            cpu_shares=400,
        )
    )

    host.add_vm(
        VM(
            name="database-01",
            vcpus=2,
            memory_gb=12,
            storage_gb=120,
            network_gbps=2,
            cpu_reservation=2,
            memory_reservation_gb=8,
            cpu_shares=600,
        )
    )

    for vm in host.vms.values():
        vm.start()

    host.vms["web-01"].set_demand(cpu=1.5, memory_gb=5.0)
    host.vms["api-01"].set_demand(cpu=4.0, memory_gb=8.0)
    host.vms["database-01"].set_demand(cpu=2.0, memory_gb=11.0)

    host.describe()
    print_allocations(host.allocate_resources())


def demonstrate_overcommitment() -> None:
    print("\n=== CPU and Memory Overcommitment ===")

    host = Host(
        "consolidation-01",
        HostResources(
            cpu_cores=8,
            memory_gb=24,
            storage_gb=1000,
            network_gbps=20,
        ),
    )

    vm_specs = [
        ("service-a", 4, 8),
        ("service-b", 4, 8),
        ("service-c", 4, 8),
    ]

    for name, cpu, memory in vm_specs:
        host.add_vm(
            VM(
                name=name,
                vcpus=cpu,
                memory_gb=memory,
                storage_gb=50,
                network_gbps=1,
                cpu_shares=100,
            )
        )

    for vm in host.vms.values():
        vm.start()
        vm.set_demand(cpu=vm.vcpus, memory_gb=vm.memory_gb)

    host.describe()

    try:
        allocations = host.allocate_resources()
        print_allocations(allocations)
    except MemoryError as exc:
        print(f"Memory failure: {exc}")

    health = host.health()

    print(
        f"\nCPU utilization: {health.cpu_utilization:.1%}\n"
        f"Memory utilization: {health.memory_utilization:.1%}\n"
        f"CPU overcommit ratio: {health.cpu_overcommit_ratio:.2f}x\n"
        f"Memory overcommit ratio: {health.memory_overcommit_ratio:.2f}x"
    )

    for warning in health.warnings:
        print(f"WARNING: {warning}")


def demonstrate_isolation() -> None:
    print("\n=== VM Isolation ===")

    host = Host(
        "secure-01",
        HostResources(
            cpu_cores=4,
            memory_gb=16,
            storage_gb=250,
            network_gbps=5,
        ),
    )

    customer_a = VM(
        name="tenant-a",
        vcpus=1,
        memory_gb=4,
        storage_gb=30,
        network_gbps=1,
        isolation_group="tenant-a",
    )

    customer_b = VM(
        name="tenant-b",
        vcpus=1,
        memory_gb=4,
        storage_gb=30,
        network_gbps=1,
        isolation_group="tenant-b",
    )

    host.add_vm(customer_a)
    host.add_vm(customer_b)

    print(
        f"Can {customer_a.name} directly access {customer_b.name}? "
        f"{host.isolation.can_access(customer_a, customer_b)}"
    )
    print(
        "Isolation model: each VM receives an independent virtual machine "
        "boundary rather than direct access to another VM's memory."
    )


def demonstrate_reservations_and_limits() -> None:
    print("\n=== Reservations, Shares, and Limits ===")

    host = Host(
        "policy-01",
        HostResources(
            cpu_cores=4,
            memory_gb=16,
            storage_gb=300,
            network_gbps=10,
        ),
    )

    critical = VM(
        name="critical-db",
        vcpus=3,
        memory_gb=8,
        storage_gb=60,
        network_gbps=2,
        cpu_reservation=2,
        memory_reservation_gb=6,
        cpu_limit=3,
        memory_limit_gb=8,
        cpu_shares=800,
    )

    batch = VM(
        name="batch-worker",
        vcpus=3,
        memory_gb=6,
        storage_gb=50,
        network_gbps=1,
        cpu_shares=100,
    )

    host.add_vm(critical)
    host.add_vm(batch)

    critical.start()
    batch.start()

    critical.set_demand(cpu=3, memory_gb=8)
    batch.set_demand(cpu=3, memory_gb=6)

    print_allocations(host.allocate_resources())

    print(
        "\nThe database receives a protected minimum through its reservation. "
        "CPU shares influence distribution of unreserved capacity, while "
        "the CPU and memory limits prevent configured ceilings from being exceeded."
    )


def demonstrate_migration() -> None:
    print("\n=== Migration Admission ===")

    source = Host(
        "source-01",
        HostResources(
            cpu_cores=8,
            memory_gb=32,
            storage_gb=500,
            network_gbps=10,
        ),
    )

    destination = Host(
        "destination-01",
        HostResources(
            cpu_cores=8,
            memory_gb=32,
            storage_gb=500,
            network_gbps=10,
        ),
    )

    vm = VM(
        name="application-01",
        vcpus=4,
        memory_gb=12,
        storage_gb=100,
        network_gbps=2,
        memory_reservation_gb=8,
    )

    source.add_vm(vm)
    vm.start()

    allowed, reason = source.can_migrate_vm_to("application-01", destination)

    print(f"Migration decision: {allowed}")
    print(f"Reason: {reason}")


def demonstrate_failure_conditions() -> None:
    print("\n=== Failure Conditions and Validation ===")

    host = Host(
        "validation-01",
        HostResources(
            cpu_cores=4,
            memory_gb=8,
            storage_gb=100,
            network_gbps=2,
        ),
    )

    try:
        host.add_vm(
            VM(
                name="invalid-vm",
                vcpus=2,
                memory_gb=2,
                storage_gb=200,
                network_gbps=1,
            )
        )
    except RuntimeError as exc:
        print(f"Rejected placement: {exc}")

    try:
        VM(
            name="bad-reservation",
            vcpus=2,
            memory_gb=4,
            storage_gb=20,
            network_gbps=1,
            memory_reservation_gb=5,
        )
    except ValueError as exc:
        print(f"Rejected configuration: {exc}")


def run_monitoring_simulation() -> None:
    """
    Simulate several workload intervals.

    The random variation represents changing application load, not physical
    hardware behavior. It makes resource contention visible over time.
    """
    print("\n=== Workload Monitoring Simulation ===")

    host = Host(
        "monitor-01",
        HostResources(
            cpu_cores=8,
            memory_gb=32,
            storage_gb=800,
            network_gbps=10,
        ),
    )

    workloads = [
        ("frontend", 2, 6, 180),
        ("orders", 3, 10, 300),
        ("analytics", 4, 12, 100),
    ]

    for name, cpu, memory, shares in workloads:
        vm = VM(
            name=name,
            vcpus=cpu,
            memory_gb=memory,
            storage_gb=80,
            network_gbps=1,
            cpu_shares=shares,
        )
        host.add_vm(vm)
        vm.start()

    cpu_samples: List[float] = []
    memory_samples: List[float] = []

    for interval in range(1, 9):
        for vm in host.running_vms():
            cpu_factor = random.uniform(0.35, 1.15)
            memory_factor = random.uniform(0.45, 1.05)

            vm.set_demand(
                cpu=vm.vcpus * cpu_factor,
                memory_gb=vm.memory_gb * memory_factor,
            )

        allocations = host.allocate_resources()
        health = host.health()

        cpu_samples.append(health.cpu_utilization)
        memory_samples.append(health.memory_utilization)

        print(
            f"Interval {interval}: "
            f"CPU={health.cpu_utilization:.1%}, "
            f"RAM={health.memory_utilization:.1%}, "
            f"CPU overcommit={health.cpu_overcommit_ratio:.2f}x, "
            f"RAM overcommit={health.memory_overcommit_ratio:.2f}x"
        )

        for allocation in allocations:
            if allocation.cpu_throttled:
                print(
                    f"  CPU contention: {allocation.vm_name} "
                    f"received {allocation.cpu_allocated:.2f} vCPU"
                )

            if allocation.memory_reclaimed_gb > 0:
                print(
                    f"  Memory reclamation: {allocation.vm_name} "
                    f"reclaimed {allocation.memory_reclaimed_gb:.2f} GB"
                )

    print(
        f"\nAverage CPU demand ratio: {statistics.mean(cpu_samples):.1%}\n"
        f"Peak CPU demand ratio: {max(cpu_samples):.1%}\n"
        f"Average memory demand ratio: {statistics.mean(memory_samples):.1%}\n"
        f"Peak memory demand ratio: {max(memory_samples):.1%}"
    )


def demonstrate_capacity_planning() -> None:
    print("\n=== Capacity Planning ===")

    host = Host(
        "capacity-01",
        HostResources(
            cpu_cores=16,
            memory_gb=64,
            storage_gb=2000,
            network_gbps=25,
        ),
    )

    vms = [
        VM("web-01", 2, 6, 100, 2),
        VM("web-02", 2, 6, 100, 2),
        VM("api-01", 4, 10, 150, 3),
        VM("db-01", 6, 20, 300, 5, cpu_reservation=4, memory_reservation_gb=16),
        VM("worker-01", 4, 8, 200, 2),
    ]

    for vm in vms:
        host.add_vm(vm)

    cpu_ratio = host.cpu_overcommit_ratio()
    memory_ratio = host.memory_overcommit_ratio()

    print(f"CPU allocation ratio: {cpu_ratio:.2f}x")
    print(f"Memory allocation ratio: {memory_ratio:.2f}x")

    print(
        "\nCapacity planning should consider peak concurrent demand rather than "
        "virtual allocation alone. A host can safely contain more virtual CPU "
        "than physical CPU when workloads are bursty, but sustained demand near "
        "or above physical capacity creates scheduling latency."
    )


def main() -> None:
    random.seed(42)

    print("=" * 78)
    print("SERVER VIRTUALIZATION RESOURCE MANAGEMENT SIMULATOR")
    print("=" * 78)

    demonstrate_basic_resource_sharing()
    demonstrate_overcommitment()
    demonstrate_isolation()
    demonstrate_reservations_and_limits()
    demonstrate_migration()
    demonstrate_failure_conditions()
    run_monitoring_simulation()
    demonstrate_capacity_planning()

    print("\n=== Key Design Boundary ===")
    print(
        "Resource sharing determines how physical capacity is distributed. "
        "VM isolation determines what one guest is allowed to access. "
        "Overcommitment permits virtual allocations to exceed physical capacity "
        "under controlled policies. Host management coordinates placement, "
        "monitoring, scheduling, reclamation, and failure handling."
    )


if __name__ == "__main__":
    main()
