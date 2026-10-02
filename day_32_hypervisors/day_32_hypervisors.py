#!/usr/bin/env python3
"""
Hypervisors: Type 1 and Type 2 virtualization architecture.

This executable learning model builds a small virtualization simulator. It
demonstrates the distinction between bare-metal (Type 1) and hosted (Type 2)
hypervisors, virtual CPUs, virtual memory, virtual devices, VM lifecycle,
resource allocation, scheduling, isolation, overcommitment, snapshots,
failure handling, and performance/security trade-offs.

The program intentionally models the architectural mechanisms rather than
pretending to be a real CPU or hardware hypervisor. Real hypervisors such as
KVM, VMware ESXi, Microsoft Hyper-V, and VirtualBox depend on processor
virtualization extensions, memory-management hardware, device virtualization,
interrupt handling, and privileged kernel or firmware components that cannot
be reproduced faithfully with ordinary Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import hashlib
import json
import random
import time
from typing import Deque, Dict, Iterable, List, Optional, Tuple


class HypervisorType(Enum):
    TYPE_1 = "Type 1 / bare-metal"
    TYPE_2 = "Type 2 / hosted"


class VMState(Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"


class VMError(RuntimeError):
    """Base exception for virtualization-specific failures."""


class ResourceError(VMError):
    """Raised when a VM cannot receive the requested resources."""


class IsolationError(VMError):
    """Raised when a simulated isolation policy is violated."""


@dataclass(frozen=True)
class CPU:
    """A physical processor core visible to the hypervisor."""

    core_id: int


@dataclass
class MemoryPage:
    """A guest physical page mapped to simulated host memory."""

    guest_frame: int
    host_frame: int
    writable: bool = True
    dirty: bool = False


@dataclass
class VirtualDisk:
    name: str
    size_gib: int
    used_gib: int = 0

    def write(self, amount_gib: int) -> None:
        if amount_gib < 0:
            raise ValueError("Disk writes cannot be negative.")
        if self.used_gib + amount_gib > self.size_gib:
            raise ResourceError(
                f"Disk {self.name} cannot accept {amount_gib} GiB; "
                f"{self.size_gib - self.used_gib} GiB remains."
            )
        self.used_gib += amount_gib


@dataclass
class VirtualNetworkCard:
    name: str
    mac_address: str
    connected: bool = True
    packets_sent: int = 0
    packets_received: int = 0

    def send(self, packets: int) -> None:
        if not self.connected:
            raise VMError(f"Network interface {self.name} is disconnected.")
        if packets < 0:
            raise ValueError("Packet count cannot be negative.")
        self.packets_sent += packets


@dataclass
class VM:
    """
    A virtual machine's resource contract.

    vcpus represent virtual processors, memory_mib represents guest RAM,
    and memory_limit_mib is a safety boundary used by the simulator.
    """

    vm_id: str
    name: str
    vcpus: int
    memory_mib: int
    disk: VirtualDisk
    nic: VirtualNetworkCard
    state: VMState = VMState.CREATED
    cpu_time_ms: int = 0
    memory_used_mib: int = 0
    guest_pages: Dict[int, MemoryPage] = field(default_factory=dict)
    snapshot: Optional[dict] = None

    @property
    def memory_limit_mib(self) -> int:
        return self.memory_mib

    def allocate_guest_memory(self, amount_mib: int) -> None:
        if amount_mib < 0:
            raise ValueError("Memory allocation cannot be negative.")
        new_usage = self.memory_used_mib + amount_mib
        if new_usage > self.memory_limit_mib:
            raise ResourceError(
                f"{self.name} requested {amount_mib} MiB, but only "
                f"{self.memory_limit_mib - self.memory_used_mib} MiB remains."
            )
        self.memory_used_mib = new_usage

    def free_guest_memory(self, amount_mib: int) -> None:
        if amount_mib < 0 or amount_mib > self.memory_used_mib:
            raise ResourceError("Invalid guest memory release.")
        self.memory_used_mib -= amount_mib

    def run_cpu(self, milliseconds: int) -> None:
        if self.state != VMState.RUNNING:
            raise VMError(f"{self.name} is not runnable.")
        if milliseconds <= 0:
            raise ValueError("CPU runtime must be positive.")
        self.cpu_time_ms += milliseconds

    def take_snapshot(self) -> None:
        self.snapshot = {
            "state": self.state.value,
            "cpu_time_ms": self.cpu_time_ms,
            "memory_used_mib": self.memory_used_mib,
            "disk_used_gib": self.disk.used_gib,
            "guest_pages": {
                frame: page.host_frame
                for frame, page in self.guest_pages.items()
            },
        }

    def restore_snapshot(self) -> None:
        if self.snapshot is None:
            raise VMError(f"{self.name} has no snapshot.")
        snapshot = self.snapshot
        self.cpu_time_ms = snapshot["cpu_time_ms"]
        self.memory_used_mib = snapshot["memory_used_mib"]
        self.disk.used_gib = snapshot["disk_used_gib"]
        self.state = VMState(snapshot["state"])


@dataclass
class Host:
    """
    Physical host resources.

    A Type 1 hypervisor executes as the primary virtualization layer on the
    machine. A Type 2 hypervisor instead consumes resources from a host OS.
    """

    name: str
    physical_cpus: int
    memory_mib: int
    storage_gib: int
    host_os: Optional[str] = None
    hypervisor_type: HypervisorType = HypervisorType.TYPE_1

    @property
    def is_bare_metal(self) -> bool:
        return self.host_os is None and self.hypervisor_type == HypervisorType.TYPE_1

    @property
    def cpu_capacity(self) -> int:
        return self.physical_cpus

    def architecture_description(self) -> str:
        if self.hypervisor_type == HypervisorType.TYPE_1:
            return (
                f"{self.name}: hardware -> {self.hypervisor_type.value} -> "
                "virtual machines"
            )
        return (
            f"{self.name}: hardware -> host OS -> "
            f"{self.hypervisor_type.value} -> virtual machines"
        )


class MemoryManager:
    """
    Simulates guest-to-host memory mapping.

    A real hypervisor may use nested page tables such as Intel EPT or AMD NPT.
    Here the mapping is explicit so the two address spaces remain conceptually
    visible.
    """

    def __init__(self, host_frames: int) -> None:
        if host_frames <= 0:
            raise ValueError("The host must provide at least one frame.")
        self.free_frames: Deque[int] = deque(range(host_frames))
        self.allocations: Dict[str, Dict[int, MemoryPage]] = defaultdict(dict)

    def map_guest_page(self, vm: VM, guest_frame: int) -> MemoryPage:
        if guest_frame < 0:
            raise ValueError("Guest frame cannot be negative.")
        if guest_frame in self.allocations[vm.vm_id]:
            return self.allocations[vm.vm_id][guest_frame]
        if not self.free_frames:
            raise ResourceError("Host memory is exhausted.")

        host_frame = self.free_frames.popleft()
        page = MemoryPage(guest_frame, host_frame)
        self.allocations[vm.vm_id][guest_frame] = page
        vm.guest_pages[guest_frame] = page
        return page

    def unmap_vm(self, vm: VM) -> None:
        pages = self.allocations.pop(vm.vm_id, {})
        for page in pages.values():
            self.free_frames.append(page.host_frame)
        vm.guest_pages.clear()


class VirtualCPU:
    """
    Models the conceptual distinction between a guest vCPU and a physical CPU.

    The guest thinks it owns a processor. The hypervisor schedules that vCPU
    onto an available physical CPU and controls privileged operations.
    """

    def __init__(self, vm: VM, vcpu_id: int) -> None:
        self.vm = vm
        self.vcpu_id = vcpu_id
        self.instructions_executed = 0

    def execute(self, instructions: int) -> None:
        if instructions <= 0:
            raise ValueError("Instruction count must be positive.")
        self.instructions_executed += instructions


class Scheduler:
    """A small round-robin vCPU scheduler."""

    def __init__(self, host: Host) -> None:
        self.host = host
        self.ready_queue: Deque[VirtualCPU] = deque()
        self.running: Dict[int, VirtualCPU] = {}

    def enqueue(self, vcpu: VirtualCPU) -> None:
        if vcpu.vm.state == VMState.RUNNING:
            self.ready_queue.append(vcpu)

    def tick(self, quantum_ms: int = 10) -> List[str]:
        if quantum_ms <= 0:
            raise ValueError("Scheduler quantum must be positive.")

        events = []
        self.running.clear()

        for core_id in range(self.host.cpu_capacity):
            if not self.ready_queue:
                break

            vcpu = self.ready_queue.popleft()
            self.running[core_id] = vcpu

            vcpu.execute(quantum_ms * 1000)
            vcpu.vm.run_cpu(quantum_ms)

            events.append(
                f"core={core_id} ran {vcpu.vm.name}/vCPU{vcpu.vcpu_id} "
                f"for {quantum_ms} ms"
            )

            if vcpu.vm.state == VMState.RUNNING:
                self.ready_queue.append(vcpu)

        return events


class Hypervisor:
    """
    Resource and lifecycle controller.

    This class is the central architectural model. It does not emulate
    privileged CPU instructions; it represents the policy boundary that a
    hypervisor provides between guests and physical resources.
    """

    def __init__(
        self,
        host: Host,
        allow_overcommit: bool = False,
    ) -> None:
        self.host = host
        self.allow_overcommit = allow_overcommit
        self.vms: Dict[str, VM] = {}
        self.memory = MemoryManager(max(1, host.memory_mib // 4))
        self.scheduler = Scheduler(host)
        self.used_memory_mib = 0
        self.used_storage_gib = 0
        self.used_vcpus = 0

    def create_vm(
        self,
        vm_id: str,
        name: str,
        vcpus: int,
        memory_mib: int,
        disk_gib: int,
    ) -> VM:
        if vm_id in self.vms:
            raise VMError(f"VM identifier {vm_id!r} already exists.")
        if not vm_id.strip() or not name.strip():
            raise ValueError("VM identifier and name are required.")
        if vcpus <= 0 or memory_mib <= 0 or disk_gib <= 0:
            raise ValueError("VM resources must be positive.")

        if not self.allow_overcommit:
            if self.used_vcpus + vcpus > self.host.physical_cpus:
                raise ResourceError("Requested vCPUs exceed physical CPU capacity.")
            if self.used_memory_mib + memory_mib > self.host.memory_mib:
                raise ResourceError("Requested RAM exceeds host capacity.")
            if self.used_storage_gib + disk_gib > self.host.storage_gib:
                raise ResourceError("Requested storage exceeds host capacity.")

        vm = VM(
            vm_id=vm_id,
            name=name,
            vcpus=vcpus,
            memory_mib=memory_mib,
            disk=VirtualDisk(f"{vm_id}-disk", disk_gib),
            nic=VirtualNetworkCard(
                name=f"{vm_id}-nic",
                mac_address=self._generate_mac(vm_id),
            ),
        )
        self.vms[vm_id] = vm
        self.used_vcpus += vcpus
        self.used_memory_mib += memory_mib
        self.used_storage_gib += disk_gib
        return vm

    @staticmethod
    def _generate_mac(vm_id: str) -> str:
        digest = hashlib.sha256(vm_id.encode()).digest()
        octets = [0x02, 0x00, digest[0], digest[1], digest[2], digest[3]]
        return ":".join(f"{octet:02x}" for octet in octets)

    def start_vm(self, vm_id: str) -> None:
        vm = self._get_vm(vm_id)
        if vm.state == VMState.RUNNING:
            raise VMError(f"{vm.name} is already running.")
        if vm.state == VMState.FAILED:
            raise VMError(f"{vm.name} must be repaired before it can start.")

        vm.state = VMState.RUNNING
        for vcpu_id in range(vm.vcpus):
            self.scheduler.enqueue(VirtualCPU(vm, vcpu_id))

    def pause_vm(self, vm_id: str) -> None:
        vm = self._get_vm(vm_id)
        if vm.state != VMState.RUNNING:
            raise VMError("Only a running VM can be paused.")
        vm.state = VMState.PAUSED

    def resume_vm(self, vm_id: str) -> None:
        vm = self._get_vm(vm_id)
        if vm.state != VMState.PAUSED:
            raise VMError("Only a paused VM can be resumed.")
        vm.state = VMState.RUNNING
        for vcpu_id in range(vm.vcpus):
            self.scheduler.enqueue(VirtualCPU(vm, vcpu_id))

    def stop_vm(self, vm_id: str) -> None:
        vm = self._get_vm(vm_id)
        if vm.state == VMState.STOPPED:
            return
        vm.state = VMState.STOPPED

    def map_guest_memory(self, vm_id: str, guest_frames: Iterable[int]) -> None:
        vm = self._get_vm(vm_id)
        for frame in guest_frames:
            self.memory.map_guest_page(vm, frame)

    def _get_vm(self, vm_id: str) -> VM:
        try:
            return self.vms[vm_id]
        except KeyError as exc:
            raise VMError(f"Unknown VM {vm_id!r}.") from exc

    def utilization(self) -> dict:
        return {
            "physical_cpus": self.host.physical_cpus,
            "allocated_vcpus": self.used_vcpus,
            "memory_mib": self.host.memory_mib,
            "allocated_memory_mib": self.used_memory_mib,
            "storage_gib": self.host.storage_gib,
            "allocated_storage_gib": self.used_storage_gib,
            "running_vms": sum(
                vm.state == VMState.RUNNING for vm in self.vms.values()
            ),
        }

    def export_state(self) -> str:
        return json.dumps(
            {
                "host": self.host.architecture_description(),
                "vms": [
                    {
                        "id": vm.vm_id,
                        "name": vm.name,
                        "vcpus": vm.vcpus,
                        "memory_mib": vm.memory_mib,
                        "state": vm.state.value,
                        "cpu_time_ms": vm.cpu_time_ms,
                        "memory_used_mib": vm.memory_used_mib,
                        "disk_used_gib": vm.disk.used_gib,
                    }
                    for vm in self.vms.values()
                ],
            },
            indent=2,
        )


def demonstrate_architectures() -> None:
    print("\n=== Virtualization Architectures ===")

    bare_metal = Host(
        name="production-host-01",
        physical_cpus=8,
        memory_mib=32768,
        storage_gib=1000,
        hypervisor_type=HypervisorType.TYPE_1,
    )

    hosted = Host(
        name="developer-workstation",
        physical_cpus=8,
        memory_mib=16384,
        storage_gib=1000,
        host_os="Windows 11",
        hypervisor_type=HypervisorType.TYPE_2,
    )

    print(bare_metal.architecture_description())
    print(hosted.architecture_description())

    print(
        "\nType 1 places the virtualization layer directly above hardware. "
        "Type 2 adds a host operating system between hardware and the "
        "virtualization software."
    )


def demonstrate_vm_lifecycle() -> Hypervisor:
    print("\n=== VM Lifecycle ===")

    host = Host(
        name="cluster-node-a",
        physical_cpus=4,
        memory_mib=16384,
        storage_gib=500,
        hypervisor_type=HypervisorType.TYPE_1,
    )
    hv = Hypervisor(host)

    web = hv.create_vm(
        vm_id="vm-web",
        name="web-server",
        vcpus=2,
        memory_mib=4096,
        disk_gib=60,
    )

    database = hv.create_vm(
        vm_id="vm-db",
        name="database-server",
        vcpus=1,
        memory_mib=4096,
        disk_gib=100,
    )

    print(f"{web.name}: {web.state.value}")
    hv.start_vm(web.vm_id)
    hv.start_vm(database.vm_id)
    print(f"{web.name}: {web.state.value}")
    print(f"{database.name}: {database.state.value}")

    web.allocate_guest_memory(1024)
    web.disk.write(5)
    web.nic.send(100)

    print("Scheduler activity:")
    for _ in range(3):
        for event in hv.scheduler.tick():
            print(f"  {event}")

    hv.pause_vm(database.vm_id)
    print(f"{database.name}: {database.state.value}")
    hv.resume_vm(database.vm_id)
    print(f"{database.name}: {database.state.value}")

    return hv


def demonstrate_memory_virtualization(hv: Hypervisor) -> None:
    print("\n=== Memory Virtualization ===")

    vm = hv.vms["vm-web"]

    vm.allocate_guest_memory(2048)
    hv.map_guest_memory(vm.vm_id, [0, 1, 2, 3])

    print("Guest-to-host frame mappings:")
    for guest_frame, page in sorted(vm.guest_pages.items()):
        print(
            f"  guest frame {guest_frame} -> host frame {page.host_frame}, "
            f"writable={page.writable}"
        )

    print(
        "The guest operates on guest physical addresses. The hypervisor and "
        "hardware memory-management mechanisms translate them to host frames."
    )

    try:
        hv.memory.map_guest_page(vm, 0)
        print("Repeated mapping reused the existing mapping.")
    except ResourceError as exc:
        print(f"Memory error: {exc}")


def demonstrate_snapshots(hv: Hypervisor) -> None:
    print("\n=== VM Snapshot Semantics ===")

    vm = hv.vms["vm-web"]
    before = vm.memory_used_mib

    vm.take_snapshot()
    vm.allocate_guest_memory(512)
    vm.disk.write(2)

    print(
        f"Before snapshot memory: {before} MiB; "
        f"after workload: {vm.memory_used_mib} MiB"
    )

    vm.restore_snapshot()
    print(
        f"After restore memory: {vm.memory_used_mib} MiB; "
        f"disk usage: {vm.disk.used_gib} GiB"
    )

    print(
        "A real snapshot implementation must also account for disk state, "
        "device state, memory consistency, and application-level consistency."
    )


def demonstrate_overcommitment() -> None:
    print("\n=== Resource Overcommitment ===")

    host = Host(
        name="consolidation-host",
        physical_cpus=4,
        memory_mib=8192,
        storage_gib=500,
    )

    strict_hv = Hypervisor(host, allow_overcommit=False)
    strict_hv.create_vm("a", "service-a", 2, 4096, 40)

    try:
        strict_hv.create_vm("b", "service-b", 2, 4096, 40)
        print("Unexpected success.")
    except ResourceError as exc:
        print(f"Strict allocation rejected: {exc}")

    flexible_hv = Hypervisor(host, allow_overcommit=True)
    flexible_hv.create_vm("a", "service-a", 4, 4096, 40)
    flexible_hv.create_vm("b", "service-b", 4, 4096, 40)

    print(
        "Overcommitment permits configured virtual capacity to exceed physical "
        "capacity, but it does not create physical resources."
    )
    print(json.dumps(flexible_hv.utilization(), indent=2))


def demonstrate_failures_and_validation(hv: Hypervisor) -> None:
    print("\n=== Failure Conditions and Validation ===")

    vm = hv.vms["vm-web"]

    for operation in (
        lambda: vm.allocate_guest_memory(-1),
        lambda: vm.disk.write(1000),
        lambda: vm.nic.send(-10),
    ):
        try:
            operation()
        except (ValueError, ResourceError, VMError) as exc:
            print(f"Rejected invalid operation: {exc}")

    try:
        hv.start_vm("missing-vm")
    except VMError as exc:
        print(f"Unknown VM handled safely: {exc}")

    vm.nic.connected = False
    try:
        vm.nic.send(1)
    except VMError as exc:
        print(f"Virtual device failure handled safely: {exc}")


def demonstrate_security_boundaries() -> None:
    print("\n=== Isolation and Security Model ===")

    print(
        "A hypervisor must prevent one guest from directly reading or writing "
        "another guest's memory, accessing unauthorized devices, or escaping "
        "its virtual CPU privilege boundary."
    )

    isolation_rules = {
        "memory": "guest virtual/physical addresses are translated and checked",
        "cpu": "privileged guest operations are controlled by the virtualization layer",
        "network": "virtual NIC traffic is attached to an explicit virtual network",
        "storage": "virtual disks expose bounded logical capacity",
        "management": "host-side management interfaces require authentication",
    }

    for area, rule in isolation_rules.items():
        print(f"{area:10} -> {rule}")

    print(
        "A simulator can model policy boundaries, but real isolation also "
        "depends on processor privilege levels, IOMMU configuration, device "
        "emulation, memory protection, patching, and hypervisor correctness."
    )


def demonstrate_type_1_vs_type_2() -> None:
    print("\n=== Type 1 vs Type 2 Architectural Trade-offs ===")

    rows = [
        ("Execution layer", "Directly above hardware", "Above a host operating system"),
        ("Typical role", "Servers, clouds, datacenters", "Desktop development and testing"),
        ("Host OS dependency", "No general-purpose host OS beneath it", "Yes"),
        ("Resource control", "Direct hardware-oriented control", "Mediated through host OS"),
        ("Failure surface", "Hypervisor and hardware boundary", "Hypervisor plus host OS boundary"),
        ("Typical isolation goal", "Strong workload separation", "Convenient local virtualization"),
    ]

    for property_name, type_1, type_2 in rows:
        print(f"{property_name:20} | Type 1: {type_1} | Type 2: {type_2}")


def demonstrate_production_considerations() -> None:
    print("\n=== Production Considerations ===")

    considerations = {
        "CPU": (
            "vCPU scheduling, CPU pinning, NUMA locality, frequency behavior, "
            "and virtualization extensions influence performance."
        ),
        "Memory": (
            "Nested page translation, huge pages, NUMA placement, ballooning, "
            "swapping, and overcommitment affect latency and capacity."
        ),
        "I/O": (
            "Paravirtualized devices can reduce the cost of device emulation; "
            "SR-IOV and device passthrough can provide more direct I/O paths."
        ),
        "Security": (
            "The hypervisor is part of the trusted computing base. Isolation "
            "failures can cross VM boundaries, so patching and least privilege matter."
        ),
        "Operations": (
            "Live migration, high availability, monitoring, backup, snapshots, "
            "and capacity planning turn virtualization into an operational platform."
        ),
    }

    for area, explanation in considerations.items():
        print(f"{area}: {explanation}")


def main() -> None:
    random.seed(7)

    demonstrate_architectures()
    hypervisor = demonstrate_vm_lifecycle()
    demonstrate_memory_virtualization(hypervisor)
    demonstrate_snapshots(hypervisor)
    demonstrate_overcommitment()
    demonstrate_failures_and_validation(hypervisor)
    demonstrate_security_boundaries()
    demonstrate_type_1_vs_type_2()
    demonstrate_production_considerations()

    print("\n=== Exported Hypervisor State ===")
    print(hypervisor.export_state())

    print("\nSimulation completed successfully.")


if __name__ == "__main__":
    main()
