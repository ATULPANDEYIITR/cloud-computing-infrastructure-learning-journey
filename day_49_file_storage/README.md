# File Storage: Shared Storage, Network File Systems, and Distributed File Systems

## Scope

File storage is concerned with preserving named byte sequences together with metadata such as size, version, timestamps, checksums, and directory or namespace information. Shared storage extends that model so multiple clients can access common data. Network file systems expose file-oriented operations across a network, while distributed file systems spread file data across multiple storage nodes and use mechanisms such as chunking and replication to support scale and fault tolerance.

These areas are related but are not interchangeable.

A local file store can provide a filesystem namespace without involving a network. A network file system makes that namespace accessible through remote file operations. A distributed file system goes further by distributing the physical representation of files across multiple machines while presenting a logical storage namespace to clients.

The implementations in this project use the same general storage problem from different technical perspectives:

| Implementation | Main perspective |
|---|---|
| Python | Progressive storage abstraction, integrity validation, quota enforcement, network access, chunking, replication, and failure recovery |
| JavaScript | Asynchronous Node.js storage operations, event-driven notifications, path validation, and distributed chunk recovery |
| C++ | Repository-style distributed storage case study with explicit node state, replica placement, failure handling, and recovery |
| Java | Enterprise-oriented storage service with explicit policies, immutable records, typed storage models, validation, and integrity enforcement |
| PostgreSQL | Relational representation of logical files, physical nodes, chunks, replicas, node state, usage, and access events |

## Core Distinctions

### File Storage

A file storage system organizes data around files and directories. A file has a logical pathname and a byte sequence, while metadata records attributes such as size, modification time, version, permissions, or integrity information.

The Python implementation represents this distinction through `FileRecord`. The actual bytes reside under a storage root while metadata is maintained separately. The checksum allows the implementation to detect a mismatch between the expected content and the bytes read from disk.

Quota enforcement is also placed in the storage abstraction. Before replacing a file, the previous file size is removed from the quota calculation so an update does not incorrectly count the old and new versions simultaneously.

Path validation is part of the storage boundary rather than an assumption made by callers. Relative paths containing traversal such as `../outside.txt` are rejected before filesystem access occurs.

### Shared Storage

Shared storage means that multiple users, processes, or applications can access common data rather than maintaining independent private copies.

The shared namespace is important because the pathname becomes a logical identifier. For example, `/engineering/design.txt` can identify a shared document independently of the physical disk location containing its bytes.

Sharing creates operational concerns that do not arise in exactly the same form for isolated local files:

- Multiple clients can attempt access at the same time.
- Storage failures can affect many consumers.
- Permissions and isolation become part of the storage boundary.
- Latency may become visible to applications.
- A centralized storage endpoint can become an availability bottleneck.
- Metadata and data durability must be considered separately.

The examples keep the namespace simple so that the storage mechanics remain visible.

## Network File Systems

A network file system provides file-oriented access to data managed somewhere other than the local client machine.

The important abstraction is that the client operates on a remote file namespace instead of explicitly managing the remote disk. In the Python implementation, `NetworkFileSystem` wraps a storage backend and introduces simulated network latency. The JavaScript implementation uses `NetworkFileClient` to represent asynchronous remote operations.

The network layer changes the failure model.

A local read might primarily fail because the local path or device is unavailable. A network read can also fail because of connectivity, remote server failure, authentication, transport delays, stale client state, or server-side resource exhaustion.

Latency matters because a remote file operation is no longer equivalent to an in-memory operation. The JavaScript version makes this visible with asynchronous methods and an artificial delay. The delay is deliberately represented as asynchronous work rather than blocking the JavaScript event loop.

## Distributed File Systems

A distributed file system distributes storage responsibilities across multiple nodes.

The key mechanisms demonstrated by the implementations are **chunking** and **replication**.

Chunking divides a file into smaller independently managed pieces. The Python implementation uses a fixed chunk size and records each chunk's checksum and replica placement. The JavaScript and C++ implementations use the same general idea but organize the implementation differently.

Replication stores multiple physical copies of a chunk on different storage nodes. If one node fails, another replica can supply the missing chunk.

Replication therefore provides fault tolerance, but it has a cost. A replication factor of two means the physical storage requirement is approximately twice the logical data volume before accounting for metadata and other overheads. Higher replication improves tolerance to failures but consumes more capacity.

## Logical Namespace Versus Physical Placement

A distributed file system separates two concepts:

```text
Logical namespace
        |
        v
/datasets/events.bin
        |
        v
+------------------------------+
| File metadata                |
| size                         |
| checksum                     |
| chunk mapping                |
+------------------------------+
        |
        +-------- chunk 0 ------> storage-a
        |                       storage-b
        |
        +-------- chunk 1 ------> storage-b
                                storage-c
