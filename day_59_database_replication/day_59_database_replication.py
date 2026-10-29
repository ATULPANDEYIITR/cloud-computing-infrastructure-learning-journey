from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
import hashlib
import random
import time


class ReplicationMode(Enum):
    SYNCHRONOUS = "synchronous"
    ASYNCHRONOUS = "asynchronous"


class NodeRole(Enum):
    PRIMARY = "primary"
    REPLICA = "replica"


class ReplicaState(Enum):
    ONLINE = "online"
    LAGGING = "lagging"
    OFFLINE = "offline"


@dataclass(frozen=True)
class Change:
    sequence: int
    key: str
    value: Optional[str]
    checksum: str

    @staticmethod
    def create(sequence: int, key: str, value: Optional[str]) -> "Change":
        raw = f"{sequence}|{key}|{value}"
        checksum = hashlib.sha256(raw.encode()).hexdigest()
        return Change(sequence, key, value, checksum)


@dataclass
class Replica:
    name: str
    state: ReplicaState = ReplicaState.ONLINE
    applied_sequence: int = 0
    data: Dict[str, str] = field(default_factory=dict)
    received_log: List[Change] = field(default_factory=list)

    def receive(self, change: Change) -> None:
        if self.state == ReplicaState.OFFLINE:
            raise RuntimeError(f"Replica {self.name} is offline")

        expected = self.applied_sequence + 1
        if change.sequence != expected:
            raise ValueError(
                f"{self.name}: expected sequence {expected}, "
                f"received {change.sequence}"
            )

        raw = f"{change.sequence}|{change.key}|{change.value}"
        if hashlib.sha256(raw.encode()).hexdigest() != change.checksum:
            raise ValueError(f"{self.name}: checksum validation failed")

        self.received_log.append(change)

    def apply_pending(self) -> None:
        if self.state == ReplicaState.OFFLINE:
            return

        while self.received_log:
            change = self.received_log.pop(0)
            if change.value is None:
                self.data.pop(change.key, None)
            else:
                self.data[change.key] = change.value
            self.applied_sequence = change.sequence

        self.state = ReplicaState.ONLINE


@dataclass
class Primary:
    name: str
    sequence: int = 0
    data: Dict[str, str] = field(default_factory=dict)
    log: List[Change] = field(default_factory=list)

    def write(self, key: str, value: Optional[str]) -> Change:
        if not key or len(key) > 128:
            raise ValueError("Key must contain 1-128 characters")

        self.sequence += 1
        change = Change.create(self.sequence, key, value)

        if value is None:
            self.data.pop(key, None)
        else:
            self.data[key] = value

        self.log.append(change)
        return change


class ReplicatedDatabase:
    """
    Small in-memory model of primary-replica replication.

    Synchronous mode waits for every configured synchronous replica to apply
    the change before acknowledging the client.

    Asynchronous mode acknowledges after the primary commits locally and
    places the change into replica receive queues.
    """

    def __init__(
        self,
        primary: Primary,
        replicas: List[Replica],
        mode: ReplicationMode,
        synchronous_quorum: Optional[int] = None,
    ):
        self.primary = primary
        self.replicas = replicas
        self.mode = mode

        online = sum(r.state != ReplicaState.OFFLINE for r in replicas)
        self.synchronous_quorum = (
            synchronous_quorum if synchronous_quorum is not None else online
        )

        if self.synchronous_quorum < 1 and mode == ReplicationMode.SYNCHRONOUS:
            raise ValueError("Synchronous replication requires at least one replica")

    def write(self, key: str, value: Optional[str]) -> Tuple[bool, str]:
        change = self.primary.write(key, value)

        acknowledgements = 0
        failures = []

        for replica in self.replicas:
            if replica.state == ReplicaState.OFFLINE:
                failures.append(replica.name)
                continue

            try:
                replica.receive(change)

                if self.mode == ReplicationMode.SYNCHRONOUS:
                    replica.apply_pending()

                acknowledgements += 1
            except (RuntimeError, ValueError) as exc:
                failures.append(str(exc))

        if self.mode == ReplicationMode.SYNCHRONOUS:
            if acknowledgements < self.synchronous_quorum:
                # A real database would normally roll back the transaction
                # before exposing it. This simulator explicitly models that
                # failure by marking the primary transaction uncertain.
                return (
                    False,
                    f"Write sequence {change.sequence} lacks required "
                    f"acknowledgements: {acknowledgements}/"
                    f"{self.synchronous_quorum}; failures={failures}",
                )

        return (
            True,
            f"Committed sequence {change.sequence}; "
            f"replica acknowledgements={acknowledgements}; failures={failures}",
        )

    def drain_async_replication(self) -> None:
        for replica in self.replicas:
            replica.apply_pending()

    def read_from_primary(self, key: str) -> Optional[str]:
        return self.primary.data.get(key)

    def read_from_replica(self, replica_name: str, key: str) -> Optional[str]:
        replica = self._find_replica(replica_name)

        if replica.state == ReplicaState.OFFLINE:
            raise RuntimeError(f"Replica {replica_name} is offline")

        return replica.data.get(key)

    def replication_lag(self, replica_name: str) -> int:
        replica = self._find_replica(replica_name)
        return self.primary.sequence - replica.applied_sequence

    def _find_replica(self, name: str) -> Replica:
        for replica in self.replicas:
            if replica.name == name:
                return replica
        raise KeyError(f"Unknown replica: {name}")

    def health_report(self) -> List[dict]:
        return [
            {
                "name": r.name,
                "state": r.state.value,
                "role": NodeRole.REPLICA.value,
                "applied_sequence": r.applied_sequence,
                "lag": self.primary.sequence - r.applied_sequence,
            }
            for r in self.replicas
        ]


def demonstrate_asynchronous_replication() -> None:
    primary = Primary("db-primary")
    replicas = [Replica("read-1"), Replica("read-2")]

    database = ReplicatedDatabase(
        primary,
        replicas,
        ReplicationMode.ASYNCHRONOUS,
    )

    ok, message = database.write("customer:100", "ACTIVE")
    assert ok
    print(message)

    # The primary has the newest value immediately. Replicas have not applied
    # their queued changes yet, so they can temporarily return stale data.
    print("Primary:", database.read_from_primary("customer:100"))
    print("Read replica before catch-up:", database.read_from_replica("read-1", "customer:100"))

    database.drain_async_replication()

    print("Read replica after catch-up:", database.read_from_replica("read-1", "customer:100"))
    print("Health:", database.health_report())


def demonstrate_synchronous_failure() -> None:
    primary = Primary("db-primary")
    replicas = [
        Replica("sync-1"),
        Replica("sync-2", state=ReplicaState.OFFLINE),
    ]

    database = ReplicatedDatabase(
        primary,
        replicas,
        ReplicationMode.SYNCHRONOUS,
        synchronous_quorum=2,
    )

    ok, message = database.write("order:9001", "PAID")
    print("Synchronous result:", ok, message)
    print("Primary sequence:", primary.sequence)
    print("Replica health:", database.health_report())


def demonstrate_recovery() -> None:
    primary = Primary("db-primary")
    replica = Replica("read-replica")

    database = ReplicatedDatabase(
        primary,
        [replica],
        ReplicationMode.ASYNCHRONOUS,
    )

    database.write("inventory:42", "20")
    database.write("inventory:42", "18")

    print("Lag before recovery:", database.replication_lag("read-replica"))

    database.drain_async_replication()

    assert database.read_from_replica("read-replica", "inventory:42") == "18"
    assert database.replication_lag("read-replica") == 0

    print("Lag after recovery:", database.replication_lag("read-replica"))


def benchmark_hash_validation() -> None:
    start = time.perf_counter()

    for sequence in range(1, 1001):
        Change.create(sequence, f"key-{sequence}", str(random.randint(1, 100000)))

    elapsed = time.perf_counter() - start
    print(f"Created and checksummed 1000 changes in {elapsed:.6f}s")


def main() -> None:
    print("=== Asynchronous replication ===")
    demonstrate_asynchronous_replication()

    print("\n=== Synchronous replication failure ===")
    demonstrate_synchronous_failure()

    print("\n=== Replica recovery ===")
    demonstrate_recovery()

    print("\n=== Change-log checksum benchmark ===")
    benchmark_hash_validation()


if __name__ == "__main__":
    main()
