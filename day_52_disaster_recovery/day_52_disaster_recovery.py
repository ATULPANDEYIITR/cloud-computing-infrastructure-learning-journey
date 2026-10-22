#!/usr/bin/env python3

"""
Disaster Recovery simulation.

Models:
- RPO: maximum acceptable data-loss window
- RTO: maximum acceptable recovery-time window
- Full backups and incremental backups
- Restore validation
- Pilot light
- Warm standby
- Active-active
- Recovery-point selection
- Recovery-time evaluation
- Failure injection
- Recovery-plan reporting

The implementation is intentionally self-contained and uses only the Python
standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


class RecoveryArchitecture(Enum):
    PILOT_LIGHT = "pilot_light"
    WARM_STANDBY = "warm_standby"
    ACTIVE_ACTIVE = "active_active"


@dataclass(frozen=True)
class RecoveryPolicy:
    name: str
    rpo_minutes: int
    rto_minutes: int

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Recovery policy requires a name")
        if self.rpo_minutes < 0:
            raise ValueError("RPO cannot be negative")
        if self.rto_minutes <= 0:
            raise ValueError("RTO must be positive")


@dataclass(frozen=True)
class DataVersion:
    timestamp: datetime
    version: int
    payload: str

    def validate(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("DataVersion timestamp must be timezone-aware")
        if self.version <= 0:
            raise ValueError("Version must be positive")


@dataclass(frozen=True)
class Backup:
    backup_id: str
    created_at: datetime
    backup_type: str
    source_version: int
    size_mb: int
    checksum: str

    def validate(self) -> None:
        if not self.backup_id.strip():
            raise ValueError("Backup ID cannot be empty")
        if self.created_at.tzinfo is None:
            raise ValueError("Backup timestamp must be timezone-aware")
        if self.backup_type not in {"FULL", "INCREMENTAL"}:
            raise ValueError("Unsupported backup type")
        if self.source_version <= 0:
            raise ValueError("Backup source version must be positive")
        if self.size_mb <= 0:
            raise ValueError("Backup size must be positive")
        if not self.checksum.strip():
            raise ValueError("Backup checksum cannot be empty")


@dataclass
class BackupCatalog:
    backups: List[Backup] = field(default_factory=list)

    def add(self, backup: Backup) -> None:
        backup.validate()
        if any(existing.backup_id == backup.backup_id for existing in self.backups):
            raise ValueError(f"Duplicate backup ID: {backup.backup_id}")
        self.backups.append(backup)
        self.backups.sort(key=lambda item: item.created_at)

    def latest_before_or_at(self, moment: datetime) -> Optional[Backup]:
        candidates = [
            backup for backup in self.backups
            if backup.created_at <= moment
        ]
        return max(candidates, key=lambda item: item.created_at) if candidates else None

    def backups_after(self, moment: datetime) -> List[Backup]:
        return [
            backup for backup in self.backups
            if backup.created_at > moment
        ]


@dataclass(frozen=True)
class RestoreResult:
    success: bool
    restored_version: Optional[int]
    recovery_point: Optional[datetime]
    restore_minutes: int
    message: str


@dataclass
class RecoveryNode:
    name: str
    architecture: RecoveryArchitecture
    healthy: bool = True
    running: bool = False
    synchronized_at: Optional[datetime] = None

    def fail(self) -> None:
        self.healthy = False
        self.running = False

    def start(self) -> None:
        if not self.healthy:
            raise RuntimeError(f"Cannot start failed node: {self.name}")
        self.running = True


class DisasterRecoverySimulator:
    """
    Simulates recovery without touching real infrastructure.

    Production systems should replace the simulated operations with:
    - immutable/object-locked backups
    - encrypted backup storage
    - infrastructure-as-code
    - monitored restore jobs
    - tested DNS/load-balancer changes
    - database replication
    - controlled failover procedures
    """

    def __init__(
        self,
        policy: RecoveryPolicy,
        architecture: RecoveryArchitecture,
        backups: BackupCatalog,
    ) -> None:
        policy.validate()
        self.policy = policy
        self.architecture = architecture
        self.backups = backups

    def calculate_rpo(self, failure_time: datetime) -> Optional[int]:
        """
        Returns the number of minutes between failure and the latest
        available recovery point.
        """
        recovery_point = self.backups.latest_before_or_at(failure_time)
        if recovery_point is None:
            return None

        delta = failure_time - recovery_point.created_at
        return max(0, int(delta.total_seconds() // 60))

    def restore(
        self,
        failure_time: datetime,
        target_version: Optional[int] = None,
    ) -> RestoreResult:
        """
        Selects the latest usable backup before failure and simulates restore.

        A real restore process must validate checksums, dependency ordering,
        encryption keys, database consistency, application compatibility,
        and post-restore integrity.
        """
        backup = self.backups.latest_before_or_at(failure_time)

        if backup is None:
            return RestoreResult(
                success=False,
                restored_version=None,
                recovery_point=None,
                restore_minutes=0,
                message="No recoverable backup exists before the failure.",
            )

        if target_version is not None and target_version != backup.source_version:
            return RestoreResult(
                success=False,
                restored_version=None,
                recovery_point=backup.created_at,
                restore_minutes=0,
                message=(
                    f"Requested version {target_version} is not available "
                    f"from the selected recovery point."
                ),
            )

        restore_minutes = (
            20 if backup.backup_type == "FULL" else 12
        )

        if self.architecture == RecoveryArchitecture.PILOT_LIGHT:
            restore_minutes += 25
        elif self.architecture == RecoveryArchitecture.WARM_STANDBY:
            restore_minutes += 8
        elif self.architecture == RecoveryArchitecture.ACTIVE_ACTIVE:
            restore_minutes = 2

        return RestoreResult(
            success=True,
            restored_version=backup.source_version,
            recovery_point=backup.created_at,
            restore_minutes=restore_minutes,
            message=f"Restored from {backup.backup_id}.",
        )

    def evaluate_recovery(self, failure_time: datetime) -> Dict[str, object]:
        rpo = self.calculate_rpo(failure_time)
        restore = self.restore(failure_time)

        rpo_met = rpo is not None and rpo <= self.policy.rpo_minutes
        rto_met = restore.success and restore.restore_minutes <= self.policy.rto_minutes

        return {
            "architecture": self.architecture.value,
            "rpo_minutes": rpo,
            "rpo_target_minutes": self.policy.rpo_minutes,
            "rpo_met": rpo_met,
            "rto_minutes": restore.restore_minutes,
            "rto_target_minutes": self.policy.rto_minutes,
            "rto_met": rto_met,
            "recovery_success": restore.success,
            "restored_version": restore.restored_version,
            "recovery_point": (
                restore.recovery_point.isoformat()
                if restore.recovery_point
                else None
            ),
            "message": restore.message,
        }


class RecoveryExercise:
    """
    Exercises an architecture using simulated nodes.

    The exercise makes architectural differences explicit:
    pilot light requires startup work, warm standby keeps a reduced
    environment ready, and active-active keeps multiple live sites serving
    traffic.
    """

    def __init__(
        self,
        architecture: RecoveryArchitecture,
        nodes: Sequence[RecoveryNode],
    ) -> None:
        self.architecture = architecture
        self.nodes = list(nodes)

    def validate_topology(self) -> None:
        if not self.nodes:
            raise ValueError("At least one recovery node is required")

        if self.architecture == RecoveryArchitecture.ACTIVE_ACTIVE:
            healthy_running = [
                node for node in self.nodes
                if node.healthy and node.running
            ]
            if len(healthy_running) < 2:
                raise ValueError(
                    "Active-active requires at least two healthy running nodes."
                )

    def fail_primary(self, primary_name: str) -> None:
        for node in self.nodes:
            if node.name == primary_name:
                node.fail()
                return
        raise KeyError(f"Unknown node: {primary_name}")

    def recover(self, failed_name: str) -> Tuple[bool, str]:
        failed = next(
            (node for node in self.nodes if node.name == failed_name),
            None,
        )
        if failed is None:
            return False, f"Unknown failed node: {failed_name}"

        if self.architecture == RecoveryArchitecture.ACTIVE_ACTIVE:
            remaining = [
                node for node in self.nodes
                if node.name != failed_name and node.healthy and node.running
            ]
            if remaining:
                return True, "Traffic can continue on another active node."
            return False, "No active node remains."

        failed.healthy = True

        if self.architecture == RecoveryArchitecture.WARM_STANDBY:
            failed.start()
            return True, "Warm standby was promoted."

        failed.start()
        return True, "Pilot-light infrastructure was started."

    def status(self) -> List[Dict[str, object]]:
        return [
            {
                "name": node.name,
                "architecture": node.architecture.value,
                "healthy": node.healthy,
                "running": node.running,
                "synchronized_at": (
                    node.synchronized_at.isoformat()
                    if node.synchronized_at
                    else None
                ),
            }
            for node in self.nodes
        ]


def utc_timestamp(minutes_from_start: int) -> datetime:
    return datetime(2026, 10, 22, 0, 0, tzinfo=timezone.utc) + timedelta(
        minutes=minutes_from_start
    )


def build_backup_catalog() -> BackupCatalog:
    catalog = BackupCatalog()

    catalog.add(
        Backup(
            backup_id="full-0001",
            created_at=utc_timestamp(0),
            backup_type="FULL",
            source_version=100,
            size_mb=8000,
            checksum="sha256:full0001",
        )
    )

    catalog.add(
        Backup(
            backup_id="inc-0002",
            created_at=utc_timestamp(30),
            backup_type="INCREMENTAL",
            source_version=101,
            size_mb=600,
            checksum="sha256:inc0002",
        )
    )

    catalog.add(
        Backup(
            backup_id="inc-0003",
            created_at=utc_timestamp(60),
            backup_type="INCREMENTAL",
            source_version=102,
            size_mb=650,
            checksum="sha256:inc0003",
        )
    )

    catalog.add(
        Backup(
            backup_id="inc-0004",
            created_at=utc_timestamp(90),
            backup_type="INCREMENTAL",
            source_version=103,
            size_mb=700,
            checksum="sha256:inc0004",
        )
    )

    return catalog


def print_report(title: str, report: Dict[str, object]) -> None:
    print(f"\n=== {title} ===")
    for key, value in report.items():
        print(f"{key}: {value}")


def demonstrate_architectures() -> None:
    failure_time = utc_timestamp(105)
    catalog = build_backup_catalog()

    architectures = [
        (
            RecoveryArchitecture.PILOT_LIGHT,
            RecoveryPolicy("Critical API", rpo_minutes=30, rto_minutes=60),
        ),
        (
            RecoveryArchitecture.WARM_STANDBY,
            RecoveryPolicy("Critical API", rpo_minutes=30, rto_minutes=30),
        ),
        (
            RecoveryArchitecture.ACTIVE_ACTIVE,
            RecoveryPolicy("Critical API", rpo_minutes=5, rto_minutes=5),
        ),
    ]

    for architecture, policy in architectures:
        simulator = DisasterRecoverySimulator(
            policy=policy,
            architecture=architecture,
            backups=catalog,
        )
        print_report(
            architecture.value,
            simulator.evaluate_recovery(failure_time),
        )


def demonstrate_failure_modes() -> None:
    print("\n=== Failure handling ===")

    empty_catalog = BackupCatalog()
    policy = RecoveryPolicy("Billing", rpo_minutes=15, rto_minutes=30)

    simulator = DisasterRecoverySimulator(
        policy=policy,
        architecture=RecoveryArchitecture.PILOT_LIGHT,
        backups=empty_catalog,
    )

    result = simulator.restore(utc_timestamp(120))
    print(result.message)

    try:
        RecoveryPolicy("Invalid", rpo_minutes=-1, rto_minutes=20).validate()
    except ValueError as exc:
        print(f"Validation failure: {exc}")

    try:
        Backup(
            backup_id="bad",
            created_at=utc_timestamp(1),
            backup_type="UNKNOWN",
            source_version=1,
            size_mb=10,
            checksum="x",
        ).validate()
    except ValueError as exc:
        print(f"Backup validation failure: {exc}")


def demonstrate_failover_topology() -> None:
    print("\n=== Active-active failover ===")

    timestamp = utc_timestamp(90)

    nodes = [
        RecoveryNode(
            name="region-a",
            architecture=RecoveryArchitecture.ACTIVE_ACTIVE,
            healthy=True,
            running=True,
            synchronized_at=timestamp,
        ),
        RecoveryNode(
            name="region-b",
            architecture=RecoveryArchitecture.ACTIVE_ACTIVE,
            healthy=True,
            running=True,
            synchronized_at=timestamp,
        ),
    ]

    exercise = RecoveryExercise(
        architecture=RecoveryArchitecture.ACTIVE_ACTIVE,
        nodes=nodes,
    )

    exercise.validate_topology()
    exercise.fail_primary("region-a")

    success, message = exercise.recover("region-a")
    print(f"Recovery successful: {success}")
    print(message)

    for node_status in exercise.status():
        print(node_status)


def demonstrate_backup_chain() -> None:
    print("\n=== Backup chain ===")

    catalog = build_backup_catalog()
    failure = utc_timestamp(75)

    selected = catalog.latest_before_or_at(failure)
    later_backups = catalog.backups_after(failure)

    if selected:
        print(
            f"Recovery point: {selected.created_at.isoformat()} "
            f"version={selected.source_version} "
            f"type={selected.backup_type}"
        )

    print(f"Backups after failure: {len(later_backups)}")


def main() -> None:
    demonstrate_architectures()
    demonstrate_failure_modes()
    demonstrate_failover_topology()
    demonstrate_backup_chain()


if __name__ == "__main__":
    main()
