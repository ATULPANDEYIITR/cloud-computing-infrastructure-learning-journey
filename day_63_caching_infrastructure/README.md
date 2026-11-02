# Caching Infrastructure

## Scope

This project models a two-tier caching infrastructure with:

- In-memory application caching
- Distributed caching
- Cache-aside reads and writes
- Write-through updates
- TTL-based expiration
- Cache invalidation
- Version-aware stale-data protection
- Distributed-cache failure handling
- Cache metrics and operational reporting
- Relational persistence for products, cache nodes, policies, and cache events

The implementations use the same domain principle while giving each language a distinct engineering perspective.

## Architectural Model

The authoritative product state is stored in a repository or relational database.

The cache hierarchy is:

    Authoritative Store
           |
           v
    Distributed Cache
           |
           v
      Local Cache
           |
           v
       Application

A local cache minimizes latency for requests handled by one application instance.

A distributed cache allows multiple application instances to share cached values.

The authoritative store remains the source of truth. A cache entry is eligible for use only when it is not expired and its stored version is not older than the authoritative version.

## Cache-Aside

Cache-aside separates database updates from cache population.

A read follows this sequence:

    Request
       |
       v
    Local Cache
       |
     miss
       v
    Distributed Cache
       |
     miss/stale
       v
    Authoritative Store
       |
       v
    Populate Cache
       |
       v
    Return Value

A successful update follows:

    Update Database
          |
          v
    Invalidate Cache
          |
          v
    Future Read Repopulates Cache

This strategy avoids requiring every database write to synchronously populate every cache tier.

Its main risk is the interval between an authoritative update and cache invalidation. The implementations reduce this risk by performing invalidation immediately after the successful update.

## Write-Through

Write-through updates the authoritative store and immediately refreshes the cache.

The workflow is:

    Application Write
          |
          v
    Authoritative Store
          |
          v
    Local Cache
          |
          v
    Distributed Cache

This gives subsequent readers a fresh cache representation without waiting for a cache miss.

The trade-off is greater write latency and a stronger dependency on cache-write operations.

The examples treat the authoritative database update as durable even when the distributed cache is temporarily unavailable. A later cache miss can repopulate the distributed tier.

## In-Memory Caching

The Python implementation uses a thread-safe `InMemoryCache` backed by a dictionary.

The JavaScript implementation uses `Map`.

The C++ implementation uses `std::unordered_map`.

The Java implementation uses `ConcurrentHashMap`.

Each local cache supports:

- Key lookup
- TTL expiration
- Insertion
- Deletion
- Capacity enforcement
- Version metadata

The local cache is deliberately short-lived compared with the distributed cache. This reduces the lifetime of stale process-local data while preserving the latency benefit of local memory.

## Distributed Cache

The distributed cache represents a service shared by multiple application instances.

The Python implementation serializes values as JSON before storing them.

The JavaScript implementation uses JSON serialization as an explicit remote-cache boundary.

The C++ and Java implementations model the distributed service as an independent cache component with availability failure states.

A production distributed cache would normally provide persistence, replication, network communication, atomic operations, and service-level monitoring. The examples focus on the application-side cache semantics rather than implementing a network protocol.

## Cache Keys

The implementations use product-specific cache keys.

The Python implementation derives a deterministic SHA-256-based identifier from the logical product key.

The JavaScript implementation uses Node.js `crypto` to derive a SHA-256 digest.

The C++ and Java examples use structured product identifiers.

Cache keys should not contain uncontrolled sensitive information. Stable namespaces such as `product:<identifier>` also reduce collisions between unrelated cache domains.

## TTL and Expiration

TTL limits how long an entry remains eligible for use.

The local and distributed layers use different TTL values.

For example:

| Layer | Typical Role | Example TTL |
|---|---|---:|
| Local | Lowest latency | 30 seconds |
| Distributed | Shared reuse | 120 seconds |
| Database | Authoritative state | No cache TTL |

The Python and JavaScript demonstrations use short TTLs so expiration can be observed during execution.

TTL is a safety mechanism, not a complete invalidation strategy. A long TTL can still expose stale data, while an immediate invalidation can remove an entry before its TTL expires.

## Version-Based Stale Protection

Each product has a monotonically increasing version.

An update changes:

    version N
       |
       v
    version N + 1

A cache entry records the version it represents.

A cached entry is rejected when:

    cached_version < authoritative_version

This prevents an older distributed entry from replacing a newer representation in the local cache.

Version checks are especially important when multiple application instances can populate the same distributed cache concurrently.

The database remains authoritative because cache versions are compared against the current persistent record before an uncertain remote entry is promoted.

## Cache Invalidation

Invalidation removes an entry after an authoritative change.

The PostgreSQL implementation provides `invalidate_product_cache`, which deletes all cache entries associated with a product and records an invalidation event.

The application implementations invalidate both local and distributed layers.

Distributed invalidation can fail when the remote service is unavailable. The failure is recorded rather than treating the cache as the authoritative data source.

## Failure Handling

The implementations cover several failure conditions.

### Distributed Cache Unavailable

The distributed cache can become unavailable.

The application then falls back to the authoritative repository.

This preserves correctness at the cost of higher latency and database load.

### Expired Entry

An expired entry is deleted or ignored.

The application retrieves a fresh authoritative value and repopulates the cache.

### Stale Entry

A cache entry with an older version is rejected.

The application reads the authoritative record rather than trusting the stale cache.

### Missing Product

A product lookup can return no record.

The cache is not populated with an invented value.

### Invalid Data

Negative prices and negative stock values are rejected.

The PostgreSQL database reinforces the same rule through `CHECK` constraints.

## Python Implementation

The Python program is a repository-oriented cache simulation.

Important components include:

| Component | Responsibility |
|---|---|
| `Product` | Immutable-style product data representation |
| `ProductRepository` | Authoritative data store |
| `InMemoryCache` | Thread-safe local cache |
| `DistributedCache` | Serialized remote-cache simulation |
| `CacheService` | Cache policy orchestration |
| `CacheMetrics` | Operational measurements |

The `CacheService.get_product` method implements a local-cache lookup, distributed-cache lookup, version validation, authoritative fallback, and cache population sequence.

`update_product_cache_aside` demonstrates database-first modification followed by invalidation.

`write_through_product` updates the repository and immediately refreshes both cache tiers.

The program also exercises distributed-cache failure, TTL expiration, invalid input, cache misses, cache hits, and metric reporting.

## JavaScript Implementation

The JavaScript implementation emphasizes event-driven processing and asynchronous execution.

`LocalCache` uses `Map` while `DistributedCache` models a remote serialization boundary.

`CacheService` provides:

- Cache-aside updates
- Write-through updates
- Event-driven invalidation
- Version validation
- Distributed failure recovery
- Metrics

The program processes explicit product-change events:

    PRODUCT_PRICE_CHANGED
              |
              v
       Repository Update
              |
              v
          Invalidate

and:

    PRODUCT_STOCK_CHANGED
              |
              v
       Repository Update
              |
              v
          Invalidate

The asynchronous `sleep` function demonstrates TTL expiration without external packages.

## C++17 Implementation

The C++ program models caching as a strongly typed infrastructure service.

`Product`, `CacheEntry`, and `Metrics` are explicit structures.

`ProductRepository`, `LocalCache`, `DistributedCache`, and `MergeEligibilityEngine` separate persistence, cache tiers, and orchestration.

The implementation uses:

- `std::unordered_map`
- `std::optional`
- `std::chrono`
- `std::runtime_error`
- `std::exception`
- STL containers and standard algorithms

`std::optional` makes missing products explicit.

`std::chrono::steady_clock` provides a monotonic time source for TTL handling, avoiding dependence on wall-clock adjustments.

The distributed cache exposes an explicit availability state, allowing the program to test degraded operation without introducing external infrastructure.

## Java 17 Implementation

The Java implementation uses explicit domain types and immutable records.

The `Product` record validates its own invariants.

`CacheEntry<T>` provides a generic cache representation.

`CacheStore<T>` defines the common cache contract.

`InMemoryCache<T>` and `DistributedCache<T>` implement that contract independently.

`ProductRepository` owns authoritative state.

`CacheService` implements the application-level policies.

`ConcurrentHashMap` provides concurrent map operations, while `AtomicLong` supports thread-safe operational counters.

The Java implementation separates:

- Domain data
- Cache abstractions
- Cache implementations
- Repository operations
- Cache orchestration
- Metrics

This structure is suitable for an enterprise service where caching policy should remain separate from individual storage implementations.

## PostgreSQL Implementation

The PostgreSQL implementation represents caching infrastructure relationally.

The main entities are:

| Table | Purpose |
|---|---|
| `repositories` | Repository metadata |
| `branches` | Repository branch state |
| `products` | Authoritative application data |
| `cache_nodes` | Local and distributed cache nodes |
| `cache_entries` | Cached product representations |
| `cache_events` | Operational cache history |
| `cache_policies` | Cache strategy and TTL configuration |

The repository and branch tables establish a realistic application-governance context, while the cache-specific tables model the infrastructure itself.

The `products.version` column changes automatically through a trigger.

The `reject_stale_cache_entry` trigger prevents insertion of a cache record whose version is older than the current authoritative product version.

This moves an important correctness rule into the database rather than relying exclusively on application code.

## PostgreSQL Cache-Aside Workflow

The function `cache_aside_update_product`:

1. Validates product values.
2. Updates the authoritative product.
3. Uses the product trigger to advance its version.
4. Invalidates all cache entries for that product.
5. Records the write event.
6. Returns the updated product.

The function runs inside the caller's transaction.

## PostgreSQL Write-Through Workflow

The procedure `write_through_product`:

1. Reads the active write-through policy.
2. Validates the new product values.
3. Updates the authoritative product.
4. Retrieves the new version.
5. Refreshes the local cache entry.
6. Refreshes the distributed cache entry.
7. Records the write event.

The `ON CONFLICT` clauses make cache refreshes idempotent for a given node and key.

## Database Constraints

Database-level constraints include:

- Primary keys
- Foreign keys
- Unique cache keys per node
- Non-negative product prices
- Non-negative stock
- Positive product versions
- Positive cache capacities
- Valid TTL relationships
- Enumerated cache strategies
- Enumerated cache layers
- Enumerated cache event types

These constraints reduce the amount of invalid state that can enter the system.

## Reporting and Evaluation

The PostgreSQL views provide operational inspection.

`active_cache_entries` combines cached state with authoritative product versions.

`cache_health_report` aggregates:

- Available cache nodes
- Cache entry counts
- Expired entries
- Stale entries

The query section demonstrates:

- Authoritative retrieval
- Cache retrieval
- Stale-entry validation
- Event aggregation
- Cache eligibility evaluation
- Node health reporting
- Policy inspection
- Failure-event analysis

## Performance Considerations

A successful local cache lookup is approximately O(1) for hash-based cache structures.

A distributed lookup has greater latency because a real implementation normally crosses a network boundary.

A cache hit can therefore avoid:

- Database connection acquisition
- SQL execution
- Disk or buffer-pool access
- Serialization associated with database responses
- Repeated computation of the same representation

The main performance risks are cache misses, excessive invalidation, cache stampedes, oversized values, and a distributed cache becoming a bottleneck.

The examples keep local and distributed TTLs separate so each layer can have an independent freshness and latency trade-off.

## Cache Stampede Consideration

If a frequently requested key expires simultaneously across many application instances, many requests can fall through to the authoritative store.

A production implementation can mitigate this through:

- Request coalescing
- Per-key locks
- Single-flight loading
- Jittered expiration
- Background refresh
- Probabilistic early refresh

These mechanisms are intentionally not hidden inside the basic cache examples because they introduce different concurrency and operational policies.

## Consistency Trade-Offs

Caching introduces a deliberate distinction between latency and freshness.

Cache-aside generally provides simple control and efficient reads but requires careful invalidation.

Write-through improves cache freshness after successful writes but increases write-path complexity.

TTL provides an eventual freshness bound but does not guarantee immediate invalidation.

Version checks strengthen correctness when multiple writers and cache-population paths operate concurrently.

No cache tier is treated as more authoritative than the persistent product record.

## Security Considerations

Cache infrastructure should be treated as an operational data store rather than an inherently trusted boundary.

Relevant controls include:

- Avoiding sensitive information in cache keys
- Restricting cache network access
- Authenticating distributed-cache clients
- Encrypting network traffic
- Applying least-privilege access
- Avoiding unvalidated deserialization
- Limiting cache entry sizes
- Monitoring unusual cache activity
- Preventing cross-tenant key collisions
- Removing sensitive values promptly when required

The examples use controlled JSON serialization in the Python and JavaScript distributed-cache models rather than arbitrary executable object deserialization.

## Implementation Relationship

The five implementations share the same conceptual separation:

    Authoritative Data
          |
          +--------------------+
          |                    |
          v                    v
    Cache-Aside           Write-Through
          |                    |
          v                    v
     Invalidate             Refresh
          |                    |
          +---------+----------+
                    |
                    v
              Cache Tiers

Python focuses on repository and cache behavior.

JavaScript focuses on asynchronous and event-driven cache operations.

C++17 focuses on strongly typed infrastructure and explicit failure handling.

Java 17 focuses on enterprise domain modeling, generic cache abstractions, immutable records, and concurrent structures.

PostgreSQL focuses on durable modeling, constraints, triggers, transactional workflows, policy storage, and operational reporting.

## Practical Distinctions

| Mechanism | Primary responsibility |
|---|---|
| In-memory cache | Fast process-local reads |
| Distributed cache | Shared cached state across instances |
| Cache-aside | Application-controlled read population and invalidation |
| Write-through | Cache refresh as part of the write path |
| TTL | Time-based freshness boundary |
| Invalidation | Explicit removal after authoritative changes |
| Versioning | Detection and rejection of stale representations |
| Metrics | Operational visibility into cache behavior |

The architecture works because these mechanisms solve different problems. A distributed cache does not replace invalidation, TTL does not replace version validation, and write-through is a write policy rather than a cache storage technology.
