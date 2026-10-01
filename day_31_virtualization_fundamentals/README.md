# Virtualization Fundamentals

## Scope

Virtualization separates the physical resources supplied by a server from the logical computing environments that consume those resources. A physical server may contain processors, memory, storage controllers, network interfaces, and other hardware. A virtualization layer presents those resources to multiple virtual machines as virtual CPUs, virtual memory, virtual disks, and virtual network interfaces.

This repository models the relationship between physical servers, virtual machines, resource abstraction, and the operational benefits and trade-offs of virtualization.

The three implementations approach the subject differently:

- The Python program provides a resource-management simulation with explicit capacity validation, VM placement, migration, isolation concepts, and capacity planning.
- The JavaScript program models virtualization as an event-driven infrastructure service and adds asynchronous monitoring to show how a management layer can observe virtualized resources.
- The C++ program presents a more structured infrastructure case study in which a virtualization platform manages physical hosts, performs capacity-aware VM placement, rejects invalid deployments, migrates workloads, and reports resource utilization.

The implementations are simulations. They do not execute guest operating systems or interact with real CPU virtualization extensions such as Intel VT-x or AMD-V.

## Physical Servers

A physical server is the hardware layer on which virtualization ultimately depends. Its resources are finite.

The programs model four major resource categories:

| Physical resource | Virtualized representation | Operational significance |
|---|---|---|
| CPU cores | vCPUs | Determines how much processor capacity can be assigned to VMs |
| RAM | Virtual memory allocation | Provides addressable memory capacity to guest systems |
| Storage | Virtual disks | Gives VMs persistent storage without exposing the entire physical device |
| Network interface capacity | Virtual network interfaces | Allows VMs to communicate while sharing physical network infrastructure |

The Python `PhysicalServer`, JavaScript `PhysicalServer`, and C++ `PhysicalServer` classes all maintain physical capacity and calculate how much has already been allocated.

A key distinction is that an allocated virtual resource is not automatically the same thing as instantaneous physical utilization. A VM can be configured with four vCPUs while its workload may currently consume only a fraction of the corresponding host processing capacity.

This distinction is important when evaluating consolidation and overcommitment.

## Virtual Machines

A virtual machine is a software-defined computing environment that presents virtual hardware to a guest operating system.

A VM typically contains logical representations of:

- CPU resources
- memory
- persistent storage
- network interfaces
- other devices exposed by the virtualization platform

The Python `VirtualMachine` class records the VM's operating system, vCPU allocation, memory, storage, workload, host, and running state.

The JavaScript implementation uses the same concepts but treats VM state as mutable objects managed by a Node.js infrastructure process.

The C++ implementation places VM state inside a physical host's managed collection. This makes the relationship between host capacity and VM placement explicit.

A VM can therefore be moved between suitable hosts without changing its logical configuration. The C++ migration case study demonstrates this relationship by changing the VM's physical host while preserving its virtual CPU, memory, storage, and workload attributes.

## Resource Abstraction

Resource abstraction is the central mechanism of virtualization.

An application inside a VM does not normally need to know which physical CPU core is executing a particular instruction or which physical memory module contains a particular page. The guest operating system interacts with virtual hardware, while the virtualization layer maps those requests to underlying physical resources.

Conceptually, the architecture can be represented as:

    Applications
          |
    Guest operating system
          |
    Virtual hardware
          |
    Hypervisor / virtualization layer
          |
    Physical CPU, RAM, storage, network
          |
    Physical server

The abstraction creates a boundary between the logical machine and the hardware that supports it.

The simulations represent that boundary by preventing a VM from directly modifying the physical host's resource accounting. Instead, the hypervisor-like classes perform allocation and placement decisions.

## Hypervisor Responsibilities

A hypervisor is the software layer that creates and manages virtual machines and controls their access to physical resources.

Two broad deployment models are commonly discussed:

| Model | Description |
|---|---|
| Type 1 | Runs directly on physical hardware and provides virtualization services to guest VMs |
| Type 2 | Runs as an application on top of a conventional host operating system |

The code in this repository does not emulate either architecture internally. Its `Hypervisor` and `VirtualizationPlatform` classes represent the resource-management role conceptually.

The simulated layer performs operations such as:

- registering physical hosts
- checking resource capacity
- selecting a suitable host
- deploying VMs
- rejecting resource requests that exceed capacity
- migrating VMs
- calculating utilization

These are management concepts rather than implementations of a real hypervisor kernel.

## CPU Virtualization

A physical CPU contains a finite number of execution resources. Virtualization exposes virtual CPUs to guest operating systems.

If a physical server has 16 CPU cores, it can expose VM configurations containing different vCPU allocations. The host scheduler determines when the VMs receive physical processor time.

The examples intentionally distinguish vCPU allocation from actual CPU consumption. A VM configured with six vCPUs does not necessarily consume six physical cores continuously.

Virtualization platforms can use scheduling and, depending on configuration and workload characteristics, may support CPU overcommitment. Overcommitment means that the sum of configured virtual CPU capacity can exceed the physical capacity available for simultaneous execution.

This can improve resource utilization when workloads have low or variable demand, but excessive contention can increase latency and reduce performance predictability.

## Memory Virtualization

Memory virtualization gives each guest operating system a logical memory address space.

The guest operating system behaves as though it owns its allocated virtual memory, while the virtualization layer controls how that memory relates to physical memory.

The Python and JavaScript simulations use simple capacity accounting:

    allocated memory =
        sum of memory assigned to every VM on the host

This is intentionally simpler than the mechanisms used by production hypervisors, which may involve hardware-assisted address translation, memory ballooning, page sharing, compression, swapping, and other platform-specific techniques.

Memory overcommitment requires particular care because physical RAM cannot provide unlimited simultaneous working-set capacity. Excessive memory pressure can cause severe performance degradation.

## Storage Virtualization

The examples represent storage using logical capacity assigned to each VM.

For example, a VM may receive a 200 GB virtual disk while the underlying physical storage is a larger pool.

A real virtualization platform can implement virtual disks using files, logical volumes, storage arrays, distributed storage systems, or other backends. The VM sees the virtual storage interface rather than necessarily interacting directly with the underlying physical media.

The simulations deliberately use capacity accounting instead of implementing a storage subsystem. This keeps the focus on the abstraction relationship between physical and virtual resources.

Storage capacity is not equivalent to storage performance. Two hosts with identical storage capacity may have very different latency, throughput, IOPS, redundancy, or failure characteristics.

## Network Virtualization

Virtual machines commonly receive virtual network interfaces. The virtualization layer connects those interfaces to physical network infrastructure through virtual switches, bridges, routing, filtering, or other mechanisms.

The models include network capacity as a physical-host property, but the primary allocation algorithms focus on CPU, memory, and storage. This is deliberate because network virtualization introduces additional concepts such as virtual switching, VLANs, overlays, traffic shaping, security groups, and physical uplink constraints.

A production placement engine would need to consider network requirements when deciding whether a VM can safely run on a particular host.

## Resource Pooling

Without virtualization, a simplified deployment model might assign one physical server to each application workload.

Virtualization permits several workloads to share a physical host.

For example:

    Physical server
    ├── Web VM
    ├── API VM
    ├── Database VM
    └── Worker VM

The Python consolidation example demonstrates this arrangement by placing several different workload types across a smaller physical infrastructure pool.

The benefit is not that virtualization creates additional resources. The benefit comes from sharing and managing existing resources more efficiently.

Workloads with different demand patterns can share infrastructure instead of requiring each workload to have a dedicated physical machine sized for its individual peak.

## Consolidation

Server consolidation is one of the practical consequences of virtualization.

Suppose six workloads previously require six physical servers. If their resource requirements can safely coexist, a virtualization platform may place them across fewer physical hosts.

The Python example calculates an illustrative active-host power budget. The numbers are intentionally simple and are not intended to represent a real data-center power model.

Actual consolidation analysis must consider:

- CPU demand
- memory working sets
- storage throughput
- network throughput
- workload interference
- hardware redundancy
- maintenance requirements
- licensing
- cooling
- availability requirements

Reducing the number of physical servers can reduce hardware, power, cooling, rack-space, and operational requirements, but those benefits depend on workload characteristics and infrastructure design.

## Placement and Scheduling

The Python and C++ implementations include capacity-aware placement.

A candidate physical host is first checked against the VM's resource requirements. A host that cannot satisfy the request is rejected.

The Python and JavaScript simulations then use a simple projected CPU-plus-memory utilization score to choose among valid hosts.

This is an educational scheduling policy rather than a production algorithm.

Real infrastructure schedulers can consider additional constraints:

- CPU and memory reservations
- affinity and anti-affinity
- NUMA topology
- storage locality
- network topology
- hardware capabilities
- licensing restrictions
- availability zones
- maintenance state
- workload priority
- power-management policies

The important mechanism demonstrated by the examples is the separation between a VM's resource request and the physical host that ultimately satisfies that request.

## VM Migration

Migration changes the physical placement of a VM.

The Python and C++ programs demonstrate migration by:

1. locating the VM on its source host
2. checking destination capacity
3. removing the VM from the source host
4. assigning it to the destination host

A real live migration system is considerably more complex. It may transfer memory state while the VM continues running, coordinate CPU execution state, synchronize storage, manage network identity, and minimize downtime.

The simulation therefore demonstrates the resource-management decision rather than claiming to implement live migration.

Migration can be useful for:

- balancing resource utilization
- preparing a host for maintenance
- reducing active-host count
- responding to infrastructure events
- moving workloads away from problematic hardware

Migration itself consumes resources and introduces operational risks. It is not free.

## Isolation

Virtualization provides logical separation between guest environments.

In the Python isolation example, two VMs share one physical server but have distinct resource allocations.

Isolation can be understood at several levels:

    VM A virtual resources
              |
        virtualization layer
              |
    VM B virtual resources

A VM does not normally receive unrestricted access to another VM's memory or virtual hardware.

Isolation should not be interpreted as an absolute security guarantee. Hypervisor vulnerabilities, unsafe device passthrough, management-plane compromise, incorrect permissions, and shared infrastructure can introduce security risks.

A secure virtualization environment therefore requires controls around the hypervisor, management interfaces, guest operating systems, virtual networking, storage, and administrative access.

## Capacity Validation

The programs explicitly reject invalid resource requests.

For example, a VM requesting eight vCPUs cannot be placed on a host that has only four unallocated physical CPU cores under the simulation's non-overcommitted policy.

The Python implementation uses `can_allocate()`, JavaScript uses `canHost()`, and C++ uses `canHost()` with an output reason.

This pattern is important because resource allocation should be validated before mutating infrastructure state.

A failed request should not partially create a VM and leave the resource accounting inconsistent.

## Overcommitment

The examples primarily use conservative allocation in which requested CPU and memory resources must fit within the host's available capacity.

Production virtualization platforms may permit overcommitment.

For CPU, the configured vCPU total may exceed the number of physical cores because workloads may not demand all vCPUs simultaneously.

Memory overcommitment can be implemented through platform-specific techniques, but it becomes more sensitive to actual working-set demand.

The key distinction is:

    configured capacity != instantaneous physical consumption

Overcommitment can improve utilization when demand is bursty or sparse. It can also create contention when multiple workloads become busy at the same time.

The appropriate level depends on workload behavior and operational objectives.

## Python Implementation

The Python program is organized around three primary abstractions.

`PhysicalServer` owns the finite physical resources and tracks its hosted VMs. It calculates allocated CPU, memory, and storage and validates whether a new VM can fit.

`VirtualMachine` represents the logical machine exposed to a guest operating system. Its state includes resource allocation, workload identity, host assignment, and running state.

`Hypervisor` provides the management layer. It registers hosts, selects suitable hosts, deploys VMs, and performs migration.

The program also demonstrates capacity planning and failure handling. Oversized VMs are rejected before deployment, while migration is permitted only when the destination can satisfy the VM's resource requirements.

This structure demonstrates the separation of concerns that is useful when designing infrastructure-management software.

## JavaScript Implementation

The JavaScript implementation uses classes and `Map` collections to represent physical hosts and their VM inventories.

The `Hypervisor` selects a host using projected utilization. The implementation is deliberately different from the Python presentation by emphasizing Node.js-style infrastructure monitoring.

`simulateMonitoring()` uses `setInterval()` and a Promise to model periodic asynchronous monitoring. This illustrates how a management process can collect host state without blocking its main execution model.

The program also uses explicit error propagation through JavaScript exceptions and a top-level `catch()` handler. Invalid capacity requests therefore become operational events rather than silent state corruption.

The JavaScript example is appropriate for understanding how a virtualization-management service could expose resource state to higher-level automation.

## C++ Case Study

The C++ implementation models a small virtualization platform managing three physical compute nodes.

The central classes are:

| Class | Responsibility |
|---|---|
| `VirtualMachine` | Stores guest configuration and VM state |
| `PhysicalServer` | Owns physical capacity and hosted VM objects |
| `VirtualizationPlatform` | Selects hosts, deploys workloads, and coordinates migration |

The physical host stores VMs in a `std::map`, which provides named lookup for resource-management operations.

The placement engine examines every registered host and rejects hosts that cannot satisfy the VM's CPU, memory, or storage request. Among valid hosts it selects the one with the lowest projected CPU-plus-memory utilization.

The case study then migrates `frontend-01` between physical nodes after checking the destination's capacity.

This design demonstrates an important virtualization relationship: a VM is logically stable while its physical placement can change.

## Failure Conditions

Virtualized infrastructure must handle resource failures explicitly.

The examples account for conditions such as:

- a VM requesting more CPU than a host can provide
- a VM requesting more memory than available
- a VM requesting more storage than available
- invalid non-positive resource values
- duplicate VM placement
- migration to an unknown host
- migration of a VM that is not on the specified source host
- migration to a destination without sufficient capacity
- attempting to start a VM without a host

A production platform would need substantially more failure handling, including storage failures, network failures, host failure, management-plane failure, stale inventory information, and partial migration failure.

## Performance Considerations

Virtualization introduces an abstraction layer, so resource allocation and management have costs.

Modern hardware-assisted virtualization can make the overhead of CPU and memory virtualization relatively small for many workloads, but the exact impact depends on workload type and configuration.

Important performance factors include:

- CPU scheduling contention
- memory pressure
- NUMA placement
- storage latency and IOPS
- virtual network overhead
- device emulation
- virtualization-aware drivers
- host oversubscription
- noisy-neighbor workloads

The simulations measure capacity rather than real execution latency. A host showing 50% allocated CPU does not necessarily mean that applications are experiencing 50% CPU utilization or predictable performance.

## Virtualization Benefits

Virtualization can provide several infrastructure-level benefits when the workloads and platform are appropriately designed.

### Resource utilization

Multiple workloads can share physical resources, allowing unused capacity from one workload to be used by another.

### Consolidation

Several logical servers can operate on fewer physical machines. This can reduce physical infrastructure requirements.

### Workload mobility

VM abstraction allows workloads to be moved between compatible physical hosts without redesigning the guest application for a different physical server.

### Operational flexibility

VMs can be created, stopped, resized, cloned, and moved through software-managed infrastructure workflows.

### Isolation

Separate guest environments provide logical boundaries that are useful for workload separation and resource governance.

### Capacity management

Virtualized infrastructure can expose resource allocations in a form that management systems can measure, compare, and automate.

These benefits depend on correct architecture. Virtualization does not eliminate hardware constraints, and it does not automatically guarantee security, availability, or performance.

## Resource Abstraction Versus Physical Ownership

A useful conceptual distinction is:

| Question | Physical layer | Virtual layer |
|---|---|---|
| Who owns the resource? | Infrastructure operator owns the physical hardware | Guest receives an abstracted allocation |
| CPU representation | Physical cores | vCPUs |
| Memory representation | Physical RAM | Guest-visible virtual memory |
| Storage representation | Physical disks or storage systems | Virtual disks |
| Network representation | Physical NICs and links | Virtual NICs and virtual network connectivity |
| Resource scheduling | Hardware and host operating system or hypervisor | Guest scheduler plus virtualization layer |
| Mobility | Hardware normally remains fixed | VM can potentially move between hosts |

The virtual layer depends on the physical layer. Virtualization changes how resources are presented and managed; it does not remove the underlying physical constraints.

## Common Design Mistakes

### Treating vCPU count as guaranteed dedicated physical CPU

A vCPU allocation describes a virtual processor resource. Unless dedicated CPU resources are explicitly configured, other workloads may share the same physical processing capacity.

### Ignoring memory contention

A large number of VMs may fit based on nominal configuration while their simultaneous working sets exceed available physical memory.

### Measuring only capacity

A host can have sufficient storage capacity but inadequate storage performance. Similarly, sufficient network capacity does not guarantee acceptable latency.

### Assuming migration is free

Migration consumes network, CPU, storage, and management resources. Large or highly active VMs can be expensive to move.

### Treating virtualization as automatic security

Virtualization creates useful isolation boundaries, but those boundaries depend on correct hypervisor configuration, patching, access control, network design, and hardware behavior.

### Ignoring host failure

Consolidation can increase the number of workloads affected by a single physical host failure. Availability architecture must therefore account for host-level failure domains.

## Security Considerations

The hypervisor and its management interfaces form a critical infrastructure layer.

Security controls should protect:

- hypervisor management interfaces
- administrative credentials
- VM creation and deletion permissions
- virtual networking
- storage access
- guest-to-host boundaries
- device passthrough configuration
- host operating systems where applicable
- management APIs
- audit records

A compromised management plane can affect multiple virtual machines because the management layer controls shared physical infrastructure.

Isolation also depends on the virtualization implementation. Vulnerabilities in the hypervisor or device emulation layer can potentially affect the security boundary between guests and the host.

## Production Considerations

A production virtualization platform requires more than CPU, memory, and storage accounting.

A complete platform may need:

- high-availability policies
- redundant physical hosts
- storage redundancy
- network redundancy
- backup and recovery workflows
- resource reservations
- affinity and anti-affinity
- monitoring and alerting
- lifecycle management
- hardware compatibility checks
- capacity forecasting
- audit logging
- access control
- maintenance workflows
- disaster recovery

The implementations in this repository intentionally concentrate on the fundamentals: physical resources, VM abstraction, placement, capacity validation, migration, consolidation, and the resulting operational trade-offs.

## Relationship Between the Core Concepts

The four central ideas form a direct technical chain:

    Physical server
          |
          | provides finite CPU, memory, storage, network capacity
          v
    Virtualization layer
          |
          | abstracts and schedules those resources
          v
    Virtual machines
          |
          | consume virtualized resources
          v
    Applications and guest operating systems

The practical benefits arise from the ability to manage this abstraction.

Resource pooling permits consolidation. Consolidation can improve utilization. VM abstraction permits workload mobility. Mobility can support maintenance and balancing. At the same time, shared infrastructure creates contention, management complexity, and host-level failure considerations.

Understanding virtualization therefore requires both sides of the abstraction: the logical resources presented to VMs and the physical resources that ultimately execute the workloads.
