# Database Infrastructure Fundamentals

## Scope

This project models the infrastructure layer beneath ordinary database queries. The five implementations connect four core concerns:

- database servers and their roles
- storage-engine behavior
- transaction processing
- replication and database availability

The implementations deliberately separate logical data operations from infrastructure responsibilities. A transaction determines whether a unit of work commits or rolls back. A write-ahead log records durable logical changes. Replication transfers committed changes to other database nodes. Availability logic determines whether a surviving replica can become authoritative after failure.

The central relationship is:

`Database Server → Storage Engine → Transaction → WAL → Replication → Health → Failover → Availability`

The implementations are educational infrastructure models rather than replacements for a production database engine.

## Infrastructure Model

A database server exposes SQL and transaction services, but internally it depends on several cooperating mechanisms.

| Layer | Responsibility | Implemented representation |
|---|---|---|
| Server | Hosts database services and accepts work | Primary and replica nodes |
| Storage engine | Reads and writes persistent logical records | Storage abstractions and record maps |
| Transaction manager | Provides atomic units of work | Explicit transaction objects |
| WAL | Records changes before or with durable state changes | LSN-based log records |
| Replication | Transfers committed changes | Primary-to-replica replay |
| Health monitoring | Determines node condition | Availability and LSN state |
| Failover | Selects a surviving authoritative node | Most-current healthy replica |

A production database has substantially more machinery, including buffer pools, page formats, checkpoints, locking or MVCC, crash recovery, background workers, filesystem interaction, network protocols, checksums, vacuum or garbage collection, and operational telemetry.

## Database Servers

A database server is the execution and coordination boundary for database workloads. It manages client sessions, transactions, storage access, concurrency, recovery and administrative operations.

The examples distinguish a `primary` from `replica` nodes.

The primary accepts writes in the model. Replicas consume committed changes. This distinction is important because replication does not automatically mean that every node is an independent writer.

The node state is represented separately from the role:

- `primary` or `replica` describes responsibility.
- `online`, `degraded`, or `offline` describes current availability.

Separating role from health prevents an operational state from being confused with architectural responsibility.

## Storage Engines

A storage engine is responsible for turning logical database operations into physical storage operations.

The Python, JavaScript, C++17, and Java 17 implementations expose a narrow storage interface:

`read → write → delete → snapshot/restore`

The implementations use in-memory structures so the transaction and replication mechanisms remain observable without requiring a custom binary storage format.

A production storage engine typically manages:

- fixed-size or variable-size pages
- records and indexes
- buffer caching
- page replacement
- free-space management
- durable writes
- checksums
- crash recovery
- locking or MVCC metadata

The important architectural boundary is that transaction logic should not need to know how a record is physically arranged on disk.

### Storage and durability

An in-memory map is not durable database storage. If the process terminates, its state disappears.

Durability requires a persistent representation and a recovery protocol. The examples therefore treat the write-ahead log as a separate concept rather than incorrectly claiming that an in-memory dictionary provides durability.

## Transactions

A transaction groups related changes into one logical unit.

The examples model the essential state transition:

`ACTIVE → COMMITTED`

or:

`ACTIVE → ROLLED_BACK`

A completed transaction cannot be reused for additional operations.

The transfer scenario demonstrates atomicity:

`Debit source account + Credit target account`

Both changes belong to the same transaction. A validation failure prevents the transfer from committing.

The Python and Java implementations use storage snapshots during commit to model recovery from an unexpected operation failure. PostgreSQL uses an actual database transaction and row-level locking.

## Transaction Isolation

The Java implementation explicitly represents:

- `READ_COMMITTED`
- `REPEATABLE_READ`
- `SERIALIZABLE`

These isolation levels describe how concurrent transactions can observe data.

The transfer workflow uses `SERIALIZABLE` in the enterprise model because financial-style consistency requirements are stricter than simple read/write processing.

Isolation is different from durability. Isolation controls visibility among concurrent transactions. Durability concerns the survival of committed data after failure.

## Write-Ahead Logging

The write-ahead log is represented using monotonically increasing log sequence numbers.

Each record contains:

- LSN
- transaction identifier
- operation type
- logical key
- changed value
- timestamp where appropriate

The LSN provides an ordering mechanism for replay.

The infrastructure flow is:

`Transaction`
`   ↓`
`Logical operation`
`   ↓`
`WAL record`
`   ↓`
`Committed state`
`   ↓`
`Replica replay`

Real database engines use WAL for much more than replication. It is central to crash recovery because the database can replay durable log records after an incomplete write or process failure.

The examples use simplified logical WAL records. Production systems generally log lower-level physical or logical changes according to the engine architecture.

## Replication

Replication maintains copies of database state on other servers.

The model contains one primary and multiple replicas:

`Primary`
`  ├── Replica 01`
`  └── Replica 02`

Each replica tracks an applied LSN. Replication lag is therefore:

`Primary LSN - Replica Applied LSN`

A replica with a lower LSN has not replayed all changes known to the primary.

The JavaScript implementation uses asynchronous event-driven processing. The Python implementation exposes replication as an explicit operation. C++ treats replication as part of a cluster object. Java separates replication into a service class. PostgreSQL stores source, replica, received LSN and replayed LSN as relational infrastructure data.

## Synchronous and Asynchronous Replication

The PostgreSQL model distinguishes replication modes:

| Mode | Basic behavior | Availability implication |
|---|---|---|
| Synchronous | Commit can depend on replica acknowledgement | Stronger replica currency, potentially higher write latency |
| Asynchronous | Replica catches up after primary processing | Lower write latency, possible replica lag |

Neither mode is universally superior.

Synchronous replication can increase commit latency when network or replica performance is poor. Asynchronous replication can lose the most recent acknowledged primary changes if the primary fails before replicas receive them.

The appropriate design depends on the required recovery point objective, recovery time objective, network topology and workload.

## Database Availability

Availability requires more than having multiple servers.

A useful availability model checks:

- number of online nodes
- primary health
- replica health
- replication lag
- replication mode
- failover policy
- ability to identify a valid promotion candidate

The PostgreSQL view `merge_like_availability_decision` combines these conditions into an operational decision.

The same principle appears in the application implementations:

`Health`
`  ↓`
`Candidate selection`
`  ↓`
`Most current healthy replica`
`  ↓`
`Promotion`

A production failover system also needs fencing, split-brain prevention, quorum or consensus mechanisms, client redirection, DNS or service-discovery changes, monitoring integration and recovery procedures.

## Failover and Split Brain

Failover promotes another server when the current primary is unavailable.

The examples select the available replica with the highest applied LSN. This demonstrates the basic candidate-selection problem.

It does not solve split brain.

Split brain occurs when two nodes independently believe they are authoritative. A production system must prevent simultaneous writers through mechanisms such as fencing, leases, consensus, external coordination or controlled operator procedures.

The simplified failover model should therefore be interpreted as a decision engine, not a production-grade distributed consensus protocol.

## Python Implementation

The Python file implements the infrastructure model using standard-library components.

### Storage and transactions

`StorageEngine` maintains logical records and supports snapshots. `TransactionManager` manages transaction state and creates WAL records.

`DatabaseService` provides realistic account operations:

- account creation
- transfer validation
- insufficient-funds detection
- atomic update grouping

The account transfer demonstrates a practical transaction boundary rather than unrelated storage operations.

### Replication

`ReplicationNode` maintains its own storage and applied LSN.

`DatabaseCluster` manages:

- primary state
- replica registration
- WAL replay
- replica lag
- failover candidate selection

A failed replica is skipped during normal replication, allowing the cluster health model to expose degraded infrastructure.

### Validation and failure handling

The Python implementation rejects:

- empty storage keys
- duplicate accounts
- negative balances
- non-positive transfers
- transfers between identical accounts
- missing accounts
- insufficient funds
- reuse of completed transactions
- failover without an available candidate

Assertions verify replica consistency after replication.

## JavaScript Implementation

The JavaScript implementation emphasizes event-driven infrastructure behavior.

`EventEmitter` is used to publish replication and failover events. This reflects the operational nature of database infrastructure, where monitoring systems react to events such as WAL replay or node promotion.

`WriteAheadLog` maintains immutable log records with LSNs.

`TransactionManager` owns transaction commit and rollback behavior.

`DatabaseNode` emits `walApplied` events after replay. `ReplicationCluster` consumes those events and emits cluster-level replication events.

The implementation also uses:

- `Map` for logical storage
- `Set`-like uniqueness through key semantics
- `structuredClone` for state isolation
- Promises and `setImmediate` for asynchronous replication work
- `crypto.randomUUID()` for transaction identifiers
- restricted checkpoint file permissions

The file uses Node.js standard-library APIs and does not require npm packages.

## C++17 Implementation

The C++ program presents the infrastructure as a strongly typed systems-oriented model.

Important types include:

- `StorageEngine`
- `Transaction`
- `TransactionManager`
- `DatabaseNode`
- `DatabaseCluster`
- `AccountService`
- `LogRecord`

`std::map` represents logical storage. `std::optional` represents potentially missing records. Enumerations make operation types, transaction states and node roles explicit.

The transaction manager takes a storage backup before applying operations. If an operation throws, the storage state is restored.

The cluster selects the available replica with the highest LSN for promotion.

The implementation also demonstrates an important systems trade-off: object references and ownership semantics matter when representing a mutable cluster. The example keeps the cluster's original primary object stable and returns the promoted replica rather than pretending that pointer reassignment alone implements a distributed failover.

## Java 17 Implementation

The Java implementation models database infrastructure as an enterprise domain.

Java records are used for immutable value objects such as `Account`, `WalRecord` and `Operation`.

The domain includes:

- explicit transaction state
- isolation-level enumeration
- node roles
- storage service
- transaction manager
- replication service
- account policy
- account service
- custom infrastructure exceptions

`AccountPolicy` is an interface. `ProductionTransferPolicy` implements operational transfer restrictions independently from storage behavior.

This separation illustrates policy-oriented enterprise design:

`AccountService`
`    ↓`
`AccountPolicy`
`    ↓`
`Validation decision`

The transfer operation uses serializable isolation as an explicit domain decision.

## PostgreSQL Implementation

The PostgreSQL script represents the infrastructure model relationally.

The schema includes:

- `database_cluster`
- `database_node`
- `application_account`
- `database_transaction`
- `transaction_operation`
- `write_ahead_log`
- `replication_status`
- `availability_policy`
- `health_check`
- `failover_event`

The schema uses PostgreSQL-specific features including:

- enum types
- partial unique indexes
- JSONB
- PL/pgSQL functions
- triggers
- views
- CTEs
- transactional locking
- check constraints
- foreign keys

### Database-level validation

The partial unique index ensures that a cluster cannot have multiple primary nodes through the modeled state:

`UNIQUE (cluster_id) WHERE role = 'primary'`

The replication trigger prevents:

- a node replicating from itself
- replayed LSN exceeding received LSN

The transaction-state trigger prevents arbitrary state transitions after a transaction has completed.

### Transactional transfer

`create_transfer` locks the source and target account rows with `FOR UPDATE`.

The operation sequence is:

`Lock source`
`   ↓`
`Validate source`
`   ↓`
`Lock target`
`   ↓`
`Validate target`
`   ↓`
`Debit source`
`   ↓`
`Credit target`

This prevents concurrent transfers from independently spending the same balance.

The standalone transaction example demonstrates actual PostgreSQL rollback behavior through an exception raised when the debit condition is not satisfied.

## Database Constraints

The relational model uses constraints where the database can enforce invariants directly.

| Constraint | Purpose |
|---|---|
| Primary keys | Identify infrastructure and business records |
| Foreign keys | Preserve relationships between infrastructure entities |
| Unique keys | Prevent duplicate node and account identities |
| Partial unique index | Limit a cluster to one modeled primary |
| Check constraints | Reject invalid balances and LSN values |
| Trigger validation | Enforce cross-column and state-transition rules |
| Row locks | Protect concurrent account modifications |

Database-level enforcement is important because application validation alone can be bypassed by another client, script or administrative session.

## Performance Considerations

The examples deliberately use a small number of indexes.

The PostgreSQL indexes target access patterns that matter to the infrastructure model:

- WAL lookup by transaction and LSN
- WAL lookup by node and LSN
- unique infrastructure identities

The application models use hash-map or map-based record access rather than repeatedly scanning all records.

Replication uses LSN ordering rather than comparing complete database snapshots.

In real systems, performance also depends on:

- buffer-cache hit rate
- storage latency
- WAL throughput
- checkpoint frequency
- index maintenance
- lock contention
- transaction duration
- network latency
- replica replay capacity
- connection-pool pressure

## Failure Scenarios

The implementations cover several realistic failure conditions.

| Failure | Expected handling |
|---|---|
| Duplicate account | Constraint violation |
| Negative balance | Validation failure |
| Missing account | Transaction failure |
| Insufficient funds | Transfer rejected |
| Reused transaction | Transaction-state error |
| Replica unavailable | Replica skipped during replay |
| Excessive replication lag | Degraded availability state |
| No healthy replica | Failover rejected |
| Invalid replication LSN | Database-level rejection |
| Failed transactional operation | State restoration or database rollback |

## Security Considerations

Database infrastructure security is broader than application authentication.

Important controls include:

- least-privilege database roles
- encrypted client connections
- encrypted replication channels
- authentication between replication members
- protected WAL and backup storage
- audit logging
- restricted administrative access
- secret rotation
- network segmentation
- controlled failover authority
- protection against unauthorized promotion

The JavaScript checkpoint example writes sensitive operational state with restrictive file permissions. The SQL model avoids embedding credentials or connection secrets.

The examples do not implement authentication or encryption themselves because those mechanisms require operating-system, database-server and network configuration beyond the logical infrastructure model.

## Availability and Recovery

Availability is distinct from durability.

A database can have durable data while being temporarily unavailable. A replicated database can remain available after a primary failure if a healthy replica can be promoted.

The recovery relationship can be expressed as:

`Durability`
`   ↓`
`Committed state survives failure`

`Replication`
`   ↓`
`Committed state exists on additional nodes`

`Failover`
`   ↓`
`A surviving node becomes authoritative`

`Availability`
`   ↓`
`Clients can resume database operations`

Recovery Point Objective is affected by replication lag. Recovery Time Objective is affected by detection, promotion, fencing, client redirection and operational automation.

## Limitations

These implementations intentionally simplify several production database mechanisms.

They do not implement:

- physical disk pages
- crash-safe filesystem writes
- buffer pools
- B-tree or hash indexes
- MVCC visibility metadata
- deadlock detection
- distributed consensus
- quorum-based leader election
- network partitions
- fencing tokens
- encrypted replication
- binary WAL formats
- point-in-time recovery
- automated client failover

The simplifications preserve the important architectural relationships without pretending that a collection of in-memory structures is equivalent to a production database engine.

## Cross-Implementation Mapping

| Concept | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Storage | `StorageEngine` | `StorageEngine` | `StorageEngine` | `StorageEngine` | Relational tables |
| Transaction | `Transaction` | `Transaction` | `Transaction` | `Transaction` | Database transaction |
| WAL | `LogRecord` | `WriteAheadLog` | `LogRecord` | `WalRecord` | `write_ahead_log` |
| Replication | `DatabaseCluster` | `ReplicationCluster` | `DatabaseCluster` | `ReplicationService` | `replication_status` |
| Health | Cluster state | Event-driven state | Node state | Node state | `cluster_health` |
| Failover | Replica promotion | Candidate selection | Candidate selection | Service-level promotion | `failover_event` |
| Validation | Exceptions | Exceptions | Exceptions | Policy objects | Constraints and triggers |
| Concurrency | Snapshot-style model | Transaction model | Snapshot-style model | Explicit isolation type | Row locking |

## Practical Infrastructure Workflow

A realistic database deployment can be reasoned about through the following sequence:

`Client request`
`      ↓`
`Database server`
`      ↓`
`Transaction begins`
`      ↓`
`Locks / MVCC establish visibility`
`      ↓`
`Storage changes prepared`
`      ↓`
`WAL records durable changes`
`      ↓`
`Transaction commits`
`      ↓`
`Replication transports and replays changes`
`      ↓`
`Health monitoring measures node state and lag`
`      ↓`
`Failure detected`
`      ↓`
`Eligible replica selected`
`      ↓`
`Fencing / promotion`
`      ↓`
`Clients redirected`

Each stage has a different responsibility. Combining them into a single generic concept would obscure the actual infrastructure design.

## Educational Focus

The project is structured to make the boundaries between database infrastructure mechanisms explicit.

The most important distinction is:

`Storage` answers where database state is represented.

`Transactions` answer how changes are grouped atomically.

`WAL` answers how ordered durable changes are recorded.

`Replication` answers how changes reach additional database servers.

`Availability` answers whether service can continue when infrastructure fails.

These mechanisms interact closely, but they solve different engineering problems.
