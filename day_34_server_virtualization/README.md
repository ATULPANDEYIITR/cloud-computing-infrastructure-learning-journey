# Server Virtualization: Resource Sharing, VM Isolation, Overcommitment, and Host Management

## Scope

Server virtualization abstracts physical computing resources into isolated virtual machines (VMs). A physical virtualization host can run multiple guest operating systems while presenting each guest with virtual CPUs, memory, storage, and network interfaces.

This repository treats four closely related mechanisms as distinct engineering concerns:

- **Resource sharing** determines how physical CPU, memory, storage, and network capacity is distributed among active VMs.
- **VM isolation** establishes the boundary between guests so that one VM cannot directly manipulate another VM's private execution state.
- **Overcommitment** permits the sum of configured virtual resources to exceed available physical resources under controlled assumptions about workload demand.
- **Host management** coordinates VM placement, lifecycle operations, scheduling, monitoring, resource reclamation, capacity decisions, and migration admission.

The implementations deliberately approach the subject from different perspectives. Python provides a resource-allocation simulator, JavaScript models event-driven host management and asynchronous monitoring, and C++ implements a private-cloud governance case study with explicit resource policies.

---

## Virtualization Model

A virtualization host has finite physical resources:

| Physical resource | Virtual representation | Primary contention mechanism |
| --- | --- | --- |
| CPU cores | vCPUs | Scheduling and CPU throttling |
| RAM | Virtual memory | Allocation, reclamation, ballooning, or swapping |
| Storage | Virtual disks | Capacity and I/O contention |
| Network | Virtual network interfaces | Bandwidth and packet-processing contention |

A VM does not receive an independent physical server. It receives a virtual hardware contract that is backed by shared physical infrastructure.

For example, a host with 8 physical CPU cores may run VMs configured with a combined total of 16 vCPUs. This is CPU overcommitment. The configuration is feasible only because the hypervisor can schedule runnable virtual CPUs onto the available physical cores and because workloads do not necessarily demand all configured vCPUs continuously.

Memory is more restrictive. A host with 32 GB of RAM cannot simultaneously provide 40 GB of actively resident physical memory without a reclamation mechanism or another form of memory backing. Memory overcommitment therefore requires careful monitoring and can produce substantially different failure behavior from CPU overcommitment.

---

## Resource Sharing

Resource sharing is the mechanism through which multiple VMs consume the same physical host.

The Python implementation represents a host with explicit CPU, memory, storage, and network capacities. Each VM has a virtual resource allocation and can independently generate workload demand.

The important distinction is between **configured capacity** and **current demand**.

A VM can have:

- 4 configured vCPUs but currently require only 1.5 CPU units.
- 10 GB of configured memory but actively require only 6 GB.
- A CPU reservation that must be protected during contention.
- A CPU share weight that influences distribution of unreserved CPU.
- A resource limit that prevents consumption beyond a configured ceiling.

This separation makes it possible for a host to consolidate workloads efficiently without assuming that every VM consumes its maximum configuration continuously.

### CPU sharing

The Python scheduler uses two stages.

First, configured CPU reservations are satisfied up to each VM's actual demand and CPU limit.

The remaining physical CPU capacity is then distributed according to CPU shares. A VM with 400 shares has twice the relative scheduling weight of a VM with 200 shares when both are competing for the same unreserved capacity.

Shares are therefore **relative**, not guaranteed. A VM with 500 shares does not automatically receive 500 CPU units or 500 percent of a processor.

The C++ implementation uses the same resource-management distinction while structuring it as a private-cloud host engine. Its `scheduleCPU()` method first accounts for reservations and then repeatedly distributes remaining CPU according to weighted shares.

### Memory sharing

Memory sharing has a different constraint because active memory ultimately requires physical backing.

The Python and C++ implementations simulate memory reclamation. When active memory demand exceeds physical RAM, each VM can surrender non-reserved memory. The amount reclaimed is proportional to reclaimable demand.

The simulator calls this mechanism ballooning. In a real virtualization platform, memory management can involve guest balloon drivers, hypervisor reclamation, host swapping, transparent page sharing, compression, or other platform-specific mechanisms.

The important engineering principle is that memory pressure must be observable and managed before the host reaches an unrecoverable condition.

---

## VM Isolation

VM isolation is separate from resource scheduling.

A host can allow two VMs to share physical CPU cores without allowing either VM to read or modify the other's private memory.

The virtualization boundary normally involves mechanisms such as:

- Hardware-assisted virtualization.
- Second-level address translation.
- Hypervisor-controlled virtual CPU execution.
- Virtual device mediation.
- Virtual network separation.
- Controlled storage access.
- I/O device assignment policies.

The Python `IsolationManager` models this boundary at policy level. Its `can_access()` method does not grant one VM arbitrary access to another VM merely because both VMs reside on the same host or belong to a similar operational category.

The JavaScript implementation adds an explicit network isolation model. VMs are assigned to network segments, and communication is blocked unless an explicit policy relationship has been created.

This distinction is important because network isolation and memory isolation solve different problems. A firewall rule can prevent network communication, but it is not a substitute for hypervisor-enforced memory isolation. Conversely, memory isolation does not automatically determine whether two VMs should communicate over a virtual network.

### Isolation failure considerations

A virtualization platform must treat escape from the guest boundary as a high-severity security event. Relevant risks include:

- Hypervisor vulnerabilities.
- Vulnerable virtual device emulation.
- Incorrect I/O device assignment.
- Misconfigured virtual networking.
- Shared storage permissions.
- Host management-plane exposure.
- Excessive administrative privileges.
- Untrusted VM images.

Resource controls do not automatically provide security isolation. A VM with a CPU limit can still be incorrectly exposed through a vulnerable virtual device or management interface.

---

## Overcommitment

Overcommitment is the deliberate allocation of more virtual resources than physically exist.

### CPU overcommitment

Suppose a host has 8 physical cores:

`VM-A = 4 vCPU`

`VM-B = 4 vCPU`

`VM-C = 4 vCPU`

The host has allocated 12 vCPUs against 8 physical cores, giving a CPU allocation ratio of:

`12 / 8 = 1.50x`

This does not mean the host immediately fails. If VM-A requires 1 CPU, VM-B requires 2 CPUs, and VM-C requires 1 CPU, only 4 physical cores are needed at that instant.

The risk appears when simultaneous demand approaches or exceeds physical capacity. The scheduler then has to delay runnable virtual CPUs, producing contention and potentially increased application latency.

The Python monitoring simulation reports CPU throttling when a VM's demand cannot be satisfied by the scheduler.

### Memory overcommitment

Memory overcommitment is more sensitive because active guest memory needs physical backing.

For a host with 32 GB RAM:

`VM-A = 16 GB`

`VM-B = 16 GB`

`VM-C = 16 GB`

The configured allocation is 48 GB, or:

`48 / 32 = 1.50x`

If the active working sets remain below 32 GB, the configuration may remain operational. If all three VMs require their full memory simultaneously, the host must reclaim memory or use another backing mechanism.

The Python and C++ simulators explicitly protect memory reservations during reclamation. If physical memory is exhausted and no reclaimable non-reserved memory remains, the simulator treats this as a failure condition rather than silently pretending that physical RAM is unlimited.

### Why overcommitment is a policy decision

Overcommitment should be based on workload characteristics rather than a fixed universal ratio.

Suitable workloads often have:

- Bursty CPU utilization.
- Significant periods of idle time.
- Predictable memory working sets.
- Measurable historical demand.
- Clear service-level objectives.

Risk increases for workloads with:

- Sustained CPU saturation.
- Large memory working sets.
- Highly synchronized traffic spikes.
- Low latency requirements.
- Unpredictable memory allocation.
- Strong performance isolation requirements.

---

## Reservations, Shares, and Limits

These controls have different semantics.

| Control | Meaning | Effect during contention |
| --- | --- | --- |
| Reservation | Minimum resource commitment | Protects a defined amount when the platform can honor the policy |
| Shares | Relative scheduling weight | Determines how remaining contested capacity is divided |
| Limit | Maximum permitted consumption | Prevents the VM from exceeding a configured ceiling |

Confusing these mechanisms produces incorrect capacity plans.

A VM with high shares does not necessarily have a guaranteed minimum. A reservation is the mechanism that expresses a minimum resource commitment.

Similarly, a limit is not an allocation. Setting a VM's CPU limit to 4 vCPUs does not reserve four physical cores for that VM.

The Python `VM` class exposes these controls directly. The C++ case study uses them in the `payments-db`, `checkout-api`, `reporting`, and `monitoring` workloads to demonstrate differentiated service requirements.

---

## Host Management

Host management is the control layer responsible for maintaining the physical virtualization environment.

The Python `Host` class performs:

- VM admission.
- Resource accounting.
- VM removal validation.
- CPU scheduling.
- Memory reclamation.
- Host health calculation.
- Migration admission checks.

The JavaScript implementation models host management as an event-driven system. `VirtualizationHost` extends Node.js `EventEmitter`, allowing resource and lifecycle changes to produce events such as VM admission, VM startup, VM shutdown, and resource-allocation cycles.

This event model reflects a common production architecture in which infrastructure components react to state changes rather than continuously embedding all management behavior inside one synchronous operation.

### Host admission

Before a VM is placed on a host, the manager checks projected resource consumption.

Storage and network capacity are treated as hard admission constraints in the examples. CPU and memory can be overcommitted only when the host policy allows it.

This distinction matters because not every resource can be safely overcommitted in the same way.

A host may tolerate a CPU allocation ratio above 1.0 while still requiring storage capacity to remain within a hard physical boundary.

---

## VM Lifecycle

The implementations model a basic VM lifecycle:

`stopped -> running -> paused -> running`

and failure transitions such as:

`running -> failed`

A stopped VM consumes configured capacity in the host accounting model but does not generate active workload demand.

A running VM participates in CPU scheduling and memory management.

A paused VM remains allocated but is not treated as actively consuming workload resources by the scheduler.

A failed VM is not treated as an ordinary running workload. The Python implementation prevents a failed VM from being started without first returning it to an appropriate lifecycle state.

Production lifecycle systems require more state than the simplified model, including creation, provisioning, booting, migration, suspended, snapshot operations, recovery, deletion, and hardware-dependent failure states.

---

## Python Implementation

The Python program is a complete resource-management simulator.

Its main structures are:

- `HostResources` describes physical CPU, memory, storage, and network capacity.
- `VM` represents virtual hardware, reservations, limits, shares, state, and workload demand.
- `Host` performs admission control, scheduling, memory reclamation, monitoring, and migration checks.
- `IsolationManager` models the separation between guest workloads.
- `Allocation` records the result of a scheduling cycle.
- `HostHealth` aggregates operational indicators.

The `schedule_cpu()` implementation is particularly important because it demonstrates the difference between guaranteed resources and weighted resource sharing.

The `manage_memory()` method models memory pressure. It calculates the demand deficit, identifies memory that is not protected by a reservation, and distributes simulated reclamation across VMs.

The monitoring simulation changes VM demand across multiple intervals. This demonstrates why virtualization capacity cannot be evaluated only from static VM configuration. A host can have a high virtual allocation ratio but experience low actual utilization, or it can have moderate allocation and still experience severe synchronized workload pressure.

The script also contains migration admission checks and explicit validation failures. These represent control-plane operations rather than actual hypervisor migration.

Run it with:

`python server_virtualization.py`

No third-party Python package is required.

---

## JavaScript Implementation

The JavaScript program emphasizes event-driven host management.

`VirtualizationHost` extends Node.js `EventEmitter`. Operations such as VM admission, startup, shutdown, and scheduling produce events that other parts of the management layer can observe.

This is different from the Python implementation's direct procedural flow. The JavaScript version models a management plane in which infrastructure events can trigger logging, monitoring, alerting, or downstream control actions.

The `VirtualMachine.transition()` method defines legal lifecycle transitions instead of allowing arbitrary state changes.

The `collectWorkload()` function is asynchronous and returns a Promise. The monitoring cycle uses `Promise.all()` so that workload information for multiple VMs can be collected concurrently.

The isolation implementation introduces network segments and explicit communication permissions. This focuses on policy-driven connectivity rather than attempting to reproduce the Python memory-access model.

The JavaScript host also performs migration admission checks against destination capacity and overcommitment policy.

Run it with:

`node server_virtualization.js`

No npm dependency is required.

---

## C++ Private-Cloud Case Study

The C++ program models a private cloud operator running several production-like workloads on one virtualization host.

The central host is `hv-prod-01`.

Its VMs have deliberately different resource policies:

- `payments-db` has a CPU reservation, memory reservation, high CPU shares, and explicit CPU and memory limits. This represents a more critical transactional workload.
- `checkout-api` has moderate reservations and a higher scheduling weight than the analytics workload.
- `reporting` has substantial virtual resources but a lower CPU share, representing a workload that can tolerate lower priority during contention.
- `monitoring` has a smaller resource footprint and a bounded CPU allocation.

The host's `scheduleCPU()` method uses reservations before distributing remaining CPU by shares.

The `reclaimMemory()` method calculates the physical memory deficit and reclaims non-reserved memory. If the host cannot reclaim enough memory because all remaining memory is protected by reservations, the model marks the affected running VMs as failed.

The case study also includes:

- Configuration validation.
- Strict admission control.
- Migration destination checks.
- VM isolation checks.
- Randomized burst-demand simulation.
- CPU contention reporting.
- Memory reclamation reporting.

Compile with a C++17 compiler:

`g++ -std=c++17 -O2 server_virtualization.cpp -o server_virtualization`

Then run:

`./server_virtualization`

On Windows with MinGW, the resulting executable can be started as:

`server_virtualization.exe`

---

## Resource Allocation Workflow

A simplified management workflow represented by the implementations is:

`VM request -> admission checks -> host placement -> VM lifecycle -> workload demand -> scheduling -> monitoring -> pressure handling -> migration or recovery`

The stages have different responsibilities.

**Admission** decides whether the host can accept the virtual hardware contract.

**Scheduling** determines how available physical CPU is distributed among active demand.

**Memory management** determines whether active memory demand fits physical capacity and whether reclaimable memory exists.

**Isolation** ensures resource sharing does not imply unrestricted guest-to-guest access.

**Monitoring** observes whether the configured policies remain appropriate under actual workload conditions.

**Migration admission** evaluates whether another host can safely accept the VM before attempting a migration operation.

---

## Performance Characteristics

The simulator is intentionally small enough to make the scheduling logic visible.

For a host with `n` running VMs, basic resource accounting is approximately `O(n)` per measurement cycle.

The weighted CPU scheduler may perform multiple redistribution passes when some VMs reach their demand or configured limit before other VMs do. In practical workloads the number of passes is bounded by the number of active VMs.

Memory reclamation performs a scan over running VMs and is approximately `O(n)`.

The dominant production cost is not normally the arithmetic represented by these methods. Real virtualization systems must account for:

- CPU scheduling overhead.
- VM exits and hypervisor transitions.
- NUMA placement.
- Cache locality.
- Memory translation structures.
- Storage I/O queues.
- Network packet processing.
- Device emulation.
- Telemetry collection.
- Management-plane communication.

A resource model that looks correct at the allocation level can still produce poor application performance if it ignores these physical effects.

---

## NUMA and Placement Considerations

Large virtualization hosts frequently use multiple CPU sockets and NUMA nodes.

NUMA means that memory access latency depends on which processor node owns the memory. A VM configured with many vCPUs may therefore perform differently depending on how its virtual CPUs and memory are placed across NUMA nodes.

The simplified implementations treat the host as one uniform CPU and memory pool. That is useful for understanding sharing and overcommitment but does not model NUMA topology.

Production host management may need to account for:

- vCPU affinity.
- NUMA-aware memory placement.
- Huge pages.
- PCI device locality.
- Memory channel capacity.
- Socket-level CPU availability.

These constraints can make a host appear to have enough aggregate resources while still lacking the correct locality for a particular VM.

---

## Migration

Migration moves or recreates a VM's execution state on another host.

The examples implement **migration admission**, not an actual migration protocol.

Before migration, the destination should satisfy the VM's resource requirements and policy constraints.

The Python and C++ implementations check destination storage, network capacity, and CPU and memory overcommitment policies.

A production migration workflow also needs to consider:

- CPU feature compatibility.
- Shared or replicated storage.
- Virtual network configuration.
- Attached devices.
- Encryption state.
- VM snapshots.
- NUMA topology.
- Destination reservations.
- Migration bandwidth.
- Dirty memory pages.
- Application latency.
- Failure recovery.

A destination passing basic capacity checks does not mean that a migration is automatically safe.

---

## Edge Cases and Failure Conditions

### Physical capacity exhaustion

If demand reaches physical capacity, the host cannot create additional physical CPU or memory. CPU contention results in scheduling delay. Memory pressure may require reclamation, swapping, compression, or workload termination depending on the platform.

### Reservation conflict

Reservations can themselves be configured incorrectly. If the sum of VM reservations exceeds host capacity, the host cannot simultaneously guarantee all declared commitments.

The Python host exposes `reservations_satisfied()` to identify this condition.

### Overcommitment disabled

A conservative host can reject a VM when projected virtual CPU or memory allocation exceeds physical capacity.

The JavaScript and C++ programs explicitly demonstrate this policy.

### Invalid resource configuration

A VM should not be accepted with:

- Zero vCPUs.
- Negative memory.
- A reservation above configured VM capacity.
- A limit below its reservation.
- Non-positive CPU shares.

The implementations reject these conditions before normal scheduling.

### Running VM removal

Removing a running VM without a lifecycle operation would bypass normal shutdown and cleanup semantics. The Python implementation therefore rejects removal while the VM is running.

### Memory pressure without reclaimable memory

If all available memory is protected by reservations, the simulator cannot manufacture additional physical RAM. The Python and C++ models treat this as a resource failure rather than silently violating reservations.

---

## Common Design Errors

### Treating vCPU allocation as physical CPU ownership

A vCPU is a virtual execution resource. It is not an independently dedicated physical processor unless a specific host policy provides dedicated CPU assignment.

### Treating CPU shares as guarantees

Shares express relative preference during contention. They are not equivalent to reservations.

### Assuming memory overcommitment behaves like CPU overcommitment

CPU overcommitment can often tolerate bursts because runnable virtual CPUs can be scheduled later. Memory overcommitment can cause immediate pressure when working sets simultaneously require more physical memory than exists.

### Confusing isolation with network segmentation

A network segment controls communication paths. Hypervisor isolation protects guest execution state. Both can be required, but they operate at different layers.

### Ignoring reservations during capacity planning

Configured virtual capacity is not enough to understand guarantees. Reservations determine how much of the physical resource has been committed as a minimum.

### Monitoring only average utilization

Average CPU utilization can hide synchronized workload spikes. Capacity management should examine peak demand, latency, contention, and memory pressure.

---

## Security Considerations

Server virtualization creates a strong security boundary but does not make the host automatically secure.

The host management plane is particularly sensitive because administrative control over a hypervisor can expose every guest running on it.

Important controls include:

- Restricting hypervisor administrative access.
- Separating management networks from guest networks.
- Applying least privilege to virtualization administrators.
- Protecting VM images and templates.
- Controlling virtual device exposure.
- Auditing lifecycle operations.
- Monitoring unexpected VM state changes.
- Validating storage and network attachment permissions.
- Keeping the virtualization platform and management components patched.

Isolation failures should be treated differently from ordinary resource contention. CPU contention may cause performance degradation, while a failure of guest isolation can become a confidentiality or integrity breach.

---

## Debugging and Observability

Useful host-level metrics include:

| Metric | What it reveals |
| --- | --- |
| Physical CPU utilization | Current pressure on processor capacity |
| Runnable vCPU count | Scheduling contention |
| CPU ready or wait time | Time VMs spend waiting for physical CPU |
| Allocated-to-physical CPU ratio | Degree of CPU overcommitment |
| Physical memory utilization | Current RAM pressure |
| Allocated-to-physical memory ratio | Degree of memory overcommitment |
| Reclaimed memory | Pressure-response activity |
| Swap activity | Potential severe memory pressure |
| Storage latency | I/O contention |
| Network utilization | Link or virtual switch pressure |
| VM lifecycle events | Unexpected starts, stops, failures, or migrations |

The JavaScript event model is particularly useful for operational telemetry because lifecycle and resource events can be consumed by monitoring components without tightly coupling those components to the host scheduler.

The Python model is more useful for inspecting resource-allocation logic and testing policy behavior directly.

The C++ implementation is useful for examining how resource governance can be represented as a strongly typed systems component.

---

## Production Considerations

A production virtualization manager needs stronger guarantees than the educational models provide.

The implementations intentionally simplify several mechanisms:

- CPU is modeled as a uniform pool rather than a NUMA topology.
- Storage is modeled as capacity rather than detailed I/O latency and queue behavior.
- Network is modeled as bandwidth rather than packet scheduling.
- Memory reclamation is represented as ballooning rather than a full hypervisor memory-management stack.
- Migration checks represent admission only, not live migration state transfer.
- Isolation is modeled at policy level rather than by implementing a real hypervisor.
- Failure recovery does not include clustered consensus or persistent control-plane state.

A production design would normally separate the control plane from the host execution layer and persist important state such as VM configuration, placement, reservations, lifecycle state, and operational history.

It would also need idempotent management operations. Repeating an operation such as "start VM" should not accidentally create a second VM or corrupt host accounting.

---

## Conceptual Separation of Responsibilities

The four major areas can be represented as a set of distinct questions:

| Area | Primary question |
| --- | --- |
| Resource sharing | How should limited physical resources be distributed among active VMs? |
| VM isolation | What prevents one guest from directly interfering with another guest? |
| Overcommitment | When is it acceptable for configured virtual resources to exceed physical capacity? |
| Host management | How does the platform place, monitor, operate, and recover VMs on physical hosts? |

These areas interact but should not be collapsed into one policy.

A host may permit CPU overcommitment while enforcing strict memory reservations. Two VMs may share physical CPU capacity while remaining isolated from each other's memory. A migration may be technically possible from a capacity perspective but rejected by the destination's overcommitment policy.

That separation is central to reliable virtualization architecture.

---

## Practical Relationship Between the Three Implementations

The Python program emphasizes **resource mechanics**: reservations, limits, weighted CPU sharing, memory reclamation, health calculation, overcommitment ratios, and capacity planning.

The JavaScript program emphasizes **management behavior**: VM state transitions, asynchronous monitoring, event emission, network isolation policy, admission failures, and destination checks.

The C++ program emphasizes **systems engineering**: typed resource contracts, private-cloud placement, production-like VM classes, deterministic scheduling logic, memory failure boundaries, migration admission, and burst simulation.

Together, these perspectives show that server virtualization is not simply the act of creating VMs. It is a resource-governance problem in which virtual capacity, physical capacity, isolation boundaries, workload demand, and operational policy must remain consistent.
