# File Storage: Shared Storage, Network File Systems, and Distributed File Systems

## Scope

File storage preserves named sequences of bytes together with metadata such as size, version, timestamps, checksums, and directory or namespace information. Shared storage extends this model so multiple users, processes, or applications can access common data. Network file systems expose file-oriented operations across a network, while distributed file systems distribute physical data across multiple storage nodes to support scalability, replication, and fault tolerance.

These concepts are related but not interchangeable.

A local file store provides a filesystem namespace without requiring network access. A network file system makes a file namespace accessible through remote operations. A distributed file system distributes storage responsibilities across multiple machines while presenting a logical namespace to clients.

The implementations in this project examine the same storage problem from different technical perspectives.

| Implementation | Main perspective |
|---|---|
| Python | Storage abstractions, integrity validation, quota enforcement, network access, chunking, replication, and recovery |
| JavaScript | Asynchronous Node.js storage operations, event-driven notifications, path validation, and distributed chunk recovery |
| C++ | Distributed storage case study with explicit node states, replica placement, failure handling, and recovery |
| Java | Enterprise storage service with typed models, immutable records, storage policies, validation, and integrity enforcement |
| PostgreSQL | Relational representation of logical files, physical nodes, chunks, replicas, node states, capacity, and access events |

## Core Distinctions

### File Storage

A file storage system organizes data around files and directories. Each file has a logical pathname and a byte sequence, while metadata records attributes such as size, modification time, version, permissions, and integrity information.

The Python implementation represents this distinction through `FileRecord`. The actual bytes reside under a storage root, while metadata is maintained separately. A checksum allows the implementation to detect when the bytes read from disk do not match the expected content.

Quota enforcement is part of the storage abstraction. Before replacing a file, the previous file size is excluded from the usage calculation so that an update does not count both the old and new versions simultaneously.

Path validation is enforced at the storage boundary. Relative paths containing traversal, such as `../outside.txt`, must be rejected before filesystem access occurs.

### Shared Storage

Shared storage allows multiple users, processes, or applications to access common data rather than maintaining independent private copies.

The shared namespace provides a logical identifier for the data. For example, `/engineering/design.txt` can identify a shared document independently of the physical disk location containing its bytes.

Sharing introduces operational concerns:

- Multiple clients can attempt to access or modify the same file concurrently.
- A centralized storage endpoint can become an availability bottleneck.
- Permissions and tenant isolation become part of the storage boundary.
- Network or server latency can affect application response times.
- Metadata and data durability must be considered separately.
- Concurrent writes require explicit consistency and conflict-handling rules.

The examples keep the namespace simple so that the underlying storage mechanisms remain visible.

## Network File Systems

A network file system provides file-oriented access to data managed somewhere other than the local client machine.

The client operates on a remote file namespace instead of explicitly managing the remote disk. In the Python implementation, `NetworkFileSystem` wraps a storage backend and introduces simulated network latency. The JavaScript implementation uses `NetworkFileClient` to represent asynchronous remote operations.

The network layer changes the failure model.

A local read can fail because the path or device is unavailable. A network read can also fail because of connectivity problems, remote server failure, authentication errors, transport delays, stale client state, or server-side resource exhaustion.

Latency matters because a remote file operation is not equivalent to an in-memory operation. The JavaScript version makes this visible through asynchronous methods and artificial delays. These delays are awaited rather than implemented with a blocking sleep, allowing the JavaScript event loop to continue processing other work.

Real network file systems, such as NFS and SMB, implement additional protocol-level behavior involving authentication, file handles, caching, locking, and consistency. A simulated network wrapper demonstrates the remote-access boundary but does not implement those protocols.

## Distributed File Systems

A distributed file system distributes storage responsibilities across multiple nodes.

Two important mechanisms are **chunking** and **replication**.

Chunking divides a file into smaller, independently managed pieces. The Python implementation uses a fixed chunk size and records each chunk's checksum and replica placement. The JavaScript and C++ implementations use the same general concept but organize their storage logic differently.

Replication stores multiple physical copies of a chunk on different storage nodes. If one node fails, another replica may supply the missing data.

Replication improves availability at a cost. A replication factor of two requires approximately twice the logical data capacity before accounting for metadata, temporary repair copies, and other overheads.

Replication alone does not guarantee durability. If every replica of a chunk is lost, that chunk cannot be reconstructed unless another recovery source exists, such as a backup or erasure-coded representation.

## Logical Namespace Versus Physical Placement

A distributed file system separates the logical file identifier from the physical placement of its bytes.

    Logical namespace
            |
            v
    /datasets/events.bin
            |
            v
    +------------------------------+
    | File metadata                |
    | Size                         |
    | Checksum                     |
    | Version                      |
    | Chunk mapping                |
    +------------------------------+
            |
            +-------- Chunk 0 ------> Storage A
            |                         Storage B
            |
            +-------- Chunk 1 ------> Storage B
                                      Storage C

The client cares about the logical path and the reconstructed file. The storage system manages the placement of individual chunks and replicas.

This separation permits physical placement to change without requiring clients to change the logical pathname.

A production implementation must also ensure that metadata updates and physical writes are coordinated. Publishing a file as complete before all required chunks and replicas are safely recorded can expose incomplete data.

## Integrity and Checksums

Successful retrieval does not necessarily mean that the retrieved bytes are trustworthy.

The implementations therefore calculate checksums. The Python implementation uses SHA-256, the JavaScript implementation uses Node.js `crypto`, and Java uses `MessageDigest` with SHA-256. The C++ case study uses a standard-library hash mechanism to illustrate the integrity workflow without introducing an external cryptographic dependency.

A checksum detects content that differs from the expected representation. It does not independently provide confidentiality, authorization, availability, or authenticity.

For security-sensitive production systems, cryptographic hashes should be selected according to the threat model. A cryptographic digest such as SHA-256 is appropriate for detecting accidental corruption and verifying content against a trusted expected digest. If an attacker can modify both the file and its recorded digest, a plain checksum is insufficient to establish authenticity.

Chunk-level checksums also improve fault diagnosis. A corrupted chunk can be identified without treating the entire reconstructed file as an unexplained failure.

## Python Implementation

The Python program begins with a local storage abstraction and progresses toward distributed behavior.

`LocalSharedStorage` provides a controlled storage root, safe relative-path resolution, quota accounting, file writes and reads, version tracking, SHA-256 checksums, integrity validation, and deletion.

The separation between `_safe_path`, quota calculation, and checksum validation demonstrates how storage policies can be enforced at a common boundary instead of being duplicated by every caller.

`NetworkFileSystem` wraps the local backend and introduces a network-style interface. The artificial latency makes remote access costs visible without requiring a real network server.

`DistributedFileSystem` changes the physical storage model. Files are divided into chunks, each chunk receives a checksum, and the placement algorithm selects replica nodes using a deterministic rotation. A node failure removes a physical location from the active topology while leaving surviving replicas available.

The `repair` operation illustrates an important distributed-storage responsibility: replication is not the same as repair. A system can remain readable after a node failure while operating with less redundancy than its policy requires. Repair restores redundancy by copying a surviving chunk to another eligible node.

The Python implementation also illustrates why capacity accounting must distinguish logical data size from physical usage. A file with multiple replicas consumes more physical storage than its logical byte length suggests.

## JavaScript Implementation

The JavaScript implementation emphasizes asynchronous and event-driven behavior.

`LocalFileStore` uses Node.js `fs/promises`, so file operations return promises rather than blocking the JavaScript event loop. Storage events such as `stored`, `read`, and `deleted` are emitted through `EventEmitter`.

This allows monitoring, logging, audit recording, and metrics collection to subscribe to storage lifecycle events without embedding those responsibilities directly into the storage methods.

`NetworkFileClient` adds asynchronous network-style delays and emits events for remote operations. The implementation demonstrates the difference between awaiting an I/O operation and blocking the execution thread.

`DistributedStore` uses `Buffer` objects for binary data, divides content into chunks, records replica placement, and recovers a chunk from any surviving replica. Node failure is modeled by removing a storage node from the active node map.

The implementation also demonstrates a security boundary through explicit path normalization and traversal rejection. Production path validation must account for platform-specific separators, symbolic links, and race conditions between path validation and file access.

## C++ Distributed Storage Case Study

The C++ program models a distributed file system as a small storage service.

`StorageNode` owns physical chunks and maintains an explicit `NodeState`. A failed node refuses new writes and does not satisfy reads.

`DistributedFileSystem` owns the logical file metadata and storage nodes. Its `store` operation divides a file into fixed-size chunks and selects replica nodes. Chunk records contain the replica locations and an integrity value.

The read operation is replica-aware. It examines configured replica locations until it finds an available copy, validates the content, and appends the chunk to the reconstructed result.

A simplified placement model looks like this:

    Logical file
        |
        +-- Chunk 0 --> Node A, Node B
        +-- Chunk 1 --> Node B, Node C
        +-- Chunk 2 --> Node C, Node D

If Node A fails, Chunk 0 can still be recovered from Node B. If another failure removes the remaining replica for a required chunk, the complete logical file becomes unreadable.

This exposes an important distributed-storage property: file availability depends on replica placement and the location of failures, not merely on the total number of healthy nodes.

The implementation uses `std::map`, `std::unordered_map`, vectors, explicit state types, and exception-based error handling. These structures provide clear ownership of metadata and physical chunk data without requiring an external framework.

The standard-library hash mechanism used in the case study is not a cryptographic integrity guarantee. A production implementation should replace it with a suitable cryptographic digest and compare values against metadata protected by an appropriate trust boundary.

## Java Enterprise Storage Model

The Java program represents storage behavior through explicit domain types.

`StorageType` distinguishes local file storage, network file systems, and distributed file systems. `StoragePolicy` captures constraints such as quota, replication factor, and checksum enforcement.

The policy constructor validates an important invariant: distributed storage cannot be configured with a replication factor below two in this model.

Java records represent immutable policy and metadata values. Immutability prevents accidental changes to policy information after construction and makes service behavior easier to reason about.

`StorageNode` owns physical chunks and explicitly transitions between `ONLINE` and `FAILED`. The storage service determines whether the available node population can satisfy the configured replication policy.

The distributed read operation reconstructs the file from chunks and verifies the final content against the stored SHA-256 value. Failure states are represented with exceptions rather than silently returning incomplete data.

The implementation models a service boundary rather than simply exposing collection operations. Storage policy determines which configurations are legal, while the storage service enforces those rules during writes and reads.

A production enterprise service would also need authorization, durable metadata transactions, idempotent retry behavior, observability, and recovery procedures for partially completed writes.

## PostgreSQL Data Model

The SQL implementation treats storage metadata as relational data.

`repositories` represents logical storage environments. Each repository specifies whether it represents local file storage, a network file system, or a distributed file system.

`storage_nodes` represents physical storage endpoints. Node state is explicit, allowing queries to distinguish online, failed, and maintenance nodes.

`files` represents the logical namespace. A unique constraint on `(repository_id, logical_path)` prevents two metadata rows from claiming the same logical pathname within one repository.

`file_chunks` separates large files into independently addressable units.

`chunk_replicas` establishes the many-to-many relationship between chunks and storage nodes. This is the relational representation of distributed replication.

The relationship is:

    repositories
        |
        +---- files
        |       |
        |       +---- file_chunks
        |                |
        |                +---- chunk_replicas ---- storage_nodes
        |
        +---- storage_nodes

Foreign keys preserve referential integrity. Check constraints enforce valid sizes and node usage. Replicas cannot reference nonexistent chunks or nodes, and a chunk cannot have the same node recorded twice.

Indexes support common access patterns, including locating files within a repository, finding chunks for a file, locating replicas on a node, and inspecting recent access events.

## Database-Level Integrity

The SQL function `record_node_usage` locks the selected node and validates its capacity before applying a usage change.

This matters because capacity is a shared resource. If two transactions independently read the same available capacity and both allocate it, application-only checks can produce an invalid final state.

The function uses row locking so that the usage calculation and update operate against a stable row. Transactions should also define how usage changes correspond to replica creation, deletion, and repair so that metadata remains consistent with actual physical storage.

The schema enforces important invariants directly:

- File and chunk sizes cannot be negative.
- Node capacity must be positive.
- Node usage cannot exceed capacity.
- Replicas must reference existing chunks and nodes.
- A chunk cannot have duplicate replica entries for the same node.
- Logical paths are unique within a repository.

These constraints place data invariants close to the data instead of relying exclusively on every application client to implement them correctly.

Relational metadata does not itself guarantee that the physical bytes exist on a storage device. Operational reconciliation is necessary to detect differences between database records and actual storage contents.

## Availability Queries

The `file_replica_health` view converts physical replica state into an operational representation.

For every file chunk, it reports the configured replica count and the number of replicas that are both available and located on online nodes.

A query can identify degraded chunks:

    SELECT
        logical_path,
        chunk_number,
        healthy_replicas,
        configured_replicas
    FROM file_replica_health
    WHERE healthy_replicas < configured_replicas;

The result identifies chunks that have lost some redundancy even if their logical files remain readable.

The `validate_file_readable` function evaluates every chunk and requires each one to have at least the requested number of healthy replicas.

This distinction matters because a file with ten healthy chunks and one unavailable chunk is still unavailable as a complete object.

Availability checks must be interpreted against the intended policy. A chunk with one healthy replica may remain readable while violating a replication policy that requires three copies.

## Replication and Failure

Replication does not mean that every failure can be survived.

With replication factor two:

    Chunk X
        |
        +-- Node A
        +-- Node B

One node can fail while the chunk remains readable.

If both nodes fail:

    Chunk X
        |
        +-- Node A: FAILED
        +-- Node B: FAILED

there is no surviving replica from which to reconstruct the chunk.

Distributed storage therefore requires both replica placement and failure monitoring. The system must detect degraded redundancy and repair it before additional failures consume the remaining copies.

Replica placement also matters. Two replicas stored on the same physical device, power domain, or failure domain may be lost together. Production systems should place replicas across appropriately independent failure domains.

## Performance Considerations

Local file storage generally avoids network round trips but remains constrained by filesystem behavior, device throughput, operating-system caching, and available capacity.

Network file systems introduce network latency and server-side contention. Many small synchronous remote operations can be substantially more expensive than larger sequential transfers.

Distributed file systems introduce additional costs:

- Chunk metadata consumes memory and storage.
- Replication increases physical storage requirements.
- Reconstructing a file requires locating and reading multiple chunks.
- Repair traffic consumes network and storage bandwidth.
- More nodes increase coordination and operational complexity.
- Poor replica placement can reduce fault tolerance despite an apparently sufficient replication factor.

The examples use small fixed chunks so that placement and failure behavior remain observable. Production systems select chunk sizes based on workload, metadata overhead, throughput, access patterns, recovery requirements, and parallelism.

## Failure Modes

A storage system must distinguish different failure classes because their remedies differ.

**Path failure** occurs when a logical file does not exist or a requested path violates namespace rules.

**Capacity failure** occurs when an allocation would exceed a quota or physical node capacity.

**Integrity failure** occurs when retrieved bytes do not match their recorded checksum.

**Node failure** occurs when a physical storage endpoint becomes unavailable.

**Replica failure** occurs when a required chunk has no usable copy or fewer copies than its configured policy requires.

**Network failure** is particularly relevant to network file systems because a healthy server can still be unreachable from a client.

**Metadata inconsistency** occurs when logical records no longer accurately describe the physical data. This can happen after interrupted writes, incomplete deletion, or failed replica repair.

These failures should not be collapsed into a single generic file error in production systems. Capacity failures require allocation management, integrity failures require investigation or replacement, node failures require availability handling, network failures require connectivity or retry behavior, and metadata inconsistencies require reconciliation.

## Security Considerations

Path traversal is explicitly rejected in the Python and JavaScript implementations. A storage service should never construct filesystem paths directly from untrusted input without enforcing a namespace boundary.

Access control is another important boundary. The examples focus on storage mechanics rather than implementing a complete identity system, but a production network or distributed file service must determine which clients may read, write, delete, or enumerate data.

Checksums should not be confused with authorization. A valid checksum establishes that the retrieved content matches the expected digest. It does not establish who was allowed to retrieve or modify the content.

Sensitive storage systems should also consider:

- Encryption at rest and in transit to protect stored bytes and network transfers.
- Authentication and authorization to prevent unauthorized access.
- Audit logging for reads, writes, deletes, and administrative actions.
- Tenant isolation to prevent one customer from accessing another customer's files.
- Secure handling of credentials, keys, and service identities.
- Recovery controls to prevent corrupted or unauthorized data from being replicated as if it were valid.
- Protection of metadata so that an attacker cannot replace both the stored content and its trusted checksum.

Path validation alone is not a complete defense against filesystem attacks. Symbolic links, platform-specific path rules, and time-of-check-to-time-of-use races must be addressed by production implementations.

## Common Design Errors

Treating network storage as if it were local memory can produce latency-sensitive failures because remote operations incur transport and server costs.

Using replication without monitoring redundancy can leave a system apparently healthy while silently operating with fewer surviving copies than policy requires.

Counting a logical file only once when calculating physical capacity can underestimate the space consumed by replicas.

Checking integrity only after reconstructing a large object can delay detection of damaged chunks. Chunk-level checksums identify corruption closer to the physical storage boundary.

Relying exclusively on application-level validation can permit invalid metadata states when multiple applications write to the same database. Constraints and transactional operations help preserve invariants across clients.

Assuming that a successful metadata write guarantees durable physical storage is another common mistake. A storage service must define what successful completion means, including whether bytes have been written, replicated, verified, and durably acknowledged.

## Practical Relationship Between the Three Storage Models

The three models describe different architectural properties.

    File Storage
        |
        | shared namespace and access
        v
    Network File System
        |
        | potentially distributed physical implementation
        v
    Distributed File System

This is not a strict hierarchy in which every network file system must be distributed or every distributed system must expose traditional network filesystem semantics.

A network file system describes how remote clients access file-oriented storage. A distributed file system describes how storage responsibilities are spread across multiple machines while maintaining a logical file namespace.

A single implementation can combine both properties: a distributed backend can expose a network file interface to clients.

The central engineering problem is not simply where bytes are stored. It is how logical names, metadata, physical placement, integrity, availability, concurrency, capacity, and failure recovery are coordinated without exposing unnecessary physical complexity to applications.
