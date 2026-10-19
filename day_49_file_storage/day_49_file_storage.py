from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional


class StorageError(Exception):
    """Base exception for storage failures."""


class QuotaExceeded(StorageError):
    """Raised when a storage allocation cannot accept more data."""


class FileIntegrityError(StorageError):
    """Raised when stored content does not match its recorded checksum."""


@dataclass
class FileRecord:
    path: str
    size: int
    checksum: str
    version: int = 1
    modified_at: float = field(default_factory=time.time)


class LocalSharedStorage:
    """
    A local filesystem abstraction representing a shared file store.

    The abstraction deliberately keeps metadata separate from file contents.
    This mirrors an important storage-system distinction: data blocks/files are
    stored separately from metadata describing names, sizes, versions, and
    integrity information.
    """

    def __init__(self, root: Path, quota_bytes: Optional[int] = None):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.quota_bytes = quota_bytes
        self.metadata: Dict[str, FileRecord] = {}

    def _safe_path(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()

        # Prevent path traversal such as ../../secret.txt.
        if candidate != self.root and self.root not in candidate.parents:
            raise StorageError("Path escapes the storage root")

        return candidate

    def _used_bytes(self) -> int:
        return sum(record.size for record in self.metadata.values())

    @staticmethod
    def _checksum(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def write(self, relative_path: str, data: bytes) -> FileRecord:
        target = self._safe_path(relative_path)
        old_size = self.metadata.get(relative_path, FileRecord("", 0, "")).size

        required = self._used_bytes() - old_size + len(data)
        if self.quota_bytes is not None and required > self.quota_bytes:
            raise QuotaExceeded(
                f"Quota exceeded: requested {required} bytes, "
                f"limit is {self.quota_bytes}"
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

        old = self.metadata.get(relative_path)
        record = FileRecord(
            path=relative_path,
            size=len(data),
            checksum=self._checksum(data),
            version=old.version + 1 if old else 1,
        )
        self.metadata[relative_path] = record
        return record

    def read(self, relative_path: str) -> bytes:
        if relative_path not in self.metadata:
            raise FileNotFoundError(relative_path)

        data = self._safe_path(relative_path).read_bytes()
        expected = self.metadata[relative_path].checksum

        if self._checksum(data) != expected:
            raise FileIntegrityError(relative_path)

        return data

    def delete(self, relative_path: str) -> None:
        if relative_path not in self.metadata:
            raise FileNotFoundError(relative_path)

        target = self._safe_path(relative_path)
        if target.exists():
            target.unlink()

        del self.metadata[relative_path]

    def list_files(self) -> List[FileRecord]:
        return sorted(self.metadata.values(), key=lambda item: item.path)


class NetworkFileSystem:
    """
    Models a network file system from a client perspective.

    A network filesystem presents a remote namespace through file-oriented
    operations. The client normally does not need to know which storage server
    or disk contains the bytes.
    """

    def __init__(self, backend: LocalSharedStorage, latency_ms: int = 15):
        self.backend = backend
        self.latency_ms = latency_ms

    def _network_delay(self) -> None:
        time.sleep(self.latency_ms / 1000)

    def write_remote(self, path: str, data: bytes) -> FileRecord:
        self._network_delay()
        return self.backend.write(path, data)

    def read_remote(self, path: str) -> bytes:
        self._network_delay()
        return self.backend.read(path)

    def delete_remote(self, path: str) -> None:
        self._network_delay()
        self.backend.delete(path)


class DistributedFileSystem:
    """
    A small distributed-storage simulation.

    Files are split into chunks and replicated across logical storage nodes.
    Metadata records where each chunk is expected to exist.

    This is intentionally different from a network filesystem abstraction:
    the distributed layer explicitly reasons about partitioning, replication,
    node failure, reconstruction, and consistency.
    """

    def __init__(self, node_names: Iterable[str], replication_factor: int = 2):
        self.nodes: Dict[str, Dict[str, bytes]] = {
            name: {} for name in node_names
        }
        self.replication_factor = replication_factor
        self.chunk_size = 8
        self.metadata: Dict[str, List[dict]] = {}

        if not self.nodes:
            raise ValueError("At least one storage node is required")
        if not 1 <= replication_factor <= len(self.nodes):
            raise ValueError("Invalid replication factor")

    def _select_nodes(self, chunk_index: int) -> List[str]:
        names = list(self.nodes)
        start = chunk_index % len(names)
        ordered = names[start:] + names[:start]
        return ordered[: self.replication_factor]

    def put(self, path: str, data: bytes) -> None:
        chunks = [
            data[offset : offset + self.chunk_size]
            for offset in range(0, len(data), self.chunk_size)
        ]

        # Empty files still require namespace metadata.
        if not chunks:
            chunks = [b""]

        entries = []

        for index, chunk in enumerate(chunks):
            checksum = hashlib.sha256(chunk).hexdigest()
            replicas = self._select_nodes(index)

            for node in replicas:
                self.nodes[node][f"{path}:{index}"] = chunk

            entries.append(
                {
                    "index": index,
                    "checksum": checksum,
                    "replicas": replicas,
                }
            )

        self.metadata[path] = entries

    def _available_replica(self, chunk_key: str, replicas: List[str]) -> Optional[bytes]:
        for node in replicas:
            if node not in self.nodes:
                continue
            if chunk_key in self.nodes[node]:
                return self.nodes[node][chunk_key]
        return None

    def get(self, path: str) -> bytes:
        if path not in self.metadata:
            raise FileNotFoundError(path)

        result = bytearray()

        for entry in self.metadata[path]:
            key = f"{path}:{entry['index']}"
            chunk = self._available_replica(key, entry["replicas"])

            if chunk is None:
                raise StorageError(
                    f"Chunk {entry['index']} is unavailable for {path}"
                )

            if hashlib.sha256(chunk).hexdigest() != entry["checksum"]:
                raise FileIntegrityError(
                    f"Corrupted chunk {entry['index']} in {path}"
                )

            result.extend(chunk)

        return bytes(result)

    def fail_node(self, node: str) -> None:
        if node not in self.nodes:
            raise KeyError(node)

        del self.nodes[node]

    def repair(self) -> List[str]:
        repaired = []

        for path, entries in self.metadata.items():
            for entry in entries:
                key = f"{path}:{entry['index']}"
                if not any(
                    node in self.nodes and key in self.nodes[node]
                    for node in entry["replicas"]
                ):
                    continue

                source = self._available_replica(key, entry["replicas"])
                if source is None:
                    continue

                surviving = [
                    node for node in entry["replicas"] if node in self.nodes
                ]

                candidates = [
                    node for node in self.nodes if node not in surviving
                ]

                for node in candidates:
                    self.nodes[node][key] = source
                    repaired.append(f"{path}:{entry['index']}->{node}")
                    break

        return repaired

    def placement_report(self, path: str) -> List[dict]:
        if path not in self.metadata:
            raise FileNotFoundError(path)

        return [
            {
                "chunk": entry["index"],
                "checksum": entry["checksum"][:12],
                "configured_replicas": entry["replicas"],
                "available_replicas": [
                    node
                    for node in entry["replicas"]
                    if node in self.nodes
                    and f"{path}:{entry['index']}" in self.nodes[node]
                ],
            }
            for entry in self.metadata[path]
        ]


def demonstrate_local_storage() -> None:
    print("\n=== Local File Storage ===")

    with tempfile.TemporaryDirectory() as directory:
        store = LocalSharedStorage(Path(directory), quota_bytes=4096)

        record = store.write(
            "reports/quarterly.txt",
            b"Revenue increased while infrastructure costs remained controlled.",
        )

        print("Stored:", record.path)
        print("Version:", record.version)
        print("Checksum:", record.checksum[:16])
        print("Read:", store.read("reports/quarterly.txt").decode())

        try:
            store.read("../outside.txt")
        except (FileNotFoundError, StorageError) as exc:
            print("Rejected unsafe access:", exc)


def demonstrate_network_storage() -> None:
    print("\n=== Network File System ===")

    with tempfile.TemporaryDirectory() as directory:
        backend = LocalSharedStorage(Path(directory))
        network = NetworkFileSystem(backend, latency_ms=2)

        network.write_remote(
            "shared/team/design.txt",
            b"Centralized namespace exposed through network file operations.",
        )

        print(network.read_remote("shared/team/design.txt").decode())

        network.delete_remote("shared/team/design.txt")

        try:
            network.read_remote("shared/team/design.txt")
        except FileNotFoundError:
            print("Remote deletion confirmed.")


def demonstrate_distributed_storage() -> None:
    print("\n=== Distributed File System ===")

    dfs = DistributedFileSystem(
        ["node-a", "node-b", "node-c"],
        replication_factor=2,
    )

    content = (
        b"Distributed storage partitions large files into chunks and "
        b"keeps replicas so individual node failures do not necessarily "
        b"make the complete file unavailable."
    )

    dfs.put("datasets/events.bin", content)

    print("Initial placement:")
    print(json.dumps(dfs.placement_report("datasets/events.bin"), indent=2))

    expected = dfs.get("datasets/events.bin")
    print("Initial integrity:", expected == content)

    dfs.fail_node("node-a")
    print("\nAfter node-a failure:")
    print(json.dumps(dfs.placement_report("datasets/events.bin"), indent=2))
    print("File still readable:", dfs.get("datasets/events.bin") == content)

    repaired = dfs.repair()
    print("Repair actions:", repaired)


def compare_models() -> None:
    print("\n=== Storage Model Distinction ===")
    models = {
        "File storage": {
            "namespace": "Filesystem hierarchy",
            "location": "Usually a local device or mounted storage",
            "main concern": "Files, directories, metadata, permissions",
        },
        "Network file system": {
            "namespace": "Remote filesystem exposed to clients",
            "location": "Managed by remote file servers",
            "main concern": "Remote access, sharing, caching, availability",
        },
        "Distributed file system": {
            "namespace": "Distributed logical filesystem",
            "location": "Multiple storage nodes",
            "main concern": "Partitioning, replication, failure recovery, scale",
        },
    }

    for name, details in models.items():
        print(f"\n{name}")
        for key, value in details.items():
            print(f"  {key}: {value}")


def main() -> None:
    demonstrate_local_storage()
    demonstrate_network_storage()
    demonstrate_distributed_storage()
    compare_models()


if __name__ == "__main__":
    main()
