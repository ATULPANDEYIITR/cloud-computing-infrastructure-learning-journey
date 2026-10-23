# Content Delivery Networks: Edge Locations, Caching, Distribution, Invalidation, and Latency

## Scope

This project models a Content Delivery Network as a distributed content-delivery layer between clients and an authoritative origin.

The central relationship is:

Client → nearest suitable edge → cache lookup → origin when required

The five implementations use different technical perspectives:

| File | Perspective | Primary responsibility |
|---|---|---|
| Python | CDN simulation | Model origin content, edge caches, TTL, routing, invalidation, ETags, and cache statistics |
| JavaScript | Event-driven delivery | Model asynchronous origin access, cache behavior, validators, private content, and public cache keys |
| C++17 | Performance and policy engine | Combine edge-cache behavior with a repository-style governance scenario for merge and deployment decisions |
| Java 17 | Enterprise domain model | Represent cache policies, content classes, edge locations, origin state, immutable domain records, and delivery services |
| PostgreSQL | Relational infrastructure model | Persist origins, content versions, edge caches, requests, policies, invalidations, and cache-health reports |

The implementations deliberately distinguish the **origin**, **edge location**, **cache entry**, **request**, **cache policy**, and **invalidation operation**. These are related objects but have different responsibilities.

---

## CDN Architecture

A CDN does not normally replace the origin. It reduces the number of requests that must travel to the origin by keeping copies of content at geographically distributed edge locations.

A simplified request path is:

Client  
→ DNS or traffic-routing layer  
→ geographically appropriate edge  
→ cache lookup  
→ cached object if fresh  
→ origin fetch if missing or stale  
→ edge cache population  
→ response to client

An edge location is a physical or logical point of presence containing infrastructure capable of serving cached content. The closest edge is not always selected solely by geographic distance. Real systems can also consider network topology, congestion, availability, routing policy, health, capacity, and real-time latency.

The implementations use simplified regional latency tables so that the behavior remains deterministic and executable without requiring an external routing service.

---

## Edge Locations

The Python, JavaScript, C++, and Java implementations represent edge locations explicitly.

Typical modeled locations include:

| Edge | Region | Purpose |
|---|---|---|
| `delhi-1` | India | Low-latency delivery to Indian clients |
| `frankfurt-1` | Europe | European delivery |
| `virginia-1` | North America | North American delivery |

An edge has a finite object capacity in the simulations. When the capacity is reached, the implementations evict an object according to a simple expiration-oriented policy.

This is intentionally simpler than a production CDN cache replacement algorithm. Real systems can use variants of LRU, LFU, segmented caching, admission policies, object-size awareness, popularity prediction, or proprietary policies.

The important architectural distinction is that an edge stores **copies**, not authoritative content.

---

## Origin Content

The origin is the source of truth.

The model stores content using:

- a path
- content
- content type
- version
- ETag
- publication time
- content classification

A new origin version does not automatically mean that every edge immediately contains the new version.

For example:

`/assets/app.js`

can exist as:

- origin version 1
- cached version 1 at Delhi
- cached version 1 at Frankfurt
- cached version 1 at Virginia

After the origin publishes version 2, those edge copies can remain valid according to their cache policy until:

- their TTL expires
- an invalidation is issued
- a revalidation detects a newer representation
- a cache policy forces bypassing

This distinction is essential to understanding cache consistency.

---

## Caching

Caching stores a previously retrieved representation close to clients.

A cache entry in the implementations contains information such as:

- content body or reference
- ETag
- content version
- creation time
- expiration time
- access information

A request produces a cache hit when a usable cached entry exists.

A cache miss occurs when:

- the object has never been cached
- the entry has expired
- the entry has been invalidated
- caching is deliberately bypassed

The Python implementation represents this using `CacheStatus`.

The JavaScript implementation uses asynchronous delivery so an origin request behaves like network I/O.

The Java implementation separates cache storage from the higher-level delivery service.

The PostgreSQL implementation persists cache entries and derives their effective state from timestamps and explicit invalidation state.

---

## Cache-Control and TTL

TTL means Time To Live.

A cache entry with a 60-second TTL can be considered fresh for 60 seconds from the point at which it was stored.

A simplified lifecycle is:

`MISS → ORIGIN FETCH → CACHE STORE → HIT → EXPIRATION → STALE → REFETCH`

TTL is a trade-off.

A longer TTL generally provides:

- fewer origin requests
- lower origin bandwidth consumption
- lower request latency
- greater tolerance for temporary origin failures

A shorter TTL generally provides:

- faster propagation of origin changes
- less stale content
- more origin traffic
- greater dependence on origin availability

The correct TTL depends on the content.

Static versioned assets can often have very long TTLs.

Dynamic API responses generally need shorter TTLs.

Private or user-specific responses normally should not enter a shared public cache without a carefully designed cache policy.

---

## Immutable and Versioned Assets

One of the most useful CDN deployment patterns is content-addressed or versioned asset naming.

Instead of repeatedly modifying:

`/assets/app.js`

a deployment can publish:

`/assets/app.a91f42d7.js`

A changed file receives a different name.

The old URL can therefore remain cached for a long time without creating ambiguity.

The Java implementation explicitly validates versioned static asset names when the configured cache policy requires them.

This approach reduces the operational dependence on large-scale cache invalidation.

The basic relationship is:

`content change → new URL → independent cache object`

rather than:

`content change → same URL → invalidate every edge`

This is especially valuable for JavaScript, CSS, images, fonts, and other static deployment artifacts.

---

## Cache Invalidation

Invalidation explicitly removes or marks cached content as unusable.

The implementations support path-based invalidation and, where appropriate, prefix invalidation.

A single-object invalidation targets:

`/assets/app.js`

A prefix invalidation can target:

`/images/`

and therefore affect multiple objects.

Invalidation is useful when content is mutable and users must see a new version before normal TTL expiration.

It also introduces an operational trade-off.

Broad invalidation can cause a large number of cache misses immediately after deployment:

`many invalidations → many origin requests → origin traffic spike`

This is commonly called a cache stampede or thundering-herd condition when many requests simultaneously require the same uncached content.

Versioned assets reduce the need for broad invalidation.

---

## ETags and Conditional Validation

The Python, JavaScript, and Java implementations use ETags to model representation validation.

An ETag identifies a particular representation.

A client can provide the previously received ETag during a conditional request.

Conceptually:

`If-None-Match: "representation-etag"`

If the representation has not changed, the server can respond with a not-modified result instead of transferring the entire body.

This provides a different mechanism from ordinary cache hits.

A cache hit answers:

> Can this edge serve the currently cached representation?

Conditional validation answers:

> Does the representation identified by this validator still match the requested representation?

ETags are especially useful when a resource cannot use a long immutable cache lifetime.

---

## Cache Keys

A CDN needs a deterministic way to decide whether two requests represent the same cacheable resource.

For example:

`/products?page=2&language=en`

can be a different cache object from:

`/products?page=3&language=en`

The JavaScript implementation builds a public cache key from explicitly allowed parameters.

Tracking identifiers are deliberately excluded.

This matters because uncontrolled cache keys can cause:

- excessive cache fragmentation
- poor hit ratios
- unbounded cache growth
- accidental exposure of user-specific information

Authentication tokens, private cookies, authorization headers, and other user-specific state require particular care.

A public cache must never accidentally serve one user's personalized response to another user.

---

## Public Versus Private Content

The implementations distinguish public content from private content.

Public static content is suitable for shared edge caching when its cache policy permits it.

Public dynamic content can be cached when the application explicitly defines safe caching semantics.

Private content should normally bypass a shared public cache unless the caching design explicitly accounts for user identity and authorization.

The JavaScript implementation models private responses using a cache bypass path.

This distinction is a security boundary, not merely a performance optimization.

A cache configuration that improves latency while mixing user-specific data into a shared cache can create a serious confidentiality problem.

---

## Latency Reduction

The principal performance benefit of a CDN is reducing the network distance between the client and the content-serving infrastructure.

The simulations use simplified latency values such as:

| Client region | Suitable edge | Approximate modeled latency |
|---|---|---:|
| India | India | 20 ms |
| Europe | Europe | 25 ms |
| North America | North America | 25 ms |
| India | Europe | 115 ms |
| India | North America | 210 ms |

The numbers are illustrative rather than measurements of a real provider.

The important behavior is the relative difference.

A cache hit can avoid the additional origin round trip:

`Client → Edge`

instead of:

`Client → Edge → Origin → Edge → Client`

The exact latency improvement depends on routing, network congestion, TLS behavior, object size, connection reuse, protocol version, edge load, origin location, and many other factors.

---

## Python Implementation

The Python program models the CDN as an executable simulation.

`OriginServer` is authoritative and maintains versioned objects.

`EdgeCache` manages entries for one edge location and performs:

- lookup
- TTL evaluation
- insertion
- invalidation
- prefix invalidation
- simple capacity-based eviction

`ContentDeliveryNetwork` performs:

- edge selection
- request processing
- origin retrieval
- cache population
- invalidation
- statistics collection

The simulation demonstrates an important deployment sequence:

`cache version 1 → origin publishes version 2 → old edge copy remains → explicit invalidation → edge fetches version 2`

The script also demonstrates ETag-based validation and safe public cache-key construction.

The temporary-file example shows how immutable asset naming can be represented with a content hash without requiring an external build system.

---

## JavaScript Implementation

The JavaScript version uses an event-driven model.

The origin `fetch` method is asynchronous and introduces a small artificial delay to represent network I/O.

This makes the cache decision independent from the mechanics of synchronous local computation.

The implementation distinguishes:

- `HIT`
- `MISS`
- `STALE`
- `BYPASS`

It also models:

- ETag validation
- private-content bypass
- stale-on-origin-error behavior
- bounded edge storage
- prefix invalidation
- public cache-key construction

The stale-on-error behavior is explicitly opt-in. Serving stale content during an origin failure can improve availability, but it should be a deliberate policy because the content may no longer be current.

---

## C++17 Implementation

The C++ implementation emphasizes deterministic data structures and explicit performance-oriented control.

`ContentDeliveryNetwork` stores:

- origin content
- version information
- edge caches
- latency information
- request counters
- origin-fetch counters

The cache uses hash maps for direct path lookup.

When an edge reaches capacity, the simulation selects an entry with the earliest expiration time for eviction.

This is not intended to reproduce a production CDN's internal cache algorithm. It provides a deterministic model of bounded cache storage.

The program also includes a separate repository-governance case study because deployment governance affects CDN content publication. The governance engine evaluates:

- protected branches
- required approvals
- reviewer eligibility
- required status checks
- unresolved conversations
- merge conflicts

This creates a realistic connection between software delivery and CDN deployment:

`approved change → deployment → new origin content → cache strategy`

The governance model remains technically distinct from the CDN cache itself.

---

## Java 17 Implementation

The Java implementation uses explicit domain types and enterprise-oriented service boundaries.

Records represent immutable value-oriented structures such as:

- edge locations
- origin objects
- cache entries
- delivery results
- cache policies

Enums distinguish content classes and cache states.

`OriginRepository` defines the origin abstraction, while `InMemoryOrigin` provides the executable implementation.

`ContentDeliveryNetwork` owns edge selection and cache delivery.

`RepositoryDeliveryService` adds a higher-level policy boundary for versioned static assets.

This separation prevents infrastructure details from becoming mixed with application-level delivery policy.

The static asset policy demonstrates a common enterprise rule:

`PUBLIC_STATIC + long TTL + versioned path`

Private content follows a separate path and bypasses shared caching.

---

## PostgreSQL Implementation

The SQL implementation models CDN infrastructure as relational state.

The core entities are:

| Table | Responsibility |
|---|---|
| `regions` | Geographic delivery regions |
| `edge_locations` | CDN edge infrastructure |
| `origins` | Authoritative content sources |
| `content_objects` | Versioned origin representations |
| `cache_entries` | Per-edge cached representations |
| `requests` | Delivery observations |
| `cache_invalidations` | Invalidation operations and impact |
| `cache_policies` | Content-class caching rules |

The database enforces important invariants using:

- primary keys
- foreign keys
- unique constraints
- check constraints
- partial unique indexes

The partial unique index on active content guarantees one active origin representation per path.

This is important because application code should not be the only protection against contradictory authoritative state.

---

## PostgreSQL Functions

`publish_content` creates a new origin version and supersedes the previous active version.

The function generates a deterministic ETag from the path, version, and content.

`cache_lookup` evaluates whether an entry is fresh.

`invalidate_path` marks matching cache entries invalidated and records the operation.

`invalidate_prefix` performs broader invalidation for a path namespace.

The invalidation functions run as ordinary database functions and can be called inside explicit transactions.

The deployment example uses:

`BEGIN → publish → invalidate → COMMIT`

This prevents the database workflow from leaving half of the deployment operation committed if an error occurs before the transaction completes.

---

## Cache Consistency

CDNs generally favor controlled eventual consistency for cached content rather than requiring every edge to synchronously reflect every origin update.

The implementations expose three important states:

| State | Meaning |
|---|---|
| Fresh | Cached representation can be served according to its TTL |
| Stale | Cached representation exists but its freshness lifetime has ended |
| Invalidated | Cached representation has been explicitly marked unusable |

The origin version can therefore differ temporarily from an edge version.

The difference is intentional and must be governed by the cache policy.

For frequently changing content, shorter TTLs or validation can reduce the inconsistency window.

For immutable content, long TTLs are safe because a changed representation receives a different URL.

---

## Latency Versus Freshness

Caching decisions are fundamentally a trade-off between latency, origin load, and freshness.

| Strategy | Latency | Origin load | Freshness behavior |
|---|---|---|---|
| No caching | Highest | Highest | Immediate origin state |
| Short TTL | Low after warm-up | Moderate | Relatively fresh |
| Long TTL | Very low | Low | Potentially stale |
| Immutable assets | Very low | Very low | New URL represents new content |
| Explicit invalidation | Low after warm-up | Can spike | Fast propagation when invalidation succeeds |
| Conditional validation | Moderate | Lower body transfer | Explicit freshness validation |

No single strategy is correct for every content type.

---

## Cache Stampede and Capacity

A cache can become ineffective if many clients request the same object immediately after it expires.

Without request coalescing, many requests can simultaneously reach the origin.

The simplified implementations expose this behavior conceptually but do not implement production-grade request coalescing.

Production systems can use techniques such as:

- request collapsing
- stale-while-revalidate
- stale-if-error
- asynchronous refresh
- probabilistic early refresh
- origin shielding

The correct approach depends on traffic patterns and consistency requirements.

---

## Security Considerations

CDN security is closely tied to cache-key correctness and content classification.

Important controls include:

- never mixing private and public representations accidentally
- preventing authorization state from being ignored by a public cache
- carefully defining which request parameters participate in cache keys
- validating purge and invalidation permissions
- protecting origin endpoints from direct unauthorized access
- using TLS for client-to-edge and edge-to-origin communication
- preventing cache poisoning
- controlling administrative cache invalidation APIs
- monitoring unusual cache-miss and origin-request patterns

Cache invalidation itself is a privileged operation in production infrastructure because broad purges can generate significant origin load.

---

## Performance Characteristics

The simulations use hash-map-based cache lookup.

For a cache lookup by exact path, the expected lookup cost is approximately:

`O(1)`

for hash-based structures.

Prefix invalidation requires examining cached keys in the simple implementations and is approximately:

`O(n)`

where `n` is the number of cached objects at the edge or across the simulated CDN.

The PostgreSQL implementation uses indexes for:

- cache lookup by edge and path
- expiration inspection by edge
- content relationships
- request reporting by path and time

Real CDN implementations require substantially more sophisticated distributed indexing, storage, routing, eviction, replication, and observability systems.

---

## Operational Observability

The implementations expose measurements that are useful for evaluating CDN behavior:

- request count
- cache hits
- cache misses
- origin fetches
- hit ratio
- invalidation count
- edge object count
- request latency

A useful operational relationship is:

`cache hit ratio = cache hits / cache lookups`

A high hit ratio is not automatically evidence of good performance. An application can have a high hit ratio while serving content from an unnecessarily distant edge, while a small number of large origin requests can still consume substantial bandwidth.

Latency, origin load, object size, error rate, and freshness should therefore be evaluated together.

---

## Deployment Workflow

A practical deployment using immutable assets can follow this model:

`build artifact`
→ `calculate content hash`
→ `publish new asset`
→ `update application references`
→ `deploy origin`
→ `serve new URL`
→ `retain old cached assets until expiration`

A mutable content workflow instead requires:

`publish origin`
→ `invalidate affected paths`
→ `edge misses`
→ `origin refetch`
→ `new edge copies`

The first model generally minimizes invalidation traffic.

The second model is useful when URLs cannot be changed or when immediate replacement of a mutable resource is required.

---

## Failure Conditions

The implementations deliberately validate several failure cases.

Invalid paths are rejected.

Empty origin content is rejected.

Negative TTL values are rejected.

Unknown edge locations produce errors.

Requests for missing origin objects fail rather than creating fake cache entries.

Private content bypasses shared caching.

Cache entries that exceed their freshness lifetime are not treated as fresh.

Required versioning can be enforced for static assets.

The PostgreSQL schema prevents invalid relationships and invalid numeric values at the database layer.

These failures are important because CDN infrastructure sits directly on the path between clients and application content. Incorrect cache behavior can produce stale data, availability problems, excessive origin traffic, or confidentiality failures.

---

## Relationship Between the Five Implementations

The five files describe the same CDN domain at different abstraction levels rather than translating one implementation line by line.

The Python implementation emphasizes **simulation and workflow behavior**.

The JavaScript implementation emphasizes **asynchronous delivery and event-driven origin access**.

The C++ implementation emphasizes **bounded data structures, deterministic performance, and deployment governance**.

The Java implementation emphasizes **enterprise domain modeling, immutable records, policy boundaries, and service composition**.

The PostgreSQL implementation emphasizes **persistent infrastructure state, relational integrity, transactional invalidation, and operational reporting**.

Together they model the complete lifecycle:

`Origin publication`
→ `Edge selection`
→ `Cache lookup`
→ `HIT or MISS`
→ `Origin retrieval`
→ `Edge population`
→ `TTL expiration or validation`
→ `Invalidation when required`
→ `Latency and cache-performance measurement`

The key architectural distinction is maintained throughout: the **origin owns authoritative content, edge locations provide geographically distributed copies, caching controls reuse, invalidation controls replacement, and routing determines where delivery occurs**.
