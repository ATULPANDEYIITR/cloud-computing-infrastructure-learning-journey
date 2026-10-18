# Block Storage: Volumes, Snapshots, IOPS, Throughput, and Disk Attachment

## Scope

This repository models block storage as an operational system rather than treating it as a single concept.

The four primary areas are related but have different responsibilities:

- **Volumes** represent persistent block devices with capacity, a storage class, performance configuration, encryption state, and a lifecycle state.
- **Snapshots** represent point-in-time recovery artifacts derived from volumes. Snapshot lineage is modeled separately from live volume attachment because a backup artifact does not become a mounted disk merely because it exists.
- **IOPS and throughput** represent different performance dimensions. IOPS measures the number of I/O operations that can be serviced per second, while throughput measures the amount of data transferred per second. Workload behavior determines which dimension becomes the bottleneck.
- **Disk attachment** connects a block volume to a compute instance through a device path. Attachment has its own lifecycle and must not be confused with volume creation or snapshot creation.

The implementations use a cloud-style block-storage model with `gp3` and `io2` volume classes. The performance limits used by the examples are deliberately encoded as validation rules so that the examples behave consistently. They should not be interpreted as current pricing or provider-wide service documentation.

## Operational relationship

A useful way to distinguish the concepts is:

    +------------------+
    |      Volume      |
    | capacity         |
    | type             |
    | IOPS             |
    | throughput       |
    | encryption       |
    +--------+---------+
             |
       +-----+-----+
       |           |
       v           v
    +----------+ +-------------+
    | Disk     | | Snapshot    |
    |Attachment| | point-in-time|
    | instance | | recovery    |
    |device path| | lineage    |
    +----+-----+ +-------------+
         |
         v
    +---------------+
    | Workload      |
    | random I/O    |
    | sequential I/O|
    +-------+-------+
            |
            v
       IOPS or throughput
       becomes bottleneck

A volume is the persistent storage resource. Attachment determines where that resource is presented to a compute system. A snapshot captures storage state for recovery. IOPS and throughput describe how effectively a workload can use the volume.

## Volumes

A block volume provides addressable storage capacity to a compute system. The Python, JavaScript, C++, Java, and SQL implementations model the volume as a resource with explicit attributes rather than as an undifferentiated disk.

The core volume attributes are:

| Attribute | Meaning |
|---|---|
| Capacity | Allocated storage size in GiB |
| Type | Performance/storage class such as `gp3` or `io2` |
| IOPS | Provisioned I/O operations per second |
| Throughput | Maximum configured data transfer rate in MiB/s |
| Encryption | Whether stored data is protected by volume encryption |
| State | Lifecycle position such as available or attached |

Capacity and performance are intentionally independent in the examples. Increasing a volume from 500 GiB to 1 TiB does not automatically mean that the workload receives twice the IOPS or twice the throughput.

The Python `Volume` class validates volume-specific constraints before the object enters the storage manager. The JavaScript `BlockVolume`, C++ `BlockVolume`, and Java `BlockVolume` classes implement the same conceptual separation through their own language-specific validation mechanisms.

The SQL schema moves part of that responsibility into database constraints. The `volumes` table uses a `CHECK` constraint to prevent invalid `gp3` and `io2` performance configurations from being stored.

## Disk attachment

Attachment is the operation that makes a volume available to a compute instance through a block-device path.

The lifecycle modeled by the implementations is:

    AVAILABLE
        |
        | attach
        v
    ATTACHED
        |
        | detach request
        v
    DETACHING
        |
        | completion
        v
    AVAILABLE

The distinction matters operationally. A volume that exists but is not attached is not equivalent to a volume currently presented to a running instance.

The implementations reject a second active attachment in the simplified single-attachment model. The SQL implementation enforces the same rule with a partial unique index:

`one_active_attachment_per_volume`

This index applies only to rows whose `detached_at` value is `NULL`, allowing historical attachment records to remain available for auditing while preventing multiple current attachments.

The JavaScript implementation uses `EventEmitter` to expose `volume.attached`, `volume.detaching`, and `volume.detached` lifecycle events. This reflects the event-driven nature of infrastructure control planes more closely than a simple sequence of print statements.

The C++ and Java implementations model the explicit `DETACHING` state before returning the resource to `AVAILABLE`. This is useful when designing systems that must distinguish a request to detach from confirmed completion.

## IOPS

IOPS means input/output operations per second.

An IOPS limit becomes important when a workload performs many relatively small operations. For example, a database workload issuing many 4 KiB or 16 KiB operations can reach an IOPS boundary before transferring a large amount of data.

The implementations calculate IOPS pressure using the relationship:

`IOPS pressure = requested IOPS / provisioned IOPS`

A value below `1.0` indicates that the workload is below the modeled IOPS ceiling. A value near `1.0` indicates that the resource is approaching saturation. A value above `1.0` indicates that the requested workload exceeds the provisioned IOPS capacity.

This metric is deliberately separated from throughput pressure.

## Throughput

Throughput measures the volume of data transferred per unit of time.

The examples derive requested throughput from workload characteristics:

`requested MiB/s = requests per second × average I/O size in KiB / 1024`

A sequential analytics workload can perform relatively few operations while transferring large amounts of data. In such a workload, throughput can become the dominant constraint even when the raw IOPS requirement is modest.

The Python, C++, Java, and JavaScript implementations compare both pressure values and identify the larger one as the modeled bottleneck.

The SQL implementation exposes the same relationship through the `workload_capacity_analysis` view. This makes the distinction queryable instead of hiding it inside application logic.

## IOPS versus throughput

These two metrics should not be treated as interchangeable.

Consider two workloads:

| Workload | Request rate | Average I/O | Primary concern |
|---|---:|---:|---|
| Database random I/O | High | Small | IOPS |
| Analytics scan | Lower | Large | Throughput |

A workload generating 12,000 operations per second with 4 KiB operations requests roughly 46.88 MiB/s. It can therefore require substantial IOPS without consuming a large amount of throughput.

A workload generating 1,000 operations per second with 512 KiB operations requests roughly 500 MiB/s. Its IOPS demand is much lower, but its throughput requirement is much higher.

The correct storage configuration depends on the workload rather than on a single performance number.

## Snapshots

A snapshot is represented as a separate resource from the source volume.

The implementations model:

- Source volume identity.
- Snapshot identity.
- Snapshot state.
- Creation progress.
- Parent snapshot.
- Source capacity.
- Completion state.

The snapshot lifecycle is represented as:

    CREATING
       |
       | progress
       v
    COMPLETED

The examples use deterministic progress increments to make the lifecycle executable. A real storage platform can implement snapshot creation asynchronously and can use provider-specific mechanisms to avoid copying every unchanged block into an independent physical storage allocation.

The important modeling decision is that a snapshot is not treated as a mounted disk. It is a recovery artifact from which a new volume can be created.

## Snapshot lineage

The second and later snapshots in the examples can reference an earlier snapshot as their parent.

The lineage is represented conceptually as:

    baseline
       |
       v
    after-index-maintenance
       |
       v
    later-backup

The SQL implementation uses a recursive common table expression to traverse this relationship.

The Python implementation uses a dictionary-backed object graph. JavaScript follows parent references in a `Map`. Java uses an explicit snapshot collection and traverses the parent identifiers. C++ uses a `std::map` and optional parent identifiers.

This is a useful distinction between snapshot metadata and the underlying storage implementation. A provider may optimize unchanged blocks internally, but the control-plane model still needs enough lineage information to determine the relationship among recovery points.

## Python implementation

The Python program acts as a compact storage control plane.

The `BlockStorageManager` owns volumes, snapshots, and attachments. The `Volume` class validates storage-specific limits and estimates a teaching-oriented monthly cost. `attach_volume()` and `detach_volume()` enforce lifecycle transitions rather than allowing arbitrary state mutation.

The workload simulator calculates IOPS pressure, requested throughput, sustainable IOPS, completed requests, rejected requests, and estimated latency. This gives the performance model executable behavior rather than describing IOPS and throughput only in prose.

The script also demonstrates:

- Invalid IOPS configuration.
- Invalid throughput configuration.
- Conflicting volume attachment.
- Snapshot creation.
- Snapshot restoration.
- Snapshot lineage.
- Performance modification with rollback after validation failure.
- Inventory export to JSON.
- Temporary-file handling.
- Comparison of IOPS-oriented and throughput-oriented workloads.

The cost calculation is explicitly an illustrative model. It is not intended to represent a provider's current billing schedule.

## JavaScript implementation

The JavaScript implementation emphasizes event-driven infrastructure behavior.

`StorageControlPlane` extends Node.js `EventEmitter`. Volume creation and attachment produce lifecycle events, while snapshot creation uses asynchronous timers to model a control-plane operation that progresses independently of the caller's immediate request.

The `BlockVolume` class performs transactional performance configuration: it saves the previous configuration, attempts validation, and restores the previous values if the new configuration is invalid.

The JavaScript workload evaluator returns a structured result containing:

- Requested requests.
- Completed requests.
- Rejected requests.
- Requested throughput.
- IOPS pressure.
- Throughput pressure.
- The selected bottleneck.

The implementation therefore demonstrates a control-plane pattern in which infrastructure changes generate observable events and asynchronous operations have explicit completion states.

## C++ case study

The C++ program presents a storage governance engine for a production database environment.

`StorageGovernanceEngine` manages volume and snapshot objects using `std::map`. `BlockVolume` encapsulates capacity, performance, encryption, and attachment state. Validation is performed at construction and when performance is changed.

The `RepositoryStoragePolicy` class represents a higher-level operational rule. It evaluates encryption, minimum IOPS, minimum throughput, and a maximum modeled latency for a workload.

This separates resource properties from policy decisions. A volume can be technically valid while still failing a production policy because its configuration does not meet the workload's requirements.

The C++ implementation also uses `std::optional` for attachment and snapshot-parent relationships. This makes the absence of an attachment or parent explicit rather than representing it through magic strings.

The case study compares a high-IOPS configuration against a high-throughput configuration under random and sequential workloads. That comparison demonstrates why storage sizing must consider workload shape.

## Java enterprise model

The Java implementation emphasizes domain modeling and policy abstraction.

`BlockVolume`, `Snapshot`, `Attachment`, and `Workload` are explicit domain types. The `StoragePolicy` interface separates storage-policy evaluation from the underlying volume implementation.

`ProductionDatabasePolicy` checks:

- Encryption.
- Minimum IOPS.
- Minimum throughput.
- Maximum modeled latency.

This creates an enterprise-style separation between infrastructure state and business or operational policy.

The `StorageService` acts as an application service responsible for volume creation, snapshot creation, snapshot restoration, inventory access, and lineage traversal.

Java's exception model is used for invalid state transitions and invalid storage configuration. Performance changes use a rollback pattern so that a failed validation cannot leave the volume containing a partially applied configuration.

## SQL data model

The PostgreSQL schema represents the block-storage domain relationally.

| Table | Purpose |
|---|---|
| `storage_instances` | Compute resources capable of receiving attached volumes |
| `volumes` | Capacity, type, IOPS, throughput, encryption, and lifecycle state |
| `volume_attachments` | Historical and active volume-to-instance relationships |
| `snapshots` | Recovery points and snapshot lineage |
| `storage_workloads` | Workload characteristics used for performance analysis |
| `storage_policies` | Operational requirements for storage configurations |
| `policy_evaluations` | Recorded policy decisions |

The schema uses PostgreSQL enum types for storage and lifecycle states.

Foreign keys prevent references to nonexistent volumes, instances, policies, workloads, or snapshots.

The `volumes` table uses a compound `CHECK` condition so that the allowed performance ranges depend on the volume type. This is database-level validation rather than an assumption made solely by an application.

## Database enforcement of attachment state

The `volume_attachments` table stores both current and historical attachments.

An active attachment has `detached_at IS NULL`.

The partial unique index `one_active_attachment_per_volume` prevents more than one active attachment for the same volume in this model.

The `enforce_volume_attachment_state()` trigger updates the volume lifecycle state when an attachment is created or detached.

This design provides two useful properties at the same time:

- The database can reconstruct historical attachment activity.
- The database can prevent multiple active attachments for one volume.

## Database enforcement of snapshot state

The `validate_snapshot_state()` trigger prevents an inconsistent snapshot from being stored as completed while having less than 100 percent progress.

It also prevents a non-completed snapshot from having a completion timestamp.

The database therefore protects the relationship:

`COMPLETED -> progress = 100% -> completed_at is present`

This is an example of integrity that belongs at the database layer because it is a structural invariant rather than a user-interface preference.

## Performance analysis query

The `workload_capacity_analysis` view exposes the two performance dimensions together.

For each workload it calculates:

- `requested_mib_s`
- `iops_pressure`
- `throughput_pressure`

This allows operations teams to determine whether a workload is approaching the IOPS ceiling or the throughput ceiling.

The SQL implementation intentionally keeps these calculations visible rather than reducing performance to a single score.

## Transactions and configuration changes

The SQL script updates the production database volume's IOPS and throughput inside a transaction.

A transaction makes the performance change atomic from the database's perspective. If an invalid value violates a `CHECK` constraint, the update cannot silently persist a partially valid configuration.

The commented invalid update demonstrates where the database would reject a configuration that violates the volume-type constraints.

## Workload design

Storage performance must be evaluated against workload shape.

### Small random I/O

Small random operations tend to produce high operation counts relative to the amount of data transferred. Such workloads are often sensitive to IOPS and latency.

Database indexes, transaction logs, metadata-heavy operations, and key-value workloads can exhibit this pattern.

### Large sequential I/O

Large sequential operations can transfer substantial data with fewer individual requests. Throughput can become the limiting dimension.

Analytics scans, backups, media processing, and large file transfers can exhibit this pattern.

The examples do not claim that every database workload is IOPS-bound or every analytics workload is throughput-bound. They demonstrate why both measurements must be evaluated.

## Edge cases and failure behavior

The implementations deliberately reject several invalid conditions.

An invalid volume configuration is rejected when its IOPS or throughput falls outside the modeled range for its volume type.

A volume cannot be attached twice while it already has an active attachment.

A volume cannot be detached if it is not currently attached.

A snapshot cannot be restored until it reaches the completed state.

A snapshot parent must exist before a child snapshot can reference it.

A workload with invalid request rate, I/O size, or duration is rejected.

An encrypted-only production policy rejects a volume that does not satisfy the required encryption state.

These failures represent different categories of control:

- Resource validation protects the volume itself.
- Lifecycle validation protects state transitions.
- Snapshot validation protects recovery metadata.
- Workload validation protects performance calculations.
- Policy validation determines operational suitability.

## Performance and capacity planning

Capacity, IOPS, and throughput should be measured independently.

A volume can have large capacity but modest IOPS. Another can have smaller capacity but substantially higher IOPS. A third configuration can prioritize throughput.

A useful operational calculation is:

`requested throughput = request rate × average I/O size`

This calculation connects the workload to the storage configuration.

For example, a workload issuing 18,000 16 KiB operations per second requests approximately 281.25 MiB/s. If the volume provides 500 MiB/s throughput but only 12,000 IOPS, the IOPS dimension can become the limiting factor even though the requested throughput is below the throughput ceiling.

Conversely, 1,000 operations per second at 512 KiB each requests approximately 500 MiB/s. A volume with sufficient IOPS but only 125 MiB/s throughput will be constrained by throughput.

## Common design mistakes

### Treating capacity as performance

A larger disk does not automatically imply proportionally higher IOPS or throughput. Capacity planning and performance planning answer different questions.

### Looking only at IOPS

A workload can have a low request rate but transfer large blocks. Such a workload can saturate throughput while remaining comfortably below the IOPS limit.

### Looking only at throughput

A workload can generate many small operations and remain relatively low in MiB/s while exhausting IOPS.

### Treating snapshots as attached disks

A snapshot is a recovery artifact. Restoration normally creates or populates a separate volume resource before it is attached to compute.

### Ignoring attachment state

A control-plane request to attach or detach a volume is not necessarily equivalent to immediate device availability. Systems that automate storage operations should model state transitions and asynchronous completion where appropriate.

### Storing only current attachment information

Removing an attachment row completely destroys useful audit history. The SQL implementation retains historical records and marks them as detached.

## Security considerations

Encryption is represented explicitly on volumes because storage security is an infrastructure property, not merely an application setting.

The production policy in the Java and C++ implementations can reject an unencrypted volume.

The SQL schema includes the same encryption attribute so that database-side policy evaluation can consider it.

Operational systems should also restrict who can attach, detach, snapshot, restore, resize, or modify the performance configuration of production volumes. Those authorization rules are outside the storage simulator but are directly related to the control-plane operations modeled here.

Snapshots also require access controls because they can contain complete copies of sensitive application data.

## Production considerations

A production block-storage control plane would need stronger guarantees than the deterministic simulations used here.

Real systems must account for asynchronous state changes, retries, idempotent requests, API timeouts, attachment visibility from the operating system, device discovery, availability-zone constraints, encryption-key permissions, snapshot consistency requirements, monitoring, audit logs, quota limits, and provider-specific failure modes.

Performance planning should use observed workload metrics rather than relying exclusively on theoretical limits. IOPS, throughput, latency, queue depth, burst behavior where applicable, and application-level response time should be considered together.

Snapshots should also be governed by retention policies, recovery objectives, deletion protection, encryption requirements, and restore testing. A snapshot that has never been successfully restored should not be treated as proof of a tested recovery process.

## Implementation boundaries

The six files intentionally use different perspectives.

Python provides a broad executable storage simulation with inventory, workload modeling, snapshot operations, validation, and export.

JavaScript focuses on event-driven and asynchronous control-plane behavior.

C++ presents a governance-oriented case study with explicit resource policies and performance evaluation.

Java models an enterprise domain using explicit types, service boundaries, state transitions, and policy interfaces.

PostgreSQL moves integrity into relational constraints, indexes, triggers, transactions, views, and recursive queries.

The shared domain is block storage, but the implementation responsibilities are deliberately different so that volumes, snapshots, performance dimensions, and attachment lifecycle remain distinct throughout the system.
