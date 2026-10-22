# Disaster Recovery: RPO, RTO, Backup and Restore, and Recovery Architectures

## Scope

This project models disaster recovery as an operational control system rather than as a collection of backup commands.

The five implementations represent the same domain from different engineering perspectives:

| Implementation | Primary perspective | Main mechanisms |
|---|---|---|
| Python | Recovery simulation | Policies, backup catalog, restore selection, RPO/RTO evaluation, architecture simulation |
| JavaScript | Event-driven recovery control | Asynchronous health checks, failover events, backup validation, architecture-specific recovery |
| C++17 | Recovery decision engine | Strongly typed domain objects, recovery-point management, topology evaluation, validation gates |
| Java 17 | Enterprise governance | Records, enums, interfaces, immutable collections, state transitions, validation services |
| PostgreSQL | Persistent operational model | Relational integrity, backup history, policies, incidents, recovery attempts, validation, reporting |

The central relationship is:

`Failure → Detection → Recovery-point selection → Restore or failover → Validation → Service recovery`

The objective is to keep two independent requirements explicit:

- **RPO** controls acceptable data loss.
- **RTO** controls acceptable service restoration time.

They describe different dimensions of recovery and should not be treated as interchangeable.

---

## Recovery Objectives

### Recovery Point Objective

RPO is the maximum acceptable amount of data that can be lost after a failure.

If a service fails at 01:45 and the newest usable recovery point was created at 01:30:

`Observed RPO = 15 minutes`

If the policy allows 30 minutes, the recovery point satisfies the RPO.

The Python, JavaScript, C++, Java, and PostgreSQL implementations all calculate RPO from an actual failure timestamp and a selected recovery point rather than storing RPO merely as descriptive metadata.

A lower RPO generally requires more frequent data protection, replication, or both. A five-minute RPO cannot be achieved reliably by a backup system that only creates backups once per hour.

### Recovery Time Objective

RTO is the maximum acceptable time between service failure and restoration of the required service capability.

For example:

`Failure = 01:45`

`Service restored = 02:05`

`Observed RTO = 20 minutes`

If the policy specifies an RTO of 30 minutes, the recovery satisfies that objective.

RTO depends on more than the existence of a backup. It can include infrastructure provisioning, database restoration, dependency recovery, configuration retrieval, secret availability, application startup, traffic routing, health validation, and operational decision time.

---

## Recovery Architecture

The project distinguishes three architectures because they provide different recovery characteristics and operational costs.

### Pilot Light

Pilot light keeps a minimal recovery environment available while the primary environment handles normal traffic.

Typical characteristics:

- Critical configuration and infrastructure definitions are prepared.
- Data may be replicated or backed up continuously.
- Application capacity is not necessarily running at production scale.
- Recovery requires infrastructure activation and capacity expansion.
- RTO is generally higher than warm standby or active-active.
- Cost is generally lower than maintaining a full secondary environment.

The implementations model pilot light as requiring additional startup or activation time.

Conceptually:

`Primary → failure → activate recovery infrastructure → restore/synchronize → validate → serve traffic`

Pilot light is useful when the organization accepts a longer recovery period in exchange for lower standby infrastructure cost.

### Warm Standby

Warm standby maintains a reduced operational environment in the recovery region.

Typical characteristics:

- Recovery infrastructure is already running.
- The environment may have reduced capacity.
- Data is synchronized or restored more frequently than in a simple cold environment.
- Failover requires promotion and scaling rather than complete environment construction.
- RTO is generally lower than pilot light.

Conceptually:

`Primary → failure → promote standby → scale/validate → serve traffic`

The JavaScript, Java, Python, and C++ implementations explicitly distinguish standby promotion from active-active continuity.

### Active-Active

Active-active keeps multiple production-capable environments serving traffic simultaneously.

Typical characteristics:

- More than one region or site actively serves requests.
- Traffic can continue through a single-region failure if sufficient capacity remains.
- Data consistency and replication become more complex.
- Traffic routing becomes a critical recovery mechanism.
- RTO can be very low because another environment is already serving traffic.
- Infrastructure and operational costs are substantially higher.

Conceptually:

`Region A ↔ Region B`

Both regions serve traffic before the failure. If Region A fails, traffic continues through Region B without requiring the complete startup of a dormant environment.

Active-active does not automatically guarantee a low RPO. The data-replication mechanism must independently satisfy the required recovery point.

---

## Backup and Restore Model

The backup model distinguishes full and incremental backups.

### Full Backup

A full backup represents a complete recovery baseline.

Example:

`Full backup → version 1000`

It provides a direct restore point but can require significant storage and transfer capacity.

### Incremental Backup

An incremental backup records changes after an earlier backup.

Example:

`Full 1000 → Incremental 1001 → Incremental 1002 → Incremental 1003`

Incremental protection can reduce backup volume but introduces dependency relationships between recovery artifacts.

A production restore process must therefore verify:

- The required full backup exists.
- Every required incremental segment exists.
- The selected artifacts are internally consistent.
- Checksums are valid.
- Encryption keys are available.
- Backup retention has not expired.
- Immutable storage has not been altered.
- The restored database and application versions are compatible.

The source implementations simplify the physical restore operation but explicitly validate backup metadata and recovery-point availability.

---

## Recovery-Point Selection

Recovery-point selection is based on the latest usable backup at or before the failure time.

For a failure at 01:45:

| Backup | Time | Version | Eligible |
|---|---:|---:|---|
| Full | 00:00 | 1000 | Yes |
| Incremental | 00:30 | 1001 | Yes |
| Incremental | 01:00 | 1002 | Yes |
| Incremental | 01:30 | 1003 | Yes |
| Future backup | 02:00 | 1004 | No |

The 01:30 backup is the preferred recovery point because it minimizes data loss while respecting the requirement that the recovery point must not occur after the failure.

The PostgreSQL model expresses this with ordered backup selection and `DISTINCT ON`. The Python and JavaScript implementations perform equivalent selection through collections.

---

## Python Implementation

The Python script uses domain classes rather than treating the recovery exercise as a collection of unrelated functions.

`RecoveryPolicy` validates RPO and RTO requirements.

`Backup` represents an individual recovery artifact and validates:

- identifier presence
- timezone-aware timestamps
- supported backup type
- positive source version
- backup size
- checksum presence

`BackupCatalog` provides ordered backup storage and selects the latest backup available at or before a failure.

`DisasterRecoverySimulator` calculates observed RPO, simulates restoration, estimates architecture-specific restoration time, and evaluates whether the policy is satisfied.

`RecoveryExercise` models recovery nodes separately from backup restoration. This separation is important because a backup restore and an infrastructure failover are related recovery mechanisms, not the same operation.

The script also demonstrates failure cases:

- no available recovery point
- invalid RPO
- invalid backup type
- missing backup metadata
- failed recovery-node state
- insufficient active-active capacity

The implementation intentionally does not manipulate real infrastructure. A production implementation would connect these decisions to backup storage, infrastructure provisioning, database recovery, DNS or traffic-management systems, secret stores, and monitoring.

---

## JavaScript Implementation

The JavaScript implementation uses an event-driven model.

`RecoveryPolicy` validates service-level objectives.

`BackupRepository` maintains ordered recovery points.

`RecoveryNode` represents a recovery environment and exposes asynchronous health and startup operations.

The asynchronous methods are deliberate. Real recovery operations are inherently time-dependent and may involve:

- health probes
- infrastructure startup
- database promotion
- replication checks
- traffic-routing changes
- service readiness checks

`DisasterRecoveryController` coordinates recovery events and records an operational event stream.

The event stream separates state changes such as:

`node_failed`

`restore_completed`

`traffic_shifted`

`standby_promoted`

`failover_failed`

The architecture changes the recovery behavior:

| Architecture | Simulated restoration |
|---|---:|
| Pilot light | 45 minutes |
| Warm standby | 18 minutes |
| Active-active | 2 minutes |

These values are simulation parameters rather than universal engineering values. Real RTO depends on infrastructure size, dependencies, replication technology, automation, operational procedures, and failure scope.

The JavaScript implementation also performs asynchronous backup-integrity validation before accepting a restore.

---

## C++17 Recovery Engine

The C++ program approaches disaster recovery as a decision engine.

The primary domain objects are:

- `RecoveryPolicy`
- `Backup`
- `StatusCheck`
- `RecoveryNode`
- `RecoveryPointManager`
- `DisasterRecoveryEngine`

`std::optional` is used when a recovery point may not exist. This makes the absence of a recovery point explicit rather than representing it with a special timestamp or integer.

`std::set` represents required recovery validation gates.

The engine evaluates:

- whether a recovery point exists
- observed RPO
- architecture-specific recovery time
- backup integrity
- required recovery checks
- failover capacity

The topology model also distinguishes node health from traffic-serving state. A healthy node that is not serving traffic is not equivalent to an active production node.

The active-active scenario requires a surviving healthy serving node after one node fails.

The C++ implementation also contains a separate validation-gate engine. The separation demonstrates an important architectural boundary: recovery decisions can depend on validated operational conditions without mixing the validation mechanism into the storage or topology classes.

---

## Java 17 Enterprise Model

The Java implementation uses explicit domain types and state transitions.

`RecoveryPolicy`, `Backup`, `RestorePlan`, and `RecoveryDecision` are records where immutable value semantics are appropriate.

Enums represent controlled state vocabularies:

- recovery architecture
- node state
- backup type
- incident recovery state

`RecoveryValidator` is an interface that allows integrity checks to be composed without embedding every validation rule inside the recovery service.

The `ChecksumValidator` is a concrete implementation.

`RecoveryEligibilityService` combines:

- recovery-point selection
- backup validation
- architecture-specific RTO estimation
- RPO comparison
- RTO comparison
- final recovery eligibility

`FailoverService` handles operational state transitions separately.

A node cannot move directly from `FAILED` to `HEALTHY`. It must move through:

`FAILED → RECOVERING → HEALTHY`

This explicit transition prevents invalid state changes from being silently accepted.

The enterprise model therefore separates policy, data protection, validation, and infrastructure state rather than putting the entire recovery process into one service.

---

## PostgreSQL Operational Model

The SQL implementation treats disaster recovery as persistent operational data.

The principal relationships are:

`repositories → recovery_policies`

`repositories → backups`

`repositories → infrastructure_nodes`

`repositories → incidents`

`incidents → recovery_attempts`

`recovery_attempts → recovery_validation_checks`

This allows the database to retain both the recovery configuration and the historical evidence needed to evaluate an incident.

### Recovery Policies

`recovery_policies` stores:

- service
- RPO
- RTO
- recovery architecture
- active policy state

Database constraints prevent negative RPO values, invalid RTO values, and unsupported architecture names.

### Backups

`backups` records:

- backup type
- creation time
- source version
- size
- checksum
- immutability
- encryption

The trigger rejects backups that do not satisfy the expected checksum format or that are not marked immutable and encrypted.

This illustrates an important database-level control: application validation should not be the only protection for recovery-critical data.

### Infrastructure Nodes

`infrastructure_nodes` stores recovery topology and distinguishes:

- node health
- traffic-serving state
- architecture
- synchronization time

This supports active-active capacity analysis.

### Incidents

An incident records when a failure started, when it was detected, its severity, and its recovery state.

The state progression is:

`OPEN → RECOVERING → RECOVERED`

A failed recovery can instead result in:

`RECOVERING → FAILED`

### Recovery Attempts

A recovery attempt records:

- selected backup
- start time
- completion time
- restored version
- result
- operational message

The validation table records individual post-restore checks.

Examples include:

- backup integrity
- database consistency
- application health

A recovery is not considered complete merely because data was copied. Post-restore validation is part of the workflow.

---

## Transactional Recovery Workflow

The PostgreSQL transaction demonstrates a controlled recovery operation:

`BEGIN`

→ mark incident as `RECOVERING`

→ select the latest usable recovery point

→ create a recovery attempt

→ record validation checks

→ mark incident `RECOVERED` only when all checks pass

→ `COMMIT`

This prevents a partially completed recovery workflow from being presented as successful.

If the transaction fails before commit, PostgreSQL can roll back the state changes as a unit.

This is particularly important for recovery records because an inconsistent recovery history can make subsequent operational decisions unreliable.

---

## Failure and Validation Conditions

A recovery system must treat failure conditions as first-class states.

### No Recovery Point

If no backup exists before the failure, the system cannot claim that the configured RPO is satisfied.

The implementations return an explicit recovery failure rather than selecting an arbitrary backup.

### Stale Recovery Point

A valid backup can still violate the RPO.

For example:

`Failure = 01:45`

`Recovery point = 00:30`

`Observed RPO = 75 minutes`

A policy requiring an RPO of 30 minutes is violated even though a technically valid backup exists.

### Slow Restoration

A backup can satisfy RPO while failing RTO.

Example:

`RPO = 10 minutes`

`RTO = 60 minutes`

`Observed RPO = 10 minutes`

`Observed RTO = 90 minutes`

The recovery point is acceptable, but the recovery process is too slow.

### Invalid Backup Integrity

A checksum failure must prevent the backup from being trusted.

A production system should never silently restore corrupted recovery artifacts.

### Active-Active Capacity Loss

Active-active architecture only provides continuity if enough healthy capacity remains.

If two active regions exist and one fails, the surviving region may continue service.

If both regions fail, the architecture no longer provides active-active continuity.

### Dependency Failure

Application restoration can fail even when the primary application database is restored.

Dependencies may include:

- identity services
- payment providers
- DNS
- certificate infrastructure
- message brokers
- object storage
- secrets
- configuration services
- external APIs

A realistic recovery test therefore needs dependency validation, not only application startup validation.

---

## Backup Security

Recovery data often contains the same sensitive information as production systems.

The SQL model requires backups to be marked as encrypted and immutable.

Production controls should also address:

- encryption at rest
- encryption during transfer
- key-management availability during a regional outage
- strict backup access permissions
- separate administrative identities
- audit logging
- immutable or object-locked retention
- protection against deletion by compromised production credentials
- geographic separation
- retention-policy enforcement

A disaster recovery system that allows a compromised production credential to delete every recovery artifact does not provide reliable recovery.

---

## Performance and Cost Trade-offs

Recovery architecture creates a trade-off among recovery speed, data protection, complexity, and infrastructure cost.

| Architecture | Typical recovery characteristic | Operational complexity | Infrastructure cost |
|---|---|---|---|
| Pilot light | Infrastructure must be activated | Moderate | Lower |
| Warm standby | Reduced environment already running | High | Medium |
| Active-active | Multiple environments actively serve traffic | Very high | Higher |

Backup frequency also affects cost and RPO.

More frequent backups generally increase:

- storage operations
- network transfer
- backup processing
- retention volume
- monitoring requirements

Replication can reduce recovery-point gaps but introduces consistency, network, conflict, and operational complexity.

The correct architecture therefore depends on the business impact of downtime and data loss rather than on architecture popularity alone.

---

## Recovery Architecture Relationship

The mechanisms can be viewed as a layered recovery model:

`RPO/RTO policy`

↓  

`Backup / replication strategy`

↓

`Recovery architecture`

↓

`Failover or restore`

↓

`Validation`

↓

`Traffic restoration`

RPO and RTO define the required outcome.

Backups and replication provide data protection.

Pilot light, warm standby, and active-active define how much recovery infrastructure is already available.

Failover or restore executes the recovery mechanism.

Validation determines whether the recovered environment is trustworthy.

Traffic restoration returns the service to users.

These layers should remain conceptually separate because changing one layer does not automatically satisfy the requirements of another.

---

## Practical Recovery Test Scenario

The example data contains a failure at 01:45.

For the payment service, the latest recovery point is at 01:00.

Therefore:

`Observed RPO = 45 minutes`

If the policy requires an RPO of 30 minutes, recovery eligibility fails even if the restore itself is successful.

For the active-active order service, a recent recovery point exists and two regions are serving traffic. Failure of one region leaves another active region available.

The database model records the incident and recovery evidence, while the application implementations simulate the decision process independently.

This distinction is important: a successful recovery simulation is not evidence that a production disaster recovery plan has actually been tested.

---

## Production Considerations

A production disaster recovery implementation should test the complete operational chain rather than only backup creation.

Relevant controls include:

- scheduled restore tests
- documented recovery procedures
- automated infrastructure provisioning
- dependency inventory
- secret and key recovery
- cross-region backup replication
- immutable backup storage
- recovery monitoring
- recovery audit logs
- DNS and traffic-routing procedures
- database consistency validation
- application smoke tests
- rollback procedures
- incident ownership
- recovery exercise frequency
- evidence retention

Recovery objectives should also be measured from real exercises.

A declared RTO of 30 minutes has little operational value if repeated recovery exercises require 90 minutes.

---

## Limitations of the Simulations

The source files intentionally model recovery decisions rather than connecting to live infrastructure.

They do not perform real:

- cloud-region failover
- database replication
- DNS changes
- object-storage restoration
- infrastructure provisioning
- secret-manager recovery
- network reconfiguration
- production traffic migration

The architecture-specific recovery durations are simulation values used to make RPO/RTO evaluation concrete.

Real disaster recovery plans require measurements from the actual infrastructure, dependencies, data volume, replication mechanisms, network characteristics, operational procedures, and recovery exercises.

The most important design principle represented by all five implementations is that recovery should be measurable and stateful: the system should know what recovery point exists, what recovery policy applies, what recovery action occurred, whether validation passed, and whether the resulting RPO and RTO satisfy the defined service requirement.
