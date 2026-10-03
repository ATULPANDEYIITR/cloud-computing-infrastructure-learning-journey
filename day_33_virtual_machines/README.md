# Virtual Machines: Lifecycle, CPU Allocation, Memory Allocation, Virtual Disks, and Snapshots

## Scope

This repository studies the control-plane mechanisms required to manage virtual machines on a shared host. The implementations model five tightly connected areas:

- VM lifecycle management, including creation, start, stop, pause, resume, suspension, and deletion.
- CPU allocation, including vCPU counts, CPU shares, CPU limits, and optional CPU pinning.
- Memory allocation, including configured memory, reservations, hard limits, and ballooning as a modeled capability.
- Virtual disks, including capacity, allocated backing storage, thin provisioning, disk formats, read-only behavior, expansion, and simulated writes.
- Snapshots, including point-in-time VM configuration and disk-state capture followed by restoration.

The programs are simulations of a virtualization management layer. They do not invoke KVM, QEMU, VMware, Hyper-V, VirtualBox, or another hypervisor. This distinction is important: a real hypervisor must also manage hardware virtualization extensions, guest memory mappings, device emulation, virtual interrupts, storage backends, networking, process isolation, and persistent VM metadata.

The three implementations deliberately approach the same domain from different perspectives. Python emphasizes an explicit resource-management model, JavaScript emphasizes an event-driven control plane, and C++ builds a more strongly typed host-governance case study.

## Virtual Machine Architecture

A VM is not simply a process with a name. A management system normally tracks several independent resource domains and combines them into one lifecycle object.

A simplified model is:

    Physical Host
    |
    +-- CPU scheduler
    |    +-- VM A: vCPUs, shares, limits, pinning
    |    +-- VM B: vCPUs, shares, limits, pinning
    |
    +-- Memory manager
    |    +-- VM A: configured memory, reservation, limit
    |    +-- VM B: configured memory, reservation, limit
    |
    +-- Storage subsystem
    |    +-- VM A: OS disk, data disk
    |    +-- VM B: OS disk
    |
    +-- VM lifecycle controller
    |    +-- defined
    |    +-- stopped
    |    +-- running
    |    +-- paused
    |    +-- suspended
    |    +-- error
    |
    +-- Snapshot manager
         +-- snapshot metadata
         +-- disk state
         +-- VM configuration state

The lifecycle controller coordinates the other components. Starting a VM is not equivalent to merely changing a string from `stopped` to `running`: a production implementation must verify that the requested CPU and memory resources can be honored, that storage is available, and that the underlying hypervisor can instantiate the required devices.

## VM Lifecycle

The Python, JavaScript, and C++ programs use explicit VM states because lifecycle state determines which operations are legal.

A representative lifecycle is:

    defined -> stopped -> running
                         |  |
                         |  +-> paused -> running
                         |
                         +-> suspended -> stopped

A newly created VM enters the stopped state after its configuration has passed validation. A running VM can be paused while retaining its execution context in memory. It can later resume from the paused state.

Suspension has a different operational meaning. A real hypervisor can persist the guest's execution state so that the host can release active memory and CPU resources. Restoring that suspended state requires persistent VM state to be valid and compatible with the host environment.

The implementations intentionally prevent invalid transitions. For example, attempting to resume a stopped VM is rejected because the program distinguishes a paused execution context from a VM that is simply powered off.

A production lifecycle controller also has to account for asynchronous failures. A start request may be accepted by a control API and fail later because a storage backend is unavailable, a device cannot be initialized, or the host lacks a required resource. Therefore real systems commonly maintain operation identifiers, event streams, logs, and explicit failure states.

## CPU Allocation

### vCPUs

A vCPU represents a virtual processor exposed to the guest operating system. The guest sees the configured vCPU topology, while the hypervisor maps virtual execution onto physical or logical host CPUs.

The number of vCPUs is a capacity setting, not a guarantee that the VM will continuously consume that many physical CPUs.

For example, a VM configured with four vCPUs can execute four parallel guest threads when sufficient host CPU capacity exists. If many VMs compete for the same physical CPUs, the hypervisor scheduler determines when each vCPU is actually dispatched.

The implementations validate that a VM cannot request more vCPUs than the modeled host exposes.

### CPU shares

CPU shares represent relative scheduling weight. If two running VMs have different shares and are both CPU constrained, the scheduler can distribute available CPU time according to their relative weights.

The Python and JavaScript models calculate a weighted entitlement using:

    VM entitlement =
        total host CPU time
        × VM shares / total active shares

This is deliberately a scheduling model rather than a claim about a particular hypervisor's exact scheduler implementation.

For example, a VM with 2048 shares receives twice the proportional scheduling weight of another VM with 1024 shares when all other modeled conditions are equal.

Shares matter most during contention. If the host has idle CPU capacity, a VM does not necessarily need to wait for its weighted share.

### CPU limits

A CPU limit imposes an upper bound on modeled consumption. The implementations calculate a limit based on vCPU count, duration, and the configured percentage.

A four-vCPU VM with a 50% limit has a modeled maximum of two physical CPU-equivalent units over a continuous interval, subject to the scheduler model.

Shares and limits therefore serve different purposes:

| Mechanism | Meaning |
| --- | --- |
| vCPU count | Virtual processor capacity exposed to the guest |
| CPU shares | Relative scheduling weight during contention |
| CPU limit | Upper bound on CPU consumption |
| CPU pinning | Association between selected vCPUs and host CPUs |

Treating shares and limits as synonyms is a common resource-management mistake.

### CPU pinning

CPU pinning associates a vCPU with selected physical or logical host CPU identifiers. Pinning can be useful for workloads requiring predictable CPU placement, but it reduces scheduler flexibility.

The Python, JavaScript, and C++ models validate that a pinned vCPU index exists and that the target host CPU exists.

Real CPU placement is substantially more complex because modern hosts have NUMA topology, SMT or hyper-threading, CPU frequency scaling, interrupt processing, and other workloads competing for processor resources.

## Memory Allocation

The memory model distinguishes configured memory, reservation, and limit.

### Configured memory

Configured memory is the amount of guest-visible RAM presented to the VM.

A guest configured with 8 GB expects the virtual hardware to expose that memory capacity. The hypervisor then maps guest physical memory to host resources.

### Reservation

A reservation represents host memory that the management system promises to make available to the VM.

Reservations are useful for capacity planning because the aggregate reservation can be compared with host memory before a VM is admitted.

The implementations therefore calculate host memory consumption from VM reservations rather than simply summing every VM's hard limit.

This distinction matters when several VMs have large limits but only a portion of that memory is guaranteed.

### Hard limit

A memory limit prevents the modeled VM allocation from exceeding a specified upper boundary.

The implementations reject configurations where the limit is below configured memory. They also reject a limit above physical host memory in the model.

### Ballooning

Memory ballooning allows a hypervisor and guest cooperation mechanism to adjust memory pressure dynamically. A balloon driver inside the guest can make selected guest memory available to the hypervisor under memory pressure.

The programs retain a `ballooning` property so that the configuration model can distinguish VMs that permit this behavior. They do not implement an actual guest balloon driver because that requires guest-kernel and hypervisor integration.

Ballooning also has an important operational limitation: reclaimed guest memory is not equivalent to arbitrary host memory. The guest must cooperate, and reclaiming memory can affect application performance.

## Virtual Disks

A virtual disk provides block storage to the guest. The guest normally sees a virtual block device while the hypervisor maps requests to an underlying storage object.

The model tracks:

- Virtual capacity.
- Current allocated backing storage.
- Disk format.
- Thin or thick provisioning.
- Read-only state.

### Virtual capacity versus physical allocation

These values are deliberately separate.

A 200 GB thin-provisioned disk may currently consume only 80 GB of physical storage. The guest can still observe a 200 GB virtual disk.

The storage subsystem must nevertheless ensure that physical backing capacity can grow as the guest writes data.

This is why the Python and JavaScript implementations check host storage when simulated writes occur on thin-provisioned disks.

### Thin provisioning

Thin provisioning allocates physical storage progressively.

The advantages include improved utilization and the ability to present large logical disks without immediately consuming the complete physical capacity.

The primary operational risk is overcommit. If several thin-provisioned disks collectively advertise much more logical capacity than the storage backend can eventually provide, the host can run out of physical space.

A production platform therefore monitors:

    physical capacity
    physical allocation
    logical capacity
    write growth rate
    snapshot overhead
    storage alerts

### Thick provisioning

A thick-provisioned disk reserves its physical backing capacity up front or according to the storage backend's equivalent semantics.

This can provide stronger capacity predictability, but it consumes storage earlier.

The C++ case study treats expansion of a thick disk as consuming additional host capacity immediately, while thin disk expansion changes virtual capacity without assuming the entire expansion is physically allocated.

### Disk expansion

Expanding a virtual disk is different from shrinking it.

Expansion normally involves:

    virtual disk capacity increase
            |
            v
    guest-visible device capacity
            |
            v
    guest partition/filesystem expansion

The first operation does not automatically resize the guest filesystem. A production workflow therefore needs coordination between the virtual hardware layer and the guest operating system.

The simulations model only the virtualization layer.

### Disk writes

A disk write changes allocated backing storage in the model. It is rejected when:

- The disk is read-only.
- The write is negative.
- The write exceeds virtual disk capacity.
- A thin-provisioned backing store has insufficient host capacity.
- The VM is not in a state where simulated I/O is permitted.

These checks represent control-plane validation rather than a real block-I/O implementation.

## Snapshots

A snapshot captures a point-in-time representation of VM state.

The programs capture:

- VM lifecycle state at the time of capture.
- CPU allocation.
- Memory allocation.
- Virtual disk allocation values.
- Snapshot metadata.

The snapshot is then used to restore those values.

A production snapshot implementation can be much more sophisticated. Many systems use copy-on-write storage, differencing disks, snapshot chains, metadata records, and optional guest memory state.

### Copy-on-write relationship

A simplified snapshot storage model is:

    Base disk
       |
       +---- snapshot reference
       |
       +---- current VM writes
                |
                +---- changed blocks

Instead of immediately copying every disk block, a storage layer can preserve the original block and redirect later writes to a new location.

This makes snapshot creation potentially much faster than copying an entire disk, but it creates a dependency chain between the original disk and subsequent writes.

### Snapshot restoration

Restoration is treated as a controlled operation. The programs require the VM to be stopped before restoring a snapshot.

That rule avoids simultaneously changing the VM's active execution state and its persisted configuration.

Real platforms may support live snapshot operations, but those require coordinated handling of memory consistency, device state, filesystem consistency, and storage writes.

### Snapshot consistency

A snapshot is not automatically equivalent to an application-consistent backup.

For example, a database may have outstanding transactions when a disk snapshot occurs. A crash-consistent snapshot may capture storage state equivalent to a sudden power loss. An application-consistent workflow can require guest coordination, database flushing, filesystem synchronization, or a dedicated backup mechanism.

Snapshots should therefore not automatically be treated as a complete backup strategy.

## Python Implementation

The Python program implements a `Hypervisor` control-plane class containing VM objects and host-level resource accounting.

`VirtualMachine` contains:

- `CPUAllocation`
- `MemoryAllocation`
- virtual disks
- lifecycle state
- snapshot records
- simulated uptime

`CPUAllocation.validate()` checks vCPU capacity, CPU limits, CPU shares, and pinning. `MemoryAllocation.validate()` enforces the relationship between configured memory, reservation, and limit.

The `Hypervisor.create_vm()` method performs admission control before registering the VM. It checks aggregate memory reservations and physical disk allocation against host capacity.

The lifecycle methods explicitly constrain valid transitions. `pause_vm()`, `resume_vm()`, `suspend_vm()`, and `stop_vm()` therefore represent distinct operational states rather than aliases.

`allocate_cpu_time()` demonstrates weighted CPU scheduling. It calculates a host CPU-time pool and divides it according to active VM CPU shares before applying each VM's CPU limit.

The disk implementation separates virtual capacity from allocated backing space. Thin-provisioned disks therefore consume backing storage progressively.

The snapshot implementation captures CPU, memory, and disk-allocation metadata. Reverting a snapshot reconstructs those configuration values and restores the recorded disk allocation.

The program also serializes its inventory into JSON inside a temporary directory. This demonstrates the distinction between an in-memory control model and persistent operational state without introducing an external database dependency.

## JavaScript Implementation

The JavaScript program uses Node.js's `EventEmitter` to represent an event-driven virtualization control plane.

This is intentionally different from the Python implementation. Instead of treating operations primarily as direct method calls, the JavaScript version emits events such as:

- `vm-created`
- `state-changed`
- `memory-resized`
- `disk-expanded`
- `disk-write`
- `snapshot-created`
- `snapshot-reverted`
- `snapshot-deleted`

This architecture reflects a common management-system pattern where resource operations generate events that can feed logging, monitoring, audit trails, asynchronous workflows, and user interfaces.

`CPUAllocation`, `MemoryAllocation`, and `VirtualDisk` encapsulate resource-specific validation.

The `Hypervisor` class manages admission control and lifecycle transitions. Its CPU allocation method calculates weighted CPU entitlement for all running VMs and then caps each result using its CPU limit.

The JavaScript snapshot model clones the VM's CPU configuration, memory configuration, and virtual disks. This is deliberately implemented as object cloning rather than simply retaining references. Without cloning, later changes to a disk could unintentionally mutate what was supposed to represent the historical snapshot state.

The program also persists an inventory using Node.js's standard filesystem API. The temporary directory is removed after the demonstration, keeping the example self-contained.

## C++ Case Study

The C++ program models a private-cloud host called `private-cloud-01`.

It contains two workloads:

- `database` uses four vCPUs, a larger memory reservation, CPU pinning for selected vCPUs, and separate operating-system and database disks.
- `ci-worker` uses two vCPUs, a smaller memory allocation, and a thick-provisioned operating-system disk.

This creates meaningful resource competition on an eight-vCPU, 16 GB memory, 500 GB storage host.

The `Hypervisor` class owns VM instances through `std::unique_ptr`, which gives the control plane explicit ownership of its managed VM objects.

`std::map` is used for VM lookup and snapshot lookup because deterministic ordering is useful for inventory output and snapshot identification.

The CPU scheduler calculates weighted CPU time using each running VM's CPU shares and then applies the configured CPU limit. This demonstrates the distinction between relative scheduling weight and an absolute consumption boundary.

The memory manager performs host admission checks based on reservations. A resize operation first validates the new VM configuration and then verifies that the additional reservation fits within the unreserved host memory.

The disk subsystem models both thin and thick provisioning. Expanding a thick disk immediately consumes modeled host capacity, whereas expanding a thin disk changes virtual capacity without assuming that the complete new capacity is physically allocated.

The snapshot engine captures VM configuration and disk allocation. Restoration is restricted while the VM is running, then the saved CPU and memory configuration and disk allocation values are reapplied.

The C++ implementation uses exceptions for invalid state transitions, resource exhaustion, invalid disk operations, missing VMs, missing disks, and incompatible snapshot state.

## Relationship Between the Resource Domains

VM lifecycle and resource allocation are separate concepts, but they interact.

A stopped VM may retain its configured CPU and memory reservation without actively consuming CPU execution time. Starting it turns those configuration values into an active workload.

Similarly, a virtual disk can exist while a VM is stopped. Storage allocation is therefore not inherently tied to CPU execution.

Snapshots span several domains because they preserve a coordinated historical point across VM configuration and storage state.

A useful conceptual relationship is:

    VM lifecycle
         |
         +---- determines whether execution is active
         |
         +---- activates CPU scheduling
         |
         +---- permits guest I/O
         |
         +---- interacts with memory availability
         |
         +---- interacts with snapshot consistency

    Resource configuration
         |
         +---- CPU: vCPUs / shares / limits / pinning
         |
         +---- Memory: configured / reservation / limit
         |
         +---- Storage: capacity / allocation / provisioning

    Snapshot
         |
         +---- captures selected configuration
         +---- captures storage state
         +---- supports restoration

## Admission Control and Capacity Planning

A virtualization host must distinguish several capacity measures.

For CPU:

    configured vCPUs
    versus
    physical/logical host CPUs

For memory:

    VM configured memory
    versus
    reserved memory
    versus
    physical host memory

For storage:

    virtual disk capacity
    versus
    physical allocated storage
    versus
    total backing-store capacity

These quantities cannot safely be treated as interchangeable.

For example, ten thin-provisioned 200 GB disks represent 2 TB of logical capacity, but their current physical allocation could be much smaller. The storage platform still needs a policy for the possibility that the guests eventually consume most of their logical capacity.

The Python, JavaScript, and C++ programs therefore use explicit resource accounting instead of assuming that VM configuration alone is sufficient.

## Edge Cases and Failure Conditions

The implementations deliberately reject several unsafe operations.

### CPU failures

A VM cannot request more vCPUs than the modeled host exposes. CPU limits cannot be below the minimum permitted value or above the VM's vCPU-equivalent maximum. CPU pinning cannot reference nonexistent vCPUs or physical CPUs.

### Memory failures

Memory reservations cannot exceed configured VM memory. A hard memory limit cannot be below configured memory. Host admission fails when aggregate reservations exceed host capacity.

### Disk failures

Disk creation rejects zero or negative capacity. Allocated backing storage cannot exceed virtual capacity. Writes to read-only disks fail. Writes that exceed virtual capacity fail. Thin-provisioned writes can fail when the physical backing store is exhausted.

### Lifecycle failures

A VM cannot be paused unless it is running. A paused VM can be resumed. A stopped VM cannot be resumed as though it were paused. Suspension is allowed only from the running state in the model.

### Snapshot failures

Snapshot identifiers must be unique. Restoration requires a valid snapshot. The programs prevent restoration while the VM is running because the case study models restoration as a stopped-VM operation.

## Common Design Mistakes

Treating vCPU count as guaranteed physical CPU time creates incorrect capacity expectations. vCPUs describe virtual processor topology, while scheduling determines physical execution.

Treating configured memory as equivalent to reserved memory leads to inaccurate admission control. A platform needs a clearly defined relationship between reservation, limit, overcommit, and reclamation.

Treating a virtual disk's logical capacity as physical storage consumption is dangerous for thin provisioning. Physical storage can grow as the guest writes.

Treating snapshots as full backups can produce incorrect recovery assumptions. A snapshot may depend on its underlying disk chain and may not provide application-consistent recovery.

Using lifecycle states without validating transitions can create impossible control-plane states, such as attempting to resume a powered-off VM as though it were paused.

Keeping references to mutable objects inside snapshots can destroy snapshot isolation. The JavaScript implementation avoids this by cloning resource objects when creating a snapshot.

## Performance Considerations

CPU scheduling requires repeated accounting across active VMs. A simple weighted allocation pass is approximately O(V), where V is the number of running VMs.

VM lookup using a hash-based structure is typically O(1) average-case, while the C++ case study uses ordered maps to provide deterministic traversal and predictable ordered inventory output.

Snapshot performance depends heavily on storage implementation. A metadata-only snapshot model is inexpensive, while copying an entire multi-terabyte disk is expensive in both time and storage.

Copy-on-write snapshots reduce initial snapshot cost but can increase metadata complexity and introduce storage-chain performance considerations.

Memory overcommit can improve utilization but introduces pressure-management complexity. Ballooning, host swapping, compression, reclamation, and workload behavior can all affect performance in a real implementation.

## Security and Isolation Considerations

A production hypervisor must treat VM boundaries as security boundaries.

Resource accounting alone is not sufficient. The underlying virtualization layer must isolate guest memory, CPU state, device access, and storage access.

Virtual disk operations must enforce authorization. A control-plane caller permitted to resize one VM's disk should not automatically receive access to another VM's storage.

Snapshot access also requires authorization because snapshots may contain sensitive application data and credentials.

Administrative APIs should authenticate callers, authorize resource-specific actions, record audit events, and protect state-changing operations from unauthorized use.

Disk images and snapshot metadata should be protected against accidental or malicious modification. Encryption at rest may be required depending on the sensitivity of guest data.

The simulated programs do not implement authentication or encryption because those features belong to a larger management service rather than the core resource-allocation model.

## Production Considerations

A real VM management platform would need additional components that are intentionally outside these self-contained simulations.

A production architecture would normally need durable VM metadata, transactional state changes, locking or concurrency control, host discovery, actual hypervisor APIs, storage backends, network configuration, authentication, authorization, audit logging, metrics, health monitoring, failure recovery, and reconciliation.

Resource operations should also be idempotent where possible. A repeated request to stop an already stopped VM should have a defined outcome rather than causing an ambiguous state transition.

Long-running operations should not rely exclusively on synchronous request execution. Creating a large disk, migrating a VM, restoring a large snapshot, or starting a complex guest can take significant time. An operational API may therefore return an operation identifier and expose progress separately.

The control plane should reconcile desired state with observed state. If its database says a VM is running but the underlying hypervisor reports that the VM has stopped, the discrepancy must be detected and resolved rather than silently trusted.

## Implementation Boundaries

The programs intentionally simulate virtualization concepts rather than claiming to be hypervisors.

They do not implement:

- Hardware virtualization instructions.
- Guest page-table management.
- Actual vCPU threads.
- Real CPU scheduling.
- NUMA-aware placement.
- Actual memory balloon drivers.
- Guest filesystem resizing.
- Real block-device I/O.
- Copy-on-write disk chains.
- Live migration.
- Device emulation.
- Virtual networking.
- Guest operating-system interaction.

Those mechanisms require integration with an actual virtualization stack and operating-system facilities.

The value of these implementations is the control-plane reasoning they expose: resource configuration must be validated, lifecycle transitions must be constrained, shared host capacity must be accounted for, storage capacity must be distinguished from logical disk capacity, and snapshot operations must preserve a coherent representation of prior VM state.
