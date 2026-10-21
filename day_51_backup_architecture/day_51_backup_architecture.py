#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
import hashlib
import json
import shutil
import tempfile
import threading
import time


class BackupType(str, Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    SNAPSHOT = "snapshot"


class BackupStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass(frozen=True)
class BackupFile:
    relative_path: str
    size: int
    checksum: str
    modified_at: float


@dataclass
class BackupRecord:
    backup_id: str
    backup_type: BackupType
    created_at: datetime
    source: str
    destination: str
    files: list[BackupFile] = field(default_factory=list)
    parent_backup_id: str | None = None
    status: BackupStatus = BackupStatus.RUNNING
    error: str | None = None

    @property
    def size(self) -> int:
        return sum(item.size for item in self.files)


class BackupError(RuntimeError):
    pass


class BackupCatalog:
    """Durable catalog representation for backup metadata.

    A real backup platform normally stores this catalog separately from the
    backup data so that loss of the backup repository does not destroy its
    recovery metadata.
    """

    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self.records: dict[str, BackupRecord] = {}
        self._lock = threading.RLock()
        self.load()

    def load(self) -> None:
        if not self.catalog_path.exists():
            return

        with self.catalog_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)

        for item in raw:
            record = BackupRecord(
                backup_id=item["backup_id"],
                backup_type=BackupType(item["backup_type"]),
                created_at=datetime.fromisoformat(item["created_at"]),
                source=item["source"],
                destination=item["destination"],
                files=[
                    BackupFile(
                        relative_path=f["relative_path"],
                        size=f["size"],
                        checksum=f["checksum"],
                        modified_at=f["modified_at"],
                    )
                    for f in item["files"]
                ],
                parent_backup_id=item.get("parent_backup_id"),
                status=BackupStatus(item["status"]),
                error=item.get("error"),
            )
            self.records[record.backup_id] = record

    def save(self) -> None:
        with self._lock:
            self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
            payload = []

            for record in self.records.values():
                payload.append(
                    {
                        "backup_id": record.backup_id,
                        "backup_type": record.backup_type.value,
                        "created_at": record.created_at.isoformat(),
                        "source": record.source,
                        "destination": record.destination,
                        "parent_backup_id": record.parent_backup_id,
                        "status": record.status.value,
                        "error": record.error,
                        "files": [
                            {
                                "relative_path": f.relative_path,
                                "size": f.size,
                                "checksum": f.checksum,
                                "modified_at": f.modified_at,
                            }
                            for f in record.files
                        ],
                    }
                )

            temporary = self.catalog_path.with_suffix(".tmp")
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)

            # Atomic replacement prevents a partially written catalog after
            # an interrupted process.
            temporary.replace(self.catalog_path)

    def add(self, record: BackupRecord) -> None:
        with self._lock:
            self.records[record.backup_id] = record
            self.save()

    def completed(self) -> list[BackupRecord]:
        return sorted(
            (
                record
                for record in self.records.values()
                if record.status == BackupStatus.COMPLETED
            ),
            key=lambda record: record.created_at,
        )

    def get(self, backup_id: str) -> BackupRecord:
        try:
            return self.records[backup_id]
        except KeyError as exc:
            raise BackupError(f"Unknown backup: {backup_id}") from exc


class BackupManager:
    def __init__(
        self,
        source: Path,
        repository: Path,
        catalog: BackupCatalog,
    ) -> None:
        self.source = source.resolve()
        self.repository = repository.resolve()
        self.catalog = catalog

        if not self.source.exists() or not self.source.is_dir():
            raise BackupError(f"Source directory does not exist: {self.source}")

        self.repository.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def checksum(path: Path) -> str:
        digest = hashlib.sha256()

        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)

        return digest.hexdigest()

    def inventory(self) -> dict[str, BackupFile]:
        result: dict[str, BackupFile] = {}

        for path in self.source.rglob("*"):
            if not path.is_file():
                continue

            relative = path.relative_to(self.source).as_posix()
            stat = path.stat()

            result[relative] = BackupFile(
                relative_path=relative,
                size=stat.st_size,
                checksum=self.checksum(path),
                modified_at=stat.st_mtime,
            )

        return result

    def _copy_file(self, relative_path: str, destination_root: Path) -> None:
        source_path = self.source / relative_path
        destination_path = destination_root / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)

    def _new_id(self, backup_type: BackupType) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"{backup_type.value}-{stamp}-{time.time_ns() % 1_000_000:06d}"

    def create_full(self) -> BackupRecord:
        return self._create_backup(BackupType.FULL)

    def create_incremental(self) -> BackupRecord:
        completed = self.catalog.completed()
        if not completed:
            return self.create_full()

        previous = completed[-1]
        return self._create_backup(
            BackupType.INCREMENTAL,
            parent_backup_id=previous.backup_id,
        )

    def create_snapshot(self) -> BackupRecord:
        """Create a filesystem-level copy representing a point-in-time state.

        This educational implementation copies data instead of depending on
        operating-system snapshot APIs such as ZFS, LVM, or VSS.
        """
        return self._create_backup(BackupType.SNAPSHOT)

    def _create_backup(
        self,
        backup_type: BackupType,
        parent_backup_id: str | None = None,
    ) -> BackupRecord:
        backup_id = self._new_id(backup_type)
        destination = self.repository / backup_id
        destination.mkdir(parents=True)

        record = BackupRecord(
            backup_id=backup_id,
            backup_type=backup_type,
            created_at=datetime.now(timezone.utc),
            source=str(self.source),
            destination=str(destination),
            parent_backup_id=parent_backup_id,
        )

        try:
            current = self.inventory()

            if backup_type in {BackupType.FULL, BackupType.SNAPSHOT}:
                selected = current
            else:
                parent = self.catalog.get(parent_backup_id)  # type: ignore[arg-type]
                previous = {
                    item.relative_path: item
                    for item in parent.files
                }
                selected = {
                    path: item
                    for path, item in current.items()
                    if path not in previous
                    or previous[path].checksum != item.checksum
                    or previous[path].size != item.size
                }

            for relative_path in selected:
                self._copy_file(relative_path, destination)

            record.files = list(selected.values())
            record.status = BackupStatus.COMPLETED
            self.catalog.add(record)

            return record

        except Exception as exc:
            record.status = BackupStatus.FAILED
            record.error = str(exc)

            try:
                self.catalog.add(record)
            finally:
                shutil.rmtree(destination, ignore_errors=True)

            raise BackupError(
                f"{backup_type.value} backup failed: {exc}"
            ) from exc

    def verify(self, backup_id: str) -> tuple[bool, list[str]]:
        record = self.catalog.get(backup_id)

        if record.status != BackupStatus.COMPLETED:
            return False, [f"Backup status is {record.status.value}"]

        problems: list[str] = []

        for item in record.files:
            path = Path(record.destination) / item.relative_path

            if not path.exists():
                problems.append(f"Missing: {item.relative_path}")
                continue

            if path.stat().st_size != item.size:
                problems.append(f"Size mismatch: {item.relative_path}")
                continue

            if self.checksum(path) != item.checksum:
                problems.append(f"Checksum mismatch: {item.relative_path}")

        return not problems, problems

    def restore(self, backup_id: str, destination: Path) -> None:
        """Restore a full backup directly or reconstruct an incremental chain."""
        record = self.catalog.get(backup_id)
        destination = destination.resolve()

        if destination == self.source:
            raise BackupError("Refusing to restore over the live source directory")

        chain: list[BackupRecord] = []
        current = record

        while True:
            chain.append(current)

            if current.backup_type == BackupType.FULL:
                break

            if current.parent_backup_id is None:
                raise BackupError("Incremental backup has no parent")

            current = self.catalog.get(current.parent_backup_id)

        chain.reverse()
        destination.mkdir(parents=True, exist_ok=True)

        for backup in chain:
            for item in backup.files:
                source_file = Path(backup.destination) / item.relative_path
                target_file = destination / item.relative_path
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, target_file)

    def apply_retention(
        self,
        keep_full: int = 2,
        keep_days: int = 14,
    ) -> list[str]:
        """Delete expired backup data while retaining recent recovery points."""
        if keep_full < 1:
            raise ValueError("keep_full must be at least 1")
        if keep_days < 1:
            raise ValueError("keep_days must be at least 1")

        now = datetime.now(timezone.utc)
        completed = self.catalog.completed()
        fulls = [
            item
            for item in completed
            if item.backup_type == BackupType.FULL
        ]

        retained_full_ids = {
            item.backup_id
            for item in fulls[-keep_full:]
        }

        cutoff = now - timedelta(days=keep_days)
        deleted: list[str] = []

        for record in completed:
            keep = (
                record.backup_id in retained_full_ids
                or record.created_at >= cutoff
            )

            if keep:
                continue

            shutil.rmtree(record.destination, ignore_errors=True)
            record.status = BackupStatus.EXPIRED
            deleted.append(record.backup_id)

        if deleted:
            self.catalog.save()

        return deleted


def build_demo_source(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "application").mkdir(exist_ok=True)
    (path / "application" / "config.txt").write_text(
        "environment=production\nbackup_required=true\n",
        encoding="utf-8",
    )
    (path / "application" / "data.txt").write_text(
        "customer-record-001\ncustomer-record-002\n",
        encoding="utf-8",
    )


def run_demo() -> None:
    with tempfile.TemporaryDirectory(prefix="backup-architecture-") as root:
        base = Path(root)
        source = base / "live-data"
        repository = base / "backup-repository"
        catalog_path = repository / "catalog.json"

        build_demo_source(source)

        catalog = BackupCatalog(catalog_path)
        manager = BackupManager(source, repository, catalog)

        full = manager.create_full()
        valid, problems = manager.verify(full.backup_id)
        print(f"FULL {full.backup_id}: verified={valid}, problems={problems}")

        # Change one file and create an incremental backup. Only changed or
        # newly created files are copied into the incremental data set.
        (source / "application" / "data.txt").write_text(
            "customer-record-001\ncustomer-record-002\ncustomer-record-003\n",
            encoding="utf-8",
        )
        (source / "application" / "new-file.txt").write_text(
            "new application data\n",
            encoding="utf-8",
        )

        incremental = manager.create_incremental()
        valid, problems = manager.verify(incremental.backup_id)
        print(
            f"INCREMENTAL {incremental.backup_id}: "
            f"files={len(incremental.files)}, verified={valid}"
        )

        snapshot = manager.create_snapshot()
        valid, problems = manager.verify(snapshot.backup_id)
        print(
            f"SNAPSHOT {snapshot.backup_id}: "
            f"files={len(snapshot.files)}, verified={valid}"
        )

        restored = base / "restored-data"
        manager.restore(incremental.backup_id, restored)

        restored_content = (
            restored / "application" / "data.txt"
        ).read_text(encoding="utf-8")

        print(f"RESTORED DATA: {restored_content.strip()}")

        expired = manager.apply_retention(
            keep_full=1,
            keep_days=1,
        )
        print(f"RETENTION EXPIRED: {expired}")

        print("\nBACKUP CATALOG")
        for record in catalog.records.values():
            print(
                record.backup_id,
                record.backup_type.value,
                record.status.value,
                record.size,
                "bytes",
            )


if __name__ == "__main__":
    run_demo()
