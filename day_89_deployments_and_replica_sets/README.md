# Deployments and ReplicaSets

## 1. Deployment Architecture

A Deployment is a declarative Kubernetes workload resource that manages application updates and maintains the desired number of application replicas.

A ReplicaSet maintains a stable set of matching Pods. A Deployment manages ReplicaSets to provide controlled updates, revision history, and rollback capabilities.

The implementation models the operational relationship:

Repository of desired configuration
    |
    v
Deployment specification
    |
    v
Deployment controller
    |
    +-----------------------+
    |                       |
    v                       v
Current ReplicaSet     Previous ReplicaSets
    |                       |
    v                       v
New application Pods   Existing application Pods
    |                       |
    +-----------+-----------+
                |
                v
       Observed workload state
                |
                v
       Reconciliation process
                |
                v
       Desired state maintained

The five implementations provide complementary models of this architecture using Python, JavaScript, C++17, Java 17, and PostgreSQL.

These programs are standalone simulations. They model deployment-controller behavior without connecting to a Kubernetes cluster.

## 2. Deployment

A Deployment describes the desired application state.

Its principal configuration includes:

| Field | Meaning |
|---|---|
| Name | Unique workload name within a namespace |
| Namespace | Logical workload isolation |
| Replicas | Desired number of application Pods |
| Container image | Application image reference |
| Container port | Application container port |
| Strategy | Method used to update application versions |
| Max surge | Maximum temporary additional Pods |
| Max unavailable | Maximum permitted unavailable Pods |
| Revision history limit | Number of historical revisions retained |

Example specification:

| Property | Value |
|---|---|
| Deployment | inventory-api |
| Namespace | production |
| Image | registry.example.com/inventory:v1 |
| Replicas | 3 |
| Max surge | 1 |
| Max unavailable | 0 |

The specification represents desired state rather than a direct description of running containers.

A Deployment can request three replicas even when only two Pods are currently ready.

This difference is fundamental to declarative orchestration.

### Declarative configuration

Declarative management specifies the required outcome.

The controller determines which operations are necessary to reach that outcome.

For example:

- Desired replicas: 3
- Observed replicas: 2
- Ready replicas: 2

The controller identifies one missing replica and creates another Pod through the current ReplicaSet.

It does not require an administrator to manually issue a separate Pod creation command every time the observed state changes.

## 3. ReplicaSets

A ReplicaSet maintains the desired number of matching Pods.

Its principal responsibilities are:

- Maintaining the required replica count.
- Creating Pods when replicas are missing.
- Replacing failed Pods.
- Removing excess Pods.
- Managing Pods associated with its selector.

A Deployment creates and manages ReplicaSets during application version changes.

Each ReplicaSet represents a particular application revision.

### Relationship between Deployment and ReplicaSet

| Resource | Responsibility |
|---|---|
| Deployment | Application rollout and revision management |
| ReplicaSet | Replica maintenance |
| Pod | Running application workload |
| Container | Application execution environment |

A Deployment does not directly perform all Pod lifecycle operations independently. It coordinates ReplicaSets, which maintain the application Pods.

### Multiple ReplicaSets

Consider three application revisions:

| Revision | Image | Desired replicas |
|---|---|---:|
| 1 | inventory:v1 | 3 |
| 2 | inventory:v2 | 3 |
| 3 | inventory:v3 | 3 |

During a rolling update, the latest ReplicaSet receives new Pods while previous ReplicaSets gradually lose Pods.

Historical ReplicaSets can remain available with zero active replicas.

This provides the revision information required for rollback.

## 4. Reconciliation

Reconciliation is the process of comparing desired state with observed state and taking corrective action.

The controller repeatedly evaluates:

- Desired replica count.
- Active replica count.
- Ready replica count.
- Current ReplicaSet.
- Historical ReplicaSets.
- Deployment pause state.
- Rollout constraints.

A simplified reconciliation sequence is:

1. Read the Deployment specification.
2. Identify the newest ReplicaSet.
3. Calculate current active replicas.
4. Calculate the permitted surge capacity.
5. Create missing Pods when capacity permits.
6. Remove eligible Pods from older ReplicaSets.
7. Evaluate workload availability.
8. Record relevant state changes.

### Desired and observed state

| Metric | Meaning |
|---|---|
| Desired replicas | Number requested by the Deployment |
| Active replicas | Pods in pending, running, or ready states |
| Ready replicas | Pods that have passed readiness checks |
| Failed replicas | Pods that have entered a failed state |

These metrics must not be treated as interchangeable.

A pending Pod contributes to active replicas but does not contribute to ready replicas.

A failed Pod is not a healthy replacement for an unavailable application replica.

### Reconciliation example

Desired replicas: 3

| ReplicaSet | Revision | Active | Ready |
|---|---:|---:|---:|
| inventory:v1 | 1 | 2 | 2 |
| inventory:v2 | 2 | 1 | 1 |

The controller observes three active Pods and three ready Pods.

If revision 2 is current, the controller can continue reducing revision 1 while preserving the configured availability requirement.

## 5. Pod Lifecycle

The implementations model these Pod states:

| State | Meaning |
|---|---|
| Pending | Pod has been accepted but is not ready |
| Running | Containers are executing |
| Ready | Readiness conditions have been satisfied |
| Failed | Pod execution has failed |
| Terminating | Pod is being removed |

A typical successful lifecycle is:

Pending
   |
   v
Running
   |
   v
Ready
   |
   v
Terminating

Failure can occur during scheduling, image retrieval, container startup, or application execution.

A readiness failure does not necessarily mean that the container has stopped running. Readiness and execution health are separate concepts.

The simulations simplify Pod readiness by allowing a controller operation to mark pending Pods ready.

A real Kubernetes environment uses scheduling, container runtime operations, startup probes, readiness probes, and liveness probes.

## 6. Rolling Updates

A rolling update replaces Pods from an older application revision with Pods from a newer revision gradually.

It is the default Deployment update strategy in Kubernetes.

The process avoids replacing every application Pod simultaneously.

### Rolling update workflow

Initial state:

| ReplicaSet | Image | Active | Ready |
|---|---|---:|---:|
| Revision 1 | payment:v1 | 3 | 3 |

New desired state:

| ReplicaSet | Image | Active | Ready |
|---|---|---:|---:|
| Revision 1 | payment:v1 | 3 | 3 |
| Revision 2 | payment:v2 | 0 | 0 |

The controller creates new Pods under revision 2, waits for their readiness, and gradually reduces revision 1.

Final state:

| ReplicaSet | Image | Active | Ready |
|---|---|---:|---:|
| Revision 1 | payment:v1 | 0 | 0 |
| Revision 2 | payment:v2 | 3 | 3 |

The older ReplicaSet can remain available for historical revision management.

### Max surge

`maxSurge` specifies the maximum number of Pods that can temporarily exist above the desired replica count during a rolling update.

For three desired replicas and a maximum surge of one:

Maximum active replicas = 3 + 1 = 4

The controller can create a new Pod before removing an older Pod.

### Max unavailable

`maxUnavailable` specifies the maximum number of desired Pods that can be unavailable during an update.

For three desired replicas and a maximum unavailable value of zero:

Minimum available replicas = 3 - 0 = 3

The update must preserve all three available replicas according to the configured rollout policy.

The values of maxSurge and maxUnavailable influence rollout speed and application availability.

| Configuration | Operational implication |
|---|---|
| High maxSurge | More temporary capacity is required |
| Low maxSurge | Fewer additional Pods can be created simultaneously |
| High maxUnavailable | Faster replacement may be possible |
| Zero maxUnavailable | Existing availability must be preserved |

Kubernetes also supports percentage-based values for these parameters. The simulations use integer values.

### Important distinction

A rolling update is not an instantaneous image replacement.

It is a sequence of ReplicaSet and Pod state changes controlled by availability and capacity constraints.

## 7. Rollback and Revision History

A rollback restores an earlier application configuration.

Suppose the deployment history is:

| Revision | Image |
|---|---|
| 1 | payment:v1 |
| 2 | payment:v2 |
| 3 | payment:v3 |

If revision 3 introduces an application failure, revision 2 can be selected as the rollback target.

The resulting state uses payment:v2.

A rollback does not erase revision 3 or reverse historical records.

It creates a new revision using the selected older configuration.

For example:

| New revision | Image |
|---|---|
| 4 | payment:v2 |

This distinction preserves an auditable sequence of deployment operations.

### Rollback limitations

Rollback does not automatically reverse:

- Database schema changes.
- External service changes.
- Persistent volume modifications.
- Message format changes.
- Configuration changes outside the Deployment.
- Irreversible application data operations.

An application rollback must therefore be compatible with the current external system state.

The implementations retain a bounded revision history. In production, Kubernetes also applies revision-history retention rules.

## 8. Deployment Pause and Resume

A Deployment can be paused to stop processing further rollout changes temporarily.

Pausing is useful when multiple related changes must be applied before a rollout proceeds.

The simulated controller maintains a pause flag.

| Operation | Result |
|---|---|
| Pause | Stops further reconciliation in the simulation |
| Resume | Re-enables reconciliation |
| Update while paused | Requires additional handling before rollout proceeds |

A paused Deployment is not equivalent to a stopped application.

Existing Pods can continue running.

The Python, JavaScript, C++, and Java implementations model the pause state explicitly.

## 9. Deployment Status

The implementations model four principal Deployment conditions.

| Phase | Interpretation |
|---|---|
| Progressing | Desired state has not yet been reached |
| Available | Required replica availability has been reached |
| Degraded | An operational failure or rollout limit has prevented progress |
| Paused | Deployment rollout processing is suspended |

These are simplified application-level states.

Kubernetes exposes Deployment conditions such as `Progressing`, `Available`, and `ReplicaFailure`, with condition status and reasons.

The simplified `Degraded` and `Paused` labels in these programs should not be interpreted as identical Kubernetes API condition types.

## 10. Python Implementation

File: `deployment_controller.py`

The Python implementation emphasizes declarative modeling and explicit reconciliation.

### Domain classes

| Class | Responsibility |
|---|---|
| ContainerSpec | Container image and execution settings |
| DeploymentSpec | Validated desired workload state |
| Pod | Individual application instance |
| ReplicaSet | Version-specific Pod collection |
| Deployment | Workload and revision state |
| DeploymentController | Reconciliation and rollout management |

### Important mechanisms

**Dataclasses**

The implementation uses dataclasses to represent workload resources and maintain readable state structures.

**Enums**

Deployment and Pod states are represented using enumerations.

This prevents inconsistent string-based state comparisons.

**Validation**

Deployment names, namespaces, image references, replica counts, ports, and rollout parameters are validated before operations are accepted.

**Dictionary-based state**

The controller uses dictionaries for deployment and ReplicaSet lookup.

This provides approximately constant-time average lookup by identifier.

**Reconciliation**

The `reconcile()` method calculates the permitted scale-up and scale-down operations.

**Failure simulation**

The controller can mark Pods as failed and simulate image startup failures.

Failed Pods are removed from the active simulation state so that reconciliation can replace them.

**Assertions**

The test routine checks initial deployment, rolling updates, rollback, scaling, and invalid input handling.

### Execution

Requires Python 3.10 or later.

Run the file directly.

The program prints the initial state, rolling update, rollback, and test results.

## 11. JavaScript Implementation

File: `deployment_controller.js`

The JavaScript implementation emphasizes event-driven state management.

### Engineering characteristics

- `EventEmitter` broadcasts deployment lifecycle events.
- `Map` stores Deployments, ReplicaSets, and Pods.
- `Set` supports image policy evaluation.
- `Promise`-based service operations provide an asynchronous workflow interface.
- UUID identifiers distinguish independently created resources.
- Explicit transition rules reject invalid Pod state changes.

### Event-driven architecture

Deployment operation
       |
       v
Controller
       |
       v
State reconciliation
       |
       v
Audit event
       |
       v
Event listeners

The controller emits events such as:

- `DEPLOYMENT_CREATED`
- `REVISION_CREATED`
- `SCALE_UP`
- `POD_READY`
- `POD_START_FAILED`
- `ROLLOUT_COMPLETED`
- `ROLLBACK_STARTED`

The `RolloutPolicy` class separately checks the approved image registry and maximum replica count.

This separates deployment execution from deployment authorization.

### Execution

Requires Node.js 18 or later.

Run the JavaScript file using Node.js.

The test routine checks rollout, rollback, scaling, policy validation, and pause/resume operations.

## 12. C++17 Implementation

File: `deployment_controller.cpp`

The C++ implementation focuses on resource ownership, deterministic state management, and explicit reconciliation algorithms.

### Domain structures

| Type | Responsibility |
|---|---|
| ContainerSpec | Container configuration |
| DeploymentSpec | Desired workload state |
| Pod | Individual workload instance |
| ReplicaSet | Revision-specific replica collection |
| DeploymentController | Resource lifecycle and reconciliation |

### STL usage

The implementation uses:

- `std::map` for deterministic resource lookup.
- `std::vector` for revision history.
- `std::set` for simulated image failure conditions.
- `std::optional` for optional rollback revisions.
- `std::all_of` and `std::max_element` for validation and revision selection.

### Reconciliation characteristics

The controller calculates:

- Total active replicas.
- Ready replicas.
- Missing replicas.
- Surge capacity.
- Minimum available replicas.

The scale-up amount is bounded by both the missing replica count and the available surge capacity.

The controller then evaluates older ReplicaSets and removes eligible Pods.

### Complexity

Let:

- R represent the number of ReplicaSets.
- P represent the total number of Pods.
- H represent retained revision history.

The main reporting and aggregation operations are approximately O(R + P).

Ordered map insertion and lookup have O(log n) complexity.

Revision history management is O(H) in the vector-based implementation.

The program prioritizes explicit domain behavior over distributed scheduling functionality.

### Compilation

Requires a C++17-compatible compiler.

Compile with the C++17 language standard and run the resulting executable.

## 13. Java 17 Implementation

File: `DeploymentManager.java`

The Java implementation emphasizes enterprise domain modeling and separation of concerns.

### Architecture

| Component | Responsibility |
|---|---|
| ContainerSpec record | Immutable container configuration |
| DeploymentSpec record | Immutable desired state |
| Pod | Pod lifecycle |
| ReplicaSet | Replica management |
| Deployment | Deployment aggregate |
| DeploymentPolicy | Policy contract |
| ProductionPolicy | Registry and replica restrictions |
| DeploymentService | Application lifecycle operations |

### Immutable specifications

Java records represent configuration objects.

A modified specification is created as a new record rather than directly mutating individual configuration fields.

This reduces accidental configuration changes.

### Policy evaluation

The `DeploymentPolicy` interface separates policy enforcement from deployment operations.

`ProductionPolicy` evaluates:

- Maximum replica limits.
- Approved container registries.

The service rejects noncompliant specifications before updating deployment state.

### State transitions

The Pod class defines permitted lifecycle transitions.

An invalid transition throws a deployment exception.

For example, a failed Pod cannot transition directly to Ready.

### Enterprise considerations

The service records audit events for important operations.

Custom exceptions distinguish invalid configuration from deployment execution errors.

The implementation uses Java collections and streams for revision selection, replica counting, and reporting.

### Execution

Requires Java 17.

Compile and run the `DeploymentManager` class.

## 14. PostgreSQL Implementation

File: `deployments.sql`

The PostgreSQL implementation models deployment state as relational data.

It separates resource definitions, workload instances, historical revisions, and operational events.

### Database schema

| Table | Purpose |
|---|---|
| namespaces | Logical workload isolation |
| container_images | Container image inventory |
| image_security_scans | Image security assessment |
| deployments | Desired application configuration |
| replica_sets | Version-specific replica groups |
| pods | Individual workload instances |
| deployment_revisions | Historical configuration |
| rollout_operations | Update and rollback operations |
| deployment_events | Operational audit history |

### Referential integrity

Foreign keys enforce relationships between:

- Deployments and namespaces.
- Deployments and container images.
- ReplicaSets and Deployments.
- Pods and ReplicaSets.
- Revisions and images.
- Rollout operations and Deployments.

Unique constraints prevent duplicate namespace names, Deployment names within a namespace, and revision numbers within a Deployment.

Check constraints validate replica counts, ports, image fields, and operation states.

### Database functions

| Function | Purpose |
|---|---|
| active_replica_count | Counts active Pods in a ReplicaSet |
| ready_replica_count | Counts ready Pods in a ReplicaSet |
| deployment_ready_count | Counts ready Pods across a Deployment |
| deployment_active_count | Counts active Pods across a Deployment |
| create_deployment_revision | Creates a new revision and ReplicaSet |
| deployment_eligibility | Evaluates replica availability |

### Stored procedures

The SQL script provides procedures for:

- Deployment creation.
- Pod creation.
- Pod readiness updates.
- Replica scaling.
- Rolling update initiation.
- Revision-based rollback.

The procedures use database transactions and row locking where concurrent modification could otherwise create inconsistent state.

### Triggers

The deployment audit trigger records changes to Deployment specifications and updates modification timestamps.

The trigger uses JSONB to retain selected before-and-after values.

### Views

`deployment_status_report` provides workload-level replica information and an evaluated phase.

`replica_set_report` provides revision-level replica information.

These views separate reporting queries from the underlying relational operations.

### Indexing

Indexes support common operational queries:

- Deployment lookup by namespace and phase.
- ReplicaSet lookup by Deployment and revision.
- Pod lookup by ReplicaSet and phase.
- Ready-Pod lookup.
- Revision history retrieval.
- Recent event retrieval.

The partial index on ready Pods targets an important operational query.

### Transaction safety

The SQL script demonstrates transactional deployment operations and a savepoint-based validation failure.

A database transaction protects the database changes made by its SQL statements.

It does not automatically make external container scheduling or Kubernetes API operations atomic.

## 15. Kubernetes Rolling Update Semantics

The simulations illustrate the central behavior of rolling updates, but actual Kubernetes deployments have additional API-level semantics.

### RollingUpdate

The `RollingUpdate` strategy gradually scales new and old ReplicaSets.

Its configuration uses:

- `maxSurge`
- `maxUnavailable`

These values control rollout capacity and availability.

### Recreate

The `Recreate` strategy terminates existing Pods before creating new Pods.

This can cause downtime.

It is appropriate only when simultaneous application versions are not supported or when the workload requires a replacement strategy.

The PostgreSQL schema includes both strategy values.

The executable simulations primarily implement rolling-update behavior.

### Readiness probes

A readiness probe determines whether a container is ready to receive traffic.

A running container that fails readiness checks should not be counted as an available application replica.

The simulations model readiness as an explicit state transition rather than implementing actual HTTP or TCP probes.

### Liveness probes

A liveness probe determines whether a container should be restarted.

It is distinct from readiness.

A container can be alive but not ready to serve traffic.

### Startup probes

Startup probes allow applications with longer initialization times to complete startup before regular liveness and readiness checks take effect.

The simulations do not implement probe timing.

## 16. Deployment Failure Scenarios

| Failure | Effect | Operational response |
|---|---|---|
| Invalid image reference | Deployment validation fails | Correct the image reference |
| Unapproved registry | Policy rejects the specification | Use an approved image source |
| Image pull failure | Pod cannot start | Verify registry access and image availability |
| Container startup failure | Pod fails before readiness | Inspect container startup logs |
| Readiness failure | Pod does not become available | Inspect application dependencies and readiness conditions |
| Insufficient cluster capacity | New Pods remain pending | Inspect node resources and scheduling constraints |
| Excessive maxSurge | Temporary resource pressure | Review surge configuration |
| Rollout timeout | Desired revision is not reached | Inspect rollout conditions and failed Pods |
| Incompatible database migration | Application rollback may fail | Use backward-compatible migration procedures |
| Revision unavailable | Requested rollback cannot be performed | Inspect retained revision history |

The examples implement selected failure cases, including invalid specifications, failed images, missing revisions, and policy violations.

## 17. Security and Reliability

Deployment configuration is part of the application security boundary.

Important production controls include:

### Image integrity

Use immutable image digests where reproducible deployment identity is required.

A mutable image tag can point to different image content over time.

### Image provenance

Validate image signatures and provenance before allowing production deployment.

### Registry restrictions

Restrict permitted image registries and repositories.

The JavaScript and Java policy implementations demonstrate registry allowlisting.

### Image vulnerability scanning

The PostgreSQL model includes security scan records and approval status.

Production policies should define how critical vulnerabilities, scan freshness, and exceptions affect deployment eligibility.

### Least privilege

Deployment controllers should receive only the Kubernetes permissions required to manage their resources.

Avoid granting unrestricted cluster-administrator privileges.

### Resource limits

Configure CPU and memory requests and limits to reduce resource contention and improve scheduling predictability.

### Availability

Use appropriate replica counts, readiness probes, disruption budgets, and scheduling policies.

A Deployment's replica count alone does not guarantee high availability across nodes or availability zones.

### Auditability

Retain revision history and operational events.

Record who initiated deployment changes and whether an operation was approved.

## 18. Performance Considerations

Deployment controllers must reconcile frequently without creating unnecessary workload changes.

Important considerations include:

- Efficient resource lookup.
- Bounded reconciliation work.
- Appropriate revision-history retention.
- Indexed database queries.
- Event retention and archival.
- Controlled rollout concurrency.
- Readiness-based scaling decisions.
- Cluster resource capacity.

The simulations use in-memory data structures and synchronous reconciliation passes.

A production controller requires distributed coordination, persistent state, retry handling, and protection against concurrent updates.

## 19. Implementation Comparison

| Capability | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Desired state | Yes | Yes | Yes | Yes | Yes |
| ReplicaSets | Yes | Yes | Yes | Yes | Yes |
| Pod lifecycle | Yes | Yes | Yes | Yes | Yes |
| Reconciliation | Yes | Yes | Yes | Yes | Procedure |
| Rolling update | Yes | Yes | Yes | Yes | Initiation procedure |
| Rollback | Yes | Yes | Yes | Yes | Yes |
| Scaling | Yes | Yes | Yes | Yes | Yes |
| Pause/resume | Yes | Yes | Yes | Yes | Schema support |
| Event recording | Yes | Yes | Console | Yes | Audit table |
| Policy evaluation | Validation | Dedicated policy | Validation | Policy interface | Image approval |
| Persistent storage | Optional JSON export | No | No | No | Yes |

## 20. Limitations of the Simulations

These implementations are educational deployment-management models, not replacements for Kubernetes.

They do not implement:

- Kubernetes API communication.
- Real container creation.
- Container runtime integration.
- Node scheduling.
- Service discovery.
- Ingress configuration.
- Persistent volumes.
- Horizontal Pod Autoscaling.
- Network policies.
- Actual readiness, liveness, and startup probes.
- Distributed controller leader election.
- Kubernetes watch streams.
- Full Kubernetes strategic merge or server-side apply behavior.
- Complete Kubernetes garbage collection and owner-reference semantics.

The Python, JavaScript, C++, and Java implementations simulate reconciliation in memory.

The PostgreSQL implementation models persistent workload records and database-level operations. Its stored procedures do not execute real Kubernetes scheduling.

A production implementation must coordinate the database or controller state with the Kubernetes API rather than treating relational transactions as atomic across external infrastructure.

## 21. Technical Terminology

| Term | Definition |
|---|---|
| Declarative management | Specifying the desired state of a system |
| Desired state | Configuration the workload should maintain |
| Observed state | Actual state reported by the system |
| Reconciliation | Correcting differences between desired and observed states |
| Deployment | Kubernetes resource managing application rollouts |
| ReplicaSet | Kubernetes resource maintaining a set of matching Pods |
| Pod | Smallest deployable Kubernetes workload unit |
| Revision | Recorded version of a Deployment configuration |
| Rolling update | Gradual replacement of application replicas |
| Max surge | Maximum temporary replicas above the desired count |
| Max unavailable | Maximum unavailable desired replicas during rollout |
| Rollback | Deployment of an earlier application configuration |
| Readiness | Whether a workload instance can receive traffic |
| Liveness | Whether a container is considered alive |
| Startup probe | Probe controlling application startup evaluation |
| Recreate | Strategy replacing old Pods before creating new ones |
| Image digest | Content-addressed identifier for a container image |
| Generation | Version of a Kubernetes resource specification |
| Controller | Component that continuously reconciles resource state |

## 22. Practical Execution Matrix

| File | Runtime | Dependencies |
|---|---|---|
| deployment_controller.py | Python 3.10+ | Standard library |
| deployment_controller.js | Node.js 18+ | Standard library |
| deployment_controller.cpp | C++17 | Standard library |
| DeploymentManager.java | Java 17 | Standard library |
| deployments.sql | PostgreSQL 15+ | PostgreSQL |

All five source implementations can be executed independently.

The shared domain model makes it possible to compare declarative workload management, resource reconciliation, replica maintenance, rolling updates, and revision-based recovery across different programming and data-management environments.
