#!/usr/bin/env python3
"""
Highly Available Database Infrastructure Simulator

Demonstrates:
- Primary and replica database topology
- Synchronous and asynchronous replication
- Read/write routing
- Replication lag monitoring
- Automated failover
- Point-in-time recovery planning
- Backup validation
- Cache-aside behavior
- Health checks and metrics
- Failure simulation and recovery
- Configuration validation

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import random
import threading
import time

from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("database_infrastructure")


class DatabaseError(Exception):
    pass


class DatabaseUnavailable(DatabaseError):
    pass


class ReplicationError(DatabaseError):
    pass


class BackupError(DatabaseError):
    pass


class NodeRole(Enum):
    PRIMARY = "primary"
    REPLICA = "replica"


class NodeStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    RECOVERING = "recovering"


class ConsistencyMode(Enum):
    SYNCHRONOUS = "synchronous"
    ASYNCHRONOUS = "asynchronous"


@dataclass
class DatabaseConfig:
    replication_mode: ConsistencyMode = ConsistencyMode.ASYNCHRONOUS
    maximum_replication_lag: float = 5.0
    cache_capacity: int = 1000
    cache_ttl_seconds: int = 30
    backup_directory: str = "database_backups"
    maximum_connections: int = 100

    def validate(self) -> None:
        if self.maximum_replication_lag < 0:
            raise ValueError("Replication lag cannot be negative")
        if self.cache_capacity <= 0:
            raise ValueError("Cache capacity must be positive")
        if self.cache_ttl_seconds <= 0:
            raise ValueError("Cache TTL must be positive")
        if self.maximum_connections <= 0:
            raise ValueError("Connection limit must be positive")


@dataclass
class Record:
    key: str
    value: Any
    version: int
    updated_at: datetime


@dataclass
class DatabaseMetrics:
    reads: int = 0
    writes: int = 0
    failed_operations: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    replication_events: int = 0
    failovers: int = 0
    backups: int = 0
    recovery_events: int = 0


@dataclass
class DatabaseNode:
    node_id: str
    role: NodeRole
    status: NodeStatus = NodeStatus.HEALTHY
    records: dict[str, Record] = field(default_factory=dict)
    replication_position: int = 0
    connections: int = 0
    last_heartbeat: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def is_available(self) -> bool:
        return self.status in {
            NodeStatus.HEALTHY,
            NodeStatus.DEGRADED,
        }

    def check_connection(self, maximum: int) -> None:
        if not self.is_available():
            raise DatabaseUnavailable(
                f"Node {self.node_id} is unavailable"
            )
        if self.connections >= maximum:
            raise DatabaseUnavailable(
                f"Node {self.node_id} connection limit reached"
            )

    def read(self, key: str) -> Optional[Record]:
        if not self.is_available():
            raise DatabaseUnavailable(self.node_id)
        self.last_heartbeat = datetime.now(timezone.utc)
        return self.records.get(key)


class TTLCache:
    """Thread-safe LRU cache with expiration."""

    def __init__(self, capacity: int, ttl_seconds: int):
        self.capacity = capacity
        self.ttl = ttl_seconds
        self.entries = OrderedDict()
        self.lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            entry = self.entries.get(key)
            if entry is None:
                return None

            value, expiration = entry

            if time.monotonic() >= expiration:
                del self.entries[key]
                return None

            self.entries.move_to_end(key)
            return copy.deepcopy(value)

    def set(self, key: str, value: Any) -> None:
        with self.lock:
            self.entries[key] = (
                copy.deepcopy(value),
                time.monotonic() + self.ttl,
            )
            self.entries.move_to_end(key)

            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)

    def invalidate(self, key: str) -> None:
        with self.lock:
            self.entries.pop(key, None)

    def clear(self) -> None:
        with self.lock:
            self.entries.clear()

    def size(self) -> int:
        with self.lock:
            return len(self.entries)


@dataclass
class Backup:
    backup_id: str
    created_at: datetime
    replication_position: int
    records: dict[str, Record]
    checksum: str
    backup_type: str


class BackupManager:
    def __init__(self, directory: str):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.backups: list[Backup] = []

    @staticmethod
    def calculate_checksum(records: dict[str, Record]) -> str:
        payload = {
            key: {
                "value": record.value,
                "version": record.version,
                "updated_at": record.updated_at.isoformat(),
            }
            for key, record in sorted(records.items())
        }

        encoded = json.dumps(
            payload,
            sort_keys=True,
            default=str,
        ).encode("utf-8")

        return hashlib.sha256(encoded).hexdigest()

    def create_backup(
        self,
        node: DatabaseNode,
        backup_type: str = "full",
    ) -> Backup:
        if not node.is_available():
            raise BackupError("Cannot back up an unavailable node")

        if backup_type not in {"full", "incremental"}:
            raise ValueError("Unsupported backup type")

        records = copy.deepcopy(node.records)

        backup = Backup(
            backup_id=f"backup-{len(self.backups) + 1}",
            created_at=datetime.now(timezone.utc),
            replication_position=node.replication_position,
            records=records,
            checksum=self.calculate_checksum(records),
            backup_type=backup_type,
        )

        path = self.directory / f"{backup.backup_id}.json"

        payload = {
            "backup_id": backup.backup_id,
            "created_at": backup.created_at.isoformat(),
            "replication_position": backup.replication_position,
            "checksum": backup.checksum,
            "backup_type": backup.backup_type,
            "records": {
                key: {
                    "value": record.value,
                    "version": record.version,
                    "updated_at": record.updated_at.isoformat(),
                }
                for key, record in records.items()
            },
        }

        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
        temporary.replace(path)

        self.backups.append(backup)
        logger.info("Backup created: %s", backup.backup_id)

        return backup

    def verify(self, backup: Backup) -> bool:
        actual = self.calculate_checksum(backup.records)
        return actual == backup.checksum

    def restore(
        self,
        node: DatabaseNode,
        backup: Backup,
    ) -> None:
        if not self.verify(backup):
            raise BackupError("Backup checksum validation failed")

        node.status = NodeStatus.RECOVERING
        node.records = copy.deepcopy(backup.records)
        node.replication_position = backup.replication_position
        node.status = NodeStatus.HEALTHY

        logger.info("Restored node from %s", backup.backup_id)


class ReplicationManager:
    def __init__(self):
        self.log: list[tuple[int, str, Record]] = []
        self.sequence = 0

    def record_write(self, key: str, record: Record) -> int:
        self.sequence += 1
        self.log.append((self.sequence, key, copy.deepcopy(record)))
        return self.sequence

    def replicate(
        self,
        primary: DatabaseNode,
        replica: DatabaseNode,
        maximum_lag: float,
    ) -> int:
        if not primary.is_available() or not replica.is_available():
            raise ReplicationError("Replication endpoint unavailable")

        pending = [
            entry
            for entry in self.log
            if entry[0] > replica.replication_position
        ]

        for position, key, record in pending:
            replica.records[key] = copy.deepcopy(record)
            replica.replication_position = position

        lag = max(
            0,
            primary.replication_position - replica.replication_position,
        )

        if lag > maximum_lag:
            replica.status = NodeStatus.DEGRADED
        else:
            replica.status = NodeStatus.HEALTHY

        return len(pending)


class DatabaseCluster:
    def __init__(self, config: DatabaseConfig):
        config.validate()

        self.config = config
        self.lock = threading.RLock()

        self.primary = DatabaseNode(
            node_id="db-primary",
            role=NodeRole.PRIMARY,
        )

        self.replicas = [
            DatabaseNode(
                node_id="db-replica-1",
                role=NodeRole.REPLICA,
            ),
            DatabaseNode(
                node_id="db-replica-2",
                role=NodeRole.REPLICA,
            ),
        ]

        self.replication = ReplicationManager()
        self.cache = TTLCache(
            config.cache_capacity,
            config.cache_ttl_seconds,
        )
        self.backups = BackupManager(config.backup_directory)
        self.metrics = DatabaseMetrics()

        self.primary.replication_position = 0

    def write(self, key: str, value: Any) -> Record:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Record key must be non-empty")

        with self.lock:
            try:
                self.primary.check_connection(
                    self.config.maximum_connections
                )

                self.primary.connections += 1

                try:
                    previous = self.primary.records.get(key)
                    version = (
                        previous.version + 1 if previous else 1
                    )

                    record = Record(
                        key=key,
                        value=copy.deepcopy(value),
                        version=version,
                        updated_at=datetime.now(timezone.utc),
                    )

                    position = self.replication.record_write(
                        key,
                        record,
                    )

                    self.primary.records[key] = record
                    self.primary.replication_position = position

                    if (
                        self.config.replication_mode
                        == ConsistencyMode.SYNCHRONOUS
                    ):
                        available = [
                            replica
                            for replica in self.replicas
                            if replica.is_available()
                        ]

                        if not available:
                            self.primary.records.pop(key, None)
                            self.replication.log.pop()
                            self.replication.sequence -= 1
                            self.primary.replication_position = (
                                self.replication.sequence
                            )
                            raise ReplicationError(
                                "Synchronous replication unavailable"
                            )

                        for replica in available:
                            self.replication.replicate(
                                self.primary,
                                replica,
                                self.config.maximum_replication_lag,
                            )

                    self.cache.invalidate(key)
                    self.metrics.writes += 1

                    return copy.deepcopy(record)

                finally:
                    self.primary.connections -= 1

            except DatabaseError:
                self.metrics.failed_operations += 1
                raise

    def read(
        self,
        key: str,
        prefer_replica: bool = True,
    ) -> Optional[Record]:
        with self.lock:
            cached = self.cache.get(key)

            if cached is not None:
                self.metrics.cache_hits += 1
                return cached

            self.metrics.cache_misses += 1

            candidates = (
                self.replicas if prefer_replica else []
            )

            node = next(
                (
                    replica
                    for replica in candidates
                    if replica.is_available()
                    and (
                        self.primary.replication_position
                        - replica.replication_position
                        <= self.config.maximum_replication_lag
                    )
                ),
                None,
            )

            if node is None:
                node = self.primary

            try:
                record = node.read(key)
                self.metrics.reads += 1

                if record is not None:
                    self.cache.set(key, record)

                return copy.deepcopy(record)

            except DatabaseError:
                self.metrics.failed_operations += 1
                raise

    def synchronize_replicas(self) -> int:
        with self.lock:
            total = 0

            for replica in self.replicas:
                if replica.is_available():
                    total += self.replication.replicate(
                        self.primary,
                        replica,
                        self.config.maximum_replication_lag,
                    )

                    self.metrics.replication_events += 1

            return total

    def fail_node(self, node_id: str) -> None:
        with self.lock:
            nodes = [self.primary, *self.replicas]

            node = next(
                (item for item in nodes if item.node_id == node_id),
                None,
            )

            if node is None:
                raise ValueError("Unknown database node")

            node.status = NodeStatus.DOWN
            logger.error("Node failed: %s", node_id)

    def failover(self) -> DatabaseNode:
        with self.lock:
            if self.primary.is_available():
                raise DatabaseError(
                    "Failover not required: primary is healthy"
                )

            candidates = [
                replica
                for replica in self.replicas
                if replica.is_available()
            ]

            if not candidates:
                raise DatabaseUnavailable(
                    "No healthy replica available for promotion"
                )

            promoted = max(
                candidates,
                key=lambda node: node.replication_position,
            )

            promoted.role = NodeRole.PRIMARY

            old_primary = self.primary
            old_primary.role = NodeRole.REPLICA

            self.primary = promoted
            self.replicas.remove(promoted)
            self.replicas.append(old_primary)

            self.metrics.failovers += 1
            self.cache.clear()

            logger.warning(
                "Promoted %s to primary",
                promoted.node_id,
            )

            return promoted

    def create_backup(self) -> Backup:
        with self.lock:
            backup = self.backups.create_backup(self.primary)
            self.metrics.backups += 1
            return backup

    def restore_backup(self, backup: Backup) -> None:
        with self.lock:
            self.backups.restore(self.primary, backup)
            self.cache.clear()
            self.metrics.recovery_events += 1

            for replica in self.replicas:
                replica.records = copy.deepcopy(
                    self.primary.records
                )
                replica.replication_position = (
                    self.primary.replication_position
                )

    def health_report(self) -> dict[str, Any]:
        with self.lock:
            nodes = [self.primary, *self.replicas]

            return {
                "timestamp": datetime.now(
                    timezone.utc
                ).isoformat(),
                "primary": self.primary.node_id,
                "nodes": {
                    node.node_id: {
                        "role": node.role.value,
                        "status": node.status.value,
                        "records": len(node.records),
                        "replication_position": (
                            node.replication_position
                        ),
                        "connections": node.connections,
                    }
                    for node in nodes
                },
                "metrics": vars(self.metrics),
                "cache_entries": self.cache.size(),
                "backup_count": len(self.backups.backups),
            }


def run_demo() -> None:
    config = DatabaseConfig(
        replication_mode=ConsistencyMode.ASYNCHRONOUS,
        maximum_replication_lag=5,
        cache_capacity=100,
        cache_ttl_seconds=15,
        backup_directory="database_backups",
    )

    cluster = DatabaseCluster(config)

    print("\n1. Writing records")

    cluster.write(
        "customer:1001",
        {
            "name": "Aarav Sharma",
            "email": "aarav@example.com",
            "balance": 12500,
        },
    )

    cluster.write(
        "customer:1002",
        {
            "name": "Meera Singh",
            "email": "meera@example.com",
            "balance": 18000,
        },
    )

    print("\n2. Replicating data")

    cluster.synchronize_replicas()

    print("\n3. Reading data through cache and replica")

    print(cluster.read("customer:1001"))
    print(cluster.read("customer:1001"))

    print("\n4. Creating and verifying backup")

    backup = cluster.create_backup()
    assert cluster.backups.verify(backup)

    print("Backup checksum:", backup.checksum)

    print("\n5. Simulating primary failure")

    old_primary_id = cluster.primary.node_id
    cluster.fail_node(old_primary_id)

    promoted = cluster.failover()
    print("New primary:", promoted.node_id)

    print("\n6. Writing after failover")

    cluster.write(
        "customer:1003",
        {
            "name": "Kabir Verma",
            "balance": 25000,
        },
    )

    cluster.synchronize_replicas()

    print("\n7. Health report")

    print(
        json.dumps(
            cluster.health_report(),
            indent=2,
            default=str,
        )
    )

    print("\n8. Recovery demonstration")

    cluster.restore_backup(backup)

    assert cluster.read(
        "customer:1001",
        prefer_replica=False,
    ) is not None

    print("Recovery validation successful")


if __name__ == "__main__":
    try:
        run_demo()
    except (DatabaseError, ValueError, OSError) as error:
        logger.exception("Infrastructure demonstration failed: %s", error)
        raise SystemExit(1)
