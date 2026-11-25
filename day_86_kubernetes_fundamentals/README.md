# Kubernetes Fundamentals: Container Orchestration, Clusters, and Declarative Infrastructure

## 1. Technical Scope

Kubernetes is a container orchestration platform that automates the deployment, scheduling, scaling, networking, and recovery of containerized workloads.

It manages workloads across a cluster of machines rather than requiring administrators to operate each container independently.

The implementations in this repository examine Kubernetes through five complementary engineering perspectives:

| Implementation | Engineering perspective | Primary responsibility |
|---|---|---|
| Python | Infrastructure simulation | Cluster behavior and reconciliation |
| JavaScript | Event-driven control plane | Admission policies and asynchronous operations |
| C++17 | Resource scheduling engine | Node selection and workload placement |
| Java 17 | Enterprise architecture | Domain modeling and workload lifecycle |
| PostgreSQL | Relational infrastructure model | Resource state, integrity, and operational reporting |

All implementations use standard language capabilities or PostgreSQL functionality without third-party application dependencies.

The cluster simulators use simplified orchestration behavior for educational purposes. They are not Kubernetes API servers, kubelets, container runtimes, or production scheduling replacements.

---

## 2. Kubernetes Architecture

Kubernetes follows a distributed architecture composed of a control plane and worker nodes.

<escape>
                       KUBERNETES CLUSTER
                              |
              +---------------+---------------+
              |                               |
         CONTROL PLANE                   WORKER NODES
              |                               |
       +------+------+               +--------+--------+
       |      |      |               |        |        |
    API    Scheduler Controller   Node 1   Node 2   Node 3
   Server              Manager       |        |        |
       |                 |        Kubelet  Kubelet  Kubelet
       |                 |           |        |        |
       +-----------------+        Container Container Container
                                  Runtime  Runtime  Runtime
                                     |        |        |
                                    Pods     Pods     Pods
</escape>

### 2.1 Control plane

The control plane maintains cluster-wide state and coordinates workload management.

| Component | Responsibility |
|---|---|
| kube-apiserver | Exposes the Kubernetes API and validates requests |
| etcd | Stores persistent cluster state |
| kube-scheduler | Assigns unscheduled Pods to suitable nodes |
| kube-controller-manager | Runs controllers that reconcile actual and desired state |
| cloud-controller-manager | Integrates cloud-specific infrastructure where applicable |

The control plane is responsible for coordination. It does not normally execute application containers.

### 2.2 Worker nodes

Worker nodes provide the compute resources required to execute workloads.

| Component | Responsibility |
|---|---|
| kubelet | Ensures assigned Pods are running according to their specifications |
| Container runtime | Pulls images and manages containers |
| kube-proxy | Implements Service networking behavior where configured |
| Operating system | Provides CPU, memory, networking, and storage resources |

Container runtimes commonly implement the Container Runtime Interface (CRI).

Examples include containerd and CRI-O.

The simulators represent worker-node resource accounting and Pod execution state without implementing an actual CRI runtime.

---

## 3. Core Kubernetes Objects

Kubernetes uses API objects to describe infrastructure and workload requirements.

### 3.1 Cluster

A cluster is a collection of control-plane and worker-node resources managed as one orchestration environment.

A cluster provides:

- Workload scheduling.
- Resource management.
- Networking.
- Service discovery.
- Declarative configuration.
- Health monitoring.
- Failure recovery.

Different environments can use separate clusters for development, testing, staging, and production.

### 3.2 Nodes

A Node represents a machine participating in a Kubernetes cluster.

Node resources include:

- CPU.
- Memory.
- Storage.
- Network capacity.
- Operating system characteristics.
- Architecture.
- Health conditions.

The implementations model CPU in millicores and memory in megabytes.

For CPU:

| CPU representation | Meaning |
|---|---|
| 1000m | One CPU core |
| 500m | Half a CPU core |
| 250m | One-quarter of a CPU core |
| 2000m | Two CPU cores |

A node's allocatable resources differ from its physical capacity because operating-system and Kubernetes components require resources themselves.

The schedulers use allocatable capacity rather than assuming every physical resource is available to application Pods.

### 3.3 Namespaces

Namespaces logically separate resources within a cluster.

Common examples include:

- `default`
- `kube-system`
- `kube-public`
- `kube-node-lease`

Organizations can create additional namespaces for applications, teams, and environments.

Namespaces support resource organization, access control, quotas, and policy application.

A namespace is not a separate physical cluster or a complete security boundary by itself.

### 3.4 Pods

A Pod is the smallest deployable unit in Kubernetes.

A Pod contains one or more closely related containers that share:

- Network namespace and IP address.
- Port space.
- Configured storage volumes.
- Pod-level lifecycle.

Containers within a Pod are scheduled together.

A Pod can be recreated when it fails. Its replacement generally receives a different Pod identity and may be placed on another node.

Applications should not depend on a Pod retaining its previous IP address or machine assignment.

### 3.5 Containers

Containers provide isolated application execution environments.

A container image packages application code, runtime dependencies, and other required filesystem content.

Important distinctions:

- An image is a packaged artifact.
- A container is an execution instance of an image.
- A Pod is the Kubernetes scheduling unit.
- A Deployment manages replicated application workloads.

An image reference should identify a specific version. Mutable tags such as `latest` are less suitable for controlled production releases than immutable image digests.

---

## 4. Declarative Infrastructure

Declarative infrastructure describes the required state of a system rather than listing every operational command necessary to produce that state.

For example, an application specification can declare:

- Application image.
- Desired replica count.
- Pod labels.
- CPU requests.
- Memory requests.
- CPU limits.
- Memory limits.
- Health probes.
- Deployment strategy.

The control plane uses controllers to reconcile the actual state with the declared state.

### 4.1 Desired state versus actual state

These are separate concepts.

| Desired state | Actual state |
|---|---|
| Three application replicas | Two running Pods |
| Version 2 container image | Version 1 still executing |
| Three available worker nodes | One unavailable worker |
| Service selector | Currently matching ready endpoints |
| Declared CPU request | Resources allocated to scheduled Pods |

The desired state is the target. Actual state describes what currently exists.

A difference between them represents a reconciliation requirement.

### 4.2 Reconciliation loop

A controller repeatedly observes resources and takes actions to reduce differences between desired and actual state.

<escape>
Observe desired state
        |
        v
Observe actual state
        |
        v
Compare both states
        |
        +---- States match ----> Wait and observe again
        |
        +---- States differ
                    |
                    v
             Calculate actions
                    |
                    v
             Create / Delete /
             Replace resources
                    |
                    v
             Observe new state
                    |
                    v
                Repeat
</escape>

Reconciliation is continuous rather than a one-time deployment operation.

A successful reconciliation does not imply that the cluster will remain healthy indefinitely. Controllers continue monitoring and responding to changes.

The Python and Java implementations explicitly represent this process.

---

## 5. Kubernetes Workload Controllers

Different controllers provide different workload-management guarantees.

| Controller | Purpose | Typical application |
|---|---|---|
| Deployment | Manages replicated stateless applications | REST APIs and web applications |
| ReplicaSet | Maintains a specified number of matching Pods | Deployment-managed replica maintenance |
| StatefulSet | Provides stable Pod identity and ordered operations | Databases and distributed stateful systems |
| DaemonSet | Runs a Pod on eligible nodes | Logging and node monitoring |
| Job | Runs tasks until successful completion | Data processing |
| CronJob | Creates Jobs on a schedule | Scheduled maintenance |

### 5.1 Deployment

A Deployment manages application releases and replicated workloads.

Its specification includes:

- Pod template.
- Replica count.
- Selector.
- Update strategy.

A Deployment normally manages ReplicaSets, which manage Pods.

### 5.2 ReplicaSet

A ReplicaSet ensures that a specified number of matching Pods are running.

For example:

- Desired replicas: 3.
- Running replicas: 2.
- Required action: create one additional Pod.

ReplicaSets are generally managed through Deployments rather than manipulated directly for routine application releases.

### 5.3 Scaling

Scaling changes the desired number of replicas.

Scale-up:

- Desired replicas increase.
- The controller creates additional Pods.
- The scheduler places them on feasible nodes.

Scale-down:

- Desired replicas decrease.
- Excess Pods are terminated.
- Their allocated resources become available.

A desired replica count does not guarantee successful scheduling. Insufficient resources, admission rejection, node failures, or other constraints can prevent the cluster from reaching the target.

---

## 6. Scheduling and Resource Management

The Kubernetes scheduler determines where unscheduled Pods should execute.

It considers workload requirements and node characteristics.

### 6.1 Resource requests

A resource request specifies the amount of CPU or memory required for scheduling.

For example:

| Resource | Request |
|---|---:|
| CPU | 500m |
| Memory | 512Mi |

A scheduler generally avoids placing a Pod on a node whose remaining allocatable resources cannot satisfy its requests.

Requests influence scheduling and resource allocation decisions.

### 6.2 Resource limits

Limits define maximum resource consumption.

CPU and memory have different enforcement behavior.

- CPU limits constrain CPU consumption through throttling.
- Memory limits can result in termination when a container exceeds its permitted memory allocation.

A Pod can have requests without explicitly defining limits.

Kubernetes can also apply default resource behavior through namespace-level configuration.

### 6.3 Scheduling constraints

Scheduling can involve:

- Resource availability.
- Node selectors.
- Node affinity.
- Pod affinity.
- Pod anti-affinity.
- Taints and tolerations.
- Topology spread constraints.
- Persistent-volume availability.

The sample schedulers use CPU and memory feasibility followed by a utilization-based selection rule.

They intentionally do not reproduce the complete Kubernetes scheduling framework.

### 6.4 Scheduling algorithm

The simplified scheduling procedure is:

1. Collect available worker nodes.
2. Exclude nodes that are not Ready.
3. Calculate allocated CPU and memory.
4. Compare remaining capacity against Pod requests.
5. Reject infeasible nodes.
6. Rank feasible nodes by utilization.
7. Assign the Pod to the selected node.

For N nodes, evaluating one Pod requires O(N) feasibility checks.

Sorting feasible nodes requires O(N log N) time.

Production scheduling includes additional filtering, scoring, plugins, constraints, and scheduling-cycle behavior.

---

## 7. Pod Lifecycle and Health

A Pod moves through lifecycle phases.

| Phase | Meaning |
|---|---|
| Pending | Accepted but not yet fully scheduled and running |
| Running | At least one container is running or starting |
| Succeeded | All containers completed successfully |
| Failed | All containers terminated and at least one failed |
| Unknown | Pod state cannot currently be determined |

Terminating is commonly represented as a deletion state rather than a Pod phase.

The simulations represent it explicitly to make lifecycle transitions easier to understand.

### 7.1 Readiness probes

A readiness probe determines whether a container is ready to receive application traffic.

An application can be running but not ready.

A failed readiness probe removes the affected Pod from normal Service endpoint selection.

### 7.2 Liveness probes

A liveness probe determines whether a container should be restarted.

It is intended to detect application conditions that prevent continued useful operation.

### 7.3 Startup probes

A startup probe provides additional initialization time for applications that take longer to start.

It prevents liveness and readiness checks from prematurely affecting an application during initialization.

These three probes have different responsibilities and should not be treated as interchangeable.

### 7.4 Self-healing

Self-healing refers to Kubernetes controllers and node agents taking corrective action when workloads or infrastructure fail.

Examples:

- Replacing failed Deployment Pods.
- Restarting containers under the applicable restart policy.
- Detecting unavailable nodes.
- Recreating missing replicas.
- Removing unready Pods from normal Service routing.

The Python, JavaScript, C++, and Java implementations simulate failed-Pod detection and replica replacement.

---

## 8. Services and Networking

Pods are temporary workload instances. Their IP addresses and locations can change.

A Service provides a stable networking abstraction for a logical group of Pods.

### 8.1 Service selectors

A Service selector identifies Pods through labels.

For example:

| Label key | Label value |
|---|---|
| app | payment-api |
| tier | backend |

A matching ready Pod can become a Service endpoint.

### 8.2 Service types

| Type | Purpose |
|---|---|
| ClusterIP | Internal cluster access |
| NodePort | Exposes a port on eligible nodes |
| LoadBalancer | Integrates with an external load-balancing implementation |
| ExternalName | Maps a Service to an external DNS name |

ClusterIP is the default Service type.

### 8.3 Service discovery

Kubernetes normally provides DNS-based discovery for Services.

A workload can access another Service using its DNS name rather than maintaining a manually updated list of Pod IP addresses.

The implementations use label-based endpoint discovery to model this behavior.

The database view `ready_service_endpoints` identifies matching ready Pods on Ready nodes.

It represents a reporting projection, not the complete Kubernetes EndpointSlice controller.

---

## 9. Configuration, Storage, and Security Concepts

### 9.1 ConfigMaps

A ConfigMap stores non-confidential configuration data.

Examples:

- Application settings.
- Feature flags.
- Environment-specific configuration.
- Non-sensitive connection parameters.

### 9.2 Secrets

A Secret stores confidential application data such as credentials and tokens.

Base64 encoding is not encryption.

Production environments should use appropriate encryption at rest, access controls, restricted permissions, and external secret-management integrations where required.

### 9.3 Persistent volumes

Kubernetes storage abstractions separate application storage requirements from the lifecycle of individual Pods.

| Object | Responsibility |
|---|---|
| PersistentVolume | Represents provisioned storage |
| PersistentVolumeClaim | Requests storage |
| StorageClass | Defines storage provisioning behavior |

A PersistentVolumeClaim allows workloads to request storage without directly managing the underlying storage implementation.

### 9.4 Security controls

Important Kubernetes security mechanisms include:

- Role-Based Access Control (RBAC).
- ServiceAccounts.
- NetworkPolicies.
- Pod Security Standards.
- Security contexts.
- Admission controllers.
- Image provenance and signature verification.
- Secret protection.
- Encryption at rest.
- Audit logging.
- Least-privilege permissions.

The JavaScript and Java implementations model admission policies that reject workloads failing defined validation rules.

These examples are simplified policy engines, not replacements for Kubernetes admission webhooks or admission plugins.

---

## 10. Python Implementation: Infrastructure Simulation

The Python file models cluster behavior using dataclasses, enums, dictionaries, and service classes.

### Main components

| Component | Responsibility |
|---|---|
| ResourceRequirements | CPU and memory requests |
| Pod | Individual workload execution state |
| Node | Worker-node capacity and allocations |
| Deployment | Desired replica count and Pod ownership |
| Service | Label-based endpoint selection |
| Scheduler | Feasible node selection |
| KubernetesCluster | Cluster state and reconciliation |

### Important mechanisms

**Resource accounting**

Each node calculates CPU and memory allocated to active Pods.

Pending and running Pods are included in resource accounting.

**Reconciliation**

The cluster compares active replicas with the desired replica count.

Missing replicas are created. Excess replicas are removed.

**Failure recovery**

A failed Pod is removed from its node allocation and the Deployment reconciler attempts replacement.

**Rolling updates**

The implementation creates replacement Pods using a new image before removing previous Pods.

Insufficient capacity can interrupt an update.

**Service discovery**

Service endpoints are determined using label matching and Pod readiness.

### Complexity considerations

- Node feasibility evaluation: O(N).
- Node selection with sorting: O(N log N).
- Pod lookup within a Deployment dictionary: average O(1).
- Service endpoint discovery: O(P), where P represents examined Pods.

The simulator is useful for studying how declarative workloads, resource constraints, and failure recovery interact.

---

## 11. JavaScript Implementation: Event-Driven Orchestration

The JavaScript implementation emphasizes asynchronous execution and event-driven architecture.

### Main components

- `ClusterNode`
- `AdmissionController`
- `KubernetesCluster`
- `EventEmitter`
- Asynchronous scheduling operations
- Structured audit events

### Event-driven behavior

The cluster emits events when:

- Nodes are added.
- Deployments are created.
- Pods are scheduled.
- Scheduling fails.
- Replicas change.
- Rolling updates complete.
- Pods fail.
- Nodes are drained.

This separates infrastructure state transitions from audit and monitoring consumers.

### Admission policy evaluation

The admission controller supports multiple asynchronous policy functions.

The sample policies enforce:

1. Trusted image registry usage.
2. Minimum memory requests.
3. Cluster-level Pod quotas.

A rejected Pod does not proceed through scheduling.

### Asynchronous operations

Scheduling and reconciliation use asynchronous functions.

This structure provides a foundation for modeling external operations such as:

- API requests.
- Admission webhooks.
- Infrastructure integrations.
- Monitoring callbacks.
- Distributed control-plane interactions.

### Failure handling

Rolling updates retain the previous workload specification when replacement scheduling fails.

This is a simplified rollback mechanism. Real Kubernetes rollout behavior is managed through Deployment and ReplicaSet state, with configurable surge and availability policies.

---

## 12. C++17 Implementation: Resource Scheduling Engine

The C++17 implementation emphasizes resource allocation, explicit domain structures, and deterministic scheduling decisions.

### Domain structures

| Structure | Responsibility |
|---|---|
| Resources | CPU and memory requests |
| Pod | Workload execution state |
| Node | Resource capacity and allocation |
| Deployment | Desired replicas and workload revision |
| Service | Endpoint selection |
| Cluster | Scheduling and orchestration operations |

### Scheduling decisions

The scheduler:

1. Checks each node.
2. Rejects unavailable nodes.
3. Checks CPU capacity.
4. Checks memory capacity.
5. Ranks feasible nodes.
6. Selects the least-utilized feasible node.

The implementation uses STL containers and algorithms rather than external scheduling libraries.

### Resource accounting

Node allocations are derived from active Pod records.

This keeps the accounting model connected to workload state.

Failed and terminating Pods do not consume the modeled resources.

### Rolling updates

The update engine creates replacement Pods and removes the corresponding old Pods.

If scheduling fails, newly created replacement Pods are removed, the previous image and revision are restored, and reconciliation attempts to restore the previous replica count.

### Tradeoffs

The program uses vectors and linear searches for clarity and deterministic behavior.

This makes many operations O(P), where P is the number of Pods in the relevant workload or node.

A production implementation could introduce indexed containers for frequent identifier lookups.

---

## 13. Java 17 Implementation: Enterprise Cluster Management

The Java implementation uses records, enums, immutable collections, domain classes, and policy objects.

It separates workload definitions from execution state.

### Architectural separation

| Class | Responsibility |
|---|---|
| ResourceRequest | Immutable resource requirements |
| WorkloadSpec | Declarative workload specification |
| Pod | Runtime workload state |
| Node | Worker-node resource accounting |
| Deployment | Replica and revision management |
| AdmissionPolicy | Workload acceptance rules |
| Service | Application endpoint selection |
| Cluster | Orchestration and lifecycle coordination |

### Immutable domain data

`ResourceRequest`, `WorkloadSpec`, and `ClusterEvent` use Java records.

The workload specification stores an immutable selector map through `Map.copyOf`.

This prevents callers from changing the declared selector through a mutable reference after construction.

### Enterprise policy model

Admission policies are implemented as predicates.

Multiple validation rules can be registered and evaluated before scheduling.

The example requires:

- An approved container image registry.
- Minimum memory allocation.
- Valid workload specifications.
- Sufficient node resources.

### State transitions

The cluster coordinates:

- Node registration.
- Deployment creation.
- Pod scheduling.
- Scaling.
- Failure recovery.
- Rolling updates.
- Node draining.
- Service discovery.

### Operational event history

Cluster operations generate timestamped events with sequence numbers.

This provides a simple audit trail for understanding state changes and debugging orchestration behavior.

The implementation uses a thread-safe event collection, but the cluster's state transitions are still designed for a single coordinating execution flow. A production multi-threaded controller would require explicit concurrency control.

---

## 14. PostgreSQL Implementation: Relational Infrastructure Model

The SQL file models Kubernetes resources and operational records using a relational schema.

It uses foreign keys, checks, indexes, JSONB, views, functions, triggers, transactions, and analytical queries.

### 14.1 Relational architecture

| Table | Stored information |
|---|---|
| clusters | Cluster identity and environment |
| nodes | Worker and control-plane capacity |
| namespaces | Logical resource boundaries |
| resource_quotas | Namespace-level resource constraints |
| workloads | Declarative workload specifications |
| replica_sets | Workload revision records |
| pods | Actual Pod state |
| containers | Container execution instances |
| node_conditions | Node health conditions |
| services | Service specifications |
| service_endpoints | Service-to-Pod relationships |
| cluster_events | Operational event history |
| reconciliation_runs | Desired versus actual state |

### 14.2 Referential integrity

Foreign keys enforce relationships between resources.

For example:

- A Node belongs to a Cluster.
- A Namespace belongs to a Cluster.
- A Workload belongs to a Namespace.
- A Pod belongs to a Namespace.
- A Pod can reference a Workload and ReplicaSet.
- A Pod can reference an assigned Node.
- A Service belongs to a Namespace.
- A Service Endpoint references a Service and Pod.

The schema uses cascading deletion selectively to avoid leaving dependent records behind.

### 14.3 JSONB selectors and labels

Kubernetes selectors and labels are naturally represented as structured key-value data.

PostgreSQL JSONB supports:

- Structured storage.
- Key-value matching.
- Containment queries.
- GIN indexing.

The schema uses JSONB for workload selectors and Pod labels.

For example, a Service selector can identify all Pods whose labels contain the required application key.

### 14.4 Integrity enforcement

The schema enforces several rules.

- CPU requests must be positive.
- Memory requests must be positive.
- Replica counts cannot be negative.
- Ports must fall within the valid TCP/UDP port range.
- Container images must be non-empty and include a tag.
- A ready Pod must be in the Running phase.
- A Pod and its assigned Node must belong to the same Cluster.

The cross-cluster validation trigger provides an integrity check that ordinary foreign keys cannot express directly.

### 14.5 Resource utilization

The `node_resource_utilization` view aggregates resource requests from Pods.

It distinguishes:

- Physical node capacity.
- Allocatable capacity.
- Allocated CPU requests.
- Allocated memory requests.

Resource requests are not the same as actual runtime CPU and memory consumption.

Actual utilization monitoring requires runtime metrics.

### 14.6 Workload health

The `workload_health` view compares desired replicas against running and ready replicas.

This supports operational classifications:

- Healthy.
- Degraded.
- Unavailable.

A workload can have running replicas that are not ready. This is why running and ready counts are tracked separately.

### 14.7 Scheduling eligibility

The `eligible_nodes` function identifies nodes that have sufficient remaining CPU and memory capacity.

It excludes nodes that are not Ready.

This provides a relational representation of resource-based scheduling eligibility.

It does not implement the complete Kubernetes scheduler, which also considers affinity, taints, topology, volumes, and other scheduling constraints.

### 14.8 Transaction management

The scaling example updates the desired replica count and generation inside a transaction.

The database records the new desired state.

It does not directly create Pods or execute containers.

A separate controller or reconciliation service must observe the change and carry out the necessary operations.

---

## 15. How the Five Implementations Fit Together

The implementations examine different layers of the same orchestration model.

<escape>
Declarative Workload Specification
               |
               v
       Admission Validation
               |
               v
       Resource Scheduling
               |
               v
         Worker Node
               |
               v
          Pod Creation
               |
               v
      Container Execution
               |
               v
        Readiness Checks
               |
               v
       Service Endpoints
               |
               v
       Runtime Monitoring
               |
               v
        Reconciliation
               |
               +------> Desired State
</escape>

| Layer | Main responsibility | Implementation |
|---|---|---|
| Specification | Declare workload requirements | Java, SQL |
| Validation | Enforce workload policies | JavaScript, Java |
| Scheduling | Allocate available resources | C++17, Python |
| Execution model | Represent Pod lifecycle | Python, Java |
| Event processing | Record infrastructure transitions | JavaScript, Java |
| Persistence | Store cluster and workload records | PostgreSQL |
| Reporting | Evaluate resource and workload health | PostgreSQL, C++17 |

The layers are conceptually connected, but the five programs are independent implementations rather than components of one deployed Kubernetes control plane.

---

## 16. Important Operational Distinctions

| Concept | Meaning | Common misunderstanding |
|---|---|---|
| Cluster | Collection of managed infrastructure resources | A cluster is not one machine |
| Node | Machine participating in a cluster | A node is not an application |
| Pod | Smallest scheduling unit | A Pod is not necessarily one container |
| Container | Running instance of an image | A container is not a Deployment |
| Image | Packaged application artifact | An image is not a running process |
| Deployment | Manages replicated application releases | A Deployment does not directly represent a physical node |
| ReplicaSet | Maintains a replica count | A ReplicaSet is not the same as a Service |
| Service | Stable networking abstraction | A Service is not a workload controller |
| Namespace | Logical resource organization | A Namespace is not a separate cluster |
| Scheduler | Selects suitable nodes | Scheduling does not guarantee application readiness |
| Controller | Reconciles desired and actual state | A controller does not replace the API server |
| ConfigMap | Non-confidential configuration | It is not a Secret |
| Secret | Confidential configuration data | Base64 encoding does not provide encryption |
| PersistentVolume | Storage resource | It is not a Pod-local temporary filesystem |

---

## 17. Failure Scenarios and Recovery

Kubernetes infrastructure must account for partial failures.

| Failure | Expected operational response |
|---|---|
| Pod crashes | Restart or replacement according to workload configuration |
| Node becomes unavailable | Node health detection and workload recovery |
| Insufficient CPU | Pod remains unscheduled until capacity becomes available |
| Insufficient memory | Pod remains unscheduled or encounters runtime memory constraints |
| Image pull failure | Container remains in a waiting or image-pull failure condition |
| Readiness failure | Pod is excluded from ready Service endpoints |
| Liveness failure | Container may be restarted |
| Invalid workload configuration | API validation or admission rejection |
| Service selector mismatch | No matching Service endpoints |
| Persistent storage unavailable | Pod may remain pending or fail to mount storage |
| Failed rollout | Deployment may remain degraded or require rollback |

A critical distinction exists between scheduling failure and runtime failure.

A scheduling failure occurs before a Pod is assigned to a node.

A runtime failure occurs after the Pod has been assigned and its containers have started or attempted to start.

These failures require different diagnostics.

---

## 18. Rolling Updates and Application Availability

A Deployment supports controlled application replacement.

A rolling update gradually replaces Pods running an older revision with Pods running a newer revision.

Important configuration fields include:

- `maxSurge`
- `maxUnavailable`
- `progressDeadlineSeconds`
- `revisionHistoryLimit`

`maxSurge` controls how many additional Pods can be created above the desired replica count.

`maxUnavailable` controls how many replicas may be unavailable during an update.

For a three-replica workload, a rollout can create a replacement before removing an older Pod, provided sufficient capacity and readiness conditions exist.

The simplified programs demonstrate replacement-first behavior but do not implement every Kubernetes Deployment strategy rule.

A successful image replacement also does not prove that the new application version is functionally correct. Readiness checks and application-level validation remain necessary.

---

## 19. Performance and Scalability Considerations

Kubernetes performance depends on cluster size, workload distribution, resource requests, control-plane health, and networking.

Important considerations include:

- Scheduling throughput.
- API server request volume.
- etcd latency and database growth.
- Controller reconciliation frequency.
- Pod startup time.
- Image distribution.
- Node resource fragmentation.
- Service endpoint update frequency.
- Monitoring data volume.

The example implementations intentionally use simple in-memory structures.

Their complexity characteristics differ from a distributed Kubernetes control plane.

| Operation | Simplified implementation |
|---|---|
| Node lookup | O(N) in vector-based implementations |
| Node feasibility | O(N) across nodes |
| Sorted scheduling | O(N log N) |
| Deployment lookup | Average O(1) in dictionary-based implementations |
| Service endpoint discovery | O(P) across examined Pods |
| Resource utilization | O(P) aggregation over relevant Pods |

The PostgreSQL implementation uses indexes for frequently queried relationships and JSONB containment.

The actual query planner should be examined with `EXPLAIN (ANALYZE, BUFFERS)` against realistic data volumes before production optimization decisions.

---

## 20. Security and Production Considerations

A production Kubernetes environment requires stronger controls than the simplified educational models.

### Identity and access

- Use RBAC for API authorization.
- Restrict ServiceAccount permissions.
- Avoid unnecessary cluster-admin privileges.
- Protect control-plane credentials.
- Audit privileged operations.

### Workload security

- Use trusted and verified container images.
- Prefer immutable image digests.
- Run containers as non-root where possible.
- Restrict Linux capabilities.
- Configure seccomp and appropriate security contexts.
- Avoid privileged containers unless explicitly required.

### Network security

- Use NetworkPolicies where supported.
- Restrict unnecessary ingress and egress.
- Separate workloads through appropriate network segmentation.
- Protect control-plane endpoints.

### Resource governance

- Define requests and limits.
- Apply namespace ResourceQuotas.
- Use LimitRanges where appropriate.
- Configure workload availability policies.
- Monitor CPU and memory pressure.

### Reliability

- Distribute replicas across failure domains.
- Configure readiness, liveness, and startup probes.
- Use PodDisruptionBudgets for applicable voluntary disruptions.
- Configure persistent storage correctly.
- Monitor control-plane and worker-node health.
- Test recovery procedures.

### Operational observability

A production environment generally needs:

- Structured logs.
- Infrastructure metrics.
- Application metrics.
- Distributed tracing.
- Kubernetes events.
- Audit records.
- Alerting.
- Capacity monitoring.

The sample implementations use event records and state reports to illustrate these operational requirements.

---

## 21. Implementation Limitations

These programs model fundamental orchestration mechanisms. They do not reproduce all Kubernetes API behavior.

| Feature | Implemented | Limitation |
|---|---|---|
| Cluster and node modeling | Yes | No real node registration |
| CPU and memory requests | Yes | Simplified accounting |
| Pod lifecycle | Yes | Simplified lifecycle transitions |
| Deployment replicas | Yes | No full ReplicaSet controller |
| Declarative reconciliation | Yes | In-memory simulation |
| Scheduling | Yes | No complete scheduler framework |
| Service selectors | Yes | No real network dataplane |
| Readiness representation | Yes | No actual HTTP, TCP, or exec probes |
| Failure recovery | Yes | Simplified controller behavior |
| Rolling updates | Yes | Not full Kubernetes rollout semantics |
| Admission policies | Yes | No actual admission webhook integration |
| Namespaces | SQL | Relational modeling only |
| Resource quotas | SQL | Reporting and validation examples, not full admission enforcement |
| Persistent storage | Not simulated | PV, PVC, CSI, and storage provisioning are outside the executable examples |
| RBAC | Not simulated | Security concepts are documented |
| etcd | Not implemented | Database schema is an educational relational representation |
| Actual containers | Not executed | No container runtime integration |
| Real Kubernetes API | Not connected | No live cluster operations |

The Python, JavaScript, C++, and Java implementations use independent in-memory cluster models. Their state is not automatically synchronized with the PostgreSQL database.

The PostgreSQL model records declarative specifications and observed infrastructure state but does not independently schedule workloads or execute containers.

These boundaries are important when interpreting the results.

---

## 22. Execution Requirements

| Deliverable | Requirement |
|---|---|
| Python | Python 3.10 or newer |
| JavaScript | Node.js 18 or newer |
| C++17 | Compiler supporting the C++17 standard |
| Java | JDK 17 |
| PostgreSQL | PostgreSQL 15 or newer |

The Python and JavaScript examples use standard-library functionality.

The C++17 program uses STL containers and algorithms.

The Java program uses Java 17 language features and standard APIs.

The PostgreSQL script creates the `kube_lab` schema, domain types, relational tables, triggers, functions, views, sample records, and reporting queries.

The database script is intended for a development database and creates persistent schema objects. Its initial DDL and sample-data section is enclosed in a transaction.

---

## 23. Technical Terminology

| Term | Definition |
|---|---|
| Orchestration | Automated coordination of application workloads |
| Control plane | Components responsible for cluster coordination |
| Worker node | Machine that executes scheduled workloads |
| Declarative configuration | Description of the required system state |
| Reconciliation | Process of reducing differences between desired and actual state |
| Scheduler | Component responsible for assigning Pods to nodes |
| Allocatable resources | Node resources available for workload scheduling |
| Resource request | Minimum resource amount used for scheduling decisions |
| Resource limit | Maximum permitted resource consumption |
| Replica | One instance of a replicated workload |
| Selector | Criteria used to identify matching resources |
| Label | Key-value metadata attached to Kubernetes objects |
| Readiness | Whether an application instance can receive traffic |
| Liveness | Whether an application instance should continue running |
| Admission control | API request validation and policy enforcement |
| Rollout | Controlled replacement of an application version |
| Self-healing | Automated recovery from workload or infrastructure failures |
| Service discovery | Mechanism for locating application endpoints |
| Node drain | Controlled removal of workloads from a node |
| Resource quota | Namespace-level resource consumption restriction |
| Persistent storage | Storage that can outlive an individual Pod |

The central architectural distinction is that Kubernetes manages declared application state through controllers and scheduling decisions while actual execution takes place on worker-node infrastructure.
