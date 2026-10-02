# Hypervisors: Type 1, Type 2, and Virtualization Architecture

## Scope

A hypervisor is the virtualization layer that allows multiple virtual machines (VMs) to share a physical computer while presenting each VM with an isolated set of virtual processors, memory, storage, and devices.

The central architectural distinction is the location of the hypervisor relative to the host hardware:

- A **Type 1 hypervisor**, also called a bare-metal hypervisor, runs directly on the physical machine and provides the virtualization boundary above the hardware.
- A **Type 2 hypervisor**, also called a hosted hypervisor, runs as software on top of a conventional host operating system. The host operating system remains part of the resource path between the hardware and the virtual machines.

The three implementations in this repository approach the subject from different perspectives. The Python program builds a resource-oriented virtualization simulator, the JavaScript program models an event-driven VM lifecycle, and the C++ program develops a more structured production-style resource and scheduling case study.

This material models virtualization architecture rather than implementing a real hypervisor. A production hypervisor requires privileged execution, processor virtualization extensions, interrupt virtualization, memory-management hardware, device virtualization, IOMMU support, firmware integration, and substantial kernel-level code.

## Architectural Foundation

### Type 1 virtualization

The simplified Type 1 path is:

    Physical hardware
           |
           v
    Type 1 hypervisor
       /    |    \
      v     v     v
     VM-A  VM-B  VM-C

The hypervisor is responsible for controlling access to physical CPU resources, memory, storage, networking, interrupts, and other devices. Guest operating systems do not receive unrestricted control of the physical machine.

Examples of technologies commonly associated with Type 1 virtualization include VMware ESXi, Microsoft Hyper-V in its hypervisor architecture, and Xen. Linux KVM is commonly described as a kernel-based virtualization solution and has an architectural model that differs from the traditional standalone bare-metal hypervisor terminology, so its classification should not be reduced to a simple product-label comparison.

Type 1 virtualization is particularly important in server consolidation and cloud infrastructure because the virtualization layer can manage many workloads on a physical host while maintaining resource boundaries.

### Type 2 virtualization

The simplified Type 2 path is:

    Physical hardware
           |
           v
       Host OS
           |
           v
    Type 2 hypervisor
       /    |    \
      v     v     v
     VM-A  VM-B  VM-C

A Type 2 hypervisor depends on the host operating system for ordinary host-level resource management. This architecture is convenient for desktop development, testing, laboratories, and environments where the user needs to run a guest operating system without dedicating the whole machine to a virtualization platform.

VirtualBox and VMware Workstation are familiar examples of hosted virtualization products.

The additional host operating-system layer can simplify integration with desktop hardware and applications, but it also adds another software layer to the execution and resource path.

## Virtualization Architecture

A VM does not normally receive a literal physical machine. Instead, the hypervisor constructs a virtual hardware environment.

A typical conceptual VM contains:

| Virtual resource | Purpose | Physical relationship |
|---|---|---|
| vCPU | Presents processor execution contexts to the guest | Scheduled onto physical CPU cores |
| Guest memory | Provides the guest operating system with addressable RAM | Mapped to host physical memory |
| Virtual disk | Presents persistent block storage | Backed by files, volumes, devices, or storage services |
| Virtual NIC | Gives the guest network connectivity | Connected to virtual switches or physical interfaces |
| Virtual firmware | Provides the boot environment | Implemented by the virtualization platform |
| Virtual interrupts | Allow devices and timers to signal the guest | Managed by the hypervisor and hardware |

The important principle is **indirection**. The guest operates against virtual resources, while the virtualization layer maps those resources onto physical resources.

## Virtual CPU Architecture

A vCPU is a virtual execution context. It is not necessarily a permanently reserved physical core.

For example, a host with four physical CPU cores might expose multiple VMs with several vCPUs each. The hypervisor scheduler determines which runnable vCPU receives execution time on which physical processor.

The Python implementation represents this relationship through `VirtualCPU` objects and a round-robin `Scheduler`. Each vCPU is associated with a VM, placed into a ready queue, and given a simulated execution quantum.

The JavaScript implementation uses `CpuScheduler` and emits `cpu-scheduled` events when a vCPU receives simulated processor time. This emphasizes the event-driven nature of resource management.

The C++ implementation uses `VirtualCPU` objects containing a pointer to their VM and a scheduler queue. The scheduler assigns a time quantum to available physical cores.

This model exposes an important distinction:

- **Physical CPU capacity** is hardware capacity.
- **Configured vCPU capacity** is virtual capacity.
- **Scheduler allocation** determines which runnable vCPU executes at a particular time.

CPU overcommitment can therefore exist. A host may expose more total configured vCPUs than it has physical cores. That can improve consolidation when workloads are not continuously CPU-bound, but sustained contention can cause scheduling delay and reduced performance.

## Memory Virtualization

Memory virtualization is more complicated than simply assigning a number of megabytes to a VM.

There are multiple conceptual address spaces:

    Guest virtual address
            |
            v
    Guest physical address
            |
            v
    Host physical address

A guest operating system normally manages its own virtual memory. The hypervisor must ensure that guest memory references ultimately resolve to host memory belonging to that VM.

Modern processors provide hardware-assisted mechanisms such as Intel Extended Page Tables (EPT) and AMD Nested Page Tables (NPT) to accelerate this additional translation.

The Python program makes the relationship explicit through `MemoryPage` and `MemoryManager`. A guest frame is mapped to a host frame, allowing the simulation to demonstrate that a guest-visible memory location is not automatically the same thing as a physical host frame.

The JavaScript `MemoryMapper` performs a similar mapping using a `Map`. Its purpose is architectural clarity: repeated requests for the same guest frame return the existing mapping rather than allocating another host frame.

The C++ implementation uses `MemoryMapping` and `MemoryManager` to maintain a mapping between guest frames and host frames.

Real systems must also handle:

- page permissions
- dirty pages
- page faults
- huge pages
- NUMA locality
- memory overcommitment
- swapping
- ballooning
- shared memory mechanisms
- copy-on-write behavior
- hardware translation caches
- DMA isolation

A simple frame map cannot represent all of those mechanisms, but it captures the central ownership relationship.

## Storage Virtualization

A virtual disk presents a logical block device to a guest. Its physical backing can take many forms, including a file, logical volume, network-backed block device, or dedicated physical storage.

The three implementations use bounded virtual disks.

The Python `VirtualDisk` tracks capacity and usage and rejects writes that exceed the configured virtual capacity.

The JavaScript `VirtualDisk` performs the same resource-boundary operation as part of the VM object model.

The C++ `VirtualDisk` is integrated into the production case study so disk capacity is treated as one component of the VM resource contract.

A production storage design must distinguish logical disk size from actual physical consumption. Thin-provisioned virtual disks, for example, can present a large logical capacity while consuming physical storage progressively.

## Virtual Networking

A virtual network interface provides the guest with an interface that behaves like a network adapter from the guest operating system's perspective.

The Python implementation associates each VM with a `VirtualNetworkCard` and tracks packet transmission.

The JavaScript implementation uses `VirtualNic` and generates a deterministic locally administered MAC address for each VM identifier.

The C++ implementation models a virtual NIC with connectivity state and packet accounting.

Real virtualization platforms add layers such as:

    Guest network stack
          |
          v
    Virtual NIC
          |
          v
    Virtual switch
          |
          v
    Virtual or physical uplink
          |
          v
    External network

Isolation becomes important at this boundary. VLANs, virtual switches, security groups, firewall policies, network namespaces, and hardware offload mechanisms can influence the final architecture.

## Python Implementation

The Python program is a resource-oriented virtualization simulator.

### Host model

The `Host` class records:

- physical CPU count
- physical memory
- physical storage
- host operating-system presence
- hypervisor type

The `architecture_description()` method makes the Type 1 and Type 2 execution paths explicit.

A Type 1 host is represented without a conventional host OS beneath the hypervisor. A Type 2 host includes a host operating system.

### VM lifecycle

The `VM` class supports the states:

- `CREATED`
- `RUNNING`
- `PAUSED`
- `STOPPED`
- `FAILED`

The `Hypervisor` class controls transitions between these states.

Starting a VM makes its virtual processors schedulable. Pausing removes it from active execution by changing its state. Stopping leaves the VM inactive while preserving the conceptual VM definition.

Lifecycle validation prevents operations that do not make architectural sense, such as running CPU work for a VM that is not running.

### Resource allocation

The Python `Hypervisor.create_vm()` method checks CPU, memory, and storage capacity before accepting a VM when overcommitment is disabled.

The resource accounting distinguishes:

- physical capacity
- configured virtual allocation
- runtime VM usage

This is important because a virtualization platform must reason about both capacity planning and actual runtime consumption.

### Scheduler

`Scheduler.tick()` implements a small round-robin model.

Each runnable virtual CPU receives a simulated time quantum and is returned to the ready queue. The scheduler uses the number of physical cores as the maximum number of vCPUs that can execute during a single tick.

This is intentionally simpler than production scheduling. Real hypervisors account for priorities, CPU affinity, NUMA topology, load balancing, timer interrupts, virtualization exits, processor frequency behavior, and other hardware-specific constraints.

### Memory mapping

`MemoryManager.map_guest_page()` assigns a host frame to a guest frame.

If a guest frame has already been mapped, the existing mapping is reused. This represents the persistence of an address translation rather than allocating a new host page for every lookup.

### Snapshot model

The VM snapshot captures selected VM state:

- lifecycle state
- CPU time
- memory usage
- disk usage
- guest-to-host page relationships

Restoring the snapshot rolls those selected fields back.

A production snapshot system is substantially more complex. A disk snapshot may need copy-on-write structures, while memory snapshots require a consistent representation of guest state. Application-level consistency may require coordination with the workload itself.

### Failure handling

The Python program explicitly demonstrates:

- invalid negative memory allocation
- disk-capacity exhaustion
- invalid packet counts
- unknown VM identifiers
- disconnected virtual networking

The exceptions separate resource failures from lifecycle failures and validation errors.

## JavaScript Implementation

The JavaScript implementation approaches the same architecture through Node.js event-driven programming.

### Event-driven VM management

`Hypervisor` extends `EventEmitter`.

Lifecycle operations emit events such as:

- `vm-created`
- `vm-started`
- `vm-paused`
- `vm-stopped`
- `cpu-scheduled`

This is useful for understanding how a virtualization management layer can publish state changes to monitoring, logging, automation, or orchestration components.

A production management system might use event streams, message queues, telemetry pipelines, or APIs rather than an in-process `EventEmitter`, but the architectural relationship is similar.

### Virtual machine state

`VirtualMachine` owns the virtual hardware model and resource counters.

Its methods enforce local invariants. For example, `allocateMemory()` rejects an allocation that would exceed the VM's configured memory.

The state machine is intentionally explicit so lifecycle errors do not become silent state corruption.

### JavaScript memory representation

The JavaScript `MemoryMapper` uses a `Map` to associate guest frames with host-frame mappings.

The choice is appropriate for the simulation because the primary operation is lookup by guest frame identifier. It also demonstrates a JavaScript-specific data structure without turning the file into a general JavaScript tutorial.

### Event-based scheduling

The scheduler emits a structured event for every simulated execution assignment.

That event contains:

- physical core
- vCPU identifier
- VM name
- scheduling quantum

This allows the same scheduling operation to be consumed by logging or monitoring code without coupling the scheduler directly to a particular output mechanism.

### Snapshot behavior

The JavaScript VM stores snapshot state as a JavaScript object. The mapping collection is serialized into an array of entries so it can be reconstructed as a `Map`.

This illustrates a practical issue in stateful systems: a snapshot is not merely a copy of an object. Data structures must be captured in a representation that can be restored without losing their semantics.

## C++ Case Study

The C++ program represents a production-style VM resource manager running on a Type 1 host.

The scenario contains:

- an eight-core virtualization node
- physical memory
- physical storage
- an API-service VM
- a database-service VM
- virtual CPUs
- virtual memory mappings
- virtual disks
- virtual network interfaces
- scheduling
- snapshots
- capacity enforcement
- overcommitment
- failure handling

### Resource contract

The `Hypervisor` tracks:

- allocated vCPUs
- allocated memory
- allocated storage
- physical host capacity
- overcommitment policy

When overcommitment is disabled, VM creation is rejected if the new configuration would exceed the physical host's declared capacity.

This separates **configuration admission control** from **runtime scheduling**.

### CPU scheduling

`CpuScheduler` uses a queue of `VirtualCPU` pointers.

Each scheduling tick selects runnable vCPUs up to the number of physical CPUs and assigns them a simulated time quantum.

The design illustrates why vCPUs and physical cores are different resources. A VM can own several vCPUs without owning dedicated physical cores.

The queue-based approach also makes the basic mechanics of time sharing visible without introducing hardware-specific scheduling details.

### Memory isolation

`MemoryManager` assigns free host frames to guest frames.

The VM owns its mapping table, while the hypervisor owns the host-frame pool.

This division reflects an important isolation principle: the guest can request and use memory exposed to it, but the mapping from guest memory to physical host memory remains under virtualization-layer control.

A production implementation would require much stronger enforcement using hardware page tables, privilege boundaries, TLB management, page permissions, IOMMU controls, and carefully validated kernel paths.

### Snapshot and restore

The C++ `Snapshot` captures selected VM state and allows it to be restored.

The example deliberately treats the snapshot as a simplified control-plane representation. A real VM snapshot has to define exactly what happens to guest memory, disk blocks, device state, CPU registers, timers, network connections, and application consistency.

### Capacity failure

The constrained-host example creates a resource boundary and then attempts an allocation that exceeds available memory.

The strict hypervisor rejects the configuration.

A second hypervisor enables overcommitment and accepts a configuration whose virtual allocation exceeds physical capacity.

This illustrates a central virtualization trade-off:

> Virtualization can multiplex resources, but it cannot eliminate physical resource limits.

Overcommitment therefore requires additional policies for memory pressure, CPU contention, workload priority, and capacity monitoring.

## Type 1 and Type 2: Technical Distinction

| Property | Type 1 | Type 2 |
|---|---|---|
| Hypervisor position | Directly above hardware | Above a host operating system |
| Host OS beneath virtualization layer | Not required as a conventional host OS | Required |
| Common environment | Datacenters, servers, cloud infrastructure | Desktops, development, testing |
| Resource path | Hardware to hypervisor to VM | Hardware to host OS to hypervisor to VM |
| Operational dependency | Hypervisor and underlying hardware | Hypervisor plus host OS |
| Desktop integration | Usually not the primary design goal | Usually strong |
| Isolation boundary | Hypervisor-centered | Hypervisor plus host-OS boundary |

The distinction describes architecture, not an absolute statement that one model has a particular performance or security result in every environment. Implementation quality, hardware support, workload characteristics, configuration, and management practices can materially affect behavior.

## Hardware-Assisted Virtualization

Modern x86 virtualization commonly relies on processor extensions.

The CPU provides mechanisms that allow a virtualization layer to control guest execution while allowing suitable guest code to run directly on the processor.

Important mechanisms include:

- privileged execution controls
- virtualization-specific CPU modes
- interrupt virtualization
- nested page translation
- hardware-assisted device isolation

Intel VT-x and AMD-V are major examples of CPU virtualization extensions. Intel EPT and AMD NPT provide hardware support for nested memory translation.

Hardware assistance changes the architecture significantly compared with older software-only virtualization techniques because the processor itself participates in enforcing the guest execution boundary.

## Privilege and Isolation

A guest operating system is privileged relative to applications running inside that guest, but it must not receive unrestricted control over the physical host.

The virtualization boundary therefore has to mediate operations such as:

- privileged CPU instructions
- memory mapping changes
- interrupt configuration
- device access
- DMA
- timer operations
- hardware configuration

A critical security property is that one VM must not be able to use virtualization mechanisms to access another VM's memory or devices.

This is why virtualization security is more than simply placing multiple operating systems on one machine. The hypervisor and supporting components become part of the trusted computing base.

## IOMMU and Device Isolation

CPU memory protection is not sufficient for devices that perform direct memory access.

An IOMMU can constrain which physical memory regions a device is allowed to access.

This becomes particularly important for:

- PCI passthrough
- SR-IOV
- high-performance network interfaces
- storage controllers
- accelerators

A secure virtualization architecture therefore considers both CPU-generated memory references and device-generated DMA references.

## Virtual Device Models

Virtual devices can be implemented through emulation, paravirtualization, or hardware-assisted mechanisms.

**Device emulation** presents a software model of a familiar physical device. It can provide compatibility but may require more host processing.

**Paravirtualized devices** use interfaces designed specifically for virtualization. They can reduce unnecessary emulation work and improve performance.

**Device passthrough** can give a VM more direct access to a physical device, but this introduces additional isolation and lifecycle requirements.

The Python, JavaScript, and C++ programs deliberately use abstract virtual devices rather than attempting to emulate real PCI hardware.

## Snapshots Versus Backups

A VM snapshot records a point-in-time state of selected VM resources. It should not automatically be treated as an independent backup strategy.

Snapshots may depend on the underlying storage system and may consume substantial storage as changes accumulate.

A production backup architecture should define:

- where backup data is stored
- how long it is retained
- how restoration is validated
- whether application state is consistent
- whether backups survive host or storage failure

The implementations use snapshots to teach state rollback, not to represent a complete backup system.

## Overcommitment

Overcommitment allows configured virtual capacity to exceed physical capacity.

CPU overcommitment can be reasonable when workloads are bursty because not every vCPU needs a physical core simultaneously.

Memory overcommitment is more sensitive because physical memory exhaustion can produce severe performance consequences. Platforms may use techniques such as ballooning, reclamation, compression, swapping, or workload-specific policies.

Storage thin provisioning is another form of overcommitment. A virtual disk can expose a logical capacity larger than the physical storage currently consumed.

Overcommitment therefore changes the problem from simple allocation to continuous capacity management.

## Performance Considerations

Virtualization introduces several potential sources of overhead:

- vCPU scheduling
- guest exits to the virtualization layer
- memory translation
- device emulation
- virtual networking
- storage virtualization
- interrupt handling
- contention among VMs
- NUMA placement

Hardware assistance can reduce many of these costs.

CPU-bound workloads can be affected by scheduler contention. Memory-intensive workloads can be affected by translation and NUMA behavior. I/O-heavy workloads can be affected by the path between the guest device and physical hardware.

Performance should therefore be analyzed according to the actual workload rather than assuming that virtualization adds one fixed percentage of overhead.

## NUMA Considerations

Large physical servers may contain multiple NUMA nodes.

A VM whose virtual CPUs execute on one NUMA node while its memory resides primarily on another may experience additional memory-access latency.

Production hypervisors can use:

- NUMA-aware VM placement
- CPU affinity
- memory affinity
- vCPU pinning
- huge pages
- topology-aware scheduling

The simplified simulators do not implement NUMA placement because the purpose is to make the basic virtualization mapping visible first.

## Security Considerations

A hypervisor represents a high-value isolation boundary.

Security concerns include:

- hypervisor vulnerabilities
- guest escape vulnerabilities
- malicious device interactions
- DMA attacks
- management-plane compromise
- insecure VM images
- exposed virtual device interfaces
- unsafe passthrough configurations
- insufficient patching
- excessive administrative privileges

The management plane deserves particular attention. An attacker who can control VM creation, device attachment, memory allocation, or host-level configuration may effectively control the virtualization environment even if guest isolation itself is functioning correctly.

Least privilege, authenticated management, secure configuration, timely patching, device isolation, and monitoring are therefore core operational controls.

## Common Modeling Mistakes

### Treating a vCPU as a physical core

A vCPU is a virtual execution context. The hypervisor can schedule many vCPUs across fewer physical cores.

### Treating guest physical memory as host physical memory

Guest physical addresses belong to the guest's abstraction. The virtualization layer ultimately maps them to host memory.

### Assuming Type 2 means no hardware virtualization

Hosted hypervisors can still use CPU virtualization extensions and hardware-assisted memory translation. The Type 2 distinction concerns the placement of the hypervisor relative to the host operating system.

### Treating snapshots as complete backups

A snapshot is a state-management mechanism. Its durability, consistency, retention, and independence from the original storage environment must be evaluated separately.

### Ignoring device access

CPU and memory isolation alone do not describe the complete virtualization boundary. Devices, DMA, interrupts, and passthrough configurations also require isolation.

## Practical Relationship Between the Three Layers of the Model

The architecture can be summarized as:

    Physical hardware
            |
            v
       Hypervisor layer
            |
      +-----+-----+
      |     |     |
     VM-A  VM-B  VM-C
      |     |     |
     OS    OS    OS

The hypervisor creates the virtual resource boundary.

The VM operating system sees virtual CPUs, virtual memory, virtual disks, and virtual devices.

The hypervisor maps those abstractions onto physical resources while enforcing the isolation and scheduling rules required by the virtualization architecture.

For Type 1, the path from hardware to the virtualization layer is direct.

For Type 2, the host operating system remains beneath the hosted hypervisor.

The Python implementation emphasizes resource accounting and explicit mappings. The JavaScript implementation emphasizes lifecycle events and management-plane behavior. The C++ implementation combines admission control, scheduling, memory mapping, device handling, snapshots, and overcommitment into a coherent infrastructure scenario.

## Limitations of the Implementations

These programs are educational architectural simulations rather than real hypervisors.

They do not implement:

- privileged CPU instruction interception
- VM exits and entries
- actual EPT or NPT hardware
- real page tables
- interrupt controllers
- IOMMU programming
- PCI device emulation
- DMA
- real virtual switches
- guest operating systems
- hardware timers
- live migration
- high-availability failover
- NUMA-aware scheduling
- production storage backends
- real isolation enforcement at processor privilege level

Their purpose is to make the relationships between physical resources, virtual resources, scheduling, lifecycle management, and isolation explicit in executable form.

## Running the Implementations

The Python program requires Python 3.10 or newer because it uses modern type annotations and standard-library features.

Run it with:

    python hypervisor_simulation.py

The JavaScript program is designed for Node.js and uses only built-in modules.

Run it with:

    node hypervisor_architecture.js

The C++ program requires C++17 or newer.

Compile it with:

    g++ -std=c++17 -O2 -Wall -Wextra -pedantic hypervisor_case_study.cpp -o hypervisor_case_study

Run it with:

    ./hypervisor_case_study

On Windows with a suitable C++ compiler, the resulting executable can be started from the command line using its generated `.exe` filename.

## Key Technical Relationships

The most important relationships demonstrated by the implementations are:

- **Type 1 versus Type 2** describes where the virtualization layer sits in the software and hardware stack.
- **Virtual CPUs versus physical CPUs** describes scheduling and multiplexing rather than simple one-to-one ownership.
- **Guest memory versus host memory** describes address translation and ownership boundaries.
- **Virtual devices versus physical devices** describes controlled abstraction and access mediation.
- **Overcommitment versus physical capacity** describes the difference between configured virtual capacity and actual hardware resources.
- **Snapshots versus persistent storage** describes state capture rather than a complete backup architecture.
- **Virtualization versus isolation** describes why CPU, memory, devices, and DMA must all participate in the security boundary.

A useful mental model is therefore not that a VM is a miniature physical computer sitting independently inside a host, but that a VM is a controlled collection of virtual resources whose execution and access are mediated by a virtualization layer.
