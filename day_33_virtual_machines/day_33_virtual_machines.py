#!/usr/bin/env python3
"""
Virtual Machines: lifecycle, CPU allocation, memory allocation, virtual disks,
and snapshots.

This self-contained simulation models the resource and lifecycle decisions made
by a small virtualization platform. It does not create real VMs or interact
with a hypervisor. Instead, it implements the control-plane logic needed to
reason about VM states, CPU scheduling, memory reservations/limits, virtual
disks, snapshots, and operational failures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import math
import shutil
import tempfile


class VMState(str, Enum):
    DEFINED = "defined"
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    SUSPENDED = "suspended"
    ERROR = "error"


class DiskFormat(str, Enum):
    RAW = "raw"
    QCOW2 = "qcow2"
    VMDK = "vmdk"


class SnapshotState(str, Enum):
    ACTIVE = "active"
    DELETED = "deleted"


@dataclass
class CPUAllocation:
    """CPU topology and scheduling limits assigned to one VM."""

    vcpus: int
    cpu_limit_percent: float = 100.0
    cpu_shares: int = 1024
    pinning: Dict[int, int] = field(default_factory=dict)

    def validate(self, host_vcpus: int) -> None:
        if self.vcpus < 1:
            raise ValueError("A VM must have at least one vCPU.")
        if self.vcpus > host_vcpus:
            raise ValueError(
                f"VM requests {self.vcpus} vCPUs but host has only "
                f"{host_vcpus} logical CPUs."
            )
        if not 1 <= self.cpu_limit_percent <= self.vcpus * 100:
            raise ValueError(
                "CPU limit must be between 1% and vCPU_count * 100%."
            )
        if self.cpu_shares < 2:
            raise ValueError("CPU shares must be at least 2.")

        for vcpu, physical_cpu in self.pinning.items():
            if not 0 <= vcpu < self.vcpus:
                raise ValueError(f"Invalid vCPU index for pinning: {vcpu}")
            if not 0 <= physical_cpu < host_vcpus:
                raise ValueError(
                    f"Invalid host CPU index for pinning: {physical_cpu}"
                )


@dataclass
class MemoryAllocation:
    """Memory reservation, configured memory, and hard limit."""

    memory_mb: int
    reservation_mb: int
    limit_mb: int
    ballooning: bool = False

    def validate(self, host_memory_mb: int) -> None:
        if self.memory_mb <= 0:
            raise ValueError("Configured VM memory must be positive.")
        if self.reservation_mb < 0:
            raise ValueError("Memory reservation cannot be negative.")
        if self.limit_mb < self.memory_mb:
            raise ValueError("Memory limit cannot be below configured memory.")
        if self.reservation_mb > self.memory_mb:
            raise ValueError(
                "Memory reservation cannot exceed configured memory."
            )
        if self.limit_mb > host_memory_mb:
            raise ValueError(
                "Memory limit cannot exceed the host's physical memory."
            )


@dataclass
class VirtualDisk:
    """A virtual disk backed by a file or logical storage object."""

    name: str
    capacity_gb: float
    allocated_gb: float
    format: DiskFormat = DiskFormat.QCOW2
    thin_provisioned: bool = True
    read_only: bool = False

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Disk name cannot be empty.")
        if self.capacity_gb <= 0:
            raise ValueError("Disk capacity must be positive.")
        if self.allocated_gb < 0:
            raise ValueError("Allocated disk space cannot be negative.")
        if self.allocated_gb > self.capacity_gb:
            raise ValueError("Allocated space cannot exceed disk capacity.")

    @property
    def free_virtual_space_gb(self) -> float:
        return self.capacity_gb - self.allocated_gb

    def write(self, amount_gb: float) -> None:
        if self.read_only:
            raise PermissionError(f"Disk {self.name} is read-only.")
        if amount_gb < 0:
            raise ValueError("Write size cannot be negative.")
        if self.allocated_gb + amount_gb > self.capacity_gb:
            raise OSError(
                f"Disk {self.name} would exceed its virtual capacity."
            )
        self.allocated_gb += amount_gb


@dataclass
class Snapshot:
    """A point-in-time VM state record.

    The simulation stores disk allocation and VM configuration metadata.
    Real hypervisors may use copy-on-write chains, memory state files, or
    provider-specific metadata instead of duplicating every disk byte.
    """

    snapshot_id: str
    vm_name: str
    description: str
    state_at_capture: VMState
    cpu: CPUAllocation
    memory: MemoryAllocation
    disk_allocations: Dict[str, float]
    state: SnapshotState = SnapshotState.ACTIVE


@dataclass
class VirtualMachine:
    """A VM managed by the simulated hypervisor."""

    name: str
    cpu: CPUAllocation
    memory: MemoryAllocation
    disks: List[VirtualDisk]
    state: VMState = VMState.DEFINED
    snapshots: Dict[str, Snapshot] = field(default_factory=dict)
    uptime_ticks: int = 0

    def validate(self, host: "Hypervisor") -> None:
        self.cpu.validate(host.host_vcpus)
        self.memory.validate(host.host_memory_mb)

        if not self.disks:
            raise ValueError("A VM must have at least one virtual disk.")

        for disk in self.disks:
            disk.validate()

        duplicate_names = {
            disk.name for disk in self.disks
            if sum(existing.name == disk.name for existing in self.disks) > 1
        }
        if duplicate_names:
            raise ValueError(
                f"Duplicate virtual disk names: {sorted(duplicate_names)}"
            )

    def total_disk_capacity(self) -> float:
        return sum(disk.capacity_gb for disk in self.disks)

    def total_disk_allocation(self) -> float:
        return sum(disk.allocated_gb for disk in self.disks)

    def tick(self, ticks: int = 1) -> None:
        if ticks < 0:
            raise ValueError("Ticks cannot be negative.")
        if self.state == VMState.RUNNING:
            self.uptime_ticks += ticks


class Hypervisor:
    """Small control-plane model for host-level VM resource management."""

    def __init__(
        self,
        name: str,
        host_vcpus: int,
        host_memory_mb: int,
        storage_capacity_gb: float,
    ) -> None:
        if host_vcpus < 1:
            raise ValueError("Host must expose at least one logical CPU.")
        if host_memory_mb < 512:
            raise ValueError("Host memory is unrealistically small.")
        if storage_capacity_gb <= 0:
            raise ValueError("Host storage must be positive.")

        self.name = name
        self.host_vcpus = host_vcpus
        self.host_memory_mb = host_memory_mb
        self.storage_capacity_gb = storage_capacity_gb
        self.vms: Dict[str, VirtualMachine] = {}

    def _used_memory_reservation(self, exclude: Optional[str] = None) -> int:
        return sum(
            vm.memory.reservation_mb
            for name, vm in self.vms.items()
            if name != exclude and vm.state != VMState.ERROR
        )

    def _used_storage(self, exclude: Optional[str] = None) -> float:
        return sum(
            vm.total_disk_allocation()
            for name, vm in self.vms.items()
            if name != exclude
        )

    def create_vm(self, vm: VirtualMachine) -> None:
        if vm.name in self.vms:
            raise KeyError(f"VM {vm.name!r} already exists.")

        vm.validate(self)

        required_memory = self._used_memory_reservation() + vm.memory.reservation_mb
        if required_memory > self.host_memory_mb:
            raise MemoryError(
                f"Creating {vm.name} would reserve {required_memory} MB, "
                f"above host capacity of {self.host_memory_mb} MB."
            )

        required_storage = self._used_storage() + vm.total_disk_allocation()
        if required_storage > self.storage_capacity_gb:
            raise OSError(
                f"Creating {vm.name} would allocate {required_storage:.1f} GB, "
                f"above host capacity of {self.storage_capacity_gb:.1f} GB."
            )

        vm.state = VMState.STOPPED
        self.vms[vm.name] = vm

    def start_vm(self, name: str) -> None:
        vm = self.get_vm(name)

        if vm.state == VMState.RUNNING:
            raise RuntimeError(f"VM {name} is already running.")
        if vm.state not in {VMState.STOPPED, VMState.PAUSED}:
            raise RuntimeError(
                f"VM {name} cannot start from state {vm.state.value}."
            )

        self._validate_runtime_memory(vm)
        vm.state = VMState.RUNNING

    def stop_vm(self, name: str) -> None:
        vm = self.get_vm(name)

        if vm.state == VMState.STOPPED:
            return
        if vm.state not in {
            VMState.RUNNING,
            VMState.PAUSED,
            VMState.SUSPENDED,
        }:
            raise RuntimeError(
                f"VM {name} cannot stop from state {vm.state.value}."
            )

        vm.state = VMState.STOPPED

    def pause_vm(self, name: str) -> None:
        vm = self.get_vm(name)
        if vm.state != VMState.RUNNING:
            raise RuntimeError("Only a running VM can be paused.")
        vm.state = VMState.PAUSED

    def resume_vm(self, name: str) -> None:
        vm = self.get_vm(name)
        if vm.state != VMState.PAUSED:
            raise RuntimeError("Only a paused VM can be resumed.")
        vm.state = VMState.RUNNING

    def suspend_vm(self, name: str) -> None:
        vm = self.get_vm(name)
        if vm.state != VMState.RUNNING:
            raise RuntimeError("Only a running VM can be suspended.")

        # A real hypervisor would write CPU/device/memory state to persistent
        # storage. Here the state transition is enough to model that lifecycle.
        vm.state = VMState.SUSPENDED

    def delete_vm(self, name: str) -> None:
        vm = self.get_vm(name)
        if vm.state == VMState.RUNNING:
            raise RuntimeError("Stop a running VM before deletion.")
        del self.vms[name]

    def resize_memory(
        self,
        name: str,
        memory_mb: int,
        reservation_mb: Optional[int] = None,
        limit_mb: Optional[int] = None,
    ) -> None:
        vm = self.get_vm(name)

        new_memory = MemoryAllocation(
            memory_mb=memory_mb,
            reservation_mb=(
                reservation_mb
                if reservation_mb is not None
                else min(vm.memory.reservation_mb, memory_mb)
            ),
            limit_mb=(
                limit_mb
                if limit_mb is not None
                else max(vm.memory.limit_mb, memory_mb)
            ),
            ballooning=vm.memory.ballooning,
        )
        new_memory.validate(self.host_memory_mb)

        available = (
            self.host_memory_mb
            - self._used_memory_reservation(exclude=name)
        )
        if new_memory.reservation_mb > available:
            raise MemoryError(
                f"Only {available} MB is available for VM {name}'s reservation."
            )

        vm.memory = new_memory

    def resize_disk(self, vm_name: str, disk_name: str, new_capacity_gb: float) -> None:
        vm = self.get_vm(vm_name)
        disk = self._find_disk(vm, disk_name)

        if new_capacity_gb <= disk.capacity_gb:
            raise ValueError(
                "This simulation only supports disk expansion, not shrinking."
            )

        additional_allocated = max(
            0.0, new_capacity_gb - disk.capacity_gb
        ) if not disk.thin_provisioned else 0.0

        if (
            self._used_storage(exclude=vm_name)
            + vm.total_disk_allocation()
            + additional_allocated
            > self.storage_capacity_gb
        ):
            raise OSError("Host storage is insufficient for this expansion.")

        disk.capacity_gb = new_capacity_gb

    def write_disk(
        self,
        vm_name: str,
        disk_name: str,
        amount_gb: float,
    ) -> None:
        vm = self.get_vm(vm_name)
        if vm.state != VMState.RUNNING:
            raise RuntimeError("A VM must be running to perform simulated I/O.")

        disk = self._find_disk(vm, disk_name)

        if disk.thin_provisioned:
            physical_required = amount_gb
            if self._used_storage() + physical_required > self.storage_capacity_gb:
                raise OSError("Thin-provisioned backing storage is full.")

        disk.write(amount_gb)

    def create_snapshot(
        self,
        vm_name: str,
        snapshot_id: str,
        description: str,
    ) -> Snapshot:
        vm = self.get_vm(vm_name)

        if snapshot_id in vm.snapshots:
            raise KeyError(f"Snapshot {snapshot_id!r} already exists.")

        snapshot = Snapshot(
            snapshot_id=snapshot_id,
            vm_name=vm.name,
            description=description,
            state_at_capture=vm.state,
            cpu=CPUAllocation(
                vcpus=vm.cpu.vcpus,
                cpu_limit_percent=vm.cpu.cpu_limit_percent,
                cpu_shares=vm.cpu.cpu_shares,
                pinning=dict(vm.cpu.pinning),
            ),
            memory=MemoryAllocation(
                memory_mb=vm.memory.memory_mb,
                reservation_mb=vm.memory.reservation_mb,
                limit_mb=vm.memory.limit_mb,
                ballooning=vm.memory.ballooning,
            ),
            disk_allocations={
                disk.name: disk.allocated_gb for disk in vm.disks
            },
        )

        vm.snapshots[snapshot_id] = snapshot
        return snapshot

    def revert_snapshot(self, vm_name: str, snapshot_id: str) -> None:
        vm = self.get_vm(vm_name)
        snapshot = vm.snapshots.get(snapshot_id)

        if snapshot is None or snapshot.state == SnapshotState.DELETED:
            raise KeyError(f"Snapshot {snapshot_id!r} does not exist.")

        if vm.state == VMState.RUNNING:
            raise RuntimeError(
                "Stop the VM before reverting this simulation snapshot."
            )

        vm.cpu = CPUAllocation(
            vcpus=snapshot.cpu.vcpus,
            cpu_limit_percent=snapshot.cpu.cpu_limit_percent,
            cpu_shares=snapshot.cpu.cpu_shares,
            pinning=dict(snapshot.cpu.pinning),
        )
        vm.memory = MemoryAllocation(
            memory_mb=snapshot.memory.memory_mb,
            reservation_mb=snapshot.memory.reservation_mb,
            limit_mb=snapshot.memory.limit_mb,
            ballooning=snapshot.memory.ballooning,
        )

        for disk in vm.disks:
            if disk.name in snapshot.disk_allocations:
                disk.allocated_gb = snapshot.disk_allocations[disk.name]

        vm.state = VMState.STOPPED

    def delete_snapshot(self, vm_name: str, snapshot_id: str) -> None:
        vm = self.get_vm(vm_name)
        snapshot = vm.snapshots.get(snapshot_id)

        if snapshot is None:
            raise KeyError(f"Snapshot {snapshot_id!r} does not exist.")

        snapshot.state = SnapshotState.DELETED

    def allocate_cpu_time(self, duration_seconds: float) -> Dict[str, float]:
        """Distribute host CPU time according to active VMs' shares.

        This is not a real scheduler. It models weighted CPU entitlement.
        CPU limits cap a VM's maximum simulated CPU consumption.
        """

        if duration_seconds < 0:
            raise ValueError("Duration cannot be negative.")

        running = [
            vm for vm in self.vms.values()
            if vm.state == VMState.RUNNING
        ]
        if not running:
            return {}

        total_shares = sum(vm.cpu.cpu_shares for vm in running)
        host_cpu_seconds = self.host_vcpus * duration_seconds
        result: Dict[str, float] = {}

        for vm in running:
            entitlement = host_cpu_seconds * vm.cpu.cpu_shares / total_shares
            limit = (
                vm.cpu.vcpus
                * duration_seconds
                * vm.cpu.cpu_limit_percent
                / 100.0
            )
            result[vm.name] = min(entitlement, limit)

        return result

    def _validate_runtime_memory(self, vm: VirtualMachine) -> None:
        if vm.memory.reservation_mb > self.host_memory_mb:
            raise MemoryError("VM memory reservation exceeds host capacity.")

    def get_vm(self, name: str) -> VirtualMachine:
        try:
            return self.vms[name]
        except KeyError as exc:
            raise KeyError(f"Unknown VM: {name!r}") from exc

    @staticmethod
    def _find_disk(vm: VirtualMachine, disk_name: str) -> VirtualDisk:
        for disk in vm.disks:
            if disk.name == disk_name:
                return disk
        raise KeyError(f"Disk {disk_name!r} does not exist on VM {vm.name}.")

    def inventory(self) -> List[Dict[str, object]]:
        return [
            {
                "name": vm.name,
                "state": vm.state.value,
                "vcpus": vm.cpu.vcpus,
                "memory_mb": vm.memory.memory_mb,
                "disk_capacity_gb": round(vm.total_disk_capacity(), 2),
                "disk_allocated_gb": round(vm.total_disk_allocation(), 2),
                "snapshots": [
                    snapshot_id
                    for snapshot_id, snapshot in vm.snapshots.items()
                    if snapshot.state == SnapshotState.ACTIVE
                ],
            }
            for vm in self.vms.values()
        ]


def print_heading(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def demonstrate_lifecycle(host: Hypervisor) -> None:
    print_heading("VM lifecycle")

    vm = host.get_vm("analytics")
    print("Initial:", vm.state.value)

    host.start_vm(vm.name)
    print("After start:", vm.state.value)

    vm.tick(5)
    print("Uptime ticks:", vm.uptime_ticks)

    host.pause_vm(vm.name)
    print("After pause:", vm.state.value)

    host.resume_vm(vm.name)
    print("After resume:", vm.state.value)

    host.suspend_vm(vm.name)
    print("After suspend:", vm.state.value)

    host.stop_vm(vm.name)
    print("After stop:", vm.state.value)

    try:
        host.resume_vm(vm.name)
    except RuntimeError as exc:
        print("Expected lifecycle error:", exc)


def demonstrate_cpu_allocation(host: Hypervisor) -> None:
    print_heading("CPU allocation")

    host.start_vm("analytics")
    host.start_vm("build-runner")

    allocations = host.allocate_cpu_time(10)
    for name, cpu_seconds in allocations.items():
        print(f"{name}: {cpu_seconds:.2f} simulated CPU-seconds")

    print(
        "The result is weighted by CPU shares and capped by each VM's "
        "configured CPU limit."
    )


def demonstrate_memory(host: Hypervisor) -> None:
    print_heading("Memory allocation")

    vm = host.get_vm("analytics")
    print(
        "Before resize:",
        vm.memory.memory_mb,
        "MB configured,",
        vm.memory.reservation_mb,
        "MB reserved",
    )

    host.stop_vm(vm.name)
    host.resize_memory(
        vm.name,
        memory_mb=6144,
        reservation_mb=4096,
        limit_mb=8192,
    )

    print(
        "After resize:",
        vm.memory.memory_mb,
        "MB configured,",
        vm.memory.reservation_mb,
        "MB reserved,",
        vm.memory.limit_mb,
        "MB hard limit",
    )

    try:
        host.resize_memory(
            vm.name,
            memory_mb=100000,
            reservation_mb=90000,
            limit_mb=100000,
        )
    except (MemoryError, ValueError) as exc:
        print("Expected memory allocation error:", exc)


def demonstrate_disks_and_snapshots(host: Hypervisor) -> None:
    print_heading("Virtual disks and snapshots")

    vm = host.get_vm("analytics")
    disk = host._find_disk(vm, "root")

    print(
        f"Disk {disk.name}: capacity={disk.capacity_gb:.1f} GB, "
        f"allocated={disk.allocated_gb:.1f} GB, "
        f"thin={disk.thin_provisioned}"
    )

    host.resize_disk(vm.name, disk.name, 80)
    print("Expanded root disk to:", disk.capacity_gb, "GB")

    host.start_vm(vm.name)
    host.write_disk(vm.name, disk.name, 4)
    print("After simulated writes:", disk.allocated_gb, "GB allocated")

    snapshot = host.create_snapshot(
        vm.name,
        "before-upgrade",
        "Known-good state before analytics platform upgrade",
    )
    print("Created snapshot:", snapshot.snapshot_id)

    host.stop_vm(vm.name)
    host.write_disk = host.write_disk  # Keeps the public method explicit.
    disk.allocated_gb += 8
    print("Simulated post-snapshot change:", disk.allocated_gb, "GB allocated")

    host.revert_snapshot(vm.name, "before-upgrade")
    print(
        "After revert:",
        disk.allocated_gb,
        "GB allocated, VM state=",
        vm.state.value,
    )

    host.delete_snapshot(vm.name, "before-upgrade")
    print("Snapshot marked deleted.")


def demonstrate_validation(host: Hypervisor) -> None:
    print_heading("Validation and failure handling")

    try:
        invalid_cpu_vm = VirtualMachine(
            name="invalid-cpu",
            cpu=CPUAllocation(vcpus=host.host_vcpus + 1),
            memory=MemoryAllocation(1024, 512, 2048),
            disks=[
                VirtualDisk(
                    name="root",
                    capacity_gb=20,
                    allocated_gb=5,
                )
            ],
        )
        host.create_vm(invalid_cpu_vm)
    except ValueError as exc:
        print("CPU validation:", exc)

    try:
        host.write_disk("analytics", "missing", 1)
    except KeyError as exc:
        print("Disk lookup validation:", exc)

    try:
        host.start_vm("analytics")
    except RuntimeError as exc:
        print("Lifecycle validation:", exc)


def demonstrate_serialization(host: Hypervisor) -> None:
    print_heading("Operational inventory")

    inventory = host.inventory()
    print(json.dumps(inventory, indent=2))

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "vm-inventory.json"
        path.write_text(
            json.dumps(inventory, indent=2),
            encoding="utf-8",
        )
        print("Inventory persisted to:", path)
        print("Persisted bytes:", path.stat().st_size)

        # The temporary directory is removed automatically. A production
        # control plane would use durable storage and atomic replacement.


def build_demo_host() -> Hypervisor:
    host = Hypervisor(
        name="lab-hypervisor-01",
        host_vcpus=8,
        host_memory_mb=16384,
        storage_capacity_gb=500,
    )

    analytics = VirtualMachine(
        name="analytics",
        cpu=CPUAllocation(
            vcpus=4,
            cpu_limit_percent=80,
            cpu_shares=2048,
        ),
        memory=MemoryAllocation(
            memory_mb=4096,
            reservation_mb=2048,
            limit_mb=6144,
            ballooning=True,
        ),
        disks=[
            VirtualDisk(
                name="root",
                capacity_gb=60,
                allocated_gb=20,
                format=DiskFormat.QCOW2,
                thin_provisioned=True,
            ),
            VirtualDisk(
                name="data",
                capacity_gb=100,
                allocated_gb=40,
                format=DiskFormat.QCOW2,
                thin_provisioned=True,
            ),
        ],
    )

    build_runner = VirtualMachine(
        name="build-runner",
        cpu=CPUAllocation(
            vcpus=2,
            cpu_limit_percent=100,
            cpu_shares=1024,
        ),
        memory=MemoryAllocation(
            memory_mb=4096,
            reservation_mb=2048,
            limit_mb=4096,
        ),
        disks=[
            VirtualDisk(
                name="root",
                capacity_gb=50,
                allocated_gb=25,
                format=DiskFormat.RAW,
                thin_provisioned=False,
            )
        ],
    )

    host.create_vm(analytics)
    host.create_vm(build_runner)
    return host


def main() -> None:
    host = build_demo_host()

    demonstrate_lifecycle(host)
    demonstrate_cpu_allocation(host)
    demonstrate_memory(host)
    demonstrate_disks_and_snapshots(host)
    demonstrate_validation(host)
    demonstrate_serialization(host)

    print_heading("Final VM inventory")
    for entry in host.inventory():
        print(entry)


if __name__ == "__main__":
    main()
