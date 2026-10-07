#!/usr/bin/env python3
"""
Containers vs Virtual Machines
==============================

A self-contained executable study of:
- isolation
- performance
- portability
- resource utilization
- workload comparison

The program models a small infrastructure environment containing:
- virtual machines with a guest operating system
- containers sharing a host kernel
- CPU and memory limits
- startup behavior
- workload placement
- resource accounting
- failure isolation
- portability checks

No external packages are required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil
from typing import Dict, List, Optional, Tuple


class WorkloadType(Enum):
    WEB_API = "web-api"
    DATABASE = "database"
    LEGACY_APPLICATION = "legacy-application"
    BATCH_JOB = "batch-job"
    MULTI_SERVICE = "multi-service"


@dataclass(frozen=True)
class Workload:
    name: str
    workload_type: WorkloadType
    cpu_request: float
    memory_request_gb: float
    storage_gb: float
    requires_linux_kernel: bool = False
    requires_custom_kernel: bool = False
    long_running: bool = True


@dataclass
class RuntimeInstance:
    name: str
    workload: Workload
    cpu_limit: float
    memory_limit_gb: float
    startup_seconds: float
    isolation_strength: float
    portability_score: float
    overhead_cpu: float
    overhead_memory_gb: float
    running: bool = False
    host_name: Optional[str] = None

    @property
    def effective_cpu_capacity(self) -> float:
        return max(0.0, self.cpu_limit - self.overhead_cpu)

    @property
    def effective_memory_capacity(self) -> float:
        return max(0.0, self.memory_limit_gb - self.overhead_memory_gb)

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False


@dataclass
class Host:
    name: str
    total_cpu: float
    total_memory_gb: float
    total_storage_gb: float
    kernel: str
    instances: List[RuntimeInstance] = field(default_factory=list)

    @property
    def allocated_cpu(self) -> float:
        return sum(instance.cpu_limit for instance in self.instances)

    @property
    def allocated_memory_gb(self) -> float:
        return sum(instance.memory_limit_gb for instance in self.instances)

    @property
    def used_storage_gb(self) -> float:
        return sum(instance.workload.storage_gb for instance in self.instances)

    def can_host(self, instance: RuntimeInstance) -> bool:
        return (
            self.allocated_cpu + instance.cpu_limit <= self.total_cpu
            and self.allocated_memory_gb + instance.memory_limit_gb
            <= self.total_memory_gb
            and self.used_storage_gb + instance.workload.storage_gb
            <= self.total_storage_gb
        )

    def deploy(self, instance: RuntimeInstance) -> None:
        if not self.can_host(instance):
            raise RuntimeError(
                f"{instance.name} cannot fit on {self.name}: "
                f"CPU={self.allocated_cpu + instance.cpu_limit:.1f}/"
                f"{self.total_cpu:.1f}, "
                f"memory={self.allocated_memory_gb + instance.memory_limit_gb:.1f}/"
                f"{self.total_memory_gb:.1f} GB"
            )

        self.instances.append(instance)
        instance.host_name = self.name


class Container(RuntimeInstance):
    """
    A container represents an isolated process tree sharing the host kernel.

    The model deliberately gives containers low startup and memory overhead.
    The isolation score is lower than a VM because a kernel compromise can
    affect multiple containers on the same host.
    """

    def __init__(
        self,
        name: str,
        workload: Workload,
        cpu_limit: float,
        memory_limit_gb: float,
    ) -> None:
        super().__init__(
            name=name,
            workload=workload,
            cpu_limit=cpu_limit,
            memory_limit_gb=memory_limit_gb,
            startup_seconds=0.8,
            isolation_strength=0.72,
            portability_score=0.95,
            overhead_cpu=0.02,
            overhead_memory_gb=0.08,
        )


class VirtualMachine(RuntimeInstance):
    """
    A VM includes a guest operating system and virtual hardware.

    Its larger boot and memory overhead model the guest kernel, system
    services, virtual devices, and hypervisor boundary.
    """

    def __init__(
        self,
        name: str,
        workload: Workload,
        cpu_limit: float,
        memory_limit_gb: float,
        guest_os: str = "Linux",
    ) -> None:
        self.guest_os = guest_os
        super().__init__(
            name=name,
            workload=workload,
            cpu_limit=cpu_limit,
            memory_limit_gb=memory_limit_gb,
            startup_seconds=22.0,
            isolation_strength=0.96,
            portability_score=0.82,
            overhead_cpu=0.20,
            overhead_memory_gb=0.65,
        )


class PlacementEngine:
    """
    Chooses a runtime according to workload characteristics.

    This is intentionally a rule-based decision engine rather than a claim
    that one virtualization model is universally superior.
    """

    @staticmethod
    def recommend(workload: Workload) -> Tuple[str, str]:
        if workload.requires_custom_kernel:
            return (
                "Virtual Machine",
                "The workload requires a kernel configuration that "
                "should not be shared with other workloads.",
            )

        if workload.workload_type == WorkloadType.LEGACY_APPLICATION:
            return (
                "Virtual Machine",
                "Legacy software may require a complete guest operating "
                "system and stronger environment independence.",
            )

        if workload.workload_type in {
            WorkloadType.WEB_API,
            WorkloadType.BATCH_JOB,
            WorkloadType.MULTI_SERVICE,
        }:
            return (
                "Container",
                "The workload benefits from rapid startup, high density, "
                "and application-level packaging.",
            )

        if workload.workload_type == WorkloadType.DATABASE:
            return (
                "Depends",
                "Database workloads can run in either model; storage, "
                "kernel requirements, operational tooling, and isolation "
                "requirements determine the better choice.",
            )

        return "Depends", "The workload requires additional architectural analysis."


def print_heading(title: str) -> None:
    print("\n" + "=" * 76)
    print(title)
    print("=" * 76)


def demonstrate_isolation() -> None:
    print_heading("Isolation")

    print(
        "Container boundary: process, namespace, cgroup, filesystem and "
        "capability isolation while sharing the host kernel."
    )
    print(
        "VM boundary: virtual hardware separates a guest OS and its processes "
        "from processes running in another guest."
    )

    container = Container(
        "api-container",
        Workload("API", WorkloadType.WEB_API, 1.0, 0.5, 2),
        1.0,
        0.5,
    )
    vm = VirtualMachine(
        "api-vm",
        Workload("API", WorkloadType.WEB_API, 1.0, 0.5, 2),
        1.0,
        0.5,
    )

    print(f"Container isolation score: {container.isolation_strength:.2f}")
    print(f"VM isolation score:        {vm.isolation_strength:.2f}")

    print(
        "A container failure normally affects its containerized process "
        "environment. A VM provides an additional guest-kernel boundary."
    )
    print(
        "Security consequence: containers reduce overhead but share more "
        "kernel-level attack surface than separate guest operating systems."
    )


def demonstrate_performance() -> None:
    print_heading("Performance and Startup")

    workload = Workload(
        "order-api",
        WorkloadType.WEB_API,
        cpu_request=1.0,
        memory_request_gb=0.75,
        storage_gb=3.0,
    )

    container = Container("order-api-container", workload, 1.0, 0.75)
    vm = VirtualMachine("order-api-vm", workload, 1.0, 0.75)

    container.start()
    vm.start()

    print(f"Container startup: {container.startup_seconds:.1f} seconds")
    print(f"VM startup:        {vm.startup_seconds:.1f} seconds")
    print(
        f"Container effective memory: "
        f"{container.effective_memory_capacity:.2f} GB"
    )
    print(
        f"VM effective memory: "
        f"{vm.effective_memory_capacity:.2f} GB"
    )

    startup_speedup = vm.startup_seconds / container.startup_seconds
    print(f"Approximate startup advantage: {startup_speedup:.1f}x")

    print(
        "The exact runtime difference depends on image size, guest OS boot "
        "configuration, storage, hardware, orchestration, and application "
        "initialization."
    )


def demonstrate_resource_density() -> None:
    print_heading("Resource Utilization and Density")

    host = Host(
        name="compute-01",
        total_cpu=16.0,
        total_memory_gb=32.0,
        total_storage_gb=500.0,
        kernel="Linux 6.x",
    )

    web_workload = Workload(
        "web",
        WorkloadType.WEB_API,
        cpu_request=1.0,
        memory_request_gb=1.0,
        storage_gb=4.0,
    )

    print("Container density:")
    containers = []
    for index in range(1, 13):
        instance = Container(
            f"web-container-{index}",
            web_workload,
            1.0,
            1.0,
        )
        if host.can_host(instance):
            host.deploy(instance)
            containers.append(instance)

    print(
        f"12 containers requested -> {len(containers)} deployed "
        f"on {host.name}"
    )
    print(
        f"Allocated CPU: {host.allocated_cpu:.1f}/"
        f"{host.total_cpu:.1f}"
    )
    print(
        f"Allocated memory: {host.allocated_memory_gb:.1f}/"
        f"{host.total_memory_gb:.1f} GB"
    )

    vm_host = Host(
        name="vm-host",
        total_cpu=16.0,
        total_memory_gb=32.0,
        total_storage_gb=500.0,
        kernel="Linux 6.x",
    )

    vms = []
    for index in range(1, 12):
        instance = VirtualMachine(
            f"web-vm-{index}",
            web_workload,
            1.0,
            1.0,
        )
        if vm_host.can_host(instance):
            vm_host.deploy(instance)
            vms.append(instance)

    print("\nVM density:")
    print(f"11 VMs requested -> {len(vms)} deployed on {vm_host.name}")
    print(
        f"Allocated CPU: {vm_host.allocated_cpu:.1f}/"
        f"{vm_host.total_cpu:.1f}"
    )
    print(
        f"Allocated memory: {vm_host.allocated_memory_gb:.1f}/"
        f"{vm_host.total_memory_gb:.1f} GB"
    )

    print(
        "\nThe simplified model shows why application containers can achieve "
        "higher density: each VM carries guest-OS overhead."
    )


def demonstrate_portability() -> None:
    print_heading("Portability")

    workload = Workload(
        "inventory-service",
        WorkloadType.WEB_API,
        0.5,
        0.5,
        1.0,
        requires_linux_kernel=True,
    )

    container = Container(
        "inventory-container",
        workload,
        0.5,
        0.5,
    )

    supported_container_hosts = {"linux", "managed-linux", "linux-vm-host"}
    test_hosts = ["linux", "windows", "managed-linux"]

    for host in test_hosts:
        portable = host in supported_container_hosts
        print(
            f"Container image on {host:14}: "
            f"{'supported' if portable else 'requires compatible runtime'}"
        )

    vm = VirtualMachine(
        "inventory-vm",
        workload,
        0.5,
        0.5,
        guest_os="Linux",
    )

    print(
        f"\nContainer portability score: {container.portability_score:.2f}"
    )
    print(f"VM portability score:        {vm.portability_score:.2f}")
    print(
        "Portability does not mean that every image or VM runs unchanged on "
        "every machine. CPU architecture, kernel features, hypervisor support, "
        "drivers, filesystem behavior, and external dependencies still matter."
    )


def demonstrate_workload_comparison() -> None:
    print_heading("Workload Comparison")

    workloads = [
        Workload(
            "public-api",
            WorkloadType.WEB_API,
            1.0,
            0.75,
            5.0,
        ),
        Workload(
            "analytics-batch",
            WorkloadType.BATCH_JOB,
            4.0,
            8.0,
            25.0,
            long_running=False,
        ),
        Workload(
            "old-finance-system",
            WorkloadType.LEGACY_APPLICATION,
            2.0,
            4.0,
            40.0,
            requires_custom_kernel=True,
        ),
        Workload(
            "orders-db",
            WorkloadType.DATABASE,
            4.0,
            12.0,
            200.0,
        ),
    ]

    for workload in workloads:
        runtime, reason = PlacementEngine.recommend(workload)
        print(f"\n{workload.name}")
        print(f"  Type:       {workload.workload_type.value}")
        print(f"  CPU:        {workload.cpu_request:.1f} cores")
        print(f"  Memory:     {workload.memory_request_gb:.1f} GB")
        print(f"  Storage:    {workload.storage_gb:.1f} GB")
        print(f"  Recommendation: {runtime}")
        print(f"  Reason: {reason}")


def demonstrate_failure_modes() -> None:
    print_heading("Failure Modes and Boundaries")

    host = Host(
        "production-host",
        total_cpu=4.0,
        total_memory_gb=8.0,
        total_storage_gb=100.0,
        kernel="Linux",
    )

    workload = Workload(
        "worker",
        WorkloadType.BATCH_JOB,
        1.0,
        1.0,
        5.0,
    )

    container = Container("worker-container", workload, 1.0, 1.0)
    host.deploy(container)

    print("Simulating application failure inside a container.")
    container.stop()
    print(f"Container running: {container.running}")
    print(f"Host remains available: {host.name}")

    print(
        "\nA VM offers stronger isolation between guest operating systems, "
        "but neither model eliminates host-level failure. A host outage "
        "can affect every workload placed on that host."
    )

    print(
        "Operational mitigation requires redundancy, health checks, "
        "restart policies, capacity planning, backup, and workload "
        "distribution across independent failure domains."
    )


def demonstrate_validation() -> None:
    print_heading("Validation and Failure Conditions")

    invalid_workload = Workload(
        "invalid-api",
        WorkloadType.WEB_API,
        -1.0,
        -2.0,
        -5.0,
    )

    errors = []

    if invalid_workload.cpu_request <= 0:
        errors.append("CPU request must be greater than zero.")
    if invalid_workload.memory_request_gb <= 0:
        errors.append("Memory request must be greater than zero.")
    if invalid_workload.storage_gb < 0:
        errors.append("Storage cannot be negative.")

    print("Validation results:")
    for error in errors:
        print(f"  {error}")

    print(
        "\nResource limits should be validated before deployment because "
        "invalid requests can cause scheduling failures or unsafe resource "
        "assumptions."
    )


def benchmark_model() -> None:
    print_heading("Capacity Model")

    host_cpu = 32.0
    host_memory = 64.0

    container_cpu_overhead = 0.02
    container_memory_overhead = 0.08
    vm_cpu_overhead = 0.20
    vm_memory_overhead = 0.65

    application_cpu = 1.0
    application_memory = 1.0

    container_cpu_per_workload = application_cpu + container_cpu_overhead
    container_memory_per_workload = application_memory + container_memory_overhead

    vm_cpu_per_workload = application_cpu + vm_cpu_overhead
    vm_memory_per_workload = application_memory + vm_memory_overhead

    container_capacity = min(
        floor_division(host_cpu, container_cpu_per_workload),
        floor_division(host_memory, container_memory_per_workload),
    )

    vm_capacity = min(
        floor_division(host_cpu, vm_cpu_per_workload),
        floor_division(host_memory, vm_memory_per_workload),
    )

    print(f"Estimated container capacity: {container_capacity}")
    print(f"Estimated VM capacity:        {vm_capacity}")
    print(
        "This is a conceptual capacity calculation, not a production "
        "benchmark. Real systems must measure CPU throttling, memory pressure, "
        "I/O, network throughput, cache behavior, and application latency."
    )


def floor_division(capacity: float, per_instance: float) -> int:
    if per_instance <= 0:
        raise ValueError("Per-instance resource consumption must be positive.")
    return int(capacity // per_instance)


def production_decision_matrix() -> None:
    print_heading("Production Decision Matrix")

    criteria = [
        ("Fast startup", "Container", "VM"),
        ("Shared host kernel", "Required", "Not required"),
        ("Strong guest OS boundary", "Lower", "Higher"),
        ("High application density", "Excellent", "Good"),
        ("Legacy OS environment", "Limited", "Strong"),
        ("Application packaging", "Excellent", "Good"),
        ("Kernel customization", "Limited by host", "Strong"),
        ("Isolation of untrusted workloads", "Requires hardening", "Stronger boundary"),
        ("Operational consistency", "High with images", "High with VM images"),
        ("Resource overhead", "Low", "Higher"),
    ]

    width = max(len(row[0]) for row in criteria) + 2

    print(f"{'Criterion':<{width}} {'Containers':<22} Virtual Machines")
    print("-" * 76)
    for criterion, containers, vms in criteria:
        print(f"{criterion:<{width}} {containers:<22} {vms}")


def main() -> None:
    print_heading("Containers vs Virtual Machines")
    print(
        "This executable model compares two isolation strategies without "
        "requiring Docker, a hypervisor, or external packages."
    )

    demonstrate_isolation()
    demonstrate_performance()
    demonstrate_resource_density()
    demonstrate_portability()
    demonstrate_workload_comparison()
    demonstrate_failure_modes()
    demonstrate_validation()
    benchmark_model()
    production_decision_matrix()

    print_heading("Final Technical Observation")
    print(
        "Containers and VMs solve overlapping infrastructure problems using "
        "different isolation boundaries. Containers package processes while "
        "sharing a kernel; VMs virtualize hardware sufficiently to run "
        "independent guest operating systems."
    )
    print(
        "A production architecture may legitimately use both: VMs can form "
        "the infrastructure boundary while containers provide application "
        "packaging and density inside those VMs."
    )


if __name__ == "__main__":
    main()
