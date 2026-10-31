from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
from typing import Any, Callable
import json
import time
import uuid


class Consistency(Enum):
    STRONG = "strong"
    EVENTUAL = "eventual"


class DatabaseError(Exception):
    pass


class ValidationError(DatabaseError):
    pass


class ConflictError(DatabaseError):
    pass


def validate_key(key: str) -> None:
    if not isinstance(key, str) or not key.strip():
        raise ValidationError("Key must be a non-empty string")
    if len(key) > 256:
        raise ValidationError("Key exceeds 256 characters")


@dataclass
class VersionedValue:
    value: Any
    version: int
    updated_at: float = field(default_factory=time.time)


class KeyValueStore:
    """In-memory key-value store with optional optimistic version checks."""

    def __init__(self) -> None:
        self._data: dict[str, VersionedValue] = {}

    def put(self, key: str, value: Any, expected_version: int | None = None) -> int:
        validate_key(key)
        current = self._data.get(key)

        if expected_version is not None:
            actual = current.version if current else 0
            if actual != expected_version:
                raise ConflictError(
                    f"Version conflict for {key}: expected {expected_version}, got {actual}"
                )

        version = (current.version + 1) if current else 1
        self._data[key] = VersionedValue(value, version)
        return version

    def get(self, key: str) -> VersionedValue | None:
        validate_key(key)
        return self._data.get(key)

    def delete(self, key: str) -> bool:
        validate_key(key)
        return self._data.pop(key, None) is not None


class DocumentStore:
    """Document store with indexed equality lookup and basic validation."""

    def __init__(self, required_fields: set[str]) -> None:
        self.required_fields = required_fields
        self.documents: dict[str, dict[str, Any]] = {}
        self.indexes: dict[str, dict[Any, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )

    def insert(self, document_id: str, document: dict[str, Any]) -> None:
        validate_key(document_id)

        missing = self.required_fields - document.keys()
        if missing:
            raise ValidationError(f"Missing required fields: {sorted(missing)}")

        if document_id in self.documents:
            raise ConflictError(f"Document {document_id} already exists")

        stored = json.loads(json.dumps(document))
        self.documents[document_id] = stored

        for field_name, value in stored.items():
            if isinstance(value, (str, int, float, bool)):
                self.indexes[field_name][value].add(document_id)

    def find_by(self, field_name: str, value: Any) -> list[dict[str, Any]]:
        ids = self.indexes[field_name].get(value, set())
        return [self.documents[i].copy() for i in ids]

    def get(self, document_id: str) -> dict[str, Any] | None:
        return self.documents.get(document_id)


class WideColumnStore:
    """
    Wide-column model:
    partition key -> clustering key -> sparse columns.
    """

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    def upsert(
        self,
        partition_key: str,
        clustering_key: str,
        columns: dict[str, Any],
    ) -> None:
        validate_key(partition_key)
        validate_key(clustering_key)

        existing = self.rows[partition_key].get(clustering_key, {})
        existing.update(columns)
        self.rows[partition_key][clustering_key] = existing

    def query_partition(self, partition_key: str) -> list[dict[str, Any]]:
        rows = self.rows.get(partition_key, {})
        return [
            {"clustering_key": ck, **columns}
            for ck, columns in sorted(rows.items())
        ]


class GraphStore:
    """Property graph with directed edges and adjacency-based traversal."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)

    def add_node(self, node_id: str, **properties: Any) -> None:
        validate_key(node_id)
        self.nodes.setdefault(node_id, {}).update(properties)

    def add_edge(
        self,
        source: str,
        target: str,
        relationship: str,
        **properties: Any,
    ) -> None:
        if source not in self.nodes or target not in self.nodes:
            raise ValidationError("Both graph endpoints must exist")
        self.edges[source].append((target, relationship, properties))

    def neighbors(
        self,
        source: str,
        relationship: str | None = None,
    ) -> list[str]:
        return [
            target
            for target, rel, _ in self.edges.get(source, [])
            if relationship is None or rel == relationship
        ]

    def shortest_path(self, source: str, target: str) -> list[str] | None:
        if source not in self.nodes or target not in self.nodes:
            return None

        queue = deque([(source, [source])])
        visited = {source}

        while queue:
            node, path = queue.popleft()
            if node == target:
                return path

            for neighbor in self.neighbors(node):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return None


@dataclass
class Replica:
    name: str
    data: dict[str, VersionedValue] = field(default_factory=dict)


class EventualKeyValueCluster:
    """
    Demonstrates eventual consistency.

    Writes are immediately applied to the leader and queued for replicas.
    A replica can temporarily return an older version until replication occurs.
    """

    def __init__(self, replica_names: list[str]) -> None:
        self.leader = Replica("leader")
        self.replicas = [Replica(name) for name in replica_names]
        self.pending: deque[tuple[str, VersionedValue]] = deque()

    def write(self, key: str, value: Any) -> int:
        validate_key(key)
        current = self.leader.data.get(key)
        version = current.version + 1 if current else 1
        item = VersionedValue(value, version)
        self.leader.data[key] = item

        for replica in self.replicas:
            self.pending.append((replica.name, item))

        return version

    def read(self, key: str, replica_name: str = "leader") -> VersionedValue | None:
        validate_key(key)

        if replica_name == "leader":
            return self.leader.data.get(key)

        for replica in self.replicas:
            if replica.name == replica_name:
                return replica.data.get(key)

        raise ValidationError(f"Unknown replica: {replica_name}")

    def replicate(self, max_operations: int | None = None) -> int:
        processed = 0

        while self.pending and (
            max_operations is None or processed < max_operations
        ):
            replica_name, value = self.pending.popleft()

            replica = next(r for r in self.replicas if r.name == replica_name)
            current = replica.data.get(
                next(
                    key
                    for key, item in self.leader.data.items()
                    if item.version == value.version and item.value == value.value
                ),
                None,
            )

            # The queue is ordered, so a newer value cannot be overwritten
            # by an older version.
            if current is None or value.version >= current.version:
                for key, leader_value in self.leader.data.items():
                    if leader_value is value:
                        replica.data[key] = value
                        break

            processed += 1

        return processed


def run_demo() -> None:
    print("=== NoSQL Infrastructure Case Study ===")

    kv = KeyValueStore()
    version = kv.put("session:user-1001", {"role": "engineer", "active": True})
    print("Key-value:", kv.get("session:user-1001"))
    try:
        kv.put(
            "session:user-1001",
            {"role": "admin"},
            expected_version=version - 1,
        )
    except ConflictError as exc:
        print("Expected conflict:", exc)

    documents = DocumentStore({"user_id", "name", "department"})
    documents.insert(
        "u1001",
        {
            "user_id": "u1001",
            "name": "Anita",
            "department": "security",
            "skills": ["python", "postgresql"],
        },
    )
    documents.insert(
        "u1002",
        {
            "user_id": "u1002",
            "name": "Ravi",
            "department": "engineering",
            "skills": ["cpp"],
        },
    )
    print("Documents:", documents.find_by("department", "security"))

    wide = WideColumnStore()
    wide.upsert("device-42", "2026-10-31T11:00:00Z", {"temperature": 31.2})
    wide.upsert("device-42", "2026-10-31T11:01:00Z", {"temperature": 31.4})
    wide.upsert("device-42", "2026-10-31T11:01:00Z", {"battery": 87})
    print("Wide-column:", wide.query_partition("device-42"))

    graph = GraphStore()
    for node in ("alice", "bob", "carol", "database"):
        graph.add_node(node, type="principal" if node != "database" else "resource")

    graph.add_edge("alice", "bob", "trusts")
    graph.add_edge("bob", "carol", "trusts")
    graph.add_edge("carol", "database", "accesses")
    print("Graph path:", graph.shortest_path("alice", "database"))

    cluster = EventualKeyValueCluster(["replica-a", "replica-b"])
    cluster.write("config:service-x", {"enabled": True})

    print("Leader read:", cluster.read("config:service-x"))
    print("Replica before replication:", cluster.read("config:service-x", "replica-a"))

    cluster.replicate()
    print("Replica after replication:", cluster.read("config:service-x", "replica-a"))

    try:
        documents.insert(
            "invalid",
            {"user_id": "invalid", "name": "Missing department"},
        )
    except ValidationError as exc:
        print("Validation failure:", exc)

    print("Security considerations:")
    print("- Validate keys and document structure at write boundaries.")
    print("- Apply authentication and authorization outside this in-memory model.")
    print("- Avoid storing secrets as ordinary document values.")
    print("- Use version checks for concurrent updates.")
    print("- Treat replica reads as potentially stale under eventual consistency.")

    print("Complexity:")
    print("- Key-value lookup: average O(1).")
    print("- Indexed document equality lookup: approximately O(k).")
    print("- Wide-column partition lookup: O(r log r) here because rows are sorted.")
    print("- Graph shortest path: O(V + E) for breadth-first traversal.")


if __name__ == "__main__":
    run_demo()
