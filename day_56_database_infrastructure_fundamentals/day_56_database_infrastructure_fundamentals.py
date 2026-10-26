from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable
import copy
import json
import tempfile


class TransactionState(Enum):
    ACTIVE = "active"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"


class ReplicationRole(Enum):
    PRIMARY = "primary"
    REPLICA = "replica"


class DatabaseError(Exception):
    """Base database infrastructure error."""


class TransactionError(DatabaseError):
    pass


class ConstraintViolation(DatabaseError):
    pass


class ReplicationError(DatabaseError):
    pass


class StorageEngine:
    """Small storage-engine abstraction using an in-memory page-like dictionary."""

    def __init__(self) -> None:
        self._pages: dict[str, dict[str, Any]] = {}

    def read(self, key: str) -> Any:
        return copy.deepcopy(self._pages.get(key))

    def write(self, key: str, value: Any) -> None:
        self._pages[key] = copy.deepcopy(value)

    def delete(self, key: str) -> None:
        self._pages.pop(key, None)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return copy.deepcopy(self._pages)

    def restore(self, snapshot: dict[str, dict[str, Any]]) -> None:
        self._pages = copy.deepcopy(snapshot)

    def size(self) -> int:
        return len(self._pages)


@dataclass(frozen=True)
class LogRecord:
    lsn: int
    transaction_id: str
    operation: str
    key: str
    value: Any


@dataclass
class Transaction:
    transaction_id: str
    state: TransactionState = TransactionState.ACTIVE
    operations: list[tuple[str, str, Any]] = field(default_factory=list)


class TransactionManager:
    """Coordinates atomic changes and produces a simple write-ahead log."""

    def __init__(self, engine: StorageEngine) -> None:
        self.engine = engine
        self.transactions: dict[str, Transaction] = {}
        self.wal: list[LogRecord] = []
        self._next_lsn = 1

    def begin(self, transaction_id: str) -> Transaction:
        if transaction_id in self.transactions:
            raise TransactionError(f"Transaction already exists: {transaction_id}")
        tx = Transaction(transaction_id)
        self.transactions[transaction_id] = tx
        return tx

    def put(self, tx: Transaction, key: str, value: Any) -> None:
        self._ensure_active(tx)
        if not key:
            raise ConstraintViolation("Storage key cannot be empty.")
        tx.operations.append(("put", key, copy.deepcopy(value)))

    def delete(self, tx: Transaction, key: str) -> None:
        self._ensure_active(tx)
        tx.operations.append(("delete", key, None))

    def commit(self, tx: Transaction) -> list[LogRecord]:
        self._ensure_active(tx)

        before = self.engine.snapshot()
        records: list[LogRecord] = []

        try:
            for operation, key, value in tx.operations:
                if operation == "put":
                    self.engine.write(key, value)
                else:
                    self.engine.delete(key)

                record = LogRecord(
                    self._next_lsn,
                    tx.transaction_id,
                    operation,
                    key,
                    copy.deepcopy(value),
                )
                self._next_lsn += 1
                records.append(record)

            self.wal.extend(records)
            tx.state = TransactionState.COMMITTED
            return records
        except Exception:
            self.engine.restore(before)
            raise

    def rollback(self, tx: Transaction) -> None:
        self._ensure_active(tx)
        tx.operations.clear()
        tx.state = TransactionState.ROLLED_BACK

    @staticmethod
    def _ensure_active(tx: Transaction) -> None:
        if tx.state is not TransactionState.ACTIVE:
            raise TransactionError(
                f"Transaction {tx.transaction_id} is {tx.state.value}."
            )


class ReplicationNode:
    def __init__(self, name: str, role: ReplicationRole) -> None:
        self.name = name
        self.role = role
        self.engine = StorageEngine()
        self.applied_lsn = 0
        self.available = True

    def apply(self, record: LogRecord) -> None:
        if not self.available:
            raise ReplicationError(f"Node {self.name} is unavailable.")

        if record.lsn <= self.applied_lsn:
            return

        if record.operation == "put":
            self.engine.write(record.key, record.value)
        elif record.operation == "delete":
            self.engine.delete(record.key)
        else:
            raise ReplicationError(f"Unsupported WAL operation: {record.operation}")

        self.applied_lsn = record.lsn


class DatabaseCluster:
    """Primary/replica cluster with synchronous-style replication simulation."""

    def __init__(self, primary_name: str) -> None:
        self.primary = ReplicationNode(primary_name, ReplicationRole.PRIMARY)
        self.replicas: list[ReplicationNode] = []

    def add_replica(self, name: str) -> ReplicationNode:
        replica = ReplicationNode(name, ReplicationRole.REPLICA)
        self.replicas.append(replica)
        return replica

    def replicate(self, records: list[LogRecord]) -> dict[str, int]:
        replicated: dict[str, int] = {}

        for replica in self.replicas:
            if not replica.available:
                continue

            for record in records:
                replica.apply(record)

            replicated[replica.name] = replica.applied_lsn

        return replicated

    def failover(self) -> ReplicationNode:
        candidates = [
            node
            for node in self.replicas
            if node.available
        ]

        if not candidates:
            raise ReplicationError("No available replica can become primary.")

        promoted = max(candidates, key=lambda node: node.applied_lsn)
        promoted.role = ReplicationRole.PRIMARY
        self.primary.role = ReplicationRole.REPLICA
        self.primary = promoted
        return promoted

    def health(self) -> dict[str, Any]:
        return {
            "primary": {
                "name": self.primary.name,
                "lsn": self.primary.applied_lsn,
                "available": self.primary.available,
            },
            "replicas": [
                {
                    "name": node.name,
                    "lsn": node.applied_lsn,
                    "available": node.available,
                    "lag": self.primary.applied_lsn - node.applied_lsn,
                }
                for node in self.replicas
                if node is not self.primary
            ],
        }


class DatabaseService:
    def __init__(self, cluster: DatabaseCluster) -> None:
        self.cluster = cluster
        self.transactions = TransactionManager(cluster.primary.engine)

    def create_account(
        self,
        tx: Transaction,
        account_id: str,
        owner: str,
        balance: float,
    ) -> None:
        if balance < 0:
            raise ConstraintViolation("Account balance cannot be negative.")
        if not owner.strip():
            raise ConstraintViolation("Account owner is required.")

        existing = self.transactions.engine.read(f"account:{account_id}")
        if existing is not None:
            raise ConstraintViolation(f"Account exists: {account_id}")

        self.transactions.put(
            tx,
            f"account:{account_id}",
            {
                "account_id": account_id,
                "owner": owner,
                "balance": round(balance, 2),
            },
        )

    def transfer(
        self,
        tx: Transaction,
        source_id: str,
        target_id: str,
        amount: float,
    ) -> None:
        if source_id == target_id:
            raise ConstraintViolation("Source and target accounts must differ.")
        if amount <= 0:
            raise ConstraintViolation("Transfer amount must be positive.")

        source_key = f"account:{source_id}"
        target_key = f"account:{target_id}"
        source = self.transactions.engine.read(source_key)
        target = self.transactions.engine.read(target_key)

        if source is None or target is None:
            raise ConstraintViolation("Both accounts must exist.")
        if source["balance"] < amount:
            raise ConstraintViolation("Insufficient funds.")

        source["balance"] = round(source["balance"] - amount, 2)
        target["balance"] = round(target["balance"] + amount, 2)

        self.transactions.put(tx, source_key, source)
        self.transactions.put(tx, target_key, target)


def demonstrate_file_checkpoint() -> Path:
    """Creates a small durable metadata checkpoint using the standard library."""
    directory = Path(tempfile.mkdtemp(prefix="db-infra-"))
    checkpoint = directory / "checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "format": 1,
                "checkpoint_type": "logical",
                "description": "Database infrastructure learning checkpoint",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return checkpoint


def run_demo() -> None:
    cluster = DatabaseCluster("db-primary-01")
    replica_a = cluster.add_replica("db-replica-01")
    replica_b = cluster.add_replica("db-replica-02")

    service = DatabaseService(cluster)

    tx = service.transactions.begin("tx-1001")
    service.create_account(tx, "A100", "Operations", 1000.00)
    service.create_account(tx, "A200", "Analytics", 250.00)
    records = service.transactions.commit(tx)

    cluster.replicate(records)

    transfer_tx = service.transactions.begin("tx-1002")
    service.transfer(transfer_tx, "A100", "A200", 125.00)
    transfer_records = service.transactions.commit(transfer_tx)
    cluster.replicate(transfer_records)

    assert cluster.primary.engine.read("account:A100")["balance"] == 875.00
    assert replica_a.engine.read("account:A200")["balance"] == 375.00
    assert replica_b.applied_lsn == cluster.primary.applied_lsn

    failed_tx = service.transactions.begin("tx-1003")
    try:
        service.transfer(failed_tx, "A100", "A200", 5000.00)
    except ConstraintViolation:
        service.transactions.rollback(failed_tx)

    assert failed_tx.state is TransactionState.ROLLED_BACK

    replica_b.available = False
    health_before_failover = cluster.health()

    promoted = cluster.failover()
    assert promoted.name == replica_a.name
    assert promoted.engine.read("account:A100")["balance"] == 875.00

    checkpoint = demonstrate_file_checkpoint()

    print("Database infrastructure simulation")
    print("=" * 40)
    print("WAL records:", len(cluster.primary.name == "db-primary-01" and transfer_records or []))
    print("Primary:", promoted.name)
    print("Health before failover:", json.dumps(health_before_failover, indent=2))
    print("Promoted replica LSN:", promoted.applied_lsn)
    print("Account A100:", promoted.engine.read("account:A100"))
    print("Account A200:", promoted.engine.read("account:A200"))
    print("Checkpoint:", checkpoint)
    print("Storage pages:", promoted.engine.size())


if __name__ == "__main__":
    run_demo()
