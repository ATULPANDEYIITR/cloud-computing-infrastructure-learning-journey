# Storage Virtualization: Logical Volumes, Virtual Disks, Storage Pools and Abstraction Layers

## Scope

This learning artifact models storage virtualization as a layered storage system rather than as a collection of unrelated storage terms.

The central abstraction is:

**Physical Devices → Storage Pool → Logical Volumes → Virtual Disks → Consumer**

A physical storage device owns actual capacity. A storage pool aggregates capacity from multiple devices. A logical volume presents a virtual capacity independent of the physical device boundaries. A virtual disk exposes that logical storage to a consumer such as a virtual machine or application server.

The implementations deliberately use different perspectives:

| Deliverable | Primary perspective |
|---|---|
| Python | Executable storage virtualization simulator |
| JavaScript | Event-driven and asynchronous storage controller |
| C++ | Resource-allocation and failure-management case study |
| Java | Enterprise domain model with explicit policies and state |
| SQL | Relational representation with database-enforced integrity |

The important distinction is between **where data is logically addressed** and **where data is physically stored**. Storage virtualization exists because those two identities do not have to be the same.

## Core Architecture

A virtualized storage system can be understood through several boundaries.

### Physical storage

Physical devices are the lowest storage layer represented in these implementations. Each device has a finite capacity, current utilization, operational state, and performance characteristics.

A device may be an SSD, NVMe device, HDD, RAID member, SAN LUN, or another lower-level block-storage resource. The virtualization layer does not require consumers to know the device's physical identity.

The Python `PhysicalDevice`, C++ `PhysicalDevice`, Java `PhysicalDevice`, and SQL `physical_device` representations all preserve this physical boundary.

### Storage pool

A storage pool combines capacity from multiple physical devices into one allocation domain.

For example, three devices with capacities of 12 GB, 16 GB, and 24 GB can provide a 52 GB physical pool before accounting for other reservations or metadata.

The pool is responsible for deciding where new extents are placed. In the Python, C++, and Java implementations, allocation uses a least-utilized-device policy. The Java version expresses this as an `AllocationPolicy` interface, making the placement rule an explicit domain policy.

The pool is therefore an abstraction layer between physical devices and logical storage.

### Extents

An extent is a unit of physical allocation.

A logical volume does not need to occupy one contiguous physical region. It can be composed of multiple extents distributed across several physical devices.

The simplified implementations use one-GB extents to make allocation visible. Real storage systems can use different allocation units and more complex metadata.

An extent records enough information to answer the physical-placement question:

`Which physical device contains the storage allocated to this logical volume?`

The SQL `storage_extent` table makes this relationship explicit through foreign keys to the pool, volume, and physical device.

### Logical volumes

A logical volume presents storage capacity without exposing the physical device layout.

A volume can be **thick provisioned** or **thin provisioned**.

With thick provisioning, physical capacity is reserved when the logical volume is created.

With thin provisioning, a larger virtual capacity can be advertised while physical capacity is allocated as data is actually written.

For example, a 20 GB thin volume can initially consume almost no physical capacity. Writing data causes physical extents to be allocated as needed.

This creates a deliberate distinction:

**Virtual capacity ≠ current physical consumption**

That distinction is central to capacity planning. Thin provisioning improves utilization but introduces an operational risk if aggregate virtual demand grows beyond the available physical capacity.

### Virtual disks

A virtual disk is a consumer-facing abstraction over a logical volume.

A virtual machine can interact with a disk identifier such as `vdisk-db-01` without needing to know whether the underlying data resides on `nvme-01`, `nvme-02`, or another physical device.

The Python `VirtualDisk`, JavaScript `VirtualDisk`, and Java `VirtualDisk` classes demonstrate this separation.

The virtual disk therefore represents the interface seen by the consumer, while the storage pool manages the implementation beneath that interface.

## Abstraction Layers

The complete data path can be represented as:

**Application → Filesystem → Virtual Disk → Logical Volume → Storage Pool → Extent Mapping → Physical Device**

Each layer has a different responsibility.

The application generates logical storage operations.

The filesystem organizes files, directories, metadata, allocation structures, and logical blocks.

The virtual disk exposes a block-oriented device identity to a virtual machine or operating system.

The logical volume provides virtual capacity.

The storage pool decides how that virtual storage is backed by physical resources.

The extent mapper translates logical allocation into physical placement.

The physical device ultimately stores the blocks.

A key property of this architecture is **indirection**. A consumer can retain the same logical disk identity even when physical placement changes.

## Thick and Thin Provisioning

### Thick provisioning

A thick volume reserves its physical allocation during creation.

In the Python implementation, `create_volume(..., thin=False)` immediately allocates the required extents.

The C++ implementation performs the same operation through `VolumeMode::Thick`.

The SQL model represents this relationship by creating `storage_extent` rows associated with the volume before the volume has necessarily received user data.

Thick provisioning has predictable physical capacity requirements. If a pool has insufficient free capacity, creation fails before the volume becomes available.

### Thin provisioning

A thin volume separates advertised capacity from physical allocation.

The Python simulator creates a thin logical volume without immediately allocating all of its extents. A write operation invokes `_ensure_thin_block_capacity()` and allocates physical storage only when the logical block requires backing storage.

The JavaScript implementation performs the same conceptual operation through `ensureThinExtent()`.

Thin provisioning improves capacity utilization, especially when consumers request large logical disks but initially write only a fraction of the advertised capacity.

The operational trade-off is capacity overcommitment. A system may expose more virtual capacity than physically exists. This is safe only while actual consumption remains within the available backing capacity.

## Logical-to-Physical Translation

Suppose a virtual disk exposes logical block 64.

The consumer does not issue:

`write to nvme-02 at physical position 17`

Instead, it issues a logical operation against the virtual disk.

The virtualization layer determines:

- which logical volume owns the block,
- whether the block has physical backing,
- which extent covers the logical region,
- which physical device owns that extent,
- and where the physical storage is located.

The C++ case study stores these relationships through `Extent` and `LogicalBlock`.

The SQL implementation provides the same relationship through joins between `logical_block`, `logical_volume`, and `storage_extent`.

This separation is one of the defining properties of storage virtualization.

## Snapshot Semantics

A snapshot records the state of a logical volume at a particular generation.

The examples maintain block-level integrity metadata rather than duplicating every physical byte.

The Python snapshot records hashes of the source volume's blocks. When the source volume changes later, the snapshot's recorded state can be compared against the current volume.

The JavaScript and Java implementations use the same conceptual mechanism with language-specific data structures.

The SQL model separates snapshot metadata into:

- `storage_snapshot`
- `snapshot_block`

This allows snapshot identity and snapshot block state to be represented relationally.

A production snapshot system may use copy-on-write metadata, redirect-on-write mechanisms, reference counting, changed-block tracking, or storage-array-specific mechanisms. The educational implementations model the state relationship without claiming to reproduce a vendor's physical snapshot engine.

## Copy-on-Write Relationship

A snapshot must preserve a previous logical state while the active volume continues changing.

A common implementation strategy is copy-on-write.

Conceptually:

**Before modification**

`Snapshot → Original Block`

**When the active volume changes**

`Snapshot → Preserved Old Block`

`Active Volume → New Block`

The active volume and snapshot therefore acquire independent references to different physical representations of the changed data.

The code examples simplify this by retaining snapshot integrity metadata rather than implementing a complete block-reference-counting storage engine.

## Device Failure

Storage virtualization does not eliminate physical failures.

Instead, it creates an abstraction layer in which the failure can be represented separately from the logical identity of the volume.

The Python simulator marks a device as failed and evaluates volume health from the devices associated with its extents.

The JavaScript controller changes affected volumes to a read-only state and emits an alert event.

The Java enterprise model explicitly represents `DeviceState.FAILED` and `VolumeState.READ_ONLY`.

The C++ case study reports a volume as `DEGRADED` when one of its allocated extents resides on a failed device.

The exact production behavior would depend on redundancy. A replicated or RAID-backed design may remain fully available after a device failure, whereas a non-redundant mapping can become unavailable or degraded.

The examples intentionally distinguish **virtualization** from **redundancy**. Virtualization abstracts physical placement; redundancy provides additional copies or parity so that physical failure does not necessarily cause data loss or service interruption.

## Python Implementation

The Python program is a complete in-memory storage virtualization simulator.

`PhysicalDevice` models physical capacity and device state.

`StoragePool` owns physical devices, extents, logical volumes, snapshots, and allocation policy.

`LogicalVolume` records virtual capacity, provisioning mode, physical extents, and logical blocks.

`VirtualDisk` provides the consumer-facing interface.

`VirtualizationStack` makes the abstraction boundary explicit by exposing logical volumes as virtual disks.

The simulator demonstrates thick allocation, thin allocation, logical block validation, snapshots, device failures, inventory persistence, and utilization analysis.

The `status()` method intentionally reports both virtual and physical capacity because storage operations cannot be understood correctly by looking at only one of those values.

## JavaScript Implementation

The JavaScript implementation uses an event-driven storage controller.

`StoragePool` extends `EventEmitter`, allowing storage operations to produce events such as device addition, volume creation, writes, snapshot creation, and device failure.

This is appropriate for storage control software because monitoring, auditing, alerting, and orchestration frequently operate asynchronously around storage state changes.

The `VirtualDisk` methods are asynchronous and introduce a small simulated I/O delay. The purpose is not to reproduce real disk latency but to model the fact that storage operations commonly have asynchronous completion semantics.

The controller separates storage state from monitoring behavior. Audit consumers can subscribe to write events without modifying the allocation algorithm.

The implementation also demonstrates how a failed physical device can trigger an alert while the virtual disk identifier remains unchanged.

## C++ Case Study

The C++ program models an enterprise virtual-machine storage pool.

The physical layer contains multiple devices with finite capacity.

The storage pool chooses a physical device based on relative utilization rather than simply selecting the device with the largest absolute free capacity.

Logical volumes use either `VolumeMode::Thick` or `VolumeMode::Thin`.

Logical blocks contain a generation number so that state changes can be related to the evolution of the virtual storage state.

The snapshot model stores block integrity metadata at a particular generation.

The program also demonstrates failure handling. When a physical device fails, the volume remains identifiable through its logical name, but its health changes to `DEGRADED`.

This illustrates an important architectural distinction: a logical volume is a stable abstraction, while its physical backing is mutable infrastructure.

The C++ implementation uses maps and vectors because the storage controller needs keyed lookup for devices, volumes, extents, and blocks, while extent lists naturally represent the set of physical allocations belonging to a volume.

## Java Implementation

The Java implementation emphasizes enterprise domain modeling.

The `AllocationPolicy` interface separates the allocation rule from the storage pool itself.

`LeastUsedPolicy` implements one concrete placement strategy and orders candidate devices according to relative utilization.

This design allows the storage domain to replace the policy without rewriting the entire pool implementation.

Java records are used for immutable value-like objects such as `PhysicalDevice`, `Extent`, `BlockData`, and `Snapshot`.

Mutable state is kept inside the logical volume and storage pool where state transitions are required.

Volume state is explicitly represented by `VolumeState`, preventing storage policy from being encoded solely as strings or ad-hoc Boolean flags.

The device failure operation changes the affected logical volume to `READ_ONLY` in the demonstration. That models a governance decision made by the storage controller after detecting that physical backing is no longer fully healthy.

## SQL Data Model

The SQL implementation represents the virtualization hierarchy using foreign keys.

`storage_pool` represents the aggregation boundary.

`physical_device` represents physical resources.

`logical_volume` represents virtual capacity.

`virtual_disk` represents consumer-facing disk identities.

`storage_extent` represents physical allocation belonging to logical volumes.

`logical_block` represents logical data addresses.

`storage_snapshot` and `snapshot_block` represent snapshot state and its block-level integrity metadata.

The relationships are intentionally normalized rather than storing device names directly inside volume rows.

For example, an extent references both its logical volume and its physical device. This allows SQL queries to reconstruct the physical placement of a logical storage object.

## Database-Level Integrity

The database uses primary keys for identity and foreign keys for relationships.

`CHECK` constraints reject impossible capacities and negative utilization.

`UNIQUE` constraints prevent duplicate device names within a pool, duplicate volume names within a pool, duplicate virtual disk names, and duplicate snapshot names within a volume.

The `prevent_failed_device_allocation()` trigger prevents new extents from being assigned to a failed device.

The `synchronize_device_usage()` trigger keeps the physical device's recorded usage synchronized with extent insertion, deletion, and movement.

This illustrates why storage accounting should not depend entirely on application code. Capacity invariants that can be enforced at the database layer should not be left solely to an external application.

## Storage Capacity Accounting

There are several different capacity values.

**Physical capacity** is the sum of the capacities supplied by physical devices.

**Physical allocated capacity** is the capacity consumed by actual extents.

**Virtual capacity** is the capacity advertised through logical volumes.

For thick provisioning, virtual capacity normally requires corresponding physical reservation.

For thin provisioning, virtual capacity can exceed currently allocated physical capacity.

A capacity report should therefore expose at least:

`physical capacity`

`physical used`

`physical free`

`virtual capacity`

`physical allocation per volume`

A system that reports only virtual capacity can hide an impending physical-capacity problem.

## Allocation Policies

The examples use least-utilized allocation.

The policy compares relative device utilization:

`used capacity / total capacity`

This prevents a large device from automatically appearing less utilized merely because it has more absolute free space.

A production system may use considerably more information, including:

- device performance tiers,
- failure domains,
- RAID groups,
- replication requirements,
- latency,
- available IOPS,
- write endurance,
- encryption boundaries,
- locality,
- reserved capacity,
- and workload characteristics.

The important architectural point is that placement policy belongs in the storage-control layer rather than being exposed to the consumer as a physical-device selection problem.

## Performance Considerations

Storage virtualization introduces metadata and translation work.

A logical request can require several operations:

`logical address → volume metadata → extent mapping → physical placement → device I/O`

Caching can reduce repeated metadata lookups.

Indexes such as the SQL index on `(volume_id, logical_block)` accelerate logical block retrieval.

Indexes on `device_id` and `volume_id` accelerate physical-placement and capacity queries.

Thin provisioning adds allocation work during first writes to previously unbacked regions.

Snapshots can increase metadata pressure because changed blocks may require new mappings or preserved versions.

The performance cost of virtualization is not simply the cost of one extra lookup. Production systems also account for queueing, caching, metadata contention, network latency, multipath behavior, replication, and device scheduling.

## Failure and Recovery Boundaries

A failed physical device and a failed logical volume are different states.

A physical device can fail while a redundant virtual volume remains available.

A physical device can fail while a non-redundant logical volume becomes degraded or unavailable.

A logical volume can be healthy even though its physical allocation is distributed across several devices.

This is why the implementations do not equate a device's identity with the volume's identity.

Recovery may involve replacing a physical device, rebuilding redundant data, remapping extents, restoring snapshots, or moving workloads to another storage pool. The virtualization layer provides the abstraction necessary for these operations to occur without necessarily changing the consumer-facing virtual disk identity.

## Validation and Failure Conditions

The implementations reject invalid operations such as:

- zero or negative storage capacities,
- duplicate device identities,
- duplicate volume identities,
- allocations larger than available physical capacity,
- writes outside the logical volume,
- allocation to failed devices,
- invalid snapshot identities,
- and writes to volumes that have entered a non-writable state.

These checks are important because storage corruption can result when logical capacity rules are not enforced consistently.

The SQL implementation reinforces several of these rules with database constraints and triggers.

## Security Considerations

Storage virtualization does not automatically provide data confidentiality or authorization.

A production implementation must control who can:

- create logical volumes,
- expand virtual capacity,
- attach virtual disks,
- modify allocation mappings,
- create or delete snapshots,
- change device state,
- move extents,
- and access raw storage.

Administrative interfaces should authenticate operators and authorize operations according to least privilege.

Storage metadata can reveal workload structure, device topology, virtual-machine relationships, and capacity utilization. Such metadata should be protected like other infrastructure control-plane information.

Encryption at rest may operate below the virtualization layer, at the volume layer, or at the guest/filesystem layer depending on the architecture.

## Debugging Considerations

Storage virtualization failures should be investigated across layers rather than only at the consumer interface.

A useful diagnostic path is:

**Virtual Disk → Logical Volume → Extent Mapping → Physical Device → Device State**

If a virtual disk reports an I/O failure, the investigation should determine whether the failure originates from logical capacity, missing allocation, a failed physical device, an invalid mapping, or a lower-level device problem.

The implementations expose inventory and mapping information specifically to make this layered reasoning visible.

The SQL mapping query is particularly useful because it reconstructs the relationship between logical blocks, logical volumes, extents, and physical devices.

## Common Modeling Mistakes

Treating a logical volume as if it were a physical disk removes the primary benefit of virtualization.

Confusing virtual capacity with physical consumption produces incorrect capacity planning.

Assuming thin provisioning creates physical capacity is incorrect. Thin provisioning changes allocation timing and abstraction, not the amount of physical storage that ultimately exists.

Assuming virtualization provides redundancy is also incorrect. Abstraction and redundancy solve different problems.

Allowing failed devices to receive new allocations can create immediately invalid storage mappings.

Keeping physical placement directly inside consumer-facing objects makes migrations and rebalancing substantially harder because every consumer becomes coupled to infrastructure identity.

## Practical Relationship Between the Layers

The four central concepts answer different questions.

**Storage pools** answer: *Which physical resources are available to the allocation system?*

**Logical volumes** answer: *How much virtual storage should be presented as one logical storage object?*

**Virtual disks** answer: *What storage device identity should the consumer interact with?*

**Abstraction layers** answer: *How can the consumer use storage without depending on the physical implementation?*

Their relationship can therefore be expressed as:

**Physical devices provide resources → storage pools aggregate resources → logical volumes allocate virtual capacity → virtual disks expose that capacity through a stable consumer-facing interface.**

That separation is the core design principle demonstrated throughout the six deliverables.
