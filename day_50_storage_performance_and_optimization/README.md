# Storage Performance and Optimization

This project models storage performance as a combination of **IOPS, throughput, latency, caching, storage tiers, and cost**. The five implementations use the same engineering domain while deliberately emphasizing different programming and system-design perspectives.

The central principle is that storage performance is workload-dependent. A system performing many small random operations can be limited by IOPS and latency, while a system transferring large sequential objects can be limited by throughput.

## Performance Model

### IOPS

**Input/output operations per second (IOPS)** measures how many individual storage operations a system can sustain.

IOPS is especially important for workloads dominated by small operations:

- transactional databases
- metadata-heavy applications
- virtual-machine storage
- random key-value access
- application logs with frequent small writes

A high IOPS value does not automatically imply high sequential throughput.

For a request size of \(S\) KB and a device throughput of \(T\) MB/s, an approximate throughput-limited IOPS value is:

`IOPS = (T × 1024) / S`

The effective sustainable IOPS is bounded by both the device IOPS ceiling and its throughput ceiling.

### Throughput

Throughput measures the amount of data transferred per unit of time, normally expressed as MB/s or GB/s.

Large sequential requests generally make better use of available throughput because each operation transfers more data.

For example, a device capable of 7,000 MB/s may provide extremely high throughput without necessarily delivering proportional performance for every small random workload.

### Latency

Latency is the time required to complete an individual I/O request.

The implementations use a simplified model:

`total latency ≈ base device latency + transfer time`

Transfer time increases with request size and decreases as device throughput increases.

Latency matters when individual operations must complete quickly. A low average latency is not sufficient for production analysis because tail latency, queue depth, contention, and workload distribution can materially affect user-visible performance.

## Caching

Caching stores frequently accessed data closer to the application.

The Python, JavaScript, C++, and Java implementations use bounded LRU-style caches. Recently accessed objects remain available while older objects are evicted when capacity is reached.

A cache hit avoids the modeled storage access:

`cache hit → lower effective latency`

A cache miss requires storage access:

`cache miss → device latency + transfer time`

Cache effectiveness depends heavily on locality. The examples intentionally create a hot set of frequently accessed customer objects and a colder archive set.

A high cache-hit ratio does not mean that the storage layer can be ignored. Cache capacity, invalidation, consistency, memory consumption, and write behavior remain important.

The examples use write-through behavior so that a write updates the cached representation rather than leaving an intentionally stale value.

## Storage Tiers

The model contains three representative tiers.

| Tier | Approx. IOPS | Approx. Throughput | Latency | Relative Cost |
|---|---:|---:|---:|---:|
| HDD | 180 | 220 MB/s | 8 ms | Low |
| SATA SSD | 75,000 | 550 MB/s | 0.10 ms | Medium |
| NVMe SSD | 800,000 | 7,000 MB/s | 0.025 ms | Higher |

These values are modeling assumptions rather than hardware guarantees. Actual performance depends on device generation, queue depth, workload pattern, filesystem, controller, RAID configuration, operating system, thermal state, and other factors.

Tier selection is therefore treated as a constraint problem rather than simply choosing the fastest device.

A candidate tier must satisfy the required:

- IOPS
- throughput
- capacity
- monthly cost

When several tiers satisfy the constraints, the implementations select the least expensive eligible tier.

## Cost-Performance Trade-Off

The relevant decision is not:

`Which storage device is fastest?`

It is:

`Which storage configuration satisfies the workload requirements at an acceptable cost?`

For a storage capacity of `C` GB and a tier cost of `P` dollars per GB per month:

`monthly cost = C × P`

A workload requiring 120,000 IOPS and 1,500 MB/s will reject a tier that cannot satisfy either requirement, even if that tier has a lower price.

This avoids a common optimization error: selecting inexpensive storage first and discovering later that the workload cannot meet its performance target.

## Python Implementation

The Python program is a storage workload simulator.

`StorageTier` represents device characteristics. `IORequest` represents an individual operation. `WorkloadMetrics` aggregates performance measurements.

`LRUCache` uses `OrderedDict` to provide constant-time average cache lookup and recency management.

`StorageSimulator` processes reads and writes and calculates modeled latency. Reads can be cache hits or misses, while writes use write-through behavior.

The workload generator produces a mixture of hot and cold keys and read/write operations. This creates realistic locality rather than treating every request as independent.

The tier-selection function evaluates IOPS, throughput, capacity, and optional cost constraints before selecting an eligible tier.

The program also calculates sustainable IOPS for several request sizes, showing why request size matters when interpreting a throughput specification.

## JavaScript Implementation

The JavaScript implementation uses Node.js and emphasizes event-driven processing.

`LruCache` implements bounded recency tracking with JavaScript's `Map`, whose insertion order allows the oldest entry to be removed efficiently.

`StoragePolicy` performs validation and tier selection.

`StorageDevice` evaluates individual I/O requests and exposes asynchronous request processing through `Promise`-based execution.

The workload is processed with `Promise.all`, representing independent operations that can be scheduled concurrently. The program does not introduce artificial sleep delays, so its timing is a deterministic analytical model rather than a physical disk benchmark.

The implementation also demonstrates why asynchronous application execution should not be confused with unlimited storage capacity. A large number of concurrently scheduled operations can still encounter device-level queueing and contention in a real system.

## C++ Implementation

The C++ implementation focuses on a repository-independent storage decision engine and memory-efficient data structures.

`StorageTier` contains physical performance and cost characteristics.

`GovernanceEngine` selects a tier using explicit performance and cost constraints. Its sustainable-IOPS calculation demonstrates the interaction between request size, throughput, and the device IOPS ceiling.

`LruCache` uses a linked list plus an unordered map. This provides average O(1) lookup and O(1) promotion or eviction while maintaining explicit control over the underlying data structures.

`StorageSystem` separates capacity planning from workload execution. It validates requests, records metrics, calculates modeled latency, and maintains cache behavior.

The workload generator uses a deterministic random engine so that the same seed produces repeatable experiments.

## Java Implementation

The Java implementation models storage optimization as an enterprise service.

The domain uses:

- records for immutable value objects
- an enum for access type
- a generic LRU cache
- an interface for storage-selection policy
- a concrete cost-aware policy
- a storage service for execution
- explicit validation and exception handling

`StorageTier` owns the physical performance and pricing rules.

`WorkloadPolicy` represents business-level requirements.

`StoragePolicy` separates the selection strategy from the service that executes storage operations. This allows different enterprise policies to be represented without embedding policy decisions directly into I/O execution.

The Java implementation therefore separates:

`workload requirements → policy evaluation → selected tier → storage execution → metrics`

This is useful when infrastructure decisions are governed by explicit service-level or budget policies.

## PostgreSQL Model

The SQL implementation represents storage optimization as a relational system.

The principal entities are:

- `storage_tiers`
- `storage_workloads`
- `storage_devices`
- `io_operations`
- `cache_events`
- `benchmark_runs`

Relationships connect physical devices to their storage tiers and workloads to capacity and performance requirements.

Constraints prevent invalid values such as negative capacity, zero request sizes, invalid operation types, and impossible cache ratios.

### Database-Level Latency Calculation

The `calculate_io_latency()` trigger derives modeled latency before an I/O record is inserted.

A cache hit receives a reduced modeled latency. A storage operation uses:

`device latency + transfer time`

This keeps the calculation inside the database rather than requiring every client application to reproduce the rule.

### Tier Recommendation

`recommend_storage_tier()` is a PostgreSQL function that evaluates all tiers against IOPS, throughput, capacity, and cost requirements.

It returns the least expensive eligible tier.

This is different from simply storing a preferred tier because the recommendation can be recalculated when workload requirements change.

### Reporting

`storage_capacity_report` exposes a reusable comparison of workloads and storage tiers.

The report identifies whether each tier is:

`ELIGIBLE`

or

`REJECTED`

based on the workload constraints.

Additional queries calculate:

- operation counts
- read/write distribution
- average latency
- cache-hit ratio
- request-size sensitivity
- estimated monthly cost
- sustainable IOPS

## Workload Sensitivity

Storage specifications should always be interpreted with request size and access pattern.

| Workload | Primary Concern |
|---|---|
| Small random database reads | IOPS and latency |
| Small random writes | IOPS, latency, durability |
| Large sequential reads | Throughput |
| Large sequential writes | Throughput and sustained write behavior |
| Frequently reused objects | Cache effectiveness |
| Large cold archive | Capacity and cost |
| Interactive application storage | Latency and tail latency |
| Analytics scratch storage | Throughput and parallelism |

The same storage device can appear excellent for one workload and inadequate for another.

## Performance Reasoning

A simplified performance relationship is:

`Effective performance = min(IOPS capacity, throughput capacity)`

after considering request size.

For example, a 4 KB workload on a 7,000 MB/s device has a theoretical throughput-based ceiling of approximately:

`7,000 × 1024 / 4 = 1,792,000 IOPS`

If the device itself is rated at 800,000 IOPS, the practical modeled ceiling becomes approximately 800,000 IOPS.

For a 256 KB workload:

`7,000 × 1024 / 256 = 28,000 IOPS`

The same device is therefore throughput-limited much earlier.

This illustrates why quoting only IOPS or only MB/s is insufficient for storage architecture decisions.

## Edge Cases and Failure Conditions

The implementations reject:

- zero or negative request sizes
- invalid storage keys
- invalid capacity values
- negative performance requirements
- negative costs
- empty storage-tier collections
- workloads for which no tier satisfies the required constraints
- excessively large individual I/O requests

The SQL schema also enforces these rules at the database layer.

This matters because validation performed only by an application can be bypassed by another client or integration. Database constraints provide an independent integrity boundary.

## Transactional Behavior

The PostgreSQL script includes a transaction containing a benchmark record and an associated I/O operation.

Both changes are committed together.

If a constraint or trigger fails before the commit, PostgreSQL can roll back the transaction so that a partially recorded benchmark does not remain.

This is important for operational metrics because inconsistent benchmark records can lead to incorrect capacity-planning decisions.

## Complexity

The LRU cache operations are designed for average O(1) lookup and update.

Tier selection scans the available storage tiers:

`O(T)`

where `T` is the number of tiers.

Workload simulation processes each request once:

`O(R)`

where `R` is the number of requests.

The SQL reporting queries rely on indexes for device/time and object-key access. Indexes should be added according to actual query patterns because every additional index introduces storage overhead and write-maintenance cost.

## Caching and Consistency

Caching can reduce latency and storage load, but it introduces a consistency problem.

A cache can contain:

- current data
- stale data
- partially invalidated data
- data belonging to an unauthorized request

The examples use write-through behavior to make the model straightforward. Production systems may instead use write-back, write-around, explicit invalidation, TTL-based expiration, or distributed cache protocols.

Security-sensitive data should not be cached without considering authorization boundaries, eviction behavior, memory exposure, and data lifecycle requirements.

## Benchmarking Limitations

These programs are analytical simulations rather than hardware benchmarks.

They do not model all real storage behavior, including:

- filesystem overhead
- kernel I/O scheduling
- controller queues
- RAID reconstruction
- SSD garbage collection
- flash wear
- thermal throttling
- network storage protocol overhead
- multi-tenant contention
- tail-latency distributions
- durability guarantees
- replication
- synchronization barriers

Real infrastructure decisions should therefore combine this model with workload traces and controlled benchmarks.

A production benchmark should measure at least average latency, percentile latency, IOPS, throughput, queue depth, CPU consumption, cache behavior, and workload-specific error rates.

## Architectural Relationship

The complete model can be viewed as:

`Workload requirements`
→ `IOPS / throughput / latency analysis`
→ `cache strategy`
→ `storage-tier evaluation`
→ `cost constraint`
→ `selected storage`
→ `measured workload`
→ `capacity decision`

Caching is an optimization layer, not a replacement for suitable storage.

Storage tiers provide different performance and cost characteristics.

IOPS and throughput describe capacity from different perspectives.

Latency describes the time dimension of individual operations.

Cost-performance optimization connects these technical properties to an operational capacity decision.
