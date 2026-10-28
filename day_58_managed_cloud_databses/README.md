# Managed Cloud Databases

## Scope

This project models the operational lifecycle of a managed cloud database service. The five implementations use a provider-neutral PostgreSQL-style database environment and focus on four operational capabilities:

- Managed database lifecycle
- Automated patching and maintenance
- Backups and retention
- Read scaling and high availability

The implementations distinguish application-level database behavior from infrastructure operations. A managed service can automate infrastructure work, but the database still requires explicit policies for availability, recovery, capacity, version consistency, and operational safety.

## Core Domain Model

The implementations use the following relationship:

`Managed Database`
→ `Database Nodes`
→ `Primary / Read Replicas`
→ `Health Metrics`
→ `Backups`
→ `Maintenance`
→ `Scaling`
→ `Failover`
→ `Operational Policy`

A managed database normally has a primary node responsible for writes and may have read replicas for read capacity and failover. The service tracks database state independently from individual node state.

The principal database states are:

| State | Meaning |
|---|---|
| `available` | The database is operating normally |
| `maintenance` | A controlled maintenance operation is in progress |
| `degraded` | A health metric or node condition requires attention |
| `failed` | The service cannot provide normal operation |
| `restoring` | Recovery from a backup is in progress |

A primary is not interchangeable with a read replica. The primary represents the write authority, while replicas provide read capacity and can provide failover candidates.

## Automated Patching

Managed database services commonly separate database version management from application deployment. Patching can therefore be scheduled inside a maintenance window rather than performed as an uncontrolled manual operation.

The implementations model a safe maintenance sequence:

`Current Version`
→ `Pre-maintenance Backup`
→ `Maintenance State`
→ `Node Update`
→ `Version Validation`
→ `Available State`

The Python implementation creates a verified snapshot before updating nodes and records maintenance failures in an audit log.

The JavaScript implementation uses asynchronous processing to represent sequential node maintenance. Event emission exposes operational events such as patch start, patch completion, and patch failure.

The C++ implementation treats maintenance as a stateful operation with explicit rollback of the recorded database version when an operation fails.

The Java implementation models maintenance as a domain object with explicit states: `SCHEDULED`, `RUNNING`, `COMPLETED`, and `FAILED`.

The PostgreSQL implementation persists maintenance events and uses transactions to protect state transitions. A database can be locked during a maintenance transition so that competing operations do not independently modify the same lifecycle state.

### Patch Safety

A patch operation should not be treated as a simple version string replacement. The implementations validate several conditions:

- The target version must differ from the current version.
- A valid primary must exist.
- A recovery point should be created before maintenance.
- Node versions must remain consistent with the database version.
- Failure must leave an observable operational state.
- Maintenance history must remain auditable.

A real managed service may perform rolling upgrades, failover-based maintenance, replica-first upgrades, or other provider-specific procedures. The examples model the governance principles rather than a particular provider's internal implementation.

## Backups and Recovery

Backups protect against data loss and operational errors. They are distinct from read replicas.

A read replica primarily supports read scalability and availability. A backup represents a recovery point. Losing both the primary and replicas does not necessarily eliminate recovery capability if valid backups exist.

Each backup contains:

| Attribute | Purpose |
|---|---|
| Backup identifier | Unique recovery object |
| Database identifier | Source database |
| Type | Full or snapshot-style backup |
| Creation time | Recovery point timestamp |
| Expiration time | Retention boundary |
| Size | Storage accounting |
| Checksum | Integrity verification |
| Status | Availability or expiration state |

The Python implementation uses SHA-256 checksums for simulated backup verification and removes expired backup objects.

The JavaScript implementation creates immutable backup records with checksums and expiration timestamps and validates the backup before restoration.

The C++ implementation uses value-oriented backup structures and explicit expiration timestamps.

The Java implementation represents a backup as an immutable record. Its `validAt` method prevents expired or structurally invalid backups from being treated as recovery points.

PostgreSQL stores backup metadata relationally and enforces the relationship between backup expiration and the configured retention period with a trigger.

### Backup Retention

Retention is an operational policy rather than merely a storage property.

The examples distinguish:

`Backup Created`
→ `Backup Retained`
→ `Retention Expired`
→ `Backup Marked Expired`
→ `Recovery Point No Longer Available`

The PostgreSQL database stores the configured retention period at the database level and records backup expiration explicitly. A cleanup operation changes expired backups to the `expired` status instead of silently removing their history.

The examples use a production-oriented policy requiring at least seven days of retention for governance eligibility, while allowing the database configuration itself to support a wider range.

## Scaling

Managed databases may scale vertically by changing compute or storage capacity and horizontally for read workloads by adding read replicas.

These artifacts focus on read-replica scaling.

The scaling relationship is:

`Read Demand`
→ `Replica Count`
→ `Replica Distribution`
→ `Read Capacity`
→ `Failover Capacity`

Replica scaling is bounded to prevent uncontrolled resource creation. The Python and JavaScript implementations explicitly validate replica counts. The C++ implementation uses STL containers to manage node state, while the Java implementation uses a domain-oriented node model.

The examples distribute replicas across availability zones. This matters because adding multiple replicas to the same failure domain does not provide the same resilience as distributing them across independent zones.

Scaling also creates a trade-off:

| Benefit | Cost |
|---|---|
| Higher read capacity | Additional infrastructure cost |
| More failover candidates | More replication traffic |
| Better zone distribution | Operational complexity |
| Reduced primary read pressure | Replica lag management |

A replica should not automatically be treated as an equivalent copy of the primary at every instant. Replication lag is therefore included as a health metric.

## Health Monitoring

The model evaluates database health through several measurements:

- CPU utilization
- Storage utilization
- Replication lag
- Active connections
- Node state
- Version consistency

A replica is considered suitable for failover only when it is operational and within the simulated replication-lag threshold.

This prevents a degraded replica from being selected simply because it exists.

The basic failover decision is:

`Healthy Primary Failure`
→ `Find Healthy Replicas`
→ `Compare Replication Lag`
→ `Select Best Candidate`
→ `Promote Replica`
→ `Demote Failed Primary`

If no suitable replica exists, the database enters a failed state instead of pretending that failover succeeded.

## Python Implementation

The Python file is a self-contained operational simulator built from standard-library features.

Important structures include:

- `ManagedDatabase` for service-level state
- `DatabaseNode` for primary and replica instances
- `Backup` for recovery metadata
- `MaintenanceEvent` for patch operations
- `StatusMetric` for health measurements
- `AuditEvent` for operational history
- Enumerations for lifecycle and role states

The implementation uses dataclasses to represent domain records and explicit exceptions for validation and operational failures.

The `scale_read_replicas` method changes the replica topology while preserving the single-primary invariant.

The `create_backup` method validates primary availability before producing a recovery object.

The `run_maintenance` method creates a snapshot before changing node versions.

The `failover` method chooses the healthy replica with the lowest simulated replication lag.

The `validate_configuration` method checks production-oriented requirements such as multi-zone placement, retention, primary uniqueness, and version consistency.

The script finishes with assertions that verify important invariants after the simulated workflow.

## JavaScript Implementation

The JavaScript file provides an event-driven interpretation of managed database operations.

It uses Node.js standard-library modules:

- `crypto` for identifiers and checksums
- `events` for operational event handling

The `ManagedDatabase` class extends `EventEmitter`, allowing maintenance, scaling, backup, and failover events to be observed without coupling the operations directly to a user interface or monitoring implementation.

JavaScript asynchronous behavior is used during patching. Each node is processed sequentially, representing a controlled maintenance workflow rather than an uncontrolled simultaneous update.

The policy evaluator produces a structured result containing individual checks and an aggregate eligibility decision.

The JavaScript model also separates exceptions into `ValidationError` and `OperationalError`, allowing invalid configuration to be distinguished from runtime infrastructure failure.

## C++17 Implementation

The C++17 implementation emphasizes explicit resource and state management.

The model uses:

- `struct` for compact domain records
- `class` for database lifecycle behavior
- `std::map` for node and backup registries
- `std::vector` for replica candidates
- `std::set` for availability-zone detection
- `std::optional`-compatible domain design
- STL algorithms for policy evaluation
- exceptions for operational failures

The governance engine checks:

1. Exactly one primary exists.
2. Backup retention meets policy.
3. Nodes span multiple zones.
4. A healthy replica exists.
5. Node versions match the database version.

This creates a production eligibility decision independent from the mechanics of individual database operations.

The implementation also demonstrates a rollback-oriented maintenance design. The original database version is preserved before maintenance and restored in the model if the operation throws an exception.

## Java 17 Implementation

The Java implementation uses explicit enterprise domain modeling.

The main domain types are:

- `ManagedInstance`
- `DatabaseNode`
- `MaintenanceJob`
- `Backup`
- `Metrics`
- `StatusCheck`
- `GovernanceDecision`

Java records are used for immutable value-oriented data such as metrics, backups, status checks, and governance decisions.

The `GovernancePolicy` interface separates policy definition from database lifecycle operations. Individual policies implement distinct concerns:

- Backup retention
- Multi-zone deployment
- Single-primary enforcement
- Failover capability
- Version consistency

This prevents all production rules from being embedded in one large method.

The maintenance service uses explicit state transitions and preserves the original version if the operation fails.

The Java implementation therefore represents a service-oriented governance architecture rather than merely reproducing the Python simulator.

## PostgreSQL Implementation

The PostgreSQL script represents the managed database environment as relational data.

The central tables are:

| Table | Responsibility |
|---|---|
| `cloud_databases` | Database configuration and lifecycle state |
| `database_nodes` | Primary and replica topology |
| `backups` | Recovery-point metadata |
| `maintenance_events` | Scheduled and executed maintenance |
| `status_checks` | Operational policy results |
| `backup_policies` | Backup governance configuration |
| `audit_events` | Operational history |

The database uses PostgreSQL-specific features including:

- Enumerated types
- Partial unique indexes
- Foreign keys
- Check constraints
- Triggers
- PL/pgSQL functions
- Views
- Common relational queries
- Transaction boundaries
- Row locking

The partial unique index on primary nodes enforces a critical invariant:

`One Database`
→ `At Most One Primary`

This is stronger than relying solely on application code because concurrent application requests cannot create multiple primary rows without violating the database constraint.

The node-version trigger ensures that a node cannot be inserted with an engine version different from the parent database.

The backup-retention trigger verifies that a backup expiration timestamp does not exceed the configured retention period.

## Operational Workflow

The five implementations represent the following operational lifecycle:

`Provision`
→ `Configure`
→ `Add Primary`
→ `Add Replicas`
→ `Monitor`
→ `Back Up`
→ `Scale`
→ `Patch`
→ `Validate`
→ `Fail Over if Required`
→ `Recover if Required`

Each stage has a different responsibility.

Provisioning establishes the database resource.

Configuration establishes storage, version, region, and retention policy.

Node management establishes primary and replica topology.

Monitoring evaluates runtime health.

Backups establish recovery points.

Scaling changes read capacity.

Patching changes the managed engine version under controlled maintenance.

Failover changes the write authority when the primary becomes unavailable.

Recovery uses a retained backup when normal service state cannot be trusted.

## Failure Conditions

The implementations deliberately reject unsafe conditions rather than silently accepting them.

Examples include:

- Missing primary node
- Multiple primary nodes
- No healthy failover candidate
- Expired backup
- Invalid backup checksum
- Invalid maintenance version
- Unsupported replica count
- Insufficient backup retention
- Single-zone production deployment
- Node version mismatch
- Invalid storage capacity
- Invalid retention period
- Repeated maintenance execution

These checks illustrate an important distinction between validation and recovery.

Validation prevents an unsafe operation from starting. Recovery handles an operational failure after an operation has already begun.

## Security Considerations

Managed database operations require controls beyond basic database credentials.

The domain model supports several security-relevant operational principles:

- Restrict maintenance operations to controlled service identities.
- Keep audit events for administrative actions.
- Validate backup integrity before restoration.
- Prevent unauthorized topology changes through policy enforcement.
- Avoid treating read replicas as independent write authorities.
- Preserve database-level constraints even when application services are compromised.
- Restrict direct access to production database infrastructure.
- Encrypt sensitive database and backup data in a real deployment.
- Use managed identity or short-lived credentials where supported.
- Separate operational roles for database administration, backup services, and application access.

The source files simulate these controls through explicit actors, audit records, validation functions, and policy decisions. They do not claim to implement cloud-provider IAM, network encryption, key management, or storage encryption.

## Performance Considerations

The operational models use collections selected for their respective workloads.

Python dictionaries provide efficient node and backup lookup by identifier.

JavaScript `Map` provides keyed resource management, while `Set` is used for unique availability-zone evaluation.

C++ uses `std::map` for predictable ordered resource registries and vectors for replica candidate evaluation.

Java uses hash-based collections for resource registries and streams for policy evaluation.

PostgreSQL indexes target common operational queries:

- Nodes by database and role
- Backups by database and creation time
- Maintenance events by database and schedule

The database model avoids indexing every column. Indexes have value when they support a real lookup, filtering, ordering, uniqueness requirement, or concurrency invariant.

Replica selection uses replication lag as a decision metric. In a large environment, a production implementation would normally maintain richer health and replication telemetry rather than repeatedly scanning all nodes.

## Managed Service Boundaries

A managed cloud database abstracts many infrastructure responsibilities but does not eliminate operational responsibility.

A managed service may automate:

- Database provisioning
- Host replacement
- Routine patching
- Automated backups
- Storage management
- Replica provisioning
- Failover orchestration
- Monitoring integration

The application and platform team still need to define:

- Backup retention
- Recovery objectives
- Maintenance constraints
- Capacity requirements
- Replica strategy
- Availability-zone distribution
- Version compatibility
- Access controls
- Operational alerts
- Disaster recovery expectations

The implementations therefore model managed databases as policy-driven services rather than simple database connections.

## Important Distinctions

### Backup vs Replica

A replica is an active database node used primarily for read capacity and availability.

A backup is a recovery artifact representing a recoverable database state.

A replica can fail with the primary. A retained backup provides a separate recovery mechanism.

### Scaling vs Failover

Scaling changes capacity.

Failover changes which node owns the primary role.

Adding a read replica does not itself constitute failover.

### Patching vs Restoration

Patching changes the database software version.

Restoration reconstructs service state from a recovery point.

A pre-maintenance backup exists partly because a maintenance operation can require recovery.

### Health vs Policy Eligibility

A node can be healthy while the overall deployment violates a governance policy.

For example, a database can have healthy nodes but still fail a production policy because all nodes are located in one availability zone.

## Practical Production Implications

A production managed database design should evaluate both runtime health and structural configuration.

Runtime questions include:

- Is the primary accepting traffic?
- Are replicas within acceptable replication lag?
- Is storage approaching capacity?
- Are connection counts sustainable?
- Are backups completing successfully?
- Is maintenance progressing?

Structural questions include:

- Is backup retention adequate?
- Are nodes distributed across failure domains?
- Is there a valid failover candidate?
- Are all nodes on supported versions?
- Are administrative actions auditable?
- Are direct modifications restricted?
- Are recovery procedures tested?

The five implementations combine these two categories so that operational health is not confused with configuration compliance.

## Artifact Relationship

The implementations intentionally use different engineering perspectives.

| Artifact | Primary Perspective |
|---|---|
| Python | Operational simulation and lifecycle behavior |
| JavaScript | Event-driven management and asynchronous maintenance |
| C++17 | Governance and merge-style eligibility engine for infrastructure state |
| Java 17 | Enterprise domain modeling and policy objects |
| PostgreSQL | Relational enforcement, persistence, transactions, and reporting |

The implementations model the same managed-database domain while using language-specific structures and design decisions.

The central principle remains:

`Managed Database`
→ `Automated Operations`
→ `Policy Enforcement`
→ `Health Evaluation`
→ `Controlled Recovery`

This separates infrastructure automation from the policies that determine whether the resulting database environment is safe, available, recoverable, and operationally compliant.
