# Kubernetes Pods: Architecture, Lifecycle, Manifests and Multi-Container Workloads

## 1. Pod Architecture

A Pod is the smallest deployable workload unit in Kubernetes. It represents one or more containers that are scheduled together and share selected execution resources.

Kubernetes schedules Pods rather than independently scheduling every application container.

A Pod provides a common environment for its containers, including:

- A shared network namespace.
- A shared Pod IP address.
- Shared port space.
- Optional shared storage through mounted volumes.
- Coordinated scheduling and lifecycle management.
- Shared access to Pod-level configuration and identity.

Each container retains its own process space, filesystem image, resource limits and container runtime state.

### Architecture

    Kubernetes Cluster
    |
    +-- Control Plane
    |   |
    |   +-- API Server
    |   +-- Scheduler
    |   +-- Controller Manager
    |
    +-- Worker Node
        |
        +-- Kubelet
        |
        +-- Container Runtime
        |
        +-- Pod: orders-api
            |
            +-- Pod Network Namespace
            |   |
            |   +-- Shared Pod IP
            |   +-- Shared Port Space
            |
            +-- Application Container
            |   +-- API service
            |
            +-- Sidecar Container
            |   +-- Log collection
            |
            +-- Shared Volume
                +-- Application logs

The control plane manages desired state and scheduling decisions. The kubelet on the selected worker node coordinates container execution and reports observed state.

## 2. Pod Components and Responsibilities

| Component | Responsibility |
|---|---|
| Pod metadata | Identifies the Pod through its name, namespace, labels and annotations |
| Pod specification | Defines the desired workload configuration |
| Application container | Executes the primary application workload |
| Init container | Performs preparation before application containers start |
| Sidecar container | Provides supporting functionality alongside the application |
| Pod network | Provides a shared network namespace and Pod IP |
| Pod volume | Provides storage that can be mounted by multiple containers |
| Service account | Provides the Pod's Kubernetes identity |
| Pod conditions | Describe scheduling, initialization and readiness |
| Pod status | Reports the observed lifecycle phase and container states |

### Pod versus Container

A container is an isolated application execution environment.

A Pod is a Kubernetes scheduling and management unit that can contain multiple related containers.

Containers within one Pod:

- Run on the same worker node.
- Share the Pod network namespace.
- Can communicate through `localhost`.
- Can mount the same Pod volume.
- Are managed under one Pod lifecycle.
- Have separate container runtime states.

Containers in different Pods generally have different Pod IP addresses and independent lifecycle management.

## 3. Pod Lifecycle

The Pod lifecycle describes how Kubernetes moves a workload from creation to termination.

### Lifecycle phases

| Phase | Meaning |
|---|---|
| Pending | The Pod has been accepted but is not yet fully running |
| Running | The Pod has been bound to a node and at least one application container has started |
| Succeeded | All application containers have terminated successfully and will not be restarted |
| Failed | All application containers have terminated and at least one terminated unsuccessfully |
| Unknown | The control plane cannot determine the Pod's state |

A Pending Pod may be waiting for scheduling, image downloads, volume preparation or initialization.

Running does not necessarily mean Ready. An application can be running while failing its readiness probe.

### Lifecycle sequence

    Pod Manifest Submitted
             |
             v
        API Validation
             |
             v
          Pending
             |
             v
          Scheduling
             |
             v
       Worker Node Selected
             |
             v
       Init Containers
             |
             v
     Application Containers
             |
             v
           Running
             |
             v
       Readiness Evaluation
             |
       +-----+------+
       |            |
       v            v
     Ready       Not Ready
       |            |
       +-----+------+
             |
             v
      Runtime Monitoring
             |
       +-----+------+
       |            |
       v            v
   Continues     Termination
       |            |
       |       Graceful Shutdown
       |            |
       |       Resource Release
       |            |
       +------> Completed

### Pod conditions

Pod phases and Pod conditions represent different information.

Phases provide a broad lifecycle classification.

Conditions provide more specific information about operational readiness and progress.

Important conditions include:

- `PodScheduled`: Indicates whether the Pod has been assigned to a node.
- `Initialized`: Indicates whether initialization has completed.
- `Ready`: Indicates whether the Pod can serve its intended workload.
- `ContainersReady`: Indicates whether all application containers are ready.

A Pod can be in the Running phase while its Ready condition is False.

## 4. Container Lifecycle and Restart Policies

Each container has its own lifecycle within the Pod.

| State | Description |
|---|---|
| Waiting | Container is waiting for an execution prerequisite |
| Running | Container process is executing |
| Terminated | Container process has stopped |

A terminated container may be restarted depending on the Pod restart policy.

### Restart policies

| Policy | Behavior |
|---|---|
| Always | Restart containers after termination |
| OnFailure | Restart containers when they terminate unsuccessfully |
| Never | Do not restart terminated containers |

Restart policies are specified at the Pod level.

They apply to application containers and init containers, subject to their respective execution semantics.

A restart does not create a new Pod. The Pod retains its identity while the affected container is restarted.

The restart count helps identify repeated failures.

### Failure scenarios

| Failure | Operational implication |
|---|---|
| Application exits with code 1 | Restart behavior depends on the restart policy |
| Application exits with code 0 | Successful termination |
| Liveness probe fails | Kubelet may restart the affected container |
| Readiness probe fails | Container remains running but is removed from readiness-based service endpoints |
| Image cannot be downloaded | Container remains waiting |
| Worker node becomes unavailable | Pod may become inaccessible and require control-plane recovery |

Repeated failures may result in `CrashLoopBackOff`, a container waiting reason associated with repeated unsuccessful starts and backoff delays.

## 5. Pod Manifests

A Pod manifest is a declarative YAML or JSON representation of the desired Pod configuration.

Kubernetes uses the manifest to validate and create the workload through the API server.

A typical Pod manifest contains:

| Field | Purpose |
|---|---|
| `apiVersion` | Identifies the Kubernetes API version |
| `kind` | Identifies the resource type |
| `metadata` | Contains name, namespace, labels and annotations |
| `spec` | Defines the desired configuration |
| `containers` | Defines application containers |
| `initContainers` | Defines initialization containers |
| `volumes` | Defines storage resources |
| `restartPolicy` | Controls container restart behavior |
| `resources` | Defines CPU and memory requests and limits |
| `probes` | Defines application health checks |
| `serviceAccountName` | Specifies the workload identity |

### Example Pod manifest

    apiVersion: v1
    kind: Pod
    metadata:
      name: orders-api
      namespace: production
      labels:
        app: orders-api
        tier: backend

    spec:
      restartPolicy: Always
      terminationGracePeriodSeconds: 30

      serviceAccountName: orders-service

      initContainers:
        - name: config-check
          image: busybox:1.36
          command:
            - sh
            - -c
            - echo checking configuration

      containers:
        - name: api
          image: nginx:1.27

          ports:
            - containerPort: 8080

          resources:
            requests:
              cpu: 300m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 512Mi

          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8080

          livenessProbe:
            httpGet:
              path: /health/live
              port: 8080

        - name: log-agent
          image: fluent-bit:3.1

          resources:
            requests:
              cpu: 100m
              memory: 128Mi

### Applying and inspecting manifests

Typical Kubernetes operations include:

- `kubectl apply -f pod.yaml`: Applies the declarative manifest.
- `kubectl get pods`: Lists Pods in the current namespace.
- `kubectl get pods -n production`: Lists Pods in a specific namespace.
- `kubectl describe pod orders-api`: Displays Pod configuration, conditions and events.
- `kubectl get pod orders-api -o yaml`: Displays the Pod resource representation.
- `kubectl logs orders-api -c api`: Retrieves logs from a specific container.
- `kubectl exec -it orders-api -c api -- sh`: Opens a shell inside a container.
- `kubectl delete pod orders-api`: Requests Pod deletion.

The actual Pod object stored by the API server can contain defaults and fields added by admission controllers. It is not necessarily identical to the original manifest.

A standalone Pod does not provide automatic replacement after deletion. Workloads requiring continuous availability should generally be managed through higher-level controllers such as Deployments or StatefulSets.

## 6. Multi-Container Pods

A multi-container Pod groups containers that have a close operational relationship.

The containers share scheduling, networking and potentially storage, while maintaining independent processes.

### Common multi-container patterns

#### Sidecar

A sidecar provides supporting functionality to the primary application.

Examples:

- Log collection.
- Metrics collection.
- Proxy functionality.
- Local monitoring agents.

The application and sidecar can access a shared volume to exchange files.

#### Adapter

An adapter transforms application output into a format expected by another system.

Examples include:

- Converting application logs into a standardized structure.
- Transforming monitoring data.
- Normalizing application metadata.

#### Ambassador

An ambassador container provides an intermediary communication mechanism.

Examples include:

- Local proxying.
- Connection routing.
- Service access abstraction.

These patterns are architectural approaches rather than separate Kubernetes resource types.

### Multi-container communication

Containers in one Pod share the network namespace.

For example:

    Pod IP: 10.10.2.15
    |
    +-- API container
    |   +-- localhost:8080
    |
    +-- Metrics sidecar
        +-- localhost:9100

The API container and metrics sidecar can communicate through localhost.

Since they share the same network namespace, they cannot independently bind the same IP address and port combination.

### Shared volumes

A Pod volume can be mounted by multiple containers.

Example:

    Pod
    |
    +-- API Container
    |   +-- /var/log/application
    |
    +-- Log Agent
    |   +-- /var/log/application
    |
    +-- emptyDir Volume
        +-- Shared application log files

An `emptyDir` volume is created for the Pod and remains available while the Pod exists on its node. Its data does not provide durable storage after the Pod is removed.

Persistent data requires an appropriate persistent storage configuration.

### Benefits and tradeoffs

| Benefits | Tradeoffs |
|---|---|
| Local communication | Shared failure and scheduling domain |
| Shared storage | Additional storage coordination |
| Coordinated lifecycle | Independent scaling is difficult |
| Reduced network overhead for local communication | Shared network port space |
| Closely integrated supporting services | Increased resource consumption |

A sidecar should be placed in the same Pod when it has a genuine lifecycle and communication dependency on the application.

Independent services that require separate scaling or deployment should generally use separate Pods.

## 7. Init Containers

Init containers perform preparation tasks before application containers start.

They execute sequentially.

The next init container starts only after the previous init container completes successfully.

Typical responsibilities include:

- Configuration validation.
- Directory preparation.
- Initial data retrieval.
- Dependency availability checks.
- Permission preparation.

Application containers do not start until all required init containers have completed successfully.

### Init container versus application container

| Attribute | Init container | Application container |
|---|---|---|
| Execution order | Before application containers | After successful initialization |
| Execution behavior | Sequential | Concurrent |
| Main purpose | Preparation | Workload execution |
| Completion | Expected for ordinary init containers | May continue running |
| Restart behavior | Depends on Pod policy and init-container semantics | Depends on Pod policy |

Regular init containers and application containers have different scheduling and execution characteristics.

Native sidecar containers, introduced through Kubernetes restartable init-container semantics, have additional lifecycle behavior and should not be confused with ordinary init containers.

## 8. Resource Requests and Limits

Kubernetes uses resource requests and limits to manage workload placement and resource consumption.

### CPU

CPU is measured in cores or millicores.

- `1000m` represents one CPU core.
- `500m` represents half a CPU core.
- `250m` represents one-quarter of a CPU core.

CPU limits constrain CPU consumption through runtime enforcement.

### Memory

Memory is specified using quantities such as:

- `128Mi`
- `256Mi`
- `512Mi`
- `1Gi`

Memory limits constrain the memory available to a container. Exceeding a memory limit can result in an out-of-memory termination.

### Requests versus limits

| Property | Request | Limit |
|---|---|---|
| Purpose | Scheduling and resource reservation | Maximum permitted consumption |
| CPU | Used for placement and resource accounting | CPU throttling boundary |
| Memory | Used for placement and resource accounting | Memory enforcement boundary |

### Multi-container resource calculation

For ordinary application containers, Pod CPU and memory requests are generally additive.

For ordinary init containers, scheduling must account for the maximum resource requirement of an individual init container rather than summing sequential init-container requests.

For the simplified case implemented in the C++ and Java examples:

\[
CPU_{Pod} =
\max\left(
\sum CPU_{Application},
\max CPU_{Init}
\right)
\]

\[
Memory_{Pod} =
\max\left(
\sum Memory_{Application},
\max Memory_{Init}
\right)
\]

This is a simplified scheduling model. Kubernetes resource accounting can also include Pod overhead, restartable init containers, Pod-level resource settings and other version-dependent features.

## 9. Readiness, Liveness and Startup Probes

Probes allow Kubernetes to evaluate application health.

| Probe | Purpose | Failure behavior |
|---|---|---|
| Readiness | Determines whether the container should receive traffic | Container is marked not ready |
| Liveness | Determines whether the container should be restarted | Container may be restarted |
| Startup | Determines whether the application has completed startup | Other probes are deferred until startup succeeds |

### Readiness

Readiness indicates whether an application can currently handle requests.

A running container can be unready.

Kubernetes uses readiness information to manage traffic eligibility through supporting workload and Service mechanisms.

### Liveness

Liveness detects processes that are running but no longer functioning correctly.

A failed liveness probe can cause the kubelet to restart the affected container.

### Startup

Startup probes support applications with lengthy initialization periods.

They prevent liveness and readiness checks from prematurely interfering with startup.

### Important distinction

A readiness failure does not automatically restart a container.

A liveness failure can trigger a restart.

These mechanisms solve different operational problems.

## 10. Pod Security

Pods require security controls at multiple levels.

### Container security

Recommended controls include:

- Run processes as non-root users where possible.
- Set `allowPrivilegeEscalation: false`.
- Use read-only root filesystems where practical.
- Drop unnecessary Linux capabilities.
- Avoid privileged containers.
- Define CPU and memory limits.
- Use trusted and appropriately pinned images.

### Pod security

Pod-level controls include:

- Dedicated service accounts.
- Least-privilege RBAC.
- Namespace isolation.
- Pod Security Standards.
- NetworkPolicies.
- Appropriate volume permissions.
- Restricted access to host namespaces.
- Controlled secret exposure.

### Identity and credentials

Service account tokens should not be mounted unnecessarily.

Sensitive credentials should be managed through appropriate secret-management mechanisms.

Credentials should not be stored directly in source-controlled manifests or container images.

## 11. Python Implementation

The Python implementation provides an object-oriented Pod simulation.

### Main classes

| Class | Responsibility |
|---|---|
| `ResourceRequirements` | Validates CPU and memory requests |
| `Container` | Models container configuration and runtime state |
| `PodSpec` | Represents the desired Pod configuration |
| `Pod` | Maintains Pod identity, conditions and lifecycle state |
| `Node` | Tracks worker-node resource capacity |
| `PodManager` | Handles creation, scheduling and lifecycle operations |

### Implemented mechanisms

- Container-name and image validation.
- Resource request validation.
- Init-container execution.
- Worker-node scheduling.
- Application-container startup.
- Readiness changes.
- Restart-policy evaluation.
- Liveness-triggered restarts.
- Graceful deletion.
- Resource release.
- Event tracking and JSON reporting.

The implementation uses dictionaries for Pod conditions, lists for container definitions and event histories, and a dictionary keyed by namespace and Pod name for lookup.

The scheduler uses first-fit placement.

For \(P\) Pods and \(N\) worker nodes, scheduling one Pod requires \(O(N + C)\) work, where \(C\) is the number of containers examined for resource accounting.

The simulation is intentionally single-process and does not implement a distributed scheduler.

## 12. JavaScript Implementation

The JavaScript implementation emphasizes event-driven execution and runtime state management.

### Main components

| Component | Responsibility |
|---|---|
| `ResourceRequest` | Immutable resource requests |
| `ContainerDefinition` | Validated container configuration |
| `ContainerRuntime` | Tracks individual container execution |
| `WorkerNode` | Manages node capacity |
| `Pod` | Represents the Pod aggregate and publishes events |
| `PodController` | Coordinates scheduling and lifecycle transitions |

### Event-driven design

The implementation uses Node.js `EventEmitter`.

Pod events include:

- `PodCreated`
- `PodScheduled`
- `InitContainerStarted`
- `InitContainerCompleted`
- `ContainerStarted`
- `ReadinessChanged`
- `ContainerTerminated`
- `ContainerRestarted`
- `DeletionRequested`
- `PodDeleted`

This event model separates lifecycle changes from operational reporting.

The controller also uses a `Map` for Pod lookup and a `Set` for resource-allocation tracking.

Asynchronous deletion demonstrates non-blocking termination behavior.

The grace-period demonstration is deliberately bounded for a short-running simulation. A production controller must honor the configured grace period and integrate with the actual container runtime.

## 13. C++17 Implementation

The C++17 program focuses on domain modeling, resource accounting and explicit lifecycle transitions.

### Main classes and structures

| Type | Responsibility |
|---|---|
| `ResourceRequest` | Represents CPU and memory requirements |
| `Container` | Models container state |
| `PodSpec` | Stores application and init-container definitions |
| `Pod` | Maintains lifecycle and event history |
| `Node` | Controls worker-node capacity |
| `PodScheduler` | Selects nodes and manages allocation |
| `PodLifecycle` | Performs container and Pod transitions |

The implementation uses:

- `std::vector` for container collections.
- `std::map` for labels.
- `std::set` for allocation tracking.
- `std::optional` for optional node assignment.
- `std::shared_ptr` for shared node ownership.
- STL algorithms for lookup and readiness evaluation.

The scheduler calculates resource requirements before node placement.

A node accepts a Pod only when both CPU and memory capacity are sufficient.

The release operation reverses the allocation to prevent resource-accounting leaks.

Assertions verify expected behavior during the production and batch workload scenarios.

## 14. Java 17 Implementation

The Java implementation provides an enterprise-oriented domain model with explicit service boundaries.

### Domain model

| Type | Responsibility |
|---|---|
| `PodMetadata` | Immutable Pod metadata |
| `PodSpec` | Immutable desired configuration |
| `ContainerDefinition` | Validated container specification |
| `ContainerRuntime` | Mutable container execution state |
| `PodAggregate` | Pod identity and lifecycle aggregate |
| `WorkerNode` | Resource capacity and allocation |
| `SchedulingStrategy` | Node selection contract |
| `FirstFitScheduler` | Scheduling policy implementation |
| `PodSchedulingService` | Resource placement and release |
| `PodLifecycleService` | Initialization, readiness and termination |

Java records represent immutable configuration.

The `SchedulingStrategy` interface separates placement policy from scheduling execution.

Custom exceptions distinguish resource and lifecycle failures.

The implementation demonstrates:

- Immutable metadata.
- Defensive collection copying.
- Unique container names.
- Explicit state transitions.
- Sequential init-container execution.
- Application readiness evaluation.
- Restart-policy behavior.
- Liveness-triggered restart.
- Node resource release.

This separation is suitable for extending the model with additional scheduling strategies, admission policies and observability services.

## 15. PostgreSQL Data Model

The PostgreSQL implementation models the Pod lifecycle as a relational workflow.

### Entity relationships

    Clusters
       |
       +-- Namespaces
              |
              +-- Service Accounts
              |
              +-- Pods
                    |
                    +-- Containers
                    |     |
                    |     +-- Container Ports
                    |     |
                    |     +-- Container Probes
                    |
                    +-- Pod Volumes
                    |     |
                    |     +-- Volume Mounts
                    |
                    +-- Pod Conditions
                    |
                    +-- Pod Events
                    |
                    +-- Resource Allocations
                              |
                              +-- Worker Nodes

### Principal tables

| Table | Purpose |
|---|---|
| `clusters` | Cluster identification |
| `namespaces` | Namespace isolation |
| `worker_nodes` | Worker capacity and allocated resources |
| `service_accounts` | Workload identities |
| `pods` | Pod specification and lifecycle phase |
| `containers` | Container configuration and runtime state |
| `pod_volumes` | Pod-level storage definitions |
| `volume_mounts` | Container-to-volume relationships |
| `container_ports` | Network port configuration |
| `pod_conditions` | Readiness and scheduling conditions |
| `pod_events` | Lifecycle event history |
| `container_probes` | Health-check configuration |
| `resource_allocations` | Resource reservation and release history |

### Database integrity

Primary keys provide entity identity.

Foreign keys maintain relationships between Pods, namespaces, containers and worker nodes.

Unique constraints prevent duplicate Pod names within a namespace and duplicate container names within a Pod.

Check constraints validate:

- Positive resource requests.
- Valid container ports.
- Valid restart counts.
- Valid termination periods.
- Valid JSON structures.
- Consistent CPU and memory limits.

Partial indexes support active resource-allocation lookup.

GIN indexing supports JSONB label searches.

### Database functions

| Function | Purpose |
|---|---|
| `record_pod_event` | Records lifecycle events |
| `calculate_pod_readiness` | Determines Pod readiness from container states |
| `schedule_pod` | Allocates a worker node |
| `complete_init_container` | Records init-container completion |
| `start_pod` | Starts application containers |
| `update_container_readiness` | Updates readiness state |
| `terminate_container` | Applies restart-policy behavior |
| `release_pod_resources` | Reverses resource reservations |
| `terminate_pod` | Performs Pod termination |

### Transaction handling

The scheduling function locks the Pod and selected worker node before changing resource allocations.

This protects the resource-accounting workflow against concurrent scheduling attempts.

Allocation history is retained through `resource_allocations`.

The `released_at` timestamp distinguishes active reservations from released allocations.

A partial unique index ensures that a Pod cannot have multiple active allocation records.

## 16. Important Kubernetes Distinctions

| Concept | Meaning |
|---|---|
| Pod | Smallest Kubernetes deployable workload unit |
| Container | Individual execution environment |
| Pod manifest | Declarative desired configuration |
| Pod phase | Broad lifecycle classification |
| Pod condition | Specific operational status |
| Container state | Individual runtime execution state |
| Readiness | Ability to receive workload traffic |
| Liveness | Process health used for restart decisions |
| Init container | Preparation workload executed before application containers |
| Sidecar | Supporting container with a related lifecycle |
| Restart policy | Rule governing container restarts |
| Resource request | Resource quantity used for scheduling |
| Resource limit | Maximum permitted resource consumption |

These concepts are related but are not interchangeable.

A Pod is not the same as a container. Running is not the same as Ready. A readiness failure is not the same as a liveness failure. A Pod restart policy is not an independent Deployment rollout strategy.

## 17. Production Limitations and Design Considerations

The implementations are educational lifecycle and scheduling simulations. They are not replacements for the Kubernetes control plane or container runtime.

Important differences include:

1. The Python, JavaScript, C++ and Java implementations use simplified lifecycle transitions rather than the complete Kubernetes state machine.
2. Scheduling uses simplified resource calculations and first-fit placement.
3. Actual Kubernetes scheduling includes node selectors, affinity, taints, tolerations, topology constraints, volume requirements and admission decisions.
4. Actual Kubernetes container restarts include backoff behavior.
5. The examples do not implement distributed control-plane coordination.
6. The SQL model represents operational state relationally but does not implement the Kubernetes API or kubelet.
7. The SQL resource accounting uses simplified ordinary init-container semantics. Restartable init-container sidecars and Pod overhead require additional accounting.
8. The SQL termination function simulates termination rather than implementing an actual timed graceful-shutdown process.
9. Kubernetes readiness and liveness probes are executed by the kubelet, not by the database.
10. Real production deployments require security policies, observability, access control and durable storage decisions.

A standalone Pod is appropriate for limited workloads and testing. Production application workloads commonly use controllers that provide replica management, replacement, rollout and recovery behavior.
