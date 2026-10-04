"""
Storage Virtualization Laboratory
=================================

A self-contained simulation of storage virtualization covering:

- Physical storage devices
- Storage pools
- Logical volumes
- Virtual disks
- Abstraction layers
- Extent allocation
- Thin provisioning
- Snapshots
- Copy-on-write behavior
- Capacity accounting
- Allocation policies
- I/O translation
- Failure handling
- Integrity validation
- Performance and utilization analysis

The program intentionally models the mechanisms instead of depending on a
specific operating-system storage stack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import hashlib
import math
import random
import tempfile
from pathlib import Path


class StorageError(Exception):
    """Base exception for storage virtualization failures."""


class CapacityError(StorageError):
    """Raised when an allocation cannot be satisfied."""


class InvalidOperationError(StorageError):
    """Raised when an operation violates storage state rules."""


class DeviceState(Enum):
    ONLINE = "online"
    DEGRADED = "degraded"
    FAILED = "failed"


class AllocationPolicy(Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_USED = "least_used"


@dataclass
class PhysicalDevice:
    device_id: str
    capacity_gb: int
    state: DeviceState = DeviceState.ONLINE
    used_gb: int = 0
    read_iops: int = 50000
    write_iops: int = 30000

    @property
    def free_gb(self) -> int:
        return self.capacity_gb - self.used_gb

    def allocate(self, size_gb: int) -> None:
        if self.state == DeviceState.FAILED:
            raise InvalidOperationError(
                f"{self.device_id} is failed and cannot allocate storage."
            )
        if size_gb <= 0:
            raise ValueError("Allocation size must be positive.")
        if size_gb > self.free_gb:
            raise CapacityError(
                f"{self.device_id} has only {self.free_gb} GB free."
            )
        self.used_gb += size_gb

    def release(self, size_gb: int) -> None:
        if size_gb < 0 or size_gb > self.used_gb:
            raise InvalidOperationError("Invalid device release.")
        self.used_gb -= size_gb

    def fail(self) -> None:
        self.state = DeviceState.FAILED

    def recover(self) -> None:
        self.state = DeviceState.ONLINE


@dataclass
class Extent:
    extent_id: int
    device_id: str
    start_gb: int
    size_gb: int
    logical_volume: Optional[str] = None


@dataclass
class LogicalVolume:
    name: str
    requested_size_gb: int
    thin: bool
    block_size_kb: int = 64
    allocated_extents: List[int] = field(default_factory=list)
    logical_blocks: Dict[int, str] = field(default_factory=dict)

    @property
    def allocated_size_gb(self) -> int:
        return len(self.allocated_extents)


@dataclass
class Snapshot:
    name: str
    source_volume: str
    source_generation: int
    block_hashes: Dict[int, str]


class StoragePool:
    """
    Abstracts multiple physical devices behind one logical capacity domain.

    The pool owns extent placement. Consumers do not need to know which
    physical device contains their logical storage.
    """

    def __init__(
        self,
        name: str,
        extent_size_gb: int = 1,
        policy: AllocationPolicy = AllocationPolicy.LEAST_USED,
    ):
        if extent_size_gb <= 0:
            raise ValueError("Extent size must be positive.")

        self.name = name
        self.extent_size_gb = extent_size_gb
        self.policy = policy
        self.devices: Dict[str, PhysicalDevice] = {}
        self.extents: Dict[int, Extent] = {}
        self.volumes: Dict[str, LogicalVolume] = {}
        self.snapshots: Dict[str, Snapshot] = {}
        self._next_extent_id = 1
        self._generation = 0

    def add_device(self, device: PhysicalDevice) -> None:
        if device.device_id in self.devices:
            raise InvalidOperationError(
                f"Device {device.device_id} already exists."
            )
        self.devices[device.device_id] = device

    @property
    def physical_capacity_gb(self) -> int:
        return sum(d.capacity_gb for d in self.devices.values())

    @property
    def physical_used_gb(self) -> int:
        return sum(d.used_gb for d in self.devices.values())

    @property
    def physical_free_gb(self) -> int:
        return self.physical_capacity_gb - self.physical_used_gb

    def _candidate_devices(self) -> List[PhysicalDevice]:
        candidates = [
            d for d in self.devices.values()
            if d.state != DeviceState.FAILED and d.free_gb >= self.extent_size_gb
        ]

        if self.policy == AllocationPolicy.LEAST_USED:
            candidates.sort(
                key=lambda d: (
                    d.used_gb / d.capacity_gb,
                    d.device_id,
                )
            )
        else:
            candidates.sort(key=lambda d: d.device_id)

        return candidates

    def allocate_extent(self, volume_name: str) -> int:
        candidates = self._candidate_devices()
        if not candidates:
            raise CapacityError("The storage pool has no allocatable extent.")

        device = candidates[0]
        device.allocate(self.extent_size_gb)

        extent_id = self._next_extent_id
        self._next_extent_id += 1

        extent = Extent(
            extent_id=extent_id,
            device_id=device.device_id,
            start_gb=device.used_gb - self.extent_size_gb,
            size_gb=self.extent_size_gb,
            logical_volume=volume_name,
        )
        self.extents[extent_id] = extent
        return extent_id

    def create_volume(
        self,
        name: str,
        size_gb: int,
        thin: bool = False,
    ) -> LogicalVolume:
        if name in self.volumes:
            raise InvalidOperationError(f"Volume {name} already exists.")
        if size_gb <= 0:
            raise ValueError("Volume size must be positive.")

        if not thin and size_gb > self.physical_free_gb:
            raise CapacityError(
                f"Cannot create thick volume of {size_gb} GB; "
                f"pool has {self.physical_free_gb} GB free."
            )

        volume = LogicalVolume(
            name=name,
            requested_size_gb=size_gb,
            thin=thin,
        )
        self.volumes[name] = volume

        if not thin:
            extent_count = math.ceil(size_gb / self.extent_size_gb)
            for _ in range(extent_count):
                volume.allocated_extents.append(
                    self.allocate_extent(name)
                )

        return volume

    def _validate_block(self, volume: LogicalVolume, block: int) -> None:
        blocks_per_gb = 1024 // (volume.block_size_kb or 1)
        maximum_blocks = volume.requested_size_gb * blocks_per_gb
        if block < 0 or block >= maximum_blocks:
            raise InvalidOperationError(
                f"Block {block} is outside logical volume {volume.name}."
            )

    def _ensure_thin_block_capacity(
        self,
        volume: LogicalVolume,
        block: int,
    ) -> None:
        if block in volume.logical_blocks:
            return

        blocks_per_extent = max(
            1,
            (self.extent_size_gb * 1024) // volume.block_size_kb,
        )
        required_extent_index = block // blocks_per_extent

        while len(volume.allocated_extents) <= required_extent_index:
            if len(volume.allocated_extents) >= volume.requested_size_gb:
                raise CapacityError(
                    f"Thin volume {volume.name} reached its virtual capacity."
                )
            volume.allocated_extents.append(
                self.allocate_extent(volume.name)
            )

    def write_block(self, volume_name: str, block: int, data: str) -> None:
        volume = self.volumes[volume_name]
        self._validate_block(volume, block)

        if volume.thin:
            self._ensure_thin_block_capacity(volume, block)
        elif not volume.allocated_extents:
            raise CapacityError(f"Volume {volume_name} has no physical storage.")

        if not isinstance(data, str):
            raise TypeError("This demonstration stores block content as strings.")

        volume.logical_blocks[block] = data
        self._generation += 1

    def read_block(self, volume_name: str, block: int) -> str:
        volume = self.volumes[volume_name]
        self._validate_block(volume, block)

        # A sparse thin-provisioned block reads as zero/unwritten content
        # until a physical extent is consumed for it.
        return volume.logical_blocks.get(block, "")

    def create_snapshot(self, snapshot_name: str, volume_name: str) -> Snapshot:
        if snapshot_name in self.snapshots:
            raise InvalidOperationError(
                f"Snapshot {snapshot_name} already exists."
            )

        volume = self.volumes[volume_name]
        snapshot = Snapshot(
            name=snapshot_name,
            source_volume=volume_name,
            source_generation=self._generation,
            block_hashes={
                block: hashlib.sha256(data.encode()).hexdigest()
                for block, data in volume.logical_blocks.items()
            },
        )
        self.snapshots[snapshot_name] = snapshot
        return snapshot

    def verify_snapshot(self, snapshot_name: str) -> Dict[int, bool]:
        snapshot = self.snapshots[snapshot_name]
        volume = self.volumes[snapshot.source_volume]

        result = {}
        for block, expected_hash in snapshot.block_hashes.items():
            current = volume.logical_blocks.get(block, "")
            result[block] = (
                hashlib.sha256(current.encode()).hexdigest()
                == expected_hash
            )
        return result

    def fail_device(self, device_id: str) -> None:
        self.devices[device_id].fail()

    def volume_health(self, volume_name: str) -> str:
        volume = self.volumes[volume_name]
        devices = {
            self.extents[eid].device_id
            for eid in volume.allocated_extents
        }

        states = {self.devices[d].state for d in devices}

        if DeviceState.FAILED in states:
            return "degraded"
        if DeviceState.DEGRADED in states:
            return "warning"
        return "healthy"

    def status(self) -> Dict[str, object]:
        return {
            "pool": self.name,
            "physical_capacity_gb": self.physical_capacity_gb,
            "physical_used_gb": self.physical_used_gb,
            "physical_free_gb": self.physical_free_gb,
            "virtual_capacity_gb": sum(
                volume.requested_size_gb
                for volume in self.volumes.values()
            ),
            "volumes": {
                name: {
                    "virtual_size_gb": volume.requested_size_gb,
                    "physical_allocated_gb": volume.allocated_size_gb,
                    "thin": volume.thin,
                    "health": self.volume_health(name),
                }
                for name, volume in self.volumes.items()
            },
        }


class VirtualDisk:
    """
    Represents the consumer-facing abstraction.

    The operating system interacts with a virtual disk while the storage
    virtualization layer translates those logical operations into pool
    allocations and physical placement.
    """

    def __init__(self, disk_id: str, volume: LogicalVolume, pool: StoragePool):
        self.disk_id = disk_id
        self.volume = volume
        self.pool = pool

    def write(self, logical_block: int, data: str) -> None:
        self.pool.write_block(self.volume.name, logical_block, data)

    def read(self, logical_block: int) -> str:
        return self.pool.read_block(self.volume.name, logical_block)


class VirtualizationStack:
    """
    Models the abstraction boundary:

        application
             |
        filesystem
             |
        virtual disk
             |
        logical volume
             |
        storage pool
             |
        physical devices
    """

    def __init__(self, pool: StoragePool):
        self.pool = pool
        self.virtual_disks: Dict[str, VirtualDisk] = {}

    def expose_disk(self, disk_id: str, volume_name: str) -> VirtualDisk:
        if disk_id in self.virtual_disks:
            raise InvalidOperationError(f"Disk {disk_id} already exists.")

        disk = VirtualDisk(
            disk_id=disk_id,
            volume=self.pool.volumes[volume_name],
            pool=self.pool,
        )
        self.virtual_disks[disk_id] = disk
        return disk


def demonstrate_basic_abstraction() -> None:
    print("\n=== Storage abstraction ===")

    pool = StoragePool("production-pool", extent_size_gb=1)
    pool.add_device(PhysicalDevice("nvme-a", 8))
    pool.add_device(PhysicalDevice("nvme-b", 8))
    pool.add_device(PhysicalDevice("ssd-c", 16))

    volume = pool.create_volume("database-data", 6, thin=False)
    stack = VirtualizationStack(pool)
    disk = stack.expose_disk("vdisk-db01", volume.name)

    disk.write(0, "transaction-page-0000")
    disk.write(1, "transaction-page-0001")

    print("Virtual disk read:", disk.read(0))
    print("Pool status:", pool.status())


def demonstrate_thin_provisioning() -> None:
    print("\n=== Thin provisioning ===")

    pool = StoragePool("thin-pool", extent_size_gb=1)
    pool.add_device(PhysicalDevice("ssd-01", 10))
    pool.add_device(PhysicalDevice("ssd-02", 10))

    volume = pool.create_volume("analytics", 12, thin=True)

    print(
        "Virtual capacity:",
        volume.requested_size_gb,
        "GB; physical allocation:",
        volume.allocated_size_gb,
        "GB",
    )

    pool.write_block("analytics", 0, "partition-2026")
    pool.write_block("analytics", 16384, "partition-2027")

    print(
        "After sparse writes:",
        volume.allocated_size_gb,
        "physical extents allocated",
    )


def demonstrate_snapshot_behavior() -> None:
    print("\n=== Snapshot and copy-on-write semantics ===")

    pool = StoragePool("snapshot-pool", extent_size_gb=1)
    pool.add_device(PhysicalDevice("array-a", 12))
    pool.add_device(PhysicalDevice("array-b", 12))

    volume = pool.create_volume("orders", 5)
    pool.write_block("orders", 10, "order-state: OPEN")
    pool.write_block("orders", 11, "order-state: PAID")

    snapshot = pool.create_snapshot("orders-before-migration", "orders")
    print("Snapshot generation:", snapshot.source_generation)

    pool.write_block("orders", 10, "order-state: SHIPPED")

    verification = pool.verify_snapshot("orders-before-migration")
    print("Snapshot block verification:", verification)
    print("Current block:", pool.read_block("orders", 10))


def demonstrate_failure() -> None:
    print("\n=== Physical device failure ===")

    pool = StoragePool("failure-pool", extent_size_gb=1)
    pool.add_device(PhysicalDevice("disk-a", 4))
    pool.add_device(PhysicalDevice("disk-b", 4))

    pool.create_volume("critical-db", 6)

    print("Before failure:", pool.volume_health("critical-db"))

    allocated_devices = {
        extent.device_id
        for extent in pool.extents.values()
        if extent.logical_volume == "critical-db"
    }

    failed_device = sorted(allocated_devices)[0]
    pool.fail_device(failed_device)

    print("Failed device:", failed_device)
    print("After failure:", pool.volume_health("critical-db"))

    try:
        pool.allocate_extent("critical-db")
        print("New extent allocated despite failed device.")
    except StorageError as exc:
        print("Allocation result:", exc)


def demonstrate_validation_and_capacity() -> None:
    print("\n=== Validation and capacity enforcement ===")

    pool = StoragePool("validation-pool")
    pool.add_device(PhysicalDevice("disk-1", 3))

    try:
        pool.create_volume("too-large", 4)
    except CapacityError as exc:
        print("Expected capacity error:", exc)

    pool.create_volume("valid", 2)

    try:
        pool.write_block("valid", -1, "invalid")
    except InvalidOperationError as exc:
        print("Expected block validation error:", exc)

    try:
        pool.create_volume("invalid-size", 0)
    except ValueError as exc:
        print("Expected size validation error:", exc)


def demonstrate_persistence() -> None:
    print("\n=== Exporting storage inventory ===")

    pool = StoragePool("inventory-pool")
    pool.add_device(PhysicalDevice("nvme-1", 20))
    pool.add_device(PhysicalDevice("nvme-2", 20))
    pool.create_volume("vm-root", 8)
    pool.create_volume("vm-data", 10, thin=True)

    inventory = pool.status()

    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "storage_inventory.txt"
        path.write_text(
            "\n".join(
                [
                    f"Pool: {inventory['pool']}",
                    f"Physical capacity: {inventory['physical_capacity_gb']} GB",
                    f"Physical used: {inventory['physical_used_gb']} GB",
                    f"Physical free: {inventory['physical_free_gb']} GB",
                    f"Virtual capacity: {inventory['virtual_capacity_gb']} GB",
                ]
            ),
            encoding="utf-8",
        )

        print(path.read_text(encoding="utf-8"))


def demonstrate_allocation_analysis() -> None:
    print("\n=== Allocation analysis ===")

    random.seed(42)

    pool = StoragePool(
        "performance-pool",
        extent_size_gb=1,
        policy=AllocationPolicy.LEAST_USED,
    )

    for index, capacity in enumerate((12, 16, 24), start=1):
        pool.add_device(
            PhysicalDevice(
                device_id=f"device-{index}",
                capacity_gb=capacity,
                read_iops=random.randint(40000, 70000),
                write_iops=random.randint(20000, 50000),
            )
        )

    pool.create_volume("transaction-log", 9)
    pool.create_volume("warehouse", 15)

    for device in pool.devices.values():
        utilization = device.used_gb / device.capacity_gb
        print(
            f"{device.device_id}: "
            f"{device.used_gb}/{device.capacity_gb} GB "
            f"({utilization:.1%}), "
            f"read IOPS={device.read_iops}, "
            f"write IOPS={device.write_iops}"
        )

    print(
        "Virtual-to-physical capacity ratio:",
        sum(v.requested_size_gb for v in pool.volumes.values())
        / pool.physical_capacity_gb,
    )


def main() -> None:
    demonstrate_basic_abstraction()
    demonstrate_thin_provisioning()
    demonstrate_snapshot_behavior()
    demonstrate_failure()
    demonstrate_validation_and_capacity()
    demonstrate_persistence()
    demonstrate_allocation_analysis()


if __name__ == "__main__":
    main()
