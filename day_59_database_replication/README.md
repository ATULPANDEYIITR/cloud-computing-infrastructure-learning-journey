
# Database Replication

## Scope

This project models database replication as a primary-replica architecture with explicit write ordering, replication modes, replica state, acknowledgement requirements, lag detection, recovery, and read routing.

The four central concepts are:

| Concept | Role |
|---|---|
| Primary | Accepts authoritative writes and establishes transaction order |
| Synchronous replication | Requires configured replica acknowledgements before the write is accepted |
| Asynchronous replication | Allows the primary to acknowledge before replicas apply the change |
| Read replicas | Replicas used for read workloads while accepting replicated state from the primary |

The implementations intentionally distinguish the write authority from replicated copies. A replica can be temporarily stale, lagging, or unavailable without changing the conceptual role of the primary.

## Architecture

```text
                         WRITE
                           |
                           v
                  +------------------+
                  |      PRIMARY     |
                  | authoritative DB |
                  +---------+--------+
                            |
                replication log / changes
                 +----------+----------+
                 |          |          |
                 v          v          v
            +---------+ +---------+ +---------+
            | Replica | | Replica | | Replica |
            |    A    | |    B    | |    C    |
            +----+----+ +----+----+ +----+----+
                 |           |           |
                 v           v           v
              READ        READ        READ

Synchronous:
PRIMARY -> replica acknowledgement -> client acknowledgement

Asynchronous:
PRIMARY -> client acknowledgement
        -> replication queue -> replicas
```

## Primary-Replica Architecture

The primary is the authoritative writer. It assigns an increasing sequence number to each change and records the resulting change in a replication log.

A replica maintains its own applied sequence number. The difference between the primary sequence and the replica sequence represents replication lag.

The important distinction is that replication does not make the primary and replicas independent writers. The model assumes a single authoritative write stream and one or more consumers of that stream.

A typical transaction has these stages:

1. The client submits a write.
2. The primary validates the request.
3. The primary creates a monotonically increasing sequence number.
4. The primary applies the local change.
5. The change is sent to configured replicas.
6. Replicas validate sequence continuity.
7. Replicas apply the change.
8. Synchronous policies wait for the required acknowledgements.
9. Asynchronous policies allow replication to continue after the primary acknowledgement.
10. Read traffic can be routed to an appropriate replica when consistency requirements permit it.

This model makes branch-like replication state explicit without treating a replica as an independent source of truth.

## Synchronous Replication

Synchronous replication couples write acknowledgement to replica acknowledgement.

A simplified flow is:

```text
Client
  |
  v
Primary
  |
  +----> Replica A ----+
  |                    |
  +----> Replica B ----+----> acknowledgement
                       |
                       v
                     Client
```

The Python implementation exposes `ReplicationMode.SYNCHRONOUS` and evaluates a required acknowledgement count. A write is considered unsuccessful when the configured acknowledgement requirement cannot be satisfied.

The JavaScript implementation represents this as an asynchronous service operation. Replica application is awaited before a synchronous acknowledgement is returned.

The C++ implementation uses `GovernanceEngine` to evaluate synchronous acknowledgement requirements while keeping the primary, replicas, and policy as separate objects.

The Java implementation represents the policy explicitly through the `ReplicationPolicy` record. `ReplicationService` uses the policy to determine whether a transaction reaches the committed state.

The PostgreSQL implementation stores synchronous requirements in `replication_policies` and records individual acknowledgements in `replication_acknowledgements`.

### Synchronous Failure

Synchronous replication trades write availability or latency for stronger replication guarantees.

If two acknowledgements are required and only one replica is available, the write cannot satisfy the configured policy.

This creates an operational dependency:

```text
Required acknowledgements = 2
Available healthy replicas = 1

1 < 2
Write policy not satisfied
```

The exact behavior of a production database depends on its replication configuration and transaction protocol. A learning model must not be interpreted as a universal implementation of a particular database engine.

## Asynchronous Replication

Asynchronous replication separates primary commit acknowledgement from replica application.

The flow is:

```text
Client
  |
  v
Primary -----> Client acknowledgement
  |
  +----> replication queue ----> Replica A
  |
  +----> replication queue ----> Replica B
```

The Python model stores pending changes in each replica's receive queue. `drain_async_replication()` applies queued changes and brings replicas up to the primary sequence.

The JavaScript model uses Promises and `setImmediate()` to model asynchronous application work without external dependencies. This gives the implementation an event-driven structure rather than simply translating the Python control flow.

The C++ implementation represents pending changes with STL containers and applies them explicitly through `Replica::apply()`.

The Java implementation uses `ArrayDeque<Change>` as the replica queue. This makes the state transition from `ONLINE` to `LAGGING` explicit.

The PostgreSQL model records transactions and acknowledgements independently. This allows reporting queries to distinguish the existence of a primary transaction from the replicas that have acknowledged it.

## Read Replicas

A read replica is a replicated copy intended to serve read workloads.

Read routing must account for consistency.

A replica with lag may not contain the newest committed value:

```text
Primary sequence: 100
Replica sequence: 97

Replica lag: 3 changes
```

A read immediately after a primary write can therefore observe different state depending on the selected node.

The Python implementation exposes separate primary and replica reads and reports lag.

The JavaScript implementation provides `routeRead()` with an explicit preferred replica. This makes the consistency decision visible to the caller.

The Java implementation permits replica reads while rejecting reads from an offline replica.

The PostgreSQL `replica_health` view exposes primary sequence, replica sequence, and calculated lag for operational reporting.

Read replicas can improve read throughput, but they do not automatically provide read-after-write consistency. Applications that require the newest value may need to read from the primary or use a consistency mechanism appropriate to the database system.

## Replication State

The source files model three important replica states:

| State | Meaning |
|---|---|
| `ONLINE` | Replica can accept and apply replication work |
| `LAGGING` | Replica has received work that has not yet been applied |
| `OFFLINE` | Replica cannot participate in replication or reads |

The state is derived from operational conditions rather than being treated as a permanent property.

A replica can move through a sequence such as:

```text
ONLINE
  |
  | receives unapplied changes
  v
LAGGING
  |
  | applies queued changes
  v
ONLINE

ONLINE
  |
  | node failure
  v
OFFLINE
  |
  | recovery and catch-up
  v
LAGGING
  |
  | replication catches up
  v
ONLINE
```

## Sequence Integrity

Each implementation uses an ordered change sequence.

A replica expects the next change to follow the last applied sequence. This prevents silent acceptance of an obvious sequence gap.

For example:

```text
Replica applied: 10
Expected:        11
Received:        13

Result: reject change
```

This is important because replication correctness is not only about copying values. The replica must preserve the intended order of changes.

The Python and JavaScript implementations also validate change checksums. The C++ implementation uses a deterministic dependency-free hash for the educational simulator and explicitly identifies that production cryptographic integrity protection should use a vetted cryptographic implementation.

The PostgreSQL transaction records store a checksum derived from repository, sequence, key, and value.

## Python Implementation

The Python source models the replication domain with dataclasses and enumerations.

`Change` is an immutable description of a replication event. It contains:

- Sequence number
- Record key
- Value
- Checksum

`Primary` maintains authoritative data and a change log.

`Replica` maintains:

- Replica identity
- State
- Applied sequence
- Replicated data
- Pending changes

`ReplicatedDatabase` coordinates primary writes, replica acknowledgement, synchronous policies, asynchronous queues, reads, lag calculation, and health reporting.

The implementation deliberately separates:

```text
Primary.write()
        |
        v
Change
        |
        +----> Replica.receive()
        |
        +----> Replica.apply_pending()
```

The failure demonstration configures a synchronous quorum larger than the number of available replicas. This exposes the difference between a locally successful primary write and a write that satisfies a configured replication policy.

The recovery example demonstrates asynchronous lag followed by catch-up.

Assertions verify that recovered replica state matches the expected value and that lag reaches zero.

## JavaScript Implementation

The JavaScript implementation emphasizes event-driven processing.

`PrimaryDatabase` extends `EventEmitter` and emits a `commit` event whenever a primary transaction is recorded.

`ReadReplica` validates sequence continuity, queues changes, and applies them asynchronously.

`ReplicationCluster` coordinates:

- Primary commits
- Replica delivery
- Synchronous acknowledgement
- Asynchronous delivery
- Replica catch-up
- Lag reporting
- Read routing
- Health reporting

The use of Promises is meaningful here because replication work is represented as an operation that can complete independently of the initial primary write.

The implementation also handles an offline replica without allowing that failure to crash the entire asynchronous workflow.

## C++17 Implementation

The C++ implementation treats replication as a small governance engine.

The main domain objects are:

| Type | Responsibility |
|---|---|
| `Change` | Immutable description of a replication event |
| `Replica` | Stores replica state, pending changes, and local data |
| `Primary` | Maintains authoritative state and sequence |
| `GovernanceEngine` | Applies replication policy and acknowledgement requirements |
| `ReplicaHealth` | Provides operational health information |

STL containers are used for data storage and pending queues.

The `GovernanceEngine` receives a replication mode and acknowledgement requirement, which allows the same engine to represent different deployment policies.

The program also handles:

- Invalid keys
- Offline replicas
- Sequence gaps
- Asynchronous catch-up
- Synchronous acknowledgement failure
- Lag calculation
- Exception-based failure reporting

The C++ design emphasizes explicit ownership and object boundaries rather than relying on dynamic runtime structures.

## Java 17 Implementation

The Java implementation represents replication as an enterprise-style domain service.

The principal domain types are:

- `Change`
- `ReplicationPolicy`
- `ReplicationResult`
- `PrimaryNode`
- `ReplicaNode`
- `ReplicationService`

Java records are used for immutable value objects such as `Change`, `ReplicationPolicy`, and `ReplicationResult`.

`ReplicationPolicy` separates policy from execution. It contains:

- Replication mode
- Required acknowledgements
- Stale-read permission

`ReplicationService` owns the workflow that evaluates these policy values.

The replica queue uses `ArrayDeque`, while replica and primary state use collection types with explicit encapsulation.

The Java program also models transaction outcomes through `TransactionState`, allowing the result to be expressed as `CREATED`, `COMMITTED`, or `REJECTED`.

This design is useful when replication is part of a larger enterprise service where domain policy and operational behavior need to remain separate.

## PostgreSQL Relational Model

The PostgreSQL implementation represents replication state relationally.

The core relationships are:

```text
Repository
    |
    +---- Database Nodes
    |
    +---- Replication Policies
    |
    +---- Data Records
    |
    +---- Replication Transactions
                |
                +---- Acknowledgements
                |
                +---- Status Checks
```

### Main Tables

| Table | Purpose |
|---|---|
| `repositories` | Logical database/repository identity |
| `database_nodes` | Primary and replica nodes |
| `replication_policies` | Synchronous/asynchronous policy configuration |
| `data_records` | Current replicated application data |
| `replication_transactions` | Ordered primary-side replication events |
| `replication_acknowledgements` | Replica acknowledgement records |
| `status_checks` | Operational validation associated with replication transactions |

Primary keys enforce row identity.

Foreign keys prevent orphaned replication records.

Unique constraints prevent duplicate repository names, node names, policy names within a repository, record keys within a repository, and duplicate sequence numbers.

Check constraints enforce valid sequence and key ranges.

Indexes target the principal operational access paths:

- Transaction sequence by repository
- Acknowledgements by replica
- Records by repository and key
- Nodes by repository and state

## Database-Level Enforcement

The PostgreSQL model uses triggers where application-only validation would be insufficient.

`validate_replication_policy()` verifies that synchronous acknowledgement requirements are meaningful and do not exceed the configured replica population.

`update_record_from_transaction()` synchronizes the current `data_records` representation when a transaction changes into the committed state.

This illustrates an important database design principle: invariants that must hold regardless of the application client can be enforced at the database layer.

## Transactional Integrity

The SQL script demonstrates an explicit transaction for acknowledgement and transaction-state updates.

```text
BEGIN
  |
  +-- acknowledgement update
  |
  +-- transaction state update
  |
COMMIT
```

If an operation inside the transaction raises an error, PostgreSQL can roll the transaction back rather than leaving a partially updated workflow.

The SQL functions also provide reusable operations for creating replication transactions and evaluating their eligibility.

## Replication Eligibility

The PostgreSQL function `evaluate_merge_eligibility()` evaluates several independent conditions:

1. The referenced transaction exists.
2. A replication policy exists.
3. The transaction has the required state.
4. Required acknowledgements exist when synchronous replication is configured.
5. Required status checks have passed.

The result contains:

- Eligibility
- Acknowledgement count
- Required acknowledgement count
- Unresolved check count
- Reason

This separates evidence from the final decision.

For example:

```text
Primary transaction: committed
Acknowledgements:    1
Required:            2
Pending checks:      0

Eligible: false
Reason: synchronous acknowledgement requirement not met
```

## Consistency and Availability Trade-Offs

Synchronous and asynchronous replication represent different operational trade-offs.

| Property | Synchronous | Asynchronous |
|---|---|---|
| Primary acknowledgement | Waits for configured replicas | Does not require replica application first |
| Typical write latency | Higher | Lower |
| Replica failure impact | Can prevent policy satisfaction | Can allow primary writes to continue |
| Stale replica reads | Possible if a replica is behind | Common possibility |
| Write availability | More dependent on replication policy | Usually less dependent on replica availability |
| Recovery requirement | Failed replicas must rejoin safely | Lagged replicas must catch up |

These are architectural tendencies rather than universal guarantees. Actual database products expose different replication and consistency mechanisms.

## Failure Conditions

The implementations explicitly handle several failure classes.

### Offline Replica

An offline replica cannot acknowledge a synchronous write and cannot serve reads in the provided models.

### Sequence Gap

A replica rejects a change when its expected next sequence does not match the received sequence.

### Replication Lag

A lagging replica can contain older application state while the primary has already accepted newer changes.

### Insufficient Acknowledgements

A synchronous policy can reject the operation when the configured acknowledgement threshold is not met.

### Invalid Input

Keys are validated for non-empty content and bounded length.

### Checksum Failure

The Python and JavaScript models validate change integrity before accepting a replicated event.

## Security Considerations

Replication transports should be authenticated and encrypted in production.

Important controls include:

- Encrypted replication channels
- Authenticated database nodes
- Least-privilege replication accounts
- Restricted administrative access
- Protected credentials and certificates
- Audit logging for configuration changes
- Integrity validation for replicated data
- Monitoring for unexpected replication topology changes
- Controlled failover procedures
- Prevention of unauthorized replica promotion

A checksum in an educational simulator is not a substitute for authenticated transport or a production-grade cryptographic integrity mechanism.

Read replicas also require access control. A replica should not become a route around authorization rules merely because it is intended primarily for reads.

## Performance Considerations

Replication introduces network, storage, and coordination costs.

The main factors represented by these implementations are:

- Number of replicas
- Replication queue length
- Acknowledgement count
- Write frequency
- Replica apply rate
- Replication lag
- Read distribution
- Synchronous waiting time

A simple lag metric is:

```text
lag = primary_sequence - replica_applied_sequence
```

Large lag indicates that the replica is consuming changes more slowly than the primary is producing them.

Indexes in the PostgreSQL model are limited to access patterns used by operational queries. Indexes should not be added indiscriminately because every additional index adds write and storage overhead.

## Read Consistency

A read-after-write requirement can conflict with read-replica routing.

Consider:

```text
1. Client writes account:100 = ACTIVE
2. Primary commits sequence 20
3. Replica is still at sequence 18
4. Client reads from replica
5. Replica may not contain ACTIVE
```

The application must choose an appropriate consistency strategy.

Possible strategies include:

- Route critical reads to the primary
- Wait for a replica to reach a required sequence
- Use session-level consistency tracking
- Tolerate bounded staleness for suitable workloads

The correct choice depends on application semantics rather than replication alone.

## Operational Reporting

The PostgreSQL `replica_health` view exposes:

- Primary sequence
- Replica sequence
- Calculated lag
- Replica state
- Node identity

The `replication_report` view combines transactions, policies, acknowledgements, and status checks into a reporting-oriented representation.

These views illustrate the distinction between transactional data and operational observability.

## Implementation Comparison

| Area | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Primary model | Dataclass | Event emitter class | `Primary` class | `PrimaryNode` | `database_nodes` |
| Replica state | Enum | Frozen object values | Enum | Enum | PostgreSQL enum |
| Replication queue | List | Array | Vector | `ArrayDeque` | Transaction/acknowledgement rows |
| Synchronous policy | Quorum count | Cluster quorum | Governance engine | Policy record | Policy table |
| Async processing | Explicit drain | Promise/event loop | Explicit catch-up | Explicit service catch-up | Transactional records |
| Integrity | SHA-256 | SHA-256 | Dependency-free deterministic hash | Domain validation | Stored checksum |
| Lag | Sequence difference | Sequence difference | Sequence difference | Sequence difference | `replica_health` view |
| Failure handling | Exceptions | Errors/Promises | Exceptions | Custom exception | Constraints/triggers |
| Reporting | Health list | Health objects | `ReplicaHealth` | Service inspection | SQL views and CTEs |

## Practical Domain Distinctions

The project deliberately keeps these concepts separate:

```text
Primary write
    |
    v
Replication event
    |
    +---- synchronous acknowledgement
    |
    +---- asynchronous queue
    |
    v
Replica applied state
    |
    v
Read availability
```

A replication event is not the same thing as an acknowledgement.

An acknowledgement is not the same thing as a replica being fully caught up.

A replica being online is not the same thing as a replica being current.

A read replica being available is not the same thing as a read being strongly consistent with the latest primary transaction.

These distinctions are central to understanding primary-replica database architectures.
