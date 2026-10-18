from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil
from pathlib import Path
import json
import random
import tempfile
import time


class VolumeType(str, Enum):
    GP3 = "gp3"
    IO2 = "io2"


class VolumeState(str, Enum):
    AVAILABLE = "available"
    ATTACHED = "attached"
    DETACHING = "detaching"


class SnapshotState(str, Enum):
    CREATING = "creating"
    COMPLETED = "completed"


@dataclass
class Volume:
    volume_id: str
    size_gib: int
    volume_type: VolumeType
    iops: int
    throughput_mib_s: int
    encrypted: bool = True
    state: VolumeState = VolumeState.AVAILABLE
    attached_instance: str | None = None
    device: str | None = None

    def validate(self) -> None:
        if self.size_gib <= 0:
            raise ValueError("Volume size must be positive")

        if self.volume_type == VolumeType.GP3:
            if not 3000 <= self.iops <= 16000:
                raise ValueError("gp3 IOPS must be between 3,000 and 16,000")
            if not 125 <= self.throughput_mib_s <= 1000:
                raise ValueError("gp3 throughput must be between 125 and 1,000 MiB/s")

        if self.volume_type == VolumeType.IO2:
            if not 100 <= self.iops <= 64000:
                raise ValueError("io2 IOPS must be between 100 and 64,000")
            if self.throughput_mib_s <= 0:
                raise ValueError("Throughput must be positive")

    def estimated_monthly_cost(self) -> float:
        # This is a teaching estimate rather than a provider price quote.
        storage_cost = self.size_gib * (0.08 if self.volume_type == VolumeType.GP3 else 0.125)
        iops_cost = max(0, self.iops - 3000) * (0.000005 if self.volume_type == VolumeType.GP3 else 0.000015)
        throughput_cost = max(0, self.throughput_mib_s - 125) * 0.02
        return storage_cost + iops_cost + throughput_cost


@dataclass
class Snapshot:
    snapshot_id: str
    source_volume_id: str
    size_gib: int
    state: SnapshotState = SnapshotState.CREATING
    progress_percent: int = 0
    parent_snapshot_id: str | None = None

    def advance(self, percent: int) -> None:
        self.progress_percent = min(100, self.progress_percent + percent)
        if self.progress_percent == 100:
            self.state = SnapshotState.COMPLETED


@dataclass
class Attachment:
    volume_id: str
    instance_id: str
    device: str
    attached_at: float = field(default_factory=time.time)


class BlockStorageManager:
    """
    Models a cloud block-storage control plane.

    The manager separates:
    - volume lifecycle and attachment
    - snapshot lifecycle
    - performance configuration
    - capacity and workload simulation
    """

    def __init__(self) -> None:
        self.volumes: dict[str, Volume] = {}
        self.snapshots: dict[str, Snapshot] = {}
        self.attachments: dict[str, Attachment] = {}
        self._volume_counter = 0
        self._snapshot_counter = 0

    def create_volume(
        self,
        size_gib: int,
        volume_type: VolumeType = VolumeType.GP3,
        iops: int = 3000,
        throughput_mib_s: int = 125,
        encrypted: bool = True,
    ) -> Volume:
        self._volume_counter += 1
        volume = Volume(
            volume_id=f"vol-{self._volume_counter:04d}",
            size_gib=size_gib,
            volume_type=volume_type,
            iops=iops,
            throughput_mib_s=throughput_mib_s,
            encrypted=encrypted,
        )
        volume.validate()
        self.volumes[volume.volume_id] = volume
        return volume

    def attach_volume(self, volume_id: str, instance_id: str, device: str) -> Attachment:
        volume = self.volumes[volume_id]

        if volume.state != VolumeState.AVAILABLE:
            raise RuntimeError(f"{volume_id} is not available for attachment")

        if not device.startswith("/dev/"):
            raise ValueError("Linux block devices must use a /dev/ path in this simulation")

        attachment = Attachment(volume_id, instance_id, device)
        volume.state = VolumeState.ATTACHED
        volume.attached_instance = instance_id
        volume.device = device
        self.attachments[volume_id] = attachment
        return attachment

    def detach_volume(self, volume_id: str) -> None:
        volume = self.volumes[volume_id]

        if volume.state != VolumeState.ATTACHED:
            raise RuntimeError(f"{volume_id} is not attached")

        volume.state = VolumeState.DETACHING

        # A real control plane would wait for attachment state transitions.
        # Here the transition completes synchronously.
        del self.attachments[volume_id]
        volume.state = VolumeState.AVAILABLE
        volume.attached_instance = None
        volume.device = None

    def create_snapshot(self, volume_id: str, parent_snapshot_id: str | None = None) -> Snapshot:
        volume = self.volumes[volume_id]

        self._snapshot_counter += 1
        snapshot = Snapshot(
            snapshot_id=f"snap-{self._snapshot_counter:04d}",
            source_volume_id=volume_id,
            size_gib=volume.size_gib,
            parent_snapshot_id=parent_snapshot_id,
        )
        self.snapshots[snapshot.snapshot_id] = snapshot

        # Snapshot creation is modeled as incremental work.
        while snapshot.state != SnapshotState.COMPLETED:
            snapshot.advance(25)

        return snapshot

    def restore_snapshot(
        self,
        snapshot_id: str,
        volume_type: VolumeType = VolumeType.GP3,
    ) -> Volume:
        snapshot = self.snapshots[snapshot_id]

        if snapshot.state != SnapshotState.COMPLETED:
            raise RuntimeError("Cannot restore an incomplete snapshot")

        return self.create_volume(
            size_gib=snapshot.size_gib,
            volume_type=volume_type,
        )

    def modify_performance(
        self,
        volume_id: str,
        iops: int,
        throughput_mib_s: int,
    ) -> None:
        volume = self.volumes[volume_id]
        old_iops = volume.iops
        old_throughput = volume.throughput_mib_s

        volume.iops = iops
        volume.throughput_mib_s = throughput_mib_s

        try:
            volume.validate()
        except ValueError:
            volume.iops = old_iops
            volume.throughput_mib_s = old_throughput
            raise

    def estimate_request_latency_ms(
        self,
        volume_id: str,
        requests_per_second: int,
        average_io_kib: int = 16,
    ) -> float:
        volume = self.volumes[volume_id]

        if requests_per_second < 0 or average_io_kib <= 0:
            raise ValueError("Workload parameters are invalid")

        requested_mib_s = requests_per_second * average_io_kib / 1024
        iops_pressure = requests_per_second / volume.iops
        throughput_pressure = requested_mib_s / volume.throughput_mib_s

        pressure = max(iops_pressure, throughput_pressure)

        # The formula intentionally models queueing pressure rather than
        # pretending to predict an exact cloud-provider latency.
        base_latency = 1.2
        if pressure <= 1:
            return base_latency * (1 + pressure)

        return base_latency * (1 + pressure * pressure * 8)

    def simulate_workload(
        self,
        volume_id: str,
        duration_seconds: int,
        requests_per_second: int,
        average_io_kib: int = 16,
    ) -> dict[str, float]:
        if duration_seconds <= 0:
            raise ValueError("Duration must be positive")

        volume = self.volumes[volume_id]
        requested_mib_s = requests_per_second * average_io_kib / 1024
        effective_mib_s = min(requested_mib_s, volume.throughput_mib_s)

        max_iops = min(
            volume.iops,
            int(volume.throughput_mib_s * 1024 / average_io_kib),
        )
        accepted_iops = min(requests_per_second, max_iops)
        completed_requests = accepted_iops * duration_seconds
        requested_requests = requests_per_second * duration_seconds

        return {
            "requested_requests": requested_requests,
            "completed_requests": completed_requests,
            "dropped_requests": requested_requests - completed_requests,
            "requested_mib_s": requested_mib_s,
            "effective_mib_s": effective_mib_s,
            "estimated_latency_ms": self.estimate_request_latency_ms(
                volume_id,
                requests_per_second,
                average_io_kib,
            ),
        }


def demonstrate_capacity_and_performance(manager: BlockStorageManager) -> None:
    print("\n=== Volume creation and performance configuration ===")

    database_volume = manager.create_volume(
        size_gib=500,
        volume_type=VolumeType.GP3,
        iops=12000,
        throughput_mib_s=500,
    )

    print(database_volume)
    print(f"Estimated monthly cost: ${database_volume.estimated_monthly_cost():.2f}")

    print("\n=== Attachment ===")
    attachment = manager.attach_volume(
        database_volume.volume_id,
        instance_id="db-production-01",
        device="/dev/sdf",
    )
    print(attachment)

    print("\n=== Workload simulation ===")
    result = manager.simulate_workload(
        database_volume.volume_id,
        duration_seconds=60,
        requests_per_second=18000,
        average_io_kib=16,
    )

    for key, value in result.items():
        print(f"{key}: {value}")

    print("\n=== Online performance modification ===")
    manager.modify_performance(
        database_volume.volume_id,
        iops=16000,
        throughput_mib_s=750,
    )
    print(manager.volumes[database_volume.volume_id])

    print("\n=== Snapshot and restore ===")
    snapshot = manager.create_snapshot(database_volume.volume_id)
    print(snapshot)

    restored = manager.restore_snapshot(snapshot.snapshot_id)
    print(restored)

    print("\n=== Detachment ===")
    manager.detach_volume(database_volume.volume_id)
    print(manager.volumes[database_volume.volume_id])


def demonstrate_snapshot_chain(manager: BlockStorageManager) -> None:
    print("\n=== Snapshot lineage ===")

    source = manager.create_volume(
        size_gib=200,
        volume_type=VolumeType.GP3,
        iops=6000,
        throughput_mib_s=250,
    )

    first = manager.create_snapshot(source.volume_id)
    second = manager.create_snapshot(source.volume_id, parent_snapshot_id=first.snapshot_id)

    print(f"{first.snapshot_id}: parent={first.parent_snapshot_id}, state={first.state.value}")
    print(f"{second.snapshot_id}: parent={second.parent_snapshot_id}, state={second.state.value}")

    # Snapshot lineage is useful for backup auditing even when the provider
    # internally optimizes how unchanged blocks are stored.
    lineage = []
    current = second
    while current:
        lineage.append(current.snapshot_id)
        parent_id = current.parent_snapshot_id
        current = manager.snapshots.get(parent_id) if parent_id else None

    print("Lineage:", " -> ".join(lineage))


def demonstrate_validation(manager: BlockStorageManager) -> None:
    print("\n=== Validation and failure conditions ===")

    try:
        manager.create_volume(
            size_gib=100,
            volume_type=VolumeType.GP3,
            iops=500,
            throughput_mib_s=125,
        )
    except ValueError as exc:
        print(f"Rejected invalid IOPS configuration: {exc}")

    try:
        manager.create_volume(
            size_gib=100,
            volume_type=VolumeType.GP3,
            iops=3000,
            throughput_mib_s=2000,
        )
    except ValueError as exc:
        print(f"Rejected invalid throughput configuration: {exc}")

    volume = manager.create_volume(50)
    manager.attach_volume(volume.volume_id, "application-01", "/dev/sdg")

    try:
        manager.attach_volume(volume.volume_id, "application-02", "/dev/sdh")
    except RuntimeError as exc:
        print(f"Rejected second attachment: {exc}")


def demonstrate_storage_inspection(manager: BlockStorageManager) -> None:
    print("\n=== Storage inventory ===")

    inventory = [
        {
            "volume_id": volume.volume_id,
            "size_gib": volume.size_gib,
            "type": volume.volume_type.value,
            "iops": volume.iops,
            "throughput_mib_s": volume.throughput_mib_s,
            "state": volume.state.value,
            "encrypted": volume.encrypted,
            "attached_instance": volume.attached_instance,
        }
        for volume in manager.volumes.values()
    ]

    print(json.dumps(inventory, indent=2))

    # Writing an inventory snapshot to a temporary file demonstrates how an
    # operations system could export storage state for auditing.
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "storage_inventory.json"
        path.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
        print(f"Audit inventory written to: {path}")


def demonstrate_iops_vs_throughput(manager: BlockStorageManager) -> None:
    print("\n=== IOPS versus throughput ===")

    small_io = manager.create_volume(
        size_gib=100,
        volume_type=VolumeType.GP3,
        iops=10000,
        throughput_mib_s=125,
    )

    large_io = manager.create_volume(
        size_gib=100,
        volume_type=VolumeType.GP3,
        iops=3000,
        throughput_mib_s=500,
    )

    workload = [
        ("small random I/O", 9000, 4),
        ("large sequential I/O", 1000, 512),
    ]

    for name, iops, io_kib in workload:
        print(f"\n{name}: {iops} IOPS, {io_kib} KiB per operation")

        for volume in (small_io, large_io):
            requested_mib_s = iops * io_kib / 1024
            iops_pressure = iops / volume.iops
            throughput_pressure = requested_mib_s / volume.throughput_mib_s
            bottleneck = "IOPS" if iops_pressure >= throughput_pressure else "throughput"

            print(
                f"{volume.volume_id}: requested={requested_mib_s:.2f} MiB/s, "
                f"bottleneck={bottleneck}"
            )


def demonstrate_cost_and_capacity(manager: BlockStorageManager) -> None:
    print("\n=== Capacity and cost planning ===")

    volumes = [
        manager.create_volume(1024, VolumeType.GP3, 6000, 250),
        manager.create_volume(2048, VolumeType.IO2, 16000, 500),
        manager.create_volume(512, VolumeType.GP3, 12000, 500),
    ]

    total_capacity = sum(v.size_gib for v in volumes)
    total_estimated_cost = sum(v.estimated_monthly_cost() for v in volumes)

    print(f"Managed capacity: {total_capacity} GiB")
    print(f"Estimated monthly cost: ${total_estimated_cost:.2f}")

    # A useful operational distinction is that capacity, IOPS, and throughput
    # are separate dimensions. Increasing capacity does not automatically
    # produce proportional performance.
    for volume in volumes:
        print(
            f"{volume.volume_id}: "
            f"{volume.size_gib} GiB, "
            f"{volume.iops:,} IOPS, "
            f"{volume.throughput_mib_s} MiB/s"
        )


def main() -> None:
    random.seed(42)

    manager = BlockStorageManager()

    demonstrate_capacity_and_performance(manager)
    demonstrate_snapshot_chain(manager)
    demonstrate_validation(manager)
    demonstrate_storage_inspection(manager)
    demonstrate_iops_vs_throughput(manager)
    demonstrate_cost_and_capacity(manager)


if __name__ == "__main__":
    main()
