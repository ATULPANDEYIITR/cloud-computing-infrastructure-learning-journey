# Database High Availability: Multi-Zone Replication and Controlled Failover

## Technical Scope

This project models a database high-availability architecture based on multiple availability zones, replicated database nodes, health monitoring, quorum evaluation, primary-node fencing, and controlled replica promotion.

The central scenario is an active-passive database service operating across three availability zones. One node accepts writes as the primary. Other nodes maintain replicated copies and can become the new primary when the current primary becomes unavailable and the failover policy permits promotion.

The implementations focus on the control-plane decisions that make failover safe. They distinguish an unavailable database from a database that has been safely isolated from accepting writes. They also distinguish a healthy replica from a replica that is sufficiently current and eligible for promotion.

The five source files are independent implementations of the same technical scenario:

| File | Engineering perspective |
|---|---|
| `database_ha.py` | Object-oriented cluster simulation, validation, policy evaluation, and failover events |
| `database_ha.js` | Asynchronous monitoring, event-driven notifications, fencing adapters, and serialized promotion |
| `database_ha.cpp` | Strongly typed failover eligibility engine with synchronized state transitions |
| `DatabaseHighAvailability.java` | Enterprise domain model, policy objects, fencing service interface, and transactional promotion logic |
| `database_ha.sql` | Relational cluster model, health history, eligibility function, promotion procedure, and audit records |

## High-Availability Architecture

Database high availability reduces service interruption when database infrastructure or individual components fail. A high-availability design must address more than the existence of a backup database. It must determine whether a replica is current, whether the old primary can still accept writes, whether enough cluster members remain available, and whether the promotion operation can be completed safely.

The modeled architecture uses three database nodes:

| Node | Zone | Initial role | Replication mode | Lag | Initial condition |
|---|---|---|---|---:|---|
| `db-az1-primary` | Zone A | Primary | Synchronous | 0 ms | Unreachable and fenced |
| `db-az2-replica` | Zone B | Replica | Synchronous | 15 ms | Healthy |
| `db-az3-replica` | Zone C | Replica | Asynchronous | 160 ms | Healthy |

The configured promotion policy requires two healthy voting members, a synchronous candidate, no more than 100 ms of replication lag, and a fresh health observation.

### Logical topology

    Availability Zone A       Availability Zone B       Availability Zone C
    -------------------       -------------------       -------------------
    Database Primary          Synchronous Replica       Asynchronous Replica
          |                            |                         |
          |                            |                         |
          +----------------------------+-------------------------+
                         Replication and health monitoring
                                      |
                              HA Control Plane
                                      |
                         Quorum and policy evaluation
                                      |
                              Primary fencing
                                      |
                              Replica promotion
                                      |
                            New primary confirmed

The diagram represents the logical architecture, not a specific cloud-provider network topology or a physical replication configuration.

## Fundamental High-Availability Concepts

### Availability zones

An availability zone is an infrastructure failure domain within a cloud or data-centre region. Placing database nodes in separate zones reduces the risk that one localized infrastructure failure will make every database copy unavailable.

Multi-zone placement is useful only when the replication and control-plane design also accounts for network partitions, shared dependencies, and zone-level failures.

The implementations validate that the configured cluster contains nodes in multiple zones. They do not automatically provision infrastructure or verify the physical independence of the zones.

### Replication

Replication transfers database changes from one database node to another. The primary generates changes, while replica nodes receive and apply them.

The distinction between synchronous and asynchronous replication is fundamental to failover decisions.

| Property | Synchronous replication | Asynchronous replication |
|---|---|---|
| Acknowledgement | A commit may wait for acknowledgement from a synchronous standby | The primary can acknowledge without waiting for the replica |
| Potential data loss | Can reduce acknowledged-transaction loss when the required synchronous acknowledgement is correctly configured | Recent acknowledged transactions may not yet exist on the replica |
| Write latency | Can increase due to network and standby acknowledgement delays | Usually lower than synchronous replication |
| Failover risk | Depends on the actual synchronous commit and standby configuration | Depends heavily on replica lag and the position of received and applied log records |
| Operational concern | Standby availability can affect write availability | Promotion may lose transactions not received by the candidate |

Synchronous replication does not guarantee zero data loss in every configuration. The guarantee depends on the database's commit semantics, the number of synchronous standbys, the acknowledgement level, and the failure scenario.

Asynchronous replication is not inherently unsuitable for production. It can be appropriate when lower write latency is more important than minimizing recovery-point loss and when the application accepts the associated risk.

### Replication lag

Replication lag measures the delay between changes made by the primary and their availability on a replica. The meaning of the measurement depends on the database engine and monitoring method.

A replica with significant lag may not contain the most recent committed transactions. Promoting it without considering the lag can produce data loss or application-level inconsistencies.

The project uses `replication_lag_ms` as a simplified policy input. A real PostgreSQL deployment would use replication and write-ahead-log measurements such as received and replayed log positions, along with appropriate timestamp and monitoring information.

### Redundancy and fault tolerance

Redundancy provides alternative components when a component fails. In database infrastructure, redundancy can include:

- Multiple database nodes.
- Replicas in independent availability zones.
- Multiple monitoring paths.
- Redundant network connectivity.
- Independent control-plane components.
- Backups and point-in-time recovery capabilities.

Redundancy and high availability are related but not identical. A system can have multiple replicas and still fail if all nodes depend on one network, one control-plane service, or one shared storage failure domain.

High availability also does not replace backups. Replication can propagate accidental deletion, corruption, or malicious changes. Backups provide a separate recovery mechanism.

## Active-Passive and Active-Active Patterns

### Active-passive architecture

In an active-passive design, one database node is the designated write primary. Replicas receive changes and remain available for recovery or read traffic, depending on the database architecture.

The project implements this model.

Its main state transition is:

    Primary unavailable
          |
          v
    Health observations evaluated
          |
          v
    Healthy voting quorum verified
          |
          v
    Former primary fenced
          |
          v
    Replica eligibility evaluated
          |
          v
    Eligible replica promoted
          |
          v
    Cluster epoch and fencing token updated

Only one database node should be authorized to accept primary writes at a time.

### Active-active architecture

An active-active architecture allows multiple database nodes or sites to accept writes. This requires coordination mechanisms that are not equivalent to promoting one replica in an active-passive cluster.

Important active-active concerns include:

- Conflict detection and resolution.
- Transaction ownership and consistency.
- Global ordering or coordination of writes.
- Replication-loop prevention.
- Multi-site failure handling.
- Split-brain prevention.
- Consistency guarantees across concurrent writers.

The five implementations do not claim to implement multi-writer replication. Their single-primary state model is deliberately designed for active-passive failover.

## Quorum and Failure Detection

A quorum is the minimum number of participating voting members required to authorize a cluster decision.

The sample cluster contains three voting members and requires two healthy voters. The two healthy replicas provide the required voting count after the original primary becomes unavailable.

Quorum is important during network partitions. A node that cannot reach the other members cannot safely infer that the entire cluster has failed. Without a coordination policy, isolated cluster members may independently attempt to become primary.

Health monitoring and quorum solve different problems:

- Health monitoring reports observations about individual nodes.
- Quorum establishes whether enough voting members are available to authorize an operation.
- Fencing prevents an old primary from continuing to accept writes after a replacement is promoted.

A monitoring failure is not proof of a database failure. Production systems should consider multiple observation paths, network partitions, and the difference between a failed node and an unreachable node.

## Primary Fencing and Split-Brain Prevention

Split brain occurs when more than one database node behaves as an authoritative primary. Both nodes may accept writes, producing divergent data histories and difficult recovery problems.

A failed health check is not sufficient to prevent split brain. The old primary may still be running even when the monitoring system cannot communicate with it.

Fencing isolates the former primary from the ability to perform primary writes. Depending on the infrastructure, fencing can involve:

- Revoking a write lease.
- Disabling access through an independent infrastructure control plane.
- Removing storage access.
- Powering off or isolating a host.
- Revoking network or service-level write authorization.

The implementations require fencing confirmation before promotion. This is a safety condition, not a substitute for an actual fencing service.

The JavaScript and Java implementations expose fencing through an adapter or service interface. The Python and C++ examples represent confirmed fencing as cluster state. The PostgreSQL model records fencing state and checks it during eligibility evaluation.

A production implementation must verify fencing independently. It must not set a node's fenced state merely because a monitoring request timed out.

## Failover Policy

The example uses the following policy:

| Policy parameter | Value | Purpose |
|---|---:|---|
| Required healthy voters | 2 | Prevents promotion without sufficient cluster participation |
| Maximum replica lag | 100 ms | Limits promotion of an outdated replica |
| Synchronous candidate required | Yes | Excludes the sample asynchronous replica |
| Maximum health-observation age | 30 seconds | Rejects old monitoring information |
| Minimum availability zones | 3 in the sample | Ensures the configured topology spans independent zones |
| Old primary fenced | Required | Prevents simultaneous primary writers |

The policy is illustrative. These values are not universal production recommendations. Real settings depend on database commit guarantees, workload, network latency, recovery objectives, and the application's tolerance for data loss.

### Recovery Point Objective

Recovery Point Objective (RPO) defines the amount of data loss an application can tolerate, expressed as a time interval or equivalent data-loss measure.

Replication mode and replica lag influence the potential recovery point. The model uses a maximum lag threshold as a simplified eligibility rule.

### Recovery Time Objective

Recovery Time Objective (RTO) defines the maximum acceptable duration of service interruption.

Failover time can include failure detection, quorum evaluation, fencing, replica promotion, connection redirection, and application recovery. A fast promotion alone does not guarantee that the application has resumed normal service.

The implementations do not measure real recovery time. They model the decision and state-transition portions of that process.

## Python Implementation: Repository-Independent Cluster Simulation

The Python program uses dataclasses and enumerations to model cluster nodes, policy parameters, promotion decisions, and failover events.

`DatabaseNode` stores the node's role, zone, replication mode, lag, health, observation timestamp, fencing state, and fencing token. Its validation rejects invalid identifiers, negative lag values, and timezone-naive health observations.

`FailoverPolicy` separates policy configuration from node state. It validates quorum, lag limits, monitoring freshness, and zone requirements.

`DatabaseCluster` stores the current primary, cluster epoch, fencing token, node collection, and event history. It validates the initial topology and enforces exactly one initial primary.

The `evaluate_failover` function is read-only. It accumulates rejection reasons for an invalid candidate, stale monitoring data, an unacceptable replication mode, excessive replication lag, an unfenced primary, or insufficient quorum.

The `promote_replica` function performs a state transition under a re-entrant lock. It checks the expected cluster epoch before changing node roles. This prevents a promotion request based on an outdated cluster version from silently overriding newer state.

The demonstration intentionally rejects the asynchronous replica and promotes the synchronous replica. Assertions check the important conditions and verify the resulting primary role.

The implementation is an in-memory simulation. Its lock protects operations within one Python process; it does not replace distributed consensus or durable cluster coordination.

## JavaScript Implementation: Asynchronous Failover Coordination

The JavaScript implementation emphasizes asynchronous monitoring and event-driven control-plane operations.

`DatabaseNode` validates node data and applies health observations. `DatabaseCluster` uses a `Map` for node membership and validates the initial topology.

`FailoverCoordinator` extends Node.js `EventEmitter`. It exposes events for primary fencing, promotion rejection, and successful primary promotion.

### Asynchronous health processing

The `collectHealth` method uses `Promise.allSettled` to process observations from multiple nodes. A failed probe does not prevent the remaining nodes from being checked.

Probe failures are recorded as unreachable observations. They do not automatically set the primary's fencing state.

### Serialized promotion operations

The coordinator maintains an asynchronous operation queue. Each promotion waits for the preceding operation, preventing competing requests within that coordinator instance from changing the cluster simultaneously.

The expected epoch provides an additional stale-request check.

### Fencing adapter

The fencing adapter represents an independent infrastructure service. A valid response must identify the node being fenced and include a proof identifier.

A rejected candidate leaves the old primary fenced. This is an intentional fail-safe behavior: once fencing is confirmed, the system does not automatically restore write access to the old primary merely because one promotion candidate fails eligibility checks.

The example uses a simulated adapter. A real implementation must integrate with an authenticated infrastructure service and independently verify the effectiveness of fencing.

## C++17 Implementation: Typed Eligibility Engine

The C++ implementation focuses on a strongly typed and synchronized state engine.

The program uses enumerations for roles, health conditions, and replication modes. `DatabaseNode`, `FailoverPolicy`, `FailoverDecision`, and `FailoverEvent` represent the main domain records.

`FailoverEngine` maintains the cluster state in an ordered map. Its constructor validates node identifiers, voting membership, primary uniqueness, quorum requirements, and availability-zone count.

The eligibility function separates decision-making from promotion. It returns a structured result containing eligibility, rejection reasons, healthy voter count, and candidate lag.

The `promote` method uses `std::lock_guard` with a mutex to protect the transition. The method checks the expected epoch and evaluates the candidate while holding the same lock. It then demotes the previous primary, promotes the candidate, and records the new cluster epoch and fencing token.

The implementation uses standard-library containers and algorithms without third-party dependencies.

The mutex provides thread safety within one process. It is not a distributed lock and cannot coordinate independent failover controllers running on different hosts.

## Java 17 Implementation: Enterprise Domain and Policy Model

The Java program represents failover as an enterprise service operation rather than a collection of unrelated state changes.

Records are used for immutable values such as health observations, policy configuration, eligibility decisions, fencing receipts, and failover events.

`DatabaseNode` holds mutable node state while keeping its identity, zone, voting membership, and replication mode fixed. `DatabaseCluster` owns the node membership and primary pointer.

`FailoverPolicy` represents the configurable promotion rules. The `FencingService` interface separates infrastructure isolation from the domain service that makes the promotion decision.

`FailoverService` is responsible for:

- Checking the expected cluster epoch.
- Obtaining a fencing receipt for the former primary.
- Verifying that the fencing receipt identifies the correct node.
- Evaluating replica health and freshness.
- Enforcing synchronous replication and lag requirements.
- Counting healthy voting members.
- Applying the primary-role transition.
- Updating the cluster epoch and fencing token.
- Recording an audit event.

The `ReentrantLock` protects the in-process transition. The service retains the fenced state when a candidate is rejected, rather than making an unsafe attempt to restore the former primary.

The model demonstrates separation between domain policy and infrastructure integration. A production fencing service would need authenticated requests, authorization checks, durable confirmation, retries, timeouts, and independently verifiable proof.

## PostgreSQL Implementation: Relational State and Failover Workflow

The PostgreSQL script represents the cluster using relational tables, integrity constraints, a health-history view, a read-only eligibility function, and a transactional promotion procedure.

### Relational model

| Database object | Responsibility |
|---|---|
| `ha.clusters` | Cluster identity, current primary, epoch, and fencing token |
| `ha.database_nodes` | Node membership, zone, role, replication mode, lag, and fencing state |
| `ha.failover_policies` | Promotion and quorum policy for each cluster |
| `ha.health_observations` | Historical node health observations |
| `ha.latest_node_health` | Latest health record for each node |
| `ha.failover_events` | Auditable primary transitions |

The model uses foreign keys to preserve cluster membership relationships. A composite foreign key ensures that the primary pointer identifies a node belonging to the same cluster.

The partial unique index `uq_one_primary_per_cluster` prevents a cluster from storing two nodes with the primary role.

The node-membership trigger prevents updates that silently change a node's identity or cluster membership. The timestamp triggers maintain `updated_at` for mutable records.

### Health observation history

Health records are append-only observations. The `latest_node_health` view uses PostgreSQL's `DISTINCT ON` to select the latest observation for each node.

This design preserves historical evidence. It avoids losing earlier observations when monitoring data changes.

The index on node identity and descending observation time supports retrieval of recent health records.

### Eligibility evaluation

`ha.evaluate_failover` evaluates a proposed replica without changing cluster state.

It checks:

- Cluster and policy existence.
- Candidate membership and role.
- Candidate health and observation freshness.
- Replication mode.
- Maximum allowed replication lag.
- Current-primary health.
- Primary fencing state.
- Healthy voting-member count.

The function returns an eligibility result, a reason string, a healthy-voter count, and the candidate's lag.

This separation allows administrators and monitoring systems to inspect a rejected promotion before attempting a state transition.

### Transactional promotion

`ha.promote_replica` performs the promotion inside the caller's transaction.

It uses a transaction-scoped advisory lock to serialize operations for a cluster and row locks to protect the cluster and relevant nodes. It evaluates eligibility before changing roles.

When a promotion is accepted, the procedure demotes the old primary, updates the cluster's primary pointer and epoch, increments the fencing token, promotes the candidate, and inserts an audit event.

The unique partial index provides an additional database-level safeguard against two stored primary roles.

The procedure does not physically fence a database host. The fencing state must be confirmed by an external infrastructure process before the procedure is called.

### Reporting queries

The SQL script includes queries for:

- Current node roles and health observations.
- Candidate eligibility comparisons.
- Primary-node uniqueness.
- Cluster epoch and fencing-token verification.
- Node-health aggregation.
- Average and maximum replication lag.
- Failover event history.
- Basic replica policy assessment.

These queries separate current operational state from historical observations and failover records.

## Cross-Language Design Comparison

| Concern | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Node membership | Dictionary | Map | Ordered map | LinkedHashMap | Relational table |
| Policy representation | Frozen dataclass | Immutable policy object | Struct | Record | Policy table |
| Health data | Dataclass fields | Asynchronous observations | Typed node fields | Health observation record | Observation history |
| Validation | Exceptions and assertions | Validation and failover errors | Exceptions | Domain validation | Constraints and functions |
| Quorum | Voting-node count | Voting-node filter | Voting-node iteration | Stream-based count | Aggregate query |
| Concurrency | Re-entrant lock | Promise operation queue | Mutex | ReentrantLock | Advisory and row locks |
| Fencing | Explicit node state | Infrastructure adapter | Explicit node state | Fencing service interface | Stored fencing state |
| Audit | Event dataclass | Event collection | Event structure | Immutable event record | Event table |

The implementations share the same safety principles but use different language features and architectural boundaries. Their locking mechanisms are local to each runtime, while PostgreSQL provides transaction and relational-integrity mechanisms for persisted state.

## Failure Conditions and Edge Cases

| Failure condition | Expected handling |
|---|---|
| Candidate does not exist | Reject promotion |
| Candidate is already primary | Reject promotion |
| Candidate is unhealthy | Reject promotion |
| Health observation is stale | Reject promotion |
| Replication lag exceeds policy | Reject promotion |
| Asynchronous candidate violates policy | Reject promotion |
| Healthy quorum is unavailable | Reject promotion |
| Current primary is still healthy | Reject automatic promotion |
| Previous primary is not fenced | Reject promotion |
| Promotion request uses an old epoch | Reject stale request |
| Two promotion requests compete | Serialize locally or through database locking |
| One health probe fails | Retain results from other probes |
| Candidate fails after primary fencing | Keep the old primary fenced and require a safe recovery decision |

A production implementation must also address authentication failures, monitoring-service outages, network partitions, storage failures, replica divergence, incomplete replication, transaction recovery, client connection redirection, and failure of the control plane itself.

## Performance and Operational Considerations

Failover evaluation scales with the number of cluster members in the in-memory implementations because each evaluation examines node health and voting membership.

The PostgreSQL implementation uses a latest-health view and indexes based on node identity and observation time. As a cluster grows, current health information should be materialized or otherwise indexed according to monitoring frequency and query workload.

High-frequency monitoring can create substantial write volume in health-history tables. Retention and partitioning policies should be designed around the required audit period and operational reporting needs.

Promotion is a low-frequency control-plane operation, so its safety requirements are more important than minimizing a small number of validation queries. Locking and transaction boundaries should remain explicit.

## Security and Data Integrity

A high-availability control plane can affect every application transaction. Its permissions and operational interfaces should therefore be tightly controlled.

Production deployment should include:

- Authentication for database nodes, health monitors, and control-plane services.
- Encryption in transit for replication and management traffic.
- Least-privilege database and infrastructure permissions.
- Independent authorization for primary fencing.
- Durable, tamper-resistant failover auditing.
- Protection against stale or replayed promotion requests.
- Monitoring for unexpected role changes and fencing-token regression.
- Controlled credential rotation.
- Restricted access to administrative procedures.
- Backup and recovery validation independent of replica status.

The sample programs do not implement production authentication, encryption, secret management, or infrastructure authorization. These are deployment requirements, not properties that can be guaranteed by an in-memory failover simulation.

## Execution

The programs use standard language libraries and do not require third-party packages.

| Implementation | Execution command |
|---|---|
| Python | `python database_ha.py` |
| JavaScript | `node database_ha.js` |
| C++17 | `g++ -std=c++17 -O2 -pthread database_ha.cpp -o database_ha` followed by `./database_ha` |
| Java 17 | `javac DatabaseHighAvailability.java` followed by `java DatabaseHighAvailability` |
| PostgreSQL | `psql -d database_name -f database_ha.sql` |

The PostgreSQL script requires permission to create and drop the `ha` schema and its objects. Its schema reset should be used only in a dedicated development or test database.

## Model Limitations

These implementations demonstrate policy evaluation and failover control logic. They do not establish that a real database cluster will achieve a particular availability percentage, RPO, or RTO.

Actual database availability depends on the database engine, replication configuration, storage architecture, network behavior, consensus or lease mechanism, recovery procedures, connection routing, and application retry logic.

A production deployment must integrate the modeled decisions with the database's native replication and recovery mechanisms. It must also test zone failures, partitions, delayed replication, fencing failures, stale monitoring data, and recovery of a former primary before relying on automated failover.
