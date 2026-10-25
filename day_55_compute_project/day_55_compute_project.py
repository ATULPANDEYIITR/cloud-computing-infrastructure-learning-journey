#!/usr/bin/env python3
"""
Compute and Storage Project
Scalable application simulation covering:
- compute instances
- object storage
- load balancing
- horizontal scaling
- health checks
- backups and restore
- capacity evaluation
- request routing
- failure handling
- security and validation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import hashlib
import json
import math
import tempfile


class InstanceState(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    UNHEALTHY = "unhealthy"


class BackupState(str, Enum):
    AVAILABLE = "available"
    RESTORING = "restoring"
    FAILED = "failed"


class ScalingError(Exception):
    """Raised when a scaling operation violates capacity constraints."""


class StorageError(Exception):
    """Raised when an object-storage operation is invalid."""


@dataclass
class ApplicationConfig:
    min_instances: int = 2
    max_instances: int = 6
    requests_per_instance: int = 100
    scale_up_threshold: float = 0.70
    scale_down_threshold: float = 0.25
    max_object_size: int = 10 * 1024 * 1024
    backup_retention_days: int = 7


@dataclass
class ComputeInstance:
    instance_id: str
    capacity: int
    state: InstanceState = InstanceState.RUNNING
    active_requests: int = 0

    @property
    def utilization(self) -> float:
        if self.capacity <= 0:
            return 1.0
        return self.active_requests / self.capacity

    def can_accept(self) -> bool:
        return self.state == InstanceState.RUNNING and (
            self.active_requests < self.capacity
        )


@dataclass
class StoredObject:
    key: str
    content: bytes
    checksum: str
    created_at: datetime

    @property
    def size(self) -> int:
        return len(self.content)


@dataclass
class Backup:
    backup_id: str
    created_at: datetime
    objects: Dict[str, StoredObject]
    state: BackupState = BackupState.AVAILABLE


class ObjectStorage:
    """Small object-storage model with checksum validation."""

    def __init__(self, max_object_size: int):
        self.max_object_size = max_object_size
        self.objects: Dict[str, StoredObject] = {}

    def put(self, key: str, content: bytes) -> StoredObject:
        if not key or key.startswith("/"):
            raise StorageError("Object key must be non-empty and relative.")

        if len(content) > self.max_object_size:
            raise StorageError(
                f"Object '{key}' exceeds the configured size limit."
            )

        checksum = hashlib.sha256(content).hexdigest()
        obj = StoredObject(
            key=key,
            content=content,
            checksum=checksum,
            created_at=datetime.now(),
        )
        self.objects[key] = obj
        return obj

    def get(self, key: str) -> bytes:
        obj = self.objects.get(key)
        if obj is None:
            raise StorageError(f"Object '{key}' does not exist.")

        if hashlib.sha256(obj.content).hexdigest() != obj.checksum:
            raise StorageError(f"Integrity check failed for '{key}'.")

        return obj.content

    def delete(self, key: str) -> None:
        if key not in self.objects:
            raise StorageError(f"Cannot delete missing object '{key}'.")
        del self.objects[key]

    def snapshot(self) -> Dict[str, StoredObject]:
        return {
            key: StoredObject(
                key=value.key,
                content=value.content,
                checksum=value.checksum,
                created_at=value.created_at,
            )
            for key, value in self.objects.items()
        }


class LoadBalancer:
    """Routes requests only to healthy instances using least-loaded selection."""

    def __init__(self, instances: List[ComputeInstance]):
        self.instances = instances

    def route(self) -> ComputeInstance:
        candidates = [i for i in self.instances if i.can_accept()]
        if not candidates:
            raise ScalingError("No healthy compute instance can accept traffic.")

        return min(candidates, key=lambda instance: instance.utilization)

    def process_requests(self, request_count: int) -> Dict[str, int]:
        if request_count < 0:
            raise ValueError("Request count cannot be negative.")

        distribution: Dict[str, int] = {}

        for _ in range(request_count):
            instance = self.route()
            instance.active_requests += 1
            distribution[instance.instance_id] = (
                distribution.get(instance.instance_id, 0) + 1
            )

        return distribution

    def complete_requests(self, request_count: int) -> None:
        remaining = request_count

        for instance in sorted(
            self.instances,
            key=lambda item: item.active_requests,
            reverse=True,
        ):
            completed = min(instance.active_requests, remaining)
            instance.active_requests -= completed
            remaining -= completed

            if remaining == 0:
                break

        if remaining:
            raise ValueError("Cannot complete more requests than are active.")


class AutoScaler:
    """Horizontal scaling policy based on aggregate utilization."""

    def __init__(
        self,
        config: ApplicationConfig,
        instances: List[ComputeInstance],
        load_balancer: LoadBalancer,
    ):
        self.config = config
        self.instances = instances
        self.load_balancer = load_balancer

    def average_utilization(self) -> float:
        active = [
            instance
            for instance in self.instances
            if instance.state == InstanceState.RUNNING
        ]

        if not active:
            return 1.0

        return sum(i.utilization for i in active) / len(active)

    def evaluate(self) -> str:
        utilization = self.average_utilization()
        count = len(self.instances)

        if (
            utilization >= self.config.scale_up_threshold
            and count < self.config.max_instances
        ):
            self._add_instance()
            return "scaled_up"

        if (
            utilization <= self.config.scale_down_threshold
            and count > self.config.min_instances
        ):
            removable = self._find_removable_instance()
            if removable:
                self.instances.remove(removable)
                self.load_balancer.instances = self.instances
                return "scaled_down"

        return "unchanged"

    def _add_instance(self) -> None:
        if len(self.instances) >= self.config.max_instances:
            raise ScalingError("Maximum instance count reached.")

        instance_id = f"app-{len(self.instances) + 1:02d}"
        self.instances.append(
            ComputeInstance(
                instance_id=instance_id,
                capacity=self.config.requests_per_instance,
            )
        )
        self.load_balancer.instances = self.instances

    def _find_removable_instance(self) -> Optional[ComputeInstance]:
        candidates = [
            i
            for i in self.instances
            if i.state == InstanceState.RUNNING and i.active_requests == 0
        ]

        if not candidates:
            return None

        return candidates[-1]


class BackupManager:
    """Creates, lists, expires, and restores storage snapshots."""

    def __init__(self, storage: ObjectStorage, retention_days: int):
        self.storage = storage
        self.retention_days = retention_days
        self.backups: List[Backup] = []
        self.sequence = 0

    def create_backup(self) -> Backup:
        self.sequence += 1
        backup = Backup(
            backup_id=f"backup-{self.sequence:04d}",
            created_at=datetime.now(),
            objects=self.storage.snapshot(),
        )
        self.backups.append(backup)
        return backup

    def expire_old_backups(self, now: Optional[datetime] = None) -> None:
        current = now or datetime.now()
        cutoff = current - timedelta(days=self.retention_days)
        self.backups = [
            backup for backup in self.backups if backup.created_at >= cutoff
        ]

    def restore(self, backup_id: str) -> None:
        backup = next(
            (item for item in self.backups if item.backup_id == backup_id),
            None,
        )

        if backup is None:
            raise StorageError(f"Backup '{backup_id}' was not found.")

        backup.state = BackupState.RESTORING

        self.storage.objects = {
            key: StoredObject(
                key=obj.key,
                content=obj.content,
                checksum=obj.checksum,
                created_at=obj.created_at,
            )
            for key, obj in backup.objects.items()
        }

        backup.state = BackupState.AVAILABLE


class ApplicationPlatform:
    """Coordinates compute, load balancing, storage, scaling, and backups."""

    def __init__(self, config: ApplicationConfig):
        if config.min_instances < 1:
            raise ValueError("At least one compute instance is required.")

        if config.min_instances > config.max_instances:
            raise ValueError("Minimum instances cannot exceed maximum instances.")

        self.config = config
        self.instances = [
            ComputeInstance(
                instance_id=f"app-{index:02d}",
                capacity=config.requests_per_instance,
            )
            for index in range(1, config.min_instances + 1)
        ]
        self.storage = ObjectStorage(config.max_object_size)
        self.load_balancer = LoadBalancer(self.instances)
        self.scaler = AutoScaler(
            config,
            self.instances,
            self.load_balancer,
        )
        self.backups = BackupManager(
            self.storage,
            config.backup_retention_days,
        )

    def upload_application_data(self, key: str, content: str) -> StoredObject:
        return self.storage.put(key, content.encode("utf-8"))

    def simulate_traffic(self, requests: int) -> Dict[str, int]:
        return self.load_balancer.process_requests(requests)

    def finish_traffic(self, requests: int) -> None:
        self.load_balancer.complete_requests(requests)

    def health_check(self) -> Dict[str, str]:
        return {
            instance.instance_id: instance.state.value
            for instance in self.instances
        }

    def mark_unhealthy(self, instance_id: str) -> None:
        instance = self._find_instance(instance_id)
        if instance.active_requests:
            raise ScalingError(
                "An instance with active requests cannot be immediately failed."
            )
        instance.state = InstanceState.UNHEALTHY

    def replace_unhealthy_instances(self) -> int:
        replacements = 0

        for instance in list(self.instances):
            if instance.state == InstanceState.UNHEALTHY:
                self.instances.remove(instance)
                replacements += 1

        while len(self.instances) < self.config.min_instances:
            next_number = len(self.instances) + 1
            self.instances.append(
                ComputeInstance(
                    instance_id=f"replacement-{next_number:02d}",
                    capacity=self.config.requests_per_instance,
                )
            )

        self.load_balancer.instances = self.instances
        return replacements

    def _find_instance(self, instance_id: str) -> ComputeInstance:
        for instance in self.instances:
            if instance.instance_id == instance_id:
                return instance
        raise ScalingError(f"Instance '{instance_id}' was not found.")

    def capacity_report(self) -> Dict[str, object]:
        running = [
            instance
            for instance in self.instances
            if instance.state == InstanceState.RUNNING
        ]

        total_capacity = sum(instance.capacity for instance in running)
        active = sum(instance.active_requests for instance in running)

        return {
            "instance_count": len(self.instances),
            "running_instances": len(running),
            "total_capacity": total_capacity,
            "active_requests": active,
            "aggregate_utilization": (
                round(active / total_capacity, 3)
                if total_capacity
                else 1.0
            ),
            "stored_objects": len(self.storage.objects),
            "stored_bytes": sum(
                obj.size for obj in self.storage.objects.values()
            ),
            "backup_count": len(self.backups.backups),
        }


def run_validation_tests() -> None:
    config = ApplicationConfig(
        min_instances=2,
        max_instances=4,
        requests_per_instance=10,
    )
    platform = ApplicationPlatform(config)

    assert len(platform.instances) == 2

    obj = platform.upload_application_data(
        "documents/config.json",
        '{"version": 1, "environment": "production"}',
    )
    assert obj.checksum == hashlib.sha256(obj.content).hexdigest()

    assert platform.storage.get("documents/config.json").startswith(b"{")

    distribution = platform.simulate_traffic(15)
    assert sum(distribution.values()) == 15

    platform.finish_traffic(15)

    backup = platform.backups.create_backup()
    assert backup.backup_id == "backup-0001"

    platform.storage.delete("documents/config.json")
    assert "documents/config.json" not in platform.storage.objects

    platform.backups.restore(backup.backup_id)
    assert "documents/config.json" in platform.storage.objects

    platform.mark_unhealthy(platform.instances[0].instance_id)
    replaced = platform.replace_unhealthy_instances()
    assert replaced == 1
    assert len(platform.instances) == config.min_instances


def main() -> None:
    run_validation_tests()

    config = ApplicationConfig(
        min_instances=2,
        max_instances=6,
        requests_per_instance=100,
        scale_up_threshold=0.70,
        scale_down_threshold=0.25,
    )

    platform = ApplicationPlatform(config)

    platform.upload_application_data(
        "application/releases/v1/config.json",
        '{"version":"1.0.0","region":"primary"}',
    )
    platform.upload_application_data(
        "application/releases/v1/index.html",
        "<html><body>Scalable application</body></html>",
    )

    traffic = platform.simulate_traffic(180)
    print("Traffic distribution:")
    print(json.dumps(traffic, indent=2))

    print("\nCapacity before scaling:")
    print(json.dumps(platform.capacity_report(), indent=2))

    scaling_result = platform.scaler.evaluate()
    print(f"\nScaling decision: {scaling_result}")

    platform.finish_traffic(180)

    backup = platform.backups.create_backup()
    print(f"\nCreated backup: {backup.backup_id}")

    print("\nHealth status:")
    print(json.dumps(platform.health_check(), indent=2))

    print("\nFinal capacity report:")
    print(json.dumps(platform.capacity_report(), indent=2))


if __name__ == "__main__":
    main()
