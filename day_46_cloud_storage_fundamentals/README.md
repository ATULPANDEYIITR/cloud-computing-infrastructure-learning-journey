# Cloud Storage Fundamentals

## Storage as a reliability and lifecycle decision

Cloud object storage retains data independently of the compute systems that create and consume it. Objects are typically addressed by a bucket and key, accompanied by metadata such as size, version, checksum, storage class, and creation time.

A storage design must distinguish several properties that are related but not interchangeable.

| Property | Meaning | Engineering question |
|---|---|---|
| Durability | Probability that stored data remains intact over a specified period | How likely is permanent object loss? |
| Availability | Probability that a request can be served when required | Can an application read the object during a failure? |
| Replication | Process that copies data between storage locations | How quickly does a destination receive an update? |
| Redundancy | Availability of alternative copies or service paths | Can another independent copy serve the request? |
| Storage class | Policy governing cost, access patterns, retrieval behavior, and retention | Which storage tier fits the expected workload? |
| Integrity | Ability to detect unintended data changes | Does the retrieved content match its expected checksum? |
| Recoverability | Ability to restore usable data after loss or corruption | Can a known-good version be recovered after an incident? |

A replicated object can be durable while temporarily unavailable in a particular region. A service can be highly available while still accepting an accidental deletion that eventually removes every replica. These distinctions determine how replication, versioning, retention, and backup policies should be designed.

## Durability and availability

Durability concerns long-term preservation. Availability concerns successful access over a period of time. A durability figure is not an uptime percentage, and a service availability objective does not guarantee recovery from logical corruption.

### Independent failure model

Suppose a single copy has a probability \(p\) of being lost during a specified period. If \(n\) copies fail independently, the simplified probability of losing all copies is

\[
P(\text{total loss})=p^n
\]

For an illustrative single-copy loss probability of \(10^{-4}\), three independent copies produce a modeled total-loss probability of \(10^{-12}\).

This result depends on independence. Shared credentials, a compromised account, an erroneous lifecycle rule, common control-plane failures, or an operator deleting every copy can invalidate the model.

The Python and C++ programs calculate the number of copies required to meet a target under this assumption. The JavaScript program uses the same reliability relationship to calculate availability rather than durability. These are distinct calculations even though both benefit from redundancy.

### Availability of alternative service paths

If each independent service path is available with probability \(a\), the probability that at least one of \(n\) paths is available is

\[
P(\text{available})=1-(1-a)^n
\]

With a path availability of 99.9%, the simplified model predicts 99.9% availability for one path and 99.9999% for three independent paths.

This is a mathematical model, not a provider service-level agreement. Actual availability depends on network routing, authentication, client retries, regional dependencies, control planes, and whether a surviving replica is current enough to serve the application.

## Replication and redundancy

Replication is the act of copying an object. Redundancy is the resulting availability of alternative copies or paths. A system may configure replication without yet having a completed replica.

### Single-region storage

A single-region configuration stores an object in one configured region. The storage provider may internally distribute data across multiple devices or facilities, but application-level regional recovery is not implied by the single-region setting.

If that region becomes inaccessible, the application may lose access even when the underlying data remains intact.

### Synchronous replication

A synchronous write waits for the configured destinations to acknowledge the write before the operation is reported as successful.

This provides a stronger write-acknowledgement condition than merely placing a replication task in a queue. The trade-off is that destination failures or increased network latency can delay or reject writes.

The Python, C++, and Java implementations reject synchronous writes when a required destination is unavailable. The check occurs before the simulated write is committed.

The JavaScript implementation similarly validates destination availability before storing the new object. These examples model application-level policies; they do not claim that every commercial storage service implements synchronous cross-region replication in the same way.

### Asynchronous replication

An asynchronous write is accepted before all destination copies are confirmed. The source can continue serving requests while a replication job remains pending.

This improves write responsiveness, but it creates a replication-lag window. If the source fails before a destination receives the latest version, the destination may contain older data.

The implementations model pending replication explicitly. A job records its destination, object version, and delivery state. Unavailable destinations can be retried, and the simulations prevent a delayed older version from overwriting a newer destination version.

The JavaScript version adds event-driven observability through events such as `object:stored`, `replication:retry`, and `replication:completed`. These events make replication state visible to monitoring and operational workflows.

### Failure domains matter

Three copies in one failure domain are not equivalent to three copies in independent regions. A failure-domain label identifies a boundary such as a region, facility, or another relevant infrastructure grouping.

The SQL model counts distinct available failure domains rather than treating every replica record as independent. Even distinct regions can share dependencies, so a production design must evaluate actual provider architecture and the application's failure assumptions.

### Failover and stale data

Failover changes which surviving location serves as the active source or primary. It is not sufficient to select any available region. The destination must contain the required object versions and meet the application's consistency and recovery objectives.

The programs demonstrate reading from a preferred region, checking region availability, and promoting a surviving region. They do not implement distributed leader election, fencing tokens, quorum consensus, or split-brain prevention. Those mechanisms are necessary when multiple writers or concurrent failover controllers could otherwise create conflicting authoritative states.

## Storage classes and lifecycle policies

Storage classes represent different economic and operational choices. Lower storage prices can be offset by retrieval fees, retention restrictions, minimum billable sizes, or slower retrieval.

| Illustrative class | Intended workload | Storage cost | Retrieval cost | Access expectation |
|---|---|---:|---:|---|
| Standard | Frequent reads and active application data | Higher | Low or none | Immediate access |
| Infrequent access | Data retained for occasional retrieval | Lower | May apply | Usually rapid access |
| Archive | Long-term records and rarely accessed evidence | Lowest | Often higher | May require restoration |

The prices and latency values in the implementations are teaching assumptions, not quotations from a particular cloud provider. Actual classes differ by provider, region, redundancy option, request type, object size, retrieval tier, and contract.

### Estimating total cost

For a simplified workload, monthly cost can be estimated as

\[
C_{\text{month}}
=
S \times R_s \times N
+
D_r \times R_r
+
C_{\text{requests}}
\]

where:

- \(S\) is the stored size in gigabytes.
- \(R_s\) is the monthly storage rate per gigabyte.
- \(N\) is the number of billable copies in the model.
- \(D_r\) is the volume retrieved during the month.
- \(R_r\) is the retrieval rate per gigabyte.
- \(C_{\text{requests}}\) represents request charges.

This estimate omits transfer charges, metadata operations, minimum billable object sizes, early-deletion charges, monitoring, and provider-specific pricing details. Those costs should be included when estimating an actual workload.

The Python implementation compares classes using a shared cost function. The JavaScript implementation validates input quantities before calculating costs. The C++ program separates tier policies from transition decisions, and the Java program places class-specific rates and retention values in an enum-keyed catalog.

### Lifecycle transitions

A lifecycle policy moves objects between classes as their access patterns change. An active telemetry file might begin in Standard storage and transition to Infrequent Access when regular processing finishes. Long-retained compliance evidence might later move to Archive.

A transition must account for object age, minimum retention, expected retrieval frequency, retrieval latency, and the cost of moving the object back to a faster class.

The Python, JavaScript, C++, and Java programs model retention checks and lifecycle eligibility. The SQL script records both accepted and rejected transition evaluations with a reason for rejection.

These examples model policy decisions rather than a provider's complete lifecycle engine. In particular, moving an object to an archive class does not necessarily mean it can be read immediately. Some archive services require a restoration request and a waiting period.

## Python implementation

The Python script combines domain modeling, reliability calculations, and operational simulations.

`StorageClassPolicy` is an immutable data class that keeps pricing, minimum retention, and retrieval latency together. `StoredObject` records an object's key, size, checksum, version, and replica locations. `StorageRegion` separates regional health from the data stored in that region.

`CloudStorage` implements three replication modes. Single-copy writes retain one application-visible copy. Synchronous writes validate the destinations before committing the simulated write. Asynchronous writes enqueue pending replica deliveries.

The `replicate_pending()` method processes the queue and avoids replacing a newer version with an older one. Region availability can be changed independently of stored content, which makes it possible to simulate a service outage without pretending that all unavailable data has been destroyed.

The reliability helpers provide analytic availability estimates, a Monte Carlo simulation, and a minimum-copy calculation. The Monte Carlo function is useful for checking a probability model numerically, but it does not make the independence assumption more realistic.

The cost model also makes an important limitation visible: it uses simplified rates and a small per-object charge. Real billing should use the applicable provider's request, retention, transfer, and retrieval rules.

## JavaScript implementation

The JavaScript program emphasizes asynchronous workflow behavior and operational events.

`ObjectStorageService` extends Node.js's `EventEmitter`. Successful writes, replication attempts, completed deliveries, and region-health changes emit named events. An observer can consume these events without becoming responsible for the storage service's internal state transitions.

`ReplicationJob` stores a unique job identifier, target region, version, attempt count, and status. This reflects the practical distinction between accepting a write and confirming that replication completed.

The use of `Buffer` prevents text encoding assumptions from changing the byte representation of stored content. The SHA-256 digest is calculated from the bytes that are actually stored, and reads verify the digest before returning the object.

Object keys and cost inputs are validated before processing. The example uses an in-memory model, so its maps and job queue disappear when the process exits. A production worker would need durable queues, persistent metadata, idempotent retries, structured logs, and a way to recover jobs after a process restart.

The lifecycle evaluator deliberately rejects a transition when the current class's minimum retention period has not elapsed. It evaluates eligibility rather than silently changing the class, separating policy evaluation from execution.

## C++ case study

The C++ program models a regional telemetry repository used by an industrial monitoring system.

`GovernanceStorageEngine` owns the regions, the current primary, the replication policy, version counters, and pending replication tasks. The `StoredObject` structure carries the metadata needed to identify a version and evaluate a storage-tier decision.

The design uses `std::map` for region and object lookup, `std::set` to validate unique region names, and `std::optional` to represent a read that has no accessible copy. The read path first checks the primary and then considers available alternative regions.

The replication queue demonstrates a version-ordering rule: an older queued object must not overwrite a newer destination version. This is a useful safeguard against out-of-order delivery, although production replication systems need more complete concurrency and failure-handling mechanisms.

`evaluateTierTransition()` checks the age of an object against the source class's retention requirement. It returns a structured decision instead of mixing policy validation with output statements.

The program also calculates simplified availability and durability values. Its cost estimate converts bytes to decimal gigabytes and includes storage and retrieval rates. It is an illustrative model, not a complete financial calculator.

The C++ implementation highlights the need to separate data structures, policy calculations, failure handling, and operational reporting. Its replication simulation is suitable for studying version and failure behavior, but it does not persist state or implement distributed coordination.

## Java implementation

The Java program uses an enterprise-oriented domain model with explicit types and service boundaries.

`StoragePolicy` represents the economics and retention requirements of a class. `ObjectVersion` carries immutable version metadata, while `Region` owns the state and objects for a particular region. `StorageClassCatalog` centralizes the policy values used for cost and retention decisions.

The `ObjectStorageService` exposes synchronized operations for writes, replication delivery, reads, region-health updates, and failover. Synchronization prevents concurrent callers within the same service instance from interleaving those operations arbitrarily. It is not a substitute for distributed transactions or cross-process locking.

The `ReplicationTask` record separates the work to be delivered from the object metadata. A destination is updated only if the candidate is not older than the current version. The read operation verifies the recorded checksum before returning an object.

The implementation clones byte arrays in the `ObjectVersion` constructor and accessor to prevent callers from mutating stored content through a shared array reference. This is a useful Java-specific example of defensive copying for an otherwise immutable domain object.

The checksum helper uses CRC32 to keep the example self-contained. CRC32 can detect some accidental changes but does not provide cryptographic collision resistance. Production integrity verification should use a suitable cryptographic digest and appropriate authentication controls.

## PostgreSQL relational model

The SQL script represents storage configuration, object metadata, replication work, lifecycle decisions, and operational observations as related tables.

### Relational structure

| Table | Responsibility |
|---|---|
| `storage_classes` | Defines class-specific prices, retention requirements, and retrieval latency |
| `regions` | Records region identity, health, geography, and failure domain |
| `storage_buckets` | Connects a bucket to its primary region and replication policy |
| `stored_objects` | Holds the current object metadata and lifecycle state |
| `object_versions` | Preserves version-specific metadata and checksums |
| `object_replicas` | Records object versions available in individual regions |
| `replication_jobs` | Tracks pending, completed, and failed replica deliveries |
| `lifecycle_events` | Records accepted or rejected storage-class transitions |
| `access_events` | Captures reads, writes, restores, and checksum failures |
| `durability_assumptions` | Stores the probability assumptions used by reliability queries |

Primary keys identify records. Foreign keys prevent records from referencing nonexistent objects, classes, buckets, or regions. Check constraints enforce valid sizes, positive versions, non-negative rates, valid digest formatting, and permitted state values.

The unique constraint on `(bucket_id, object_key)` prevents duplicate object keys within a bucket. The partial unique index `one_current_version_per_object` permits at most one version marked as current for each object.

### Triggers and transactions

The `validate_current_object_version()` trigger checks that a version marked current agrees with the version number on its parent object. The `validate_replica_version()` trigger rejects replica records whose version exceeds the source object's current version.

The replication-delivery block runs inside a transaction. It selects eligible jobs, updates or creates destination replicas, and marks successfully processed jobs complete. A transaction ensures that the replica update and job-state change commit together.

The replication queue index targets pending and retryable jobs, rather than indexing completed work that is not needed for the normal retry query. This reduces the indexed set for that operational workload.

### Policy and resilience queries

The storage-cost query compares monthly storage charges and retrieval charges across classes. The `object_resilience` view counts replicas whose region is available and whose version and checksum match the source object's current metadata.

The availability query estimates the probability that at least one distinct available failure domain can serve the object. The durability query estimates the copy count required under the explicitly recorded independent-failure assumption.

These results are estimates, not proof of a provider's durability or availability commitments. The SQL schema records replica metadata and regional health; it does not independently prove that the physical content of each replica matches its checksum. A real storage integration must verify content during transfer or retrieval and persist trustworthy verification results.

The lifecycle-event query records rejected transitions as data, including the reason that the minimum retention period has not elapsed. This supports auditing and investigation without pretending that every policy failure is a database constraint violation.

## Integrity, versioning, and recovery

A checksum helps detect content changes. A version identifier distinguishes revisions of the same logical object. Neither alone provides a recoverable backup.

Versioning can help restore a previous revision after an accidental overwrite, provided that the earlier revision has not been permanently removed. A backup should also have an appropriate retention policy, access restrictions, and an independent recovery path.

Replication is primarily a continuity mechanism. If a deletion or corrupted update is automatically propagated to every replica, all live copies can become unusable even though the replication process worked as designed.

A robust storage design therefore treats these controls separately:

- **Replication** maintains copies in other locations and reduces dependence on a single failure domain.
- **Checksums** detect content that differs from an expected representation.
- **Versioning** preserves distinguishable revisions of an object.
- **Backups** provide a recovery source with an independently controlled retention and restoration process.
- **Access controls** limit who can read, overwrite, delete, or change retention settings.
- **Restore tests** establish whether retained data can actually be recovered within the required time.

## Consistency and operational limitations

Asynchronous replication permits temporary differences between source and destination versions. A successful read from a secondary region does not necessarily mean that the latest source write is present.

A production failover procedure should verify the latest replicated version, prevent conflicting writers, establish a single authoritative writer, and record the recovery point. A system that promotes a stale replica without checking its version may lose acknowledged updates.

Replication monitoring should track queue age, pending job count, retry count, failed jobs, destination health, and the difference between source and destination versions. A permanently failed job must not be reported as successful merely because the source write was accepted.

The programs intentionally use in-memory data structures and simplified regional state. They do not model provider-specific replication guarantees, distributed consensus, cross-region routing, object-lock enforcement, request-level billing, or real service-level objectives. Their purpose is to make the underlying relationships and failure conditions explicit.

## Security and production considerations

Storage architecture must account for accidental deletion, compromised credentials, unauthorized reads, malicious overwrites, and misconfigured lifecycle rules.

A production deployment should apply least-privilege access policies, encrypt data in transit and at rest, protect version and retention controls, and maintain audit records for destructive operations. Where recovery from account compromise is required, backups should be isolated through separate permissions or administrative boundaries.

Monitoring must distinguish an unavailable region from a missing object and a checksum mismatch from a stale replica. These failures require different responses. A region outage may call for failover, a replication delay may call for queue recovery, and an integrity failure may require quarantine and restoration from a verified version.

The central architectural decision is not simply how many copies to keep. It is how to preserve data, keep it accessible under the expected failure model, control the cost of retaining and retrieving it, and demonstrate that a usable copy can be recovered when normal operations fail.
