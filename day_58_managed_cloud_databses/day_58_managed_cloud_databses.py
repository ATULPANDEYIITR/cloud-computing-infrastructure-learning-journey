#!/usr/bin/env python3
"""
Managed Cloud Database Operations Simulator

Models a managed PostgreSQL-style cloud database with:
- automated patching
- scheduled and retention-aware backups
- horizontal read scaling
- maintenance windows
- health monitoring
- failover
- backup restoration
- operational validation
- audit logging

The implementation is intentionally provider-neutral.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Set
import hashlib
import random
import secrets


class DatabaseState(str, Enum):
    AVAILABLE = "available"
    MAINTENANCE = "maintenance"
    DEGRADED = "degraded"
    FAILED = "failed"
    RESTORING = "restoring"


class NodeRole(str, Enum):
    PRIMARY = "primary"
    REPLICA = "read-replica"


class BackupType(str, Enum):
    FULL = "full"
    SNAPSHOT = "snapshot"


class MaintenanceStatus(str, Enum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidationError(ValueError):
    pass


class OperationalError(RuntimeError):
    pass


@dataclass(frozen=True)
class Backup:
    backup_id: str
    database_id: str
    created_at: datetime
    backup_type: BackupType
    size_gb: float
    checksum: str
    expires_at: datetime

    def validate(self) -> None:
        if self.size_gb <= 0:
            raise ValidationError("Backup size must be positive.")
        if self.expires_at <= self.created_at:
            raise ValidationError("Backup expiration must be after creation.")


@dataclass
class StatusMetric:
    cpu_percent: float
    storage_percent: float
    replication_lag_seconds: float
    connections: int

    def healthy(self) -> bool:
        return (
            self.cpu_percent < 85
            and self.storage_percent < 90
            and self.replication_lag_seconds < 30
        )


@dataclass
class DatabaseNode:
    node_id: str
    zone: str
    role: NodeRole
    version: str
    state: DatabaseState = DatabaseState.AVAILABLE
    metrics: Optional[StatusMetric] = None

    def accept_reads(self) -> bool:
        return self.state == DatabaseState.AVAILABLE

    def accept_writes(self) -> bool:
        return self.role == NodeRole.PRIMARY and self.accept_reads()


@dataclass
class MaintenanceEvent:
    event_id: str
    database_id: str
    scheduled_at: datetime
    version_from: str
    version_to: str
    status: MaintenanceStatus = MaintenanceStatus.SCHEDULED
    error: Optional[str] = None


@dataclass
class AuditEvent:
    timestamp: datetime
    action: str
    resource: str
    actor: str
    result: str
    details: str


@dataclass
class ManagedDatabase:
    database_id: str
    name: str
    engine: str
    version: str
    region: str
    storage_gb: int
    backup_retention_days: int
    maintenance_hour_utc: int
    nodes: Dict[str, DatabaseNode] = field(default_factory=dict)
    backups: List[Backup] = field(default_factory=list)
    maintenance: List[MaintenanceEvent] = field(default_factory=list)
    audit_log: List[AuditEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.database_id or not self.name:
            raise ValidationError("Database identifiers cannot be empty.")
        if self.storage_gb < 10:
            raise ValidationError("Managed databases require at least 10 GB.")
        if not 1 <= self.backup_retention_days <= 35:
            raise ValidationError("Backup retention must be between 1 and 35 days.")
        if not 0 <= self.maintenance_hour_utc <= 23:
            raise ValidationError("Maintenance hour must be between 0 and 23.")

    def log(self, action: str, actor: str, result: str, details: str) -> None:
        self.audit_log.append(
            AuditEvent(
                timestamp=datetime.now(timezone.utc),
                action=action,
                resource=self.database_id,
                actor=actor,
                result=result,
                details=details,
            )
        )

    def primary(self) -> DatabaseNode:
        primaries = [n for n in self.nodes.values() if n.role == NodeRole.PRIMARY]
        if len(primaries) != 1:
            raise OperationalError("Database must have exactly one primary node.")
        return primaries[0]

    def replicas(self) -> List[DatabaseNode]:
        return [n for n in self.nodes.values() if n.role == NodeRole.REPLICA]

    def provision_node(self, zone: str, role: NodeRole) -> DatabaseNode:
        if role == NodeRole.PRIMARY and any(
            n.role == NodeRole.PRIMARY for n in self.nodes.values()
        ):
            raise ValidationError("A database can have only one primary.")

        node_id = f"{self.database_id}-{secrets.token_hex(4)}"
        node = DatabaseNode(
            node_id=node_id,
            zone=zone,
            role=role,
            version=self.version,
        )
        self.nodes[node_id] = node
        self.log("PROVISION_NODE", "system", "SUCCESS", f"{role.value} in {zone}")
        return node

    def scale_read_replicas(self, desired: int, zones: List[str]) -> None:
        if desired < 0 or desired > 10:
            raise ValidationError("Replica count must be between 0 and 10.")
        if desired > 0 and not zones:
            raise ValidationError("At least one availability zone is required.")

        current = len(self.replicas())

        if desired > current:
            for index in range(current, desired):
                zone = zones[index % len(zones)]
                self.provision_node(zone, NodeRole.REPLICA)
        elif desired < current:
            candidates = self.replicas()
            for node in candidates[desired:]:
                del self.nodes[node.node_id]

        self.log(
            "SCALE_READ_REPLICAS",
            "operator",
            "SUCCESS",
            f"{current} -> {desired}",
        )

    def collect_metrics(self) -> None:
        for node in self.nodes.values():
            node.metrics = StatusMetric(
                cpu_percent=round(random.uniform(15, 92), 2),
                storage_percent=round(random.uniform(25, 88), 2),
                replication_lag_seconds=(
                    0
                    if node.role == NodeRole.PRIMARY
                    else round(random.uniform(0.2, 18), 2)
                ),
                connections=random.randint(10, 180),
            )

            if not node.metrics.healthy():
                node.state = DatabaseState.DEGRADED
            else:
                node.state = DatabaseState.AVAILABLE

    def create_backup(
        self,
        backup_type: BackupType,
        now: Optional[datetime] = None,
    ) -> Backup:
        now = now or datetime.now(timezone.utc)

        # A backup is useful only if the database has an operational primary.
        if not self.primary().accept_reads():
            raise OperationalError("Cannot create backup while primary is unavailable.")

        payload = f"{self.database_id}:{self.version}:{now.isoformat()}".encode()
        checksum = hashlib.sha256(payload).hexdigest()

        backup = Backup(
            backup_id=f"bkp-{secrets.token_hex(6)}",
            database_id=self.database_id,
            created_at=now,
            backup_type=backup_type,
            size_gb=max(1.0, self.storage_gb * 0.18),
            checksum=checksum,
            expires_at=now + timedelta(days=self.backup_retention_days),
        )
        backup.validate()
        self.backups.append(backup)

        self.log(
            "CREATE_BACKUP",
            "backup-service",
            "SUCCESS",
            f"{backup.backup_id} expires {backup.expires_at.isoformat()}",
        )
        return backup

    def purge_expired_backups(self, now: Optional[datetime] = None) -> int:
        now = now or datetime.now(timezone.utc)
        before = len(self.backups)
        self.backups = [b for b in self.backups if b.expires_at > now]
        removed = before - len(self.backups)

        self.log(
            "PURGE_BACKUPS",
            "backup-service",
            "SUCCESS",
            f"Removed {removed} expired backups.",
        )
        return removed

    def schedule_patch(self, target_version: str, scheduled_at: datetime) -> MaintenanceEvent:
        if target_version == self.version:
            raise ValidationError("Target version is already installed.")
        if scheduled_at.tzinfo is None:
            raise ValidationError("Maintenance time must be timezone-aware.")
        if scheduled_at < datetime.now(timezone.utc):
            raise ValidationError("Maintenance cannot be scheduled in the past.")

        event = MaintenanceEvent(
            event_id=f"mnt-{secrets.token_hex(5)}",
            database_id=self.database_id,
            scheduled_at=scheduled_at,
            version_from=self.version,
            version_to=target_version,
        )
        self.maintenance.append(event)

        self.log(
            "SCHEDULE_PATCH",
            "maintenance-service",
            "SUCCESS",
            f"{self.version} -> {target_version}",
        )
        return event

    def run_maintenance(self, event_id: str) -> None:
        event = next(
            (item for item in self.maintenance if item.event_id == event_id),
            None,
        )
        if event is None:
            raise ValidationError("Maintenance event does not exist.")
        if event.status != MaintenanceStatus.SCHEDULED:
            raise OperationalError("Maintenance event cannot be executed again.")

        event.status = MaintenanceStatus.RUNNING
        previous_state = self.state
        self.state = DatabaseState.MAINTENANCE

        try:
            backup = self.create_backup(BackupType.SNAPSHOT)
            if not backup.checksum:
                raise OperationalError("Backup verification failed.")

            for node in self.nodes.values():
                node.state = DatabaseState.MAINTENANCE
                node.version = event.version_to
                node.state = DatabaseState.AVAILABLE

            self.version = event.version_to
            event.status = MaintenanceStatus.COMPLETED
            self.state = DatabaseState.AVAILABLE

            self.log(
                "PATCH_DATABASE",
                "maintenance-service",
                "SUCCESS",
                f"Patched to {event.version_to}; backup {backup.backup_id} verified.",
            )
        except Exception as exc:
            event.status = MaintenanceStatus.FAILED
            event.error = str(exc)
            self.state = previous_state
            self.log("PATCH_DATABASE", "maintenance-service", "FAILED", str(exc))
            raise

    def failover(self) -> DatabaseNode:
        old_primary = self.primary()
        candidates = [
            node
            for node in self.replicas()
            if node.state == DatabaseState.AVAILABLE
        ]

        if not candidates:
            old_primary.state = DatabaseState.FAILED
            self.state = DatabaseState.FAILED
            self.log(
                "FAILOVER",
                "failover-service",
                "FAILED",
                "No healthy replica available.",
            )
            raise OperationalError("Failover failed: no healthy replica.")

        selected = min(
            candidates,
            key=lambda node: node.metrics.replication_lag_seconds
            if node.metrics
            else float("inf"),
        )

        old_primary.role = NodeRole.REPLICA
        old_primary.state = DatabaseState.DEGRADED
        selected.role = NodeRole.PRIMARY
        selected.state = DatabaseState.AVAILABLE
        self.state = DatabaseState.AVAILABLE

        self.log(
            "FAILOVER",
            "failover-service",
            "SUCCESS",
            f"{old_primary.node_id} -> {selected.node_id}",
        )
        return selected

    def restore(self, backup_id: str) -> None:
        backup = next((b for b in self.backups if b.backup_id == backup_id), None)
        if backup is None:
            raise ValidationError("Backup not found.")
        if backup.expires_at <= datetime.now(timezone.utc):
            raise OperationalError("Backup has expired.")

        self.state = DatabaseState.RESTORING

        expected = hashlib.sha256(
            f"{self.database_id}:{self.version}:{backup.created_at.isoformat()}".encode()
        ).hexdigest()

        if expected != backup.checksum:
            self.state = DatabaseState.FAILED
            raise OperationalError("Backup checksum verification failed.")

        self.state = DatabaseState.AVAILABLE
        self.log(
            "RESTORE_BACKUP",
            "restore-service",
            "SUCCESS",
            f"Restored from {backup.backup_id}",
        )

    def validate_configuration(self) -> List[str]:
        errors: List[str] = []

        if len([n for n in self.nodes.values() if n.role == NodeRole.PRIMARY]) != 1:
            errors.append("Exactly one primary node is required.")

        if self.backup_retention_days < 7:
            errors.append("Production backup retention is below seven days.")

        zones = {node.zone for node in self.nodes.values()}
        if len(zones) < 2:
            errors.append("Production deployments should span at least two zones.")

        for node in self.nodes.values():
            if node.version != self.version:
                errors.append(f"Node {node.node_id} has a version mismatch.")

        return errors


def demonstrate() -> None:
    now = datetime.now(timezone.utc)

    database = ManagedDatabase(
        database_id="orders-prod",
        name="orders",
        engine="PostgreSQL",
        version="16.4",
        region="ap-south-1",
        storage_gb=250,
        backup_retention_days=14,
        maintenance_hour_utc=2,
    )

    database.provision_node("zone-a", NodeRole.PRIMARY)
    database.provision_node("zone-b", NodeRole.REPLICA)
    database.scale_read_replicas(2, ["zone-b", "zone-c"])

    database.collect_metrics()

    backup = database.create_backup(BackupType.FULL, now)
    database.purge_expired_backups(now)

    maintenance = database.schedule_patch(
        "16.5",
        now + timedelta(minutes=5),
    )
    database.run_maintenance(maintenance.event_id)

    database.collect_metrics()

    primary = database.primary()
    if primary.state != DatabaseState.AVAILABLE:
        database.failover()

    errors = database.validate_configuration()
    if errors:
        print("Configuration warnings:")
        for error in errors:
            print(f" - {error}")
    else:
        print("Configuration validation: PASS")

    database.restore(backup.backup_id)

    print(f"Database: {database.name}")
    print(f"Version: {database.version}")
    print(f"State: {database.state.value}")
    print(f"Nodes: {len(database.nodes)}")
    print(f"Backups retained: {len(database.backups)}")
    print(f"Audit events: {len(database.audit_log)}")

    assert database.state == DatabaseState.AVAILABLE
    assert database.primary().role == NodeRole.PRIMARY
    assert all(node.version == database.version for node in database.nodes.values())


if __name__ == "__main__":
    demonstrate()
