# Backup Architecture

## Scope

This project models a production-oriented backup architecture covering full backups, incremental backups, filesystem-style snapshots, retention policies, backup automation, integrity verification, restore-chain reconstruction, and failure handling.

The central design separates four mechanisms:

| Mechanism | Primary purpose | Data behavior |
|---|---|---|
| Full backup | Establish an independent recovery baseline | Copies the complete selected dataset |
| Incremental backup | Capture changes after an earlier recovery point | Stores files changed since its parent backup |
| Snapshot | Represent a point-in-time filesystem state | Creates a complete point-in-time copy in this implementation |
| Retention policy | Control recovery-point lifetime and storage consumption | Expires backup data according to age and minimum-preservation rules |

A backup is useful only when it can be recovered. The implementations therefore track backup metadata, parent relationships, file sizes, checksums, completion states, verification results, and retention decisions rather than treating copying files as the entire backup problem.

## Recovery Model

A full backup establishes the root of a recovery chain.

An incremental backup references a parent backup:

`FULL → INCREMENTAL → INCREMENTAL → INCREMENTAL`

Restoring the newest incremental backup requires reconstructing the chain from the full backup through each subsequent incremental backup.

A snapshot is represented separately because its conceptual purpose is a point-in-time state rather than a conventional full-plus-incremental chain. The Python, JavaScript, C++, and Java implementations use filesystem copies so they remain executable without operating-system-specific snapshot APIs. Actual storage platforms may implement snapshots through copy-on-write mechanisms, volume snapshots, filesystem snapshots, or cloud-provider primitives.

## Backup Lifecycle

The operational state model is:

`RUNNING → COMPLETED`

`RUNNING → FAILED`

`COMPLETED → EXPIRED`

A completed backup must have usable metadata and recoverable data. A failed backup must not be treated as a recovery point. An expired backup remains visible in the catalog so operational history is not confused with currently available recovery data.

The implementations perform these stages:

- inspect the source data
- calculate file metadata and checksums
- select files according to backup type
- copy selected data into an isolated backup directory
- record the backup relationship
- verify stored data
- reconstruct incremental chains during restore
- apply retention rules
- preserve failure information

## Full Backups

A full backup copies every selected source file.

The advantage is recovery simplicity. A valid full backup can be restored without depending on earlier incremental backups.

The cost is storage and backup time. Repeating full backups can consume substantial storage when the protected dataset is large and changes relatively slowly.

The Python implementation calculates a SHA-256 checksum for each file before recording it. The JavaScript implementation uses Node.js cryptographic hashing. Java uses `MessageDigest` with SHA-256.

The C++ implementation intentionally uses a dependency-free non-cryptographic fingerprint for portability and documents the production limitation. A production C++ backup engine should use a vetted cryptographic library for integrity verification.

## Incremental Backups

An incremental backup compares the current source inventory with its parent backup.

A file is selected when:

- it did not exist in the parent
- its size changed
- its checksum changed

Unchanged files are not copied again.

This reduces backup storage and transfer volume but introduces a recovery dependency. If a full backup or an intermediate incremental backup is lost, the chain may no longer be restorable.

The restore implementations therefore walk backward through `parent_backup_id` references until they reach a full backup, reverse that chain, and apply the files in chronological order.

## Snapshots

A snapshot represents a point-in-time recovery state.

The source files are copied into a separate snapshot directory in these educational implementations. Real snapshot systems can provide substantially different properties, including:

- copy-on-write storage
- near-instant creation
- space sharing between recovery points
- filesystem-level consistency
- volume-level atomicity

A filesystem copy should therefore not be interpreted as equivalent to a storage-array or filesystem snapshot.

For databases, application-aware snapshots may also require coordination with the database engine. A raw filesystem copy taken during active writes may not represent a transactionally consistent database state.

## Python Implementation

The Python implementation uses:

- `dataclass` objects for backup metadata
- `Enum` values for backup and failure states
- `pathlib` for filesystem operations
- SHA-256 through `hashlib`
- JSON for a durable local catalog
- atomic catalog replacement through a temporary file
- recursive file inventory
- full, incremental, and snapshot creation
- verification
- incremental-chain restoration
- retention processing
- temporary demo data

The catalog separates metadata from backup data. Each `BackupRecord` stores the backup type, parent, destination, creation time, status, and file inventory.

Incremental selection compares checksums and sizes rather than relying solely on modification timestamps. This is important because timestamps can be preserved, changed unexpectedly, or fail to describe the actual content difference.

The restore method refuses to restore directly over the live source directory. This is a deliberate safety boundary against accidental destructive restoration.

## JavaScript Implementation

The JavaScript implementation uses Node.js filesystem and cryptographic APIs.

Its complementary design emphasizes asynchronous event-driven filesystem operations:

- `fs/promises` for asynchronous I/O
- `crypto.createHash()` for SHA-256
- `Map` for the in-memory catalog
- recursive asynchronous directory traversal
- explicit backup status values
- atomic catalog replacement
- asynchronous restore and verification
- retention processing

The asynchronous model prevents large filesystem workflows from being written as blocking synchronous operations.

The implementation also distinguishes a backup repository from the source directory. This prevents the demonstration from accidentally treating the live dataset as its own recovery storage.

## C++ Implementation

The C++17 implementation models the backup system as an explicit `BackupEngine`.

Its design emphasizes:

- `std::filesystem` for platform-aware filesystem operations
- strongly typed enumerations
- `std::map` and `std::unordered_map`
- exception-based failure propagation
- deterministic inventory construction
- backup-chain traversal
- filesystem cleanup
- configurable retention duration

The incremental comparison uses an unordered lookup table for parent file metadata. This avoids repeatedly scanning the parent file list for every current file.

If there are `n` current files and `m` parent files, indexed comparison is approximately O(n + m), excluding the cost of reading and hashing the file contents.

The implementation's hash is deliberately documented as insufficient for production cryptographic integrity guarantees. A backup system must not silently present a weak checksum as equivalent to a cryptographic digest.

## Java Implementation

The Java implementation represents the backup domain with explicit types.

`BackupType` distinguishes full, incremental, and snapshot operations.

`BackupStatus` models lifecycle state.

`FileFingerprint` is an immutable record containing:

- relative path
- size
- checksum
- modification timestamp

`RetentionPolicy` validates minimum full-backup and retention-window requirements when the policy object is created.

`BackupRecord` owns the state of one recovery point. Its state-changing operations are constrained to explicit methods such as completion, failure, and expiration.

`BackupService` coordinates inventory generation, checksum calculation, backup creation, verification, restoration, and retention.

Java streams are used for inventory filtering, backup selection, full-backup ordering, and retention calculations. `MessageDigest` supplies SHA-256 without a third-party dependency.

## PostgreSQL Model

The SQL implementation treats the database as the control plane for a backup platform.

The main relationships are:

`repositories → backup_policies`

`repositories → backup_schedule`

`repositories → backups`

`backups → backup_files`

`backups → backup_verifications`

`backups → backups` through `parent_backup_id`

This self-reference represents an incremental recovery chain.

### Repository

A repository identifies the protected workload and the storage destination.

Keeping source and backup locations as separate attributes makes the failure-domain distinction explicit.

### Backup Policy

A policy records:

- full-backup frequency
- incremental frequency
- snapshot frequency
- retention duration
- minimum full-backup count
- verification requirement

These are operational rules rather than properties of an individual backup.

### Backup

The `backups` table records lifecycle state, parent relationship, storage location, size, object count, checksum algorithm, and failure information.

The constraints prevent invalid states such as a completed backup without a completion timestamp or a failed backup without a failure reason.

### Backup Files

`backup_files` stores the file-level recovery inventory.

The unique constraint on `(backup_id, relative_path)` prevents duplicate entries for the same path within a recovery point.

### Verification

`backup_verifications` separates successful creation from successful validation.

A backup can be successfully copied while still containing corrupt, incomplete, or inaccessible data. Verification provides an independent operational signal.

## PostgreSQL Integrity Enforcement

The `validate_backup_parent` trigger verifies that an incremental backup's parent belongs to the same repository.

This prevents a logically invalid chain such as:

`Repository A → Incremental → Parent from Repository B`

The `validate_completed_backup` trigger requires a completed backup to contain at least one recorded file.

The `mark_backup_completed` function calculates the stored object count and stored byte count from `backup_files` before changing a backup from `running` to `completed`.

These checks demonstrate the distinction between application validation and database-enforced integrity.

## Backup Automation

Automation is represented by `backup_schedule`.

Each schedule defines:

- repository
- schedule type
- interval
- next execution time
- enabled state

A typical operational schedule might be represented as:

`Full: every 24 hours`

`Incremental: every 1 hour`

`Snapshot: every 6 hours`

The schedule table does not itself execute operating-system jobs. It is the database representation of scheduling policy. An external scheduler or service would consume these records and invoke the backup engine.

The important architectural distinction is that scheduling decides when work should happen, while the backup engine decides how the recovery point is created.

## Retention Policies

Retention determines which recovery points remain available.

A simple policy can combine:

- an age-based retention window
- a minimum number of recent full backups

For example:

`retain backups for 30 days`

`retain at least 2 full backups`

Age alone is insufficient because a quiet system could allow all recent full backups to disappear under a poorly designed policy. A minimum-full-backup rule provides a recovery baseline.

Retention must also consider incremental dependencies. Deleting a full backup while retaining incrementals that depend on it can produce apparently present but unusable recovery points.

A production implementation should therefore calculate dependency closure before deleting recovery data.

## Verification and Integrity

The implementations calculate checksums for stored files and compare them during verification.

The basic verification flow is:

`backup metadata → expected file → existence → size → checksum`

A failure at any stage invalidates that file's verification result.

Checksums detect accidental corruption and incomplete copies. They do not by themselves provide confidentiality or authorization. Backup storage should also use appropriate access control, encryption, key management, audit logging, and isolated credentials.

## Transactions and Database Consistency

The PostgreSQL script uses transactions when creating backup records and adding their file inventory.

The database should not expose a completed recovery point before the corresponding metadata has been committed successfully.

A transaction boundary can therefore protect operations such as:

`create running backup → register files → mark completed → commit`

If an error occurs before commit, PostgreSQL can roll back the database changes.

The actual filesystem or object-storage operation remains outside the database transaction. This is a critical distributed-systems boundary. A PostgreSQL rollback cannot automatically undo an already-uploaded object. Production systems therefore need reconciliation logic for orphaned storage objects and incomplete catalog records.

## Failure Conditions

Important failure modes include:

| Failure | Effect | Required response |
|---|---|---|
| Source unavailable | Backup cannot start | Mark operation failed |
| Read error | File cannot be copied or hashed | Abort or isolate according to policy |
| Storage unavailable | Recovery point incomplete | Do not mark completed |
| Corrupt backup file | Recovery point cannot be trusted | Fail verification |
| Missing parent | Incremental chain cannot be reconstructed | Reject restore |
| Expired full backup | Dependent incrementals may become unusable | Retention must consider dependencies |
| Catalog corruption | Recovery metadata unavailable | Maintain catalog redundancy |
| Encryption-key loss | Encrypted data may be unrecoverable | Protect and test key recovery |
| Silent backup failure | Recovery coverage becomes stale | Monitor and alert on age and verification |

## Performance Considerations

A full backup reads the entire protected dataset.

If the source contains `N` bytes, the I/O work is approximately proportional to `N`.

An incremental backup still needs an inventory and usually needs file metadata or content checks to identify changes. The amount of data transferred can be much smaller than a full backup when the change rate is low.

For `n` files, indexed comparison of current and parent inventories is approximately O(n) after the inventories are available.

Checksum calculation is I/O-bound for large files. Parallel hashing can improve throughput on suitable storage systems, but uncontrolled concurrency can saturate disks, networks, CPU resources, or backup-storage APIs.

Retention operations can also become expensive when millions of backup objects are stored. Production systems commonly maintain indexed metadata and lifecycle policies rather than scanning every object during every retention run.

## Security Considerations

Backup data often contains the same sensitive information as the primary system.

Security controls should include:

- encryption in transit
- encryption at rest
- separate backup credentials
- least-privilege storage permissions
- immutable or write-protected recovery points where appropriate
- restricted deletion privileges
- audit logging
- protected encryption keys
- independent backup infrastructure
- monitoring of failed verification
- protection against accidental restoration over production data

A backup repository should not automatically inherit unrestricted access from the application that creates the data.

An attacker who can delete both production data and backups can defeat a recovery strategy. Separate credentials and storage controls reduce this risk.

## Recovery-Point Dependency

For a chain:

`FULL-01 → INC-01 → INC-02 → INC-03`

`INC-03` is not independently sufficient if it stores only changed files.

The restore process must apply:

`FULL-01`

then:

`INC-01`

then:

`INC-02`

then:

`INC-03`

This makes the full-backup retention policy a structural requirement, not merely a storage preference.

A production retention engine should preserve every ancestor required by any retained incremental recovery point.

## Snapshot Versus Backup

A snapshot is not automatically a complete backup strategy.

A snapshot can be extremely useful for rapid rollback, but if it exists only on the same storage system as the production volume, destruction of that storage can destroy both production data and snapshots.

A resilient architecture separates recovery mechanisms by failure domain:

`Production data`

`→ local snapshot`

`→ independent backup repository`

`→ off-site or cross-region recovery copy`

The exact arrangement depends on recovery-time objectives, recovery-point objectives, storage cost, regulatory requirements, and workload characteristics.

## Practical Recovery Workflow

A controlled restore should follow a sequence such as:

`Select recovery point`

`→ verify backup metadata`

`→ validate chain`

`→ verify available backup objects`

`→ restore to isolated destination`

`→ validate restored contents`

`→ perform application-level consistency checks`

`→ authorize production replacement if required`

Restoring directly over production without validation increases the risk of turning a recovery operation into a destructive operation.

## Educational Boundaries

The five implementations deliberately use local filesystem storage so they remain self-contained.

They do not claim to implement:

- cloud object-storage APIs
- filesystem-native atomic snapshots
- database-specific hot-backup protocols
- distributed consensus
- cross-region replication
- deduplicated block storage
- production-grade encryption-key management
- immutable object-lock enforcement
- multi-node backup scheduling

These omissions are architectural boundaries rather than unfinished implementations. The supplied code focuses on the core relationships among full backups, incrementals, snapshots, verification, restoration, automation metadata, and retention.
