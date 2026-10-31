# NoSQL Infrastructure: Data Models, Replication, and Consistency

## Project Scope

This project models four major NoSQL database families as related but technically distinct systems:

| Model | Primary structure | Typical access pattern | Main strength |
|---|---|---|---|
| Key-value | Key → value | Exact key lookup | Very fast simple access |
| Document | Document identified by key | Field-based document queries | Flexible records |
| Wide-column | Partition key → clustered rows → sparse columns | Partition-oriented retrieval | Large distributed workloads |
| Graph | Nodes and relationships | Traversal and relationship queries | Connected-data analysis |

The implementations also model eventual consistency, versioned writes, validation, replication, graph traversal, indexed document lookup, and operational governance.

The central architectural relationship is:

`Application request → data model → partition/access strategy → consistency policy → read/write operation → failure handling`

NoSQL is not one database design. The appropriate model depends on the shape of the data, query patterns, scaling requirements, relationship density, and consistency requirements.

## Key-Value Databases

A key-value database stores an opaque value under a unique key.

The Python implementation uses a dictionary-backed store with version numbers. A write increments the version, while an optional expected version implements optimistic concurrency control.

The important invariant is:

`expected_version == current_version → update allowed`

If the versions differ, the update is rejected rather than silently overwriting another writer's change.

This is useful for data such as:

- Sessions
- Feature flags
- Configuration values
- Cached objects
- Short-lived application state
- Idempotency records

The normal lookup operation is approximately `O(1)` in a hash-based implementation.

The model deliberately does not assume that every value is queryable internally. The key is the primary access mechanism.

## Document Databases

Document databases represent records as structured documents, commonly JSON-like objects.

The Python and JavaScript implementations validate required fields and maintain equality indexes. The PostgreSQL implementation uses `JSONB` to represent document content and a GIN index for document-oriented querying.

A document can contain fields such as:

`user_id`, `department`, `skills`, `status`, `metadata`

Different documents can contain different optional fields, which gives document stores more structural flexibility than a rigid relational row.

The important distinction is that flexible document structure does not eliminate the need for validation. Production systems still need rules for:

- Required identifiers
- Field types
- Allowed values
- Maximum document size
- Schema evolution
- Access control
- Sensitive fields

The PostgreSQL implementation demonstrates a database-level JSON document representation while retaining relational integrity for the surrounding operational metadata.

## Wide-Column Databases

Wide-column systems organize data around a partition key and one or more clustering dimensions.

The conceptual structure used by the implementations is:

`partition key → clustering key → sparse columns`

The telemetry example uses:

`device-42 → timestamp → temperature, battery`

This arrangement is intentionally access-pattern driven. A query for one device can retrieve its time-ordered measurements without scanning unrelated devices.

The C++ implementation uses an ordered map for clustering keys. The Python and JavaScript versions explicitly model partitions and clustered rows. The Java implementation uses nested maps to make the partition boundary explicit.

Wide-column design requires careful partition selection. A partition that grows without bound can become a scalability problem even when individual row operations are efficient.

Useful workloads include:

- Time-series telemetry
- Event histories
- Large-scale logs
- Distributed counters
- User activity streams

## Graph Databases

A graph database represents data as nodes connected by typed relationships.

The model is:

`node → relationship → node`

The implementations create relationships such as:

`alice → trusts → bob`

and:

`service → accesses → database`

The graph implementations use adjacency structures and breadth-first search to find a shortest unweighted path.

Breadth-first traversal has complexity `O(V + E)` for `V` visited vertices and `E` examined edges.

Graph storage is useful when the relationship itself is central to the query, such as:

- Identity relationships
- Dependency analysis
- Access-control relationships
- Recommendation networks
- Fraud connections
- Service dependencies

A graph model should not be selected merely because the data contains links. It is most useful when multi-hop traversal and relationship analysis are frequent operations.

## Eventual Consistency

Eventual consistency allows replicas to temporarily contain older state.

The simplified replication model is:

`Client write → leader → replication queue → replica`

Immediately after the leader accepts a write, a replica may still return an older value.

After replication:

`leader version = replica version`

The Python, JavaScript, and Java implementations explicitly model replicas and propagation. The PostgreSQL schema stores replication events and replica versions so operational lag can be inspected.

Eventual consistency is useful when availability, geographic distribution, and write scalability are more important than immediate convergence for every read.

Applications must understand the consequence:

`read from replica ≠ guaranteed newest value`

This matters for workflows such as configuration propagation, telemetry, activity feeds, and geographically distributed services.

Strong consistency is more appropriate when a stale read could produce an unacceptable business or safety outcome.

## Versioned Writes and Conflict Handling

The key-value implementations use monotonically increasing versions.

A client can read:

`version = 4`

and then request:

`write if version = 4`

If another writer has already produced version `5`, the operation fails.

This prevents a lost update.

The Java implementation exposes this through `Optional<Long>` expected-version input. The C++ implementation uses `std::optional<std::uint64_t>`. Python uses an optional integer and raises `ConflictError`.

Version checks are not the same as distributed consensus. They provide application-level protection against overwriting state that changed between read and write operations.

## Python Implementation

The Python program contains five cooperating components.

| Component | Responsibility |
|---|---|
| `KeyValueStore` | Versioned exact-key storage |
| `DocumentStore` | Validated documents and equality indexes |
| `WideColumnStore` | Partition and clustering-key storage |
| `GraphStore` | Nodes, edges, and shortest-path traversal |
| `EventualKeyValueCluster` | Leader, replicas, and replication queue |

Python dictionaries provide the core in-memory structures. Dataclasses model versioned values and replicas. Exceptions distinguish validation failures from concurrency conflicts.

The executable demonstration exercises successful operations and intentional failure conditions.

The program also prints operational complexity and security considerations so the implementation does not treat data structures as isolated syntax examples.

## JavaScript Implementation

The JavaScript implementation emphasizes event-driven behavior.

`EventEmitter` publishes replication events when:

- A leader accepts a write
- A replica receives propagated state

The `EventualConsistencyCluster` performs asynchronous replication using promises and timers. This provides a different engineering perspective from the synchronous Python implementation.

JavaScript `Map` and `Set` structures provide key-value and graph indexes. `structuredClone` prevents callers from unintentionally mutating stored objects through shared references.

The document store creates equality indexes for scalar fields. The wide-column store keeps partitions explicit. The graph implementation performs breadth-first traversal.

The file is executable with a Node.js runtime and requires no npm package.

## C++17 Implementation

The C++ program treats NoSQL infrastructure as a systems-oriented case study.

It uses:

- `std::unordered_map` for key-value access
- `std::unordered_set` for graph membership
- `std::map` for ordered wide-column clustering
- `std::queue` for graph traversal
- `std::deque` for replication events
- `std::optional` for absent values and conditional versions
- Custom exceptions for validation and conflicts

The `ReplicatedKeyValueCluster` separates the leader from replicas and explicitly queues replication events.

This structure makes an important distinction between accepting a write and propagating that write.

The C++ implementation also demonstrates deterministic resource ownership through standard-library containers rather than external infrastructure libraries.

## Java 17 Implementation

The Java implementation uses an enterprise-oriented domain structure.

Records model immutable values:

- `VersionedValue`
- `Document`
- `ReviewDecision`

Services represent domain boundaries:

- `KeyValueService`
- `DocumentService`
- `WideColumnService`
- `GraphService`

`RepositoryPolicy` is a policy object that evaluates approvals and required checks. This illustrates a broader design principle: storage mechanisms and governance decisions should not be tightly coupled.

The implementation also models explicit consistency modes with the `Consistency` enum.

The `EventualCluster` distinguishes strong reads from replica reads. Domain validation and custom exceptions provide explicit failure states.

Java collections and streams are used where they make filtering and aggregation clear without hiding the main domain behavior.

## PostgreSQL Implementation

The PostgreSQL script provides a relational operational model for the same infrastructure concepts.

The schema contains:

- `repositories`
- `branches`
- `commits`
- `document_records`
- `wide_column_rows`
- `graph_nodes`
- `graph_edges`
- `replicas`
- `replication_events`

The document model uses PostgreSQL `JSONB`. A GIN index supports document containment queries.

Wide-column rows are represented with:

`repository_id + partition_key + clustering_key + JSONB columns`

Graph nodes and edges use foreign keys so invalid endpoints cannot be inserted.

Replication state is represented explicitly with:

- `queued`
- `applied`
- `rejected`

The script also includes database-level workflow metadata for repository governance, including Pull Requests, reviews, status checks, and branch-protection policies.

## Pull Requests

A Pull Request represents a proposed change between a source branch and a target branch.

Its lifecycle in the model is:

`source branch → changes → Pull Request → review/checks → merge or close`

A Pull Request contains the source and target branch identities and records the source and target versions observed when the request was created.

The source branch represents the proposed change. The target branch represents the destination whose history and protection rules determine whether the change can be merged.

A Draft Pull Request communicates that the proposal is not ready for final review. Changing it to an ordinary open Pull Request does not itself approve the change.

A Pull Request can be:

- Draft
- Open
- Closed
- Merged

Synchronizing the source branch with the target branch can change the effective source version. That distinction matters because approvals may have been produced against an earlier version.

Merge conflicts occur when the proposed changes cannot be combined automatically with the target branch state. A conflict must be resolved before a normal merge can proceed.

Closing a Pull Request ends the proposal without merging it. Reopening restores an active proposal but does not automatically restore every earlier approval or guarantee merge eligibility.

## Code Review

Code Review evaluates the proposed changes inside a Pull Request.

Reviewers inspect:

- Correctness
- Security
- Maintainability
- Test coverage
- Error handling
- Data-model consequences
- Performance implications
- Compatibility with repository policies

A review can contain inline comments associated with files and lines.

The review implementation distinguishes review states:

| State | Meaning |
|---|---|
| Approved | Reviewer accepts the current revision |
| Changes requested | Reviewer identifies blocking problems |
| Commented | Reviewer provides feedback without approval |
| Dismissed | Previous review decision is no longer active |

A review discussion is a conversation about a particular change. Resolving a conversation means the issue has been addressed according to the repository workflow. It does not itself constitute approval.

Review quality depends on scope. A reviewer should examine the actual change and its consequences rather than treating approval as a general statement that the repository is correct.

## Approvals

An approval is a review decision.

It is narrower than Code Review as a process. Code Review includes inspection, comments, discussion, and evaluation. An approval is the resulting positive decision recorded by an eligible reviewer.

Approval eligibility can depend on:

- Reviewer identity
- Repository role
- Required reviewer groups
- Number of required approvals
- Current source revision
- Repository policy

A stale approval is one associated with an older source revision than the current Pull Request head.

The PostgreSQL queries explicitly compare:

`reviewed_source_version`

with:

`source_head_version`

This prevents an approval for revision `7` from automatically being treated as an approval for revision `8` when repository policy requires review of the current change.

Dismissed approvals are not equivalent to active approvals. A rejected or dismissed decision should not silently contribute to a required approval count.

## Branch Protection

Branch Protection is repository-level enforcement.

It operates after considering the proposed change, reviews, approvals, and automated checks.

Typical protected-branch rules include:

- Required reviews
- Required status checks
- Required conversation resolution
- Restrictions on direct pushes
- Restrictions on force pushes
- Restrictions on branch deletion
- Linear-history requirements
- Merge restrictions
- Administrator bypass behavior
- Explicit governance exceptions

The important distinction is:

`Pull Request = proposal workflow`

`Code Review = evaluation process`

`Approval = review decision`

`Branch Protection = repository-level enforcement`

A Pull Request can exist without being mergeable. A review can exist without being an approval. An approval can exist without satisfying the required count. Passing status checks does not replace required human approvals. Branch Protection combines these conditions into a merge policy.

## Merge Eligibility

The PostgreSQL function `evaluate_pull_request` combines independent conditions.

It checks:

1. Required approval count
2. Status-check state
3. Unresolved review conversations
4. Current approval revision

The result reports both eligibility and reasons for rejection.

Conceptually:

`Merge eligible = approvals satisfied AND checks satisfied AND conversations resolved`

This is intentionally different from treating one approval as automatic permission to merge.

A repository may also require conditions not represented by the simplified function, such as:

- Required linear history
- Merge queue rules
- Signed commits
- CODEOWNERS-based review
- Deployment gates
- Administrator restrictions

Those conditions belong to the branch-protection layer rather than the basic review decision.

## Failure Modes

The implementations intentionally include several failure conditions.

### Invalid Keys

Empty or excessively long keys are rejected.

This prevents malformed identifiers from entering the storage layer.

### Missing Document Fields

The document stores require essential fields before insertion.

Flexible documents still require meaningful application validation.

### Duplicate Documents

The document implementations reject an existing identifier rather than silently replacing it.

### Optimistic Concurrency Conflicts

A stale expected version produces a conflict.

This protects against lost updates when multiple writers modify the same logical record.

### Stale Replica Reads

An eventual-consistency replica may temporarily return no value or an older version.

Applications must not treat a replica read as proof that the leader has the same state.

### Invalid Graph References

Graph edges require both endpoints to exist.

The PostgreSQL model enforces the same principle through foreign keys.

### Stale Approvals

An approval associated with an earlier source revision is identified as stale by comparing versions.

### Failed Status Checks

A Pull Request with failed or incomplete required checks is not eligible when those checks are part of the protection policy.

### Unresolved Conversations

A protected branch can require all review discussions to be resolved before merge eligibility is granted.

## Security Considerations

NoSQL databases frequently expose large distributed datasets, so security must cover both data and infrastructure.

Important controls include:

- Authentication for every database service
- Authorization based on least privilege
- Encryption in transit
- Encryption at rest
- Secret management outside application documents
- Audit logging
- Key rotation
- Network segmentation
- Rate limiting
- Input validation
- Document-size limits
- Protection against unauthorized administrative operations

Flexible document storage creates a particular risk: sensitive fields can be introduced without the same review discipline used for a fixed relational schema.

Schema validation, field-level authorization, and automated security checks remain necessary.

Eventual consistency also has a security implication. Authorization data should not be read from a replica whose state may be stale when a stale decision could grant or deny sensitive access incorrectly.

## Performance Considerations

The main performance decision is to organize data around the dominant access pattern.

| Operation | Main structure | Typical complexity |
|---|---|---|
| Key-value lookup | Hash map | Average `O(1)` |
| Indexed document equality | Field index | Approximately `O(k)` for matches |
| Wide-column partition access | Partition index | Depends on rows returned |
| Graph traversal | Adjacency list | `O(V + E)` |
| Replication queue | FIFO queue | `O(1)` enqueue/dequeue |

The exact performance of a distributed NoSQL database depends on partition distribution, network latency, replication factor, storage engine behavior, indexing, serialization, and workload concurrency.

Wide-column systems require special attention to partition size. A technically valid partition key can still produce a poor production design if nearly all traffic is concentrated into one partition.

Graph workloads require attention to high-degree nodes because a traversal can expand rapidly even when the basic algorithm is linear in the visited graph.

Document indexes improve query performance but increase write and storage costs.

## Data-Model Selection

A practical selection process is:

`Exact identifier lookup? → Key-value`

`Flexible records and field queries? → Document`

`Large partitioned event or telemetry workload? → Wide-column`

`Multi-hop relationship queries? → Graph`

If the workload has several characteristics, the decision should be based on the dominant operational requirement rather than forcing all data into one model.

A single enterprise architecture can legitimately use multiple NoSQL models when different workloads require different data structures.

## Implementation Relationship

The five source files deliberately use different perspectives.

| File | Engineering perspective |
|---|---|
| Python | Simulation and validation of four NoSQL structures |
| JavaScript | Event-driven asynchronous replication |
| C++17 | Systems-oriented storage and traversal engine |
| Java 17 | Enterprise domain services and policy objects |
| PostgreSQL | Relational representation of NoSQL infrastructure metadata and operational workflows |

The implementations share the same conceptual domain but do not mechanically translate one another.

The core separation remains:

`Data model → access pattern → consistency model → validation → operational policy`

This separation prevents key-value, document, wide-column, graph, and eventual-consistency concepts from being treated as interchangeable database features.
