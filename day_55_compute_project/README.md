# Compute and Storage Project

## Scope

This project models the deployment of a scalable application using compute capacity, persistent object storage, load balancing, horizontal scaling, health monitoring, backups, and recovery.

The five implementations use the same infrastructure concepts while emphasizing different engineering perspectives:

| Implementation | Primary perspective |
|---|---|
| Python | Repository-style platform simulation with dataclasses, validation, scaling, storage, and backup recovery |
| JavaScript | Event-driven infrastructure model using `EventEmitter`, asynchronous request handling, `Map`, and `Set`-compatible collection patterns |
| C++17 | Resource-governance and capacity engine using STL containers, explicit state, and deployment eligibility evaluation |
| Java 17 | Enterprise domain model using records, interfaces, immutable results, policy objects, services, and explicit validation |
| PostgreSQL | Relational infrastructure model with constraints, indexes, triggers, views, CTEs, transactions, and merge-eligibility evaluation |

The central relationship is:

`Application → Compute Instances → Load Balancer → Storage → Backups → Health State → Scaling → Deployment Eligibility`

The project separates application traffic management from persistent data management and from deployment governance.

---

## Architecture

A scalable deployment has several distinct responsibilities.

                    ┌──────────────────────┐
                    │      Application     │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │    Load Balancer     │
                    └──────────┬───────────┘
                               │
                 ┌─────────────┼─────────────┐
                 ▼             ▼             ▼
            ┌────────┐   ┌────────┐   ┌────────┐
            │ App-01 │   │ App-02 │   │ App-03 │
            └────────┘   └────────┘   └────────┘
                 │             │             │
                 └─────────────┼─────────────┘
                               │
                    ┌──────────▼───────────┐
                    │   Object Storage     │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │ Backup / Recovery    │
                    └──────────────────────┘

                    Health + Capacity
                           │
                           ▼
                    ┌───────────────┐
                    │ Auto Scaling  │
                    └───────────────┘

Compute handles active application requests.

The load balancer distributes requests across healthy compute instances.

Object storage maintains application data independently from the lifetime of a compute instance.

Backups provide recovery from accidental deletion, corruption, or infrastructure failure.

Health checks determine whether an instance should continue receiving traffic.

Scaling changes compute capacity when demand changes.

Deployment governance evaluates whether the platform satisfies required operational conditions.

---

## Compute Capacity

A compute instance is represented by a capacity and an active-request count.

For an instance:

`utilization = active_requests / capacity`

An instance can accept traffic only when:

- its state is `running`
- its active request count is below its capacity

The implementations deliberately prevent active requests from exceeding declared capacity.

This makes capacity exhaustion an explicit failure condition rather than an invisible implementation detail.

For example, two instances with capacity `100` each provide:

`2 × 100 = 200 requests`

of modeled concurrent capacity.

Adding a third instance changes the theoretical capacity to:

`3 × 100 = 300 requests`

This is horizontal scaling because capacity is increased by adding instances rather than by increasing the resources of one existing instance.

---

## Load Balancing

The load-balancing implementations select healthy instances with available capacity.

The Python, JavaScript, and Java implementations use a least-utilized selection strategy. The C++ implementation performs the same decision through STL algorithms.

The selection process is:

Receive request  
↓  
Find healthy instances  
↓  
Discard instances at capacity  
↓  
Select least-utilized instance  
↓  
Increment active request count  
↓  
Process request

This is a simplified model of a production load balancer.

A production system may use additional mechanisms such as:

- connection draining
- weighted routing
- geographic routing
- session affinity
- latency-aware routing
- health-check thresholds
- circuit breaking
- retry policies

The project focuses on capacity-aware routing so that the relationship between compute capacity and traffic distribution remains explicit.

---

## Health Management

An unhealthy instance should not receive new application traffic.

The model distinguishes `running`, `unhealthy`, and `stopped` states.

An important operational rule is that an instance with active requests cannot be immediately removed from service in the application simulations.

This models connection draining:

Running  
↓ Failure detected  
Drain active requests  
↓  
Unhealthy  
↓  
Replace instance  
↓  
Running

Removing an instance with active work can cause incomplete requests or data inconsistency.

The PostgreSQL model records health checks independently, allowing historical health measurements to be queried rather than storing only the latest state.

---

## Horizontal Scaling

The Python and JavaScript implementations contain an explicit autoscaling policy.

The policy uses aggregate utilization thresholds.

A simplified policy is:

| Condition | Decision |
|---|---|
| Utilization ≥ scale-up threshold | Add an instance if the maximum has not been reached |
| Utilization ≤ scale-down threshold | Remove an idle instance if the minimum has not been reached |
| Otherwise | Keep the current fleet |

The project uses both a minimum and maximum instance count.

This prevents two important failure modes:

1. Scaling down until the application has no redundancy.
2. Scaling up without an upper bound during abnormal traffic.

For example, `min_instances = 2` and `max_instances = 6` means the platform normally maintains at least two instances and cannot automatically exceed six instances.

Real autoscaling systems normally use time windows, cooldown periods, warm-up time, queue depth, CPU utilization, memory pressure, request latency, or multiple metrics rather than a single instantaneous utilization value.

---

## Object Storage

Object storage is intentionally separated from compute.

A stored object contains:

- object key
- content
- size
- checksum
- creation timestamp

A key identifies the object logically.

Examples include:

- `releases/v1/config.json`
- `releases/v1/index.html`

The Python, JavaScript, and Java implementations verify stored content using checksums.

The checksum allows the application to detect unexpected modification or corruption.

The Java implementation uses SHA-256 through the standard Java security library.

The JavaScript implementation uses Node.js `crypto`.

The Python implementation uses the standard-library `hashlib` module.

The C++ implementation remains dependency-free and uses a standard-library hash for its self-contained demonstration. A production C++ storage implementation should use a dedicated cryptographic hashing library when cryptographic integrity guarantees are required.

---

## Storage Validation

The storage layer rejects invalid object operations.

Examples include:

- empty object keys
- absolute object keys
- objects larger than the configured size limit
- retrieval of missing objects
- deletion of missing objects
- checksum mismatches

These checks make storage failures explicit.

The storage model also treats data integrity separately from availability. An object can exist while still failing integrity verification.

---

## Backups

A backup is modeled as a point-in-time snapshot of stored objects.

Storage Objects  
↓ Snapshot  
Backup  
↓ Restore  
Storage Objects

The backup system stores:

- backup identifier
- creation time
- backup state
- object snapshot
- retention information where applicable

The sample workflow creates a backup, deletes an object, and restores the backup.

This demonstrates why backups are different from ordinary storage replication.

Replication generally helps maintain availability of current data.

Backups provide historical recovery points.

A resilient production system often requires both.

---

## Backup Retention

The Python, JavaScript, and PostgreSQL models include retention concepts.

A retention policy prevents indefinite accumulation of backup data.

The PostgreSQL implementation represents expiration through `expires_at`.

A backup is considered currently valid when:

- its state is `available`
- its expiration time is in the future
- it satisfies the configured maximum backup age

Retention policies should be designed around recovery objectives.

Two important operational concepts are:

| Concept | Meaning |
|---|---|
| RPO | Maximum acceptable amount of data loss measured in time |
| RTO | Maximum acceptable time required to restore service |

The project does not claim that a backup alone provides a specific RPO or RTO. Those values depend on backup frequency, storage durability, restore speed, infrastructure capacity, and operational procedures.

---

## Deployment Governance

The project also models deployment eligibility.

A deployment can be considered operationally unsafe even when the application code itself is valid.

The governance model checks conditions such as:

- sufficient healthy compute instances
- sufficient total healthy capacity
- availability of a current backup
- valid storage state

This produces a clear separation:

Application change  
↓  
Build and test  
↓  
Deployment policy  
↓  
- Capacity sufficient?
- Instances healthy?
- Backup available?
- Other operational checks?
↓  
Deployment eligible

This is distinct from merely checking whether an application can start.

---

## Python Implementation

The Python implementation uses dataclasses to model infrastructure state.

Important classes include:

| Class | Responsibility |
|---|---|
| `ApplicationConfig` | Defines capacity, scaling, storage, and retention limits |
| `ComputeInstance` | Represents application compute capacity |
| `ObjectStorage` | Stores and validates objects |
| `LoadBalancer` | Selects available compute instances |
| `AutoScaler` | Evaluates horizontal scaling conditions |
| `BackupManager` | Creates, expires, and restores backups |
| `ApplicationPlatform` | Coordinates infrastructure components |

The script includes assertions covering:

- instance creation
- object integrity
- traffic distribution
- backup creation
- deletion and restore
- unhealthy-instance replacement

The Python implementation keeps infrastructure state in memory so the relationships between components remain easy to inspect.

---

## JavaScript Implementation

The JavaScript implementation takes an event-driven approach.

`EventEmitter` is used to expose infrastructure events such as:

- scaling
- health changes

This separates infrastructure actions from observers that may need to record metrics, logs, or alerts.

The implementation also uses asynchronous request processing through `Promise.resolve()` to represent an event-loop-friendly workflow without requiring an external HTTP library.

`Map` is used for:

- stored objects
- backup records
- request distributions

The JavaScript implementation is therefore structurally different from the Python version even though the domain rules are related.

---

## C++17 Implementation

The C++ implementation focuses on resource governance.

Its major components are:

| Component | Purpose |
|---|---|
| `Instance` | Represents bounded compute capacity |
| `ObjectStorage` | Stores objects and validates integrity |
| `BackupManager` | Creates and restores snapshots |
| `LoadBalancer` | Routes traffic using STL algorithms |
| `RepositoryGovernanceEngine` | Evaluates deployment conditions |
| `BranchProtectionPolicy` | Represents deployment-level enforcement rules |
| `ComputeStoragePlatform` | Owns infrastructure state |

The C++ model demonstrates explicit ownership and references between infrastructure components.

STL algorithms are used for selection, searching, counting, and ordering.

The governance engine returns both an eligibility result and a list of blocking conditions. This is useful in operational systems because a binary `true` or `false` result alone does not explain why a deployment was blocked.

---

## Java 17 Implementation

The Java implementation emphasizes enterprise domain modeling.

A `record` is used for immutable configuration and result values.

The domain contains:

- `PlatformConfig`
- `ComputeInstance`
- `StoredObject`
- `Backup`
- `LoadBalancer`
- `GovernancePolicy`
- `EligibilityResult`

The `DeploymentPolicy` interface separates policy definition from infrastructure state.

`ProductionDeploymentPolicy` implements the policy.

This design makes it possible to replace one governance strategy with another without embedding policy decisions directly inside compute or storage classes.

The Java implementation also uses:

- streams for aggregation and filtering
- immutable result lists
- custom runtime exceptions
- explicit state transitions
- SHA-256 integrity validation
- domain-specific validation

This structure resembles the separation commonly used in enterprise service-layer designs.

---

## PostgreSQL Data Model

The PostgreSQL implementation treats the infrastructure as a relational system.

The principal relationships are:

Repository  
├── Branches  
│   └── Commits  
├── Compute Instances  
│   └── Health Checks  
├── Storage Objects  
│   └── Backup Objects  
├── Backups  
├── Deployment Requirements  
└── Pull Requests  
    ├── Reviews  
    │   └── Review Comments  
    ├── Status Checks  
    └── Conversations

The relational model intentionally separates infrastructure concerns instead of placing the complete application state in one table.

---

## Database Constraints

Database-level constraints enforce important invariants.

Examples include:

- compute capacity must be positive
- active requests cannot be negative
- active requests cannot exceed instance capacity
- branch names are unique within a repository
- storage object versions are unique for an object key
- backup expiration must occur after backup creation
- review states must come from a controlled set
- status checks must use valid states

The `validate_instance_request_count` trigger provides an additional database-level safeguard for request accounting.

This is important because application code is not the only component capable of modifying a database.

---

## Database Indexing

Indexes are placed around access patterns rather than every column.

Important indexes include:

- compute instances by repository and state
- commits by branch and creation time
- Pull Requests by repository and state
- Pull Requests by target branch and state
- storage objects by repository and key
- backups by repository, state, and creation time
- reviews by Pull Request and review state
- conversations by Pull Request and resolution state
- health checks by instance and timestamp

These indexes support operational queries such as:

- finding healthy compute capacity
- finding open Pull Requests
- retrieving recent backups
- locating unresolved review conversations
- retrieving recent health checks

Excessive indexing would increase write cost and storage overhead, so the schema uses indexes around clear query patterns.

---

## Database Views

`healthy_capacity` provides a consolidated capacity view.

It reports:

- healthy instance count
- total healthy capacity
- active requests
- utilization

`pull_request_review_summary` aggregates review outcomes for Pull Requests.

These views reduce repeated aggregation logic in operational queries.

---

## Merge Eligibility Function

The PostgreSQL function `evaluate_merge_eligibility` combines repository governance and infrastructure state.

It evaluates:

1. Pull Request existence.
2. Pull Request state.
3. Draft status.
4. Required approvals.
5. Active change requests.
6. Failed status checks.
7. Pending status checks.
8. Unresolved conversations.
9. Healthy compute capacity.
10. Backup validity.

The result contains both:

- `eligible`
- `reason`

This makes the database capable of explaining why a workflow is blocked.

---

## Transactional Integrity

The sample PostgreSQL workflow evaluates eligibility before changing the Pull Request state.

The merge operation is performed inside a transaction.

This prevents a partially completed workflow from leaving the database in an inconsistent state.

The database trigger also ensures that a merged Pull Request receives a merge timestamp.

The same transactional principle is useful for infrastructure operations such as:

- reserving capacity
- updating deployment state
- recording a backup
- changing operational status
- completing a deployment

---

## Scaling and Storage Relationship

Compute and storage scale differently.

More requests  
↓  
Higher utilization  
↓  
More compute instances

More application data  
↓  
More storage objects  
↓  
More storage capacity

The two dimensions should not be conflated.

Adding compute instances does not automatically solve a storage-capacity problem.

Increasing storage capacity does not automatically increase request-processing capacity.

A scalable architecture treats each resource dimension independently while coordinating them through application behavior and operational policy.

---

## Failure Scenarios

The implementations cover several meaningful failures.

### Compute capacity exhaustion

If all healthy instances are at capacity, the load balancer cannot route another request.

The correct response is an explicit capacity failure rather than silently assigning work to an overloaded instance.

### Instance failure

An unhealthy instance stops receiving traffic.

The platform can replace it while maintaining the configured minimum fleet size.

### Storage corruption

Checksum verification detects unexpected object modification.

The application can reject corrupted data rather than treating it as valid.

### Missing object

Attempting to retrieve or delete a nonexistent object raises an explicit error.

### Missing backup

Deployment governance can block deployment when a required valid backup does not exist.

### Stale backup

A backup can exist but still fail a policy requiring a recent recovery point.

### Insufficient healthy capacity

A deployment can be blocked when enough compute instances are not healthy or total capacity falls below the configured requirement.

---

## Security Considerations

The project models several security-related controls without pretending that the in-memory implementations provide complete production security.

Important controls include:

- validation of object keys
- object size limits
- integrity checks
- explicit state validation
- bounded compute capacity
- backup verification
- failure isolation
- restricted deployment eligibility

Production object storage should also address:

- encryption at rest
- encryption in transit
- identity and access management
- least-privilege permissions
- audit logging
- object versioning
- retention and deletion policies
- immutable backup options where required
- secret management

Production load balancing should address:

- TLS termination
- authentication and authorization
- rate limiting
- request validation
- abuse detection
- health-check security
- network isolation

Production backups should address:

- separate credentials
- encryption
- access isolation
- immutable or protected recovery copies
- restore testing
- monitoring of backup failures

---

## Performance Considerations

The Python, JavaScript, and Java simulations select a compute instance by scanning the available instances.

For `n` instances, a single routing decision is approximately `O(n)`.

If many thousands of instances must be considered, a production load-balancing implementation would normally use more specialized routing structures and distributed control-plane mechanisms.

Storage retrieval through a hash map is approximately `O(1)` average-case for key lookup.

The PostgreSQL queries depend on indexes, cardinality, query plans, and table size.

Capacity aggregation uses grouped queries and can benefit from appropriate indexes when the dataset becomes large.

Backup creation in these simulations copies the represented object state. A production backup service would normally use incremental snapshots, copy-on-write techniques, deduplication, or storage-native snapshots to avoid copying every byte on every backup.

---

## Operational Trade-offs

| Design choice | Benefit | Trade-off |
|---|---|---|
| Horizontal scaling | Improves capacity and redundancy | More instances increase operational cost |
| Minimum instance count | Preserves redundancy | Capacity remains allocated during low traffic |
| Maximum instance count | Limits runaway scaling | Extremely large traffic may still exceed capacity |
| Least-utilized routing | Simple capacity-aware distribution | Requires current instance utilization information |
| Checksums | Detects data corruption | Adds computation and metadata |
| Frequent backups | Improves recovery point | Increases storage and operational cost |
| Database constraints | Protects integrity centrally | Makes schema changes more deliberate |
| In-memory simulation | Simple and deterministic | Does not provide distributed durability |
| Explicit governance | Makes deployment conditions visible | More policy conditions can increase operational complexity |

---

## Relationship Between the Components

The project treats the infrastructure as a set of related but distinct control planes.

Request Plane  
└── Load Balancer  
    ├── Compute Fleet  
    └── Health Checks  
        └── Scaling Policy

Data Plane  
└── Object Storage  
    └── Backup

Governance Plane  
├── Capacity Policy  
├── Backup Policy  
└── Deployment State

This separation prevents a common architectural mistake: treating compute, storage, availability, and recovery as one problem.

They are connected, but they have different failure modes and different scaling characteristics.

---

## Practical Workflow

A realistic deployment sequence represented by the project is:

1. Establish the application repository and deployment configuration.
2. Provision the minimum compute fleet.
3. Configure persistent object storage.
4. Register health checks.
5. Place compute instances behind the load balancer.
6. Upload application release data.
7. Create a recovery backup.
8. Validate compute capacity.
9. Process application traffic.
10. Evaluate scaling conditions.
11. Detect and isolate unhealthy instances.
12. Replace failed capacity.
13. Validate backup availability.
14. Evaluate deployment eligibility.
15. Complete the deployment only when required operational conditions are satisfied.

Each stage has a distinct responsibility and failure condition.

---

## Limitations of the Simulation

The source files intentionally model infrastructure behavior without attempting to implement a complete cloud platform.

The simulations do not provide:

- real virtual machines
- real network load balancing
- real object-storage durability
- multi-region replication
- distributed consensus
- real DNS management
- TLS certificate provisioning
- cloud IAM
- real autoscaling APIs
- production-grade monitoring
- real-time distributed metrics

The PostgreSQL implementation provides a stronger persistence model but still represents infrastructure state rather than controlling actual cloud resources.

The purpose of the implementations is to make the architecture, state transitions, constraints, and operational policies executable and inspectable.

---

## File-Level Responsibilities

### Python

Models the complete infrastructure lifecycle in one executable simulation.

It is particularly useful for inspecting:

- configuration
- compute state
- traffic distribution
- scaling
- object integrity
- backup restoration
- validation

### JavaScript

Models the same domain through an event-driven design.

It emphasizes:

- asynchronous request handling
- event emission
- `Map`-based state
- infrastructure events
- health and scaling notifications

### C++17

Focuses on resource governance and capacity evaluation.

It emphasizes:

- explicit types
- STL algorithms
- resource ownership
- stateful infrastructure objects
- deployment eligibility

### Java 17

Models the platform using enterprise-oriented domain abstractions.

It emphasizes:

- interfaces
- records
- immutable results
- policy objects
- service boundaries
- validation
- stream-based aggregation

### PostgreSQL

Provides durable relational state and database-enforced rules.

It emphasizes:

- normalized infrastructure entities
- foreign keys
- check constraints
- indexes
- triggers
- views
- CTEs
- transactional workflows
- merge and deployment eligibility

---

## Core Domain Model

The complete conceptual model can be represented as:

Repository  
├── Compute Instances  
│   └── Health Checks  
├── Storage Objects  
│   └── Backups  
├── Branches  
│   └── Commits  
└── Deployment Requirements  
    ├── Healthy Instance Requirement  
    ├── Capacity Requirement  
    └── Backup Requirement

The resulting architecture connects runtime capacity, persistent data, recovery, and governance without treating them as interchangeable resources.
