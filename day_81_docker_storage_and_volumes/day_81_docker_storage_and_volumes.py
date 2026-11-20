#!/usr/bin/env python3
"""
Docker Storage and Volumes
Demonstrates persistent volumes, bind mounts, temporary storage,
mount validation, lifecycle management, backup metadata, and cleanup.

Python 3.10+
Uses only the Python standard library.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)
logger = logging.getLogger("docker-storage")


class StorageError(Exception):
    """Base exception for storage operations."""


class ValidationError(StorageError):
    """Invalid storage configuration."""


class ResourceNotFoundError(StorageError):
    """Requested storage resource does not exist."""


class MountType(Enum):
    VOLUME = "volume"
    BIND = "bind"
    TMPFS = "tmpfs"


class VolumeState(Enum):
    AVAILABLE = "available"
    IN_USE = "in_use"
    REMOVED = "removed"


@dataclass
class Volume:
    name: str
    driver: str = "local"
    labels: dict[str, str] = field(default_factory=dict)
    state: VolumeState = VolumeState.AVAILABLE
    containers: set[str] = field(default_factory=set)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    data: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", self.name):
            raise ValidationError(f"Invalid volume name: {self.name}")
        if not self.driver:
            raise ValidationError("Volume driver cannot be empty")


@dataclass(frozen=True)
class Mount:
    mount_type: MountType
    source: str
    destination: str
    read_only: bool = False
    propagation: str = "rprivate"

    def validate(self) -> None:
        if not self.destination.startswith("/"):
            raise ValidationError("Container destination must be absolute")

        if ".." in Path(self.destination).parts:
            raise ValidationError("Destination traversal is prohibited")

        if self.mount_type == MountType.VOLUME:
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", self.source):
                raise ValidationError("Invalid volume source")

        elif self.mount_type == MountType.BIND:
            if not Path(self.source).is_absolute():
                raise ValidationError("Bind source must be an absolute host path")

        elif self.mount_type == MountType.TMPFS:
            if self.source not in ("", "tmpfs"):
                raise ValidationError("Invalid tmpfs source")


@dataclass
class Container:
    container_id: str
    mounts: list[Mount] = field(default_factory=list)
    running: bool = False

    def validate_mounts(self) -> None:
        destinations = set()

        for mount in self.mounts:
            mount.validate()

            if mount.destination in destinations:
                raise ValidationError(
                    f"Duplicate mount destination: {mount.destination}"
                )

            destinations.add(mount.destination)


class VolumeManager:
    """Manages named volumes and their container references."""

    def __init__(self) -> None:
        self.volumes: dict[str, Volume] = {}
        self.containers: dict[str, Container] = {}

    def create_volume(
        self,
        name: str,
        driver: str = "local",
        labels: Optional[dict[str, str]] = None
    ) -> Volume:
        if name in self.volumes:
            raise ValidationError(f"Volume already exists: {name}")

        volume = Volume(
            name=name,
            driver=driver,
            labels=labels or {}
        )
        volume.validate()
        self.volumes[name] = volume

        logger.info("Created volume %s", name)
        return volume

    def get_volume(self, name: str) -> Volume:
        volume = self.volumes.get(name)

        if volume is None or volume.state == VolumeState.REMOVED:
            raise ResourceNotFoundError(f"Volume not found: {name}")

        return volume

    def attach(self, container: Container) -> None:
        if container.container_id in self.containers:
            raise ValidationError("Container already registered")

        container.validate_mounts()

        # Validate every reference before changing any state.
        referenced_volumes = set()

        for mount in container.mounts:
            if mount.mount_type == MountType.VOLUME:
                volume = self.get_volume(mount.source)
                referenced_volumes.add(volume.name)

            elif mount.mount_type == MountType.BIND:
                if not Path(mount.source).exists():
                    raise ResourceNotFoundError(
                        f"Bind source does not exist: {mount.source}"
                    )

        for name in referenced_volumes:
            self.volumes[name].containers.add(container.container_id)
            self.volumes[name].state = VolumeState.IN_USE

        self.containers[container.container_id] = container
        logger.info("Attached mounts to %s", container.container_id)

    def detach(self, container_id: str) -> None:
        container = self.containers.pop(container_id, None)

        if container is None:
            raise ResourceNotFoundError(
                f"Container not registered: {container_id}"
            )

        for mount in container.mounts:
            if mount.mount_type == MountType.VOLUME:
                volume = self.get_volume(mount.source)
                volume.containers.discard(container_id)

                if not volume.containers:
                    volume.state = VolumeState.AVAILABLE

        logger.info("Detached %s", container_id)

    def write_data(
        self,
        volume_name: str,
        key: str,
        value: str,
        container_id: Optional[str] = None
    ) -> None:
        volume = self.get_volume(volume_name)

        if container_id is not None:
            if container_id not in volume.containers:
                raise StorageError("Container does not have this volume attached")

            container = self.containers[container_id]

            matching = [
                m for m in container.mounts
                if m.mount_type == MountType.VOLUME
                and m.source == volume_name
            ]

            if not matching or all(m.read_only for m in matching):
                raise StorageError("Volume is mounted read-only")

        volume.data[key] = value

    def read_data(self, volume_name: str, key: str) -> str:
        volume = self.get_volume(volume_name)

        if key not in volume.data:
            raise ResourceNotFoundError(f"Data key not found: {key}")

        return volume.data[key]

    def backup(self, volume_name: str, destination: Path) -> Path:
        volume = self.get_volume(volume_name)

        payload = {
            "name": volume.name,
            "driver": volume.driver,
            "created_at": volume.created_at,
            "data": volume.data
        }

        destination.parent.mkdir(parents=True, exist_ok=True)

        # Exclusive creation prevents accidental backup overwrites.
        with destination.open("x", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)

        logger.info("Backup created: %s", destination)
        return destination

    def restore(self, source: Path, new_name: str) -> Volume:
        if not source.is_file():
            raise ResourceNotFoundError("Backup file does not exist")

        with source.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        if not isinstance(payload, dict):
            raise ValidationError("Invalid backup format")

        if not isinstance(payload.get("data"), dict):
            raise ValidationError("Invalid backup data")

        if not all(
            isinstance(k, str) and isinstance(v, str)
            for k, v in payload["data"].items()
        ):
            raise ValidationError("Backup contains invalid key-value data")

        volume = self.create_volume(
            new_name,
            driver=payload.get("driver", "local")
        )
        volume.data = payload["data"].copy()

        return volume

    def remove_volume(self, name: str, force: bool = False) -> None:
        volume = self.get_volume(name)

        if volume.containers and not force:
            raise StorageError("Cannot remove a volume in use")

        if force and volume.containers:
            raise StorageError(
                "Detach containers before removing a volume"
            )

        volume.state = VolumeState.REMOVED
        del self.volumes[name]

        logger.info("Removed volume %s", name)

    def list_volumes(self) -> list[dict]:
        return [
            {
                "name": volume.name,
                "driver": volume.driver,
                "state": volume.state.value,
                "attached_containers": sorted(volume.containers),
                "labels": volume.labels
            }
            for volume in self.volumes.values()
        ]

    def inspect_volume(self, name: str) -> dict:
        volume = self.get_volume(name)

        result = asdict(volume)
        result["state"] = volume.state.value
        result["containers"] = sorted(volume.containers)
        return result

    def prune(self, label: Optional[str] = None) -> list[str]:
        removable = [
            name for name, volume in self.volumes.items()
            if not volume.containers
            and (
                label is None
                or volume.labels.get("environment") == label
            )
        ]

        for name in removable:
            self.remove_volume(name)

        return removable


def demonstrate_storage() -> None:
    manager = VolumeManager()

    # Named volume: persistent data independent of container lifecycle.
    database = manager.create_volume(
        "postgres_data",
        labels={"environment": "development", "owner": "database"}
    )

    manager.write_data("postgres_data", "database", "inventory")

    # Bind mounts provide access to an existing host directory.
    with tempfile.TemporaryDirectory() as temporary:
        host_directory = Path(temporary).resolve()

        container = Container(
            container_id="database-container",
            mounts=[
                Mount(
                    MountType.VOLUME,
                    "postgres_data",
                    "/var/lib/postgresql/data"
                ),
                Mount(
                    MountType.BIND,
                    str(host_directory),
                    "/app/config",
                    read_only=True
                ),
                Mount(
                    MountType.TMPFS,
                    "tmpfs",
                    "/run/cache"
                )
            ]
        )

        manager.attach(container)

        manager.write_data(
            "postgres_data",
            "last_operation",
            "transaction_committed",
            container_id="database-container"
        )

        print("Volume inspection:")
        print(json.dumps(
            manager.inspect_volume("postgres_data"),
            indent=2
        ))

        # A second container can access the same named volume.
        worker = Container(
            container_id="worker-container",
            mounts=[
                Mount(
                    MountType.VOLUME,
                    "postgres_data",
                    "/data",
                    read_only=True
                )
            ]
        )
        manager.attach(worker)

        try:
            manager.write_data(
                "postgres_data",
                "unauthorized",
                "write",
                container_id="worker-container"
            )
        except StorageError as error:
            print("Expected read-only failure:", error)

        # Backups should be stored outside the volume being backed up.
        backup_path = host_directory / "postgres-backup.json"
        manager.backup("postgres_data", backup_path)

        manager.detach("worker-container")
        manager.detach("database-container")

        restored = manager.restore(
            backup_path,
            "postgres_data_restored"
        )

        assert restored.data["database"] == "inventory"
        assert restored.data["last_operation"] == "transaction_committed"

        print("Restored volume:", restored.name)
        print("Restored records:", restored.data)

    print("\nAvailable volumes:")
    print(json.dumps(manager.list_volumes(), indent=2))

    removed = manager.prune(label="development")
    print("\nPruned volumes:", removed)


def run_tests() -> None:
    manager = VolumeManager()
    manager.create_volume("test_data")

    container = Container(
        "test-container",
        [Mount(MountType.VOLUME, "test_data", "/data")]
    )

    manager.attach(container)
    manager.write_data("test_data", "key", "value", "test-container")

    assert manager.read_data("test_data", "key") == "value"

    try:
        manager.remove_volume("test_data")
        raise AssertionError("Removal should have failed")
    except StorageError:
        pass

    manager.detach("test-container")
    manager.remove_volume("test_data")

    try:
        manager.get_volume("test_data")
        raise AssertionError("Removed volume should not exist")
    except ResourceNotFoundError:
        pass

    print("All tests passed.")


if __name__ == "__main__":
    try:
        demonstrate_storage()
        run_tests()
    except (StorageError, OSError, ValueError, json.JSONDecodeError) as error:
        logger.error("Storage operation failed: %s", error)
        raise SystemExit(1)
