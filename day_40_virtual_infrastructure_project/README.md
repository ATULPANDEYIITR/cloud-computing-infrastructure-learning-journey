# Virtual Infrastructure Project

## Project scope

This project models the control plane of a virtual infrastructure platform. The platform organizes compute, networking, storage, identities, and resource policies into isolated environments. It demonstrates how a provisioning request moves from validation to resource allocation, how lifecycle changes affect resource ownership, and how infrastructure state can be audited.

The implementations use an engineering sandbox containing an application server, an isolated subnet, a storage pool, and an attached data volume. Administrative, operational, and read-only identities have different permissions.

The examples simulate infrastructure management. They do not create real virtual machines, configure host networking, format disks, or invoke a hypervisor. A production deployment would connect the control plane to a virtualization platform or cloud provider and reconcile desired state with the actual state of its resources.

## Architecture and resource relationships

The infrastructure model separates tenant boundaries from the resources contained within them.

- **Environment:** A logical boundary for an application team, project, or workload. It owns a resource quota and groups related VMs, networks, and storage pools.
- **Virtual machine:** A compute instance with a lifecycle state, CPU allocation, memory allocation, image reference, network assignment, and optional attached volumes.
- **Virtual network:** An isolated addressing domain identified by a CIDR subnet and a VLAN identifier. Its IP allocation records map VM identities to addresses.
- **Storage pool:** A capacity boundary for virtual disks. A pool records its total capacity and the volumes allocated from it.
- **Volume:** A persistent block-storage resource with a size, encryption setting, owning environment, and optional VM attachment.
- **User and role:** An identity and its permitted operations. Environment membership further restricts access to resources belonging to a particular environment.
- **Audit event:** A record of an infrastructure action, its actor, its outcome, and the relevant resource identifiers.

The intended ownership relationship is:

    Environment
      ├── Resource quota
      ├── Virtual networks
      │     └── IP allocations
      ├── Storage pools
      │     └── Volumes
      └── Virtual machines
            ├── Compute allocation
            ├── Network and IP assignment
            └── Volume attachments

A VM and its network must belong to the same environment. A VM and an attached volume must also share an environment. These restrictions prevent a resource from one tenant from being used implicitly by another tenant.

## Provisioning workflow

A provisioning operation follows a controlled sequence.

**Request validation:** The control plane validates resource identifiers, VM image references, requested CPU and memory, network ownership, and storage size.

**Authorization:** The caller must possess the required role and access to the target environment. A viewer can inspect inventory, an operator can manage workloads, and an administrator can configure environments and their foundational resources.

**Quota evaluation:** The requested resources are compared with the environment's configured limits. Compute quotas include VM count, vCPUs, and memory. Storage quotas limit the storage capacity allocated to the environment.

**Network allocation:** The VM receives an address from its assigned network. The address must be unique and must not be the subnet's network address, broadcast address, or reserved gateway.

**Resource creation:** The control plane registers the VM and updates the resource inventory. A failed allocation must not leave an orphaned IP reservation or a partially registered VM.

**Lifecycle management:** The VM moves between permitted states. Invalid operations are rejected instead of silently changing the state.

**Verification and audit:** Inventory queries report the resulting configuration. Invariant checks identify inconsistent IP ownership, storage accounting, or volume attachments.

These steps represent a control-plane workflow. A real provider integration must also handle API timeouts, asynchronous hypervisor operations, partial failures, and reconciliation after the control plane loses contact with a compute host.

## Virtual machine lifecycle

The code distinguishes VM existence from VM execution state.

| State | Meaning |
|---|---|
| `provisioning` | Resource creation is in progress. |
| `stopped` | The VM exists but is not running. |
| `running` | The VM is intended to execute workloads. |
| `suspended` | Execution has been suspended according to the platform's lifecycle model. |
| `terminated` | The VM has reached a terminal state in the simulator. |
| `failed` | Provisioning or an infrastructure operation failed. |

The Python, JavaScript, C++, and Java implementations primarily exercise the stopped, running, suspended, and terminated states. The SQL model additionally represents provisioning and failed states.

Starting is permitted from stopped or suspended states. Stopping requires a running VM. Suspending also requires a running VM. Termination is terminal in the Java model and SQL trigger. The implementations reject invalid transitions, such as stopping an already stopped VM.

Termination also affects related resources. The Python and C++ models release the IP address and detach volumes while retaining the volume resources. The JavaScript model similarly releases the IP and detaches volumes. This distinction matters because deleting a VM should not automatically imply deleting persistent data.

A production system must define whether termination deletes the boot disk, preserves data disks, releases reserved addresses, and retains snapshots. Those decisions should be explicit policies rather than accidental side effects of a lifecycle method.

## Networking and isolation

### CIDR addressing

A CIDR prefix determines the address range available to a subnet. For example, `10.90.1.0/24` describes an IPv4 subnet containing 256 addresses. Under conventional IPv4 subnetting, the network and broadcast addresses are not assigned to hosts. The gateway is reserved for network routing.

The Python implementation uses `ipaddress.ip_network` to validate subnet boundaries and detect overlapping networks. Its allocator iterates over usable host addresses and excludes reserved or previously allocated addresses.

The C++ implementation converts IPv4 addresses to 32-bit integers. This allows subnet boundaries and overlap to be checked using integer comparisons. The JavaScript implementation performs equivalent arithmetic for a constrained IPv4 range, while the Java model focuses on ownership and allocation relationships.

The JavaScript and Java examples deliberately have narrower IPAM validation than the Python implementation. The JavaScript parser supports a restricted prefix range and the Java allocator uses a deterministic example subnet. Neither should be mistaken for a general-purpose IP address management system.

### VLANs and network boundaries

A VLAN identifier associates a virtual network with a Layer 2 segmentation mechanism. The examples validate VLAN identifiers against the conventional range of 1 through 4094. Merely storing a VLAN identifier does not configure a switch, virtual switch, overlay network, routing table, or firewall.

Network isolation requires enforcement in the actual data plane. A production implementation must also address routing between subnets, security groups, firewall rules, address spoofing, DNS, DHCP, and access to management interfaces.

### Address ownership

An IP allocation should identify the network, address, and owning VM. Releasing an address during termination makes it available for reuse. Reuse is safe only when stale references and outstanding network configuration have been handled appropriately.

The SQL implementation gives IP allocations their own table and enforces unique addresses within each network. A trigger verifies that an allocated address belongs to the specified subnet and that its VM uses the same network.

## Storage provisioning and attachment

Storage is modeled as two related resource layers.

A storage pool represents a capacity boundary. Its `capacity_gib` value is compared with the sum of its provisioned volumes. The remaining capacity is the pool capacity minus the provisioned volume sizes.

A volume is an independently identified disk resource. It records its owning environment, pool, size, encryption setting, and attachment state. The models prevent a volume from being attached to a VM in another environment. They also reject deletion while a volume is attached.

The Python implementation includes explicit allocation and release methods in `StoragePool`. If allocation exceeds available capacity, a `CapacityError` is raised before the pool accounting changes.

The JavaScript implementation represents pool usage through its volume map and serializes asynchronous provisioning operations with an `AsyncMutex`. This protects concurrent requests within one Node.js process from simultaneously consuming the same observed capacity. A process-local mutex cannot coordinate separate service instances.

The C++ implementation uses a map of volume identifiers to sizes. Its `usedGB()` method derives usage from the stored allocations rather than maintaining a second independently mutable counter.

The Java implementation uses a `HashMap` to represent provisioned volume sizes and calculates usage with streams. Its explicit domain classes keep storage validation and VM lifecycle behavior separate.

The SQL implementation uses foreign keys to associate volumes with pools and composite foreign keys to enforce environment ownership. A volume attachment has its own relational record. Triggers keep the volume's attachment state consistent when a valid attachment is inserted or removed.

The encryption flag in these examples is metadata. It does not encrypt a disk. A real system must configure encryption at the storage backend or application layer and manage encryption keys, permissions, rotation, and recovery.

## Python implementation

The Python program is a standard-library control-plane simulator with dataclasses, enumerations, dictionaries, sets, exceptions, and a reentrant lock.

`ResourceRequest` and `ResourceQuota` validate resource specifications at construction time. This makes invalid requests fail before they enter the infrastructure registry.

`VirtualInfrastructure` coordinates the relationships between environments, users, networks, storage pools, VMs, and volumes. Its authorization method checks both the user's role and environment membership. Resource-specific methods then enforce ownership and capacity requirements.

The `create_vm` operation demonstrates an allocation sequence in which an IP address is obtained before the VM is registered. If a later operation fails, the exception handler releases the IP and removes any partially registered VM. This is a small example of compensating rollback in an in-memory system.

`validate_invariants()` checks cross-object relationships that individual field validations cannot establish. It verifies compute quotas, storage accounting, IP ownership, and both directions of volume attachment.

The snapshot method writes a JSON metadata manifest through a temporary file followed by a replacement operation. It explicitly identifies the manifest as metadata-only and does not claim to capture the contents of guest memory or disks.

The built-in `unittest` suite checks lifecycle transitions, role enforcement, subnet overlap rejection, VM quota limits, storage exhaustion, cross-environment attachment, IP release, and invariant consistency.

The Python lock protects mutations only inside the current process. The implementation is educational rather than a replacement for transactional persistence or a distributed resource scheduler.

## JavaScript implementation

The JavaScript program emphasizes event-driven control-plane behavior and asynchronous resource provisioning.

`InfrastructureController` extends Node.js `EventEmitter`. Infrastructure operations emit audit events, separating the occurrence of an operation from the collection of its audit record. Audit records are frozen copies so event consumers cannot directly mutate the controller's original event object.

`AsyncMutex` serializes asynchronous operations using a promise queue. This prevents two overlapping VM or volume creation requests in the same controller from both making a capacity decision against an unchanged resource inventory.

`VirtualMachine.transition()` uses an explicit transition table. An action is accepted only when the VM is in a state listed for that action. This approach makes the lifecycle policy visible and easier to test than a collection of unrelated assignments.

The network implementation converts IPv4 addresses to integers, making subnet arithmetic and address iteration straightforward. It intentionally supports only a constrained subset of IPv4 CIDR notation and is not suitable for general production IPAM.

The volume workflow keeps attachment ownership on both the volume and VM. It rejects duplicate attachments, cross-environment use, and deletion while a volume is attached.

The assertions in `runTests()` exercise the controller's lifecycle and isolation behavior. The controller records failed VM provisioning attempts, while the demonstration also tests overlapping subnet rejection.

In a distributed environment, event delivery, audit persistence, and locking require additional infrastructure. An in-memory event emitter does not provide durable delivery, and the local mutex cannot prevent conflicts across independent controller processes.

## C++ case study

The C++ program models an enterprise hosting service through an `InfrastructureManager`. Its focus is explicit resource ownership, typed state, network arithmetic, and a coherent VM provisioning workflow.

`InfrastructureManager` maintains ordered maps for environments, networks, storage pools, VMs, volumes, and users. Ordered maps make inventory output predictable and provide logarithmic lookup by identifier.

The `Subnet` structure parses IPv4 addresses into 32-bit integers. It computes network and broadcast addresses from the prefix length and exposes an overlap test based on the two address ranges. The supported subnet prefix is deliberately restricted to `/16` through `/30`.

The manager checks the VM count, aggregate vCPU allocation, and aggregate memory allocation before creating a VM. Network and storage ownership are verified before their resources can be attached to a workload.

The volume attachment operation maintains reciprocal references: the VM records the attached volume, and the volume records its owning VM. `invariantsHold()` checks both sides, detects missing attachments, and verifies that storage usage does not exceed pool capacity.

Termination releases the VM's IP allocation and detaches its data volumes. The volume resources themselves remain present, demonstrating the difference between removing a compute instance and destroying persistent data.

The case study uses `std::optional` for attachment ownership, enums for roles and VM states, and exceptions for capacity, authorization, and lifecycle failures. It compiles with C++17 and requires no external libraries.

For the map-based data structures, lookup and insertion are generally logarithmic in the number of records. Scanning all VMs to calculate quota usage is linear in the number of VMs in an environment. A larger scheduler would normally maintain transactional allocation records and queryable resource counters rather than repeatedly scanning all VM records.

## Java implementation

The Java program presents an enterprise-oriented domain model with separate classes for users, environments, networks, storage pools, volumes, and virtual machines.

`ResourceRequest` and `ResourceQuota` are records with compact constructors that validate resource limits. Their values are immutable after construction, preventing a request from being changed after it has passed its initial validation.

`AccessPolicy` maps roles to permission sets. The `InfrastructureService` applies that policy before changing infrastructure state and checks environment membership for users who are not administrators.

The VM class owns the lifecycle transition rules. Invalid transitions raise `InvalidStateException`, while missing resources, insufficient permissions, and quota violations use distinct exception types.

The service calculates current compute usage with Java streams. It also checks whether the selected network and storage pool belong to the same environment as the resource being created.

The `Network` class provides a deliberately simplified IP allocation model, and its comments distinguish that demonstration from a fully validated IP address management service. A production implementation should replace it with subnet-aware allocation and overlap checking.

The service records infrastructure events as immutable `AuditEvent` records. Its storage accounting validation derives usage from the volume map and verifies that pool capacity is not exceeded.

The design separates domain objects from orchestration logic. This helps identify where policy belongs, though production code would also require persistent repositories, transactional resource reservations, provider adapters, and explicit retry behavior.

## SQL data model

The PostgreSQL implementation stores infrastructure state in relational tables with explicit ownership relationships.

| Table | Responsibility |
|---|---|
| `infrastructure_users` | User identities, roles, and enabled status. |
| `environments` | Tenant boundaries and compute/storage quota definitions. |
| `environment_memberships` | User access to specific environments and the administrator who granted it. |
| `virtual_networks` | Subnets, gateways, VLAN identifiers, and environment ownership. |
| `ip_allocations` | Address assignments, network ownership, and VM associations. |
| `storage_pools` | Storage capacity boundaries and environment ownership. |
| `virtual_machines` | VM specifications, lifecycle state, image reference, and network relationship. |
| `storage_volumes` | Disk capacity, encryption metadata, pool ownership, and volume state. |
| `volume_attachments` | The VM to which a volume is attached and the environment of the relationship. |
| `infrastructure_events` | Auditable operations, actors, outcomes, and structured details. |
| `vm_status_checks` | Individual VM health or readiness check results. |

### Constraints and integrity

Primary keys identify records. Foreign keys enforce references to existing users, environments, networks, pools, VMs, and volumes. Unique constraints prevent duplicate resource identifiers, duplicate IP assignments within a network, and duplicate attachment records.

Composite foreign keys are important for multi-tenant isolation. A VM's network reference includes the environment identifier, so the database rejects a VM-to-network relationship across environment boundaries. The same approach is used for volume-to-pool ownership and VM-to-volume attachment.

Check constraints enforce local rules such as positive storage capacity, valid VLAN ranges, supported VM resource sizes, and non-empty image references.

The subnet exclusion constraint uses PostgreSQL's GiST support to reject overlapping managed networks. The `btree_gist` extension is used to provide the relevant GiST operator classes.

The IP allocation trigger validates that an address lies within its subnet, is not the network or broadcast address, and is associated with a VM that uses the selected network. The attachment trigger checks VM state and changes the volume state to attached.

The VM state trigger prevents a terminated VM from returning to an active state and maintains its termination timestamp.

### Reporting and queries

`environment_resource_inventory` reports active VMs, running VMs, allocated CPU and memory, pool capacity, and provisioned volume capacity. The additional queries identify compute quota violations, show VM-to-network and VM-to-volume relationships, and calculate storage usage per pool.

Indexes support common access paths: environment and VM state, VM network assignment, environment-specific volume lookup, chronological audit events, and the latest status checks for a VM.

The SQL file includes sample data for an engineering environment, an application operator, an administrator, a read-only auditor, a virtual subnet, a storage pool, a VM, an IP assignment, and an attached data volume.

### Transactional and concurrency limits

Relational constraints can enforce local facts and reference integrity. They cannot independently enforce every aggregate quota across multiple concurrent transactions.

For example, two simultaneous provisioning transactions could each observe enough free capacity and then collectively exceed the environment's VM quota. A production provisioning transaction should lock the relevant environment or allocation record, calculate current usage, reserve capacity, insert the resource, and commit. Serializable isolation is another option when accompanied by retry handling.

The inventory view is for reporting, not for concurrency control. The in-memory locking used by the language implementations also does not replace database transactions when multiple service instances share the same infrastructure inventory.

## Security and operational considerations

**Tenant isolation:** Check ownership at every relationship boundary. A valid VM identifier does not imply permission to access the VM, and a valid volume does not imply permission to attach it to an arbitrary workload.

**Least privilege:** Separate read-only inventory access, workload operations, and environment administration. Production systems should use provider-backed identity, authenticated service requests, and policy enforcement that cannot be bypassed by callers.

**Capacity enforcement:** Treat quotas as hard admission-control rules rather than advisory reports. Reservations and quota updates must be atomic under concurrent provisioning.

**Persistent storage:** Distinguish provisioned capacity from actual data usage. A 40 GiB virtual volume may reserve 40 GiB in a thick-provisioned pool, while thin provisioning may reserve physical capacity differently. The examples use simple provisioned-capacity accounting.

**Address management:** Prevent subnet overlap, duplicate IP assignments, accidental gateway allocation, and stale allocations after failures. IPv6, routed networks, DHCP, floating IPs, and overlays require additional models.

**Secrets and image integrity:** Image references should identify approved and verified images. Credentials, cloud API tokens, private keys, and guest passwords should not be stored in ordinary infrastructure metadata or audit payloads.

**Audit integrity:** Production audit events should be durable, access-controlled, time-synchronized, and protected against unauthorized modification. The in-memory audit lists in the examples are not tamper-proof records.

**Snapshots and recovery:** A metadata manifest is not a disk snapshot. Real snapshot operations must coordinate with the storage backend and, where application consistency is required, with guest agents or workload-specific quiescing.

**Failure recovery:** Provisioning can fail after a provider creates a resource but before the control plane records the result. A robust controller needs idempotency keys, provider resource identifiers, retry limits, cleanup workflows, and reconciliation that discovers resources left behind by partial failures.

**Observability:** Resource inventories show intended or recorded state. Production operations also require health checks, host capacity telemetry, storage latency measurements, network error metrics, alerting, and reconciliation between control-plane records and provider-reported state.

## Implementation distinctions

| Concern | Python | JavaScript | C++ | Java | PostgreSQL |
|---|---|---|---|---|---|
| Main emphasis | Resource simulation and invariant testing | Event-driven operations and asynchronous provisioning | Typed resource manager and subnet arithmetic | Enterprise domain model and access policy | Durable relational ownership and integrity |
| Resource representation | Dataclasses and dictionaries | Classes, maps, and sets | Structs, enums, and ordered maps | Domain classes and records | Related tables and constraints |
| Concurrency model | Process-local reentrant lock | Promise-queue mutex | Sequential demonstration | Sequential service demonstration | Transactions, locks, and isolation levels |
| Validation | Construction checks and cross-resource invariants | Identifier checks, capacity checks, and lifecycle transitions | Explicit subnet and quota validation | Typed requests and domain exceptions | Constraints, foreign keys, and triggers |
| Persistence | Optional JSON metadata manifest | In-memory state | In-memory state | In-memory state | Relational database |

The implementations share the same domain principles but use different mechanisms to make those principles explicit. Their differences also identify the boundaries between a simulator, an application control plane, and a production infrastructure management service.
